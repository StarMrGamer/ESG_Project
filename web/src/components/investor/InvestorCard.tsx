import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import { LABEL_PLAIN, FINANCIAL_PLAIN, bandOf, horizonPlain, strengthOf, watchLine } from '../../lib/plain'
import type { LabelKey, TrailRow } from '../../types'

/**
 * The investor's front page: one company, in sentences.
 *
 * Everything on this card is already on the board somewhere — the label, the two percentiles,
 * the confidence, the financial gate, the sensitivity report, the dated trail. What changes is
 * that a reader who does not work on a desk can follow it: no percentile, no signed
 * disagreement, no `composite_confidence`, and the receipts are three real sources with dates
 * and links rather than a panel three levels down.
 *
 * FOUR RULES, and the first two are the ones that keep this honest.
 *
 * 1. **Nothing here is softened.** A weak financial read says the business is going backwards.
 *    A thin evidence base says thin, and says why. `unknown` says we cannot tell rather than
 *    quietly reading as a pass. The whole reason the plain version is allowed to exist is that
 *    it says the same thing as the numbers.
 * 2. **No recommendation, in any wording.** The plainer the language, the easier it is to slide
 *    from "the rating looks stale here" into "this is worth buying", and that slide is the one
 *    failure this product cannot have. There is no buy, sell, hold, cheap, undervalued or
 *    should-own anywhere on this card.
 * 3. **The numbers are one click away, not hidden.** "Show the numbers" restores the analyst
 *    view in place. Simplifying is a default, never a wall.
 * 4. **It says when to look again.** A verdict built from decaying evidence has a shelf life,
 *    and a reader who is not told that will assume it is permanent — which is the exact
 *    criticism this product levels at a published rating.
 */
export default function InvestorCard() {
  const { board, settings, setSettings, openEvidence, openDeepDive } = useStore()
  const [trail, setTrail] = useState<TrailRow[] | null>(null)
  const [watch, setWatch] = useState<{ loadBearing: number | null; flipSet: number | null }>(
    { loadBearing: null, flipSet: null })
  /** Mean source quality for this company — what turns "fair" into "fair, and here is why". */
  const [quality, setQuality] = useState(0)

  const focused = board?.focused
  const ticker = (focused?.constituent as { ticker?: string } | undefined)?.ticker || ''
  const rec = ticker ? board?.engine?.records?.[ticker] : undefined

  useEffect(() => {
    if (!ticker || !rec) { setTrail(null); return }
    let dead = false
    void Promise.all([
      api.evidence(ticker, settings.demo, settings.horizon).catch(() => null),
      api.sensitivity(ticker, settings.demo, settings.horizon).catch(() => null),
    ]).then(([ev, sens]) => {
      if (dead) return
      setTrail(ev?.trail ?? [])
      setQuality(ev?.mean_source_quality ?? 0)
      setWatch({ loadBearing: sens?.load_bearing_count ?? null, flipSet: sens?.smallest_flip_set ?? null })
    })
    return () => { dead = true }
  }, [ticker, rec, settings.demo, settings.horizon])

  if (!focused) {
    return (
      <div className="inv-card">
        <div className="inv-head">Pick a company to start</div>
        <p className="inv-lead">
          Search for a name in the bar above, or ask the assistant — “how is DBS doing?”. We will
          show you what its published ESG rating says, what the dated evidence says, and where the
          two part company.
        </p>
      </div>
    )
  }

  const name = focused.constituent.company
  const plain = rec ? LABEL_PLAIN[rec.label as LabelKey] : null
  const strength = rec ? strengthOf(rec.composite_confidence, rec.signal_count, quality) : null
  const fin = focused.case?.financial.verdict ?? ''
  const half = board?.engine?.half_life_days ?? 180

  // Three receipts: the newest dated sources, which is what "how do you know that" actually wants.
  const receipts = (trail ?? [])
    .filter(t => t.published_at)
    .sort((a, b) => (a.published_at < b.published_at ? 1 : -1))
    .slice(0, 3)

  return (
    <div className="inv-card" data-tour="verdict-plain">
      <div className="inv-top">
        <div>
          <div className="inv-co">{name}</div>
          <div className="inv-head">{plain ? plain.head : focused.classification.label}</div>
        </div>
      </div>

      <p className="inv-lead">{plain ? plain.gloss : focused.plain_summary.body}</p>

      {rec && (
        <div className="inv-rows">
          <div className="inv-row">
            <span className="inv-k">What its rating says</span>
            <span className="inv-v">
              This company sits <b>{bandOf(rec.lseg_percentile)}</b> of the {board?.counts.total}{' '}
              companies we track, on its published score.
            </span>
          </div>
          <div className="inv-row">
            <span className="inv-k">What the evidence says</span>
            <span className="inv-v">
              Counting only dated news and filings from {horizonPlain(half)}, it sits{' '}
              <b>{bandOf(rec.momentum_percentile)}</b> of the same list.
            </span>
          </div>
          {strength && (
            <div className="inv-row">
              <span className="inv-k">How solid is that</span>
              <span className="inv-v">{strength.line}.</span>
            </div>
          )}
          {fin && (
            <div className="inv-row">
              <span className="inv-k">And the business?</span>
              <span className="inv-v">
                {FINANCIAL_PLAIN[fin] ?? fin}{' '}
                <i className="inv-aside">We keep this separate from the ESG read and never average the two.</i>
              </span>
            </div>
          )}
          {watch.loadBearing !== null && (
            <div className="inv-row">
              <span className="inv-k">What would change it</span>
              <span className="inv-v">{watchLine(watch.loadBearing, watch.flipSet, rec.signal_count)}</span>
            </div>
          )}
          <div className="inv-row">
            <span className="inv-k">When to look again</span>
            {/* Was one 30-word sentence, the only block on the card above grade 12 and the
                last thing read. Same content, split at the natural break. */}
            <span className="inv-v">
              This reads {horizonPlain(half)} of evidence, so it moves as news arrives.
              A regulator’s action or an exchange filing shifts it fastest; a press release least.
            </span>
          </div>
        </div>
      )}

      {receipts.length > 0 && (
        <div className="inv-receipts" data-tour="receipts">
          <div className="inv-k">Where this comes from</div>
          {receipts.map(r => (
            <a key={r.signal_id} className="inv-receipt" href={r.source_url}
               target="_blank" rel="noreferrer">
              <span className="inv-date">{r.published_at}</span>
              <span className="inv-text">{r.raw_text.slice(0, 120)}</span>
              <span className="inv-src">{r.source_type.replace(/_/g, ' ')} ›</span>
            </a>
          ))}
          {rec && rec.signal_count > receipts.length && (
            <button className="btn btn-sm inv-all" onClick={() => openEvidence(ticker)}>
              See all {rec.signal_count} sources
            </button>
          )}
        </div>
      )}

      <div className="inv-actions">
        <button className="btn btn-primary" onClick={() => void openDeepDive(ticker, 'interrogate')}>
          Ask about this company
        </button>
        <button className="btn" data-tour="show-numbers"
          onClick={() => setSettings({ showNumbers: true })}
          title="Put the analyst view back on screen: the radar, the percentiles and the score record.">
          Show the numbers
        </button>
      </div>

      {/* The first sentence is load-bearing and stays word for word. The second half used to
          re-explain source weighting, which "How solid is that" already says above it with this
          company's own numbers — a general note repeating a specific one it cannot improve on. */}
      <div className="inv-foot">
        We never say buy, sell or hold, and nothing here is advice. This is a second opinion on a
        published rating, with the sources attached.
      </div>
    </div>
  )
}
