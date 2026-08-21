# CLAUDE.md — ASEAN ESG Momentum Radar

> **Read this fully before any work.** It is the single source of truth for every
> agent/session. Detailed per-stage briefs live in `docs/stageN.md` (load the one for
> your stage). If anything here is ambiguous, ASK before coding — do not guess.

---

## WHAT we're building

A hackathon ESG investing tool. One-sentence concept:

> **An AI that interrogates along ESG-native axes, then competes with the market's view
> — disagreeing with evidence, not picking.**

Three behaviours ("beats"):
- **Thinks** — asks adaptive questions instead of dumping a dashboard. *(Stage 1)*
- **Challenges** — pushes back on the user's framing when it's wrong. *(Stage 1)*
- **Competes** — takes a position against the stale rating AND the market, using a
  signal the rating can't see. **The differentiator.** *(Stage 2)*

It is NOT a stock picker / ranker. It disagrees with ratings; it never says buy/sell.

---

## ARCHITECTURE — foundation first, then a 3-stage relay (pipeline)

The three stages form a **pipeline**: Stage 1's output feeds Stage 2, whose output feeds
Stage 3. Build them as a **relay** — one agent per stage, in order — on top of a shared
core that is built and FROZEN first. Each stage hands the next a *verified contract
output* (the handoff baton).

```
esg-momentum-radar/
  CLAUDE.md                 # this file (auto-loaded every session)
  core.py                   # FROZEN — DeepSeek client (call_llm), live-fetch (http_get), JSON parser, config
  contracts.py              # FROZEN — the handoff data shapes (below)
  rag.py                    # live retrieval: DuckDuckGo search + AI summary + TF-IDF rank (RAG)
  datasource.py             # build a CompanyData LIVE (free-text OR constituent-anchored) / UPLOAD; + snapshot
  universe.py               # ASEAN base DB loader/filter/resolver (the watchlist menu)
  metrics.py                # pure aggregation: avg ESG / pillar momentum / hidden winners / classify
  benchmarks.py             # industry benchmarks: ASEAN peer average + OECD GHG intensity (never merged)
  quotes.py                 # live market quote strip (Yahoo, best-effort) — context only, never a signal
  lseg.py                   # LSEG's REAL published ESG score (public finder, keyless) — the incumbent view
  server.py                 # FastAPI API boundary + static React host: dashboard · chat · relay · evidence
  stage1.py                 # AGENT 1 owns — interrogation loop (+ visible CoT rationale)
  stage2.py                 # AGENT 2 owns — reason over data + RAG + history (emits CoT + sources)
  stage3.py                 # Contract C Markdown/text export helpers (React owns live rendering)
  engine.py                 # run_engine(company_list) — the reproducible score records (Gate 1)
  signals.py                # deterministic signal extraction from stored evidence (no LLM, no clock)
  sensitivity.py            # what would CHANGE a verdict — leave-one-out + boundary margins (pure)
  engine_config.py          # loads data/engine_config.json (A1 labels · A2 sub-weights · A5 tiers · horizons)
  company_metadata.py       # A3 loader over the FROZEN green-bond CSV header + the A4 badge payloads
  pipeline_counts.py        # A6/B2 — N issuers · M pipeline · K review list (screen + money slide)
  anchor.py                 # C2/C3 — Merkle root per run + Sepolia anchoring (best-effort)
  contracts/EvidenceAnchor.sol  # C1 — append-only run_id -> root, ~20 lines
  harness.py                # A8 — determinism · stability · golden · cases · timelines · merkle · sweep · calibration
  calibration.py            # A8 — BLIND rating sheet: 2 humans vs the model over 10 companies
  backtest_timeline.py      # A8 — per-case validation chart (flat grey baseline vs moving momentum)
  phase_b.py                # Playbook steps 7–8 — issuance backtest + the blind 17-pick run
  llm_cost.py               # cost per company off the golden set (no price is ever guessed)
  cost_inputs.py            # the three cost-model cells for Sean (signals/co/month · tokens/signal · cache)
  scripts/                   # developer-only data builders and the LLM probe
    build_cgsi_basket.py     # CGSI's verified 52 -> the universe + the frozen-shape metadata CSV
    refresh_eurostat_benchmark.py  # verifies/refreshes the industry bar from the free Eurostat API
    build_metadata_mock.py   # regenerates the PROVISIONAL metadata CSV (deterministic)
    build_oecd_benchmark.py  # pulls OECD SDMX (emissions x value added) -> the industry benchmark CSV
    demo_reset.py            # puts the running app into a deterministic RECORDING state
    demo_diversify.py        # re-derives ONLY demo momentum/live_signals/news
                            #   (preserves esg_score — the MOCK baseline must not move)
  data/oecd_industry_benchmark.csv  # REAL OECD GHG intensity per ISIC industry (built by the script below)
  data/asean_universe.json  # BASE DB — CGSI's REAL verified 52 (built by scripts/build_cgsi_basket.py)
  data/asean_universe_reconstructed.json  # the public-evidence 52 we built while waiting — kept, superseded
  data/company_metadata.csv # the VERIFIED green-bond/profitability rows, frozen 29-column shape
  data/oecd_sector_benchmark.csv  # the industry bar, joined on CGSI's `industry` (Eurostat EU-27 2023)
  data/claim_vs_evidence.json     # the ILLUSTRATIVE claim-vs-satellite panel (3 rows)
  data/demo_universe.json   # FICTIONAL fully-numeric demo set — makes the command center alive (labelled illustrative)
  data/hero_company.json    # SAMPLE only — offline-demo safety net + test fixture (PLACEHOLDER)
  data/watchlist.json       # runtime: pinned tickers (local, git-ignored — not source)
  data/calibration_sheet.json  # the blind 10-company rating sheet (humans fill it; no model output in it)
  data/phase_b/             # the two input SHAPES to ask CGSI for (templates only, never data)
  docs/backtest/            # the five per-case timeline SVGs + the series.json behind them
  fixtures/                 # handoff batons: seeded in Phase 0, then REPLACED by each
    narrowed_question.json  #   stage's real verified output as the relay proceeds.
    stage2_answer.json      #   Each file = next stage's input + a regression check.
  docs/stage1.md docs/stage2.md docs/stage3.md   # detailed per-stage briefs
```

**Dashboard front-end (added 2026-06-25).** The app is now a **command-center dashboard** over an
ASEAN base DB. The *universe* (`data/asean_universe.json`, loaded by `universe.py`) is "**52 ASEAN
companies with consistent ESG improvement 2019–2023**" — the ESG Momentum foundation basket;
**MSCI ASEAN is the BENCHMARK** it beat (55.1% vs 6.4%), NOT the source of names. Each constituent
carries evidence (`esg_basis`/`source_url`/`confidence`).

**The assistant comes first (added 2026-08-18).** A first-time visitor lands on an
assistant-led **setup** (`web/src/components/setup/Setup.tsx`), not the board: four short
questions — mandate, then the fork between *screen the universe* and *investigate one company*,
then country/industry or a company name. The answers set the filters, and DERIVE the risk tier
and decay horizon (both shown with their reason and left editable). Everything runs locally —
chips plus a local matcher, no LLM call — because a demo cannot be one flaky network hop away
from its opening screen. `settings.setupDone` persists, so a returning browser goes straight to
the board; **Reconfigure** in the header re-runs it.

**The stylesheet has a scale, and everything is on it** (`web/src/styles.css` `:root`).
Spacing is `--sp-1..8` (multiples of 4, with 6px and 10px kept for chips and dense rows) and six
component densities — `--pad-panel` / `--pad-card` / `--pad-row` / `--pad-pill` / `--pad-chip` /
`--pad-btn` — which cover 67 of the sheet's 75 padding declarations. Radius is fully tokenised
(`--r-radius`, `-sm`, `-xs`, `-2xs`; only `999px` and `50%` stay literal). Type runs
10.5 / 11.5 / 12.5 / 13 / 14 / 15 / 17 / 19 / 22 plus a handful of one-per-component display
sizes; letter-spacing runs four positive steps and three negative. Before this the sheet held
~40 distinct padding pairs, 20 untokenised radii, 13 type steps between 10 and 14px and 14
letter-spacing values — none of it decided, all of it accreted. **Do not invent a new value: pick
the nearest token.**

**The disagreement matrix has real axes.** x and y are drawn as a framed L with gridlines, tick
marks and labels on both (percentile 0–100%, momentum −1.0 to +1.0), named axes, and the two
QUADRANT BOUNDARIES called out separately from the grid — dashed and captioned *median rating* /
*no momentum*, because crossing one changes a company's label and no other gridline does that.
The plot measures its own box with a ResizeObserver on a callback ref and sets its viewBox to
that pixel width, so it draws 1:1 and fills the board. (A fixed viewBox with the default
`preserveAspectRatio` letterboxed the whole chart on a wide monitor; a mount effect could not
measure it, because `EngineBoard` returns null until the board loads and the element does not
exist yet.)

**The board is centred, not stacked.** At every numeric level the middle column opens with
`RadarHub` (`web/src/components/dashboard/RadarHub.tsx`): the focused company in a core card with
the four pillar readings as satellites at the corners around it. The plot is a real radar and it
carries the thesis rather than decorating — the emphasised dashed ring is ZERO momentum, which is
what a static rating implicitly assumes, and the filled shape is the live read; the gap between
them IS the disagreement. Each satellite repeats its pillar as a diverging bar off the same zero
line. At level 1 (`solo`) the hub grows into the closed rails and carries the live signals inside
the core, because that is the one view where the right rail cannot show them. There is no sweep
and no rotation: the brief was a calmer screen. A filter with no pillar readings falls back to the
old three-card strip rather than leaving a hole.

**The board is layered.** `settings.level` is 1 Brief · 2 Analysis · 3 Everything, and every
widget declares the level it earns: level 1 is the verdict, the pillar cards, one action and a
one-line assistant bar; level 2 adds the momentum chart, the rankings, the industry-benchmark
table and the universe grid; level 3 adds the disagreement matrix, provenance and the evidence
trail. `simplified` is DERIVED from `level` in `setSettings`, so the server-facing flag and the
UI control can never disagree. A step-up bar at the foot of levels 1 and 2 says what the next
level would add. The matrix used to be the first thing on the page — a wall of dots before you
knew what a dot meant — which was most of why the board read as overwhelming.

**The incumbent rating is now REAL** (`lseg.py`, added 2026-08-19, Jayden's ask). LSEG publish a
free, keyless **Company ESG scores finder** on lseg.com — the overall 0–5 score (higher is better),
the three pillar scores, the twelve theme scores under them, the fiscal year, and the rank inside
the TRBC industry, for ~12.5k issuers. **All 52 of our universe resolve.** The deep dive opens with
it (`web/src/components/lseg/LsegPanel.tsx`) drawn as LSEG's own wheel — 12 outer theme segments,
3 inner pillar arcs sized 5/3/4, depth by score — so "what the rating sees" is finally the rating
rather than a stand-in. `engine.py`'s `lseg_percentile` is STILL the MOCK baseline and still says
so; wiring the real score into the engine is a Gate-1 decision (the engine is pure — it would have
to read a dated snapshot file, never fetch), NOT something to do quietly. Three traps, all pinned
by `selftest.py`: the endpoint needs a **`Referer`** header or it 200s with `{}`; their dispatcher
**caches by path and ignores `?ricCode=`**, so the RIC goes in the URL path as an AEM selector or
every company gets served the first company's scores under the first company's name (LSEG's own
widget has this bug); and an uncovered issuer is `{}` → `None`, never zeros. **Terms of use**:
non-commercial reference/publication needs written approval, and commercial use, redistribution or
**systematic reproduction** needs a licence — so this is attributed, on-demand, one company at a
time, cached locally, and **`data/` never receives a scrape**.

**"But what about the future?"** (added 2026-08-19, review feedback). The fair objection to
everything above is that evidence keeps arriving — so a verdict on screen is a snapshot, which is
exactly what we criticise a rating for being. Two surfaces answer it, and neither predicts
anything, because the engine cannot and will not. **Forwards** (`sensitivity.py`, drawn by
`web/src/components/future/VerdictSensitivity.tsx`): re-score the company with each signal
removed in turn and report which removals change the quadrant label, plus the signed distance
from every boundary in `engine.label_for`, nearest first. Pure — no clock, no RNG, no network —
so it replays with the run it describes. The cohort is held fixed and only this company is
re-ranked, because `momentum_percentile` is a RANK: re-scoring in isolation gets the momentum
right and the quadrant wrong. Reading the count needs care and the copy does it for you — "10 of
11 signals are load-bearing" is not ten important findings, it is a company balanced on a
boundary, so the summary line reads the nearest margin to tell the two apart. Margins are drawn
NEUTRAL, never green/red: "below the median rating" is the defining property of a Hidden Winner,
and colouring it red would call the thesis a warning. **Backwards** (`/api/backtest` ->
`TrackRecord.tsx`): the five validation cases redrawn from the same `docs/backtest/series.json`
the SVGs come from, where every point is a real engine run at its own cutoff — what the Radar
would have said on that date — against an incumbent view that did not move. Adaro stays in,
flagged: a backtest you can only pass is not a backtest.

**The setup asks about YOU now** (added 2026-08-19, review feedback). The first version asked
four questions and DERIVED the risk tier and decay horizon from the mandate alone; the objection
was that a vague question earns a vague answer. So the inputs that actually move the board are
asked for — **risk appetite** (sets the A5 tier), **holding period** (sets the decay horizon) and
**green-finance focus** (reads `green_bond_status`, the same field the Conservative tier and the
N bucket use) — as ONE profile step rather than three, because they are one thought. The mandate
still pre-fills every answer with its reason attached, so the fast path is unchanged and nothing
is decided silently. **Every answer has to do something**: a question whose answer only changes a
summary line is decoration, and worse than not asking. Years of holding and days of evidence
memory are different quantities, so the translation between them is printed rather than implied.
`greenFocus` DIMS non-matching names rather than hiding them — the same A5 discipline.

**The evidence is reachable from level 1.** The trail, provenance and matrix are level-3
furniture and setup lands a first-time visitor on level 1, so the backing was real but invisible
— "fancy UI, no explanation of where the evidence is from" was literally true of what a new
visitor saw. `RadarHub` now carries one always-present row — *N dated sources behind this
verdict* — one click from every excerpt, source and date.

**THE REAL BASKET LANDED** (2026-08-21, `CGSI_52_verified.csv`). Until now the universe was our
own public-evidence *reconstruction* of "52 ASEAN ESG improvers" — its own note said it would not
reproduce CGSI's basket, and it did not: only **22 of CGSI's 52 names appear in it**. CGSI's real
list is now `data/asean_universe.json`, built by `scripts/build_cgsi_basket.py`; the
reconstruction is kept as `asean_universe_reconstructed.json` and still donates **aliases** so
"add BCA" and "show Maybank" survive CGSI's terser legal names. Four things to know:

- **"Same schema, zero code changes" was wrong.** CGSI's file has **23** columns against our
  **29**-column frozen contract (renamed `company_id`→`bbg_code`, dropped `traction_flag` /
  `sgx_recognised` / `bond_isin`, added `esg_score_2023` / `esg_cagr_5y` / `high_conviction_17`).
  The adapter absorbs it and writes `data/company_metadata.csv` in the frozen shape — which is
  exactly what freezing the header was *for*. `traction_flag` stays EMPTY because CGSI ran no
  traction screen, and inventing one would drive a tier the data cannot support.
- **The baseline is real now.** `_baseline_score` returns a third value, `baseline_origin`:
  `SUPPLIED` (a score WITH a stated basis — CGSI's 2023 number, read from a dated file, so the
  engine stays pure), `MOCK` (a score with no basis — the fictional demo set, which must keep
  saying so), or `DERIVED-EVIDENCE`. The old hard-coded `MOCK-LSEG` was true then and would be a
  lie now. **None of the three is LSEG's published score** — `lseg.py` still fetches that live,
  separately, on its own 0–5 scale.
- **CGSI's `lseg_rating` column is not LSEG.** Its values are BB / BBB / B — the **MSCI** notch
  scale; LSEG's runs A+ to D−. Verified against the live endpoint: SGX 62 vs LSEG 52, Siam Cement
  70 vs 78, PTT 73 vs 78 on a 0–100 basis. It is carried as `incumbent_notch`, displayed
  unattributed, and **never called LSEG's**.
- **`esg_cagr_5y` is display-only and deliberately unscored.** It is derived from the rating's own
  history, so scoring it as our momentum would make us agree with the incumbent by construction.

The numbers the deck was waiting on, frozen in `data/nmk_frozen.json`: **N = 13** issuers (12
`labelled_reviewed` + PTT `cbi_certified` — reproducing CGSI's own count independently), **M = 4**
bond-ready pipeline, **K = 1** review list. The blind 17-pick test agrees on **5 of 17 (29.4%)**,
and 8 of the 12 misses have **zero signals** — we have no evidence for them, which is a different
statement from disagreeing, and the report says which. **M was redefined** per the build notes to
"below sector benchmark + positive momentum + passes profitability/traction"; "below sector
benchmark" is measured as the company's ESG score against **its own industry's ASEAN peer
average**, because that is the only unit we hold per company — it is NOT the Eurostat GHG
intensity, which sizes the *industry's* bar and is carried alongside as context. Differencing a
company ESG score against an industry emissions intensity would be two different measures
subtracted, which is the thing this project exists to refuse.

**A threshold worth knowing about.** `hidden_winners` needs `signal_count >= 10` and
`confidence >= 0.5`, calibrated when the only rich universe was the demo set (10–15 signals a
name). The real basket, scored deterministically off a verification CSV, tops out at **5**, so
**no real company can currently be labelled a Hidden Winner** — RHB Bank sits at disagreement
+0.80 on 5 signals and lands in `consensus`. That is a calibration mismatch, not a data error,
and it has been left alone on purpose: lowering our own bar until the screen returns the answer
we want is the exact failure the Adaro case exists to warn about. Fix it with evidence (live
retrieval over the 30 names that have none), not with a smaller number.

**The two delisted names are a feature.** MAHB (25 Feb 2025) and INTUCH (3 Apr 2025) went private
while sitting in a basket meant to be current. They keep their row, wear a `delisted — basket
membership stale` badge, and are excluded from investable output by rule. A static list going
stale IS the argument.

**"Even the yardstick can't be quietly swapped"** — the Merkle tree is now `leaf-v2`: signals, the
green-bond verification rows (already there), **and the hash of each benchmark FILE**. Hashing the
file rather than the parsed rows is deliberate: a reference year or a fallback flag edited in
place changes the meaning of a published gap and would survive a row-level digest. A run over the
real 52 is 130 leaves — 76 signals, 52 rows, 2 benchmarks.

**The industry bar is reproducible from a judge's laptop** (`scripts/refresh_eurostat_benchmark.py`).
`data/oecd_sector_benchmark.csv` joins **directly** on CGSI's own `industry` label — no crosswalk
guessing — and every one of its **22 rows reproduces from the free, keyless Eurostat API**
(`env_ac_aeint_r2`, pin `airpol=GHG&na_item=B1G&unit=G_EUR_CP` or the response carries several
series and you pick the wrong one). Banks (K), EU-27, 2023 = **7.89 g CO₂e/€**. Despite the
filename CGSI gave it, this is **Eurostat, not the OECD** — every surface says "OECD-Europe
(EU-27) benchmark", cites the dataset, keeps the nine Germany-fallback rows flagged, and carries
the PCAF caveat for financials.

**Claim vs Evidence** (`data/claim_vs_evidence.json`, drawn by `ClaimVsEvidence.tsx`) answers "you
only read what companies say". Three rows: PTT's CBI-certified forestry bond against Global Forest
Watch, a plantation no-deforestation claim against GFW alerts, and a bank's financed emissions
against **nothing at all**. It is labelled ILLUSTRATIVE **per row, not once at the top** — because
the third row is a *genuine* determination ("no independent dataset exists; this needs PCAF
disclosure") and a blanket disclaimer would teach the reader to discount the best row in the set.
Every claim, every piece of evidence and every verdict carries `checked`; an unchecked verdict is
drawn hollow. No satellite query is run.

**"AI-assisted · human-reviewed"** is the maker-checker chip the panel asked for, driven off the
metadata report (`verified` / `review_chip` / `header`). The green-bond header reads *"Team-verified
per the ICMA-based process, 2 sources per company — not CGSI-confirmed"* — verified BY US is not an
endorsement CGSI gave, and the panel never received the 52-name results. A chip plus a named
reviewer is the whole control: **no review workflow before the freeze.**

**Industry benchmarks** (`benchmarks.py`) answer "compared to what?" with two numbers that are
deliberately never merged: the **ASEAN peer average** (same unit as the company, from our own
universe) and the **OECD industry footprint** (tonnes CO2e per US$m of gross value added, from
the OECD's public SDMX API). A gap is computed ONLY when both sides are the same measure — a
static score is not differenced against the evidence-leadership index, and an incumbent risk
score is not read at all unless the snapshot has established which way it runs. Uploads land in
the same panel, so a new file is benchmarked against its ASEAN peers and its OECD industry with
no extra plumbing. The GICS -> ISIC crosswalk is a STATED MAPPING, reported as such (`via`), and
an unmatched sector says so rather than falling into the nearest bucket.

Layout (3 columns): **Left** = Filters (Industry/Country) + the **average ESG of the filtered set**
(recomputes per industry — the user's key ask) + the Monitored list. **Center** = four pillar
cards (avg **E/S/G/Digital-AI** momentum) + a momentum chart + **Hidden winners vs peer avg** +
a **Classification** verdict. **Right** = the **AI assistant** (it *controls the filters* — "show
banks", "Singapore", "all ASEAN" — adds/focuses companies, applied at the TOP of the run before
widgets via `ss.pending_chat`) + **Live signals** + **Why the rating may be wrong**.

`metrics.py` holds all aggregation (pure, tested). Three data MODES (auto-detected by
`_uni_mode`): **numeric** — full per-constituent numbers (`esg_score`, `esg_as_of`,
`momentum:{environment,social,governance,digital_ai}`, `live_signals:{…}`) drive the mockup
exactly; **evidence** — the real 52 carry NO numbers but DO carry `esg_basis`, so
`metrics.parse_evidence` derives a GROUNDED ESG-leadership score (0–100) + credential rows from the
ratings the text actually cites (MSCI/DJSI/CDP/FTSE4Good/Sustainalytics/GRESB/national indices) —
Avg-ESG-leadership, ESG-leaders ranking & classification work; pillar momentum + live signals stay
"awaiting data" (that's the alt-data the radar still needs); **empty** — neither → "awaiting data".
Nothing is fabricated for real names. A **Demo data** toggle swaps in `data/demo_universe.json`
(FICTIONAL, fully numeric). Each demo name carries one coherent `trajectory` (improving / mixed /
deteriorating, ~60/25/15) so its momentum, live signals and headlines tell the SAME story —
without it the fixture was uniformly positive and the Value Traps / Overrated Leaders quadrants
could never be populated. Click a card → **deep dive** = the Stage 1→2→3 relay.
`country`/`exchange`/numeric/evidence fields ride as NON-contract fields, so `contracts.py` stays frozen.

**Build order (relay, in sequence):** Phase 0 — build & FREEZE `core.py`, `contracts.py`,
the `server.py` API boundary, and seed `fixtures/`. Then **Stage 1 → Stage 2 → Stage 3 in order**:
each agent owns ONE file, consumes the previous stage's verified output from `fixtures/`,
and saves its own verified output there as the baton for the next. Integrate through `server.py`.
The existing `stage1_interrogation.py` is refactored into `stage1.py` + `core.py` in
Phase 0. Note: a fresh agent session has no memory of the last — this file + the contracts
+ the on-disk fixtures ARE the memory that travels down the pipe.

---

## THE CONTRACTS (the glue — do not change without sign-off)

**Contract A — `NarrowedQuestion` (Stage 1 → Stage 2)**
```json
{
  "narrowed_question": "string — the sharp, specific restated question",
  "mandate": "risk | return | compliance",
  "sector": "string",
  "horizon": "near_term | structural",
  "trail": [{"axis": "string", "type": "string", "text": "string"}]
}
```

**Contract B — `CompanyData` (→ Stage 2).** Built one of three ways (all → `coerce_company_data`,
which fills any gap with `"unknown"` and stamps `_origin`):
- **live** — `datasource.build_live_company(text)`: identify the company + fetch real docs,
  then the LLM extracts a Contract B **grounded ONLY in those sources** (unknown otherwise).
- **upload** — `datasource.load_upload`: `.json` used as-is; `.csv`/`.txt` AI-extracted from
  the file only.
- **sample** — `data/hero_company.json` (offline/demo + tests).
```json
{
  "company": "DemoBank SG", "ticker": "SGX:DEMO", "sector": "Financials — Banks",
  "layer_a": { "esg_score_static": "22.4 (Medium Risk)", "as_of_date": "2023-09-30",
               "note": "Risk score: LOWER = better. Stale baseline." },
  "layer_a_history": { "note": "...placeholder...", "trend_note": "...",
    "series": [{"as_of":"2022-09-30","esg_score_static":"24.1 (Medium Risk)"}, ...] },
  "layer_b": {
    "momentum": { "E": {"direction":"improving","magnitude":"+8%"},
                  "S": {"direction":"flat","magnitude":"0%"},
                  "G": {"direction":"improving","magnitude":"+15%"} },
    "digital_ai_signal": { "ai_governance_hiring_velocity": "+340% YoY",
                           "ai_disclosure_level": "none",
                           "gap_note": "Hiring for AI governance, disclosing nothing." },
    "conflicting_signals": { "news_sentiment": "positive", "behaviour_trend": "negative",
                             "conflict_note": "Press upbeat; behaviour says otherwise." },
    "near_term_catalyst": "MAS AI Risk Management Guidelines — finalising 2026, 12-month transition."
  }
}
```

**Contract C — `Stage2Answer` (Stage 2 → Stage 3)**
```json
{
  "question_to_ask": "string (restate the narrowed question)",
  "what_rating_sees": "string (from Layer A + its history — the stale view)",
  "what_we_see": "string (from Layer B — the signal + the gap)",
  "check_before_monday": "string (one concrete action, framed by mandate)",
  "competes_summary": "string (one tight sentence that explicitly disagrees with the rating)",
  "reasoning": ["string", "..."],                    // ADDITIVE — visible chain-of-thought
  "sources":   [{"title": "string", "url": "string"}] // ADDITIVE — RAG citations (real URLs)
}
```
> Additions (sign-off 2026-06-23) are **additive**: the five text fields are unchanged, so
> older batons still validate. `reasoning` is the CoT (set by the model); `sources` is the
> live-retrieval provenance (set from the real fetched snippets — never invented by the model).
> Contract A's `trail` items also gained an optional `rationale` (Stage 1's per-question CoT).

---

## THE STAGES (concise — full spec in docs/stageN.md)

**Stage 1 — Interrogate.** Vague question in → up to 5 ADAPTIVE questions, each mapped to
ONE ESG axis (materiality / time-horizon / mandate / blind-spot) → output a
`NarrowedQuestion`. CHALLENGE bad framing. NEVER answer the ESG question. Uses LLM
reasoning only — NO data. Each turn also carries a short `rationale` (visible CoT: *why
this axis now*).

**Stage 2 — Reason over data + retrieve (RAG).** Take a `NarrowedQuestion` + `CompanyData`
(incl. `layer_a_history`) + **live RETRIEVED_CONTEXT** (`rag.gather_context` — real DuckDuckGo
search snippets ranked by TF-IDF, plus a DuckDuckGo Instant-Answer **AI summary** the agent
INTERPRETS). Answer by COMPETING: disagree with Layer A
using Layer B evidence **and the historical trend**, grounded by the retrieved context.
Cite Layer B figures verbatim, surface the conflict, frame the closing line by the
`mandate`, **keep the five text fields tight**, and emit a `reasoning` chain-of-thought.
`sources` is attached from the real retrieval (never invented). NEVER invent company data;
a missing fact is "unknown". Retrieval is best-effort — offline just means no snippets.

**Stage 3 — Render.** Take a `Stage2Answer` and present it as a clear decision tool: the
verdict first, a collapsible **chain-of-thought**, the four lines, the "market view vs
reality" panel, the Layer B evidence, a **historical-vs-current** static-score strip, and
the **live sources**. Sophistication in how it thinks, simplicity in what it says
(CGSI criterion 02 — "simple, clear output").

---

## TECH STACK & COMMANDS

- Python 3.8+, OpenAI SDK (DeepSeek is OpenAI-compatible), `requests` (live fetch), FastAPI,
  and a React/Vite frontend.
- LLM: **DeepSeek**, model `deepseek-v4-flash`, `base_url="https://api.deepseek.com"`,
  key from env `DEEPSEEK_API_KEY`. All LLM access goes through `core.call_llm()`.
- RAG: keyless live fetch from DuckDuckGo (HTML/Lite search results + the Instant-Answer "AI"
  summary) via `core.http_get()`, ranked by a pure-Python TF-IDF retriever in `rag.py`. The
  agent INTERPRETS the AI summary; snippets carry real source URLs. Tunables (all optional):
  `ESG_HTTP_TIMEOUT` (10s), `ESG_RAG_TOP_K` (5), `ESG_RAG_MAX_DOCS` (12), `ESG_RAG_TTL` (6h),
  `ESG_LLM_TIMEOUT` (30s), `ESG_USER_AGENT`. Results cache to `.cache/` (git-ignored).
```bash
pip install -r requirements.txt          # API, LLM, retrieval, and test dependencies
export DEEPSEEK_API_KEY="sk-..."          # Windows: $env:DEEPSEEK_API_KEY="sk-..."
python server.py                          # NEW PRIMARY UI: React (web/) + FastAPI -> http://localhost:8000
cd web && npm install && npm run build    # one-time frontend build (dev: npm run dev, port 5173)
python selftest.py                        # offline check — no key, no network
python harness.py                         # ENGINE check (A8): Gate 1 determinism + stability +
                                          #   golden set + the 5 backtest cases + their timelines +
                                          #   merkle + sensitivity sweep + calibration
python harness.py --update-golden         # re-freeze the golden set (review the diff!)
python backtest_timeline.py               # redraw docs/backtest/*.svg (harness checks they are current)
python calibration.py --sheet             # (re)write the blind sheet (cases + real names, >=2 excerpts)
python calibration.py --rate rater_a --name "..."   # rate it, one keypress per company; resumable
python calibration.py                     # score it once BOTH rater columns are filled
python cost_inputs.py                     # the three numbers Sean's cost model is missing
python phase_b.py --template              # the two Phase-B input shapes; --blind / --issuance to run
python anchor.py                          # build + anchor EVERY (universe x horizon) run; --list, --verify
python pipeline_counts.py --freeze        # B2 — N/M/K frozen with a run id + date
python llm_cost.py --price-in X --price-out Y   # cost per company (prices must be supplied)
python -m scripts.build_cgsi_basket       # rebuild the basket from CGSI_52_verified.csv (--check)
python -m scripts.refresh_eurostat_benchmark  # verify the industry bar live (--write to refresh)
python pipeline_counts.py --real --freeze     # N/M/K on the real basket -> data/nmk_frozen.json
python phase_b.py --blind data/phase_b/cgsi_picks_17.json --real   # the blind 17-pick test
python -m scripts.build_metadata_mock    # regenerate the PROVISIONAL metadata CSV
python -m scripts.build_oecd_benchmark   # refresh data/oecd_industry_benchmark.csv from OECD SDMX
python benchmarks.py                     # the per-industry table: ASEAN average vs OECD intensity
python quotes.py                         # live quotes for one name per ASEAN exchange
python lseg.py "DBS Group Holdings" SGX  # one company's real LSEG ESG score; no args = all 52
python sensitivity.py IDX:ASMB           # what would change this verdict (--real, --horizon, --json)
python -m scripts.demo_diversify         # re-derive demo momentum/signals/news (esg_score untouched)
python -m scripts.demo_reset             # deterministic recording state: pins the 3 heroes,
                                          #   pre-computes both Compete answers, prints the
                                          #   localStorage blob for the UI half (--no-warm skips
                                          #   the billable calls)
```

**The engine (Prototype Build Spec v2, `D/`).** `run_engine` is a PURE function — no clock, no
RNG, no network, no LLM — so the same files always produce the same `run_id` and the same
records; that is Gate 1 and everything else leans on it. Signals are extracted by rules from the
evidence we already store, each one dated, sourced, directional and carrying a one-line
`rationale` that the evidence trail shows. Company-PR sources are capped at 0.5 confidence and
forward-looking language has its materiality halved (the Adaro lesson). `lseg_percentile` is a
**MOCK** baseline (the stored static rating, percentile-ranked in the cohort) and every record
says so. Momentum is `direction_consensus x shrinkage`: the consensus says which way the evidence
points, the shrinkage term `w/(w+k)` says how much evidence is behind it — so one thin signal can
never score like twelve corroborating ones, and no company reaches a perfect ±1.000. Quadrant labels are CGSI's, including the new `overrated_leaders`; `disagreement` is
SIGNED (our percentile minus the rating's) so a deteriorating high-rated name can never be
labelled a Hidden Winner. Green-bond/profitability metadata joins from a CSV whose **header is a
frozen contract** — the Phase B1 swap is a file, not a code change — and every shipped row is
`is_provisional=TRUE` until verified. Each run's evidence hashes into one Merkle root anchored on
Sepolia; with no RPC configured the run is recorded `anchor_pending` and says so on screen,
never silently unanchored.

---

## HARD RULES (never violate)

1. **Live fetch is allowed, isolated, and best-effort** *(updated 2026-06-23, production)*.
   Outbound HTTP ONLY through `core.http_get()` (the company *dataset* stays a local JSON;
   the web only adds grounding context). Retrieval is best-effort: a blocked/slow network
   MUST degrade to "no external context" — never a hard crash, never a blocked demo. No DB.
2. **Never fabricate.** The model reasons ONLY over provided inputs (data + retrieved
   snippets). Missing company fact → say "unknown", never invent a number/date/rating. This
   also governs the LIVE data builder (`datasource.py`): it extracts a Contract B **grounded
   only in fetched sources / the uploaded file** — anything unsupported is "unknown", never
   estimated. `sources` are the REAL URLs, attached by the radar — the model never makes them up.
3. **Label data by origin.** `data/hero_company.json` is a SAMPLE placeholder — never present
   it as real (in code, comments, or output). LIVE/UPLOAD data is real and labelled by its
   `_origin` ("live"/"upload") — never call it "placeholder". Output is never investment advice.
4. **Never give buy/sell/hold or a score.** We disagree with ratings; we don't pick.
5. **Never hard-code secrets.** API key from env only (`DEEPSEEK_API_KEY`).
6. **I/O isolation.** LLM calls only via `core.call_llm()`; web fetch only via
   `core.http_get()`. (DeepSeek wraps JSON in prose sometimes — always parse defensively via
   `core.parse_json()`.) RAG logic (fetch + rank) lives only in `rag.py`.
7. **File ownership.** Each agent edits ONLY its own `stageN.py` (+ `rag.py` / `datasource.py`
   for retrieval & data-building). Do NOT edit `core.py` or `contracts.py` (frozen) without
   sign-off. Do NOT build the next stage's job.

---

## HOW EACH AGENT WORKS (relay)

1. Read this file + your `docs/stageN.md`.
2. Take the previous stage's verified output in `fixtures/` as your concrete input. Build
   ONLY your `stageN.py`, against the contracts.
3. Propose your file plan and wait for OK before writing (use Plan Mode).
4. Verify your stage produces its contract EXACTLY; save a real example of your output to
   `fixtures/` as the baton for the next stage; wire into `server.py`.
5. Acceptance = your stage consumes/produces its contract exactly, and the end-to-end
   demo chain runs: vague question → narrowed question → four-line competing answer that
   cites the Layer B gap + the MAS catalyst, with zero invented facts.
