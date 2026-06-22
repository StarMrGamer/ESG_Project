# docs/stage3.md — Stage 3 brief: **Render** (the decision tool)

> Load this with `CLAUDE.md` before touching `stage3.py`. The contract shapes in
> `CLAUDE.md` / `contracts.py` are frozen and authoritative. If anything conflicts,
> `CLAUDE.md` wins — ask, don't guess.

---

## Job

Take a `Stage2Answer` (Contract C) and present it as a clear decision tool. This is CGSI
**criterion 02 ("simple, clear output")**. **Render-only — NO LLM call here.** Re-reasoning
would risk re-wording or fabricating the verified baton (HARD RULE 2); Stage 3 just
displays what Stage 2 verified.

## Owns / does not touch

- **Owns:** `stage3.py` only.
- **Must not:** call the LLM, mutate the answer dict, or edit `core.py` / `contracts.py`
  (frozen). All `st.*` calls live inside `render_answer()` so the module imports cleanly.

## Input

- **Contract C** `Stage2Answer` (`fixtures/stage2_answer.json` / live from Stage 2) — now
  incl. `reasoning` (CoT) + `sources` (RAG citations).
- Optional `company` (subject caption, Layer B evidence, `layer_a_history` strip),
  `narrowed` (Contract A — the interrogation trail recap) and `debug`.

## Layout — **verdict first** (action-plan Fix #3)

A decision tool leads with the punchline ("show me something I don't know", criterion 03);
the depth (CoT, evidence, history, sources) sits below it — *simplicity in what it says,
sophistication in how it thinks*:

1. **Subject caption** — company · ticker · sector, with the **illustrative-scenario /
   placeholder** disclaimer (we keep DemoBank SG framed as illustrative, never as real).
2. **Failure guard** — if `_parse_failed` or every text field is `"unknown"`, show a warning
   instead of a wall of `"unknown"`; the verdict headline is skipped in that case.
3. **⚔️ The verdict** — `competes_summary` headline + "what would change our mind" +
   **🧠 collapsible chain-of-thought** (`reasoning`).
4. **🧭 How we narrowed your question** — the interrogation trail recap (from `narrowed`).
5. **🎯 The question** — `question_to_ask`.
6. **Market view vs. reality** — two columns: 📊 `what_rating_sees` | 🛰️ `what_we_see`.
7. **✅ Check before Monday** — `check_before_monday`.
8. **📡 Evidence** (Layer B momentum/AI/conflict) + **📈 historical-vs-current** static-score
   strip (from `layer_a_history`) + **🔗 Sources** (live RAG citations) + **📋 export** card.
9. Disclaimer caption — we disagree with the rating using a signal it can't see; never
   buy/sell/hold.

## Key function

- `render_answer(answer, company=None, debug=False, narrowed=None)` — the whole panel. Pure
  display; reads Contract C keys (`_FIELDS` + `reasoning`/`sources`) plus optional `_raw` /
  `_parse_failed` / `_rag_status` debug fields. Never calls the LLM or mutates the answer.

## Acceptance

- Displays the five text fields led by the verdict, plus the CoT, the historical strip, and
  the live sources (or a graceful "no sources" note when offline / disabled).
- A failed / empty Stage 2 degrades to the warning box (no wall of `"unknown"`).
- Never shows buy/sell/hold or a score; the placeholder framing is always visible.
