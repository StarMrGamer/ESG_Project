import { useRef } from 'react'
import { useStore } from '../store'

const RADAR_SVG = (
  <svg width="22" height="22" viewBox="0 0 34 34" aria-hidden>
    <circle cx="17" cy="17" r="15" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <circle cx="17" cy="17" r="9" fill="none" stroke="var(--r-borderStrong)" strokeWidth="1.4" />
    <line x1="17" y1="17" x2="29.5" y2="8" stroke="var(--r-pos)" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="17" cy="17" r="3" fill="var(--r-pos)" />
  </svg>
)

export default function Header() {
  const { settings, setSettings, board, health, loadSample, uploadFile, toast, goDashboard } = useStore()
  const fileRef = useRef<HTMLInputElement>(null)
  const s = settings

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
          </div>
        </div>
      </div>
      <div className="cc-hdr-right">
        {pill}
        {board?.fresh && <span className="cc-fresh">↻ {board.fresh}</span>}
      </div>

      <div className="cc-controls">
        <div className="seg">
          <button className={`btn ${!s.simplified ? 'on' : ''}`}
            onClick={() => setSettings({ simplified: false, leftOpen: true, rightOpen: true })}>Full</button>
          <button className={`btn ${s.simplified ? 'on' : ''}`}
            onClick={() => setSettings({ simplified: true, leftOpen: false, rightOpen: false })}>Simple</button>
        </div>
        <div className="seg">
          <button className={`btn ${s.dark ? 'on' : ''}`} onClick={() => setSettings({ dark: true })}>Dark</button>
          <button className={`btn ${!s.dark ? 'on' : ''}`} onClick={() => setSettings({ dark: false })}>Light</button>
        </div>
        <button className={`btn ${s.leftOpen ? 'btn-primary' : ''}`}
          onClick={() => setSettings({ leftOpen: !s.leftOpen })}>
          {s.leftOpen ? '‹ Filters' : '› Filters'}
        </button>
        <button className={`btn ${s.rightOpen ? 'btn-primary' : ''}`}
          onClick={() => setSettings({ rightOpen: !s.rightOpen })}>
          {s.rightOpen ? 'Assistant ›' : '‹ Assistant'}
        </button>
        <button className={`btn ${s.demo ? 'btn-amber' : ''}`}
          title="ON: fictional numeric universe. OFF: real ASEAN base DB."
          onClick={() => setSettings({ demo: !s.demo })}>
          Demo {s.demo ? 'on' : 'off'}
        </button>
        <span className="cc-controls-spacer" />
        <button className="btn" onClick={goDashboard}>Dashboard</button>
        <button className="btn" onClick={loadSample}
          title="Pin the offline demo company (no network or key needed).">Sample</button>
        <button className="btn" onClick={() => fileRef.current?.click()}>Upload</button>
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
