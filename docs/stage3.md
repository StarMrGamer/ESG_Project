# docs/stage3.md — Stage 3 brief: **Export** (the decision tool)

> Load this with `CLAUDE.md` before touching `stage3.py`. The contract shapes in
> `CLAUDE.md` / `contracts.py` are frozen and authoritative. If anything conflicts,
> `CLAUDE.md` wins — ask, don't guess.

---

## Job

Take a `Stage2Answer` (Contract C) and provide dependency-free Markdown/text exports. The
React client is the live decision-tool renderer. This is CGSI **criterion 02 ("simple, clear
output")**. **Export-only — NO LLM call here.** Re-reasoning would risk re-wording or
fabricating the verified baton (HARD RULE 2).

## Owns / does not touch

- **Owns:** `stage3.py` export helpers; React owns the live presentation.
- **Must not:** call the LLM, mutate the answer dict, import Streamlit/Plotly, or edit
  `core.py` / `contracts.py` (frozen).

## Input

- **Contract C** `Stage2Answer` (`fixtures/stage2_answer.json` / live from Stage 2) — now
  incl. `reasoning` (CoT) + `sources` (RAG citations).
- Optional `company` metadata and Layer B evidence.

## Export shape — **verdict first**

A decision tool leads with the punchline ("show me something I don't know", criterion 03);
the depth (CoT, evidence, history, sources) sits below it — *simplicity in what it says,
sophistication in how it thinks*:

1. Subject, origin disclaimer, and verdict.
2. Market view versus reality and the concrete Monday check.
3. Known Layer B pillar/AI signals only; unknown-only rows are omitted.
4. Optional reasoning and live sources.
5. Disclaimer: this is not investment advice and never says buy/sell/hold.

## Key functions

- `_card_md(answer, company)` — Markdown report.
- `_card_text(answer, company)` — plain-text report.
- `_disclaimer(company)` — origin-aware provenance language.

## Acceptance

- Reports the five text fields led by the verdict, plus known evidence, reasoning, and sources.
- Sparse data omits unknown-only evidence sections.
- Never shows buy/sell/hold; origin framing is always visible.
