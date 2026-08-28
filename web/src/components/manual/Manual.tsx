import { useStore } from '../../store'
import { LABEL_PLAIN } from '../../lib/plain'
import type { LabelKey } from '../../types'

/**
 * HOW IT WORKS — the whole application, explained line by line, inside the application.
 *
 * The tutorial teaches the four things a first-time reader needs to click. This is the other
 * document: the one you read when you want to know what the thing actually does before you
 * trust a word of it. It walks the app in the order the work happens — where the companies come
 * from, how a news item becomes a signal, how a signal becomes a verdict, how sure we are, what
 * the money check does, what the receipts prove, and what we cannot do at all.
 *
 * IT READS ITSELF OUT OF THE LOADED RUN. The label rules, the tier rules, the N/M/K definitions,
 * theta, the half-life, the metadata header, the harvest counts and the anchor status are all
 * printed from `board.engine` — the same block the panels draw from. Nothing here is a
 * transcription, because a hand-written manual is a promise about behaviour that stops being
 * true the first time a threshold moves and nobody remembers this file exists. Where a sentence
 * IS hand-written, it describes a rule that lives in code and is named so you can go read it.
 *
 * IT DEEPENS RATHER THAN FORKING. One document, not two: an investor reads the plain body of
 * every section, an analyst additionally sees the `detail` — the formula, the exact rule string,
 * the file that owns it. Two manuals would drift, and the plain one would quietly become the
 * marketing version.
 */

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="man-sec">
      <div className="man-n">{String(n).padStart(2, '0')}</div>
      <div className="man-body">
        <h3 className="man-h">{title}</h3>
        {children}
      </div>
    </section>
  )
}

/** Analyst-only depth: the rule as the code states it, and the file that owns it. */
function Detail({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null
  return <div className="man-detail">{children}</div>
}

export default function Manual() {
  const { board, settings } = useStore()
  const e = board?.engine
  const pro = settings.audience === 'analyst'
  const demo = settings.demo
  const half = e?.half_life_days ?? 180
  const total = board?.counts.total ?? 0

  return (
    <div className="manual">
      <header className="man-top">
        <h2 className="man-title">How this works</h2>
        <p className="man-lead">
          Every claim on the board comes from the same short pipeline, and this page walks it in
          order. {pro
            ? 'The rules below are printed from the run that is loaded, not transcribed — change a threshold and this page changes with it.'
            : 'Nothing here is a sales pitch: it is what the app does, including the parts it cannot do.'}
        </p>
        {/* An investor gets no run id, no day counts and no cohort size: this page exists to
            explain the thing, and a line of identifiers at the top of it is the first sentence
            that says "this is not for you". The analyst keeps every one of them. */}
        {e && pro && (
          <div className="man-run">
            run <b>{e.run_id}</b> · as of {e.as_of} · {half}-day evidence window · {total} companies
            {demo && <span className="cc-tag-illus">illustrative demo universe</span>}
          </div>
        )}
        {demo && !pro && (
          <div className="man-run"><span className="cc-tag-illus">illustrative demo universe</span></div>
        )}
      </header>

      <Section n={1} title="What this is — and what it refuses to do">
        <p>
          It is a second opinion on published ESG ratings. A rating is a <b>level</b>: where a
          company stood, in a file that closed months ago. We rank every company twice — once on
          that published rating, once on dated public evidence — and report where the two
          disagree, with the sources attached.
        </p>
        <p>
          It never says buy, sell or hold, it publishes no score of its own, and it is not
          investment advice. It disagrees with ratings; it does not pick.
        </p>
        <Detail show={pro}>
          HARD RULE 4 in <code>CLAUDE.md</code>. <code>disagreement</code> is a signed difference
          of two percentiles inside one run's cohort — deliberately not a composite, so it stays
          decomposable.
        </Detail>
      </Section>

      <Section n={2} title="Where the companies come from">
        <p>
          {demo
            ? 'You are on the demo universe: fictional companies with invented numbers, labelled illustrative on every panel. It exists so the mechanics can be shown without dressing invented figures up as real ones.'
            : 'The companies are a published research basket: index constituents that stayed in throughout and improved their ESG score over several years. We did not choose the names, and we do not add to them.'}
        </p>
        <Detail show={pro}>
          <code>data/asean_universe.json</code>, built by <code>scripts/build_cgsi_basket.py</code>{' '}
          from CGSI's verified sheet. Two delisted names keep their row and wear a badge: a static
          list going stale is the argument.
        </Detail>
      </Section>

      <Section n={3} title="How a news item becomes evidence">
        <p>
          We search for each company along four angles — emissions, governance, financing and
          controversy — and read what comes back. A fact only counts if it has a <b>date</b> and a{' '}
          <b>working source link</b>; anything else is dropped rather than guessed at. We decide
          what kind of source it is from the web address, never from what the publisher calls
          itself.
        </p>
        <p>
          A company's own announcement counts for <b>half</b> of what a regulator's filing counts
          for, and a promise about the future ("we aim to, by 2030") counts for half of what a
          thing that already happened counts for.
        </p>
        <Detail show={pro}>
          <code>harvest.py</code> gathers, <code>signals.py</code> routes by rule, and the model
          never sets a direction, a weight or a label. Source quality: regulator 1.0 · exchange
          filing 0.95 · index provider 0.9 · NGO 0.7 · news 0.65 · <b>company PR 0.5</b> · unknown
          0.4. Forward-looking language halves materiality. Five guards run on every harvested
          fact, including one that drops any date later than the basket's own cut-off — added
          after a model read target years as publication dates and silently flattened the whole
          universe's momentum.
        </Detail>
      </Section>

      <Section n={4} title="Old news counts for less">
        <p>
          Evidence fades. A source counts for full weight the day it lands and half as much by
          the end of the window — {half >= 120 ? 'about six months' : 'about six weeks'} — so a
          verdict reflects what is happening now rather than what happened once. That is also why
          a company with real evidence can read flat: everything it has is older than the window.
        </p>
        <Detail show={pro}>
          <code>weight = materiality × confidence × 2^(−age / {half})</code>. The window is a
          setting, not a fact about the world — the short one (45 days) asks "what changed
          recently", the long one (180) asks "what does the record say".
        </Detail>
      </Section>

      <Section n={5} title="How the verdict is decided">
        <p>
          Each company lands in one of five buckets, from where its rating sits and which way its
          evidence points. These are {pro ? "this run's own definitions and counts" : 'what each one means'}:
        </p>
        <ul className="man-list">
          {e && Object.entries(e.label_counts ?? {}).map(([key, n]) => (
            <li key={key}>
              <b>{pro ? (e.labels?.[key] ?? key) : (LABEL_PLAIN[key as LabelKey]?.head ?? key)}</b>
              {' — '}
              {pro ? (e.label_rules?.[key] ?? '') : (LABEL_PLAIN[key as LabelKey]?.gloss ?? '')}
              {pro && <span className="man-count">{n}</span>}
            </li>
          ))}
        </ul>
        <Detail show={pro}>
          Evaluated in order, and <code>hidden_winners</code> is checked first, so it wins where
          conditions overlap. θ = {e?.theta ?? 0.3}. Rules and thresholds live in{' '}
          <code>data/engine_config.json</code> — never inline in code.
        </Detail>
      </Section>

      <Section n={6} title="How sure we are, and why it is capped">
        <p>
          Confidence is three things at once: <b>how much</b> evidence there is, <b>how good</b>{' '}
          the sources are, and <b>how many independent lines</b> of it agree. Eight facts about one
          topic are weaker than four about four topics.
        </p>
        <p>
          Because most of what a public search returns is written by the companies themselves, and
          we cap that at half weight, confidence cannot climb past roughly half of coverage on
          self-reported material however much of it we gather. That is the cap working, not a bug —
          and it is why the strictest bucket holds a handful of names rather than forty.
        </p>
        <Detail show={pro}>
          <code>confidence = coverage × [mean_quality + (1 − mean_quality) × 0.35 ×
          corroboration]</code>, coverage saturating at 12 signals and corroboration at 6 distinct
          routes. The route to more names is better sources — regulator actions, exchange filings,
          index-provider decisions — never a lower bar.
        </Detail>
      </Section>

      <Section n={7} title="Does the business make money?">
        <p>
          Alongside the ESG read, we check two audited years of the company's own reported profit
          and report it beside the verdict: growing, steady, going backwards, or <b>unknown</b>.
          Unknown means we cannot read it from what we hold — it is never counted as a failure.
        </p>
        <p>
          The two are never averaged. A company can be rated behind its evidence and still be a
          business in decline; one combined number would hide exactly that.
        </p>
        <Detail show={pro}>
          <code>financials.py</code>, a context GATE computed after scoring. <code>selftest.py</code>{' '}
          pins that neither <code>engine</code> nor <code>signals</code> imports it, so the
          separation cannot rot.
        </Detail>
      </Section>

      {pro && e?.nmk && (
        <Section n={8} title="The origination counts (N / M / K)">
          <p>Three counts that turn the board into a call list for whoever arranges the financing:</p>
          <ul className="man-list">
            {(['N', 'M', 'K'] as const).map(k => (
              <li key={k}>
                <b>{k} — {e.nmk.labels?.[k]}</b> — {e.nmk.rules?.[k]}
                <span className="man-count">{e.nmk[k]}</span>
              </li>
            ))}
          </ul>
          <Detail show>
            <code>pipeline_counts.py</code>, definitions in <code>engine_config.json</code> so the
            board and the money slide can never disagree. "Below sector benchmark" in M is the
            company's ESG score against its own industry's ASEAN peer average — not the industry
            emissions intensity, which is a different measure and is never differenced against it.
          </Detail>
        </Section>
      )}

      <Section n={pro ? 9 : 8} title="The receipts">
        <p>
          Every verdict opens onto the signals behind it: each one dated, sourced, pointing up or
          down, with one line saying why it counted for what it did. The excerpt is the source's
          own words. The ones that argue against the verdict are in there too — they are never
          dropped or collapsed.
        </p>
        <p>
          We also publish a fingerprint of the whole evidence set for each run. Re-checking it
          proves the verdict you are reading was built on exactly the evidence we said it was.
          {e?.anchor && <> This run is <b>{e.anchor.status.replace(/_/g, ' ')}</b>{e.anchor.chain ? ` on ${e.anchor.chain}` : ''}.</>}
        </p>
        <Detail show={pro}>
          One Merkle root per run over signals, the green-bond rows and the hash of each benchmark
          file (<code>leaf-v2</code>), anchored on Sepolia by <code>anchor.py</code>. The chain is
          the LEDGER layer, not verification: it cannot check an off-chain fact, and immutability
          applied to a false claim just makes it permanent. With no chain reachable the run records{' '}
          <code>anchor_pending</code> and says so rather than claiming otherwise.
        </Detail>
      </Section>

      <Section n={pro ? 10 : 9} title="What would change a verdict">
        <p>
          For any company we can remove each source in turn and re-score, then tell you which
          removals would actually change the answer. "No single source is holding this up" and
          "this rests on one filing" are very different verdicts that look identical on a
          dashboard.
        </p>
        <Detail show={pro}>
          <code>sensitivity.py</code> — leave-one-out plus the signed distance to every boundary.
          Pure: no clock, no RNG, no network, so it replays with the run it describes. The cohort
          is held fixed and only this company re-ranked, because momentum is a rank.
        </Detail>
      </Section>

      <Section n={pro ? 11 : 10} title="What we cannot do">
        <ul className="man-list man-limits">
          <li>
            <b>We read documents, not sensors.</b> Filings, regulator actions, exchange notices and
            press — no satellites, no meters on a smokestack.
          </li>
          <li>
            <b>Most public sources are company-published</b>, and we cap how far that can count.
            More searching does not fix it; better sources do.
          </li>
          <li>
            <b>Some companies have no dated evidence at all.</b> They are drawn hollow and counted,
            never quietly filled in.
          </li>
          <li>
            <b>Licensed ratings cannot be shown.</b> MSCI, S&amp;P and Sustainalytics are contracts,
            not capability problems{pro && <>; the baseline percentile here is a MOCK stand-in and says so on every record</>}.
          </li>
          {e?.metadata?.header && <li><b>Metadata:</b> {e.metadata.header}</li>}
          {demo && (
            <li>
              <b>You are on demo data.</b> Fictional companies, invented numbers, labelled
              illustrative throughout. Switch it off in the menu to see the real basket.
            </li>
          )}
        </ul>
      </Section>

      <Section n={pro ? 12 : 11} title="Everything on your screen">
        <ul className="man-list">
          <li><b>Investor / Analyst</b> — the same run in plain sentences, or with every number and control.</li>
          <li><b>Preferences / Everything</b> — how much of the board is on at once; the chips at the foot add one panel at a time.</li>
          <li><b>The assistant</b> — filters ("show banks"), focuses a name, keeps one ("monitor DBS"), or runs the full interrogation.</li>
          <li><b>Tutorial</b> — the four-card walkthrough of this screen, in the ⚙ menu.</li>
          <li><b>Recap this run</b> — walks the current run and hands you one copyable summary at the end.</li>
          {pro && <li><b>Present mode</b> — drives the pitch through the live app, one click per step, no captions.</li>}
        </ul>
      </Section>
    </div>
  )
}
