import { useCallback, useMemo, useRef, useState } from 'react'
import { useStore } from '../../store'
import type { EngineRecord, HorizonKey, TierKey } from '../../types'
import { dimSplit, matches, passesPPP, PPP_DIM_REASON } from '../../lib/tierMatch'
import { useCollapsed } from '../ui'

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

/** Where the tick marks and gridlines fall on the y axis. x has its own — see `PX_TICKS`. */
const Y_TICKS = [1, 0.5, 0, -0.5, -1]

/**
 * ONE PLOT: price momentum across, our evidence up.
 *
 * It used to be two, switchable — the original x was the incumbent RATING percentile, so a Hidden
 * Winner sat top-LEFT, rated low while improving. That plot was removed on 2026-09-01 on an
 * explicit instruction, and the toggle with it.
 *
 * Worth knowing if you are thinking of bringing it back: the rating percentile is still on every
 * record as `lseg_percentile`, it still drives `disagreement` and every quadrant label, and the
 * legend below still counts those labels. So the rating axis was DROPPED FROM THE DRAWING, not
 * from the engine — nothing about how a company is classified changed. What is lost is the
 * picture of it, which is why the quadrant captions here now describe price-vs-evidence corners
 * and the label legend beside them still describes rating-vs-evidence ones. Those are two
 * different readings of the same 52 companies and the panel says so rather than implying the
 * captions and the legend are the same axis.
 */
const PLOT = {
  xName: 'financial price momentum — 12-1 factor →',
  xLow: 'price falling', xHigh: 'price rising',
  xDivide: 'no price momentum',
} as const

/** Price momentum in percent, mapped onto the same −1..+1 half-width the plot already draws. */
const PX_FULL_SCALE = 60
const pxToUnit = (pct: number) => Math.max(-1, Math.min(1, pct / PX_FULL_SCALE))
const PX_TICKS = [1, 0.5, 0, -0.5, -1]
const fmtPx = (u: number) => `${u > 0 ? '+' : u < 0 ? '−' : ''}${Math.abs(u * PX_FULL_SCALE).toFixed(0)}%`

/**
 * The dual plot's own corners. Named for the combination they ARE, not for a quadrant label
 * borrowed from the other plot — `hidden_winners` is a rule about a RATING and cannot be
 * evaluated here at all.
 */
const DUAL_QUADRANTS: { key: string; caption: string; tone: string; anchor: 'start' | 'end';
                        at: (r: Rect) => { x: number; y: number }; title: string }[] = [
  { key: 'aligned', caption: 'Dual momentum aligned', tone: 'q-hidden', anchor: 'end',
    at: r => ({ x: r.x1 - 10, y: r.y0 + 16 }),
    title: 'Price rising and evidence improving. Agreement between the market and our read — not a recommendation, and it says nothing about what is already priced in.' },
  { key: 'evidence_ahead', caption: 'Evidence ahead of price', tone: 'q-future', anchor: 'start',
    at: r => ({ x: r.x0 + 10, y: r.y0 + 16 }),
    title: 'Our dated evidence is improving while the price has fallen over the window. The mirror of the trap.' },
  { key: 'downside_trap', caption: 'Downside risk · value traps', tone: 'q-trap', anchor: 'end',
    at: r => ({ x: r.x1 - 10, y: r.y1 - 8 }),
    title: 'The price is running while our dated evidence deteriorates — the People/Planet side going backwards without the market marking it. This is the shape a static rating cannot see.' },
  { key: 'both_falling', caption: 'Both deteriorating', tone: 'q-overrated', anchor: 'start',
    at: r => ({ x: r.x0 + 10, y: r.y1 - 8 }),
    title: 'Price and evidence both negative over their respective windows.' },
]

const fmtY = (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v < 0 ? `−${Math.abs(v).toFixed(1)}` : '0')

interface Rect { x0: number; x1: number; y0: number; y1: number; midX: number; midY: number }


/**
 * The A5 discipline: a non-matching company DIMS, it never disappears. A green-finance mandate
 * still has to be able to see the name it is choosing not to hold — hiding it would turn a
 * preference into a claim that the company does not exist.
 *
 * `greenLabelled` is read from the metadata CSV's `green_bond_status`, the same field the
 * Conservative tier and the N bucket use, so the setup's focus answer and the origination
 * counts can never mean different things by "green". Both now live in lib/tierMatch so the
 * setup's live preview is computed by the SAME rule this plot draws with.
 */
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
  // The PPP lens rides alongside the tier and pipeline filters rather than inside `matches`:
  // Sustainability Focus needs no code here at all (it IS `greenFocus`, derived in the store),
  // and only Profit First adds a rule. Same A5 discipline either way — a non-matching name DIMS.
  const base = useCallback((r: EngineRecord) =>
    matches(r, settings.tier, settings.pipelineOnly, settings.greenFocus,
      engine?.badges?.[r.company_id]?.green_bond?.status || '',
      engine?.badges?.[r.company_id]?.pipeline?.bucket || ''),
    [engine, settings.tier, settings.pipelineOnly, settings.greenFocus])
  const on = useCallback((r: EngineRecord) => base(r) && passesPPP(settings.ppp, r),
    [base, settings.ppp])
  const shown = useMemo(() => rows.filter(on), [rows, on])
  // The 90-second walk has to reach a Hidden Winner without hunting for a dot, so the strongest
  // disagreements get a named, one-click route straight into the evidence trail.
  const hidden = useMemo(
    () => rows.filter(r => r.label === 'hidden_winners')
      .sort((a, b) => b.disagreement - a.disagreement).slice(0, 5),
    [rows])

  if (!engine) return null
  const { nmk, labels, label_counts, label_tooltips, label_rules, tiers, tier_rules, anchor,
    horizons, half_life_days } = engine
  // WHY a name is dimmed, split by cause — see `dimSplit`, which both this caption and the PPP
  // strip read, so the two can never report the same control differently.
  const dim = dimSplit(rows, settings, r => ({
    greenStatus: engine.badges?.[r.company_id]?.green_bond?.status || '',
    bucket: engine.badges?.[r.company_id]?.pipeline?.bucket || '',
  }))
  const blankCount = rows.filter(r => r.signal_count === 0).length

  const W = clamp(MIN_W, wide, MAX_W)
  const H = heightFor(W)
  const rect: Rect = {
    x0: PAD.l, x1: W - PAD.r, y0: PAD.t, y1: H - PAD.b,
    midX: PAD.l + (W - PAD.r - PAD.l) / 2, midY: PAD.t + (H - PAD.b - PAD.t) / 2,
  }
  const dual = board?.dual

  /** percentile 0..1 -> x */
  const xOf = (p: number) => rect.x0 + p * (rect.x1 - rect.x0)
  /** −1..+1 -> x, for the dual plot, where 0 is the middle rather than the left edge */
  const xOfUnit = (u: number) => xOf((Math.max(-1, Math.min(1, u)) + 1) / 2)

  /**
   * The x coordinate for one company on the CURRENT plot, or null.
   *
   * Null is the load-bearing case: on the dual plot a company with no quotable listing has no x
   * at all — nine of the 52, being the seven Philippine names our audited symbol column does not
   * cover and the two delisted constituents. They are DROPPED and counted beside the chart
   * rather than parked at zero, because a dot at x=0 says "the price did not move", which is a
   * measurement we did not make. The same distinction the hollow dots draw on the y axis.
   */
  const xFor = (r: EngineRecord): number | null => {
    const pct = dual?.rows?.[r.company_id]?.price_pct
    return pct == null ? null : xOfUnit(pxToUnit(pct))
  }
  const unquotable = rows.filter(r => dual?.rows?.[r.company_id]?.price_pct == null).length
  /** momentum -1..+1 -> y, +1 at the top */
  const yOf = (m: number) =>
    rect.y1 - ((Math.max(-1, Math.min(1, m)) + 1) / 2) * (rect.y1 - rect.y0)



  const [open, toggleOpen] = useCollapsed('matrix', true)

  return (
    <div className={`engine-board section ${open ? 'is-open' : 'is-closed'}`} data-tour="matrix">
      <div className="engine-head">
        <div>
          {/* The matrix measures its own box with a ResizeObserver, so it keeps its own chrome
              and takes a fold toggle in place rather than being wrapped in a <Section>. */}
          <button className="section-toggle" onClick={toggleOpen} aria-expanded={open}
            title={open ? 'Fold the matrix' : 'Unfold the matrix'}>
            <span className="section-chev" aria-hidden="true">▾</span>
            <span className="cc-h section-title">Dual momentum matrix</span>
          </button>
          {/* The densest thing in the product, one click from its own explanation — and the
              click has to be findable, so it sits on the title line rather than under it. */}
          <button className="btn matrix-explain" data-tour="explain-matrix"
            onClick={() => setSettings({ tourDeck: 'matrix' })}
            title="Walk the plot corner by corner: both directions, the two dividing lines, each quadrant, and what a dimmed or hollow dot means.">
            <span className="matrix-explain-q" aria-hidden>?</span> What am I looking at?
          </button>
          <div className="cc-muted">
            x = 12-1 price momentum (<b title="Twelve months of return ending ONE MONTH ago — the
              classical momentum factor. The skipped month is deliberate: the one-month reversal
              is a documented, opposite-signed effect. Read from a dated snapshot, and never an
              input to any score.">price is context, not a score</b>)
            {' · '}y = our live momentum, <b title="Direction consensus (the weighted mean of
              each signal's +1/-1) scaled by evidence weight, so one thin signal cannot score
              like twelve corroborating ones. Names cluster where the evidence agrees; an
              extreme score has to be earned.">−1 to +1</b>
            {' · '}{shown.length} of {rows.length} in view
          </div>
        </div>
        {/* Run id, as-of, half-life and the chain chip — the provenance a reader checks first.
            It used to fold away for the investor rendering; there is one reader now and this is
            the line they came for, so it is always on. */}
        <div className="engine-run"
          title={`config ${engine.config_version} · ${engine.config_hash}`}>
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

      {open && (<>

      <div className="engine-controls">
        <div className="seg" role="group" aria-label="Risk appetite" data-tour="tiers">
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
          data-tour="pipeline" title={nmk.rules.M}
          onClick={() => setSettings({ pipelineOnly: !settings.pipelineOnly })}>
          Origination pipeline {settings.pipelineOnly ? 'on' : 'off'}
        </button>
        <div className="nmk" data-tour="nmk">
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
          {PX_TICKS.map(u => (
            <line key={`gx${u}`} x1={xOfUnit(u)} y1={rect.y0} x2={xOfUnit(u)} y2={rect.y1}
              className="matrix-grid" />
          ))}
          {Y_TICKS.map(t => (
            <line key={`gy${t}`} x1={rect.x0} y1={yOf(t)} x2={rect.x1} y2={yOf(t)}
              className="matrix-grid" />
          ))}

          {/* the two quadrant boundaries — the only gridlines that mean something */}
          <line x1={rect.midX} y1={rect.y0} x2={rect.midX} y2={rect.y1} className="matrix-divide" />
          <line x1={rect.x0} y1={rect.midY} x2={rect.x1} y2={rect.midY} className="matrix-divide" />
          <text x={rect.midX + 6} y={rect.y0 + 13} className="matrix-divide-label"
            data-tour="boundaries">{PLOT.xDivide}</text>
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

          {/* x ticks + labels. x is a SIGNED percent around a zero in the middle, so the ticks
              run -60%..+60% rather than a 0-100 percentile scale. */}
          {PX_TICKS.map(u => (
              <g key={`x${u}`}>
                <line x1={xOfUnit(u)} y1={rect.y1} x2={xOfUnit(u)} y2={rect.y1 + 6} className="matrix-axis" />
                <text x={xOfUnit(u)} y={rect.y1 + 20} textAnchor="middle" className="matrix-tick">
                  {fmtPx(u)}
                </text>
              </g>
            ))}

          {/* axis names */}
          <text x={rect.x0 - 62} y={rect.midY} className="matrix-axis-name" data-tour="axis-y"
            transform={`rotate(-90 ${rect.x0 - 62} ${rect.midY})`} textAnchor="middle">
            our live momentum →
          </text>
          <text x={(rect.x0 + rect.x1) / 2} y={rect.y1 + 44} textAnchor="middle"
            className="matrix-axis-name" data-tour="axis-x">
            {PLOT.xName}
          </text>
          <text x={rect.x1} y={rect.y0 - 10} textAnchor="end" className="matrix-end">
            click a dot to focus it · click it again for the evidence
          </text>
          <text x={rect.x0} y={rect.y1 + 44} textAnchor="start" className="matrix-end">{PLOT.xLow}</text>
          <text x={rect.x1} y={rect.y1 + 44} textAnchor="end" className="matrix-end">{PLOT.xHigh}</text>

          {DUAL_QUADRANTS.map(q => (
            <text key={q.key} {...q.at(rect)} textAnchor={q.anchor}
              className={`matrix-quad ${q.tone}`} data-tour={`quad-${q.key}`}>
              {q.caption}
              <title>{q.title}</title>
            </text>
          ))}
          {rows.map(r => {
            const cx = xFor(r)
            // No x on this plot means we did not measure it. Drop the dot and say so beside the
            // chart rather than parking it at zero, which would read as a real reading of zero.
            if (cx == null) return null
            const cy = yOf(r.composite_momentum)
            const lit = on(r)
            // Two-stage click. One click used to focus AND open the evidence trail, which meant
            // every exploratory click on a 52-dot plot threw the reader into a full-screen panel
            // they then had to back out of. First click brings the company onto the board above
            // (the overview); a second click on the same dot opens the evidence.
            const isFocus = r.company_id === focusTicker
            // No evidence is not the same claim as evidence that says flat, and on this plot
            // both land on exactly y=0 — so they are drawn differently. A hollow dot reads as
            // "nothing to say about this one yet", which is what a zero signal count means.
            const blank = r.signal_count === 0
            return (
              <circle key={r.company_id} cx={cx} cy={cy}
                r={r.label === 'hidden_winners' ? 8 : 6}
                className={`matrix-dot ${LABEL_TONE[r.label]} ${lit ? '' : 'is-dim'} ${isFocus ? 'is-focus' : ''}${blank ? ' is-blank' : ''}`}
                onClick={() => { if (isFocus) openEvidence(r.company_id); else setFocus(r.company_id) }}>
                <title>{`${nameOf[r.company_id] || r.company_id} — ${r.label_display}
price momentum ${(dual?.rows?.[r.company_id]?.price_pct ?? 0) >= 0 ? '+' : ''}${(dual?.rows?.[r.company_id]?.price_pct ?? 0).toFixed(1)}% (12-1)} · evidence momentum ${r.composite_momentum >= 0 ? '+' : ''}${r.composite_momentum.toFixed(2)}
disagreement ${r.disagreement >= 0 ? '+' : ''}${r.disagreement.toFixed(2)} · confidence ${r.composite_confidence.toFixed(2)} · ${r.signal_count} signals${lit ? '' : '\ndimmed by the current filter — dimmed, never hidden'}

${isFocus ? 'Focused above — click again to open its evidence trail.' : 'Click to bring this company onto the board above.'}`}</title>
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
      {/* The x-axis twin of the hollow-dot note. Nine names have no quotable listing, so on the
          dual plot they have no x at all — the seven Philippine names our audited symbol column
          does not cover, and the two delisted constituents. Dropping them silently would make
          the plot quietly smaller than the basket. */}
      {unquotable > 0 && (
        <p className="matrix-blank-note">
          <b>{unquotable}</b> of {rows.length} companies have no quotable listing, so they have no
          price axis and are not drawn here. Seven are Philippine names our audited symbol column
          does not cover; two are the delisted constituents. They are all still on the rating plot.
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
        {dim.total > 0 && (
          <span className="cc-muted">
            {dim.tier > 0 && <>
              {dim.tier} dimmed by the {settings.pipelineOnly ? 'pipeline filter' : 'risk tier'}
            </>}
            {dim.tier > 0 && dim.lens > 0 && ' · '}
            {dim.lens > 0 && <>
              {dim.lens} by the PPP lens — {PPP_DIM_REASON[settings.ppp]}
            </>}
            {' '}— dimmed, not hidden.
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
          {engine.harvest && engine.harvest.events > 0 && (
            <span className="harvest-note" title={engine.harvest.note}>
              +{engine.harvest.events} harvested across {engine.harvest.companies}
            </span>
          )}
          {engine.metadata.header}{' '}
          {engine.metadata.verified && <>Reviewer: {engine.metadata.verified_by} — </>}
          <span className="mono-path">{engine.metadata.path}</span>
        </div>
      )}
      </>)}
    </div>
  )
}
