import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import type { ModuleKey } from '../store'
import { SHOW_CLIENTS } from '../features'
import type { Level } from '../store'

/**
 * The layering control. Replaces the old Full/Simple pair: two states forced every widget to be
 * either "always on" or "expert only", so the middle ground — charts and rankings without the
 * engine internals — had nowhere to live, and the default landed on everything at once.
 */
const LEVELS: { n: Level; label: string; hint: string }[] = [
  { n: 1, label: 'Preferences', hint: 'The board your setup answers asked for. Add any module from the bar at the foot.' },
  { n: 3, label: 'Everything', hint: 'Every panel: the disagreement matrix, provenance and the evidence trail.' },
]

const RADAR_SVG = (
  <svg width="22" height="22" viewBox="0 0 34 34" aria-hidden>
    <circle cx="17" cy="17" r="15" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <circle cx="17" cy="17" r="9" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <line x1="17" y1="17" x2="29.5" y2="8" stroke="var(--r-pos)" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="17" cy="17" r="3" fill="var(--r-pos)" />
  </svg>
)

export default function Header({ onPresent, onFears, onRecap }:
                               { onPresent?: () => void; onFears?: () => void
                                 onRecap?: () => void }) {
  const { settings, setSettings, board, health, loadSample, uploadFile, toast, goDashboard,
    restartSetup } = useStore()

  /**
   * Open a rail from the header — at ANY level.
   *
   * The rails are a level-3 module, so at Preferences these two buttons used to set `leftOpen` /
   * `rightOpen` and produce nothing: the flag flipped, the gate above it stayed shut, and the
   * control was dead with no way for the reader to know why. A control that silently does nothing
   * is worse than one that is missing.
   *
   * So opening a rail PINS the rails module — the same thing the chip at the foot of the board
   * does — and closing the last open rail unpins it, which keeps the header, the chip and what is
   * actually on screen from ever disagreeing.
   */
  const toggleRail = (side: 'left' | 'right') => {
    const leftOpen = side === 'left' ? !settings.leftOpen : settings.leftOpen
    const rightOpen = side === 'right' ? !settings.rightOpen : settings.rightOpen
    const anyOpen = leftOpen || rightOpen
    const extras: ModuleKey[] = anyOpen
      ? (settings.extras.includes('rails') ? settings.extras : [...settings.extras, 'rails'])
      : settings.extras.filter(k => k !== 'rails')
    setSettings({ leftOpen, rightOpen, extras })
  }
  const fileRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDetailsElement>(null)
  const s = settings

  // A <details> popover rather than managed state: it is a disclosure widget, the browser
  // already gives it keyboard and screen-reader behaviour for free, and the only thing missing
  // is closing when you click past it.
  useEffect(() => {
    const close = (e: MouseEvent) => {
      const el = menuRef.current
      if (el?.open && !el.contains(e.target as Node)) el.open = false
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && menuRef.current) menuRef.current.open = false
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [])

  const pill = s.demo
    ? <span className="cc-live" style={{ color: 'var(--r-amber)', border: '1px solid color-mix(in srgb, var(--r-amber) 50%, transparent)' }}>Demo</span>
    : board?.mode === 'evidence'
      ? <span className="cc-live" style={{ color: 'var(--r-blue)', border: '1px solid color-mix(in srgb, var(--r-blue) 50%, transparent)' }}>Evidence</span>
      : <span className="cc-live" style={{ color: 'var(--r-pos)', border: '1px solid color-mix(in srgb, var(--r-pos) 50%, transparent)' }}>Live</span>

  const tag = s.demo ? 'demo data' : board?.mode === 'evidence' ? 'evidence-based' : 'live'
  const n = board?.counts.total ?? 0
  const industries = board?.industries ?? 0

  const activeTab = (!SHOW_CLIENTS && s.tab === 'clients') ? 'board' : s.tab

  return (
    <header className="cc-header">
      <div className="cc-hdr-wrap" onClick={goDashboard} title="Back to dashboard">
        <div className="cc-brand-mark">{RADAR_SVG}</div>
        <div style={{ minWidth: 0 }}>
          <div className="cc-title2">ASEAN ESG Momentum Radar</div>
          <div className="cc-meta">
            {board?.universe.quarter || ''} · {n} listed · {industries} industries · {tag}
            {health && !health.llm_configured && ' · no DEEPSEEK_API_KEY'}
            {s.profile.label && <> · set up for <b>{s.profile.label}</b></>}
          </div>
        </div>
      </div>
      <div className="cc-hdr-right">
        {pill}
        {board?.fresh && <span className="cc-fresh">↻ {board.fresh}</span>}
      </div>

      <div className="cc-controls">
        {/* Board vs Context is a different question from how much detail. The Context tab holds
            the panels that read the same whichever company is focused — the foundation backtest,
            the pillar momentum series, the industry bar, the five validation cases — so the
            board is only things that answer to a click. */}
        {/* A browser can still be holding `tab: 'clients'` from before the flag went off. The
            board is what actually renders in that case, so the control has to agree with it —
            otherwise no tab reads as selected and the header looks broken. */}
        <div className="seg" role="group" aria-label="Section">
          <button className={`btn ${activeTab === 'board' ? 'on' : ''}`}
            title="The live read: filters, the radar, the verdict and its evidence."
            onClick={() => setSettings({ tab: 'board' })}>Board</button>
          <button className={`btn ${activeTab === 'context' ? 'on' : ''}`}
            title="Method and benchmarks — the same for every company, so they live here."
            onClick={() => setSettings({ tab: 'context' })}>Context</button>
          {/* The long explanation. A tab rather than a help icon: someone deciding whether to
              trust any of this is doing a first-class job, not looking something up. */}
          <button className={`btn ${activeTab === 'manual' ? 'on' : ''}`} data-tour="manual"
            title="What this app does, line by line — read out of the run that is loaded."
            onClick={() => setSettings({ tab: 'manual' })}>How it works</button>
          {/* The book. Its own tab rather than a mode of the board: a client meeting is a
              different job from screening the universe, and the brief is a document, not a
              dashboard. */}
          {SHOW_CLIENTS && (
            <button className={`btn ${activeTab === 'clients' ? 'on' : ''}`}
              title="Your client book and the pre-meeting brief"
              onClick={() => setSettings({ tab: 'clients' })}>Clients</button>
          )}
        </div>
        {/* WHO is reading. First, and on its own, because it changes what every other control
            below it means. */}
        <div className="seg" role="group" aria-label="Audience">
          <button className={`btn ${s.audience === 'investor' ? 'on' : ''}`}
            title="Findings in plain sentences, the desk furniture folded away. The numbers stay one click behind “Show the numbers”."
            onClick={() => setSettings({ audience: 'investor', showNumbers: false, level: 1 })}>
            Investor
          </button>
          <button className={`btn ${s.audience === 'analyst' ? 'on' : ''}`}
            title="The board as built: percentiles, tiers, N/M/K, the run id and the evidence trail."
            onClick={() => setSettings({ audience: 'analyst' })}>
            Analyst
          </button>
        </div>

        <div className="seg" role="group" aria-label="Detail level" data-tour="level">
          {LEVELS.map(l => (
            <button key={l.n} className={`btn ${s.level === l.n ? 'on' : ''}`} title={l.hint}
              onClick={() => setSettings({ level: l.n, leftOpen: l.n > 1, rightOpen: l.n > 1 })}>
              {l.label}
            </button>
          ))}
        </div>
        <span className="cc-controls-spacer" />
        <button className="btn" onClick={() => { setSettings({ tab: 'board' }); goDashboard() }}>Dashboard</button>

        {/*
          Everything that CONFIGURES the app, rather than navigating it, lives behind one
          control. The header carried ten buttons in a row, which made a product look like a
          settings panel — the first thing a reader saw was our knobs rather than the argument.
          What stays out is what someone actually uses while reading: where they are (Board /
          Context), how much detail they want, and the way back.

          The Demo toggle moves in here, but the amber "Demo" pill does NOT — what data you are
          looking at is never hidden, only the switch that changes it.
        */}
        <details className="cc-menu" ref={menuRef}>
          <summary className="btn" title="Theme, panels, data source and setup.">⚙ Customise</summary>
          <div className="cc-menu-body">
            <div className="cc-menu-group">
              <span className="cc-menu-label">Theme</span>
              <div className="seg">
                <button className={`btn ${s.dark ? 'on' : ''}`} onClick={() => setSettings({ dark: true })}>Dark</button>
                <button className={`btn ${!s.dark ? 'on' : ''}`} onClick={() => setSettings({ dark: false })}>Light</button>
              </div>
            </div>

            <div className="cc-menu-group">
              <span className="cc-menu-label">Panels</span>
              <button className={`btn ${s.leftOpen ? 'btn-primary' : ''}`}
                onClick={() => toggleRail('left')}>
                {s.leftOpen ? '‹ Filters' : '› Filters'}
              </button>
              <button className={`btn ${s.rightOpen ? 'btn-primary' : ''}`}
                onClick={() => toggleRail('right')}>
                {s.rightOpen ? 'Assistant ›' : '‹ Assistant'}
              </button>
            </div>

            <div className="cc-menu-group">
              <span className="cc-menu-label">Data source</span>
              <button className={`btn ${s.demo ? 'btn-amber' : ''}`}
                title="ON: fictional numeric universe. OFF: real ASEAN base DB."
                onClick={() => setSettings({ demo: !s.demo })}>
                Demo {s.demo ? 'on' : 'off'}
              </button>
              <button className="btn" onClick={loadSample}
                title="Pin the offline demo company (no network or key needed).">Sample</button>
              <button className="btn" onClick={() => fileRef.current?.click()}>Upload</button>
            </div>

            <div className="cc-menu-group">
              <span className="cc-menu-label">Setup</span>
              <button className="btn" onClick={restartSetup}
                title="Run the assistant setup again and re-shape the board.">Reconfigure</button>
              <button className="btn"
                onClick={() => { menuRef.current!.open = false; goDashboard(); setSettings({ tourDone: false }) }}
                title="Replay the walkthrough of the board.">Tutorial</button>
              <button className="btn"
                onClick={() => {
                  menuRef.current!.open = false
                  goDashboard()
                  // The plot has to be ON SCREEN for a walkthrough of it to have anything to
                  // point at, so asking for the explanation brings it up.
                  setSettings({ tab: 'board', level: 3, tourDeck: 'matrix' })
                }}
                title="The disagreement matrix, corner by corner.">Explain the matrix</button>
            </div>

            {/* A demo control, so it lives with the other configuration rather than in the
                header proper — but it is the one a presenter needs to find in a hurry, so it
                is also reachable as ?present=1 straight from a bookmark. */}
            <div className="cc-menu-group">
              <span className="cc-menu-label">Demo</span>
              <button className="btn" onClick={() => { menuRef.current!.open = false; onPresent?.() }}
                title="Walk the pitch through the running app, one click per step. Esc to leave.">
                Present mode
              </button>
              {/* The same clicker again, arranged as three fears and their answers — the way
                  a room listens, rather than the order the pipeline runs in. */}
              <button className="btn"
                onClick={() => { menuRef.current!.open = false; onFears?.() }}
                title="Three worries a private investor already has, each answered by the app doing the thing: the risk tiers, the four corners, and dated evidence against a stale rating.">
                Why it matters
              </button>
              {/* The same clicker, pointed at the run you are on rather than at a stranger:
                  five stops and a card that consolidates what it passed. */}
              <button className="btn"
                onClick={() => { menuRef.current!.open = false; onRecap?.() }}
                title="Walk this run — the quadrants, the pipeline, the focused company, what would change it — and end on one copyable summary.">
                Recap this run
              </button>
            </div>
          </div>
        </details>
        <input ref={fileRef} type="file" accept=".json,.csv,.txt" style={{ display: 'none' }}
          onChange={e => {
            const f = e.target.files?.[0]
            if (f) uploadFile(f).catch(err => toast(String(err), 'bad'))
            e.target.value = ''
          }} />
      </div>
    </header>
  )
}
