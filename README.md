# 🛰️ ASEAN ESG Momentum Radar

> **An AI that interrogates along ESG-native axes, then competes with the market's view —
> disagreeing with evidence, not picking.**

A hackathon ESG tool that does three things ("beats"):

- **Thinks** — asks adaptive questions instead of dumping a dashboard *(Stage 1)*
- **Challenges** — pushes back on your framing when it's wrong *(Stage 1)*
- **Competes** — takes a position against the stale rating using a signal the rating
  can't see *(Stage 2)* — **the differentiator**

It is **not** a stock picker. It disagrees with ratings; it never says buy / sell / hold,
and it never gives a score.

---

## How it works — a 3-stage relay

Each stage is a **fresh LLM agent** that hands the next only its verified output (the
"baton"). Stage 2 never sees Stage 1's chat — only the narrowed question.

```
vague question
  → Stage 1  Interrogate ......... emits a NarrowedQuestion   (LLM only, no data)
  → Stage 2  Compete over data ... emits a Stage2Answer        (LLM + the company data)
  → Stage 3  Render .............. the "market view vs reality" decision panel
```

The tool analyses **one company at a time**, loaded from a single local JSON file
(`data/hero_company.json`, currently the placeholder **DemoBank SG**). The interrogation
is anchored to that company.

---

## Quickstart

Requires **Python 3.8+** and a **DeepSeek API key** (`DEEPSEEK_API_KEY`).

### 1. Set up a virtual environment

Many Linux distros block `pip install` into system Python (PEP 668), so use a venv.

**fish** (this repo's shell):
```fish
python -m venv .venv
source .venv/bin/activate.fish
pip install -r requirements.txt
```

**bash / zsh:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your API key

```fish
set -x DEEPSEEK_API_KEY "sk-..."        # fish
```
```bash
export DEEPSEEK_API_KEY="sk-..."        # bash/zsh   (Windows: $env:DEEPSEEK_API_KEY="sk-...")
```

### 3. Run

```bash
streamlit run app.py
```

### Demo flow
1. Type **"Is this bank a good ESG investment?"** (or use a sidebar demo input).
2. Answer the 2–4 adaptive questions. The AI will challenge weak framing.
   - Stuck? Click **"→ I've said enough — narrow it & continue"** to jump to the answer.
3. Click **"Reason over the data →"** to get the four-line competing answer.

> 💡 The placeholder data's hidden signal is an **undisclosed AI-governance build-out**
> (+340% hiring, zero disclosure) ahead of the **MAS AI guidelines**. The sharpest demo
> steers the interrogation toward that AI/digital blind-spot.

---

## Configuration

| Env var | Required | Default | Notes |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | yes | — | Your DeepSeek key. Read from env only, never hard-coded. |
| `DEEPSEEK_MODEL` | no | `deepseek-v4-flash` | Override the model, e.g. `deepseek-chat`. |

All LLM calls go through `core.call_llm()` and use the DeepSeek endpoint
(`https://api.deepseek.com`, OpenAI-compatible).

---

## Project structure

```
core.py                  # shared: LLM client, defensive JSON parser, config, data loader
contracts.py             # the handoff data shapes (A: NarrowedQuestion, B: CompanyData, C: Stage2Answer)
app.py                   # Streamlit shell — wires the 3-stage relay
stage1.py                # interrogation agent
stage2.py                # competing reasoner
stage3.py                # render the decision panel
data/hero_company.json   # the one company under analysis (PLACEHOLDER values)
fixtures/                # sample contract outputs (used by tests / as batons)
selftest.py              # offline end-to-end check (no key, no network)
debug_llm.py             # one-shot probe of your DeepSeek endpoint
requirements.txt
```

---

## Testing & troubleshooting

**Offline self-test** (no API key or network needed) — validates the contracts and the
relay wiring with a mocked LLM:
```bash
python selftest.py
```

**Probe the live endpoint** — shows exactly what DeepSeek returns (useful if Stage 1/2
loop or come back empty):
```bash
python debug_llm.py      # needs DEEPSEEK_API_KEY set
```
- `CALL FAILED: NotFoundError` → wrong model name → set `DEEPSEEK_MODEL=deepseek-chat`
- `RAW REPR: ''` → empty content
- `PARSED: {...}` → JSON works; the app should too

**In-app debug** — tick **"🐞 Show raw model output"** in the sidebar to see each turn's
raw model response inline.

---

## Hard rules (by design)

1. No live data / no DB / no web fetch — one local JSON file only.
2. Never fabricate — the model reasons only over provided data; a missing fact is
   "unknown", never invented.
3. Placeholder data is **not** real facts about any real company.
4. Never give buy / sell / hold or a score.
5. The API key is read from the environment only.

---

*Built for a CGSI hackathon. Sample data is illustrative placeholder content.*
