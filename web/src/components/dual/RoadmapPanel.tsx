import { useStore } from '../../store'
import type { RoadmapScenario } from '../../types'

/**
 * THE ROADMAP — what better SOURCES would do, run through the real engine.
 *
 * Every other forward-looking panel in every other pitch is a number somebody typed. This one is
 * the actual `run_engine` re-executed over the SAME evidence with exactly one thing changed —
 * where each fact came from — so the reader is looking at a computed counterfactual rather than
 * an aspiration. Nothing is invented: not an event, not a date, not a direction, not a company.
 *
 * IT MAKES NO CLAIM ABOUT RETURNS, AND THE COPY IS BUILT SO IT CANNOT DRIFT INTO ONE. The dial
 * is source provenance and the readouts are confidence and coverage — how sure we are and how
 * many companies we can be sure about. There is deliberately no row here for performance, loss
 * rate or hit rate, because changing where a fact came from tells you nothing about what a share
 * price will do, and a roadmap that quietly implied otherwise would be the exact overclaim this
 * product exists to argue against.
 *
 * THE DISCLOSURE IS RENDERED FROM THE DATA, NOT WRITTEN HERE. `header` comes off the payload
 * verbatim — the same discipline `data/claim_vs_evidence.json` uses — so a change to what the
 * scenario does can never leave a stale description of it on screen. And the badge is PER ROW,
 * not once at the top: today's row is measured and the rest are not, and a blanket disclaimer
 * would teach a reader to discount the one row that is real.
 *
 * WHY THE HIDDEN-WINNER COLUMN DOES NOT MOVE, and why that is left visible rather than dropped:
 * `hidden_winners` needs `signal_count >= 10` as well as confidence, so lifting source quality
 * alone does not manufacture more of them. Showing a column that stays flat is the honest way to
 * say "this fixes one of the two gates" — hiding it would let the slide imply it fixed both.
 */

const fmtPct = (v: number) => `${Math.round(v * 100)}%`

function Row({ s, base }: { s: RoadmapScenario; base: RoadmapScenario | undefined }) {
  const measured = s.reality === 'measured'
  const delta = base ? s.companies_confident - base.companies_confident : 0
  return (
    <div className={`rm-row ${measured ? 'is-now' : ''}`}>
      <div className="rm-head">
        <span className="rm-title">{s.title}</span>
        <span className={`rm-badge ${measured ? 'is-now' : ''}`}>
          {measured ? 'measured today' : 'counterfactual'}
        </span>
      </div>
      <p className="rm-unlock">{s.unlock}</p>
      <div className="rm-nums">
        <span className="rm-num">
          <b>{fmtPct(s.company_pr_share)}</b>
          <span className="rm-lbl">self-published</span>
        </span>
        <span className="rm-num">
          <b>{s.mean_company_confidence.toFixed(3)}</b>
          <span className="rm-lbl">mean confidence</span>
        </span>
        <span className="rm-num is-key">
          <b>{s.companies_confident}<span className="rm-of">/{s.companies}</span></b>
          <span className="rm-lbl">
            confident enough to act on{delta > 0 ? ` · +${delta}` : ''}
          </span>
        </span>
        <span className="rm-num">
          <b>{s.hidden_winners}</b>
          <span className="rm-lbl">hidden winners</span>
        </span>
      </div>
    </div>
  )
}

export default function RoadmapPanel() {
  const { board } = useStore()
  const r = board?.engine?.roadmap
  if (!r || !r.scenarios?.length) return null
  const base = r.scenarios.find(s => s.reality === 'measured')

  return (
    <div className="rz rm" data-tour="roadmap">
      <div className="fc-head">
        <span className="fc-title">Roadmap · what better sources are worth</span>
        <span className="cc-muted">{r.dial}</span>
      </div>

      {r.scenarios.map(s => <Row key={s.key} s={s} base={base} />)}

      {/* Verbatim from the payload — see the header note. */}
      <p className="rz-caveat">{r.header}</p>

      {/* The arithmetic, so a reader can check the mechanism rather than trust the panel. */}
      <div className="fc-skill">
        {Object.entries(r.source_quality)
          .filter(([k]) => !k.startsWith('_'))
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => (
            <span key={k} className={k === 'company_pr' ? 'is-on' : ''}>
              {k.replace(/_/g, ' ')} <b>{v}</b>
            </span>
          ))}
      </div>
    </div>
  )
}
