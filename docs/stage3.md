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

- **Contract C** `Stage2Answer` (`fixtures/stage2_answer.json` / live from Stage 2).
- Optional `company` (for the subject caption) and `debug` (show raw model output).

## Layout — **verdict first** (action-plan Fix #3)

A decision tool leads with the punchline ("show me something I don't know", criterion 03):

1. **Subject caption** — company · ticker · sector, with the **illustrative-scenario /
   placeholder** disclaimer (we keep DemoBank SG framed as illustrative, never as real).
2. **Failure guard** — if `_parse_failed` or every field is `"unknown"`, show a warning
   instead of a wall of `"unknown"`; the verdict headline is skipped in that case.
3. **⚔️ The verdict** — `competes_summary` as the headline (the one-sentence disagreement).
4. **🎯 The question** — `question_to_ask`.
5. **Market view vs. reality** — two columns: 📊 `what_rating_sees` | 🛰️ `what_we_see`.
6. **✅ Check before Monday** — `check_before_monday`.
7. Disclaimer caption — we disagree with the rating using a signal it can't see; never
   buy/sell/hold.

## Key function

- `render_answer(answer, company=None, debug=False)` — the whole panel. Pure display;
  reads only Contract C keys (`_FIELDS`) plus the optional `_raw` / `_parse_failed`
  debug fields.

## Acceptance

- Displays all five Contract C fields, led by the verdict.
- A failed / empty Stage 2 degrades to the warning box (no wall of `"unknown"`).
- Never shows buy/sell/hold or a score; the placeholder framing is always visible.
