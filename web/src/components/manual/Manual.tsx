import { useStore } from '../../store'

/**
 * HOW IT WORKS — the whole application, explained line by line, inside the application.
 *
 * The tutorial teaches the things a first-time reader needs to click. This is the other
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
 * ONE DOCUMENT, ONE READER. It used to fork: every section had a plain body for the investor
 * rendering and a `detail` — the formula, the exact rule string, the file that owns it — for the
 * analyst. That fork went with the investor view (2026-09-01). The reader is a CGSI ESG investor
 * who came here to check the mechanism, so every section now shows its detail: two versions of
 * one explanation drift, and the softer one wins the drift because it is the one nobody
 * re-checks against the engine.
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
/** The mechanism behind a section: the formula, the exact rule string, the file that owns it. */
function Detail({ children }: { children: React.ReactNode }) {
  return <div className="man-detail">{children}</div>
}

export default function Manual() {
  const { board, settings } = useStore()
  const e = board?.engine
  const demo = settings.demo
  const half = e?.half_life_days ?? 180
  const total = board?.counts.total ?? 0

  return (
    <div className="manual">
      <header className="man-top">
        <h2 className="man-title">How this works</h2>
        <p className="man-lead">
          Every claim on the board comes from the same short pipeline, and this page walks it in
          order. The rules below are printed from the run that is loaded, not transcribed —
          change a threshold and this page changes with it. It is not a sales pitch: it is what
          the app does, including the parts it cannot do.
        </p>
        {/* The identifiers stay at the top. This page explains a run, and a reader who cannot
            tell WHICH run it explains has been handed a document that cannot go stale visibly —
            which is the failure this repo has been bitten by twice. */}
        {e && (
          <div className="man-run">
            run <b>{e.run_id}</b> · as of {e.as_of} · {half}-day evidence window · {total} companies
            {demo && <span className="cc-tag-illus">illustrative demo universe</span>}
          </div>
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
        <Detail>
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
        <Detail>
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
        <Detail>
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
        <Detail>
          <code>weight = materiality × confidence × 2^(−age / {half})</code>. The window is a
          setting, not a fact about the world — the short one (45 days) asks "what changed
          recently", the long one (180) asks "what does the record say".
        </Detail>
      </Section>

      <Section n={5} title="How the verdict is decided">
        <p>
          Each company lands in one of five buckets, from where its rating sits and which way its
          evidence points. These are this run's own definitions and counts:
        </p>
        <ul className="man-list">
          {e && Object.entries(e.label_counts ?? {}).map(([key, n]) => (
            <li key={key}>
              <b>{e.labels?.[key] ?? key}</b>
              {' — '}
              {e.label_rules?.[key] ?? ''}
              <span className="man-count">{n}</span>
            </li>
          ))}
        </ul>
        <Detail>
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
        <Detail>
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
        <Detail>
          <code>financials.py</code>, a context GATE computed after scoring. <code>selftest.py</code>{' '}
          pins that neither <code>engine</code> nor <code>signals</code> imports it, so the
          separation cannot rot.
        </Detail>
      </Section>

      <Section n={8} title="The second axis: what the market has already done">
        <p>
          Beside the evidence read we carry one financial number: the <b>12-1 price momentum
          factor</b> — twelve months of share-price return ending <em>one month ago</em>. The
          skipped month is deliberate, not a rounding convenience: the one-month reversal is a
          documented, opposite-signed effect, and a window that includes it measures two things
          at once.
        </p>
        <p>
          The two directions are read together and the combination is named. Both up is
          <b> aligned</b>. Price up while the dated evidence <em>deteriorates</em> is the{' '}
          <b>downside divergence</b> — the People/Planet side going backwards without the market
          marking it, which is the shape a slow-refreshing score cannot show you. Evidence up
          while the price falls is the mirror of it.
        </p>
        <p>
          <b>The price never enters the score.</b> It is context beside the ESG read, exactly as
          the profit check is — no part of it reaches momentum, the disagreement, or any quadrant
          label. And it carries no accuracy or hit-rate claim: no backtest here has produced one,
          so none is printed.
        </p>
        <p>
          A company with no quotable listing has no second direction at all, and says so rather
          than being drawn at zero. Nine of the basket sit there: seven Philippine names our
          audited symbol column does not cover, and the two delisted constituents.
        </p>
        <Detail>
          <code>price_momentum.py</code>, read from the dated snapshot{' '}
          <code>data/price_momentum.json</code> so the board needs no network and the same file
          always gives the same reading. <code>selftest.py</code> pins that neither{' '}
          <code>engine</code> nor <code>signals</code> can import it, that a short window returns
          nothing rather than a partial reading, and that zero signals is <code>unknown</code>{' '}
          rather than a divergence.
        </Detail>
      </Section>

      <Section n={9} title="Profit, People, Planet — the lens">
        <p>
          The strip at the top of the board is how you say what you are optimising for, and each
          answer changes what is on screen. <b>Profit first</b> lets the financial direction lead
          and runs ESG as a strict downside gate: a name whose dated evidence is deteriorating is
          dimmed however well the price has run. <b>Balanced</b> weighs the three equally and
          dims nothing. <b>Sustainability focus</b> puts the labelled green-bond hurdle first.
        </p>
        <p>
          It is a lens, not a second scoring model. No weight moves, nothing is re-scored, and a
          name that fails it <b>dims rather than disappearing</b> — a filter that deletes
          companies is making the decision for you.
        </p>
        <Detail>
          <code>lib/tierMatch.ts</code>. The green hurdle reads <code>green_bond_status</code>,
          the same field the Conservative tier and the N bucket use, so the three cannot mean
          different things by "green". <code>dimSplit</code> attributes every dimmed name to one
          cause, which is why the strip and the matrix caption always report the same number.
        </Detail>
      </Section>

      <Section n={10} title="The PPP triangle">
        <p>
          The same company, asked a different question: not <em>which way is it going</em> but{' '}
          <em>what is its story about</em>. Three shares of one whole — Planet, People, Profit —
          so moving toward one corner necessarily means moving away from the other two.
        </p>
        <p>
          <b>It is a magnitude, not a verdict.</b> The shares are built from how much each axis is
          MOVING, so a dot in the Planet corner can mean rapid environmental progress or rapid
          deterioration. The direction of each axis is printed beside the dot rather than encoded
          in its position, because a corner label is a much stronger suggestion than a number.
        </p>
        <p>
          Most of the basket leans Profit, and that is the evidence gap rather than a fact about
          ASEAN business: the E/S/G pulls are small because we hold little dated evidence for
          those companies. It is the same finding the hollow dots report on the matrix, arriving
          through a third door. A company missing an axis is <b>not placed at the centre</b> —
          the centre is a measurement, and it has none.
        </p>
        <Detail>
          <code>ppp.py</code>. Planet is the E pillar&rsquo;s contribution to momentum
          (|direction| &times; evidence weight); People is the same for S, G and Digital/AI, which
          is a governance question and is folded in rather than dropped; Profit is |12-1 price
          momentum| over a stated full scale — the same one the matrix draws its x axis with, so
          the two cannot disagree. The rule is printed on the panel: a normalising constant chosen
          in private is how a composition quietly becomes an opinion.
        </Detail>
      </Section>

      <Section n={11} title="The forward view — and what it honestly measured">
        <p>
          This is the only thing on the board that predicts, and it reports its own failure. A
          ridge regression was fitted on a real panel: the engine replayed at quarterly cutoffs
          (it is pure, so it can be), the PPP shares and evidence read <em>as they stood at each
          cutoff</em>, paired against the return each stock actually delivered over the following
          six months. Trained on the early cutoffs, graded on the later ones — split by time,
          never randomly.
        </p>
        <p>
          <b>It has no measured skill.</b> Across nine configurations — three horizons by three
          train splits — every out-of-sample R&sup2; came back negative and every directional hit
          rate came in below the majority class. It does not beat guessing the average. That is
          the finding: on roughly three years, one market regime and ~43 companies, this data does
          not support forecasting a price from these features.
        </p>
        <p>
          The estimate is still shown, because it was asked for and because a failed model that
          says so is worth more than a plausible one that does not — but <b>it never appears
          without its typical error and its verdict beside it</b>. A number whose reliability you
          cannot check is the exact thing this product exists to argue against.
        </p>
        <p>
          Beside it sits the part that <em>is</em> evidenced: CGSI&rsquo;s own published figures
          for how often an ESG improver in this basket beat the index — 28.9% at one year, 46.2%
          at three, 61.5% at five — attributed, with their own caveat that it does not transfer to
          a single stock. A measured historical frequency, not our guess, and not a forecast.
        </p>
        <Detail>
          <code>forecast.py</code>, frozen to <code>data/forecast_model.json</code> with its
          robustness sweep recorded so the split cannot be quietly re-rolled until it looks good.
          Feature scaling is fitted on the training rows only. Returns overlap, so consecutive
          rows are not independent and the effective sample is far smaller than the row count —
          stated on the panel. <code>selftest.py</code> pins that neither <code>engine</code> nor{' '}
          <code>signals</code> can import it, and that an estimate never travels without its skill.
        </Detail>
      </Section>

      {e?.nmk && (
        <Section n={12} title="The origination counts (N / M / K)">
          <p>Three counts that turn the board into a call list for whoever arranges the financing:</p>
          <ul className="man-list">
            {(['N', 'M', 'K'] as const).map(k => (
              <li key={k}>
                <b>{k} — {e.nmk.labels?.[k]}</b> — {e.nmk.rules?.[k]}
                <span className="man-count">{e.nmk[k]}</span>
              </li>
            ))}
          </ul>
          <Detail>
            <code>pipeline_counts.py</code>, definitions in <code>engine_config.json</code> so the
            board and the money slide can never disagree. "Below sector benchmark" in M is the
            company's ESG score against its own industry's ASEAN peer average — not the industry
            emissions intensity, which is a different measure and is never differenced against it.
          </Detail>
        </Section>
      )}

      <Section n={13} title="The receipts">
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
        <Detail>
          One Merkle root per run over signals, the green-bond rows and the hash of each benchmark
          file (<code>leaf-v2</code>), anchored on Sepolia by <code>anchor.py</code>. The chain is
          the LEDGER layer, not verification: it cannot check an off-chain fact, and immutability
          applied to a false claim just makes it permanent. With no chain reachable the run records{' '}
          <code>anchor_pending</code> and says so rather than claiming otherwise.
        </Detail>
      </Section>

      <Section n={14} title="What would change a verdict">
        <p>
          For any company we can remove each source in turn and re-score, then tell you which
          removals would actually change the answer. "No single source is holding this up" and
          "this rests on one filing" are very different verdicts that look identical on a
          dashboard.
        </p>
        <Detail>
          <code>sensitivity.py</code> — leave-one-out plus the signed distance to every boundary.
          Pure: no clock, no RNG, no network, so it replays with the run it describes. The cohort
          is held fixed and only this company re-ranked, because momentum is a rank.
        </Detail>
      </Section>

      <Section n={15} title="What we cannot do">
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
            not capability problems; the baseline percentile here is a MOCK stand-in and
            says so on every record.
          </li>
          <li>
            <b>We cannot forecast a price.</b> A model was fitted and it has no measured skill —
            see section 11. The estimate is on screen with that verdict attached; it is not a
            capability we have.
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

      <Section n={16} title="Everything on your screen">
        <ul className="man-list">
          <li><b>Preferences / Everything</b> — how much of the board is on at once; the chips at the foot add one panel at a time.</li>
          <li><b>PPP risk filter</b> — Profit first, Balanced or Sustainability focus, with a live count of what each one dims.</li>
          <li><b>The matrix</b> — price momentum across, our evidence up. One dot per company; the corners are the four combinations.</li>
          <li><b>The PPP triangle</b> — where a company&rsquo;s movement sits across Profit, People and Planet.</li>
          <li><b>Forward view</b> — a model estimate of 6-month return, always shown with the skill it actually measured, and CGSI&rsquo;s published base rate beside it.</li>
          <li><b>The assistant</b> — filters ("show banks"), focuses a name, keeps one ("monitor DBS"), or runs the full interrogation.</li>
          <li><b>Tutorial</b> — the six-card walkthrough of this screen, in the ⚙ menu.</li>
          <li><b>Recap this run</b> — walks the current run and hands you one copyable summary at the end.</li>
          <li><b>Present mode</b> — drives the pitch through the live app, one click per step, no captions.</li>
        </ul>
      </Section>
    </div>
  )
}
