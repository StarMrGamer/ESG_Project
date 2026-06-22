# docs/stage2.md — Stage 2 brief: **Compete over data** (the differentiator)

> Load this with `CLAUDE.md` before touching `stage2.py`. The contract shapes in
> `CLAUDE.md` / `contracts.py` are frozen and authoritative. If anything conflicts,
> `CLAUDE.md` wins — ask, don't guess.

---

## Job

Take the `NarrowedQuestion` (Contract A) + the `CompanyData` (Contract B, incl.
`layer_a_history`) + **live RETRIEVED_CONTEXT** (RAG) and answer by **COMPETING**: take a
position that **disagrees with the stale Layer A rating**, justified by specific **Layer B**
evidence **and the historical trend** the static rating cannot see, **grounded** by the
retrieved context. This is the **differentiator** — the "Competes" beat. It is **not** a
ranker and **never** says buy/sell/hold or a score. It also **shows its reasoning** (CoT).

A fresh agent: it sees ONLY the narrowed-question baton + the data + the retrieved snippets
— **never Stage 1's interrogation chat**.

## Owns / does not touch

- **Owns:** `stage2.py` (the competing-reasoner IP is `SYSTEM_PROMPT`) + `rag.py` (retrieval).
- **Must not:** invent any company fact, use outside knowledge of a real company, render UI,
  or edit `core.py` / `contracts.py` (frozen). No Streamlit imports here. Web fetch only via
  `core.http_get()`.

## Input

- **Contract A** `NarrowedQuestion` (from `fixtures/narrowed_question.json` / Stage 1).
- **Contract B** `CompanyData` — built **live** (grounded extraction), **uploaded**, or the
  **sample** (`data/hero_company.json`); see `datasource.py`. Holds `layer_a` (STALE static
  rating), `layer_a_history` (the static-score TREND over time), + `layer_b` (momentum,
  `digital_ai_signal`, `conflicting_signals`, `near_term_catalyst`). For live/uploaded data
  many fields may be `"unknown"` (grounded-only) — reason over what's present, never invent.
- **RETRIEVED_CONTEXT** — ranked snippets from `retrieve_context(nq, company, use_rag)` →
  `rag.gather_context()`. May be empty (offline / disabled) — reason anyway.

All three are packed into ONE user turn by `build_user_message(nq, company, snippets)`.

## Live retrieval (RAG) — `rag.py`

- `build_query(nq, company)` → focused query (narrowed question + sector + catalyst).
- `fetch_documents(query)` → real docs via Google News RSS + Wikipedia (keyless), cached to
  `.cache/` with a TTL. **Never raises** — a dead network returns `([], "offline")`.
- `retrieve(query, docs, k)` → pure-Python **TF-IDF + cosine** ranking; top-k snippets with
  their real `title` + `url`. Sources are attached from these — the model never invents a URL.

## Output baton — Contract C (`Stage2Answer`)

```json
{ "question_to_ask": "...", "what_rating_sees": "...", "what_we_see": "...",
  "check_before_monday": "...", "competes_summary": "...",
  "reasoning": ["short CoT step", "..."], "sources": [{"title": "...", "url": "..."}] }
```

Produced by `reason(nq, company, context=...)` → `core.call_llm(..., json_mode=True)` →
`contracts.coerce_stage2_answer`, then `sources` is set from the real retrieval. The five
text fields are **tight** (one sentence each; `competes_summary` ≤ 30 words) — the long
thinking lives in `reasoning`. Saved to `fixtures/stage2_answer.json` for Stage 3.

## Hard constraints (enforced by `SYSTEM_PROMPT`)

- Reason ONLY over the three inputs. Missing **company** fact → **"unknown"**, never invented
  (the coercer fills `"unknown"` if the model omits a text key). RETRIEVED_CONTEXT only
  *grounds* the argument — it never supplies a company number/date/rating.
- The COMPANY_DATA values are **placeholders** — never present them as real facts.
- **Never** buy/sell/hold, a target, or a score.
- Quote Layer B figures **verbatim** (e.g. `ai_governance_hiring_velocity` `+340% YoY`,
  `ai_disclosure_level` `none`, the momentum magnitudes, the `near_term_catalyst`), and
  surface the `layer_a_history` trend + the `conflicting_signals`.
- Frame `check_before_monday` by the mandate: **risk** → a downside/exposure check;
  **return** → an upside/mispricing check; **compliance** → a regulatory-readiness check.
- `competes_summary` MUST be ONE tight sentence (≤ 30 words) that **explicitly contradicts**
  Layer A. Keep all five text fields to one sentence; put the long thinking in `reasoning`.

## Defensive behaviour

- `coerce_stage2_answer` keeps the five text fields (filling `"unknown"`) + normalises
  `reasoning`/`sources` to clean lists.
- `sources` is **overwritten** from the real retrieved snippets in `reason()` — provenance
  the model can't fabricate. Empty when offline / disabled.
- `_raw` + `_parse_failed` + `_rag_status` + `_rag_query` are attached for the debug view /
  Stage 3; they are stripped from any on-disk baton.
- Retrieval is best-effort: `retrieve_context` and `rag.*` never raise — offline ⇒ no snippets.

## Acceptance

- Emits a valid Contract C that **cites the Layer B AI gap (`+340% YoY`) + the MAS
  catalyst** and **names the stale Layer A view** (`Medium Risk`), with a non-empty
  `reasoning` chain-of-thought; `selftest.py :: test_stage2_chain` passes (RAG bypassed).
- RAG: `selftest.py :: test_rag_retrieval` ranks the relevant doc first; `test_rag_offline_
  graceful` proves a dead network degrades to `[]`.
- Live: it actually contradicts the rating — it does not hedge — and cites real sources.
