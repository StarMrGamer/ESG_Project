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
  app.py                    # Streamlit COMMAND-CENTER shell: filters · pillars · hidden winners · AI assistant · deep dive
  stage1.py                 # AGENT 1 owns — interrogation loop (+ visible CoT rationale)
  stage2.py                 # AGENT 2 owns — reason over data + RAG + history (emits CoT + sources)
  stage3.py                 # AGENT 3 owns — render the answer (verdict, CoT, history, sources)
  data/asean_universe.json  # BASE DB — 52 ASEAN ESG improvers (evidence-based: esg_basis/source_url/confidence)
  data/demo_universe.json   # FICTIONAL fully-numeric demo set — makes the command center alive (labelled illustrative)
  data/hero_company.json    # SAMPLE only — offline-demo safety net + test fixture (PLACEHOLDER)
  data/watchlist.json       # runtime: pinned tickers (local, git-ignored — not source)
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

Layout (3 columns): **Left** = Filters (Industry/Country) + the **average ESG of the filtered set**
(recomputes per industry — the user's key ask) + the Monitored list. **Center** = four pillar
cards (avg **E/S/G/Digital-AI** momentum) + a momentum chart + **Hidden winners vs peer avg** +
a **Classification** verdict. **Right** = the **AI assistant** (it *controls the filters* — "show
banks", "Singapore", "all ASEAN" — adds/focuses companies, applied at the TOP of the run before
widgets via `ss.pending_chat`) + **Live signals** + **Why the rating may be wrong**.

`metrics.py` holds all aggregation (pure, tested). The panels need OPTIONAL numeric per-constituent
fields — `esg_score`, `esg_as_of`, `momentum:{environment,social,governance,digital_ai}`,
`live_signals:{ai_hiring_surge,green_patents,carbon_disclosure,controversy_flags,board_ai_policy}` —
absent → "awaiting data" (never fabricated for real names). A **Demo data** toggle swaps in
`data/demo_universe.json` (FICTIONAL, fully numeric) so the board is alive before real numbers land.
Click a card → **deep dive** = the Stage 1→2→3 relay. `country`/`exchange`/numeric fields ride as
NON-contract fields, so `contracts.py` stays frozen.

**Build order (relay, in sequence):** Phase 0 — build & FREEZE `core.py`, `contracts.py`,
the `app.py` shell, and seed `fixtures/`. Then **Stage 1 → Stage 2 → Stage 3 in order**:
each agent owns ONE file, consumes the previous stage's verified output from `fixtures/`,
and saves its own verified output there as the baton for the next. Integrate in `app.py`.
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

- Python 3.8+, Streamlit, OpenAI SDK (DeepSeek is OpenAI-compatible), `requests` (live fetch).
- LLM: **DeepSeek**, model `deepseek-v4-flash`, `base_url="https://api.deepseek.com"`,
  key from env `DEEPSEEK_API_KEY`. All LLM access goes through `core.call_llm()`.
- RAG: keyless live fetch from DuckDuckGo (HTML/Lite search results + the Instant-Answer "AI"
  summary) via `core.http_get()`, ranked by a pure-Python TF-IDF retriever in `rag.py`. The
  agent INTERPRETS the AI summary; snippets carry real source URLs. Tunables (all optional):
  `ESG_HTTP_TIMEOUT` (8s), `ESG_RAG_TOP_K` (5), `ESG_RAG_MAX_DOCS` (12), `ESG_RAG_TTL` (6h),
  `ESG_USER_AGENT`. Results cache to `.cache/` (git-ignored).
```bash
pip install -r requirements.txt          # streamlit, openai, requests
export DEEPSEEK_API_KEY="sk-..."          # Windows: $env:DEEPSEEK_API_KEY="sk-..."
streamlit run app.py
python selftest.py                        # offline check — no key, no network
```

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
   `fixtures/` as the baton for the next stage; wire into `app.py`.
5. Acceptance = your stage consumes/produces its contract exactly, and the end-to-end
   demo chain runs: vague question → narrowed question → four-line competing answer that
   cites the Layer B gap + the MAS catalyst, with zero invented facts.
