import { useCallback, useEffect, useState } from 'react'
import { api, streamStage2 } from '../../api'
import type { ComparePayload } from '../../types'
import { useStore } from '../../store'
import { CompareMomentumBars, CompareScoreBars } from '../charts'
import { Spinner } from '../ui'

export default function CompareView({ tickers }: { tickers: string[] }) {
  const { goDashboard, settings, openDeepDive, entries, saveEntry, toast } = useStore()
  const [data, setData] = useState<ComparePayload | null>(null)
  const [error, setError] = useState('')
  const [kept, setKept] = useState(tickers)
  // Per-ticker state for the parallel run: 'run' while competing, 'done', or an error string.
  const [running, setRunning] = useState<Record<string, string>>({})

  /**
   * Compete on every compared name AT ONCE.
   *
   * One at a time meant open a deep dive, run it, navigate back, pick the next — and the whole
   * point of a comparison is that the verdicts are read together. These are independent network
   * calls against independent snapshots, so they have no reason to be sequential; the wall clock
   * becomes the slowest single company rather than the sum of all of them.
   *
   * Each company settles on its own: one failing leaves the others alone and reports itself in
   * place, because a comparison that shows two verdicts and one error is more useful than one
   * that shows nothing.
   */
  const runAll = useCallback(async () => {
    const todo = kept.filter(t => !entries[t]?.answer)
    if (!todo.length) return
    setRunning(Object.fromEntries(todo.map(t => [t, 'run'])))
    await Promise.all(todo.map(async ticker => {
      try {
        const entry = entries[ticker] ?? (await api.monitor({ ticker, demo: settings.demo })).entry
        const nq = entry.narrowed_q ?? entry.default_nq
        if (!nq) throw new Error('no default question for this company')
        await streamStage2({ ticker, nq, use_rag: true, top_k: 5 }, {
          onAnswer: payload => saveEntry({ ...entry, answer: payload.answer, narrowed_q: payload.narrowed_q }),
          onError: err => { throw new Error(err.message) },
        })
        setRunning(r => ({ ...r, [ticker]: 'done' }))
      } catch (e) {
        setRunning(r => ({ ...r, [ticker]: e instanceof Error ? e.message : 'failed' }))
      }
    }))
    api.compare(kept).then(setData).catch(() => { /* cards still hold their own answers */ })
    toast('Competing read finished for all compared names.', 'good')
  }, [kept, entries, settings.demo, saveEntry, toast])

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
        <button className="btn btn-primary" style={{ marginLeft: 'auto' }}
          disabled={Object.values(running).includes('run')}
          title="Run the competing read on every compared company at once"
          onClick={() => void runAll()}>
          {Object.values(running).includes('run')
            ? `Competing… ${Object.values(running).filter(v => v !== 'run').length}/${Object.keys(running).length}`
            : `⚡ Deep dive all (${kept.length})`}
        </button>
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
            <span className="cc-chart-sub">
              {data.data.momentum_basis === 'evidence'
                ? 'evidence consensus −1 to +1 · higher = better'
                : data.data.momentum_basis === 'mixed'
                  ? 'mixed scales — not comparable'
                  : '% change · higher = better'}
            </span>
          </div>
          {/* A percentage and a -1..+1 consensus drawn as bars on one axis would have heights
              that mean different things — the same error the industry benchmark refuses to make.
              If the set is mixed, say so rather than plotting it. */}
          {data.data.momentum_basis === 'mixed'
            ? <div className="empty-note">
                These names are on two different momentum scales (a percentage and an evidence
                consensus), so a single bar chart would compare heights that do not mean the same
                thing. Compare within one universe.
              </div>
            : data.data.has_momentum
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
              <button className="btn btn-primary btn-block"
                disabled={running[c.ticker] === 'run'}
                onClick={() => openDeepDive(c.ticker, 'compete')}>
                {running[c.ticker] === 'run' ? 'Competing…' : 'Deep dive'}
              </button>
              {running[c.ticker] && running[c.ticker] !== 'run' && running[c.ticker] !== 'done' && (
                <div className="cc-muted">{running[c.ticker]}</div>
              )}
              <button className="btn" onClick={() => setKept(k => k.filter(t => t !== c.ticker))}>✕ Remove</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
