import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../../api'
import { useStore } from '../../store'
import type { BacktestCase, BacktestPayload } from '../../types'
import { chartTheme } from '../charts'
import { Spinner } from '../ui'

/**
 * "The AI can see now and last time, but it cannot see the future."
 *
 * True, and this panel is the honest half of the reply. It does not predict; it shows what the
 * verdict ACTUALLY DID as evidence arrived. Every point on the line is a real engine run with
 * its own cutoff — the value at a date is what the Radar would have said on that date, from
 * evidence published strictly before it. The flat line is the incumbent view over the same
 * window, which is the whole argument in one picture: one of these two lines moved.
 *
 * THE FAILURE CASE STAYS IN. Adaro is flagged `is_known_failure` and is shown with the rest,
 * not quietly dropped — it is the case that produced the forward-looking discount (announcement
 * language has its materiality halved). A backtest you can only pass is not a backtest, and a
 * judge who spots a curated set stops believing the four that worked.
 *
 * WHY IT IS DRAWN HERE RATHER THAN EMBEDDED. `docs/backtest/*.svg` already exist and `harness.py`
 * checks they are current, but they are styled for a document — fixed palette, fixed width, no
 * theme. Redrawing from the same `series.json` the SVGs come from keeps one source of truth and
 * lets the chart obey the app's own tokens.
 */

const BASELINE = '#8b97ab'

function fmtDate(d: string): string {
  return d.slice(0, 7)     // YYYY-MM — the series is monthly, the day is noise on the axis
}

/** Tab labels. Splitting on the first space turns "Top Glove" into "Top", so drop the legal and
 *  descriptive tail instead and keep whatever names the company. */
const TAIL = /\s+(corporation|corp|industries|energy|group|holdings|berhad|bhd|plc|ltd|limited|inc)\b.*$/i
function shortName(company: string): string {
  const cut = company.split(/\s*\/\s*/)[0].replace(TAIL, '').trim()
  return cut || company
}

function CaseChart({ c, dark }: { c: BacktestCase; dark: boolean }) {
  const t = chartTheme(dark)
  const rows = useMemo(() => c.points.map(p => ({
    date: fmtDate(p.date),
    momentum: p.momentum,
    rating: c.baseline.value,
    label: p.label,
    signals: p.signal_count,
  })), [c])

  const tone = c.is_known_failure ? '#f5a524' : '#35d39a'

  return (
    <div className="bt-chart">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="date" tick={{ fill: t.tick, fontSize: 11 }} minTickGap={28}
            axisLine={{ stroke: t.grid }} tickLine={false} />
          <YAxis domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]}
            tick={{ fill: t.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{
              backgroundColor: t.panel, border: `1px solid ${t.grid}`, borderRadius: 10,
              color: t.text, fontSize: 12,
            }}
            formatter={(v, n) => [
              typeof v === 'number' ? v.toFixed(3) : String(v ?? '—'),
              n === 'momentum' ? 'Our reading' : 'Incumbent view',
            ]} />
          {/* The zero line is the claim a static rating implicitly makes: nothing is moving.
              No cutoff marker: the cutoff IS the right-hand edge by construction — the series
              stops there — and the outcome is dated after it, so neither has a place on this
              axis. Drawing them anyway put two labels on top of each other in the last column. */}
          <ReferenceLine y={0} stroke={t.grid} />
          <Line type="monotone" dataKey="rating" stroke={BASELINE} strokeWidth={2}
            strokeDasharray="6 4" dot={false} isAnimationActive={false} name="rating" />
          <Line type="monotone" dataKey="momentum" stroke={tone} strokeWidth={2.5}
            dot={false} isAnimationActive={false} name="momentum" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function TrackRecord() {
  const { settings } = useStore()
  const [data, setData] = useState<BacktestPayload | null>(null)
  const [err, setErr] = useState('')
  const [pick, setPick] = useState(0)

  useEffect(() => {
    let live = true
    api.backtest().then(d => { if (live) setData(d) })
      .catch(e => { if (live) setErr(String(e.message || e)) })
    return () => { live = false }
  }, [])

  if (err) return <div className="cc-card cc-muted">Track record unavailable — {err}</div>
  if (!data) return <div className="cc-card"><Spinner label="Loading the validation runs…" /></div>
  if (!data.available || !data.cases.length) {
    return <div className="cc-card cc-muted">{data.reason || 'No backtest series on disk.'}</div>
  }

  const c = data.cases[Math.min(pick, data.cases.length - 1)]
  const moved = c.final.momentum - c.baseline.value

  return (
    <div className="bt">
      <div className="bt-head">
        <div>
          <div className="cc-h">Has the verdict moved before?</div>
          <div className="cc-muted">
            We cannot see the future. We can show what this call did as the evidence arrived —
            every point is a real run, scored only from what was published before that date.
          </div>
        </div>
      </div>

      <div className="bt-tabs">
        {data.cases.map((x, i) => (
          <button key={x.case_id} className={`bt-tab ${i === pick ? 'on' : ''}`}
            onClick={() => setPick(i)}>
            {shortName(x.company)}
            {x.is_known_failure && <span className="bt-fail" title="A case we got wrong">!</span>}
          </button>
        ))}
      </div>

      <div className="bt-case">
        <div className="bt-case-h">
          <span className="bt-co">{c.company}</span>
          <span className="cc-muted">{c.ticker}</span>
          <span className={`bt-badge ${c.is_known_failure ? 'fail' : 'ok'}`}>{c.profile}</span>
        </div>

        <CaseChart c={c} dark={settings.dark} />
        <div className="cc-muted bt-axis">
          The line stops at {c.cutoff_date} — the evidence cutoff. Nothing after that date was
          available to any point on it.
        </div>

        <div className="bt-legend">
          <span><i className="bt-key rating" /> Incumbent view — {c.baseline.basis === 'unavailable'
            ? 'no rating action dated in this window' : c.baseline.basis}</span>
          <span><i className={`bt-key mom ${c.is_known_failure ? 'fail' : ''}`} /> Our reading —
            ended at {c.final.momentum >= 0 ? '+' : ''}{c.final.momentum.toFixed(3)} on {c.final.signal_count} signals</span>
        </div>

        <div className="bt-outcome">
          <div className="bt-outcome-h">
            What happened after the cutoff <span className="cc-muted">{c.outcome_date}</span>
          </div>
          <div className="bt-outcome-t">{c.outcome}</div>
          {c.outcome_source && (
            <a className="bt-src" href={c.outcome_source} target="_blank" rel="noreferrer noopener">
              source
            </a>
          )}
        </div>

        <div className="bt-gap">
          Over this window the incumbent view moved <b>0.000</b> and ours moved{' '}
          <b>{moved >= 0 ? '+' : ''}{moved.toFixed(3)}</b>. That gap is the disagreement,
          drawn over time instead of as a single dot.
        </div>

        {c.baseline.note && <div className="cc-muted bt-note">{c.baseline.note}</div>}
      </div>

      <div className="cc-muted bt-foot">{data.disclaimer}</div>
    </div>
  )
}
