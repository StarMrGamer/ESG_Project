import { Fragment, useCallback, useMemo, useRef, useState } from 'react'
import { useStore } from '../../store'
import type { EngineRecord, HorizonKey, LabelKey, TierKey } from '../../types'

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

/**
 * The plot's geometry.
 *
 * The viewBox is measured, not fixed. It used to be a constant 1000x300 rendered into a
 * full-width box with the default `preserveAspectRatio`, which means `meet`: on a wide monitor
 * the whole chart was letterboxed to 1000px and centred, so the dots crowded into the middle
 * third and the axes had nowhere to breathe. Setting the viewBox to the element's own pixel size
 * keeps the scale at 1:1 — dots stay circles, strokes stay hairlines — and lets the plot use the
 * width the board now has.
 *
 * Padding is asymmetric because the axes need room: the left gutter holds the tick labels and the
 * rotated axis name, the bottom holds the tick labels, the axis name and the two end captions.
 *
 * HEIGHT FOLLOWS WIDTH (fixed 2026-08-22). `H` used to be a constant 340 against a measured
 * width, so the plot area got flatter the wider the board went: ~7:1 on a 1920 monitor and ~20:1
 * on a 2550 one, where every dot collapsed onto a single horizontal line and the four quadrants
 * stopped being readable as quadrants at all. y is the axis that carries our half of the argument
 * — a chart that cannot show vertical separation is not showing the disagreement. So the plot
 * area now holds a fixed ratio and the SVG grows taller as it grows wider, with `MAX_W` capping
 * how wide it is allowed to get before it simply centres in the panel. The panel itself stays
 * full-bleed, so the board still lines up with the header.
 */
const PAD = { l: 104, r: 30, t: 34, b: 66 }
const MIN_W = 520
/** Beyond this the chart centres instead of stretching — past it, extra width buys nothing. */
const MAX_W = 1180
/** plot width : plot height. Landscape enough for a dashboard, square enough to read quadrants. */
const PLOT_RATIO = 2.6
/** Keeps the chart from dominating the page on a wide screen, and readable on a narrow one. */
const H_MIN = 300
const H_MAX = 520

const clamp = (lo: number, v: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** The SVG height that gives the PLOT area its target ratio at this width. */
function heightFor(width: number): number {
  const plotW = width - PAD.l - PAD.r
  return Math.round(clamp(H_MIN, plotW / PLOT_RATIO + PAD.t + PAD.b, H_MAX))
}

/** Where the tick marks and gridlines fall on each axis. */
const X_TICKS = [0, 0.25, 0.5, 0.75, 1]
const Y_TICKS = [1, 0.5, 0, -0.5, -1]

const fmtY = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v < 0 ? `−${Math.abs(v).toFixed(1)}` : '0')

interface Rect { x0: number; x1: number; y0: number; y1: number; midX: number; midY: number }

// Where each region's caption sits, as a fraction of the plot rect. Three of these ARE their
// quadrant, exactly: future_leaders, overrated_leaders and value_traps are defined as
// `lseg_percentile` either side of 0.5 crossed with the sign of momentum, which is precisely the
// axes drawn here.
//
// The top-left corner is not one label but two. `consensus` is the fallback for that quadrant,
// but `hidden_winners` is evaluated FIRST and carves companies out of it wherever the signed
// disagreement clears theta — currently about half the dots sitting there. Captioning that
// corner "Consensus" alone put the product's whole differentiator under the name of something
// else, and a reader matching green dots to the nearest caption drew the wrong conclusion. So
// the corner names both, and each half is drawn in the colour of its own dots.
const QUADRANTS: { keys: LabelKey[]; at: (r: Rect) => { x: number; y: number }; anchor: 'start' | 'end' }[] = [
  { keys: ['hidden_winners', 'consensus'], anchor: 'start', at: r => ({ x: r.x0 + 10, y: r.y0 + 16 }) },
  { keys: ['future_leaders'], anchor: 'end', at: r => ({ x: r.x1 - 10, y: r.y0 + 16 }) },
  { keys: ['value_traps'], anchor: 'start', at: r => ({ x: r.x0 + 10, y: r.y1 - 8 }) },
  { keys: ['overrated_leaders'], anchor: 'end', at: r => ({ x: r.x1 - 10, y: r.y1 - 8 }) },
]

/**
 * The A5 discipline: a non-matching company DIMS, it never disappears. A green-finance mandate
 * still has to be able to see the name it is choosing not to hold — hiding it would turn a
 * preference into a claim that the company does not exist.
 *
 * `greenLabelled` is read from the metadata CSV's `green_bond_status`, the same field the
 * Conservative tier and the N bucket use, so the setup's focus answer and the origination
 * counts can never mean different things by "green".
 */
const GREEN_LABELLED = ['cbi_certified', 'labelled_reviewed']

function matches(record: EngineRecord, tier: TierKey | 'all', pipelineOnly: boolean,
                 greenFocus: boolean, greenStatus: string): boolean {
  if (greenFocus && !GREEN_LABELLED.includes(greenStatus)) return false
  if (pipelineOnly && !record.tiers?.balanced) return false
  if (tier === 'all') return true
  return Boolean(record.tiers?.[tier])
}

export default function EngineBoard() {
  const { board, settings, setSettings, openEvidence, focusTicker, setFocus } = useStore()
  // The plot draws itself at 1:1 with its own box, so it has to know how wide that box is.
  //
  // A callback ref rather than useRef + useEffect: this component returns null until the board
  // has loaded, so a mount effect runs once against an element that does not exist yet and, with
  // an empty dependency list, never runs again. The plot then kept its 1000px default forever and
  // the browser scaled the whole chart up to fit — every stroke and label 2.5x oversized on a
  // wide monitor. A callback ref fires when the node actually arrives, and again when it leaves.
  const roRef = useRef<ResizeObserver | null>(null)
  const [wide, setWide] = useState(1000)
  const measureRef = useCallback((el: HTMLDivElement | null) => {
    roRef.current?.disconnect()
    roRef.current = null
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(entries => {
      const w = Math.round(entries[0].contentRect.width)
      if (w > 0) setWide(w)
    })
    ro.observe(el)
    roRef.current = ro
  }, [])
  const engine = board?.engine
  const nameOf = useMemo(() => {
    const map: Record<string, string> = {}
    for (const c of board?.constituents ?? []) map[c.ticker] = c.company
    return map
  }, [board])

  const rows = useMemo(() => Object.values(engine?.records ?? {}), [engine])
  const shown = useMemo(
    () => rows.filter(r => matches(r, settings.tier, settings.pipelineOnly, settings.greenFocus,
      engine?.badges?.[r.company_id]?.green_bond?.status || '')),
    [rows, engine, settings.tier, settings.pipelineOnly, settings.greenFocus])
  // The 90-second walk has to reach a Hidden Winner without hunting for a dot, so the strongest
  // disagreements get a named, one-click route straight into the evidence trail.
  const hidden = useMemo(
    () => rows.filter(r => r.label === 'hidden_winners')
      .sort((a, b) => b.disagreement - a.disagreement).slice(0, 5),
    [rows])

  if (!engine) return null
  const { nmk, labels, label_counts, label_tooltips, label_rules, tiers, tier_rules, anchor,
    horizons, half_life_days } = engine
  const dimmed = rows.length - shown.length
  const blankCount = rows.filter(r => r.signal_count === 0).length

  const W = clamp(MIN_W, wide, MAX_W)
  const H = heightFor(W)
  const rect: Rect = {
    x0: PAD.l, x1: W - PAD.r, y0: PAD.t, y1: H - PAD.b,
    midX: PAD.l + (W - PAD.r - PAD.l) / 2, midY: PAD.t + (H - PAD.b - PAD.t) / 2,
  }
  /** percentile 0..1 -> x */
  const xOf = (p: number) => rect.x0 + p * (rect.x1 - rect.x0)
  /** momentum -1..+1 -> y, +1 at the top */
  const yOf = (m: number) =>
    rect.y1 - ((Math.max(-1, Math.min(1, m)) + 1) / 2) * (rect.y1 - rect.y0)

  const point = (r: EngineRecord) => ({ cx: xOf(r.lseg_percentile), cy: yOf(r.composite_momentum) })

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
          <span title="The decay half-life this run was scored with. Flip it in the controls
 below — the whole board re-scores.">{half_life_days}d half-life</span>
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
        {/*
          Horizon sits beside the tiers but does something different, and the copy says so.
          A tier re-segments what is already scored; a horizon re-scores. Half-lives are printed
          on the buttons because "Short" and "Long" mean nothing on their own, and the numbers
          come from config — nothing here hard-codes 45 or 180.
        */}
        <div className="seg" role="group" aria-label="Decay horizon">
          {(Object.keys(horizons) as HorizonKey[]).sort().map(key => (
            <button key={key} className={`btn ${settings.horizon === key ? 'on' : ''}`}
              title={`Re-score with a ${horizons[key]}-day decay half-life. This is not a `
                + `filter: signal weights change, so momentum, quadrants and N/M/K all move, `
                + `and the run gets its own id.`}
              onClick={() => setSettings({ horizon: key })}>
              {key === 'short' ? 'Short' : 'Long'} {horizons[key]}d
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

      {/* The chart stops widening at MAX_W, so on a wide board the legend and the hidden-winner
          shortcuts move up beside it instead of leaving a band of empty panel either side. Below
          that width they fall back under the chart, which is the narrow-screen order anyway. */}
      <div className="matrix-row">
      <div className="matrix-wrap" ref={measureRef}>
        <svg viewBox={`0 0 ${W} ${H}`} className="matrix" role="img"
          aria-label="Quadrant matrix of incumbent rating percentile against live momentum">
          {/*
            The axes are the whole claim — x is the market's view of a company, y is ours, and the
            gap between them is the product. They are drawn as a real pair of axes: a framed L,
            ticked and labelled on both, with the two quadrant boundaries called out separately
            because those carry a meaning no other gridline does.
          */}

          {/* gridlines first, so everything else sits on top of them */}
          {X_TICKS.map(t => (
            <line key={`gx${t}`} x1={xOf(t)} y1={rect.y0} x2={xOf(t)} y2={rect.y1}
              className="matrix-grid" />
          ))}
          {Y_TICKS.map(t => (
            <line key={`gy${t}`} x1={rect.x0} y1={yOf(t)} x2={rect.x1} y2={yOf(t)}
              className="matrix-grid" />
          ))}

          {/* the two quadrant boundaries — the only gridlines that mean something */}
          <line x1={rect.midX} y1={rect.y0} x2={rect.midX} y2={rect.y1} className="matrix-divide" />
          <line x1={rect.x0} y1={rect.midY} x2={rect.x1} y2={rect.midY} className="matrix-divide" />
          <text x={rect.midX + 6} y={rect.y0 + 13} className="matrix-divide-label">median rating</text>
          <text x={rect.x1 - 6} y={rect.midY - 6} textAnchor="end" className="matrix-divide-label">
            no momentum
          </text>

          {/* the axis frame */}
          <line x1={rect.x0} y1={rect.y0} x2={rect.x0} y2={rect.y1} className="matrix-axis" />
          <line x1={rect.x0} y1={rect.y1} x2={rect.x1} y2={rect.y1} className="matrix-axis" />

          {/* y ticks + labels */}
          {Y_TICKS.map(t => (
            <g key={`y${t}`}>
              <line x1={rect.x0 - 6} y1={yOf(t)} x2={rect.x0} y2={yOf(t)} className="matrix-axis" />
              <text x={rect.x0 - 11} y={yOf(t) + 4} textAnchor="end" className="matrix-tick">
                {fmtY(t)}
              </text>
            </g>
          ))}

          {/* x ticks + labels */}
          {X_TICKS.map(t => (
            <g key={`x${t}`}>
              <line x1={xOf(t)} y1={rect.y1} x2={xOf(t)} y2={rect.y1 + 6} className="matrix-axis" />
              <text x={xOf(t)} y={rect.y1 + 20} textAnchor="middle" className="matrix-tick">
                {`${t * 100}%`}
              </text>
            </g>
          ))}

          {/* axis names */}
          <text x={rect.x0 - 62} y={rect.midY} className="matrix-axis-name"
            transform={`rotate(-90 ${rect.x0 - 62} ${rect.midY})`} textAnchor="middle">
            our live momentum →
          </text>
          <text x={(rect.x0 + rect.x1) / 2} y={rect.y1 + 44} textAnchor="middle"
            className="matrix-axis-name">
            what the incumbent rating thinks — percentile →
          </text>
          <text x={rect.x0} y={rect.y1 + 44} textAnchor="start" className="matrix-end">laggard</text>
          <text x={rect.x1} y={rect.y1 + 44} textAnchor="end" className="matrix-end">leader</text>

          {QUADRANTS.map(q => (
            <text key={q.keys.join('+')} {...q.at(rect)} textAnchor={q.anchor} className="matrix-quad">
              {q.keys.map((key, i) => (
                <Fragment key={key}>
                  {i > 0 && <tspan className="matrix-quad-sep"> · </tspan>}
                  <tspan className={LABEL_TONE[key]}>{labels[key]}</tspan>
                </Fragment>
              ))}
            </text>
          ))}
          {rows.map(r => {
            const { cx, cy } = point(r)
            const on = matches(r, settings.tier, settings.pipelineOnly, settings.greenFocus,
              engine.badges?.[r.company_id]?.green_bond?.status || '')
            const isFocus = r.company_id === focusTicker
            // No evidence is not the same claim as evidence that says flat, and on this plot
            // both land on exactly y=0 — so they are drawn differently. A hollow dot reads as
            // "nothing to say about this one yet", which is what a zero signal count means.
            const blank = r.signal_count === 0
            return (
              <circle key={r.company_id} cx={cx} cy={cy}
                r={r.label === 'hidden_winners' ? 8 : 6}
                className={`matrix-dot ${LABEL_TONE[r.label]} ${on ? '' : 'is-dim'} ${isFocus ? 'is-focus' : ''}${blank ? ' is-blank' : ''}`}
                onClick={() => { setFocus(r.company_id); openEvidence(r.company_id) }}>
                <title>{`${nameOf[r.company_id] || r.company_id} — ${r.label_display}
rating percentile ${(r.lseg_percentile * 100).toFixed(0)}% · momentum ${r.composite_momentum >= 0 ? '+' : ''}${r.composite_momentum.toFixed(2)}
disagreement ${r.disagreement >= 0 ? '+' : ''}${r.disagreement.toFixed(2)} · confidence ${r.composite_confidence.toFixed(2)} · ${r.signal_count} signals`}</title>
              </circle>
            )
          })}
        </svg>
      </div>

      <div className="matrix-side">
      {/* Overplotting on the zero line is a real reading hazard on the verified basket, where
          more than half the names have nothing scorable yet. Saying the number out loud turns
          an unreadable smear into the finding it actually is. */}
      {blankCount > 0 && (
        <p className="matrix-blank-note">
          <b>{blankCount}</b> of {rows.length} companies have no scorable evidence yet and sit on
          the zero line, drawn hollow. That is an absence of evidence, not evidence of no
          movement — and closing that gap is what the alt-data feeds are for.
        </p>
      )}
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
      </div>
      </div>

      {/* Provenance + maker-checker. Two different claims, kept apart on purpose: the rows are
          verified BY US against the ICMA-based process, which is not the same as CGSI having
          confirmed them — the panel never received the 52-name results, so the header says so
          rather than letting "verified" imply an endorsement nobody gave. */}
      {engine.metadata.rows > 0 && (
        <div className="cc-muted engine-foot">
          <span className={`review-chip ${engine.metadata.verified ? 'on' : 'pending'}`}>
            {engine.metadata.review_chip || 'AI-assisted · pending review'}
          </span>
          {/* `header` already states the provisional-vs-verified claim in full; repeating it
              here read as "PROVISIONAL ... PROVISIONAL ...". Only the reviewer and the file
              path are added. */}
          {engine.metadata.header}{' '}
          {engine.metadata.verified && <>Reviewer: {engine.metadata.verified_by} — </>}
          <span className="mono-path">{engine.metadata.path}</span>
        </div>
      )}
    </div>
  )
}
