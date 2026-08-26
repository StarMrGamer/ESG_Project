import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import type { Level } from '../store'

/**
 * The layering control. Replaces the old Full/Simple pair: two states forced every widget to be
 * either "always on" or "expert only", so the middle ground — charts and rankings without the
 * engine internals — had nowhere to live, and the default landed on everything at once.
 */
const LEVELS: { n: Level; label: string; hint: string }[] = [
  { n: 1, label: 'Brief', hint: 'The verdict and one thing to check. Rails closed.' },
  { n: 2, label: 'Analysis', hint: 'Adds pillar momentum, the chart and the rankings.' },
  { n: 3, label: 'Everything', hint: 'Adds the disagreement matrix, provenance and the evidence trail.' },
]

const RADAR_SVG = (
  <svg width="22" height="22" viewBox="0 0 34 34" aria-hidden>
    <circle cx="17" cy="17" r="15" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <circle cx="17" cy="17" r="9" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <line x1="17" y1="17" x2="29.5" y2="8" stroke="var(--r-pos)" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="17" cy="17" r="3" fill="var(--r-pos)" />
  </svg>
)

export default function Header() {
  const { settings, setSettings, board, health, loadSample, uploadFile, toast, goDashboard,
    restartSetup } = useStore()
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
        <div className="seg" role="group" aria-label="Section">
          <button className={`btn ${s.tab === 'board' ? 'on' : ''}`}
            title="The live read: filters, the radar, the verdict and its evidence."
            onClick={() => setSettings({ tab: 'board' })}>Board</button>
          <button className={`btn ${s.tab === 'context' ? 'on' : ''}`}
            title="Method and benchmarks — the same for every company, so they live here."
            onClick={() => setSettings({ tab: 'context' })}>Context</button>
          {/* The book. Its own tab rather than a mode of the board: a client meeting is a
              different job from screening the universe, and the brief is a document, not a
              dashboard. */}
          <button className={`btn ${s.tab === 'clients' ? 'on' : ''}`}
            title="Your client book and the pre-meeting brief"
            onClick={() => setSettings({ tab: 'clients' })}>Clients</button>
        </div>
        <div className="seg" role="group" aria-label="Detail level">
          {LEVELS.map(l => (
            <button key={l.n} className={`btn ${s.level === l.n ? 'on' : ''}`} title={l.hint}
              onClick={() => setSettings({ level: l.n, leftOpen: l.n > 1, rightOpen: l.n > 1 })}>
              {l.n} · {l.label}
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
                onClick={() => setSettings({ leftOpen: !s.leftOpen })}>
                {s.leftOpen ? '‹ Filters' : '› Filters'}
              </button>
              <button className={`btn ${s.rightOpen ? 'btn-primary' : ''}`}
                onClick={() => setSettings({ rightOpen: !s.rightOpen })}>
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
