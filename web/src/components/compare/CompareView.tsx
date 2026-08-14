import { useEffect, useState } from 'react'
import { api } from '../../api'
import type { ComparePayload } from '../../types'
import { useStore } from '../../store'
import { CompareMomentumBars, CompareScoreBars } from '../charts'
import { Spinner } from '../ui'

export default function CompareView({ tickers }: { tickers: string[] }) {
  const { goDashboard, settings, openDeepDive } = useStore()
  const [data, setData] = useState<ComparePayload | null>(null)
  const [error, setError] = useState('')
  const [kept, setKept] = useState(tickers)

  useEffect(() => {
    api.compare(kept)
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : 'Compare failed'))
  }, [kept])

  if (error) return <div className="error-note">{error}</div>
  if (!data) return <Spinner label="Building the comparison…" />

  return (
    <div className="dd-shell" style={{ maxWidth: 1200 }}>
      <div className="dd-top">
        <button className="btn" onClick={goDashboard}>← Dashboard</button>
        <button className="btn" onClick={goDashboard} title="Return to dashboard to select more companies">⊕ Add more</button>
        <h3>Side-by-side comparison</h3>
      </div>

      {!(data.data.has_momentum || data.data.has_score) && (
        <div className="banner-note">
          No numeric momentum or rating data on these names yet — comparison graphs need the demo
          set (or built numeric data). Evidence-only names show <b>awaiting data</b>.
        </div>
      )}

      <div className="compare-layout">
        <div className="cc-card">
          <div className="cc-chart-head">
            <span className="cc-chart-title">E · S · G momentum</span>
            <span className="cc-chart-sub">% change · higher = better</span>
          </div>
          {data.data.has_momentum
            ? <CompareMomentumBars rows={data.data.rows} dark={settings.dark} />
            : <div className="empty-note">No momentum data on these names.</div>}
        </div>
        <div className="cc-card">
          <div className="cc-chart-head">
            <span className="cc-chart-title">Static ESG score</span>
            <span className="cc-chart-sub">{data.higher_better_all ? 'higher = better' : 'lower = better risk'}</span>
          </div>
          {data.data.rows.some(r => r.esg_score != null)
            ? <CompareScoreBars rows={data.data.rows} dark={settings.dark} />
            : <div className="empty-note">No static rating on these names.</div>}
        </div>
      </div>

      <div className="compare-grid" style={{ marginTop: 12 }}>
        {data.cards.map(c => (
          <div className="cc-card" key={c.ticker}>
            <h4 style={{ margin: '0 0 3px' }}>{c.snap.company}</h4>
            <div className="cc-muted"><kbd className="kbd">{c.snap.ticker}</kbd> · {c.snap.country}</div>
            <div className="cc-muted">{c.snap.sector}</div>
            <hr className="divider" />
            <div className="ev-row"><span>ESG rating</span><b>{c.snap.rating || '—'}</b></div>
            <div className="ev-row"><span>{c.snap.score_higher_better ? 'ESG band' : 'Risk band'}</span>
              <b>{c.band_emoji} {c.snap.band || '—'}</b></div>
            <div className="ev-row"><span>E · S · G momentum</span>
              <b>{c.snap.arrows.E} {c.snap.arrows.S} {c.snap.arrows.G}</b></div>
            <div className="ev-row"><span>Red flags</span><b>{c.snap.red_flags}</b></div>
            <div className="ev-row"><span>Coverage</span><b>{c.snap.coverage}/{c.snap.coverage_total}</b></div>
            <hr className="divider" />
            {c.verdict
              ? (
                <>
                  <div className="cc-muted"><b>Verdict</b></div>
                  <div className="cc-panel-body" style={{ fontSize: 12, maxHeight: 120, overflowY: 'auto' }}>{c.verdict}</div>
                </>
              )
              : <div className="cc-muted">No verdict yet — run a deep dive first.</div>}
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button className="btn btn-primary btn-block" onClick={() => openDeepDive(c.ticker, 'compete')}>Deep dive</button>
              <button className="btn" onClick={() => setKept(k => k.filter(t => t !== c.ticker))}>✕ Remove</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
