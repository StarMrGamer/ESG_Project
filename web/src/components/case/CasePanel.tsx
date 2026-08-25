import { useStore } from '../../store'
import { SectionTitle } from '../ui'

/**
 * WHY this verdict — pros and cons, on both axes, for the focused company.
 *
 * The board could always show WHAT a company was labelled. It could not say why in a form a
 * reader could argue with, and a quadrant label without its reasoning is a conclusion handed
 * down rather than a case made.
 *
 * Two rules this panel keeps, and they are the reason it is worth having:
 *
 *  1. **The cons are never collapsed or hidden behind a toggle.** They render at the same weight
 *     as the pros, in the same column. A case that only lists reasons to agree is marketing, and
 *     the entire premise of this product is that inconvenient evidence has to surface — we do not
 *     get to make an exception for our own verdicts.
 *
 *  2. **ESG and financial sit side by side and are never merged.** No combined score, no blended
 *     rank. The financial column answers "can this company pay for itself while it improves?";
 *     it gates whether an ESG disagreement is worth a reader's time and never moves the ESG
 *     verdict itself. Merging them would produce one number nobody could decompose — including
 *     us — and turn a disagreement with a rating into a pick.
 */
const VERDICT_CLASS: Record<string, string> = {
  strong: 'cc-pos', adequate: 'cc-flat', weak: 'cc-neg', unknown: 'cc-flat',
}

function Side({ title, pros, cons, note }: {
  title: string
  pros: string[]
  cons: string[]
  note?: string
}) {
  return (
    <div className="case-side">
      <div className="case-side-head">{title}</div>
      <ul className="case-list">
        {pros.map((p, i) => (
          <li className="case-item is-pro" key={`p${i}`}><span className="case-mark">+</span>{p}</li>
        ))}
        {cons.map((c, i) => (
          <li className="case-item is-con" key={`c${i}`}><span className="case-mark">−</span>{c}</li>
        ))}
        {pros.length === 0 && cons.length === 0 && (
          <li className="case-item"><span className="case-mark">·</span>Nothing on file for this axis.</li>
        )}
      </ul>
      {note && <div className="cc-muted case-note">{note}</div>}
    </div>
  )
}

export default function CasePanel() {
  const { board } = useStore()
  const kase = board?.focused?.case
  if (!kase) return null

  const fin = kase.financial
  return (
    <div className="panel-block case-panel">
      <SectionTitle sub="rule-derived from this run · no model wrote these lines">
        Why {kase.label_display} — the case, and the case against
      </SectionTitle>

      <div className="case-summary">{kase.summary}</div>

      <div className="case-grid">
        <Side title="ESG evidence" pros={kase.esg.pros} cons={kase.esg.cons} />
        <Side title="Financial read" pros={fin.pros} cons={fin.cons} note={fin.label} />
      </div>

      <div className="case-verdicts">
        <span className="cc-leftpill">
          Financial gate: <b className={VERDICT_CLASS[fin.verdict] || 'cc-flat'}>{fin.verdict}</b>
        </span>
        {fin.earnings.growth_pct != null && (
          <span className="cc-leftpill">
            Earnings {fin.earnings.direction} ({fin.earnings.growth_pct > 0 ? '+' : ''}
            {fin.earnings.growth_pct}%)
          </span>
        )}
        <span className="cc-leftpill">{fin.earnings.latest_text} vs {fin.earnings.prior_text}</span>
      </div>

      {/* The section a reader actually needs before doing anything with this. It says what would
          change the answer and what the answer rests on — never what to do about it. */}
      <div className="case-watch">
        <div className="case-side-head">What to look out for</div>
        <ul className="case-list">
          {kase.watch_outs.map((w, i) => (
            <li className="case-item is-watch" key={i}><span className="case-mark">!</span>{w}</li>
          ))}
        </ul>
      </div>

      <div className="cc-muted case-foot">
        This is a disagreement with a rating and a list of things to check — not investment
        advice, not a recommendation, and not a score. The ESG and financial reads are shown
        separately and are never combined into one number.
      </div>
    </div>
  )
}
