import { useStore } from '../../store'
import { matches } from '../../lib/tierMatch'
import type { Focus, Holding } from '../../store'
import type { TierKey } from '../../types'

/**
 * SetupPreview — "your board so far".
 *
 * The objection this answers is the one the setup has always been vulnerable to: a questionnaire
 * that asks four things and then reveals its consequences only after you finish is asking you to
 * answer blind. Every number here is computed by the SAME `matches` the matrix draws with, over
 * the run already in memory — so it costs nothing, needs no request, and cannot promise a board
 * that does not then appear.
 *
 * It deliberately shows the count that FALLS as well as the ones that rise. A preview that only
 * ever gets better as you turn the dial is a slot machine, not a control.
 */
export default function SetupPreview({ tier, holding, focus, country, sector, horizonDays }: {
  tier: TierKey
  holding: Holding
  focus: Focus
  country: string
  sector: string
  horizonDays: string
}) {
  const { board } = useStore()
  const engine = board?.engine
  if (!board || !engine) return null

  const records = Object.values(engine.records || {})
  const cons = board.constituents || []
  const meta = new Map(cons.map(c => [c.ticker, c]))

  const kept = records.filter(r => {
    const c = meta.get(r.company_id)
    if (!c) return false
    if (country !== 'All' && c.country !== country) return false
    if (sector !== 'All' && c.sector !== sector) return false
    const status = engine.badges?.[r.company_id]?.green_bond?.status || ''
    return matches(r, tier, false, focus === 'green', status)
  })

  const hidden = kept.filter(r => r.label === 'hidden_winners').length
  const bondReady = kept.filter(
    r => engine.badges?.[r.company_id]?.pipeline?.bucket === 'M').length
  const review = kept.filter(
    r => engine.badges?.[r.company_id]?.pipeline?.bucket === 'K').length
  const withEvidence = kept.filter(r => r.signal_count > 0).length
  const total = records.length
  const max = Math.max(1, hidden, bondReady, review)

  const rows = [
    { label: 'Rated behind the evidence', n: hidden,
      note: 'the disagreement is positive and the evidence is strong enough to stand on' },
    { label: 'Bond-ready (M)', n: bondReady,
      note: 'not yet an issuer, but below its peer average and improving' },
    { label: 'Needs a human (K)', n: review,
      note: 'we disagree, but something still blocks the call' },
  ]

  return (
    <aside className="sp">
      <div className="sp-h">Your board so far</div>

      <div className="sp-big">
        <b>{kept.length}</b>
        <span>of {total} names stay in view</span>
      </div>

      <div className="sp-rows">
        {rows.map(r => (
          <div className="sp-row" key={r.label} title={r.note}>
            <span className="sp-row-n">{r.n}</span>
            <span className="sp-row-l">{r.label}</span>
            <span className="sp-bar"><i style={{ width: `${(r.n / max) * 100}%` }} /></span>
          </div>
        ))}
      </div>

      <dl className="sp-meta">
        <div><dt>Risk tier</dt><dd>{tier}</dd></div>
        <div><dt>Evidence memory</dt><dd>{horizonDays}</dd></div>
        <div><dt>Holding</dt><dd>{holding.replace(/_/g, ' ').replace('y', ' years')}</dd></div>
        {focus === 'green' && <div><dt>Focus</dt><dd>labelled green issuers</dd></div>}
      </dl>

      {/* The honest footnote. Coverage is the binding constraint on this whole product, and a
          setup screen that hid it would be setting the reader up to be surprised later. */}
      <p className="sp-foot">
        {withEvidence} of these carry dated evidence. The rest sit at zero momentum because we
        have found nothing yet — which is a gap in our search, not a finding about them.
      </p>
    </aside>
  )
}
