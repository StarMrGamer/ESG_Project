import { useState } from 'react'
import { useStore } from '../../store'
import { shortSector } from '../ui'

export default function UniverseGrid() {
  const { board, setFocus, monitorOnly, openEvidence, settings } = useStore()
  const [open, setOpen] = useState(false)
  if (!board) return null
  const pinned = new Set(board.watchlist.map(w => w.ticker))
  const engine = board.engine

  // A5/A6: the tier and pipeline filters DIM a card, never remove it — a name you can't see is
  // a name you can't argue with.
  const dims = (ticker: string) => {
    const rec = engine?.records[ticker]
    if (!rec) return false
    if (settings.pipelineOnly && !rec.tiers?.balanced) return true
    return settings.tier !== 'all' && !rec.tiers?.[settings.tier]
  }

  const monitor = async (ticker: string) => {
    await monitorOnly(ticker)
  }

  return (
    <div className="universe-block">
      <button className="btn universe-toggle" onClick={() => setOpen(o => !o)}>
        <span>Browse universe · {board.counts.total} companies</span>
        <span className="cc-muted">{open ? 'Hide ▲' : 'Show ▼'}</span>
      </button>
      {open && (
        <div>
          <div className="cc-muted" style={{ marginTop: 10 }}>
            Filtered by the left panel. Focus features a company in the right rail; Monitor pins a snapshot.
          </div>
          {board.constituents.length === 0 && <div className="empty-note">No constituents match the filters.</div>}
          <div className="uni-grid">
            {board.constituents.map(c => {
              const rec = engine?.records[c.ticker]
              const badges = engine?.badges[c.ticker]
              return (
              <div className={`uni-card ${dims(c.ticker) ? 'is-dim' : ''}`} key={c.ticker}>
                <h4>{c.company}</h4>
                <div className="meta">{c.ticker} · {c.country} · {shortSector(c.sector)}</div>
                {rec && (
                  <div className="uni-verdict">
                    <span className={`legend-chip q-${rec.label.replace('_', '-')}`}>{rec.label_display}</span>
                    <span className={rec.composite_momentum >= 0 ? 'cc-pos' : 'cc-neg'}>
                      {rec.composite_momentum >= 0 ? '+' : ''}{rec.composite_momentum.toFixed(2)}
                    </span>
                    <span className="cc-muted">conf {rec.composite_confidence.toFixed(2)} · {rec.signal_count} signals</span>
                  </div>
                )}
                {badges && (
                  <div className="uni-badges">
                    <span className={`badge tone-${badges.green_bond.tone}`} title={badges.green_bond.note}>
                      {badges.green_bond.display}
                    </span>
                    <span className={`badge tone-${badges.profitability.tone}`} title={badges.profitability.note}>
                      {badges.profitability.display}
                      {badges.profitability.traction && <i className="traction-pip" title="Traction on a loss-maker">▲</i>}
                    </span>
                  </div>
                )}
                {c.esg_basis && (
                  <div className="basis">
                    {{ high: '●', medium: '●', low: '●' }[(c.confidence || '').toLowerCase()] ?? '○'}{' '}
                    <span style={{
                      color: (c.confidence || '').toLowerCase() === 'high' ? 'var(--r-pos)'
                        : (c.confidence || '').toLowerCase() === 'medium' ? 'var(--r-amber)'
                          : (c.confidence || '').toLowerCase() === 'low' ? 'var(--r-neg)' : 'var(--r-faint)',
                    }}>
                      {c.esg_basis.slice(0, 150)}{c.esg_basis.length > 150 ? '…' : ''}
                    </span>
                    {c.source_url && <> · <a href={c.source_url} target="_blank" rel="noreferrer">source</a></>}
                  </div>
                )}
                <div className="actions">
                  <button className="btn" onClick={() => setFocus(c.ticker)}>Focus</button>
                  <button className="btn" onClick={() => openEvidence(c.ticker)}
                    title="Open the evidence trail, the rationale behind every signal, and on-chain verification.">
                    Evidence
                  </button>
                  {pinned.has(c.ticker)
                    ? <button className="btn" disabled>Pinned</button>
                    : <button className="btn btn-primary" onClick={() => monitor(c.ticker)}>Monitor</button>}
                </div>
              </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
