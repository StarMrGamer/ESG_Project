# docs/stage1.md — Stage 1 brief: **Interrogate** (the hero)

> Load this with `CLAUDE.md` before touching `stage1.py`. `CLAUDE.md` + `contracts.py`
> are the source of truth for the contract shapes; this brief describes how Stage 1
> behaves and what "done" means. If anything conflicts, `CLAUDE.md` wins — ask, don't guess.

---

## Job

Turn ONE vague ESG question into ONE sharp, answerable question. Stage 1 **interrogates
only — it never answers the ESG question** (that is Stage 2). It uses **LLM reasoning
only; it sees NO Layer A / Layer B data** (only the loaded company's name + sector, for
scope).

The two demo "beats" that live here:
- **Thinks** — asks adaptive questions instead of dumping a dashboard.
- **Challenges** — pushes back when the user's framing is wrong for the sector.

## Owns / does not touch

- **Owns:** `stage1.py` only (the interrogation IP is `SYSTEM_PROMPT`).
- **Must not:** read `layer_a`/`layer_b`, answer the question, give buy/sell/hold or a
  score, or edit `core.py` / `contracts.py` (frozen).

## Input

- The Stage-1 conversation so far (`ss.s1_msgs`, this stage's OWN message list).
- `company` — used ONLY by `company_scope_note()` to anchor scope to the one loaded
  company (name + sector). Never its signals.

## Output baton — Contract A (`NarrowedQuestion`)

```json
{ "narrowed_question": "...", "mandate": "risk|return|compliance",
  "sector": "...", "horizon": "near_term|structural",
  "trail": [ {"axis": "...", "type": "...", "text": "...", "rationale": "..."} ] }
```

Each trail item carries a short **`rationale`** — Stage 1's visible chain-of-thought (*why
this axis now*, ≤ 12 words), shown beneath the question and recapped in Stage 3.

Built by `build_narrowed_question(trail, final_env)` → `contracts.coerce_narrowed_question`.
Saved to `fixtures/narrowed_question.json` as the baton Stage 2 consumes.

## The four ESG-native axes (every question probes exactly one)

1. **materiality** — does this issue even matter for THIS sector? (a bank's material
   issue is governance / data security, not carbon).
2. **time_horizon** — near-term catalyst, or structural concern?
3. **mandate** — risk, return, or compliance?
4. **blind_spot** — what would a static rating fail to see? **Drive here** — undisclosed
   AI / digital risk is where this tool's unique insight lives.

## Rules (enforced by `SYSTEM_PROMPT`)

- ONE question at a time; ADAPT each to the last answer; don't re-probe a settled axis.
- On `question`/`challenge` turns, `axis` MUST be one of the four (never null); null is
  only allowed on the final `narrowed` turn.
- CHALLENGE wrong framing inside the question (don't just accept it).
- **NARROW EAGERLY** — finish in 2–4 questions; when unsure whether to ask again or
  narrow, NARROW.
- Output is a JSON envelope only: `{axis, type, text, rationale, done, mandate, sector, horizon}`.
  Keep `text` to ONE sentence; `rationale` is a short CoT note (≤ 12 words).

## Key functions

- `ask_next(messages, turns, company)` → `(envelope, raw)`. Calls `core.call_llm(...,
  json_mode=True)`, parses defensively. Hits the cap (`core.MAX_QUESTIONS = 5`) →
  appends `FORCE_NARROW_NOTE` and forces `type="narrowed"`, guaranteeing termination.
- `build_narrowed_question(trail, final_env)` → Contract A.
- `render(ss, company)` — the Streamlit UI (all `st.*` calls confined here so the module
  imports cleanly in tests). Always offers **"→ I've said enough — narrow it & continue"**
  so the user can reach Stage 2 even if the model keeps asking.

## Defensive behaviour

- Unparseable JSON → graceful plain re-ask (`_parse_failed` flagged for the debug view).
- The cap + force-narrow guarantee Stage 1 always terminates with a Contract A.

## Acceptance

- Produces a valid Contract A every time; `selftest.py :: test_stage1_builder` passes.
- Live: narrows in 2–4 turns, challenges weak framing, steers toward the AI blind-spot,
  and **never** answers the ESG question.
