import type { DualRow } from '../../types'

/**
 * DUAL MOMENTUM — the two directions, side by side, with what their combination is called.
 *
 * The product's argument has always been one disagreement: our live evidence against a stale
 * rating. This adds the second one a reader asks for immediately — what has the MARKET already
 * done? — and puts the two on the same card so the interesting case is visible rather than
 * inferred:
 *
 *   financial momentum up + evidence up    -> Aligned
 *   financial momentum up + evidence DOWN  -> Divergence, downside risk. The People/Planet side
 *                                             is going backwards while the price is not marking
 *                                             it, which is the shape a static rating cannot see.
 *
 * THREE RULES HOLD THIS HONEST, and they are the whole reason it is a separate component rather
 * than another number in the record:
 *
 * 1. **The price never enters the score.** `price_momentum.py` cannot be reached from `engine.py`
 *    or `signals.py` and `selftest.py` pins it. `composite_momentum` is still a consensus over
 *    dated documentary evidence and `disagreement` is still our percentile minus the rating's.
 *    Nothing on this card moved a quadrant.
 * 2. **Alignment is not a recommendation.** "Aligned" means two directions agree, and agreement
 *    says nothing about what is already priced in — which is stated on the card rather than left
 *    for the reader to assume. There is no buy, sell, hold, cheap or undervalued here.
 * 3. **It carries no accuracy claim.** No hit rate, no "downside risk halved", no failure rate.
 *    No backtest in this repo has produced one, and a plausible statistic is the single most
 *    effective way to make a card look more authoritative than its evidence.
 *
 * The window is printed because "momentum" without one is meaningless: this is the classical
 * 12-1 factor — twelve months of return ending ONE MONTH AGO, skipping the documented one-month
 * reversal. And the capture date is printed because the basket runs off a dated snapshot; a
 * stored price shown as current would be a rule-3 breach for the sake of looking fresher.
 */

/** An arrow that means the direction, with the word beside it — colour alone is not a label. */
function Arrow({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="dual-arrow is-flat" aria-label="not available">—</span>
  const up = v > 0
  const flat = v === 0
  return (
    <span className={`dual-arrow ${flat ? 'is-flat' : up ? 'is-up' : 'is-down'}`}
      aria-label={flat ? 'flat' : up ? 'rising' : 'falling'}>
      {flat ? '→' : up ? '↑' : '↓'}
    </span>
  )
}

const fmtPx = (v: number | null | undefined) =>
  v == null ? 'not quotable' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

/** The evidence side is a direction CONSENSUS on −1..+1, not a percentage. Never suffix it. */
const fmtEsg = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`

export default function DualMomentum({ row, compact = false }:
  { row: DualRow | null | undefined; compact?: boolean }) {
  if (!row) return null
  const unknown = row.alignment === 'unknown'

  return (
    <div className={`dual ${compact ? 'is-compact' : ''} dual-${row.tone}`}
      data-tour="dual-momentum">
      <div className="dual-legs">
        <div className="dual-leg">
          <span className="dual-leg-k">Financial price momentum</span>
          <span className="dual-leg-v">
            <Arrow v={row.price_pct} />
            <b>{fmtPx(row.price_pct)}</b>
          </span>
          <span className="dual-leg-f" title={row.window_label
            || '12 months of return ending one month ago — the classical momentum factor. The skipped month is deliberate: the one-month reversal is an opposite-signed effect.'}>
            {row.price_window} factor · price is context, never a score input
          </span>
        </div>

        <div className="dual-leg">
          <span className="dual-leg-k">ESG evidence momentum</span>
          <span className="dual-leg-v">
            <Arrow v={row.signal_count > 0 ? row.esg_momentum : null} />
            <b>{row.signal_count > 0 ? fmtEsg(row.esg_momentum) : 'no evidence yet'}</b>
          </span>
          <span className="dual-leg-f">
            {row.signal_count > 0
              ? `${row.signal_count} scored signals · direction consensus, −1 to +1`
              : 'nothing scorable — an absence, not a flat reading'}
          </span>
        </div>
      </div>

      <div className={`dual-tag dual-tag-${row.tone}`} title={row.tooltip || ''}>
        {row.display}
      </div>

      {/* Two things the reader is owed and would otherwise supply themselves, wrongly: that
          agreement is not a verdict on value, and that nothing here touched the score. */}
      {!compact && !unknown && (
        <p className="dual-note cc-muted">
          Two directions, reported next to each other — not a recommendation, and it says nothing
          about what the market has already priced in. The price is context beside the ESG read
          and never inside it: no part of it reaches momentum, disagreement or a quadrant.
        </p>
      )}
      {/* The reason comes from the server, which is the only place that knows WHICH universe is
          loaded. Deriving it here from `price_pct == null` told a reader looking at a fictional
          demo company that our symbol column did not cover it — true of the lookup, and quietly
          implying the company was real. */}
      {!compact && unknown && row.why && (
        <p className="dual-note cc-muted">{row.why}</p>
      )}
      {!compact && !unknown && row.captured && (
        <p className="dual-note cc-muted">
          Price from a dated snapshot captured {row.captured} — context, not a live tick.
        </p>
      )}
    </div>
  )
}
