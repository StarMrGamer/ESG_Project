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
  server.py                 # FastAPI API boundary + static React host: dashboard · chat · relay · evidence
  stage1.py                 # AGENT 1 owns — interrogation loop (+ visible CoT rationale)
  stage2.py                 # AGENT 2 owns — reason over data + RAG + history (emits CoT + sources)
  stage3.py                 # Contract C Markdown/text export helpers (React owns live rendering)
  engine.py                 # run_engine(company_list) — the reproducible score records (Gate 1)
  signals.py                # deterministic signal extraction from stored evidence (no LLM, no clock)
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
    build_metadata_mock.py   # regenerates the PROVISIONAL metadata CSV (deterministic)
    build_oecd_benchmark.py  # pulls OECD SDMX (emissions x value added) -> the industry benchmark CSV
    demo_diversify.py        # re-derives ONLY demo momentum/live_signals/news
                            #   (preserves esg_score — the MOCK baseline must not move)
  data/oecd_industry_benchmark.csv  # REAL OECD GHG intensity per ISIC industry (built by the script below)
  data/asean_universe.json  # BASE DB — 52 ASEAN ESG improvers (evidence-based: esg_basis/source_url/confidence)
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

**The board is layered.** `settings.level` is 1 Brief · 2 Analysis · 3 Everything, and every
widget declares the level it earns: level 1 is the verdict, the pillar cards, one action and a
one-line assistant bar; level 2 adds the momentum chart, the rankings, the industry-benchmark
table and the universe grid; level 3 adds the disagreement matrix, provenance and the evidence
trail. `simplified` is DERIVED from `level` in `setSettings`, so the server-facing flag and the
UI control can never disagree. A step-up bar at the foot of levels 1 and 2 says what the next
level would add. The matrix used to be the first thing on the page — a wall of dots before you
knew what a dot meant — which was most of why the board read as overwhelming.

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
python -m scripts.build_metadata_mock    # regenerate the PROVISIONAL metadata CSV
python -m scripts.build_oecd_benchmark   # refresh data/oecd_industry_benchmark.csv from OECD SDMX
python benchmarks.py                     # the per-industry table: ASEAN average vs OECD intensity
python quotes.py                         # live quotes for one name per ASEAN exchange
python -m scripts.demo_diversify         # re-derive demo momentum/signals/news (esg_score untouched)
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
