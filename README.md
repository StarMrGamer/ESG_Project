# 🛰️ ASEAN ESG Momentum Radar

> **An AI that interrogates along ESG-native axes, then competes with the market's view —
> disagreeing with evidence, not picking.**

An ESG tool that does four things:

- **Thinks** — asks adaptive questions instead of dumping a dashboard, and shows *why* it
  asks each one (its chain of thought) *(Stage 1)*
- **Challenges** — pushes back on your framing when it's wrong *(Stage 1)*
- **Competes** — takes a position against the stale rating using the live signal + the
  historical trend the rating can't see, **grounded in real sources it fetches live (RAG)**
  *(Stage 2)* — **the differentiator**
- **Shows its work** — every verdict ships with a reasoning trail and its sources *(Stage 3)*

It is **not** a stock picker. It disagrees with ratings; it never says buy / sell / hold,
and it never gives a score.

---

## The command-center dashboard (ASEAN-focused)

The home screen is a 3-column monitoring dashboard over an ASEAN base universe — **52 ASEAN
companies with consistent ESG improvement 2019–2023** (the ESG Momentum foundation basket;
**MSCI ASEAN is the benchmark** it beat, 55.1% vs 6.4% — not the source of names). Each name carries
its **evidence** (`esg_basis` + `source_url` + `confidence`).

- **Left — Filters + Avg ESG.** Pick an Industry / Country; the **average ESG of the filtered set**
  recomputes live (change to *Banks* → you get the Banks average). Plus your Monitored list.
- **Center — the read.** Four pillar cards (avg **Environment / Social / Governance / Digital-AI**
  momentum), a 90-day momentum chart, **Hidden winners vs peer average**, and a **Classification**
  verdict (e.g. *HIDDEN WINNER* — never buy/sell/hold).
- **Right — the AI assistant.** It **controls the filters** by chat (*"show banks"*, *"Singapore"*,
  *"all ASEAN"*), adds/focuses companies, and drives the **Live signals** + **Why the rating may be
  wrong** panels for the focused name.
- **Click a card → deep dive** — the full Stage 1→2→3 relay (interrogate, or "⚔️ Compete now").

The aggregation lives in `metrics.py` (pure, tested), with three auto-detected **data modes**:

- **Numeric** — full per-company numbers (`esg_score`, `momentum.{environment,social,governance,
  digital_ai}`, `live_signals.…`) drive every panel exactly like the design.
- **Evidence** *(the real 52 today)* — no numbers yet, but each name carries an `esg_basis`, so the
  radar derives a **grounded ESG-leadership score (0–100)** + credential rows from the ratings the
  evidence actually cites (MSCI / DJSI / CDP A-List / FTSE4Good / Sustainalytics / GRESB / national
  ESG indices). Avg ESG-leadership, the ESG-leaders ranking and the classification all work;
  pillar momentum + live signals honestly say *"awaiting the alt-data feed."* **Nothing invented.**
- **Empty** — neither numbers nor evidence → *"awaiting data."*

A **Demo data** toggle swaps in `data/demo_universe.json` (fictional, fully numeric) to show the
full numeric vision. Pinned tickers persist in `data/watchlist.json`.

The slide's *"what's missing"* — AI adoption, alt-data (news/sentiment), real-time vs annual-report
lag — **is exactly our Layer B**: the foundation says these 52 improved on paper; the radar tests
that with the live signals the rating can't see.

---

## How it works — a 3-stage relay

Each stage is a **fresh LLM agent** that hands the next only its verified output (the
"baton"). Stage 2 never sees Stage 1's chat — only the narrowed question.

```
vague question
  → Stage 1  Interrogate ......... emits a NarrowedQuestion   (LLM only, no data; + visible CoT)
  → Stage 2  Compete over data ... emits a Stage2Answer        (LLM + company data + history + live RAG)
  → Stage 3  Render .............. verdict · chain-of-thought · history · sources
```

The tool analyses **one company at a time**, from one of three data sources (`datasource.py`):

- **🌐 Live** — type what you want to invest in (e.g. *"I want to invest in Nvidia"*). It
  identifies the company, fetches real documents, and the LLM builds an ESG profile
  **grounded only in those sources** — anything not found is `"unknown"`, never invented.
- **📤 Upload** — bring your own ESG data: `.json` is used as-is (a template is in the
  sidebar); `.csv`/`.txt` are read by the AI, grounded only in your file.
- **🧪 Sample** — the offline `data/hero_company.json` (DemoBank SG), a bulletproof demo /
  test fixture when there's no network or key.

The interrogation is anchored to whichever company is loaded.

**Live retrieval (RAG).** Before competing, Stage 2 fetches real external context for the
narrowed question from **DuckDuckGo** — its HTML/Lite search results plus the Instant-Answer
**AI summary**, no API key — and ranks the snippets with a pure-Python **TF-IDF** retriever
(`rag.py`). The agent *interprets* the AI summary; the top snippets ground the reasoning and
surface as clickable **sources**. All outbound HTTP is isolated in
`core.http_get()`; retrieval is **best-effort** — if the network is down it degrades to a
dataset-only run (toggle it off entirely with the sidebar **🌐 Live retrieval** switch). The
company *dataset* stays local and placeholder; the web only adds grounding context, never
fabricated company facts.

---

## Quickstart

Requires **Python 3.8+** and a **DeepSeek API key** (`DEEPSEEK_API_KEY`).

### 1. Set up a virtual environment

Use a virtual environment so dependencies stay isolated.

**Windows — PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> If activation is blocked with a script-execution error, run once:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

**Windows — Command Prompt (cmd):**
```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 2. Set your API key

**PowerShell:**
```powershell
$env:DEEPSEEK_API_KEY="sk-..."
```
**Command Prompt (cmd):**
```bat
set DEEPSEEK_API_KEY=sk-...
```

### 3. Run

```powershell
streamlit run app.py
```

### Demo flow
1. In the sidebar, pick a **Data source** (Live or Upload) and, optionally, **Dark mode**.
2. **Live:** type **"I want to invest in Nvidia"** (or tap an example). It builds a live ESG
   profile, then Agent 1 interrogates. **Upload:** drop a `.json`/`.csv`/`.txt`, click *Use
   this file*, then ask your question.
3. Answer the 2–4 adaptive questions (the AI challenges weak framing). Stuck? Click
   **"→ I've said enough — narrow it & continue"**.
4. Click **"Reason over the data →"**. It retrieves live sources (RAG), then returns the
   tightened competing answer — expand **🧠 Show the radar's reasoning** for the chain of
   thought, and scroll to the historical-trend strip and the **🔗 Sources** it cited.

> 💡 In the **🧪 Sample** scenario (sidebar → *Load sample*), the hidden signal is an
> **undisclosed AI-governance build-out** (+340% hiring, zero disclosure) ahead of the **MAS
> AI guidelines** — the sharpest demo steers the interrogation toward that AI/digital blind-spot.
> For **live** companies the differentiator is whatever real gap the fetched sources reveal.

---

## Configuration

| Env var | Required | Default | Notes |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | yes | — | Your DeepSeek key. Read from env only, never hard-coded. |
| `DEEPSEEK_MODEL` | no | `deepseek-v4-flash` | Override the model, e.g. `deepseek-chat`. |
| `ESG_HTTP_TIMEOUT` | no | `10` | Per-request fetch timeout (seconds) for live retrieval. |
| `ESG_LLM_TIMEOUT` | no | `30` | Per-request LLM timeout (seconds); stops a stalled endpoint hanging the UI. |
| `ESG_RAG_TOP_K` | no | `5` | How many retrieved snippets to ground the reasoning. |
| `ESG_RAG_MAX_DOCS` | no | `12` | Max documents fetched per query. |
| `ESG_RAG_TTL` | no | `21600` | Retrieval cache lifetime (seconds; default 6h). |
| `ESG_USER_AGENT` | no | _(set)_ | User-Agent sent on fetches. |

All LLM calls go through `core.call_llm()` (DeepSeek endpoint `https://api.deepseek.com`,
OpenAI-compatible); all web fetches go through `core.http_get()`. Live retrieval needs **no
API key** and caches to `.cache/` (git-ignored). No network? The app still runs — it just
reasons on the dataset alone.

---

## Project structure

```
core.py                  # shared: LLM client (call_llm), live-fetch (http_get), JSON parser, config, data loader
contracts.py             # the handoff data shapes (A: NarrowedQuestion, B: CompanyData, C: Stage2Answer)
rag.py                   # live retrieval (RAG): DuckDuckGo search + AI summary + TF-IDF rank
datasource.py            # build CompanyData LIVE (grounded) or load an UPLOAD (json/csv/txt)
app.py                   # Streamlit shell — control-panel sidebar, light/dark, wires the relay
stage1.py                # interrogation agent (+ visible chain-of-thought rationale)
stage2.py                # competing reasoner (+ RAG, history, CoT, sources)
stage3.py                # render: verdict · chain-of-thought · history · sources
data/hero_company.json   # SAMPLE only — offline-demo + test fixture (PLACEHOLDER values)
fixtures/                # sample contract outputs (used by tests / as batons)
selftest.py              # offline end-to-end check (no key, no network) — incl. RAG + datasource tests
debug_llm.py             # one-shot probe of your DeepSeek endpoint
.cache/                  # live-retrieval cache (auto-created, git-ignored)
requirements.txt
```

---

## Testing & troubleshooting

**Offline self-test** (no API key or network needed) — validates the contracts and the
relay wiring with a mocked LLM:
```powershell
python selftest.py
```

**Probe the live endpoint** — shows exactly what DeepSeek returns (useful if Stage 1/2
loop or come back empty):
```powershell
python debug_llm.py      # needs DEEPSEEK_API_KEY set
```
- `CALL FAILED: NotFoundError` → wrong model name → set a working model and re-run:
  PowerShell `$env:DEEPSEEK_MODEL="deepseek-chat"` · cmd `set DEEPSEEK_MODEL=deepseek-chat`
- `RAW REPR: ''` → empty content
- `PARSED: {...}` → JSON works; the app should too

**In-app debug** — tick **"🐞 Show raw model output"** in the sidebar to see each turn's
raw model response inline.

---

## Hard rules (by design)

1. Live fetch is allowed but **isolated** (`core.http_get`) and **best-effort** — a dead
   network degrades to a data-only run, never a crash. No DB.
2. Never fabricate — the model (and the live data builder) reason only over provided
   inputs/sources; a missing company fact is "unknown", never invented or estimated. Sources
   are the **real** retrieved URLs, never made up.
3. Data is labelled by origin: the **sample** (`hero_company.json`) is placeholder and never
   shown as real; **live**/**upload** data is real and labelled as such. Output is never advice.
4. Never give buy / sell / hold or a score.
5. The API key is read from the environment only.

---

*Built for a CGSI hackathon. Sample data is illustrative placeholder content.*
