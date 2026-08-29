import { useCallback, useEffect, useRef, useState } from 'react'
import { useStore } from '../../store'
import { PRESENT_BAR_H, Spotlight, trackAnchor } from '../../lib/anchor'
import type { Settings } from '../../store'
import RecapCard from './RecapCard'
import { subjectFor, type Driver, type Track, type ViewSpec } from './tour'

/**
 * The clicker. One overlay, one keypress forward, the real application underneath.
 *
 * Why an overlay driving the live app rather than a deck of slides: the whole pitch is that this
 * thing works. A slide of a screenshot of the thing working is a strictly weaker claim, and the
 * first question from the floor is always whether it is real. Here the room watches the board
 * re-segment, the model get asked, and the hash break — because those are all happening.
 *
 * TWO TRACKS, ONE DRIVER. `PITCH` argues the product to a room; `RECAP` (recap.ts) reviews the
 * run that is loaded and ends on a card consolidating what it walked. Everything below is common
 * to both — the absolute-state rule, establishing a view, the ring, the keys, interact mode — so
 * a second walk cost a list of steps rather than a second implementation of the clicker.
 *
 * NO CUE ON SCREEN. The bar carries the ring, the chapter, the position and the controls — and
 * not a word of what to say. A caption of the line the presenter is about to speak gives the room
 * something to read instead of the thing being demonstrated, and it made present mode a slide
 * deck wearing the app as a background. The walk itself is in `docs/pitch/slides.md`; the ticks
 * carry a one-line reminder on hover, for the presenter only.
 *
 * Interact mode is the escape hatch and it matters more than it looks. When a judge interrupts
 * with "can you show me a different company", a presenter locked inside a fixed track has to
 * either say no or drop the deck. `i` unlocks the app in place, `i` again resumes on the same
 * step. Nothing is lost.
 */

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

/**
 * Put the app on the screen a step is about.
 *
 * Only called when the view actually changes, so consecutive steps in one chapter do not
 * remount the panel the presenter is reading. The `reask` press lives here rather than in a
 * single step's `act`, because a warmed company opens on its finished answer — so ANY route
 * into the interrogation, including a jump from the progress ticks, has to ask again.
 */
async function establish(view: ViewSpec, d: Driver) {
  switch (view) {
    case 'board': d.dashboard(); return
    case 'evidence': d.evidence(d.subject); return
    case 'compete': await d.reopen(d.subject, 'compete'); return
    case 'interrogate':
      await d.reopen(d.subject, 'interrogate')
      await sleep(260)
      d.click('reask')
  }
}

export default function Present({ onExit, track }: { onExit: () => void; track: Track }) {
  const store = useStore()
  const TOUR = track.steps
  const [i, setI] = useState(0)
  const [interactive, setInteractive] = useState(false)
  const restore = useRef<Settings | null>(null)
  const stopTracking = useRef<(() => void) | null>(null)
  const shownView = useRef<ViewSpec | null>(null)
  const step = TOUR[i]
  // The pitch walks its rehearsed subject; the recap walks whatever you are looking at, because
  // a recap of the run is a recap of the company on screen. With nothing focused it falls back,
  // so the walk always has something to open.
  const subject = track.subject === 'focused'
    ? (store.focusTicker || subjectFor(store.settings.demo))
    : subjectFor(store.settings.demo)

  // Switching universe mid-tour changes the subject, so whatever deep dive or evidence panel is
  // on screen belongs to the other basket. Force the next step to re-establish.
  useEffect(() => { shownView.current = null }, [subject])

  // Snapshot on the way in, put it back on the way out. A demo should not silently rewrite the
  // settings someone spent the setup flow choosing.
  useEffect(() => {
    restore.current = store.settings
    document.body.classList.add('is-presenting')
    return () => {
      document.body.classList.remove('is-presenting')
      if (restore.current) store.setSettings(restore.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const driver: Driver = {
    subject,
    set: store.setSettings,
    dashboard: store.goDashboard,
    deep: store.openDeepDive,
    evidence: store.openEvidence,
    focus: store.setFocus,
    reopen: async (ticker, mode) => {
      // Via the dashboard, with a real frame in between. DeepDive seeds `s1Done`, `narrowedQ`
      // and `answer` from the cached entry in useState initialisers, which run on MOUNT — so
      // changing only the `mode` prop re-renders a component still holding the last step's
      // stage. Unmounting is what makes each section of the tour start from a known state.
      store.goDashboard()
      await new Promise(r => requestAnimationFrame(() => setTimeout(r, 40)))
      await store.openDeepDive(ticker, mode)
    },
    click: anchor => {
      const el = document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`)
      if (!el) return false
      el.click()
      return true
    },
  }

  // Reset to the first step when the track changes — the two walks share this component, and
  // landing on step 9 of a six-step recap because the pitch was there is not a state anyone asked
  // for.
  useEffect(() => { setI(0); shownView.current = null }, [track])

  /**
   * Run the step: drive the app, let it paint, then bring the anchor into view.
   *
   * ABANDON THE RUN THE MOMENT THE STEP CHANGES. `establish` awaits a real deep-dive open, which
   * is a network round trip and can take seconds; without a check after that await, a step the
   * presenter has already left goes on driving the app and lands its screen on top of the one
   * they are now on. Measured: jumping backwards on the ticks put a deep dive over the board
   * while the bar said "02 · Not knowing where to start", which on a stage is the demo appearing
   * to have a mind of its own.
   *
   * `shownView` is claimed BEFORE the await so two rapid steps do not both establish the same
   * view — and cleared if we were interrupted, because an abandoned establish means nobody knows
   * what is on screen and the next step has to put it right rather than assume.
   */
  useEffect(() => {
    let dead = false
    const go = async () => {
      try {
        if (shownView.current !== step.view) {
          shownView.current = step.view
          await establish(step.view, driver)
          if (dead) { shownView.current = null; return }
        }
        await step.act?.(driver)
        if (dead) return
      } catch { /* a step must never strand the presenter */ }
      await new Promise(r => setTimeout(r, step.settle ?? 220))
      if (dead || !step.anchor) return
      stopTracking.current?.()
      stopTracking.current = trackAnchor(step.anchor, () => !dead, PRESENT_BAR_H)
    }
    void go()
    return () => { dead = true; stopTracking.current?.() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i])

  const next = useCallback(() => setI(n => Math.min(n + 1, TOUR.length - 1)), [])
  const prev = useCallback(() => setI(n => Math.max(n - 1, 0)), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      // Never steal a key from someone typing a question into the live interrogation.
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) {
        if (e.key === 'Escape') (t as HTMLInputElement).blur()
        return
      }
      switch (e.key) {
        case 'ArrowRight': case ' ': case 'PageDown': case 'Enter':
          e.preventDefault(); next(); break
        case 'ArrowLeft': case 'PageUp': case 'Backspace':
          e.preventDefault(); prev(); break
        case 'Home': e.preventDefault(); setI(0); break
        case 'End': e.preventDefault(); setI(TOUR.length - 1); break
        case 'i': case 'I': setInteractive(v => !v); break
        case 'Escape': onExit(); break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev, onExit])

  const chapters = [...new Set(TOUR.map(s => s.chapter))]
  const chapterIdx = chapters.indexOf(step.chapter)

  return (
    <>
      {/*
        The advance layer. Click anywhere = next step, which is what a presenter's thumb expects
        and what a clicker sends. Wheel is forwarded rather than swallowed, so the page still
        scrolls under it — a catcher that also freezes scrolling reads as a broken app.
      */}
      {!interactive && (
        <div className="present-catch" onClick={next}
          onContextMenu={e => { e.preventDefault(); prev() }}
          onWheel={e => window.scrollBy({ top: e.deltaY })} />
      )}
      <Spotlight anchor={step.anchor} />
      {step.summary && <RecapCard ticker={subject} />}

      <div className={`present-bar ${interactive ? 'is-interactive' : ''}`}>
        <div className="present-rail" role="progressbar" aria-valuenow={i + 1} aria-valuemin={1}
          aria-valuemax={TOUR.length}>
          {TOUR.map((s, n) => (
            <button key={n} className={`present-tick ${n === i ? 'on' : n < i ? 'done' : ''}`}
              title={s.note ? `${s.chapter} — ${s.note}` : s.chapter}
              onClick={() => setI(n)} />
          ))}
        </div>

        <div className="present-body">
          <div className="present-meta">
            <span className="present-track">{track.label}</span>
            <span className="present-chapter">{step.chapter}</span>
            <span className="present-count">{i + 1} / {TOUR.length}</span>
            {step.live && <span className="present-live">LIVE · you drive this one</span>}
            {interactive && <span className="present-free">INTERACT · the app is yours · i to resume</span>}
            <span className="present-keys">
              <b>→</b> next · <b>←</b> back · <b>i</b> interact · <b>esc</b> exit
            </span>
          </div>

          <div className="present-actions">
            <button className="btn" onClick={prev} disabled={i === 0} title="← / PageUp">←</button>
            <button className="btn btn-primary" onClick={next}
              disabled={i === TOUR.length - 1} title="→ / Space / click anywhere">Next</button>
            <button className={`btn ${interactive ? 'on' : ''}`} onClick={() => setInteractive(v => !v)}
              title="Unlock the app so you can click it yourself, then press i again (i)">
              {interactive ? 'Resume tour' : 'Interact'}
            </button>
            <button className="btn" onClick={onExit} title="Leave present mode (Esc)">Exit</button>
          </div>
        </div>

        <div className="present-chapters" aria-hidden>
          {chapters.map((c, n) => (
            <span key={c} className={n === chapterIdx ? 'on' : n < chapterIdx ? 'done' : ''}>
              {c.split(' · ')[0]}
            </span>
          ))}
        </div>
      </div>
    </>
  )
}
