# Spec — AI Head-to-Head Comparison (compare 2 companies)

_Date: 2026-06-29 · ASEAN ESG Momentum Radar_

## Goal

Let a user compare **two** monitored companies with the radar's "competes" reasoning,
not just a static metric stack. A fresh agent reads **both** companies' Layer A/B data +
live RAG and produces an **axis-by-axis** comparison of their live ESG signals, naming on
each axis which company has the **stronger live ESG signal** and what each company's stale
rating misses.

This extends — does not replace — the existing static side-by-side `_render_compare`
(which already stacks rating / band / E·S·G arrows / red flags / coverage for 2–4 names).

## Non-goals & guardrails (from CLAUDE.md)

- **Not a ranker / no pick.** No overall "winner", no composite score, no buy/sell/hold,
  no allocation advice. The comparison is per ESG axis only — **no overall summary
  sentence** (explicit user decision). (HARD RULE 4.)
- **Never invent.** Any company fact not in its Contract B or a cited source is "unknown".
  Figures are quoted verbatim. (HARD RULE 2.)
- **Sources are real.** `sources` is attached from the actual retrieved snippets for both
  companies — the model never fabricates a URL. (HARD RULE 2.)
- **Retrieval isolated + best-effort.** Web fetch only via the existing `rag` /
  `core.http_get` path; offline degrades to "no external context", never a crash.
  (HARD RULES 1 & 6.)
- **File ownership.** Reasoning lives in `stage2.py`, rendering in `stage3.py`, wiring in
  `app.py`. `core.py` and `contracts.py` stay frozen — the head-to-head output is a plain
  dict, NOT a new contract. (HARD RULE 7.)

## Scope: exactly 2

The AI head-to-head runs only when **exactly 2** companies are selected. The static
side-by-side keeps supporting 2–4. With 3–4 selected, the head-to-head button is hidden
with a "select exactly 2 for the AI head-to-head" hint.

## Components

### 1. `stage2.py` — reasoning (new)

`COMPARE_SYSTEM_PROMPT` — a fresh "ESG comparative reasoner" prompt. Same hard constraints
as `SYSTEM_PROMPT`, plus: compare on a FIXED axis set, declare a per-axis `edge` by
**stronger live ESG signal**, never declare an overall winner, never give buy/sell/score.

`compare_reason(company_a, company_b, on_delta=None, context_a=None, context_b=None)`:
- Reuses `retrieve_context(...)` once per company (best-effort; offline → no snippets).
  A lightweight default NarrowedQuestion (mandate=risk) is used to seed each retrieval, so
  no prior deep dive is required.
- Builds one user turn packing both Contract B profiles + both retrieved-context blocks.
- Calls `core.call_llm(... json_mode=True ...)` with a one-shot non-streaming retry on a
  parse failure (mirrors `reason`).
- Coerces to the output shape below; attaches `sources` from the real snippets of BOTH
  companies (deduped by URL). Stamps `_raw` / `_parse_failed` / `_rag_status` debug fields.

**Output dict (new shape, not a frozen contract):**

```json
{
  "question": "the comparative ESG question across the two companies",
  "company_a": "name A",
  "company_b": "name B",
  "axes": [
    {
      "axis": "Environmental momentum",
      "a_read": "A's live signal on this axis (verbatim figures if present, else 'unknown')",
      "b_read": "B's live signal on this axis",
      "edge": "a | b | tie",
      "edge_note": "one line — which side's live ESG signal is stronger + what each rating misses"
    }
  ],
  "reasoning": ["step 1", "step 2", "..."],
  "sources": [{"title": "...", "url": "..."}]
}
```

Fixed axes (model fills reads per company; "unknown" where data is absent):
Environmental momentum · Social momentum · Governance momentum · Digital/AI signal ·
Rating staleness (Layer A as-of). `edge` ∈ {`a`,`b`,`tie`} where the stronger / more
recent live signal wins; `tie` when both are comparable or both unknown.

A small `coerce_comparison(d, a, b)` helper keeps the output robust (drop unknown-keyed
junk, ensure `axes` is a list of well-formed rows, `reasoning`/`sources` are lists).

### 2. `stage3.py` — rendering (new)

`render_comparison(result, company_a, company_b, debug=False)`:
- Caption: the two subjects + origin disclaimers.
- The comparative **question** (`result["question"]`).
- **Axis table** — one styled row per axis: axis label · A's read · B's read · an **edge
  chip** ("◀ A stronger" / "B stronger ▶" / "≈ tie", coloured) · the `edge_note`.
  Reuses the existing palette (`esg-panel` / `esg-card` / pos/flat/down colours); wraps to
  one column on narrow screens. No overall verdict line.
- Collapsed **chain-of-thought** (reuse `_render_reasoning`).
- **Sources** (reuse `_source_list`) — the live retrieval behind the comparison; honest
  "no external sources" message when offline.
- Failure handling mirrors `render_answer`: on `_parse_failed` / all-unknown axes, show a
  friendly warning + raw expander instead of a wall of "unknown".

### 3. `app.py` — wiring

In `_render_compare`, after the existing top bar and BEFORE the static cards:
- Compute `is_pair = len(tickers) == 2`.
- If `is_pair`: render a **"⚔️ Run AI head-to-head"** primary button (or "↻ Re-run" if a
  cached result exists). On click, call a new `_run_compare(ss, tk_a, tk_b)` that runs
  retrieval + `stage2.compare_reason` inside the same `st.status` spinners as `_run_stage2`,
  with friendly `LLMConfigError` / generic error recovery, then caches the result in
  `ss.compare_answers[(tk_a, tk_b)]` and reruns.
- If a cached result exists for the current pair, render it via
  `stage3.render_comparison(result, company_a, company_b)` (instant on revisit).
- If not a pair: caption "Select exactly 2 monitored companies for the AI head-to-head."
- The static side-by-side cards render unchanged below.

New session state: `compare_answers: {}` (dict keyed by sorted ticker pair). Added to the
session-state defaults and cleared by `_reset`. Cache is invalidated implicitly by keying
on the ticker pair; a "↻ Re-run" button forces a fresh call.

## Data flow

```
two monitored snapshots (CompanyData ×2)
  → stage2.compare_reason
       ├─ retrieve_context(A)  ┐ best-effort RAG, isolated, offline-safe
       └─ retrieve_context(B)  ┘
       → one LLM turn (both profiles + both contexts)
       → comparison dict (+ real sources, deduped)
  → stage3.render_comparison  → axis table + CoT + sources
  → cached in ss.compare_answers[(a,b)]
```

## Testing

- `selftest.py` stays green (no contract changes; frozen files untouched).
- Add a small offline check: `compare_reason` over two sample/`hero_company`-style dicts
  with retrieval disabled returns a well-formed dict (`axes` is a list, `sources == []`),
  and `coerce_comparison` repairs a junk/partial dict. Manual UI check: select 2 on the
  monitored board → Compare → ⚔️ head-to-head renders; 3–4 selected hides the button but
  the static compare still works; offline run degrades gracefully.

## Acceptance

Selecting exactly two monitored companies and running the head-to-head yields an
axis-by-axis ESG-signal comparison that quotes each company's Layer B figures (or
"unknown"), names the stronger live signal per axis, cites real retrieved sources, shows
its chain of thought, declares **no overall winner**, and never says buy/sell/hold or
emits a score. Offline still produces the axis table from the data alone.
