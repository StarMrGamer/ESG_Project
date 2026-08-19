import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import type { HorizonKey, MarginRow, SensitivityPayload } from '../../types'
import { Spinner } from '../ui'

/**
 * "What would change this verdict?"
 *
 * WHY THIS PANEL EXISTS. Every other number on the board describes what has already happened.
 * A reviewer's fair objection is that evidence keeps arriving: the verdict on screen is a
 * snapshot, and a snapshot is exactly what we criticise a static rating for being. The
 * difference is that we can say what ours is standing on, and how close it is to changing —
 * measured by re-scoring, not estimated.
 *
 * IT IS NOT A FORECAST, and the wording is deliberate throughout. Nothing here says what will
 * happen; it says what is currently load-bearing and how far the record sits from each line
 * that decides its label. A rating cannot answer this question at all, which is the point.
 *
 * TWO READINGS, because they fail differently:
 *   MARGINS   — distance from every boundary in `engine.label_for`, nearest first. Facts about
 *               the record. The nearest one is the thing worth watching.
 *   LEAVE ONE OUT — the company re-scored with each signal removed in turn, inside the same
 *               cohort. A row that flips the label is a row the verdict depends on.
 *
 * READING THE COUNT. "10 of 11 signals are load-bearing" is not ten important findings — it is
 * a company balanced on a boundary where almost anything tips it. The server's `verdict_note`
 * already makes that distinction by reading the nearest margin, so it leads the panel.
 */

/** How much of the bar to fill for a margin, on a scale where "comfortable" saturates. */
function fill(m: MarginRow): number {
  const span = m.key === 'signal_count' ? 6 : m.key === 'rating_percentile' ? 0.5 : 0.6
  return Math.min(1, Math.abs(m.distance) / span)
}

function fmt(m: MarginRow, v: number): string {
  return m.key === 'signal_count' ? String(Math.round(v)) : v.toFixed(3)
}

function Margins({ rows }: { rows: MarginRow[] }) {
  return (
    <div className="sens-margins">
      {rows.map((m, i) => (
        <div key={m.key} className={`sens-margin ${i === 0 ? 'near' : ''}`}>
          {/* NOT coloured by side. "Below the median rating" is the defining property of a
              Hidden Winner, so painting it red would call the thesis a warning. Distance is a
              neutral measurement; only the nearest boundary — the one worth watching — is
              tinted, and it is tinted amber to mean "watch", never "bad". */}
          <div className="sens-margin-h">
            <span className="sens-margin-name">{m.label}</span>
            <span className="sens-margin-d">
              {m.side === 'above' ? 'above by ' : 'below by '}{fmt(m, Math.abs(m.distance))}
            </span>
          </div>
          <div className="sens-bar">
            <div className="sens-bar-fill" style={{ width: `${fill(m) * 100}%` }} />
          </div>
          <div className="sens-margin-f">
            {fmt(m, m.value)} vs {m.boundary_name} {fmt(m, m.boundary)}
            {i === 0 && <span className="sens-tag">nearest</span>}
          </div>
          {i === 0 && <div className="sens-margin-note">{m.note}</div>}
        </div>
      ))}
    </div>
  )
}

export default function VerdictSensitivity({ ticker }: { ticker: string }) {
  const { settings } = useStore()
  const [data, setData] = useState<SensitivityPayload | null>(null)
  const [err, setErr] = useState('')
  const [all, setAll] = useState(false)

  useEffect(() => {
    let live = true
    setData(null); setErr(''); setAll(false)
    api.sensitivity(ticker, settings.demo, settings.horizon as HorizonKey)
      .then(d => { if (live) setData(d) })
      .catch(e => { if (live) setErr(String(e.message || e)) })
    return () => { live = false }
  }, [ticker, settings.demo, settings.horizon])

  if (err) return <div className="cc-card cc-muted">Sensitivity unavailable — {err}</div>
  if (!data) return <div className="cc-card"><Spinner label="Re-scoring without each signal…" /></div>

  // Flipping rows first: they are the answer, the rest is the evidence that they are the answer.
  const flips = data.signals.filter(s => s.flips)
  const rest = data.signals.filter(s => !s.flips)
  const shown = all ? [...flips, ...rest] : [...flips, ...rest].slice(0, 5)

  return (
    <div className="sens">
      <div className="sens-head">
        <div>
          <div className="cc-h">What would change this verdict</div>
          <div className="cc-muted">
            The evidence will keep arriving. This is what the current call is standing on.
          </div>
        </div>
        <div className={`sens-verdict ${data.load_bearing_count ? 'narrow' : 'solid'}`}>
          {data.label_display}
        </div>
      </div>

      <div className="sens-note">{data.verdict_note}</div>

      <div className="sens-sub">How close is it to a boundary?</div>
      <Margins rows={data.margins} />

      <div className="sens-sub">
        Take one signal away
        <span className="cc-muted">
          &nbsp;— {data.load_bearing_count} of {data.signal_count} change the label on their own
        </span>
      </div>

      <div className="sens-rows">
        {shown.map(s => (
          <div key={s.signal_id} className={`sens-row ${s.flips ? 'flip' : ''}`}>
            <div className="sens-row-h">
              <span className="sens-date">{s.published_at || 'undated'}</span>
              <span className="sens-comp">{s.component}</span>
              {s.flips
                ? <span className="sens-flag">without it → {s.label_without_display}</span>
                : <span className="sens-hold">label holds</span>}
            </div>
            <div className="sens-rationale">{s.rationale}</div>
            <div className="sens-row-f">
              momentum <b>{s.momentum_without >= 0 ? '+' : ''}{s.momentum_without.toFixed(3)}</b> without it
              {s.source_url && (
                <>
                  &nbsp;·&nbsp;
                  <a href={s.source_url} target="_blank" rel="noreferrer noopener">source</a>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {data.signals.length > 5 && (
        <button className="btn sens-more" onClick={() => setAll(v => !v)}>
          {all ? 'Show fewer' : `Show all ${data.signals.length} signals`}
        </button>
      )}

      <div className="cc-muted sens-foot">
        {data.disclaimer} Run <code>{data.run_id}</code> · as of {data.as_of || 'unknown'}.
      </div>
    </div>
  )
}
