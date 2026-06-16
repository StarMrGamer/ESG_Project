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
  core.py                   # FROZEN — DeepSeek client, JSON parser, config
  contracts.py              # FROZEN — the handoff data shapes (below)
  app.py                    # Streamlit shell; wires the 3 stages (integrator owns)
  stage1.py                 # AGENT 1 owns — interrogation loop
  stage2.py                 # AGENT 2 owns — reason over data
  stage3.py                 # AGENT 3 owns — render the answer (dashboard)
  data/hero_company.json    # Layer A + Layer B sample (PLACEHOLDER values)
  fixtures/                 # handoff batons: seeded in Phase 0, then REPLACED by each
    narrowed_question.json  #   stage's real verified output as the relay proceeds.
    stage2_answer.json      #   Each file = next stage's input + a regression check.
  docs/stage1.md docs/stage2.md docs/stage3.md   # detailed per-stage briefs
```

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

**Contract B — `CompanyData` (data → Stage 2), stored in `data/hero_company.json`**
```json
{
  "company": "DemoBank SG", "ticker": "SGX:DEMO", "sector": "Financials — Banks",
  "layer_a": { "esg_score_static": "22.4 (Medium Risk)", "as_of_date": "2023-09-30",
               "note": "Risk score: LOWER = better. Stale baseline." },
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
  "what_rating_sees": "string (from Layer A — the stale view)",
  "what_we_see": "string (from Layer B — the signal + the gap)",
  "check_before_monday": "string (one concrete action, framed by mandate)",
  "competes_summary": "string (one sentence that explicitly disagrees with the rating)"
}
```

---

## THE STAGES (concise — full spec in docs/stageN.md)

**Stage 1 — Interrogate.** Vague question in → up to 5 ADAPTIVE questions, each mapped to
ONE ESG axis (materiality / time-horizon / mandate / blind-spot) → output a
`NarrowedQuestion`. CHALLENGE bad framing. NEVER answer the ESG question. Uses LLM
reasoning only — NO data.

**Stage 2 — Reason over data.** Take a `NarrowedQuestion` + `CompanyData`. Answer by
COMPETING: disagree with Layer A using Layer B evidence. Cite specific Layer B figures,
surface the data conflict, frame the closing line by the `mandate`. Output a
`Stage2Answer`. NEVER invent data not in the JSON.

**Stage 3 — Render.** Take a `Stage2Answer` and present it as a clear decision tool: the
four lines, the competes summary, and a simple "market view vs reality" panel. Minimal
polish — no charts unless time. This is CGSI criterion 02 ("simple, clear output").

---

## TECH STACK & COMMANDS

- Python 3.8+, Streamlit, OpenAI SDK (DeepSeek is OpenAI-compatible).
- LLM: **DeepSeek**, model `deepseek-v4-flash`, `base_url="https://api.deepseek.com"`,
  key from env `DEEPSEEK_API_KEY`. All LLM access goes through `core.call_llm()`.
```bash
pip install streamlit openai
export DEEPSEEK_API_KEY="sk-..."     # Windows: $env:DEEPSEEK_API_KEY="sk-..."
streamlit run app.py
```

---

## HARD RULES (never violate)

1. **No live data / no DB / no web fetch.** One local JSON file only.
2. **Never fabricate.** The model reasons ONLY over provided data. Missing fact → say
   "unknown", never invent. No numbers/dates not present in the JSON.
3. **Placeholders stay placeholders.** Sample data values are NOT real facts about any
   real company — never present them as such, in code, comments, or output.
4. **Never give buy/sell/hold or a score.** We disagree with ratings; we don't pick.
5. **Never hard-code the API key.** Read from env.
6. **Provider isolation.** LLM calls only via `core.call_llm()`. (DeepSeek wraps JSON in
   prose sometimes — always parse defensively via `core.parse_json()`.)
7. **File ownership.** Each agent edits ONLY its own `stageN.py`. Do NOT edit `core.py`
   or `contracts.py` (frozen) without sign-off. Do NOT build the next stage's job.

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
