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
  harvest.py                # AI READS, rules score — live evidence for the thin names (overlay)
  traction.py               # §B.4 four-test screen for loss-makers (unknown != not_met)
  financials.py             # the financial GATE — earnings direction from the basket's own cells
  rationale.py              # WHY this verdict — pros/cons on BOTH axes, plus what would change it
  cost_model.py             # unit economics from MEASURED tokens; never guesses a price
  engine_config.py          # loads data/engine_config.json (A1 labels · A2 sub-weights · A5 tiers · horizons)
  company_metadata.py       # A3 loader over the FROZEN green-bond CSV header + the A4 badge payloads
  pipeline_counts.py        # A6/B2 — N issuers · M pipeline · K review list (screen + money slide)
  anchor.py                 # C2/C3 — Merkle root per run + Sepolia anchoring (best-effort)
  contracts/EvidenceAnchor.sol  # C1 — append-only run_id -> root, ~20 lines
  harness.py                # A8 — determinism · stability · golden · cases · timelines · merkle · sweep · calibration
  tools/                    # developer CLIs — nothing in the app imports these.
                            #   harness.py deliberately stays at the root: it IS the engine gate.
    calibration.py          #   A8 — BLIND rating sheet: 2 humans vs the model
    backtest_timeline.py    #   A8 — per-case validation chart
    phase_b.py              #   Playbook 7-8 — issuance backtest + blind 17-pick
    llm_cost.py             #   cost per company off the golden set
    cost_inputs.py          #   the three cost-model cells for Sean
  legacy/                   # PRE-REWRITE (July). Nothing in the app imports these; kept only
    esg_data.py             #   because selftest still covers them. Deleting is a DECISION.
    esg_scoring.py
  scripts/                   # developer-only data builders and the LLM probe
    build_cgsi_basket.py     # CGSI's verified 52 -> the universe + the frozen-shape metadata CSV
    refresh_eurostat_benchmark.py  # verifies/refreshes the industry bar from the free Eurostat API
    sg_day_rates.py          # blended day rates from LIVE MyCareersFuture postings
    build_cost_workbook.py   # writes the cost model as a real, calculating .xlsx
    build_pitch_pptx.py      # the 9-slide judge deck as an editable .pptx (+ speaker notes)
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
  data/cgsi_note_figures.json     # figures transcribed from CGSI's published note (perf, filters, provenance)
  data/cgsi_rics.json             # CGSI's own Reuters codes for the 52 -> exact LSEG lookup
  data/demo_universe.json   # FICTIONAL fully-numeric demo set — makes the command center alive (labelled illustrative)
  data/hero_company.json    # SAMPLE only — offline-demo safety net + test fixture (PLACEHOLDER)
  data/watchlist.json       # runtime: pinned tickers (local, git-ignored — not source)
  data/calibration_sheet.json  # the blind 10-company rating sheet (humans fill it; no model output in it)
  data/phase_b/             # the two input SHAPES to ask CGSI for (templates only, never data)
  docs/backtest/            # the five per-case timeline SVGs + the series.json behind them
  fixtures/                 # handoff batons: seeded in Phase 0, then REPLACED by each
    narrowed_question.json  #   stage's real verified output as the relay proceeds.
    stage2_answer.json      #   Each file = next stage's input + a regression check.
  docs/pitch/slides.md      # the 9-section pitch SCRIPT — what you say, and every figure's source
  docs/stage1.md docs/stage2.md docs/stage3.md   # detailed per-stage briefs
```

**Dashboard front-end (added 2026-06-25).** The app is now a **command-center dashboard** over an
ASEAN base DB. The *universe* (`data/asean_universe.json`, loaded by `universe.py`) is "**52 ASEAN
companies with consistent ESG improvement 2019–2023**" — the ESG Momentum foundation basket;
**MSCI ASEAN is the BENCHMARK** it beat (55.1% vs 6.4%), NOT the source of names. Each constituent
carries evidence (`esg_basis`/`source_url`/`confidence`).

**The assistant comes first (added 2026-08-18).** A first-time visitor lands on an
assistant-led **setup** (`web/src/components/setup/Setup.tsx`), not the board: four short
questions — mandate, then the fork between *screen ASEAN companies* and *screen a singular
company*, then country/industry or a company name. The answers set the filters, and DERIVE the risk tier
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

**The board is layered — TWO levels, not three** (collapsed 2026-08-28). `settings.level` is
**1 Preferences · 3 Everything**: Preferences is the verdict, the pillar cards, one action and a
one-line assistant bar — the board the setup answers asked for; Everything is every panel, the
disagreement matrix, provenance and the evidence trail included. `simplified` is DERIVED from
`level` in `setSettings`, so the server-facing flag and the UI control can never disagree.

**`2 · Analysis` was deleted** because the module picker made it redundant: it was
"Preferences plus five specific panels", which is exactly what pinning five chips does, only
fixed and unnegotiable. The `Level` type is now `1 | 3` so the compiler finds every leftover, and
`loadSettings` migrates a stored `2` **up** to 3 — a returning browser should find everything it
had still on screen, never less. The matrix used to be the first thing on the page — a wall of
dots before you knew what a dot meant — which was most of why the board read as overwhelming.

**The header's two rail buttons work at every level.** The rails are a level-3 module, so at
Preferences `‹ Filters` and `Assistant ›` used to set `leftOpen`/`rightOpen` and produce nothing:
the flag flipped, the gate above it stayed shut, and two controls in the menu were simply dead
with nothing on screen to say why. Opening a rail from the header now PINS the rails module — the
same thing the chip at the foot does — and closing the last open rail unpins it, so the header,
the chip and what is actually drawn can never disagree.

**The picker never reorders itself.** The chips render in registry order with an on/off state,
not pinned-first-then-off: the first build moved the chip you just clicked to the front of the
row, so the row reshuffled under your cursor and the next chip you reached for had moved. The +/×
sign sits in a fixed-width box for the same reason — a control that moves when you use it is one
you have to re-find every time.

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

**THE ANSWER TO "NO COMPANY CLEARS HIDDEN WINNERS"** (`harvest.py`, added 2026-08-22). The
verified basket is a green-bond verification sheet, not an evidence base: 28 of 52 companies
score ZERO signals off it and `hidden_winners` needs 10. The fix is not a lower threshold — that
is the Adaro failure precisely — it is more evidence, gathered where the model already belongs:
**it reads, the rules score.** Live search per company -> the LLM turns snippets into
`{text, published_at, source_url}` -> `signals.py` routes by rule -> `engine.py` scores
deterministically. The model never sets a direction, a confidence or a label.

**Four search angles, not one.** A single blended query returns one page and yields about one
usable fact; emissions / governance / financing / controversy return four disjoint result sets.
Measured on Siam Cement: blended kept 1 event, four angles kept 7, engine went 0 signals -> 4.
`controversy` is in the list deliberately, so a harvest cannot quietly become a press-release
collector.

**Five guards, because this is the one place fabrication could enter.** (1) A `source_url` not in
the retrieved snippets is dropped — the model cannot cite what it was not shown. (2) A date the
snippet does not state is dropped; nothing is back-filled to "today". (2b) **A date later than
the basket's own `as_of` is dropped** — see below. (3) `source_type` comes from the URL's domain,
decided by us, or a press release can label itself `regulator` and score at double weight.
(4) The verified basket is never overwritten: harvests land in `data/harvest/` and merge as an
OVERLAY, so CGSI's rows stay exactly as CGSI supplied them and any harvest can be thrown away.

**Guard 2b is there because of a real bug that hid completely.** The model read TARGET years as
publication dates — "aims for net zero by 2050" came back as `published_at: 2050-12-31`. Since
`engine._as_of_from` takes the newest date in the data as the decay reference, ONE such event
moved `as_of` 24 years forward, decayed every genuine signal in the basket to zero weight, and
took composite momentum for the **entire universe** to 0.000 — while every company still showed
its original `signal_count`. Nothing raised. The board would have rendered a universe with no
momentum as though that were the finding. `harvest.py --refilter` re-applies the guards to stored
harvests without re-fetching, because tightening a rule should not cost another sweep.

The overlay is applied for the REAL universe only (searching live news about a fictional demo
company is nonsense), it changes the `run_id` — correctly, since a run over more evidence is a
different run — and the board states the count rather than mixing the two silently.
`pipeline_counts` applies the same overlay so the money slide and the screen can never report a
different M, and the frozen record carries `evidence_basis` naming which run produced it.

**WHAT THE HARVEST ACTUALLY DID** (measured 2026-08-22, full sweep of every zero-signal name):

| | verified only | + harvested |
|---|---|---|
| signals | 76 | **180** |
| companies with NO evidence | 28 | **3** |
| max signals on one company | 5 | 7 |
| companies at the 10-signal bar | 0 | **0** |
| N / M / K | 13 / 4 / 1 | **13 / 10 / 3** |

(That row is the harvest measured on its own, 2026-08-22. The frozen file is the number to
quote; the table above is what the harvest alone changed.)

**THE FROZEN N/M/K IS `13 / 10 / 1`, NOT `13 / 11 / 3`** (corrected 2026-08-26). This paragraph
said 13 / 11 / 3 for two days and a submission document was written off it. That figure was real
— it was frozen on 2026-08-24 at run `8dbfa7438c2f893a`, after Cayden's traction cells landed —
but the **deep+quality sweep re-froze it the next day** at `13 / 10 / 1` on run
`1fc384a2fa92499d`, which is the run the whitepaper, the pitch slide and the Sepolia anchor all
quote. More evidence moved companies between buckets; the pre-sweep number was simply stale.

The lesson is not "someone mistyped". It is that **N/M/K was written out in prose here instead of
being read from `data/nmk_frozen.json`**, so re-freezing the run could not update it. Anything
quoting these counts should read the file — `pipeline_counts.counts(...)` or the frozen JSON —
and any figure copied into a document should carry the `run_id` it came from, because that is the
only thing that makes staleness visible.
| quadrants populated | 2 of 4 | **4 of 4** |

149 dated, sourced events across 26 companies. The evidence gap essentially closed, the
origination pipeline more than doubled, and `overrated_leaders` and `value_traps` appeared on
real data for the first time — the negative quadrants existing at all is what makes the matrix an
argument rather than a ranking.

**And still zero Hidden Winners — but the reason is NOT the signal count.** Twelve companies now
clear the disagreement bar; every one fails on CONFIDENCE, and lowering `min_signal_count` alone
changes nothing (at n>=4 with confidence>=0.5 the answer is still 0). The binding constraint is
that **92% of what live search returns is company-published**, which `source_quality` caps at 0.5
— the Adaro rule — so mean harvested quality is 0.52 and confidence cannot climb past roughly
half of coverage however much of it we gather.

That is the confidence model working exactly as designed: it refuses to be confident about
self-reported evidence, which is the entire reason the cap exists. So the route to an honest
Hidden Winner is **better sources, not more of them** — regulator actions, exchange filings,
index-provider decisions — which is the alt-data roadmap item, not a threshold to tune. Do not
lower the bar to populate the quadrant; the label would then mean "we found a lot of press
releases", which is precisely what Adaro looked like.

**DAY RATES FROM REAL POSTINGS** (`scripts/sg_day_rates.py`). The workbook marks four day-rate
cells "NEEDS SOURCE: MyCareersFuture or Michael Page". MyCareersFuture is Workforce Singapore's
job portal and its public API returns the salary range employers actually advertised, so the
rates derive from live postings rather than a remembered band:
`monthly median midpoint x 12 x (1 + 17% employer CPF) / 260 working days`. Measured 2026-08-22:
Data/ML **S$405**, Full-stack **S$398**, PM **S$435**, ESG analyst **S$290** — against the
skeleton's placeholder 500 / 450 / 450 / 400, so the estimates were high.

Three honesty notes ride with them. Singapore gazettes 11 public holidays, so dividing by 260
rather than ~249 makes every rate a **floor** by ~4%. These are **permanent-employment** costs
per working day, NOT contractor or agency rates, which carry a margin on top. And the ESG analyst
figure comes from a wide "ESG" search (143 matches) that sweeps in junior operations roles;
narrower terms return far higher rates on samples too small to trust (2 postings at ~S$628, 1 at
~S$594), so that one is flagged in the data and in the workbook as a floor to check against a
salary guide.

**THE WORKBOOK NOW CALCULATES** (`scripts/build_cost_workbook.py` ->
`data/ESG_Radar_Cost_Model_filled.xlsx`). Real formulas, so it can be sensitivity-tested, with
the original's colour convention actually applied: BLUE input (with a Source on its row), BLACK
formula, AMBER **empty** where a number is still needed — empty rather than placeholder, because
a plausible number in a cost model is worse than a blank one, and a blank gets asked about.
Verified by recalculating in LibreOffice and cross-checking against `cost_model.py`, which
computes the same figures by a separate implementation: **S$0.0793 per company per year**,
inference at 52 / 500 / 2000 companies of **S$4.12 / S$39.65 / S$158.60**. Pilot people subtotal
**S$34,965**; the pilot total is stamped INCOMPLETE while the licence and compliance rows are
blank, rather than presented as fully loaded. Hackathon actuals total **S$118.45**.
`openpyxl` is an OPTIONAL requirement — nothing in the app, engine or tests imports it.

**THE COST MODEL, BUILT** (`cost_model.py`, 2026-08-22). The business pack's
`ESG_Radar_Cost_and_Scale_Model.xlsx` is a SKELETON — labels, a colour convention and prose
descriptions of formulas ("day rate x weeks x days/week x FTE"), with zero formulas and zero
values across Pilot Cost, Unit Economics and Scale Scenarios. Its headline assumption is also
wrong for this architecture: it models **40 signals/company/month at 1500 tokens/signal**, which
describes a system where a model does the scoring.

Ours does not. **The scoring path costs ZERO tokens** — `signals.py` routes by rule, `engine.py`
scores deterministically, and no LLM is reachable from either. All LLM cost sits in GATHERING
(`harvest.py`) and is charged **per sweep of a company, not per signal**. So the variable-cost
line reads *tokens per company per sweep x sweeps per month*, and the two formulations give very
different answers.

Measured over the full 28-company sweep (`harvest.py --cost`): **4 calls and 6,059 tokens per
company per sweep** (5,604 prompt + 455 output), 28.8% of the prompt cacheable (the byte-identical
system prompt), yielding 5.3 dated facts. At DeepSeek's published off-peak card and weekly sweeps
that is **SGD 0.0793 per company per year** — about **S$4/year to cover the whole CGSI basket**,
S$159/year at 2,000 companies. Peak is exactly 2x, and a sweep is a batch job, so running
off-peak is a free halving.

Two disciplines the module keeps. **It will not guess a price**: `--price-hit`, `--price-miss`
and `--price-out` are all required, because a made-up per-token rate flatters a cost model more
effectively than any other single number. And **a cache hit is a cheaper RATE, not free** —
DeepSeek bill $0.007/1M against $0.22 on a miss, so the prompt is split into hit and miss slices
and priced separately; treating cached tokens as free, or applying a flat percentage to the whole
prompt, both overstate the saving. Pinned by `selftest.py`.

**It also refuses to draw the falling marginal-cost line the workbook asks for.** Inference is
linear in companies, so on this cost alone that line is FLAT. It only falls once the fixed data
licence is spread across clients — and no licence quote exists. Drawing it before that number
arrives is drawing the conclusion first, which is what the model exists to prevent. Day rates,
the two licence quotes, the price point and the milestone stay listed as MISSING with the
document that settles each.

**The traction screen runs now** (`traction.py`, playbook step 4 / Methodology §B.4). Four tests
— revenue growth >=10% compound over two FYs, operating cash flow positive or improving, a
disclosed order book, signed PPAs or committed green capex. **>=2 met = flag; 0 met =
disqualified.** The thresholds are OURS and the panel never confirmed them, so every surface says
*team-designed measure*.

The distinction that carries the module: **`unknown` is not `not_met`.** The basket holds net
income and nothing else, so tests 1 and 2 are unanswered for both loss-makers (PCHEM, PTTGC) and
both return `screen_not_run` — neither cleared nor disqualified. Scoring an unrun test as a
failure would disqualify a company for OUR missing data rather than its own numbers.
`--sheet --gather` builds the fill-in sheet with real candidate sources already retrieved per
test; `--apply` folds a filled sheet back into the metadata CSV and SKIPS any company whose
screen is still unrun. Net income trend is read and displayed but explicitly NOT counted as one
of the four — §B.4 asks about operating cash flow, and a narrowing loss is not that. (Parsing it
surfaced its own bug: `"FY2025 -THB14.6b"` yielded 2025, the year, so PTTGC's halving loss read
as widening.)

**THE SOURCE DOCUMENT** (`D/ESG 52 Comapnies Data.pdf`, read 2026-08-22). The CSV was not the
original — CGSI's published 43-page research note is, *"ASEAN Strategy — ESG momentum as an Alpha
selection tool"*, 29 Aug 2025. Figures transcribed into `data/cgsi_note_figures.json` and
`data/cgsi_rics.json`; the PDF itself stays in the git-ignored hand-off pack. What it settles:

- **The CSV is faithful.** All 52 rows of the note's Figure 5 parsed and compared field by field
  against `CGSI_52_verified.csv`: **zero mismatches** on ESG Rating, ESG Score, 5Y CAGR and
  Industry. The note even flags `MAHB.KL^B25` — Refinitiv's delisting marker — corroborating the
  delisted note independently.
- **The `lseg_rating` column is confirmed mislabelled.** CGSI's own header reads **"ESG Rating"**,
  unattributed. The SAME document prints LSEG's grades in its per-company briefs as an *"LSEG ESG
  Combined Score"* on the A+..D- scale (A, A-, B+, B, B-, C observed). Two different scales, and
  only the second is attributed to LSEG. Carrying it as `incumbent_notch` was right.
- **MSCI AC ASEAN is the SELECTION UNIVERSE, not only the benchmark.** The 52 are index
  constituents that stayed in throughout AND posted positive 2019-2023 ESG-score CAGR. Our
  earlier reconstruction treated the index as the benchmark alone and rebuilt names from public
  evidence — which is why only 22 of them overlapped.
- **Reuters codes for all 52** were in the note the whole time. `lseg.py` now looks companies up
  by exact RIC instead of matching names; **50 of 52 resolve, and the 2 that do not are the 2
  delisted names.**
- **The foundation backtest has a second half.** CGSI report the basket **lagging the index by
  -4.6% YTD as of 28 Aug 2025** on a ~45% banking weight, and that ESG improvement alone does not
  predict single-stock performance (probability an improver beats the index: 28.9% at 1y, 46.2%
  at 3y, 61.5% at 5y). The board now shows that beside the 55.1% vs 6.4%. A tool arguing that
  inconvenient evidence must surface cannot make an exception for its own foundation.
- **The blind-17 number was being read wrong.** CGSI's three filters are (i) above-average ESG
  CAGR, (ii) inclusion in their coverage universe, (iii) an **Add recommendation**. Only the
  first is an ESG signal; the other two are invisible to this engine, and HARD RULE 4 forbids it
  from ever forming the third. 29.4% is agreement on one criterion of three — **not** a 70%
  disagreement about ESG, and `phase_b.py` now prints the filters with the number.

**A wrong company is worse than no company** (fixed 2026-08-22, pinned by `selftest.py`). Clicking
the delisted Malaysia Airports rendered **I-Bhd's** ESG breakdown under Malaysia Airports' name.
Two holes lined up: `_norm("I-Bhd")` is the single letter `"i"`, which `resolve_ric`'s containment
tier matched as a raw substring of `"malaysia airports"`; and a RIC handed in from the basket was
fetched without checking it was a covered issuer. Containment now matches **whole words** and
requires 5+ characters, an explicit RIC is validated against the covered list first, and the
returned payload is cross-checked against the name LSEG files that RIC under. All three guards
matter — the failure looked completely normal on screen, which is what made it dangerous.

**The matrix has a shape now** (2026-08-22). `H` was a constant 340 against a MEASURED width, so
the plot area got flatter the wider the board went — about 7:1 on a 1920 monitor and 20:1 on a
2550 one, where every dot collapsed onto a single horizontal line and the four quadrants stopped
reading as quadrants at all. y is the axis carrying our half of the argument, so a chart that
cannot show vertical separation is not showing the disagreement. The plot now holds a fixed
~2.6:1 ratio, `MAX_W` (1180) caps how wide it gets, and past ~1500px the legend and the
hidden-winner shortcuts move up BESIDE it rather than leaving a band of empty panel either side.
The panel stays full-bleed, so the board still lines up with the header. Two traps if you touch
this: `margin-inline: auto` on a flex child cancels `stretch` and the SVG collapses to a few
hundred pixels (centring is the container's job), and `flex: 0 0 auto` in a row means
shrink-to-fit, which an SVG with no intrinsic width has nothing to fit to.

**"No evidence" and "evidence says flat" are different claims** and both land on exactly y=0. On
the verified basket that is 28 of 52 names overplotting into an unreadable smear, so a
zero-signal company is drawn HOLLOW and the count is stated beside the chart. An absence of
evidence is a finding, not a blank.

**Metadata follows its universe** (regression fixed 2026-08-22, pinned by `selftest.py`).
`company_metadata.active_file()` preferred the real CSV as soon as one existed, so the moment the
verified 52 landed the FICTIONAL demo universe started joining 52 real companies and matched
none of them: every demo badge silently went unverified and the demo board reported **N 0 · M 0**
— a join miss rendered as an origination finding, which is the exact failure this module exists
to prevent arriving through the other door. `load(demo=...)` now pins the pairing, and every
caller that knows which universe it is scoring passes it. Note `_metadata_hash` is an input to
`run_id`, so swapping the metadata file legitimately changes the run id and the golden digest.

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

**Then it teaches the board it just built** (`web/src/components/tour/Tutorial.tsx`, added
2026-08-28). Setup answers *what do you want*; the board then appears carrying a radar, a matrix
and four pillar tiles, none of which explain themselves. Six cards, once, straight after setup —
the dashed zero-momentum ring, the dated-sources row, the assistant, the levels, the module
picker, and what the product refuses to say. It persists as `settings.tourDone` and **Tutorial**
in the ⚙ menu replays it.

Two rules make it safe to run over a board whose shape it cannot predict: a card whose
`data-tour` anchor is not on screen is **skipped** rather than pointed at nothing (setup can land
you on any of the three levels), and it **never blocks the board** — the ring dims, it does not
trap, because a first-time visitor who would rather click than read is right. It is NOT present
mode: that is the pitch — it drives state, calls the model, and carries no words at all. They
share
`web/src/lib/anchor.tsx` — scroll-into-the-free-band, keep-aligning-while-the-page-settles, and
the ring — and nothing else. That file was extracted from `Present.tsx` rather than copied, so a
change to either bar's height cannot leave one of them measuring the wrong thing.

**A level is a default, not a cage** (`web/src/lib/modules.ts`, added 2026-08-28). Wanting the
verdict *and* the disagreement matrix used to cost you the whole of Analysis and Everything —
which is the same wall-of-panels problem the levels were introduced to fix, arrived at from the
other direction. So a module is on when `at(level) || extras.includes(key)`, `settings.extras`
persists the pins, and the bar at the foot of the board offers both routes: step up a level, or
add just this one thing. Both halves of the predicate live in one registry because the picker and
the panels have to agree about what is currently on screen. `at` is a predicate rather than a
minimum level because `rankings` is not monotonic — it appears at level 2 and is deliberately
gone at level 3, where the matrix panel already lists the same four names.

**The assistant can KEEP a company, not just look at one** (added 2026-08-28). `add DBS`,
`monitor DBS`, `track`, `watch`, `pin`, `follow` and `keep` now return a `monitor` action that
builds the snapshot and pins it to the watchlist; `focus` and `show me` still just focus. The two
had been the same code path, which quietly dropped half of the first request — focus is a view
the next click replaces, monitoring is a list that persists to `data/watchlist.json` and survives
a reload. The verb is **stripped before the name is resolved**, or `add GreenChip Bank` never
reaches a company at all: the resolver misses on the whole phrase, the sector matcher sees the
word *Bank*, and the user gets a filter to Banks — an answer to a question nobody asked. Pinned
by `selftest.py`.

**Present mode is a HIGHLIGHT, not a caption** (`web/src/components/present/`, changed
2026-08-28). It used to print each step's line under the board in 22px — which handed the room
something to read instead of the thing being demonstrated, and made a live-driven demo into a
slide deck wearing the app as a background. The cue is gone, and with it the machinery that read
its figures off the loaded run (there is nothing left to put them in). What remains is the ring,
the state change, and a slim control strip: chapter, position, keys, and the ticks. Each step
keeps a `note`, shown only as the tick's tooltip for the presenter, and it carries **no figures**
— a number typed into that file cannot follow the run it came from, and the panel being
highlighted is showing the real one anyway. The walk itself went from 24 steps to **12**: three
steps on one matrix and four on the tiers were the same picture said three different ways.

**And the same clicker now has a second track: RECAP** (`web/src/components/present/recap.ts`,
added 2026-08-28). Present mode argues the product to a stranger; the recap reviews **the run you
are on** — the quadrants, the pipeline counts, the focused company's verdict, what would change
it, the receipt — and ends on a card that CONSOLIDATES every figure it walked past, copyable as
Markdown or downloadable as a `.md` named for the run. A second walk cost a list of steps, not a
second clicker: `Track` is the only new concept, and `PITCH` and `RECAP` share the driver, the
anchors, the ring, the keys and interact mode.

Three things it keeps. **Every figure is read off the loaded run at the moment you ask** — the
card and the copied text both carry the `run_id`, because a consolidated block with no provenance
is precisely the stale-number trap this repo has been bitten by twice. **One ticker decides the
whole company section**: the first cut read the record by ticker and the NAME off `board.focused`,
which are different companies whenever the walk falls back to its default subject — it printed
*KLCC Towers* over *SatBank*'s disagreement, confidence and signal count, and looked completely
normal doing it. The walk now focuses its own subject, the card uses the focused payload only when
it IS that ticker, and the case is dropped rather than borrowed. And **the clipboard is not
trusted**: `navigator.clipboard.writeText` does not reject when the document has lost focus, it
hangs — so the write is raced against a 1.2s deadline and a miss reveals the Markdown in a
selectable block rather than doing nothing at the moment someone is waiting for it.

**AN INVESTOR VIEW, BECAUSE THE PRODUCT'S UNIT IS UNREADABLE OUTSIDE A DESK** (added
2026-08-28). `disagreement +0.80`, `composite_confidence 0.69`, `momentum percentile 97th` are
exactly right for the analyst this was built for and mean nothing to someone holding forty shares
of the bank in question. `settings.audience` is `investor` (the default) or `analyst`, and it is
NOT another level: `level` answers *how much of the board*, `audience` answers *in whose
vocabulary*.

What changes for an investor: the centre column becomes `InvestorCard` — the verdict as a
sentence, the two ranks in words ("its rating puts it in the bottom fifth; the evidence puts it
near the top"), evidence strength with the reason it is capped, the financial gate in a clause,
what would change the answer, when to look again, and three dated receipts with links. The desk
furniture (run id, half-life, anchor chip, risk tiers, the horizon switch, N/M/K) folds away, with
a line on screen saying where it went. The module chips speak plainly ("Where every company
sits"). A first-time visitor gets ONE question — which company — instead of six, and the tutorial
swaps to a four-card deck about the card in front of them. `web/src/lib/plain.ts` holds every
mapping, and it is a pure rendering of numbers the engine already computed.

**Three rules keep this from becoming a different product.** *Nothing is softened* — a weak
financial read still says the business is going backwards, `unknown` still says we cannot tell,
and "86% of this is company-published" still gets said, in plainer words. *No recommendation, in
any wording* — plain language is exactly how that line gets crossed by accident, so there is no
buy, sell, hold, cheap or undervalued anywhere in `plain.ts` or the card. *The numbers are one
click away, never gone* — "Show the numbers" restores the analyst rendering in place, and the
Analyst switch sits in the header. `settings.focus` also persists now: the reader who typed one
company should not reload onto somebody else's while the header still says "looking at" theirs.

**"How it works" is a tab, and it reads itself out of the run**
(`web/src/components/manual/Manual.tsx`, added 2026-08-28). The tutorial teaches the four things
you click; this is the document you read when you want to know what the thing does before you
trust a word of it — the pipeline in order, one numbered section at a time. Every label rule,
tier rule, N/M/K definition, θ, half-life, metadata header and anchor status is **printed from
`board.engine`**, the same block the panels draw from, because a hand-written manual is a promise
about behaviour that stops being true the first time a threshold moves. One document, not two:
an investor reads the plain body, an analyst additionally sees the `detail` — the formula, the
exact rule string, the file that owns it. Two manuals would drift and the plain one would quietly
become the marketing version.

**For an investor it carries no numbers at all** — no run id, no cohort size, no day counts, no
per-label counts. A page whose job is to explain the product cannot open with a line of
identifiers; that is the first sentence that says *this is not for you*. Same reason the
disagreement matrix's axis caption (`x = incumbent rating percentile (MOCK baseline) · y = …`) is
analyst-only: it is hidden by audience rather than deleted, because it carries the MOCK
disclosure the analyst view has to keep.

**Reconfigure means preferences, always.** The one-question start is for a first-time investor who
has no preferences yet; someone who went looking for *Reconfigure* is asking to choose them, and
handing them the same single question back is a dead end wearing a button's clothes. `setupFull`
(store state, deliberately not persisted — it describes what the user is doing right now) forces
the six-step flow for either audience.

**And the answer is no longer one company** (`MatchList.tsx`). The reader types one name, but the
preferences they set describe a SHAPE, and they picked a name out of it without ever seeing the
rest. The foot of the investor board lists the others that match — same tier flags the engine
already stamped on every record, same green-bond field, same filters — ordered by the size of the
disagreement and **stating none of it in numbers**: a name, what we call it, how solid the
evidence is, in words. A ranked list of decimals is a league table, and a league table is a pick.

**The matrix explains itself now** (`MATRIX_CARDS` in `Tutorial.tsx`, added 2026-08-28). The
disagreement plot is the densest thing in the product and carries its whole argument, and for
most of this app's life its only explanation was an axis caption written in percentiles. Twelve
cards, each ringing the thing it describes: the plot, the two axes, the two dashed boundaries
(the only lines that change what a company is called), **then the card the corners exist for** —
*Now read the two together*, which spells out all four combinations before naming any of them,
because "value trap" is jargon until you can read it straight off the two directions you were
just shown. Then the four corners one at a time, each titled by its position rather than its
label (*Left and high — rated low, but improving*), what a DIMMED dot means — it fails your risk filter and stays visible on purpose, because a filter that
deletes companies is making the decision for you — what a HOLLOW one means, and why the diagonal
is the argument. Launched from **What am I looking at?** on the plot itself or *Explain the
matrix* in the ⚙ menu, which also brings the plot up first: a walkthrough of something not on
screen has nothing to point at.

`settings.tourDeck` is how a walkthrough is asked for BY NAME, and it outranks `tourDone` —
someone clicking "What am I looking at?" is asking now, and having seen a different tour once is
no reason to refuse. The quadrant cards deliberately name no companies: that would turn an
explanation of the axes into a tip sheet, and the plot is right there.

**THE FIRST-RUN EXPERIENCE LIVES IN THE BROWSER, AND NO SERVER RESET CAN REACH IT.** `setupDone`
and `tourDone` are `localStorage`; `demo_reset` drives the API. So a browser that has already seen
the tour will never show it again however many times the server is reset — correct for a returning
user, useless five minutes before handing a laptop to a judge. Two answers, and the point of both
is that the choice is now MADE rather than inherited:

- **`?fresh=1`** clears the stored settings and strips itself from the URL, so the app opens as a
  stranger meets it. It runs before the provider mounts, because the store reads localStorage in a
  `useState` initialiser and clearing it afterwards would leave the old settings live.
- **`demo_reset --first-run`** prints that state as a blob; the default blob prints the RECORDING
  state, which now spells out every flag including `tourDone: true` and `audience: analyst`.
  Leaving `tourDone` out was a real trap: omitted keys fall back to the app's DEFAULTS, which are
  written for a first-time visitor, so a coach-mark overlay could appear mid-take on the exact
  screen the script exists to make identical.

**A card can now put its own subject on screen** (`Card.ensure`, added 2026-08-28). Card 3 of the
first-run tour points at the assistant — which at Everything with the rails shut is not rendered
at all, so the card showed its text, no ring appeared, and the tour looked broken at exactly the
moment it was explaining something. A card whose anchor is missing now runs `ensure` (open the
rail, pin the matrix) and the skip watcher gives React a paint before deciding there is nothing
to point at. It runs ONLY when the anchor is missing, so a reader who already has the panel open
is never re-arranged around it.

**And the quadrants are taught in the FIRST-RUN tour, not only the matrix deck.** Three cards —
the plot as one picture, the four corners as combinations of the two directions, and the button
that walks it properly — because someone meeting this product for the first time is exactly the
person who does not know what "value trap" means, and the matrix deck is opt-in. The
**? What am I looking at?** button moved onto the matrix's title line in the accent colour for
the same reason: a control nobody finds is a control that does not exist.

*(One debugging note worth keeping: the ring is measured in a `requestAnimationFrame` loop, which
browsers PAUSE in a hidden tab. Driving the app from a backgrounded tab shows every card with no
ring at all, and nothing is wrong — `document.hidden` is the thing to check before hunting for a
bug in `lib/anchor`.)*

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

**THE SECOND AXIS, AND WHY IT IS A GATE** (`financials.py` + `rationale.py`, added 2026-08-24,
Jayden's ask). The objection was fair: a company can improve on ESG and still be a bad business,
so "will it make money?" deserves an answer. There are two ways to build that and they end in
very different places.

**Folding an earnings term into the score would end the project.** `disagreement` currently means
one specific, defensible thing — our evidence-based momentum percentile minus the incumbent
rating's. Blend revenue into it and nobody, including us, can say what +0.6 is claiming; the
output stops being a disagreement with a rating and becomes a composite pick, which is HARD
RULE 4 and also a worse MSCI. So the financial read is a **CONTEXT GATE**, computed after the
scoring and reported beside it. `selftest.py` pins that `engine` and `signals` import neither
module, so the separation cannot rot.

**It needs no fetch.** The free keyless financial endpoints are gone — Yahoo's `quoteSummary` now
requires a crumb, and MSCI / S&P / Sustainalytics are licensed products that cannot be fetched,
shown or redistributed. But `data/company_metadata.csv` already carries **two fiscal years of net
income for all 52**, verified with sources on the row. That is the strongest financial variable
available and it was already on disk. Verdicts on the real basket: **17 strong · 22 adequate ·
11 weak · 2 unknown**.

**Three parse traps, all of which shipped a confidently wrong number under a real company's
name**, all now pinned by `selftest.py`: a parenthetical figure on a different scale
(`"S$789m (S$1.1b cont. ops)"` read the `b` and reported **+83,836%**); a range (`"~RM3.3-3.4b"`
took 3.3 with no unit against a RM3.1 **billion** prior year and reported **-99.9%** — RHB Bank
actually grew 8.1%); and a part-year cell (`"9M2024"` has no word boundary before the year, so
the leading **9** became the amount). A nine-month figure is not comparable to a full year at
all, so that case now **suppresses** the growth rate rather than computing one across two period
lengths. `unknown` stays distinct from `weak`, exactly as in `traction.py`.

**Every verdict now carries its own case against it** (`rationale.py` -> `CasePanel.tsx`). A
quadrant label is a conclusion; a reader is entitled to the reasoning, *including the parts that
cut against it*. So each company gets ESG pros/cons, financial pros/cons and a **what to look out
for** list — boundary proximity, provisional metadata, a mock baseline, evidence too old for the
horizon — all rule-derived, no LLM, so it replays with the run it describes. The cons are never
collapsed or dimmed: a case that only lists reasons to agree is marketing, and a tool arguing
that inconvenient evidence must surface cannot make an exception for its own verdicts. A company
with 92% self-published sources gets that said on its own card.

**THE BOARD STOPPED SAYING "AWAITING DATA" AT ITS OWN DATA** (fixed 2026-08-24). Four separate
causes, three of them false negatives:

- **The pillar cards were discarding the engine's own numbers.** They read a `momentum` block only
  the FICTIONAL demo set carries, so four tiles read "awaiting data" beside **E on 44 of 52** and
  **G on 38 of 52** companies that the engine had already scored. `metrics.pillar_momentum_from_records`
  falls back to `records[*].components`. Two different UNITS, so every row now carries `basis`:
  `numeric` is a momentum percent, `evidence` is a −1..+1 direction consensus. The radar's scale
  is floored at 5 for percents and fixed at 1 for consensus — flooring a consensus at 5 divides
  every real reading by five and collapses the shape onto the zero ring, which is exactly the
  "nothing is happening" picture this fix exists to stop showing. `fmtPillar` drops the percent
  sign for a consensus: "+0.59%" reads as a half-percent move when the number means "the evidence
  agrees, fairly strongly".
- **"0 signals" was counting the wrong field.** The rail read `live_signals` (demo-only) while the
  engine held three scored, dated, sourced signals for the same company.
- **A short-horizon company that decays to zero just emptied.** PTT Global Chemical reads +0.054
  on Long 180d and **0.000** on Short 45d — its newest evidence is 2023-10-15. Correct, and
  opaque. The card now says so and points at the longer horizon.
- **The price strip was never wired.** `quotes.change_90d` fetches a real 3-month series (the
  existing `CHART` range yields a one-DAY change, which under a "90 days" heading would be a real
  number with a wrong label). **20 of 52 resolve**; the Bursa misses need a numeric stock-code
  column and must NOT be closed with a name search — see the note in `quotes.py`.

**PRE-REGISTERED: the ONE calibration change we are allowed to make** (written 2026-08-25,
BEFORE the deep+quality sweep landed, and deliberately so). The standing question is whether the
Hidden Winner thresholds should be relaxed. The answer is normally NO — that is the Adaro failure
verbatim — so the rule for when it is YES has to be fixed in advance, or it is just fitting the
threshold to the answer we wanted.

**The test: a parameter may change for a reason that can be argued WITHOUT reference to the
answer it produces. It may not change because we dislike the answer.**

By that test:

- `confidence.saturation_count = 12` and `hidden_winners.min_signal_count = 10` are **suspect on
  their own merits.** Both were calibrated when the only rich universe was the FICTIONAL demo set,
  which carries 10-15 signals per name *by construction* because someone hand-authored it that
  way. That is a property of a fixture, not a fact about how much evidence exists for a real
  ASEAN mid-cap. Calibrating real-world saturation against a fixture's density is a mistake you
  can state without mentioning quadrants at all.
- `hidden_winners.min_confidence = 0.5` and `source_quality.company_pr = 0.5` are **not
  negotiable.** Neither has any defence except the answer it produces. The PR cap in particular
  IS the Adaro lesson; raising it would make "Hidden Winner" mean "we found a lot of press
  releases".

**The decision rule, fixed before the data existed.** After the sweep, read the DISTRIBUTION of
`signal_count` across the real 52:

| what the data shows | what we do |
|---|---|
| best-covered company reaches **>= `saturation_count`** (12) | Full coverage is reachable on real evidence. **Thresholds stand**, whatever the quadrant contains. |
| best-covered company is **< `saturation_count`** | Full coverage is unreachable BY CONSTRUCTION, so the parameter is mis-set. Recalibrate to the real 90th percentile — and accept whatever falls out, **including zero.** |

*(Rule tightened 2026-08-25, before the deep sweep ran and while the data it judges did not yet
exist. The first draft said ">= 15 stand / < 12 recalibrate", leaving 12-14 undefined — and the
basket then measured 13. The band was a comfort margin, never a principle: the only question the
test ever asked is whether the saturation point is REACHABLE. Fixing an ambiguous rule before it
is applied is legitimate; fixing it after seeing which branch you land in is not, which is why
the timing is recorded here rather than quietly corrected.)*

Either branch is published. A recalibration that happens to produce Hidden Winners is reported
with the fact that the threshold moved and why, never as a discovery.

**The proper instrument is already in the repo.** `tools/calibration.py` is a BLIND sheet: two
humans rate companies without seeing model output, and `harness.py` scores the model against
them. That is how a threshold is honestly justified — against human judgement, not against a
quadrant we would like populated. It is also a far better answer to a judge than any number
picked the night before.

**AND THE RULE ANSWERED ITSELF — one Hidden Winner, honestly** (measured 2026-08-25, right after
the pre-registration above and before the deep+quality sweep). The full 52-company sweep alone
was enough:

| | verified only | + first harvest | **+ full 52 sweep** |
|---|---|---|---|
| max signal_count | 5 | 7 | **13** |
| companies at confidence >= 0.5 | 0 | 0 | **4** |
| **Hidden Winners** | 0 | 0 | **1** |

**RHB Bank: disagreement +0.80, confidence 0.644, 10 signals.** The same company that sat in
`consensus` at 5 signals and 0.33 confidence — it crossed on MORE AND BETTER EVIDENCE, with not
one threshold touched. That is the outcome the Adaro rule was protecting: the quadrant populated
because the evidence arrived, not because the bar moved.

Note what this does to the pre-registered test: max is 13, which is `>= saturation_count`, so
full coverage is demonstrably reachable and **the thresholds stand unchanged.** The honest read
of "zero Hidden Winners" was never that the bar was wrong — it was that we had not gathered
enough evidence yet, and now we have. Four more names sit between 0.30 and 0.47 confidence, so
the deep+quality sweep may add to this; if it does, they cleared the same unmoved bar.

**SENSORS · VERIFICATION · LEDGER — where the chain actually sits** (framing settled 2026-08-24,
Jayden relaying the Blockchain Council line). The objection is correct and worth stating in full:
a blockchain is a closed, deterministic system that cannot reach real-world information, so *"put
ESG data on a blockchain"* is a meaningless sentence until you answer how the data got there and
whether it can be trusted. Read against this codebase it is not a gap — it is a description of
the three layers we already have, and the useful discipline is naming which file is which layer.

| layer | what it is here | where it lives |
|---|---|---|
| **1 · sensors** | evidence acquisition — four-angle live search, TF-IDF retrieval, the live incumbent rating, the industry bar, the verified basket | `harvest.py` · `rag.py` · `lseg.py` · `benchmarks.py` · `data/asean_universe.json` |
| **2 · verification** | the five harvest guards, source type decided by domain, company-PR capped at 0.5, forward-looking materiality halved, rule-based routing and deterministic scoring, the frozen 29-column header, `is_provisional` until reviewed, maker-checker | `harvest.py` · `signals.py` · `engine.py` · `company_metadata.py` · `harness.py` |
| **3 · ledger** | one Merkle root per run (`leaf-v2`), append-only `run_id -> root`, `anchor_pending` when no chain is reachable | `anchor.py` · `contracts/EvidenceAnchor.sol` |

**Our sensor layer is documentary, not telemetry, and that is a real limit** — we read filings,
regulator actions, exchange notices and press, we do not meter a smokestack. Say so plainly; the
alt-data roadmap (regulator actions, exchange filings, index-provider decisions, satellite) is
the honest answer to it, and it is also the binding constraint on Hidden Winners above.

**One correction to carry: the chain is NOT the verification layer.** By the Blockchain Council's
own argument it cannot be — a chain has no way to check an off-chain fact, and immutability
applied to a false claim just makes the false claim permanent. Verification here is done entirely
off-chain by rules that any reviewer can read, and the chain records a *commitment* to what those
rules saw: no token, no DAO, no on-chain scoring, and no raw or licensed data ever written. The
one `require` that reverts a second anchor on the same `run_id` **is** the tamper-evidence story.
Claiming the chain verifies anything would be the exact overclaim the quote is warning about.

**The two named comparables sit in a different layer, on the other side of the table.** TraceX and
Sustainability Track are supply-chain platforms: the company itself writes its own operational
data to a chain to evidence its own claims — issuer-side layer 1 and 3, with layer 2 amounting to
"immutable once written". We are investor-side and adversarial to the issuer: the company's own
publication is the *least* trusted source we hold, capped at 0.5 confidence by rule, and the
product's whole output is a disagreement with a rating rather than a report for the rated. Not a
competitor — the opposite end of the same pipe.

**Which rater, and why LSEG** (raised 2026-08-24: investors read MSCI, Sustainalytics and S&P, not
OECD reports). Two separate things were being conflated, and both answers are already in the code.
The OECD/Eurostat figure is **not an ESG rating and never stood in for one** — it is an industry
GHG intensity in g CO2e per euro of gross value added, which sizes the industry's structural bar;
`benchmarks.py` refuses to difference it against a company ESG score precisely because they are
different measures. The *incumbent rating* layer is separate: `lseg.py` fetches LSEG's real
published score live, because **LSEG is the one major rater with a free, keyless, per-company
endpoint** — MSCI, Sustainalytics and S&P are licensed products that cannot be fetched, shown or
redistributed without a contract, so quoting them would be a licence breach and inventing them
would be a HARD RULE 2 breach. The other houses are not absent: `metrics.parse_evidence` reads
MSCI, Sustainalytics, S&P Global / DJSI, CDP, FTSE4Good and GRESB wherever a company's own
`esg_basis` cites them, and the basket carries a notch grade (`incumbent_notch`, BBB / BB / B) on
the MSCI scale. That notch is now **on the engine record and shown in the evidence panel** — it
had been carried in the data and displayed nowhere, which meant the one industry-standard grade we
hold was invisible to a reader asking exactly this question. It travels **unattributed** (CGSI's
column header reads "ESG Rating" and names no agency) and is **display-only, never scored**:
`baseline_score` is the numeric score, and letting a second incumbent measure into the maths would
be two rulers in one number.

**`RECORD_SCHEMA` — a record shape is not a run input** (added with the notch). `run_id` hashes
every *input*, which is what makes a cache hit safe and what `anchor.py` keys its roots on. A
record's *shape* is decided by code, so adding a display field left the id untouched and a warm
cache would have served the old shape under the same id — on screen that reads "this company has
no notch", not "your cache is stale". `engine.RECORD_SCHEMA` is bumped when a record gains or
loses a field and `_read_cache` discards an older shape rather than serving it. It is deliberately
**not** in `run_id`: the scores, the evidence and the Merkle root are unchanged, so it is the same
run, and every existing anchor stays valid. Adding the notch moved the golden digest and nothing
else — same `run_id`, same labels, same momenta, zero per-company drift.

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
python tools/backtest_timeline.py               # redraw docs/backtest/*.svg (harness checks they are current)
python tools/calibration.py --sheet             # (re)write the blind sheet (cases + real names, >=2 excerpts)
python tools/calibration.py --rate rater_a --name "..."   # rate it, one keypress per company; resumable
python tools/calibration.py                     # score it once BOTH rater columns are filled
python tools/cost_inputs.py                     # the three numbers Sean's cost model is missing
python tools/phase_b.py --template              # the two Phase-B input shapes; --blind / --issuance to run
python anchor.py                          # build + anchor EVERY (universe x horizon) run; --list, --verify
python pipeline_counts.py --freeze        # B2 — N/M/K frozen with a run id + date
python tools/llm_cost.py --price-in X --price-out Y   # cost per company (prices must be supplied)
python -m scripts.build_cgsi_basket       # rebuild the basket from CGSI_52_verified.csv (--check)
python -m scripts.refresh_eurostat_benchmark  # verify the industry bar live (--write to refresh)
python pipeline_counts.py --real --freeze     # N/M/K on the real basket -> data/nmk_frozen.json
python tools/phase_b.py --blind data/phase_b/cgsi_picks_17.json --real   # the blind 17-pick test
python -m scripts.build_metadata_mock    # regenerate the PROVISIONAL metadata CSV
python -m scripts.build_oecd_benchmark   # refresh data/oecd_industry_benchmark.csv from OECD SDMX
python benchmarks.py                     # the per-industry table: ASEAN average vs OECD intensity
python quotes.py                         # live quotes for one name per ASEAN exchange
python lseg.py "DBS Group Holdings" SGX  # one company's real LSEG ESG score; no args = all 52
python sensitivity.py IDX:ASMB           # what would change this verdict (--real, --horizon, --json)
python harvest.py --empty                # gather evidence for every zero-signal company
python harvest.py --refilter             # re-apply the guards to stored harvests (no re-fetch)
python traction.py --sheet --gather      # the loss-maker screen + retrieved candidate sources
python harvest.py --cost                 # measured tokens/company (writes data/harvest_cost.json)
python cost_model.py --price-hit 0.007 --price-miss 0.22 --price-out 0.66 --window off-peak
python -m scripts.sg_day_rates --write   # day rates from live SG postings
python -m scripts.build_cost_workbook --price-hit 0.007 --price-miss 0.22 --price-out 0.66
python -m scripts.build_pitch_pptx --pdf # the 9-slide deck -> docs/pitch/*.pptx (+ PDF via soffice)
python -m scripts.demo_diversify         # re-derive demo momentum/signals/news (esg_score untouched)
python -m scripts.demo_reset --first-run # the blob a JUDGE should meet: setup unrun, tutorial armed
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

**The root is not a junk drawer** (tidied 2026-08-24). 32 loose `.py` files became 25: the
developer CLIs moved to `tools/` and the two pre-rewrite July modules to `legacy/`. Nothing the
app imports at runtime moved — `core`, `universe`, `signals`, `engine`, `server` and friends stay
flat, because **19 modules anchor their `data/` paths off `__file__`** and moving one silently
repoints it at a directory that does not exist. That is not hypothetical: `esg_data.py` started
reading `legacy/data/` the moment it moved, and the tools all lost their imports until the
`sys.path` bootstrap went in ABOVE them rather than below. Each moved file now derives the repo
root one level up and says so in a comment. A proper `src/` package is a real option, but it is a
40-edit change whose failure mode is a silent empty read — do it after a deadline, never before.

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
