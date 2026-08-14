import { useMemo } from 'react'
import { useStore } from '../../store'
import type { EngineRecord, LabelKey, TierKey } from '../../types'

/**
 * EngineBoard — the Build Spec v2 command strip: the CGSI quadrant matrix (A1), the risk-tier
 * selector (A5), the origination-pipeline filter with live N/M/K counts (A6), and the run's
 * provenance/anchor status.
 *
 * Position on the matrix is the disagreement itself: x is what the incumbent rating thinks
 * (percentile), y is what our live evidence says (momentum). A name high and left is one the
 * market has not caught up with; low and right is the Top Glove shape.
 */

const LABEL_TONE: Record<string, string> = {
  hidden_winners: 'q-hidden', future_leaders: 'q-future', overrated_leaders: 'q-overrated',
  value_traps: 'q-trap', consensus: 'q-consensus',
}

// The plot's own coordinate space. The viewBox is WIDE and the SVG scales uniformly
// (`preserveAspectRatio` left at its default) so a dot is always a circle, never an ellipse
// stretched by the container's width.
const VB = { w: 1000, h: 300, left: 60, right: 940, top: 30, bottom: 270, midX: 500, midY: 150 }

// Where each quadrant's caption sits. Hidden Winners is deliberately absent: it is a precedence
// label that can land anywhere on the grid, not a region — so it reads as a marker, not a corner.
const QUADRANTS: { key: LabelKey; x: number; y: number; anchor: 'start' | 'end' }[] = [
  { key: 'consensus', x: VB.left + 8, y: VB.top + 6, anchor: 'start' },
  { key: 'future_leaders', x: VB.right - 8, y: VB.top + 6, anchor: 'end' },
  { key: 'value_traps', x: VB.left + 8, y: VB.bottom + 18, anchor: 'start' },
  { key: 'overrated_leaders', x: VB.right - 8, y: VB.bottom + 18, anchor: 'end' },
]

function matches(record: EngineRecord, tier: TierKey | 'all', pipelineOnly: boolean): boolean {
  if (pipelineOnly && !record.tiers?.balanced) return false
  if (tier === 'all') return true
  return Boolean(record.tiers?.[tier])
}

export default function EngineBoard() {
  const { board, settings, setSettings, openEvidence, focusTicker, setFocus } = useStore()
  const engine = board?.engine
  const nameOf = useMemo(() => {
    const map: Record<string, string> = {}
    for (const c of board?.constituents ?? []) map[c.ticker] = c.company
    return map
  }, [board])

  const rows = useMemo(() => Object.values(engine?.records ?? {}), [engine])
  const shown = useMemo(
    () => rows.filter(r => matches(r, settings.tier, settings.pipelineOnly)),
    [rows, settings.tier, settings.pipelineOnly])
  // The 90-second walk has to reach a Hidden Winner without hunting for a dot, so the strongest
  // disagreements get a named, one-click route straight into the evidence trail.
  const hidden = useMemo(
    () => rows.filter(r => r.label === 'hidden_winners')
      .sort((a, b) => b.disagreement - a.disagreement).slice(0, 5),
    [rows])

  if (!engine) return null
  const { nmk, labels, label_counts, label_tooltips, label_rules, tiers, tier_rules, anchor } = engine
  const dimmed = rows.length - shown.length

  const point = (r: EngineRecord) => ({
    // x: the incumbent percentile (0..1). y: our momentum (-1..+1), +1 at the top.
    cx: VB.left + r.lseg_percentile * (VB.right - VB.left),
    cy: VB.midY - Math.max(-1, Math.min(1, r.composite_momentum)) * (VB.midY - VB.top),
  })

  return (
    <div className="engine-board">
      <div className="engine-head">
        <div>
          <div className="cc-h">Disagreement matrix</div>
          <div className="cc-muted">
            x = incumbent rating percentile (<b title="A mocked stand-in for the licensed LSEG
              percentile: the company's stored static rating ranked inside this run's cohort.
              Never presented as an LSEG figure.">MOCK baseline</b>)
            {' · '}y = our live momentum, <b title="Direction consensus (the weighted mean of
              each signal's +1/-1) scaled by evidence weight, so one thin signal cannot score
              like twelve corroborating ones. Names cluster where the evidence agrees; an
              extreme score has to be earned.">−1 to +1</b>
            {' · '}{shown.length} of {rows.length} in view
          </div>
        </div>
        <div className="engine-run" title={`config ${engine.config_version} · ${engine.config_hash}`}>
          <span>run <b>{engine.run_id}</b></span>
          <span>as of {engine.as_of}</span>
          <span className={`anchor-chip ${anchor.status === 'anchored' ? 'on' : ''}`}
            title={anchor.note || `${anchor.leaf_count} leaves · root ${anchor.root.slice(0, 24)}…`}>
            {anchor.status === 'anchored' ? '⛓ anchored' : '⛓ anchor pending'}
          </span>
        </div>
      </div>

      <div className="engine-controls">
        <div className="seg" role="group" aria-label="Risk appetite">
          <button className={`btn ${settings.tier === 'all' ? 'on' : ''}`}
            title="Show every company, no tier applied."
            onClick={() => setSettings({ tier: 'all' })}>All</button>
          {(Object.keys(tiers) as TierKey[]).map(key => (
            <button key={key} className={`btn ${settings.tier === key ? 'on' : ''}`}
              title={tier_rules[key] || key} onClick={() => setSettings({ tier: key })}>
              {tiers[key]}
            </button>
          ))}
        </div>
        <button className={`btn ${settings.pipelineOnly ? 'btn-primary' : ''}`}
          title={nmk.rules.M}
          onClick={() => setSettings({ pipelineOnly: !settings.pipelineOnly })}>
          Origination pipeline {settings.pipelineOnly ? 'on' : 'off'}
        </button>
        <div className="nmk">
          {(['N', 'M', 'K'] as const).map(key => (
            <span key={key} title={nmk.rules[key]}>
              <b>{key} {nmk[key]}</b> {nmk.labels[key]}
            </span>
          ))}
        </div>
      </div>

      <div className="matrix-wrap">
        <svg viewBox={`0 0 ${VB.w} ${VB.h}`} className="matrix" role="img"
          aria-label="Quadrant matrix of incumbent rating percentile against live momentum">
          <line x1={VB.midX} y1={VB.top - 16} x2={VB.midX} y2={VB.bottom + 4} className="matrix-guide" />
          <line x1={VB.left - 24} y1={VB.midY} x2={VB.right + 24} y2={VB.midY} className="matrix-guide" />
          <text x={VB.left - 28} y={VB.midY - 5} textAnchor="end" className="matrix-tick">0</text>
          <text x={VB.left - 28} y={VB.top + 5} textAnchor="end" className="matrix-tick">+1</text>
          <text x={VB.left - 28} y={VB.bottom + 4} textAnchor="end" className="matrix-tick">−1</text>
          {QUADRANTS.map(q => (
            <text key={q.key} x={q.x} y={q.y} textAnchor={q.anchor}
              className={`matrix-quad ${LABEL_TONE[q.key]}`}>{labels[q.key]}</text>
          ))}
          {rows.map(r => {
            const { cx, cy } = point(r)
            const on = matches(r, settings.tier, settings.pipelineOnly)
            const isFocus = r.company_id === focusTicker
            return (
              <circle key={r.company_id} cx={cx} cy={cy}
                r={r.label === 'hidden_winners' ? 8 : 6}
                className={`matrix-dot ${LABEL_TONE[r.label]} ${on ? '' : 'is-dim'} ${isFocus ? 'is-focus' : ''}`}
                onClick={() => { setFocus(r.company_id); openEvidence(r.company_id) }}>
                <title>{`${nameOf[r.company_id] || r.company_id} — ${r.label_display}
rating percentile ${(r.lseg_percentile * 100).toFixed(0)}% · momentum ${r.composite_momentum >= 0 ? '+' : ''}${r.composite_momentum.toFixed(2)}
disagreement ${r.disagreement >= 0 ? '+' : ''}${r.disagreement.toFixed(2)} · confidence ${r.composite_confidence.toFixed(2)} · ${r.signal_count} signals`}</title>
              </circle>
            )
          })}
        </svg>
        <div className="matrix-axis-x"><span>rating: laggard</span><span>rating: leader</span></div>
      </div>

      {hidden.length > 0 && (
        <div className="hw-strip">
          <span className="hw-strip-label" title={label_tooltips.hidden_winners}>
            {labels.hidden_winners}
          </span>
          {hidden.map(r => (
            <button key={r.company_id} className="hw-pick"
              onClick={() => { setFocus(r.company_id); openEvidence(r.company_id) }}
              title={`Disagreement ${r.disagreement >= 0 ? '+' : ''}${r.disagreement.toFixed(2)} · confidence ${r.composite_confidence.toFixed(2)} · ${r.signal_count} signals. Opens the evidence trail.`}>
              {nameOf[r.company_id] || r.company_id}
              <b>{r.disagreement >= 0 ? '+' : ''}{r.disagreement.toFixed(2)}</b>
            </button>
          ))}
        </div>
      )}

      <div className="matrix-legend">
        {Object.keys(labels).map(key => (
          <button key={key} className={`legend-chip ${LABEL_TONE[key]}`}
            title={`${label_tooltips[key]}\n\nRule: ${label_rules[key]}`}
            onClick={() => setSettings({ tier: 'all', pipelineOnly: false })}>
            <i /> {labels[key]} <b>{label_counts[key] ?? 0}</b>
          </button>
        ))}
        {dimmed > 0 && (
          <span className="cc-muted">
            {dimmed} dimmed by the {settings.pipelineOnly ? 'pipeline filter' : 'tier'} — dimmed,
            not hidden.
          </span>
        )}
      </div>

      {engine.metadata.provisional > 0 && (
        <div className="cc-muted engine-foot">
          Green-bond &amp; profitability metadata: {engine.metadata.note} Badges show
          <b> PROVISIONAL</b> until the verified CSV lands — {engine.metadata.path}
        </div>
      )}
    </div>
  )
}
