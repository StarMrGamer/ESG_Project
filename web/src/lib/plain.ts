/**
 * PLAIN — the same findings, in words a person outside a desk can read.
 *
 * Every function here is a RENDERING of a number the engine already computed. Nothing is
 * rounded up, softened, or re-derived: `bandOf(0.97)` says "near the top" because 0.97 is near
 * the top, and the number itself is one click away behind "Show the numbers". If a phrase here
 * ever stops being a faithful reading of its input, the fix is the phrase — never the input.
 *
 * WHY THIS EXISTS. The product's unit is `disagreement = our evidence percentile − the rating's`,
 * which is exactly the right unit for the analyst it was built for and unreadable for someone
 * holding forty shares of the bank in question. "+0.80" is not a fact anybody can act on; "its
 * rating puts it in the bottom fifth, and fourteen dated sources say it is the fastest-improving
 * name in its basket" is the same fact, and it is checkable by the person reading it.
 *
 * THE LINE THIS FILE DOES NOT CROSS. Friendlier wording, identical arithmetic — and never a
 * recommendation. There is no phrasing of "buy", "sell", "hold", "undervalued" or "worth owning"
 * anywhere below, because plain language is exactly how that boundary gets crossed by accident:
 * a percentile cannot be mistaken for advice, and a warm sentence can. The caveats get the same
 * treatment as the findings — if most of the evidence is company-published, the plain version
 * says so in plain words too.
 */
import type { LabelKey } from '../types'

/** Where a percentile sits, in words. Bands are stated so the reader can check the mapping. */
export function bandOf(p: number): string {
  if (p >= 0.8) return 'near the top'
  if (p >= 0.6) return 'in the upper half'
  if (p >= 0.4) return 'around the middle'
  if (p >= 0.2) return 'in the lower half'
  return 'in the bottom fifth'
}

/** The quadrant label, as a sentence rather than a term of art. */
export const LABEL_PLAIN: Record<LabelKey, { head: string; gloss: string }> = {
  hidden_winners: {
    head: 'Rated behind its evidence',
    gloss: 'The published rating sits well below what the dated evidence says — and there is '
      + 'enough evidence, from good enough sources, to mean it.',
  },
  future_leaders: {
    head: 'Improving, and its rating already says so',
    gloss: 'Rated above the middle of this basket, and still improving on the evidence. The '
      + 'rating and our read agree.',
  },
  overrated_leaders: {
    head: 'Flattered by an older score',
    gloss: 'Rated above the middle of the basket while the dated evidence points the other way. '
      + 'This is the gap a score that refreshes slowly cannot show you.',
  },
  value_traps: {
    head: 'Poorly rated, and still slipping',
    gloss: 'Rated below the middle, and the evidence agrees it is getting worse rather than '
      + 'better.',
  },
  consensus: {
    head: 'The rating and the evidence agree',
    gloss: 'Nothing here contradicts the published score. That is a finding too — most companies '
      + 'land here.',
  },
}

/** How much weight the evidence can carry, and WHY it is capped when it is. */
export function strengthOf(confidence: number, signals: number, meanQuality: number) {
  const word = confidence >= 0.7 ? 'strong'
    : confidence >= 0.5 ? 'fair'
    : confidence >= 0.3 ? 'thin'
    : 'very thin'
  const why = meanQuality > 0 && meanQuality <= 0.55
    // The Adaro cap, said plainly: company announcements can never count like a regulator.
    ? 'mostly the companies’ own announcements, which we deliberately count for less'
    : meanQuality >= 0.8
      ? 'mostly filings, exchange notices and regulators'
      : 'a mix of company announcements and independent sources'
  return { word, why, line: `${word} — ${signals} dated ${signals === 1 ? 'source' : 'sources'}, ${why}` }
}

/** The financial gate, in a sentence. `unknown` is not a failure and must never read as one. */
export const FINANCIAL_PLAIN: Record<string, string> = {
  strong: 'The business itself is growing on its last two reported years.',
  adequate: 'The business itself looks steady on its last two reported years.',
  weak: 'The business itself is going backwards on its last two reported years.',
  unknown: 'We cannot read the business from the two figures we hold — so we say nothing rather '
    + 'than mark it down.',
}

/** Days of evidence memory, as a length of time somebody thinks in. */
export const horizonPlain = (halfLifeDays: number) =>
  halfLifeDays >= 120 ? 'the last six months or so' : 'the last six weeks or so'

/**
 * What would move this verdict — the retail-facing reading of the sensitivity report.
 *
 * `load_bearing_count` is how many single removals change the label; `smallest_flip_set` is how
 * many of the heaviest would have to go together. Both are worth saying, and neither is worth
 * saying in those words.
 */
export function watchLine(loadBearing: number | null, flipSet: number | null, signals: number) {
  if (loadBearing === null) return ''
  if (loadBearing === 0) {
    if (!flipSet) return 'No single source is holding this up.'
    // Agreement, not decoration: `flipSet` is a live count off the sensitivity report, and the
    // sentence has to read at 2 as well as at 11. "2 of the heaviest would ALL have to be
    // wrong" does not agree, and at 1 it would contradict the clause before it.
    if (flipSet === 1) return 'No single source decides this, but the heaviest one would change it.'
    const many = flipSet === 2 ? 'both' : 'all'
    return `No single source is holding this up — the ${flipSet} heaviest would ${many} have `
      + `to be wrong before the answer changed.`
  }
  if (loadBearing === 1) return 'One source is holding this up. If it were wrong, the answer changes.'
  return `${loadBearing} of the ${signals} sources are load-bearing: pull any one of them out and `
    + `the answer changes. That is a verdict balanced on a line, not a strong one.`
}

/** Module names, for the picker, when the reader is not an analyst. */
export const MODULE_PLAIN: Record<string, string> = {
  matrix: 'Where every company sits',
  case: 'Why we say this',
  classification: 'The one-line verdict',
  rankings: 'Biggest gaps in the basket',
  universe: 'Browse all the companies',
  news: 'Recent news',
  price: 'Share price (context only)',
  rails: 'Filters and the assistant',
}
