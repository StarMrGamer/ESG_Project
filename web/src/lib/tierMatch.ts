import type { EngineRecord, TierKey } from '../types'
import type { PPP } from '../store'

/**
 * Does this company survive the current view's filters?
 *
 * Extracted from `EngineBoard` so the setup's live preview and the matrix cannot disagree. A
 * preview that promises "31 names in view" and then lands you on a board showing 24 is worse
 * than no preview: it teaches the reader that the numbers are decorative.
 *
 * The green-bond statuses that count as "labelled" are named here for the same reason — the
 * A5 tiers, the N bucket and this filter must never mean different things by "green".
 */
export const GREEN_LABELLED = ['cbi_certified', 'labelled_reviewed']

export function matches(record: EngineRecord, tier: TierKey | 'all', pipelineOnly: boolean,
                        greenFocus: boolean, greenStatus: string, bucket = ''): boolean {
  if (greenFocus && !GREEN_LABELLED.includes(greenStatus)) return false
  // ORIGINATION MEANS THE M BUCKET. This used to test `record.tiers.balanced` — the A5 RISK
  // TIER — so a button labelled "Origination pipeline" filtered by risk appetite and left two
  // companies on screen while the chip beside it read "M 10 pipeline (bond-ready)". The control
  // promised one thing and did another, in the same row of the same panel.
  //
  // `bucket` comes from the same `pipeline_counts.bucket_of` map that produces the N/M/K totals,
  // so the filter and the count cannot disagree by construction.
  if (pipelineOnly && bucket !== 'M') return false
  if (tier === 'all') return true
  return Boolean(record.tiers?.[tier])
}

/**
 * The PPP lens, as a predicate on one already-scored record.
 *
 * It is deliberately SEPARATE from `matches` rather than a seventh positional argument: the two
 * answer different questions, and the Planet lens needs no code here at all — it is the
 * green-bond hurdle, which `matches` already applies through the derived `greenFocus` flag. Only
 * Profit First adds a rule.
 *
 * PROFIT FIRST IS A DOWNSIDE GATE, NOT A RANKING. It dims a company whose dated evidence is
 * DETERIORATING, however well the price has run — that is what "ESG as a strict downside warning
 * gate" means, and it is the one thing a return-led reader most needs the ESG side for. It does
 * NOT dim on the price direction: this product does not rank by return, and a filter that hid
 * every name with a weak share price would be picking, which is HARD RULE 4.
 *
 * A company with no evidence scores exactly 0.000 and PASSES. An absence of evidence is not a
 * downside warning, and dimming on it would turn our own coverage gap into a verdict about the
 * company — the same trap `align` avoids by consulting the signal count.
 */
export function passesPPP(ppp: PPP, record: EngineRecord): boolean {
  if (ppp !== 'profit') return true
  return (record.composite_momentum ?? 0) >= 0
}

/** Why a name is dimmed under this lens, for the caption beside the count. */
export const PPP_DIM_REASON: Record<PPP, string> = {
  profit: 'deteriorating evidence — the downside gate, whatever the price has done',
  balanced: '',
  planet: 'no labelled green bond',
}

/**
 * WHY each name is dimmed, split by cause — the ONE definition, used by both the matrix caption
 * and the PPP strip.
 *
 * It exists because those two disagreed twice while being written, in opposite directions. The
 * strip counted the lens across the whole basket and said "3 dimmed" beside a matrix that had
 * already dimmed all three by risk tier and reported 0. Then the matrix called the green-bond
 * hurdle "the risk tier", because `greenFocus` lives INSIDE `matches` and the tier was set to
 * `all` — so 39 names were attributed to a filter that was dimming nothing.
 *
 * The split is therefore taken in a fixed order, not independently:
 *
 *   tier — fails `matches` with the green hurdle forced OFF: the risk tier, or the pipeline filter
 *   lens — survives that, and is then removed by the PPP lens (the green hurdle, or the profit gate)
 *
 * So the two parts always sum to the total dimmed and no name is blamed twice. `meta` is looked
 * up by the caller, which is the only thing either component knows that this module does not.
 */
export interface DimSplit { tier: number; lens: number; total: number }

export function dimSplit(
  records: EngineRecord[],
  s: { tier: TierKey | 'all'; pipelineOnly: boolean; greenFocus: boolean; ppp: PPP },
  meta: (r: EngineRecord) => { greenStatus: string; bucket: string },
): DimSplit {
  let tier = 0
  let lens = 0
  for (const r of records) {
    const { greenStatus, bucket } = meta(r)
    // The green hurdle is a LENS, so it is held off for the tier's own count.
    if (!matches(r, s.tier, s.pipelineOnly, false, greenStatus, bucket)) { tier++; continue }
    if (!matches(r, s.tier, s.pipelineOnly, s.greenFocus, greenStatus, bucket)
        || !passesPPP(s.ppp, r)) lens++
  }
  return { tier, lens, total: tier + lens }
}
