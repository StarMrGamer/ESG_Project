import type { EngineRecord, TierKey } from '../types'

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
