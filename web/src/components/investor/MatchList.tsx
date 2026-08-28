import { useStore } from '../../store'
import { strengthOf } from '../../lib/plain'
import type { TierKey } from '../../types'

/**
 * "Others that match what you asked for" — the rest of the answer.
 *
 * The board answers a question about ONE company, which is what the reader typed. But the
 * preferences they set — risk appetite, green-finance focus, country, industry — describe a
 * shape, and they picked one name out of that shape without ever seeing the others in it. That
 * is a screen pretending to be a lookup.
 *
 * So this is the same filter, applied to everything else, at the foot of the board.
 *
 * NO NUMBERS. Every row is a name, what we call it, and how solid the evidence behind that is —
 * in words. A ranked list of decimals is a league table, and a league table is a pick; the whole
 * argument of this product is that it does not make one. Rows are ordered by the size of the
 * disagreement because that is the most interesting first, but the number itself never appears.
 */
export default function MatchList() {
  const { board, settings, setFocus } = useStore()
  const e = board?.engine
  if (!e?.records) return null

  const focusedTicker = (board?.focused?.constituent as { ticker?: string } | undefined)?.ticker
  const names = new Map((board?.constituents ?? []).map(c => [c.ticker, c.company]))
  const tier = settings.tier

  const rows = Object.values(e.records)
    .filter(r => r.company_id !== focusedTicker)
    // The tier is the reader's own risk answer, already stamped on every record by the engine.
    .filter(r => tier === 'all' || r.tiers?.[tier as TierKey])
    // Green focus reads the green-bond metadata, the same field the Conservative tier uses —
    // it DIMS names elsewhere on the board, so here it simply does not list them.
    .filter(r => !settings.greenFocus
      || ['cbi_certified', 'labelled_reviewed'].includes(
        e.badges?.[r.company_id]?.green_bond?.status ?? ''))
    .filter(r => r.signal_count > 0)
    .sort((a, b) => b.disagreement - a.disagreement)
    .slice(0, 6)

  if (!rows.length) return null

  const shape = [
    settings.filters.country !== 'All' ? settings.filters.country : '',
    settings.greenFocus ? 'green-finance names' : '',
    tier !== 'all' ? `${tier} risk` : '',
  ].filter(Boolean).join(' · ')

  return (
    <div className="match">
      <div className="match-head">
        <span className="match-k">Others that match what you asked for</span>
        {shape && <span className="match-shape">{shape}</span>}
      </div>
      {/* Name and evidence strength, and nothing else. The verdict used to sit in the middle
          of every row and said the same words on all of them — the list is ordered by the size
          of the disagreement, so of course it did. A column that never varies is not a column,
          it is a heading repeated once per line. */}
      {rows.map(r => {
        const s = strengthOf(r.composite_confidence, r.signal_count, 0)
        return (
          <button key={r.company_id} className="match-row"
            onClick={() => setFocus(r.company_id)}>
            <span className="match-co">{names.get(r.company_id) ?? r.company_id}</span>
            <span className="match-strength">{s.word} evidence</span>
            <span className="match-go">›</span>
          </button>
        )
      })}
      <div className="match-foot">
        Ordered by how far our read sits from the published rating. Not a ranking of companies,
        and not a list of things to buy.
      </div>
    </div>
  )
}
