# docs/stage2.md — Stage 2 brief: **Compete over data** (the differentiator)

> Load this with `CLAUDE.md` before touching `stage2.py`. The contract shapes in
> `CLAUDE.md` / `contracts.py` are frozen and authoritative. If anything conflicts,
> `CLAUDE.md` wins — ask, don't guess.

---

## Job

Take the `NarrowedQuestion` (Contract A) + the `CompanyData` (Contract B) and answer by
**COMPETING**: take a position that **disagrees with the stale Layer A rating**, justified
by specific **Layer B** evidence the static rating cannot see. This is the **differentiator**
— the "Competes" beat. It is **not** a ranker and **never** says buy/sell/hold or a score.

A fresh agent: it sees ONLY the two JSON blobs — **never Stage 1's interrogation chat**.

## Owns / does not touch

- **Owns:** `stage2.py` only (the competing-reasoner IP is `SYSTEM_PROMPT`).
- **Must not:** invent any fact, use outside knowledge of a real company, render UI, or
  edit `core.py` / `contracts.py` (frozen). No Streamlit imports here — it stays a pure
  reasoning agent so tests import it cleanly.

## Input

- **Contract A** `NarrowedQuestion` (from `fixtures/narrowed_question.json` / Stage 1).
- **Contract B** `CompanyData` (`data/hero_company.json`): `layer_a` (a STALE static
  rating) + `layer_b` (momentum, `digital_ai_signal`, `conflicting_signals`,
  `near_term_catalyst`).

Both are packed into ONE user turn by `build_user_message(narrowed_question, company)`.

## Output baton — Contract C (`Stage2Answer`)

```json
{ "question_to_ask": "...", "what_rating_sees": "...", "what_we_see": "...",
  "check_before_monday": "...", "competes_summary": "..." }
```

Produced by `reason(narrowed_question, company)` → `core.call_llm(..., json_mode=True)` →
`contracts.coerce_stage2_answer`. Saved to `fixtures/stage2_answer.json` for Stage 3.

## Hard constraints (enforced by `SYSTEM_PROMPT`)

- Reason ONLY over the two inputs. Missing fact → **"unknown"**, never invented (the
  coercer fills `"unknown"` if the model omits a key).
- The sample data are **placeholders** — never present them as real facts.
- **Never** buy/sell/hold, a target, or a score.
- Quote Layer B figures **verbatim** (e.g. `ai_governance_hiring_velocity` `+340% YoY`,
  `ai_disclosure_level` `none`, the momentum magnitudes, the `near_term_catalyst`).
- Surface `conflicting_signals` where relevant.
- Frame `check_before_monday` by the mandate: **risk** → a downside/exposure check;
  **return** → an upside/mispricing check; **compliance** → a regulatory-readiness check.
- `competes_summary` MUST be ONE sentence that **explicitly contradicts** Layer A
  (not "the rating may be incomplete" — it must name the stale view and disagree).

## Defensive behaviour

- `coerce_stage2_answer` keeps only contract keys and fills gaps with `"unknown"`.
- `_raw` + `_parse_failed` are attached for the debug view / Stage 3's failure handling;
  they are stripped from any on-disk baton.

## Acceptance

- Emits a valid Contract C that **cites the Layer B AI gap (`+340% YoY`) + the MAS
  catalyst** and **names the stale Layer A view** (`Medium Risk`); `selftest.py ::
  test_stage2_chain` passes.
- Live: it actually contradicts the rating — it does not hedge.
