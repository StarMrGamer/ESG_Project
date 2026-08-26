import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import type { Settings } from '../../store'
import type { Board } from '../../types'
import { TOUR, subjectFor, type Cue, type Driver, type Step } from './tour'

/**
 * The clicker. One overlay, one keypress forward, the real application underneath.
 *
 * Why an overlay driving the live app rather than a deck of slides: the whole pitch is that this
 * thing works. A slide of a screenshot of the thing working is a strictly weaker claim, and the
 * first question from the floor is always whether it is real. Here the room watches the board
 * re-segment, the model get asked, and the hash break — because those are all happening.
 *
 * Interact mode is the escape hatch and it matters more than it looks. When a judge interrupts
 * with "can you show me a different company", a presenter locked inside a fixed track has to
 * either say no or drop the deck. `i` unlocks the app in place, `i` again resumes on the same
 * step. Nothing is lost.
 */

/**
 * Read the cue figures off the loaded run.
 *
 * Nothing here is typed into the tour: the universe size, the pipeline count, the disagreement,
 * the trail length, how many signals are load-bearing and which sub-signal dissents all come
 * from the same endpoints the panels behind them are drawing. That is what lets one tour be
 * correct in both the live basket and the fictional demo set, whose figures differ throughout.
 */
async function buildCue(demo: boolean, subject: string, board: Board | null): Promise<Cue> {
  const base: Cue = {
    demo, company: subject, disagreement: 0, signals: 0, flips: 0, flipSet: null,
    dissent: null, split: null,
    universe: board?.counts.total ?? 0,
    pipeline: Number((board?.engine as { nmk?: { M?: number } } | undefined)?.nmk?.M ?? 0),
  }
  try {
    const [ev, sens] = await Promise.all([
      api.evidence(subject, demo, 'long'),
      api.sensitivity(subject, demo, 'long').catch(() => null),
    ])
    const trail = ev.trail ?? []
    base.company = ev.company ?? subject
    base.disagreement = Number(ev.record?.disagreement ?? 0)
    base.signals = trail.length
    base.flips = sens?.load_bearing_count ?? 0
    base.flipSet = sens?.smallest_flip_set ?? null

    // The one that disagrees: the most negative sub-signal on the board's own breakdown.
    let worst: { label: string; value: number } | null = null
    for (const [, subs] of Object.entries(ev.subcomponents ?? {})) {
      for (const [name, v] of Object.entries(subs as Record<string, { momentum?: number }>)) {
        const m = Number(v?.momentum ?? 0)
        if (m < 0 && (!worst || m < worst.value)) worst = { label: name.replace(/_/g, ' '), value: m }
      }
    }
    base.dissent = worst

    // A pillar arguing with itself is a stronger point than a lone negative, so prefer it when
    // one exists: it is evidence being contested rather than simply absent.
    const by: Record<string, { up: number; down: number }> = {}
    for (const t of trail) {
      const k = String((t as { component?: string }).component ?? '')
      if (!k) continue
      by[k] ??= { up: 0, down: 0 }
      if (Number((t as { direction?: number }).direction ?? 0) < 0) by[k].down++
      else by[k].up++
    }
    const split = Object.entries(by)
      .filter(([, v]) => v.up > 0 && v.down > 0)
      .sort((a, b) => (b[1].up + b[1].down) - (a[1].up + a[1].down))[0]
    if (split) {
      base.split = { pillar: split[0], up: split[1].up, down: split[1].down,
                     total: split[1].up + split[1].down }
    }
  } catch { /* a cue is a prompt, not a gate — the tour runs without one */ }
  return base
}

/** The sticky header, and the present bar's own footprint. */
const HEADER_H = 62
const BAR_H = 170

/**
 * `scrollIntoView({block: 'center'})` centres against the WHOLE viewport, which is wrong twice
 * here: the top is under a sticky header and the bottom ~170px is under the present bar. On a
 * panel taller than what is left — the evidence trail is — centring pushes its heading off the
 * top of the screen, so the step that says "fourteen signals, each one dated" scrolled past the
 * dates. Tall anchors pin their top instead; short ones centre in the free band.
 */
function anchorTarget(el: Element): number {
  const free = window.innerHeight - HEADER_H - BAR_H
  const r = el.getBoundingClientRect()
  const top = r.top + window.scrollY
  return Math.max(0, r.height > free
    ? top - HEADER_H - 16
    : top - HEADER_H - Math.max(12, (free - r.height) / 2))
}

/**
 * Align, then KEEP aligning for a moment.
 *
 * A deep dive mounts and then grows: the LSEG panel fetches the live incumbent rating and the
 * benchmark strip fetches a quote, and both land ABOVE the relay a second or two later. A
 * one-shot scroll computed before they arrive leaves the anchor a thousand pixels below the
 * fold — measured, on the step whose whole job is to point at the relay. So the alignment is
 * re-checked while the page settles, and gives up the moment it has been stable twice or the
 * presenter has taken the wheel.
 */
function trackAnchor(anchor: string, alive: () => boolean) {
  let stable = 0
  let expected = -1
  const tick = () => {
    if (!alive()) return
    const el = document.querySelector(`[data-tour="${anchor}"]`)
    if (!el) return
    // The presenter scrolled somewhere themselves — stop fighting them.
    if (expected >= 0 && Math.abs(window.scrollY - expected) > 120) return
    const target = anchorTarget(el)
    if (Math.abs(target - window.scrollY) < 24) { if (++stable >= 2) return }
    else stable = 0
    expected = target
    window.scrollTo({ top: target, behavior: 'smooth' })
  }
  tick()
  const ids = [400, 900, 1500, 2200, 3000].map(ms => window.setTimeout(tick, ms))
  return () => ids.forEach(clearTimeout)
}

/** Rings the element a step points at. Purely decorative — never eats a click. */
function Spotlight({ anchor }: { anchor: string | undefined }) {
  const [box, setBox] = useState<DOMRect | null>(null)

  useLayoutEffect(() => {
    if (!anchor) { setBox(null); return }
    let raf = 0
    const measure = () => {
      const el = document.querySelector(`[data-tour="${anchor}"]`)
      setBox(el ? el.getBoundingClientRect() : null)
      raf = requestAnimationFrame(measure)
    }
    // Tracked per frame rather than on scroll/resize listeners: the ring has to stay glued to a
    // panel that is being smooth-scrolled AND may still be growing as its data lands.
    raf = requestAnimationFrame(measure)
    return () => cancelAnimationFrame(raf)
  }, [anchor])

  if (!box || box.width === 0) return null
  return (
    <div className="present-ring" style={{
      top: box.top - 8, left: box.left - 8, width: box.width + 16, height: box.height + 16,
    }} />
  )
}

/** What a cue function sees before the fetch lands — figures read as unknown, never as zero facts. */
const EMPTY_CUE: Cue = { demo: false, universe: 0, pipeline: 0, company: 'this company',
  disagreement: 0, signals: 0, flips: 0, flipSet: null, dissent: null, split: null }

/** A cue line is either fixed copy or a function of the loaded run. */
const cueText = (s: Step, cue: Cue | null) =>
  typeof s.say === 'function' ? s.say(cue ?? EMPTY_CUE) : s.say

export default function Present({ onExit }: { onExit: () => void }) {
  const store = useStore()
  const [i, setI] = useState(0)
  const [interactive, setInteractive] = useState(false)
  const [showScript, setShowScript] = useState(true)
  const restore = useRef<Settings | null>(null)
  const stopTracking = useRef<(() => void) | null>(null)
  const step = TOUR[i]
  const subject = subjectFor(store.settings.demo)
  const [cue, setCue] = useState<Cue | null>(null)

  // Refreshed when the universe changes, so switching demo/live mid-session re-reads every
  // figure rather than narrating the other basket's numbers.
  useEffect(() => {
    let dead = false
    void buildCue(store.settings.demo, subject, store.board)
      .then(c => { if (!dead) setCue(c) })
    return () => { dead = true }
  }, [store.settings.demo, subject, store.board])

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

  // Run the step: drive the app, let it paint, then bring the anchor into view.
  useEffect(() => {
    let dead = false
    const go = async () => {
      try { await step.act?.(driver) } catch { /* a step must never strand the presenter */ }
      await new Promise(r => setTimeout(r, step.settle ?? 220))
      if (dead || !step.anchor) return
      stopTracking.current?.()
      stopTracking.current = trackAnchor(step.anchor, () => !dead)
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
        case 's': case 'S': setShowScript(v => !v); break
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

      <div className={`present-bar ${interactive ? 'is-interactive' : ''}`}>
        <div className="present-rail" role="progressbar" aria-valuenow={i + 1} aria-valuemin={1}
          aria-valuemax={TOUR.length}>
          {TOUR.map((s, n) => (
            <button key={n} className={`present-tick ${n === i ? 'on' : n < i ? 'done' : ''}`}
              title={`${s.chapter} — ${cueText(s, cue).slice(0, 60)}…`} onClick={() => setI(n)} />
          ))}
        </div>

        <div className="present-body">
          <div className="present-meta">
            <span className="present-chapter">{step.chapter}</span>
            <span className="present-count">{i + 1} / {TOUR.length}</span>
            {step.live && <span className="present-live">LIVE · you drive this one</span>}
            {interactive && <span className="present-free">INTERACT · the app is yours · i to resume</span>}
            <span className="present-keys">
              <b>→</b> next · <b>←</b> back · <b>i</b> interact · <b>s</b> cue · <b>esc</b> exit
            </span>
          </div>

          {showScript && <p className="present-say">{cueText(step, cue)}</p>}

          <div className="present-actions">
            <button className="btn" onClick={prev} disabled={i === 0} title="← / PageUp">←</button>
            <button className="btn btn-primary" onClick={next}
              disabled={i === TOUR.length - 1} title="→ / Space / click anywhere">Next</button>
            <button className={`btn ${interactive ? 'on' : ''}`} onClick={() => setInteractive(v => !v)}
              title="Unlock the app so you can click it yourself, then press i again (i)">
              {interactive ? 'Resume tour' : 'Interact'}
            </button>
            <button className="btn" onClick={() => setShowScript(v => !v)} title="Hide the cue line (s)">
              {showScript ? 'Hide cue' : 'Show cue'}
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
