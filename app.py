"""
app.py — Streamlit shell that wires the 3-stage relay.
======================================================
Runs the pipeline in sequence, each stage a FRESH DeepSeek agent handing the next only its
verified contract baton:

    a question about a company
      → data source ..................... LIVE fetch (grounded) or UPLOAD (json/csv/txt)
      → Stage 1 interrogates ............ emits NarrowedQuestion (Contract A)
      → Stage 2 competes over data ...... emits Stage2Answer    (Contract C)  [+ live RAG]
      → Stage 3 renders the answer ...... the decision panel

Stage 2 sees ONLY the NarrowedQuestion + CompanyData — never Stage 1's chat. This module
owns all st.session_state and the cross-cutting UX: the sidebar control panel, a light/dark
theme toggle, the live/upload data sources, a progress stepper, streaming status, and
friendly error recovery.

    pip install -r requirements.txt
    export DEEPSEEK_API_KEY="sk-..."
    streamlit run app.py
"""

import html
import json
import os
import re
import time

import streamlit as st

import contracts
import core
import datasource
import metrics
import universe
import stage1
import stage2
import stage3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")
SAMPLE_FILE = os.path.join(DATA_DIR, "hero_company.json")  # offline/demo safety net + test fixture
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")  # pinned tickers persist here (local, not a DB)

# Stage-2 progress phases: as each Contract-C key appears in the streamed JSON, advance the
# status. This narrates the multi-second wait against REAL progress (not a fake timer).
_S2_PHASES = [
    ("what_rating_sees", "📊 Reading the stale rating + its history…"),
    ("what_we_see", "🛰️ Checking the live signal the rating can't see…"),
    ("check_before_monday", "✅ Framing the check for your mandate…"),
    ("competes_summary", "⚔️ Forming the disagreement…"),
    ("reasoning", "🧠 Writing out its chain of thought…"),
]

_RAG_LABELS = {
    "live": "🦆 Retrieved {n} live source(s) from DuckDuckGo (+ AI summary when available).",
    "cache": "🗃️ Loaded {n} DuckDuckGo source(s) from cache.",
    "offline": "📴 Couldn't fetch usable DuckDuckGo sources for this query — reasoning on the data.",
    "disabled": "🔌 Live retrieval is off — reasoning on the data.",
}

# Transient UI flags (not relay batons) that the Reset buttons should also clear.
_TRANSIENT = ("pending_user_input", "s2_retry", "company_draft", "live_question")


# --------------------------------------------------------------------------- #
#  THEME  (best-effort runtime light/dark via CSS injection)
# --------------------------------------------------------------------------- #
# Token palette from the design mockup. Both themes share ONE chrome + component
# stylesheet; only these CSS *variables* swap, so the command-center cards now follow
# the theme (they used to be hard-coded navy regardless of light/dark).
_DARK_VARS = {
    "bg": "#0a0e16", "bg2": "#0c1220", "panel": "#121a29", "inset": "#0e1626",
    "border": "rgba(148,163,184,.14)", "borderStrong": "rgba(148,163,184,.26)",
    "text": "#e7ebf3", "muted": "#8b97ab", "faint": "#5d6982",
    "pos": "#35d39a", "posbg": "rgba(53,211,154,.12)",
    "neg": "#f4737d", "negbg": "rgba(244,115,125,.12)",
    "amber": "#f5a524", "amberbg": "rgba(245,165,36,.13)", "blue": "#5e9cf6",
}
_LIGHT_VARS = {
    "bg": "#eef1f5", "bg2": "#e9edf2", "panel": "#ffffff", "inset": "#f4f7fa",
    "border": "rgba(15,23,42,.10)", "borderStrong": "rgba(15,23,42,.20)",
    "text": "#0f1729", "muted": "#56627a", "faint": "#8b95a7",
    "pos": "#0e9f6e", "posbg": "rgba(14,159,110,.10)",
    "neg": "#e0455b", "negbg": "rgba(224,69,91,.09)",
    "amber": "#bd7a0e", "amberbg": "rgba(189,122,14,.12)", "blue": "#2f6fe0",
}

_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500;600&"
    "family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');"
)


def _vars_css(theme):
    """Emit the per-theme CSS-variable block (+ the IBM Plex import)."""
    t = _LIGHT_VARS if theme == "light" else _DARK_VARS
    block = ";".join(f"--r-{k}:{v}" for k, v in t.items())
    return f"<style>{_FONT_IMPORT}\n:root{{{block};}}</style>"

# Streamlit-chrome overrides — ONE sheet for both themes, driven entirely by the
# --r-* variables (which swap per theme). IBM Plex everywhere; widgets retinted to the
# mockup's panel/inset/accent tokens.
_CHROME_CSS = """
<style>
/* ---- base canvas + typography ---- */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"]{
  font-family:'IBM Plex Sans',-apple-system,system-ui,sans-serif;}
[data-testid="stAppViewContainer"], [data-testid="stMain"]{background:var(--r-bg);}
[data-testid="stHeader"]{background:transparent;height:0;}
/* Reclaim the canvas: drop Streamlit's default max-width cap + the large top/side padding
   so the dashboard fills the screen edge-to-edge instead of floating in a centered column. */
[data-testid="stMainBlockContainer"], [data-testid="stMain"] .block-container{
  max-width:100% !important;padding:1rem 1.6rem 1.2rem !important;}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:1.2rem;}
[data-testid="stSidebar"]{background:var(--r-bg2);border-right:1px solid var(--r-border);}
[data-testid="stAppViewContainer"], [data-testid="stSidebar"]{color:var(--r-text);}
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] label, [data-testid="stWidgetLabel"] *,
[data-testid="stSidebar"] *{color:var(--r-text) !important;}
h1,h2,h3,h4,h5,h6{color:var(--r-text) !important;letter-spacing:-.01em;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, small{color:var(--r-muted) !important;}
hr,[data-testid="stDivider"]{border-color:var(--r-border) !important;}
/* ---- buttons — secondary = inset pill, primary = mint accent ---- */
.stButton>button, [data-testid="stBaseButton-secondary"]{
  background:var(--r-inset) !important;color:var(--r-text) !important;
  border:1px solid var(--r-border) !important;border-radius:10px !important;
  font-weight:600 !important;transition:all .15s;white-space:nowrap;}
.stButton>button p{white-space:nowrap;}
.stButton>button:hover, [data-testid="stBaseButton-secondary"]:hover{
  border-color:var(--r-pos) !important;color:var(--r-pos) !important;}
[data-testid="stBaseButton-primary"]{background:var(--r-pos) !important;color:#06231a !important;
  border:0 !important;border-radius:10px !important;font-weight:700 !important;}
[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.06);color:#06231a !important;}
/* ---- inputs / chat / selects / uploader ---- */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"]>div{
  background:var(--r-inset) !important;color:var(--r-text) !important;border-radius:10px;}
[data-testid="stChatInput"]{background:var(--r-bg2) !important;}
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"]{background:var(--r-inset) !important;border-radius:10px !important;}
[data-testid="stChatInput"] textarea{background:var(--r-inset) !important;
  color:var(--r-text) !important;-webkit-text-fill-color:var(--r-text) !important;}
[data-testid="stChatInput"] textarea::placeholder,
[data-baseweb="input"] input::placeholder{
  color:var(--r-faint) !important;-webkit-text-fill-color:var(--r-faint) !important;}
[data-testid="stFileUploaderDropzone"]{background:var(--r-inset) !important;}
/* ---- metrics / expanders / code / notifications / chat msgs ---- */
[data-testid="stMetric"]{background:var(--r-panel);border:1px solid var(--r-border);
  border-radius:12px;padding:.55rem .75rem;}
[data-testid="stMetricValue"]{color:var(--r-text) !important;font-family:'IBM Plex Mono',monospace;}
[data-testid="stMetricLabel"] *{color:var(--r-muted) !important;}
[data-testid="stExpander"]{background:var(--r-panel);border:1px solid var(--r-border);border-radius:12px;}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary *{color:var(--r-text) !important;}
code, pre{background:var(--r-inset) !important;color:var(--r-text) !important;
  font-family:'IBM Plex Mono',monospace !important;}
[data-testid="stNotification"]{background:var(--r-panel) !important;}
[data-testid="stChatMessage"]{background:var(--r-panel);border:1px solid var(--r-border);border-radius:12px;}
/* ---- scrollbars + accessibility floor ---- */
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--r-border);border-radius:8px}
:focus-visible{outline:2px solid var(--r-pos);outline-offset:2px;border-radius:6px;}
@media (prefers-reduced-motion: reduce){*{transition:none !important;animation:none !important;}}
</style>
"""

def _inject_css(theme):
    """Inject the full sheet once per run: per-theme variables → chrome → components.
    Because every component colour is a --r-* variable, the cards follow light/dark."""
    st.markdown(_vars_css(theme), unsafe_allow_html=True)
    st.markdown(_CHROME_CSS, unsafe_allow_html=True)
    st.markdown(_COMPONENT_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  SHARED UI BITS
# --------------------------------------------------------------------------- #
def _stepper(ss):
    """A simple Interrogate → Compete → Answer progress bar with the current step lit."""
    if ss.get("answer") is not None:
        active = 2
    elif ss.get("s1_done"):
        active = 1
    else:
        active = 0
    labels = ["Interrogate", "Compete", "Answer"]
    cells = []
    for i, label in enumerate(labels):
        if i < active:
            cells.append(f":green[✅ {label}]")
        elif i == active:
            cells.append(f":violet[**🔵 {label}**]")
        else:
            cells.append(f":gray[⚪ {label}]")
    st.markdown("  →  ".join(cells))


_ORIGIN_BADGE = {"live": "🌐 Live (fetched)", "upload": "📤 Uploaded", "sample": "🧪 Sample",
                 "dataset": "🗃️ Dataset"}
_ORIGIN_DISCLAIMER = {
    "live": "Built live from public sources — fields not found are shown as “unknown”, never "
            "invented. Not investment advice.",
    "upload": "Built from your uploaded data. Not investment advice.",
    "sample": "⚠️ Illustrative sample — placeholder data, not real facts about any real company.",
    "dataset": "Built from pre-scored local dataset values (not a live fetch). Not investment advice.",
}


def _company_header(company):
    """A compact subject header once a company is loaded, with an honest origin badge."""
    origin = company.get("_origin", "sample")
    st.markdown(f"#### {company.get('company', '—')} · `{company.get('ticker', '—')}`")
    st.caption(f"{company.get('sector', '—')}  ·  {_ORIGIN_BADGE.get(origin, '')}")
    st.caption(_ORIGIN_DISCLAIMER.get(origin, ""))

    # Tell the user EARLY when a live profile is sparse (so a thin Stage 2 isn't a surprise).
    if origin == "live" and company.get("_build_status") in ("thin", "offline"):
        msg = "⚠️ This live profile is **sparse** — public sources didn't yield much"
        if company.get("_build_status") == "offline":
            msg += " and live retrieval couldn't reach the network"
        msg += (". Grounded-only mode marks unverified facts “unknown”, so the answer may be "
                "limited. Try again, switch to **📤 Upload**, or use the **🎬 offline sample**.")
        if company.get("_build_error"):
            msg += f"\n\n↳ retrieval reason: _{company['_build_error']}_"
        st.warning(msg)


def _run_stage2(ss, nq, company):
    """Run Stage 2 in two visible steps — live retrieval (RAG), then the competing reason."""
    ok = False
    try:
        use_rag = bool(ss.get("rag_enabled", True))
        top_k = int(ss.get("rag_top_k", 5))
        with st.status("🌐 Retrieving live ESG context (RAG)…", expanded=False) as status:
            ctx = stage2.retrieve_context(nq, company, use_rag=use_rag, k=top_k)
            n = len(ctx.get("snippets", []))
            label = _RAG_LABELS.get(ctx.get("status"), "{n} source(s).").format(n=n)
            is_off = ctx.get("status") == "offline"
            # Offline retrieval is a soft degrade (we still reason on the data), not a hard
            # error — keep the status calm but show the reason.
            status.update(label=label, state="complete")
            if is_off and ctx.get("error"):
                st.caption(f"↳ {ctx['error']}")

        with st.status("⚔️ Competing against the stale rating…", expanded=True) as status:
            seen = set()

            def on_delta(_delta, accumulated):
                for key, label in _S2_PHASES:
                    if key not in seen and f'"{key}"' in accumulated:
                        seen.add(key)
                        status.update(label=label)

            ss.answer = stage2.reason(nq, company, on_delta=on_delta, context=ctx)
            status.update(label="Done — here's where we compete.", state="complete")
        ok = True
    except core.LLMConfigError as e:
        st.error(str(e))
    except Exception as e:  # noqa: BLE001 — friendly recovery, never a raw traceback.
        st.warning("⚠️ Something went wrong reaching the model — usually a network blip or a "
                   "wrong model name (try setting DEEPSEEK_MODEL).")
        with st.expander("Details"):
            st.code(f"{type(e).__name__}: {e}")
        if st.button("↻ Retry", key="s2_retry_btn"):
            ss["s2_retry"] = True
            st.rerun()
    if ok:
        st.rerun()


_RELAY_KEYS = ("company", "s1_msgs", "s1_trail", "s1_turns", "s1_done", "narrowed_q", "answer")


def _reset(ss):
    """Clear the current analysis (relay batons + deep-dive) back to the dashboard. The
    monitored watchlist + built snapshots are PRESERVED — 'New' restarts the question, not
    the whole board."""
    for _k in _RELAY_KEYS:
        ss.pop(_k, None)
    for _k in list(_TRANSIENT):
        ss.pop(_k, None)
    ss.pop("skip_interrogation", None)
    ss.view = "dashboard"
    ss.active_ticker = None
    ss.compare_tickers = []
    st.rerun()


# --------------------------------------------------------------------------- #
#  DASHBOARD — watchlist persistence, snapshots, monitoring board, universe grid
# --------------------------------------------------------------------------- #
def _load_watchlist():
    """Load pinned tickers from disk (local JSON — survives a restart). Never raises."""
    try:
        with open(WATCHLIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [t for t in (data.get("tickers") or []) if isinstance(t, str)]
    except (OSError, ValueError):
        return []


def _save_watchlist(tickers):
    """Persist pinned tickers (de-duped, order-preserving). Best-effort; never load-bearing."""
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"tickers": list(dict.fromkeys(tickers))}, f, indent=2)
    except OSError:
        pass


def _band_emoji(snap):
    b = (snap.get("band") or "").strip().lower()
    if not b:
        return "⚪"
    if "negli" in b or "low" in b or b in ("aaa", "aa"):
        return "🟢"
    if "med" in b or b in ("a", "bbb"):
        return "🟡"
    if "high" in b or b in ("bb", "b"):
        return "🟠"
    if "sever" in b or b == "ccc":
        return "🔴"
    return "⚪"


def _known(v):
    return bool(v) and str(v).strip().lower() not in ("", "unknown")


def _is_simplified(ss):
    """True in Simplified view (plain-language); False in In-Depth (full analyst view). [1.1]"""
    return ss.get("ui_mode", "Simplified") == "Simplified"


def _pin(ss, company):
    """Compute a snapshot for an already-built CompanyData and add it to the monitored board."""
    snap = datasource.snapshot_from_company(company)
    tk = company.get("ticker") or company.get("_constituent_ticker") or snap.get("ticker") or "unknown"
    ss.snapshots[tk] = {"company": company, "snap": snap, "answer": None, "narrowed_q": None,
                        "built_at": time.time()}     # [1.11] honest freshness clock on a real build
    ss.data_built_at = ss.snapshots[tk]["built_at"]
    if tk not in ss.watchlist:
        ss.watchlist.append(tk)
    _save_watchlist(ss.watchlist)
    return tk


def _unpin(ss, ticker):
    ss.watchlist = [t for t in ss.watchlist if t != ticker]
    ss.snapshots.pop(ticker, None)
    _save_watchlist(ss.watchlist)


def _build_and_pin_constituent(ss, constituent):
    """Live-build a grounded snapshot for a base-DB constituent, then pin it. Friendly on error."""
    try:
        with st.spinner(f"🛰️ Building a live ESG snapshot for {constituent['company']} "
                        f"({constituent.get('country','ASEAN')})…"):
            company, _meta = datasource.build_company_from_constituent(
                constituent, use_rag=bool(ss.get("rag_enabled", True)), k=int(ss.get("rag_top_k", 5))
            )
    except core.LLMConfigError as e:
        st.error(str(e))
        return None
    except Exception as e:  # noqa: BLE001 — a live flop must not break the board.
        st.warning("⚠️ Couldn't build that snapshot just now — usually a network blip or a wrong "
                   "model name (try setting DEEPSEEK_MODEL).")
        with st.expander("Details"):
            st.code(f"{type(e).__name__}: {e}")
        return None
    return _pin(ss, company)


def _ensure_snapshot(ss, constituent):
    """Return the ticker of a constituent's snapshot, building+pinning it first if needed.
    Constituents that already carry NUMBERS (demo / pre-scored) get a Contract B built locally
    (no network); evidence-only real names go through the ASEAN-scoped live builder."""
    tk = constituent.get("ticker") or constituent.get("id")
    if tk in ss.snapshots:
        return tk
    if metrics.has_numbers([constituent]):
        # demo = illustrative "sample"; real pre-scored numbers = "dataset" (locally computed, NOT
        # a live fetch) — never label a no-network numeric build "live (fetched from public sources)".
        company = datasource.company_from_numeric(
            constituent, origin="sample" if ss.get("demo_mode") else "dataset")
        return _pin(ss, company)
    return _build_and_pin_constituent(ss, constituent)


def _launch_relay(ss, ticker, mode):
    """Open the deep-dive page and run the 3-stage relay in `mode` ('compete' | 'interrogate')."""
    entry = ss.snapshots.get(ticker)
    if not entry:
        return
    ss.company = entry["company"]
    ss.active_ticker = ticker
    ss.view = "deep_dive"
    for _k in ("s1_msgs", "s1_trail", "s1_turns", "s1_done", "narrowed_q", "answer"):
        ss.pop(_k, None)
    ss.pop("skip_interrogation", None)
    if mode == "compete":                       # skip Stage 1 — land on the competing read
        ss.narrowed_q = _default_nq(entry["company"])
        ss.s1_done = True
        ss.skip_interrogation = True
    st.rerun()


def _add_live_company(ss, text):
    """Build a LIVE company by name (not in the 52) and pin it — ASEAN-only gate. Returns
    (ticker, error). The relay then runs on it like any monitored name."""
    try:
        with st.spinner(f"🌐 Building a live ESG profile for “{text}” (ASEAN check)…"):
            company, _meta = datasource.build_live_company(
                text, use_rag=bool(ss.get("rag_enabled", True)), k=int(ss.get("rag_top_k", 5)))
    except core.LLMConfigError as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001 — keep a live flop friendly.
        return None, f"Couldn't build “{text}” live ({type(e).__name__})."
    country = (company.get("_country") or "").strip()
    asean = [c.lower() for c in universe.ASEAN_COUNTRIES]
    if country and country.lower() != "unknown" and country.lower() not in asean:
        return None, (f"{company.get('company', text)} looks **{country}**-listed — this radar is "
                      "ASEAN-only (Singapore, Malaysia, Indonesia, Thailand, Philippines).")
    return _pin(ss, company), None


def _default_nq(company):
    """A sensible default NarrowedQuestion so a deep dive can 'compete' without interrogation.

    The '2019–2023 improvement' clause is grounded ONLY for the foundation-basket constituents
    (selected for that very trend; they carry a `_constituent_ticker`). For arbitrary live-added or
    uploaded names we must NOT assert an unverified trend (HARD RULE 2) — frame it generically."""
    name = company.get("company", "this company")
    grounded = _known(company.get("_constituent_ticker"))
    if grounded:
        q = (f"Is {name}'s ESG profile as solid as its static rating and 2019–2023 improvement "
             "imply, once you weigh the live AI / news / behaviour signals the rating can't see?")
    else:
        q = (f"Is {name}'s ESG profile as solid as its static rating implies, once you weigh the "
             "live AI / news / behaviour signals the rating can't see?")
    return contracts.coerce_narrowed_question({
        "narrowed_question": q,
        "mandate": "risk",
        "sector": company.get("sector", "unknown"),
        "horizon": "near_term",
        "trail": [],
    })


def _open_deep_dive(ss, ticker):
    """Switch to the deep-dive view for a monitored company, restoring any cached answer."""
    entry = ss.snapshots.get(ticker)
    if not entry:
        return
    ss.company = entry["company"]
    ss.active_ticker = ticker
    ss.view = "deep_dive"
    for _k in ("s1_msgs", "s1_trail", "s1_turns", "s1_done", "narrowed_q", "answer"):
        ss.pop(_k, None)
    ss.pop("skip_interrogation", None)
    if entry.get("answer") is not None:          # revisit is instant — reuse the computed read
        ss.answer = entry["answer"]
        ss.narrowed_q = entry.get("narrowed_q") or _default_nq(entry["company"])
        ss.s1_done = True
        ss.skip_interrogation = True
    st.rerun()


def _render_snapshot_metrics(snap):
    """The five-metric monitoring strip at the top of a deep dive."""
    ar = snap.get("arrows", {})
    cols = st.columns(5)
    cols[0].metric("ESG rating (Layer A)", snap.get("rating") if _known(snap.get("rating")) else "unknown",
                   help="The stale static rating. Lower = better for a Sustainalytics risk score.")
    cols[1].metric("Risk band", f'{_band_emoji(snap)} {snap.get("band") or "—"}',
                   help="Parsed from the rating string.")
    cols[2].metric("Momentum E·S·G", f'{ar.get("E","·")} {ar.get("S","·")} {ar.get("G","·")}',
                   help="Layer B direction per pillar (▲ improving · — flat · ▼ declining · · unknown).")
    cols[3].metric("🚩 Red flags", snap.get("red_flags", 0),
                   help="Live ESG controversies retrieved (leads to check, not verdicts).")
    cols[4].metric("Coverage", f'{snap.get("coverage", 0)}/{snap.get("coverage_total", 10)}',
                   help="How many of the 10 monitored signals are actually grounded.")


# --- command center: CSS + small helpers ----------------------------------- #
_COMPONENT_CSS = """
<style>
/* ---- Header (logo · title · meta · status pill) ---- */
.cc-hdr-wrap{display:flex;align-items:center;gap:13px;min-width:0;}
.cc-title2{font:700 18px/1.1 'IBM Plex Sans';color:var(--r-text);letter-spacing:-.01em;}
.cc-meta{font:400 12px/1.3 'IBM Plex Sans';color:var(--r-muted);margin-top:3px;}
.cc-live{display:inline-block;border-radius:20px;padding:5px 12px;font:700 12px/1 'IBM Plex Sans';
  letter-spacing:.03em;white-space:nowrap;}
.cc-leftpill{display:inline-block;background:var(--r-inset);border:1px solid var(--r-border);
  border-radius:9px;padding:7px 12px;font:600 12px/1 'IBM Plex Mono';color:var(--r-text);}
.cc-fresh{font:500 11px/1.3 'IBM Plex Mono';color:var(--r-muted);margin-top:5px;white-space:nowrap;}
.cc-tag-illus{background:var(--r-amberbg);color:var(--r-amber);font-size:10px;padding:1px 6px;
  border-radius:6px;margin-left:6px;font-weight:600;text-transform:none;letter-spacing:0;}
/* ---- Section headings ---- */
.cc-h{color:var(--r-text);font:600 15px/1.2 'IBM Plex Sans';margin:0 0 6px;}
.cc-muted{color:var(--r-muted);font-size:12px;margin-top:4px;}
/* ---- Generic card ---- */
.cc-card{background:var(--r-panel);border:1px solid var(--r-border);border-radius:14px;
  padding:13px 16px;margin-bottom:10px;}
/* ---- KPI strip (label → big number → trend, stacked to survive the narrow center) ---- */
.cc-kpi{background:var(--r-panel);border:1px solid var(--r-border);border-radius:13px;
  padding:12px 16px;overflow:hidden;}
.cc-kpi.cc-fast{background:var(--r-amberbg);border-color:var(--r-amber);}
.cc-kpi-label{font:600 10px/1.2 'IBM Plex Sans';letter-spacing:.04em;text-transform:uppercase;
  color:var(--r-muted);white-space:nowrap;}
.cc-kpi.cc-fast .cc-kpi-label{color:var(--r-amber);}
.cc-kpi-val{font:700 26px/1.1 'IBM Plex Mono';letter-spacing:-.02em;color:var(--r-text);
  margin:7px 0 3px;white-space:nowrap;}
.cc-kpi.cc-fast .cc-kpi-val{color:var(--r-amber);}
.cc-kpi-trend{font:500 11px/1.2 'IBM Plex Sans';color:var(--r-muted);white-space:nowrap;}
.cc-kpi.cc-fast .cc-kpi-trend{color:var(--r-amber);}
/* Legacy vertical-pill classes (still used by evidence-mode coverage cards) */
.cc-pill{background:var(--r-panel);border:1px solid var(--r-border);border-radius:14px;
  padding:13px 16px;margin-bottom:10px;}
.cc-pill.cc-fast{border:2px solid var(--r-amber);}
.cc-pill-h{color:var(--r-muted) !important;font:600 11px/1 'IBM Plex Sans' !important;
  text-transform:uppercase !important;letter-spacing:.08em;margin-bottom:5px;}
.cc-big{font:700 32px/1.1 'IBM Plex Mono' !important;margin:0;letter-spacing:-.01em;}
.cc-pill.cc-fast .cc-big{color:var(--r-amber) !important;}
.cc-pill-sub{color:var(--r-muted) !important;font-size:11px !important;margin-top:6px;}
/* ---- Colour semantics ---- */
.cc-pos{color:var(--r-pos);} .cc-neg{color:var(--r-neg);}
.cc-flat{color:var(--r-text);} .cc-warn{color:var(--r-amber);}
/* ---- Horizontal bar panel (hidden winners / evidence leaders) ---- */
.cc-hwwrap{background:var(--r-panel);border:1px solid var(--r-border);border-radius:14px;padding:10px 14px;}
.cc-hw{display:flex;align-items:center;gap:10px;margin:6px 0;min-height:22px;}
.cc-hw-name{flex:0 0 44%;text-align:right;padding-right:10px;color:var(--r-text);
  font:600 12.5px/1.3 'IBM Plex Sans';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.cc-new{background:var(--r-posbg);color:var(--r-pos);font-style:normal;font-size:10px;
  padding:1px 5px;border-radius:6px;margin-left:5px;white-space:nowrap;}
.cc-hw-track{flex:1;background:var(--r-inset);border-radius:6px;height:11px;overflow:hidden;}
.cc-hw-fill{height:11px;border-radius:6px;}
.cc-hw-fill.cc-pos{background:var(--r-pos);}
.cc-hw-fill.cc-neg{background:var(--r-neg);}
.cc-hw-fill.cc-tier-mid{background:var(--r-amber);}
.cc-hw-fill.cc-tier-low{background:var(--r-blue);}
.cc-hw-val{flex:0 0 52px;text-align:right;font:700 13px/1 'IBM Plex Mono';}
/* ---- Classification box (mockup: tinted bg + accent left-border) ---- */
.cc-class{border-radius:14px;padding:13px 16px;margin-top:6px;border:1px solid var(--r-pos);
  border-left:4px solid var(--r-pos);background:var(--r-posbg);}
.cc-class-good{border-color:var(--r-pos);border-left-color:var(--r-pos);background:var(--r-posbg);}
.cc-class-bad{border-color:var(--r-neg);border-left-color:var(--r-neg);background:var(--r-negbg);}
.cc-class-neutral{border-color:var(--r-blue);border-left-color:var(--r-blue);background:var(--r-panel);}
.cc-class-h{font:600 11px/1 'IBM Plex Sans';color:var(--r-muted);
  text-transform:uppercase;letter-spacing:.1em;}
.cc-class-h b{color:var(--r-pos);font:700 14px/1 'IBM Plex Sans';letter-spacing:.02em;text-transform:none;}
.cc-class-bad .cc-class-h b{color:var(--r-neg);}
.cc-class-neutral .cc-class-h b{color:var(--r-blue);}
.cc-class-line{color:var(--r-text);font:400 13px/1.55 'IBM Plex Sans';margin-top:8px;}
.cc-chips{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 4px;}
.cc-chip{display:inline-block;background:var(--r-inset);color:var(--r-text);
  font-size:11px;padding:2px 8px;border-radius:10px;white-space:nowrap;}
/* ---- Live-signal rows ---- */
.cc-sigwrap{background:var(--r-panel);border:1px solid var(--r-border);border-radius:14px;padding:4px 14px;}
.cc-sig{display:flex;justify-content:space-between;align-items:center;padding:11px 0;
  border-bottom:1px solid var(--r-border);font:400 13px/1 'IBM Plex Sans';color:var(--r-text);}
.cc-sig:last-child{border-bottom:0;} .cc-sig b{font:600 14px/1 'IBM Plex Mono';}
/* ---- "Why the rating may be wrong" prose panel ---- */
.cc-panel-body{background:var(--r-panel);border:1px solid var(--r-border);border-radius:14px;
  padding:13px 15px;color:var(--r-text);font:400 13px/1.6 'IBM Plex Sans';}
/* ---- Chat bubbles ---- */
.cc-bubble{border-radius:10px;padding:7px 11px;margin:5px 0;font:400 13px/1.4 'IBM Plex Sans';}
.cc-bubble-u{background:var(--r-inset);color:var(--r-text);border:1px solid var(--r-border);}
.cc-bubble-a{background:var(--r-posbg);color:var(--r-text);border:1px solid var(--r-pos);}
/* ---- Chart heading row ---- */
.cc-chart-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:2px;}
.cc-chart-title{font:600 16px/1 'IBM Plex Sans';color:var(--r-text);}
.cc-chart-sub{font:500 11.5px/1 'IBM Plex Mono';color:var(--r-muted);}
</style>
"""


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _sign_class(v):
    return "cc-pos" if (v is not None and v > 0) else ("cc-neg" if (v is not None and v < 0) else "cc-flat")


def _go():
    try:
        import plotly.graph_objects as go
        return go
    except Exception:  # noqa: BLE001 — chart is optional; we fall back to st.line_chart.
        return None


def _short_sector(s):
    s = s or "All"
    return "All industries" if s == "All" else s.split("—")[-1].strip()


# --- command center: chatbot intent (controls the filters + focus) ---------- #
def _match_sector(low, path):
    """Map words in a chat line onto a real sector option (token-based, so 'DemoBank' ≠ Banks)."""
    qtoks = set(re.findall(r"[a-z]+", low))
    syn = {"banks": ("bank",), "telecom": ("telco", "telcos", "mobile"),
           "estate": ("property", "realty"), "energy": ("power", "renewables", "renewable", "solar"),
           "consumer": ("staples", "food", "retail"), "technology": ("tech", "chip", "semiconductor")}
    for s in universe.sectors(path):
        words = [w for w in re.findall(r"[a-z]+", s.lower())
                 if len(w) > 3 and w not in ("services", "communication")]
        for w in words:
            if w in qtoks or any(syk in qtoks for syk in syn.get(w, ())):
                return s
    return None


# Words that ask the assistant to RUN the 3-stage relay (and which mode).
_RELAY_TRIGGERS = ("analyse", "analyze", "deep dive", "deep-dive", "deepdive", "run esg",
                   "esg analysis", "esg on", "3 stage", "three stage", "relay", "compete",
                   "interrogate", "ask about", "challenge", "assess", "evaluate", "question")
_INTERROGATE_TRIGGERS = ("interrogate", "ask about", "challenge", "question")
_RELAY_STRIP = ("run an esg analysis on", "run esg analysis on", "esg analysis on", "run esg on",
                "run the 3 stages on", "3 stage relay on", "deep dive on", "deep-dive on",
                "compete against", "compete with", "compete on", "ask about", "analyse", "analyze",
                "deep dive", "deep-dive", "deepdive", "run esg", "esg analysis", "esg on",
                "interrogate", "challenge", "evaluate", "assess", "relay", "compete", "question",
                "please", "run ")


def _relay_request(low):
    """Detect a 3-stage-relay command in a chat line; returns 'compete' | 'interrogate' | None."""
    if not any(v in low for v in _RELAY_TRIGGERS):
        return None
    return "interrogate" if any(v in low for v in _INTERROGATE_TRIGGERS) else "compete"


def _strip_relay_verbs(text):
    """Remove the relay verbs so what's left is the company name ('analyze DBS' -> 'DBS')."""
    out = text
    for v in _RELAY_STRIP:
        out = re.sub(re.escape(v), " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip(" ?.")


def _chat_act(ss, text, path):
    """The AI assistant: parse a line into RELAY / filter / focus / add actions and log a reply."""
    t = (text or "").strip()
    if not t:
        return
    low = t.lower()
    simple = _is_simplified(ss)                       # [2.2] plain-language vs analyst copy
    ss.chat_log.append({"role": "user", "text": t})

    # 1) Run the 3-stage ESG relay (two modes). Resolves a constituent, else live-builds an ASEAN
    #    name, then opens the deep-dive page in the chosen mode.
    mode = _relay_request(low)
    if mode:
        stripped = _strip_relay_verbs(t)
        # "analyze this / it" -> the currently focused company
        if stripped.lower() in ("this", "it", "focused", "the company", "") and ss.get("focus_ticker"):
            ft = ss.focus_ticker
            tk = ft if ft in ss.snapshots else _ensure_snapshot(ss, universe.get(ft, path) or {})
            if tk:
                ss.chat_log.append({"role": "assistant",
                                    "text": metrics.chat_relay_msg(None, mode, simple, focused=True)})
                _launch_relay(ss, tk, mode)
                return
        c = universe.resolve(stripped or t, path)
        if c:
            tk = _ensure_snapshot(ss, c)
            if tk:
                ss.chat_log.append({"role": "assistant",
                                    "text": metrics.chat_relay_msg(c["company"], mode, simple)})
                _launch_relay(ss, tk, mode)        # switches to the deep-dive page (reruns)
            return
        if stripped and len(stripped) >= 2 and not _match_sector(stripped.lower(), path) \
                and stripped.lower() not in ("all", "asean", "everything", "this", "it", "company"):
            tk, err = _add_live_company(ss, stripped)
            if tk:
                nm = ss.snapshots[tk]["snap"]["company"]
                ss.chat_log.append({"role": "assistant",
                                    "text": metrics.chat_relay_msg(nm, mode, simple, live=True)})
                _launch_relay(ss, tk, mode)
            else:
                ss.chat_log.append({"role": "assistant",
                                    "text": err or metrics.chat_cant_analyse_msg(stripped, simple)})
            return
        ss.chat_log.append({"role": "assistant", "text": metrics.chat_relay_help(simple)})
        return

    bits = []

    if any(k in low for k in ("all asean", "all countries", "whole asean", "everywhere", "any country")):
        ss.flt_country = "All"
        bits.append("all ASEAN markets")
    else:
        for cn in universe.countries(path):
            if cn.lower() in low:
                ss.flt_country = cn
                bits.append(cn)
                break

    if any(k in low for k in ("all industries", "all sectors", "every industry", "any industry")):
        ss.flt_sector = "All"
        bits.append("all industries")
    else:
        sec = _match_sector(low, path)
        if sec:
            ss.flt_sector = sec
            bits.append(_short_sector(sec))

    comp = universe.resolve(t, path)
    explicit = low.startswith(("add ", "monitor ", "track ", "watch ", "focus ", "show me "))
    if comp and (explicit or not bits):
        ss.focus_ticker = comp["ticker"]  # the "new" badge is derived from this, not a cache mutation
        peers = [c for c in universe.constituents(path) if c["sector"] == comp["sector"]]
        avg, _ = metrics.average_esg(peers)
        d = metrics.num((comp.get("momentum") or {}).get("digital_ai"))
        if not ss.get("demo_mode") and comp["ticker"] not in ss.watchlist:
            _build_and_pin_constituent(ss, comp)      # real mode: also build a live snapshot
        ss.chat_log.append({"role": "assistant",
                            "text": metrics.chat_focus_msg(comp["company"], _short_sector(comp["sector"]),
                                                           simple, avg=avg,
                                                           digital_pct=metrics.fmt_pct(d))})
        return

    if bits:
        ss.chat_log.append({"role": "assistant", "text": metrics.chat_filter_msg(bits, simple)})
    else:
        ss.chat_log.append({"role": "assistant", "text": metrics.chat_fallback_msg(simple)})


def _cc_focused(ss, filtered, path):
    """Which company the classification / live-signals / why-wrong panels feature."""
    ft = ss.get("focus_ticker")
    if ft:
        c = universe.get(ft, path)
        if c:
            return c
        e = ss.snapshots.get(ft)
        if e:
            return e["company"]
    hw, _, _ = metrics.hidden_winners(filtered, top_n=1)   # numeric: strongest live signal in view
    if hw:
        return universe.get(hw[0]["ticker"], path) or (filtered[0] if filtered else None)
    lead = metrics.evidence_leaders(filtered, top_n=1)     # evidence: strongest leadership score
    if lead:
        return universe.get(lead[0]["ticker"], path) or (filtered[0] if filtered else None)
    return filtered[0] if filtered else None


def _why_wrong(focused):
    if not focused:
        return "Add or focus a company to see where its live signal diverges from the stale rating."
    s = focused.get("live_signals") or {}
    d = metrics.num((focused.get("momentum") or {}).get("digital_ai"))
    name = focused.get("company", "This company")
    score, as_of = focused.get("esg_score"), (focused.get("esg_as_of") or "")
    if d is None and focused.get("esg_basis"):       # evidence mode — no live momentum yet
        p = metrics.evidence_profile(focused)
        tags = ", ".join(f'{cr["label"]} {cr["value"]}' for cr in p["credentials"][:2]) or "documented ESG progress"
        return (f"{name} is a documented ESG improver ({tags}; leadership {p['score']}/100). A stale "
                "rating may already price that leadership — the radar's edge is the LIVE alt-data "
                "(AI hiring, patents, news/behaviour) that isn't wired yet. That's where a 2023 score "
                "gets caught out.")
    cls = metrics.classify(focused)
    if cls["label"] == "HIDDEN WINNER":
        return (f"{name} is hiring hard for AI governance ({s.get('ai_hiring_surge') or 'fast'}) "
                f"while the static {as_of} score ({score if score is not None else '—'}) sits still — "
                f"the rating can't see the live Digital/AI {metrics.fmt_pct(d)} trajectory.")
    if cls["label"].startswith("WATCH"):
        return (f"{name} carries {int(metrics.num(s.get('controversy_flags')) or 0)} controversy "
                f"flag(s) with softening signals (Digital/AI {metrics.fmt_pct(d)}); the stale score "
                "lags the behaviour.")
    if d is None:
        return (f"No live momentum for {name} yet — add numeric data (or run a deep dive) so the "
                "radar can compete with its rating.")
    return (f"{name}'s live signal (Digital/AI {metrics.fmt_pct(d)}) is roughly in line with its "
            "rating — watch for divergence.")


# --- command center: panels ------------------------------------------------- #
# The KPI strip shows Environment · Governance · Digital/AI (the mockup's three cards).
# Social lives only in the momentum-chart legend, so the strip stays a clean trio.
_KPI_STRIP = ("environment", "governance", "digital_ai")


def _render_pillars(filtered):
    """Compact horizontal KPI cards: label + trend on the left, big mono % on the right.
    The Digital/AI card flips amber when it's the fast 'live-edge' riser (mockup)."""
    rows = {p["key"]: p for p in metrics.pillar_momentum(filtered)}
    cols = st.columns(3, gap="medium")
    for col, key in zip(cols, _KPI_STRIP):
        p = rows.get(key)
        if not p:
            continue
        fast = bool(p.get("fast"))
        cls = "cc-kpi cc-fast" if fast else "cc-kpi"
        tone = "" if fast else _sign_class(p["value"])  # fast -> amber via CSS; else by sign
        col.markdown(
            f'<div class="{cls}"><div class="cc-kpi-label">{_esc(p["label"])}</div>'
            f'<div class="cc-kpi-val {tone}">{_esc(metrics.fmt_pct(p["value"]))}</div>'
            f'<div class="cc-kpi-trend {tone}">{p["arrow"]} {_esc(p["trend"])}</div></div>',
            unsafe_allow_html=True)


def _render_momentum_chart(ss, filtered, height=370):
    st.markdown('<div class="cc-chart-head"><span class="cc-chart-title">ESG momentum</span>'
                '<span class="cc-chart-sub">90 days · % change</span></div>',
                unsafe_allow_html=True)
    series = metrics.momentum_series(filtered)
    if not series:
        st.caption("No momentum data for this filter yet.")
        return
    colors = {"digital_ai": "#f5a524", "environment": "#35d39a",
              "governance": "#f4737d", "social": "#5e9cf6"}
    dark = bool(ss.get("dark_mode"))
    grid = "rgba(148,163,184,.10)" if dark else "rgba(15,23,42,.08)"
    zero = "rgba(148,163,184,.30)" if dark else "rgba(15,23,42,.22)"
    tick = "#8b97ab" if dark else "#56627a"
    panel = "#121a29" if dark else "#ffffff"
    txt = "#e7ebf3" if dark else "#0f1729"
    go = _go()
    if go:
        fig = go.Figure()
        for key, vals in series.items():
            # Digital/AI is the headline signal — draw it heaviest, matching the mockup.
            width = 3.2 if key == "digital_ai" else (2.6 if key == "environment" else 2.2)
            fig.add_trace(go.Scatter(
                y=vals, mode="lines", name=metrics.PILLAR_LABEL[key],
                line=dict(color=colors.get(key, "#9aa6b2"), width=width, shape="spline"),
                hovertemplate=metrics.PILLAR_LABEL[key] + ": %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=height, margin=dict(l=8, r=8, t=6, b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            # Unified hover that NEVER disappears as the cursor moves across the plot:
            # hover/spike distance = -1 means "always snap to the nearest x", so the
            # all-series readout + the vertical guide track the cursor everywhere.
            hovermode="x unified", hoverdistance=-1, spikedistance=-1,
            hoverlabel=dict(bgcolor=panel, bordercolor=grid,
                            font=dict(family="IBM Plex Sans", size=12, color=txt)),
            legend=dict(orientation="h", y=-0.16, x=0,
                        font=dict(size=11, color=tick, family="IBM Plex Sans")),
            xaxis=dict(visible=False, showspikes=True, spikemode="across", spikesnap="cursor",
                       spikethickness=1, spikedash="dot", spikecolor=zero),
            yaxis=dict(zeroline=True, zerolinecolor=zero, gridcolor=grid, ticksuffix="%",
                       tickfont=dict(size=10, color=tick, family="IBM Plex Mono")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.line_chart({metrics.PILLAR_LABEL[k]: v for k, v in series.items()}, height=height)


def _render_hidden_winners(filtered, new_tickers=()):
    hw, peer, _ = metrics.hidden_winners(filtered, top_n=5, new_tickers=new_tickers)
    st.markdown('<div class="cc-h">Hidden winners vs peer avg</div>'
                f'<div class="cc-muted">{len(filtered)} companies · avg ESG '
                f'{peer if peer is not None else "—"}</div>', unsafe_allow_html=True)
    if not hw:
        st.caption("No live signal in this filter yet.")
        return
    maxabs = max((abs(r["value"]) for r in hw), default=1) or 1
    rows = []
    for r in hw:
        w = max(4, int(abs(r["value"]) / maxabs * 100))
        sign = "cc-pos" if r["value"] >= 0 else "cc-neg"
        new = '<em class="cc-new">new</em>' if r.get("is_new") else ""
        rows.append(f'<div class="cc-hw"><div class="cc-hw-name">{_esc(r["company"])}{new}</div>'
                    f'<div class="cc-hw-track"><div class="cc-hw-fill {sign}" style="width:{w}%"></div></div>'
                    f'<div class="cc-hw-val {sign}">{_esc(metrics.fmt_pct(r["value"]))}</div></div>')
    st.markdown('<div class="cc-hwwrap">' + "".join(rows) + "</div>"
                '<div class="cc-muted">Bar = live Digital/AI signal — the divergence the rating can\'t see.</div>',
                unsafe_allow_html=True)


def _render_classification(focused, cls=None, creds=None):
    cls = cls or metrics.classify(focused or {})
    tone = {"good": "cc-class-good", "bad": "cc-class-bad", "neutral": "cc-class-neutral"}[cls["tone"]]
    chips_html = ""
    if creds:
        chips = "".join(
            f'<span class="cc-chip">{_esc(cr["label"])} {_esc(cr["value"])}</span>'
            for cr in creds[:5])
        if chips:
            chips_html = f'<div class="cc-chips">{chips}</div>'
    st.markdown(
        f'<div class="cc-class {tone}"><div class="cc-class-h">Classification &nbsp; '
        f'<b>{_esc(cls["label"])}</b> &nbsp;<span class="cc-muted">· '
        f'{_esc((focused or {}).get("company", "—"))}</span></div>'
        f'{chips_html}'
        f'<div class="cc-class-line">{_esc(cls["line"])}</div></div>', unsafe_allow_html=True)


# --- focused-company feature panels (2026-06-30 backlog) ----------------------- #
_TONE_CLASS = {"good": "cc-class-good", "bad": "cc-class-bad", "neutral": "cc-class-neutral"}


def _render_plain_summary(focused, answer, *, demo=False):
    """[2.1] A plain-language, score-free summary card leading the Simplified center column."""
    ps = metrics.plain_summary(focused or {}, answer)
    chip = '<span class="cc-tag-illus">illustrative demo</span>' if demo else ""
    verdict = (f'<div class="cc-class-line"><b>What we see:</b> {_esc(ps["verdict"])}</div>'
               if ps["verdict"] else "")
    st.markdown(
        f'<div class="cc-class {_TONE_CLASS[ps["tone"]]}"><div class="cc-class-h">In plain terms '
        f'&nbsp; <b>{_esc(ps["headline"])}</b> {chip}</div>'
        f'<div class="cc-class-line">{_esc(ps["body"])}</div>{verdict}</div>', unsafe_allow_html=True)
    st.caption("Plain-language read — not investment advice; we never say buy / sell / hold.")


def _render_price_panel(ss, focused):
    """[#17] Illustrative 90-day share-price trajectory for a focused DEMO company; real names show
    'awaiting data' (demo-only field, HARD RULE 2). Defends with the demo_mode gate."""
    st.markdown('<div class="cc-chart-head"><span class="cc-chart-title">Share price · 90 days'
                '</span><span class="cc-chart-sub">illustrative · rebased to 100</span></div>',
                unsafe_allow_html=True)
    pct = metrics.price_change_pct(focused) if ss.get("demo_mode") else None
    if pct is None:
        st.caption("Awaiting data — no price feed wired for this name.")
        return
    st.markdown(f'<div class="cc-muted">90-day change <b class="{_sign_class(pct)}">'
                f'{_esc(metrics.fmt_pct(pct))}</b> · illustrative demo data</div>',
                unsafe_allow_html=True)
    series = metrics.price_series(pct)
    go = _go()
    if go and series:
        dark = bool(ss.get("dark_mode"))
        grid = "rgba(148,163,184,.10)" if dark else "rgba(15,23,42,.08)"
        tick = "#8b97ab" if dark else "#56627a"
        fig = go.Figure(go.Scatter(y=series, mode="lines",
                        line=dict(color="#35d39a" if pct >= 0 else "#f4737d", width=2.6,
                                  shape="spline"),
                        hovertemplate="%{y:.1f}<extra></extra>"))
        fig.update_layout(height=210, margin=dict(l=8, r=8, t=6, b=8),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis=dict(visible=False),
                          yaxis=dict(gridcolor=grid, tickfont=dict(size=10, color=tick,
                                                                   family="IBM Plex Mono")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    elif series:
        st.line_chart(series, height=210)
    if not _is_simplified(ss):
        st.caption("Illustrative rebased path (start = 100) — not a backtest or a real quote.")


def _render_forecast(focused, simple):
    """[#12] Illustrative directional outlook from current momentum — never a projected number for a
    real name (HARD RULE 2/4)."""
    fc = metrics.forecast_outlook(focused or {})
    st.markdown('<div class="cc-h">🔭 Forecast outlook '
                '<span class="cc-tag-illus">illustrative</span></div>', unsafe_allow_html=True)
    if not fc["available"]:
        st.markdown(f'<div class="cc-card cc-muted">{_esc(fc["headline"])}</div>',
                    unsafe_allow_html=True)
        return
    st.markdown(
        f'<div class="cc-class {_TONE_CLASS[fc["tone"]]}"><div class="cc-class-h">Outlook &nbsp; '
        f'<b>{_esc(fc["label"])}</b></div>'
        f'<div class="cc-class-line">{_esc(fc["headline"])}</div></div>', unsafe_allow_html=True)
    if not simple:
        chips = "".join(f'<span class="cc-chip">{_esc(p["label"])} {p["arrow"]} {_esc(p["word"])}'
                        '</span>' for p in fc["pillars"])
        st.markdown(f'<div class="cc-chips">{chips}</div>', unsafe_allow_html=True)
        st.caption(f"Basis: avg live pillar momentum {metrics.fmt_pct(fc['mean'])} "
                   "(illustrative demo signal).")
    st.caption("Illustrative directional outlook — a conditional read of current momentum, not a "
               "forecast, prediction, or price target. Never investment advice.")


def _render_check_before_monday(ss, focused, *, compact):
    """[#5] Surface the focused company's cached Stage-2 'check before Monday' action (verbatim from
    the verified baton — never generated here)."""
    tk = (focused or {}).get("ticker")
    act = metrics.focused_answer_action(ss.snapshots, tk)
    st.markdown('<div class="cc-h">✅ Check before Monday</div>', unsafe_allow_html=True)
    if not act["has"]:
        st.markdown('<div class="cc-panel-body">No competing read computed yet — run a deep-dive '
                    'Compete on this company to surface one concrete action to check.</div>',
                    unsafe_allow_html=True)
        return
    if not compact and act["verdict"]:
        st.markdown(f'<div class="cc-muted">⚔️ {_esc(act["verdict"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-panel-body">{_esc(act["check"])}</div>', unsafe_allow_html=True)
    origin = ((ss.snapshots.get(tk) or {}).get("company") or {}).get("_origin")
    cap = ("Illustrative — computed on demo data; not a real company action."
           if origin == "sample" else
           "From the computed deep-dive (Stage 2 baton). Not investment advice.")
    st.markdown(f'<div class="cc-muted">{cap}</div>', unsafe_allow_html=True)


def _render_news_card(ss, focused):
    """[#11] News headlines — illustrative for demo names; 'awaiting' + deterministic search links
    for real names (never fabricated headlines, HARD RULE 2)."""
    nc = metrics.news_card(focused or {})
    simple = _is_simplified(ss)
    st.markdown('<div class="cc-h">📰 In the news</div>', unsafe_allow_html=True)
    if nc["headlines"]:
        st.markdown('<div class="cc-muted">Illustrative demo headlines — not real news.</div>',
                    unsafe_allow_html=True)
        for h in nc["headlines"][:(3 if simple else 5)]:
            meta = " · ".join(p for p in (h.get("source"), h.get("date")) if p)
            st.markdown(f'<div class="cc-panel-body" style="margin:6px 0;">{_esc(h["title"])}'
                        f'<div class="cc-muted">{_esc(meta)}</div></div>', unsafe_allow_html=True)
    else:
        st.caption("General news not wired for this name yet — search it directly:")
    st.markdown(f'[▶ Search YouTube]({nc["youtube_url"]})'
                + ("" if simple else f"  ·  [📰 News search]({nc['news_url']})"))


def _render_analyst_coverage(focused, simplified, demo):
    """[#18] Sell-side coverage BREADTH pill — count only, never a rating (HARD RULE 4); visually
    distinct from the X/10 data-coverage meter."""
    ac = metrics.analyst_coverage(focused or {})
    if not ac["covered"]:
        if simplified:
            return                                   # keep the plain view clean when nothing to show
        st.markdown('<div class="cc-leftpill">👥 Analyst coverage · awaiting data</div>',
                    unsafe_allow_html=True)
        return
    extra = f" ({ac['as_of']})" if ac["as_of"] else ""
    tag = " · illustrative" if demo else ""
    st.markdown(f'<div class="cc-leftpill">👥 {_esc(ac["label"])}{_esc(extra)}{tag}</div>',
                unsafe_allow_html=True)
    if not simplified:
        st.markdown('<div class="cc-muted">Sell-side analyst breadth (how many analysts follow the '
                    'name) — distinct from the live-signal coverage meter (X/10); not a rating.</div>',
                    unsafe_allow_html=True)


def _render_financial_snapshot(ss, company):
    """[#10/2.3] Illustrative financial snapshot on the deep dive; 'awaiting data' when no market
    feed (HARD RULE 2). Stat grid only — no plotly."""
    fs = metrics.financial_snapshot(company or {})
    st.markdown('<div class="cc-h">💹 Financial snapshot</div>', unsafe_allow_html=True)
    if not fs["have"]:
        st.caption("Financial snapshot — awaiting data (market feed not wired for this name).")
        return
    rows = fs["simple"] if _is_simplified(ss) else fs["rows"]
    cells = "".join(f'<div class="cc-kpi"><div class="cc-kpi-label">{_esc(r["label"])}</div>'
                    f'<div class="cc-kpi-val">{_esc(r["value"])}</div></div>' for r in rows)
    st.markdown('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));'
                f'gap:8px;">{cells}</div>', unsafe_allow_html=True)
    st.caption("Illustrative figures — not real market data.")


def _render_followup_chips(ss, focused, path):
    """[14/3.7] 2-3 clickable suggestion chips under the last assistant reply; a click feeds the same
    ss.pending_chat mechanism the chat form uses (applied at the top of the next run)."""
    log = ss.get("chat_log") or []
    if not log or log[-1].get("role") != "assistant":
        return
    ft = (focused or {}).get("ticker")
    entry = ss.snapshots.get(ft) if ft else None
    secs = universe.sectors(path)
    ctys = universe.countries(path)
    chips = metrics.suggested_followups(
        focused_name=(focused or {}).get("company"),
        focused_sector=_short_sector((focused or {}).get("sector")),
        has_focus=bool(ss.get("focus_ticker")) or bool(focused),
        has_answer=bool(entry and entry.get("answer")),
        simplified=_is_simplified(ss),
        sample_sector=_short_sector(secs[0]) if secs else None,
        sample_country=ctys[0] if ctys else None)
    if not chips:
        return
    st.caption("Try next:")
    cols = st.columns(len(chips))
    for i, (col, chip) in enumerate(zip(cols, chips)):
        if col.button(chip["label"], key=f"cc_chip_{i}", use_container_width=True,
                      help=chip["prompt"]):
            ss.pending_chat = chip["prompt"]
            st.rerun()


def _render_live_signals(focused):
    st.markdown('<div class="cc-h">Live signals</div>', unsafe_allow_html=True)
    rows = metrics.live_signals(focused or {})
    if not rows:
        st.caption("No live signals for the focused company yet.")
        return
    tone = {"good": "cc-pos", "warn": "cc-warn", "neutral": "cc-flat"}
    body = "".join(f'<div class="cc-sig"><span>{_esc(r["label"])}</span>'
                   f'<b class="{tone.get(r["tone"], "cc-flat")}">{_esc(r["value"])}</b></div>'
                   for r in rows)
    st.markdown('<div class="cc-sigwrap">' + body + "</div>", unsafe_allow_html=True)


def _uni_mode(cons):
    """Which data drives the panels: full numbers, grounded-evidence, or nothing yet."""
    if metrics.has_numbers(cons):
        return "numeric"
    if any(c.get("esg_basis") for c in cons):
        return "evidence"
    return "empty"


def _render_coverage_cards(filtered):
    """Evidence-mode top row: % of the filtered set holding each marquee ESG credential."""
    cols = st.columns(4)
    for col, cv in zip(cols, metrics.credential_coverage(filtered)):
        pct = cv["pct"]
        col.markdown(
            f'<div class="cc-pill"><div class="cc-pill-h">{_esc(cv["label"])}</div>'
            f'<div class="cc-big cc-pos">{pct if pct is not None else "—"}%</div>'
            f'<div class="cc-pill-sub">{cv["count"]}/{cv["n"]} of set</div></div>',
            unsafe_allow_html=True)


def _render_bars(title, subtitle, rows, *, maxabs, suffix="", footer="", tier=False):
    """Shared horizontal-bar panel (hidden winners / evidence leaders).

    tier=True: color bars by score band (80+ green, 60–79 amber, <60 blue) instead of
    positive/negative. Used for evidence-leader scores where all values are positive.
    Names are never truncated — the column right-aligns so bars always start at the same x.
    """
    st.markdown(f'<div class="cc-h">{_esc(title)}</div><div class="cc-muted">{_esc(subtitle)}</div>',
                unsafe_allow_html=True)
    if not rows:
        st.caption("Nothing to rank in this filter yet.")
        return
    maxabs = maxabs or 1
    out = []
    for r in rows:
        w = max(4, int(abs(r["value"]) / maxabs * 100))
        sign = "cc-pos" if r["value"] >= 0 else "cc-neg"
        if tier:
            bar_cls = ("cc-pos" if r["value"] >= 80
                       else "cc-tier-mid" if r["value"] >= 60
                       else "cc-tier-low")
        else:
            bar_cls = sign
        new = '<em class="cc-new">new</em>' if r.get("is_new") else ""
        val = metrics.fmt_pct(r["value"]) if suffix == "%" else f'{r["value"]}{suffix}'
        out.append(f'<div class="cc-hw"><div class="cc-hw-name">{_esc(r["company"])}{new}</div>'
                   f'<div class="cc-hw-track"><div class="cc-hw-fill {bar_cls}" style="width:{w}%"></div></div>'
                   f'<div class="cc-hw-val {sign}">{_esc(val)}</div></div>')
    st.markdown('<div class="cc-hwwrap">' + "".join(out) + "</div>"
                + (f'<div class="cc-muted">{_esc(footer)}</div>' if footer else ""),
                unsafe_allow_html=True)


def _render_evidence_signals(focused):
    """Evidence-mode right rail: the focused company's parsed ESG credentials as signal rows."""
    st.markdown('<div class="cc-h">ESG credentials</div>', unsafe_allow_html=True)
    creds = (metrics.evidence_profile(focused)["credentials"]
             if (focused or {}).get("esg_basis") else [])
    if not creds:
        st.caption("No rating credentials parsed from the focused company's evidence.")
        return
    tone = {"good": "cc-pos", "warn": "cc-warn", "neutral": "cc-flat"}
    body = "".join(f'<div class="cc-sig"><span>{_esc(cr["label"])}</span>'
                   f'<b class="{tone.get(cr["tone"], "cc-flat")}">{_esc(cr["value"])}</b></div>'
                   for cr in creds)
    st.markdown('<div class="cc-sigwrap">' + body + "</div>", unsafe_allow_html=True)


# --- command center: columns ------------------------------------------------ #
def _cc_left(ss, uni, cons, filtered, sectors, countries, path, mode):
    # Mockup: the universe banner + one-line note head the left rail (not the center).
    st.markdown(f'<div class="cc-leftpill">{_esc(metrics.universe_banner(uni))}</div>',
                unsafe_allow_html=True)
    note = ("Fictional companies — toggle off in the sidebar for the real ASEAN base DB."
            if ss.get("demo_mode") else
            "Real ASEAN improvers (evidence) — pillar momentum awaits the alt-data feed."
            if mode == "evidence" else
            "Live ASEAN improvers — competing with each stale rating.")
    st.caption(note)
    st.markdown('<div class="cc-h" style="margin-top:14px;">Filters</div>', unsafe_allow_html=True)
    st.selectbox("Industry", sectors, key="flt_sector", format_func=_short_sector)
    st.selectbox("Country", countries, key="flt_country",
                 format_func=lambda c: "All ASEAN" if c == "All" else c)
    st.caption(f"Universe: {len(cons)} listed · showing {len(filtered)}")

    if mode == "evidence":
        avg, an = metrics.evidence_average(filtered)
        title = f"Avg ESG-leadership · {_short_sector(ss.flt_sector)}"
        sub = (f"evidence index 0–100 · {an} names") if avg is not None else "awaiting data"
    else:
        avg, an = metrics.average_esg(filtered)
        title = f"Avg ESG · {_short_sector(ss.flt_sector)}"
        sub = (f"mean static score · {an} names") if avg is not None else "awaiting data"
    st.markdown(
        f'<div class="cc-card"><div class="cc-pill-h">{_esc(title)}</div>'
        f'<div class="cc-big cc-flat">{avg if avg is not None else "—"}</div>'
        f'<div class="cc-muted">{_esc(sub)}</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="cc-h">⭐ Monitored</div>', unsafe_allow_html=True)
    if ss.watchlist:
        compare = set(ss.get("compare_tickers", []))
        cmp_valid = [tk for tk in compare if tk in ss.snapshots]
        # Entry point into the side-by-side Compare view (≥2 built snapshots selected via ⊕ below).
        if len(cmp_valid) >= 2:
            if st.button(f"⚖️ Compare {len(cmp_valid)} →", key="cc_compare_go",
                         type="primary", use_container_width=True):
                ss.compare_tickers = cmp_valid
                ss.view = "compare"
                st.rerun()
        elif compare:
            st.caption("Select 1 more built company to compare.")
        for tk in ss.watchlist:
            e = ss.snapshots.get(tk)
            name = e["snap"]["company"] if e else ((universe.get(tk, path) or {}).get("company") or tk)
            if e:
                # Append band indicator if meaningful (avoids showing "⚪" for unknowns)
                bemo = _band_emoji(e["snap"])
                suffix = f" {bemo}" if bemo != "⚪" else ""
                label = f"⭐ {name}{suffix}"
            else:
                label = f"📌 {name}"
            col_open, col_cmp = st.columns([5, 1])
            if col_open.button(label, key=f"cclm_{tk}", use_container_width=True):
                if e:
                    _open_deep_dive(ss, tk)
                else:
                    c = universe.get(tk, path)
                    if c:
                        _build_and_pin_constituent(ss, c)
                    st.rerun()
            if e:  # the comparison needs a built snapshot
                in_cmp = tk in compare
                if col_cmp.button("✓" if in_cmp else "⊕", key=f"cccmp_{tk}",
                                  use_container_width=True,
                                  type="primary" if in_cmp else "secondary",
                                  help="Remove from comparison" if in_cmp else "Add to comparison"):
                    compare.discard(tk) if in_cmp else compare.add(tk)
                    ss.compare_tickers = list(compare)
                    st.rerun()
            else:
                col_cmp.write("")
    else:
        st.caption("Nothing pinned yet — ask the assistant to *add* a company (real mode), or use "
                   "the browse panel below.")


def _cc_center(ss, filtered, focused, mode):
    nt = {ss.focus_ticker} if ss.get("focus_ticker") else set()  # the just-focused name -> "new" badge
    simple = _is_simplified(ss)  # Simple (mockup) hides the winners/leaders column
    if simple:                                       # [2.1] plain-language card leads Simplified view
        _ans = (ss.snapshots.get((focused or {}).get("ticker")) or {}).get("answer")
        _render_plain_summary(focused, _ans, demo=bool(ss.get("demo_mode")))
        st.write("")
    if mode == "evidence":
        _render_coverage_cards(filtered)
        st.write("")
        if simple:
            ep = metrics.evidence_profile(focused or {}) if (focused or {}).get("esg_basis") else {}
            _render_classification(focused, metrics.classify_evidence(focused or {}),
                                   creds=ep.get("credentials", []))
            _render_check_before_monday(ss, focused, compact=True)   # [#5]
            _render_forecast(focused, simple)                        # [#12] -> awaiting in evidence
            _render_news_card(ss, focused)                           # [#11]
            return
        c1, c2 = st.columns([1.15, 1], gap="medium")
        with c1:
            st.markdown('<div class="cc-chart-head"><span class="cc-chart-title">ESG momentum</span>'
                        '<span class="cc-chart-sub">90 days · % change</span></div>',
                        unsafe_allow_html=True)
            st.caption("Live pillar momentum needs the alt-data feed (AI hiring, patents, "
                       "news/behaviour) — not in the evidence set. **This is the radar's real edge** "
                       "once those signals are wired.")
        with c2:
            leaders = metrics.evidence_leaders(filtered, top_n=5, new_tickers=nt)
            mx = max((r["value"] for r in leaders), default=100)
            _render_bars("ESG leaders", f"{len(filtered)} companies · derived 0–100 score",
                         leaders, maxabs=mx, suffix="/100",
                         footer="Score = ratings each name's evidence cites (MSCI/DJSI/CDP/FTSE4Good/…).",
                         tier=True)
        ep = metrics.evidence_profile(focused or {}) if (focused or {}).get("esg_basis") else {}
        _render_classification(focused, metrics.classify_evidence(focused or {}),
                               creds=ep.get("credentials", []))
        _render_price_panel(ss, focused)      # real name -> 'awaiting data' (demonstrates HARD RULE 2)
        _render_forecast(focused, simple)      # [#12]
        _render_news_card(ss, focused)         # [#11]
    else:
        _render_pillars(filtered)
        st.write("")
        if simple:                                   # Simple mode: tall full-width chart, no winners
            _render_momentum_chart(ss, filtered, height=560)
        else:
            c1, c2 = st.columns([1.15, 1], gap="medium")
            with c1:
                # Taller chart so the center column reaches down to the (longer) right rail,
                # trimming the dead space that sat under the classification box.
                _render_momentum_chart(ss, filtered, height=480)
            with c2:
                _render_hidden_winners(filtered, new_tickers=nt)
        _render_classification(focused, metrics.classify(focused or {}))
        _render_price_panel(ss, focused)          # [#17] illustrative 90-day price (demo only)
        _render_forecast(focused, simple)          # [#12] directional outlook
        if simple:                                 # [#5] Simplified -> center; In-Depth -> right rail
            _render_check_before_monday(ss, focused, compact=True)
        _render_news_card(ss, focused)             # [#11]


def _cc_right(ss, filtered, focused, path, mode):
    st.markdown('<div class="cc-h">💬 AI assistant</div>', unsafe_allow_html=True)
    simple = _is_simplified(ss)
    if simple:                                        # [2.2] plain-language assistant hint
        st.caption("Try “show banks”, “Singapore”, or a company name like “DBS” — I’ll pull it up. "
                   "Say “look at DBS” for a full read.")
    else:
        st.caption("Filter (“show banks”, “Singapore”), focus a company, or run the **3-stage relay**: "
                   "“analyze DBS” (compete) · “interrogate Maybank” · “analyze Grab” (live ASEAN).")
    for m in ss.chat_log[-6:]:
        css = "cc-bubble-u" if m["role"] == "user" else "cc-bubble-a"
        st.markdown(f'<div class="cc-bubble {css}">{_esc(m["text"])}</div>', unsafe_allow_html=True)
    _render_followup_chips(ss, focused, path)         # [14/3.7] suggestion chips under the last reply
    with st.form("cc_chat", clear_on_submit=True):
        msg = st.text_input("ask", key="cc_chat_in", label_visibility="collapsed",
                            placeholder="Add a company or ask…")
        sent = st.form_submit_button("Send  ➤", use_container_width=True, type="primary")
    if sent and (msg or "").strip():
        ss.pending_chat = msg.strip()
        st.rerun()

    # Two-mode hint row — run the 3-stage relay on the focused company without knowing keywords.
    ft = (focused or {}).get("ticker")
    fname = (focused or {}).get("company", "—")
    st.caption((f"Look at **{fname}** →" if simple else f"Analyse **{fname}** →"))
    h1, h2 = st.columns(2)
    if h1.button("Quick read" if simple else "Compete", key="cc_hint_compete",
                 use_container_width=True, disabled=not ft,
                 help=("Show the competing read straight away." if simple
                       else "Skip to the competing read — Stage 2 + 3 run directly.")):
        c = universe.get(ft, path) or focused
        tk = ft if ft in ss.snapshots else _ensure_snapshot(ss, c)
        if tk:
            _launch_relay(ss, tk, "compete")
    if h2.button("Ask first" if simple else "Interrogate", key="cc_hint_interro",
                 use_container_width=True, disabled=not ft,
                 help=("Answer a few quick questions first, then see the read." if simple
                       else "Ask adaptive ESG questions first (Stage 1), then compete.")):
        c = universe.get(ft, path) or focused
        tk = ft if ft in ss.snapshots else _ensure_snapshot(ss, c)
        if tk:
            _launch_relay(ss, tk, "interrogate")

    st.divider()
    if mode == "evidence":
        _render_evidence_signals(focused)
        nsig = len((focused or {}).get("esg_basis") and metrics.evidence_profile(focused)["credentials"] or [])
    else:
        _render_live_signals(focused)
        nsig = len(metrics.live_signals(focused or {}))
    _render_analyst_coverage(focused, simple, bool(ss.get("demo_mode")))   # [#18] sell-side breadth
    st.divider()
    st.markdown('<div class="cc-h">Why the rating may be wrong</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-panel-body">{_esc(_why_wrong(focused))}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-muted">Focused: {_esc((focused or {}).get("company", "—"))} · '
                f'{nsig} {"credentials" if mode == "evidence" else "signals"}</div>',
                unsafe_allow_html=True)

    if not simple:                                   # [#5] In-Depth: diagnosis -> concrete action
        st.divider()
        _render_check_before_monday(ss, focused, compact=False)

    if (focused or {}).get("esg_basis"):     # the documented 2019–2023 improvement evidence
        with st.expander("📌 Foundation evidence (why it's an ESG improver)"):
            conf = (focused.get("confidence") or "—").title()
            st.caption(f"Confidence: **{conf}**")
            st.write(focused["esg_basis"])
            if focused.get("source_url"):
                st.markdown(f"[source]({focused['source_url']})")


def _universe_cards(ss, filtered, path):
    st.caption("Filtered by the panel on the left. 🎯 Focus features a company in the right-rail "
               "panels; ➕ Monitor builds a live ESG snapshot (real mode only).")
    if not filtered:
        st.caption("No constituents match the filters.")
        return
    ncol = 3
    for i in range(0, len(filtered), ncol):
        cols = st.columns(ncol)
        for j, c in enumerate(filtered[i:i + ncol]):
            tk = c["ticker"]
            with cols[j]:
                with st.container(border=True):
                    st.markdown(f"**{c['company']}**")
                    st.caption(f"`{tk}` · {c['country']} · {_short_sector(c['sector'])}")
                    basis = c.get("esg_basis")
                    if basis:
                        badge = {"high": "🟢", "medium": "🟡", "low": "🟠"}.get(
                            (c.get("confidence") or "").lower(), "⚪")
                        st.caption(f"{badge} {basis[:150]}{'…' if len(basis) > 150 else ''}"
                                   + (f"  ·  [source]({c['source_url']})" if c.get("source_url") else ""))
                    b1, b2 = st.columns(2)
                    if b1.button("🎯 Focus", key=f"foc_{tk}", use_container_width=True):
                        ss.focus_ticker = tk
                        st.rerun()
                    if tk in ss.watchlist:
                        b2.button("📌", key=f"upn_{tk}", use_container_width=True, disabled=True)
                    elif b2.button("➕ Monitor", key=f"umon_{tk}", use_container_width=True,
                                   disabled=bool(ss.get("demo_mode")),
                                   help="Switch off Demo data to build real snapshots"
                                        if ss.get("demo_mode") else None):
                        _build_and_pin_constituent(ss, c)
                        st.rerun()


# Distinct per-company colours for the comparison graphs (theme-agnostic, high-contrast).
_CMP_PALETTE = ["#35d39a", "#5e9cf6", "#f5a524", "#f4737d"]


def _render_compare_charts(ss, tickers):
    """Graph the side-by-side: grouped E/S/G momentum bars + static-ESG-score bars. Numbers come
    straight from each Contract B via metrics.compare_companies — never fabricated, so evidence-only
    names just drop out. Degrades to st.bar_chart when plotly is absent (HARD RULE 1)."""
    companies = [ss.snapshots[tk]["company"] for tk in tickers]
    data = metrics.compare_companies(companies)
    rows = data["rows"]
    pillars = data["pillars"]
    colors = {r["ticker"]: _CMP_PALETTE[i % len(_CMP_PALETTE)] for i, r in enumerate(rows)}

    if not (data["has_momentum"] or data["has_score"]):
        st.info("📊 No numeric momentum or rating data on these names yet — comparison graphs need "
                "the demo set (or built numeric data). Evidence-only names show **awaiting data**.")
        return

    dark = bool(ss.get("dark_mode"))
    grid = "rgba(148,163,184,.10)" if dark else "rgba(15,23,42,.08)"
    zero = "rgba(148,163,184,.30)" if dark else "rgba(15,23,42,.22)"
    tick = "#8b97ab" if dark else "#56627a"
    go = _go()
    g1, g2 = st.columns([3, 2])

    # --- E/S/G momentum, grouped bars (one cluster per pillar, one bar per company) ---
    with g1:
        st.markdown('<div class="cc-chart-head"><span class="cc-chart-title">E · S · G momentum'
                    '</span><span class="cc-chart-sub">% change · higher = better</span></div>',
                    unsafe_allow_html=True)
        if not data["has_momentum"]:
            st.caption("No momentum data on these names.")
        elif go:
            fig = go.Figure()
            for r in rows:
                fig.add_trace(go.Bar(
                    name=r["company"], x=[p for p in pillars],
                    y=[r["momentum"][p] for p in pillars],
                    marker_color=colors[r["ticker"]],
                    hovertemplate=f'{_esc(r["company"])} %{{x}}: %{{y:.1f}}%<extra></extra>'))
            fig.update_layout(
                barmode="group", height=320, margin=dict(l=8, r=8, t=6, b=8),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=-0.16, x=0,
                            font=dict(size=11, color=tick, family="IBM Plex Sans")),
                xaxis=dict(tickfont=dict(size=12, color=tick, family="IBM Plex Sans")),
                yaxis=dict(zeroline=True, zerolinecolor=zero, gridcolor=grid, ticksuffix="%",
                           tickfont=dict(size=10, color=tick, family="IBM Plex Mono")))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.bar_chart({r["company"]: [r["momentum"][p] for p in pillars] for r in rows},
                         height=320)
            st.caption("Bars ordered E · S · G.")

    # --- static ESG score, one bar per company (lower = better for a risk score) ---
    with g2:
        st.markdown('<div class="cc-chart-head"><span class="cc-chart-title">Static ESG score'
                    '</span><span class="cc-chart-sub">lower = better risk</span></div>',
                    unsafe_allow_html=True)
        scored = [r for r in rows if r["esg_score"] is not None]
        if not scored:
            st.caption("No static rating on these names.")
        elif go:
            fig = go.Figure(go.Bar(
                x=[r["company"] for r in scored], y=[r["esg_score"] for r in scored],
                marker_color=[colors[r["ticker"]] for r in scored],
                text=[f'{r["esg_score"]:.1f}' for r in scored], textposition="outside",
                hovertemplate="%{x}: %{y:.1f}<extra></extra>"))
            fig.update_layout(
                height=320, margin=dict(l=8, r=8, t=6, b=8),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                xaxis=dict(tickfont=dict(size=11, color=tick, family="IBM Plex Sans")),
                yaxis=dict(gridcolor=grid,
                           tickfont=dict(size=10, color=tick, family="IBM Plex Mono")))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.bar_chart({r["company"]: [r["esg_score"]] for r in scored}, height=320)
    st.divider()


def _render_compare(ss):
    """Side-by-side comparison of 2–4 monitored companies."""
    tickers = [tk for tk in ss.get("compare_tickers", []) if tk in ss.snapshots]

    top = st.columns([1, 2, 3])
    if top[0].button("← Dashboard", use_container_width=True):
        ss.view = "dashboard"
        ss.compare_tickers = []
        st.rerun()
    if top[1].button("⊕ Add more", use_container_width=True,
                     help="Return to dashboard to select more companies"):
        ss.view = "dashboard"
        st.rerun()
    top[2].markdown("### ⚖️ Side-by-side comparison")

    if len(tickers) < 2:
        st.warning("Select at least 2 monitored companies using **⊕ Cmp** on the monitored board.")
        return

    _render_compare_charts(ss, tickers)

    cols = st.columns(len(tickers))
    for col, tk in zip(cols, tickers):
        entry = ss.snapshots[tk]
        snap = entry["snap"]
        answer = entry.get("answer")
        ar = snap.get("arrows", {})

        with col:
            with st.container(border=True):
                st.markdown(f"**{snap['company']}**")
                st.caption(f"`{snap['ticker']}` · {snap.get('country', '—')}")
                st.caption(snap.get("sector", "—"))
                st.divider()

                st.metric("ESG rating",
                          snap.get("rating") if _known(snap.get("rating")) else "—",
                          help="Stale static rating — lower = better for a Sustainalytics risk score.")
                st.metric("Risk band",
                          f'{_band_emoji(snap)} {snap.get("band") or "—"}')
                st.metric("E · S · G momentum",
                          f'{ar.get("E", "·")} {ar.get("S", "·")} {ar.get("G", "·")}',
                          help="▲ improving · — flat · ▼ declining · · unknown")
                st.metric("🚩 Red flags", snap.get("red_flags", 0))
                st.metric("Coverage",
                          f'{snap.get("coverage", 0)}/{snap.get("coverage_total", 10)}',
                          help="How many of the 10 monitored signals are grounded.")

                st.divider()
                if answer and answer.get("competes_summary"):
                    st.caption("**Verdict**")
                    st.markdown(
                        f'<div class="cc-panel-body" style="font-size:12px;line-height:1.5;'
                        f'max-height:120px;overflow-y:auto;">'
                        f'{_esc(answer["competes_summary"])}</div>',
                        unsafe_allow_html=True)
                else:
                    st.caption("No verdict yet — run a deep dive first.")

                st.write("")
                if st.button("🔬 Deep dive", key=f"cmpdd_{tk}",
                             use_container_width=True, type="primary"):
                    _open_deep_dive(ss, tk)
                if st.button("✕ Remove", key=f"cmprm_{tk}", use_container_width=True):
                    ss.compare_tickers = [t for t in tickers if t != tk]
                    if len(ss.compare_tickers) < 2:
                        ss.view = "dashboard"
                    st.rerun()


# Radar mark from the mockup — concentric rings + a sweep tick (uses theme tokens).
_RADAR_SVG = (
    '<svg width="30" height="30" viewBox="0 0 34 34" style="flex:0 0 auto;">'
    '<circle cx="17" cy="17" r="15" fill="none" stroke="var(--r-border)" stroke-width="1.4"></circle>'
    '<circle cx="17" cy="17" r="9" fill="none" stroke="var(--r-border)" stroke-width="1.4"></circle>'
    '<line x1="17" y1="17" x2="29.5" y2="8" stroke="var(--r-pos)" stroke-width="1.6" stroke-linecap="round"></line>'
    '<circle cx="17" cy="17" r="3" fill="var(--r-pos)"></circle></svg>'
)


def _render_header(ss, uni, cons, mode):
    """The command-center header: logo · title · meta · status pill, then the control
    cluster (Full|Simple · Dark|Light · Filters · Assistant) as styled buttons."""
    n = len(cons)
    ind = len({c["sector"] for c in cons if c["sector"] != "unknown"})
    quarter = metrics._as_quarter(uni.get("as_of", "")) or uni.get("as_of", "")
    tag = ("demo data" if ss.get("demo_mode") else
           "evidence-based" if mode == "evidence" else "live")
    title_html = (
        '<div class="cc-hdr-wrap">' + _RADAR_SVG +
        '<div style="min-width:0;"><div class="cc-title2">ASEAN ESG Momentum Radar</div>'
        f'<div class="cc-meta">{_esc(quarter)} · {n} listed companies · {ind} industries · '
        f'{_esc(tag)}</div></div></div>'
    )
    if ss.get("demo_mode"):
        pill = '<span class="cc-live" style="color:var(--r-amber);border:1px solid var(--r-amber);">● Demo</span>'
    elif mode == "evidence":
        pill = '<span class="cc-live" style="color:var(--r-blue);border:1px solid var(--r-blue);">● Evidence</span>'
    else:
        pill = '<span class="cc-live" style="color:var(--r-pos);border:1px solid var(--r-pos);">● Live</span>'

    # Row 1: logo · title · meta on the left, status pill + freshness on the right.
    fresh = metrics.fmt_elapsed(time.time(), ss.get("data_built_at"))
    fresh_html = ""
    if fresh:
        label = "↻ Updated " + fresh + ("" if _is_simplified(ss) or not quarter else f" · {quarter}")
        fresh_html = f'<div class="cc-fresh">{_esc(label)}</div>'
    L, R = st.columns([7, 2], vertical_alignment="center")
    L.markdown(title_html, unsafe_allow_html=True)
    R.markdown(f'<div style="text-align:right;">{pill}{fresh_html}</div>', unsafe_allow_html=True)

    # Row 2: the control cluster, spanning the full main width so labels never wrap
    # (a slim sidebar is kept, so the header band has less room than the no-sidebar mockup).
    simple = _is_simplified(ss)
    dark = bool(ss.get("dark_mode"))
    lo, ro = bool(ss.get("left_open", True)), bool(ss.get("right_open", True))
    c = st.columns([1, 1, 1, 1, 1.3, 1.5, 3.2], vertical_alignment="center")
    # Full | Simple — drives ui_mode AND the rail/winners layout, exactly like the mockup.
    if c[0].button("Full", key="hdr_full", use_container_width=True,
                   type="secondary" if simple else "primary"):
        ss.ui_mode, ss.left_open, ss.right_open = "In-Depth", True, True
        st.rerun()
    if c[1].button("Simple", key="hdr_simple", use_container_width=True,
                   type="primary" if simple else "secondary"):
        ss.ui_mode, ss.left_open, ss.right_open = "Simplified", False, False
        st.rerun()
    if c[2].button("Dark", key="hdr_dark", use_container_width=True,
                   type="primary" if dark else "secondary"):
        ss.dark_mode = True
        st.rerun()
    if c[3].button("Light", key="hdr_light", use_container_width=True,
                   type="primary" if not dark else "secondary"):
        ss.dark_mode = False
        st.rerun()
    if c[4].button(("‹ " if lo else "› ") + "Filters", key="hdr_left",
                   use_container_width=True, type="primary" if lo else "secondary"):
        ss.left_open = not lo
        st.rerun()
    if c[5].button("Assistant " + ("›" if ro else "‹"), key="hdr_right",
                   use_container_width=True, type="primary" if ro else "secondary"):
        ss.right_open = not ro
        st.rerun()
    st.markdown('<div style="height:1px;background:var(--r-border);margin:8px 0 12px;"></div>',
                unsafe_allow_html=True)


def _render_dashboard(ss):
    """The command-center home: filters · avg ESG · pillar momentum · hidden winners · AI assistant."""
    path = universe.active_file(bool(ss.get("demo_mode")))
    if ss.get("pending_chat"):                       # apply chat BEFORE any widget instantiates
        _chat_act(ss, ss.pop("pending_chat"), path)

    uni = universe.load_universe(path)
    cons = uni["constituents"]
    sectors = ["All"] + universe.sectors(path)
    countries = ["All"] + universe.countries(path)
    if ss.flt_sector not in sectors:                 # keep filters valid across a universe swap
        ss.flt_sector = "All"
    if ss.flt_country not in countries:
        ss.flt_country = "All"
    filtered = universe.filter_constituents(country=ss.flt_country, sector=ss.flt_sector,
                                            query=ss.get("flt_search", ""), path=path)
    mode = _uni_mode(cons)
    focused = _cc_focused(ss, filtered, path)

    _render_header(ss, uni, cons, mode)

    # Headline foundation-backtest figures — display only, with the data's own NOT-recomputed
    # disclaimer (the figures refer to the team's original basket, not this reconstructed list).
    bs = uni.get("benchmark_stats") or {}
    if bs.get("basket_return") and not ss.get("demo_mode"):
        st.caption(
            f"📈 Foundation backtest (display only) — basket **{bs.get('basket_return', '—')}** vs "
            f"{_esc(uni.get('benchmark', 'MSCI ASEAN'))} **{bs.get('benchmark_return', '—')}** · "
            f"Sharpe {bs.get('basket_sharpe', '—')} vs {bs.get('benchmark_sharpe', '—')}.  \n"
            f"_{_esc(bs.get('source', ''))}_")

    # Collapsible rails (mockup: Filters / Assistant toggles). Streamlit can't animate a
    # width slide, so a closed rail is simply omitted and the canvas reclaims the space.
    lo, ro = bool(ss.get("left_open", True)), bool(ss.get("right_open", True))
    if lo and ro:
        left, center, right = st.columns([1, 2.9, 1.25], gap="medium")
    elif lo and not ro:
        left, center = st.columns([1, 4.2], gap="medium")
        right = None
    elif ro and not lo:
        center, right = st.columns([4.2, 1.25], gap="medium")
        left = None
    else:
        center, left, right = st.container(), None, None

    if left is not None:
        with left:
            _cc_left(ss, uni, cons, filtered, sectors, countries, path, mode)
    with center:
        _cc_center(ss, filtered, focused, mode)
    if right is not None:
        with right:
            _cc_right(ss, filtered, focused, path, mode)

    with st.expander(f"🔎 Browse / add from the full universe ({len(cons)} companies)"):
        _universe_cards(ss, filtered, path)


def _render_relay(ss, company):
    """The interrogate → compete → answer relay, used as the body of a deep dive. The monitored
    snapshot caches the computed answer so revisiting the company is instant."""
    if not ss.get("skip_interrogation"):
        st.subheader("1 · Interrogate")
        stage1.render(ss, company)

    if ss.s1_done and ss.narrowed_q:
        nq = ss.narrowed_q
        st.success("**Narrowed question (Stage 1 → baton):**\n\n" + nq["narrowed_question"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Mandate", nq["mandate"])
        c2.metric("Sector", nq["sector"])
        c3.metric("Horizon", nq["horizon"])

        st.subheader("2 · Compete over data")
        if ss.answer is None:
            rag_on = bool(ss.get("rag_enabled", True))
            st.caption(
                "A FRESH DeepSeek agent reasons over Layer A + its history + Layer B"
                + (", grounded by ASEAN-scoped context it fetches live (RAG). " if rag_on else ". ")
                + "It sees only the narrowed-question baton — not the interrogation chat."
            )
            clicked = st.button("Reason over the data →", type="primary", key="dd_s2")
            if clicked or ss.pop("s2_retry", False):
                _run_stage2(ss, nq, company)

        if ss.answer is not None:
            if ss.active_ticker and ss.active_ticker in ss.snapshots:  # cache for instant revisit
                ss.snapshots[ss.active_ticker]["answer"] = ss.answer
                ss.snapshots[ss.active_ticker]["narrowed_q"] = ss.narrowed_q
            st.subheader("3 · The competing answer")
            stage3.render_answer(ss.answer, company, debug=bool(ss.get("debug")), narrowed=ss.narrowed_q)
            if st.button("🔄 Ask a different question about this company", key="dd_again"):
                for _k in ("s1_msgs", "s1_trail", "s1_turns", "s1_done", "narrowed_q", "answer"):
                    ss.pop(_k, None)
                ss.pop("skip_interrogation", None)
                for _k in list(_TRANSIENT):
                    ss.pop(_k, None)
                st.rerun()


def _render_deep_dive(ss):
    """An in-depth look at one monitored company: snapshot strip + the competing relay."""
    company = ss.company
    top = st.columns([1, 5])
    if top[0].button("← Dashboard", use_container_width=True):
        _reset(ss)
    top[1].markdown("### 🔬 Deep dive")
    _company_header(company)
    entry = ss.snapshots.get(ss.active_ticker) or {}
    snap = entry.get("snap") or datasource.snapshot_from_company(company)
    _render_snapshot_metrics(snap)
    _render_financial_snapshot(ss, company)          # [#10/2.3] illustrative market stats (demo)
    st.divider()

    # Offer the fast "compete now" path before (and alongside) the interrogation.
    if not ss.s1_done and ss.answer is None and not ss.get("skip_interrogation"):
        st.markdown("**See the competing read now, or interrogate a sharper question first ↓**")
        if st.button("⚔️ Compete now (use the default question)", type="primary", key="dd_now"):
            ss.narrowed_q = _default_nq(company)
            ss.s1_done = True
            ss.skip_interrogation = True
            st.rerun()
        st.divider()
    _render_relay(ss, company)


# --------------------------------------------------------------------------- #
#  PAGE
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="ASEAN ESG Momentum Radar", page_icon="🛰️", layout="wide")

_DEFAULTS = {
    "company": None,    # Contract B (live-built / uploaded / sample) — None until chosen
    "s1_msgs": [],
    "s1_trail": [],
    "s1_turns": 0,
    "s1_done": False,
    "narrowed_q": None,
    "answer": None,
    # --- dashboard / monitoring state ---
    "view": "dashboard",     # "dashboard" (home) | "deep_dive" | "compare"
    "compare_tickers": [],  # tickers selected for side-by-side comparison
    "active_ticker": None,   # which monitored company the deep dive is showing
    "watchlist": None,       # list of pinned tickers (loaded from disk on first run)
    "snapshots": {},         # ticker -> {"company": ContractB, "snap": {...}, "answer", "narrowed_q"}
    "flt_country": "All",
    "flt_sector": "All",
    "flt_search": "",
    # --- command-center state ---
    "demo_mode": True,        # DEFAULT: the fictional, fully-numeric demo universe so the whole board is alive
                              # (labelled illustrative). Toggle OFF for the real evidence-based ASEAN base DB.
    "ui_mode": "Simplified", # "Simplified" (plain-language) | "In-Depth" (full analyst view).
                              # Opens Simplified (the locked default): plain cards, rails closed — the
                              # "Simple" toggle. Switch to "Full"/In-Depth for the analyst rails.
    "dark_mode": True,        # opens dark, matching the design mockup (header toggles Dark|Light)
    "left_open": False,       # Filters rail hidden in Simplified (header "‹ Filters" toggles it)
    "right_open": False,      # Assistant rail hidden in Simplified (header "Assistant ›" toggles it)
    "focus_ticker": None,    # the company featured in the classification / live-signals / why-wrong panels
    "chat_log": [],          # [{role, text}] for the right-rail AI assistant
    "pending_chat": None,    # a submitted chat line, applied at the TOP of the next run (before widgets)
    "data_built_at": None,   # epoch secs: when this session's board data was last (re)built (freshness pill)
}
ss = st.session_state
for _k, _v in _DEFAULTS.items():
    ss.setdefault(_k, _v)
if ss.get("data_built_at") is None:            # [1.11] stamp the session's data-load time once
    ss.data_built_at = time.time()             # (_pin refreshes it on a real build; reruns don't)
if ss.watchlist is None:                       # one-time load of persisted pins
    ss.watchlist = _load_watchlist()

# --- sidebar = the control panel ------------------------------------------- #
# Every widget owns its state via an explicit key= (NO value-from-session_state round-trip),
# so a single click registers — the old pattern changed each widget's identity and lagged.
with st.sidebar:
    st.markdown("### 🛰️ ESG Radar")
    st.caption("Control panel · theme & view live in the header")

    st.markdown("**Data source**")
    mode = st.radio(
        "Data source", ["live", "upload"], key="data_mode",
        format_func=lambda m: "🌐 Live (fetch)" if m == "live" else "📤 Upload",
        horizontal=True, label_visibility="collapsed",
    )
    if mode == "upload":
        up = st.file_uploader("ESG data file", type=["json", "csv", "txt"],
                              label_visibility="collapsed")
        if up is not None and st.button("Use this file →", type="primary", use_container_width=True):
            try:
                company_up, meta = datasource.load_upload(up.name, up.getvalue())
                tk = _pin(ss, company_up)                  # uploaded data joins the monitored board
                st.success(f"Loaded **{company_up.get('company', up.name)}** ({meta['mode']}).")
                _open_deep_dive(ss, tk)
            except core.LLMConfigError as e:
                st.error(str(e))
            except ValueError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.warning("⚠️ Couldn't read that file.")
                with st.expander("Details"):
                    st.code(f"{type(e).__name__}: {e}")
        with st.expander("📋 JSON template"):
            st.code(json.dumps(contracts.coerce_company_data(
                {"company": "Acme Corp", "ticker": "EX:ACME", "sector": "..."}, origin="upload"
            ), indent=2), language="json")
    else:
        st.caption("Add ASEAN names in the chat — e.g. *“DBS”*, *“add PTT”*, *“BCA”*.")

    st.divider()
    st.markdown("**Universe**")
    st.toggle("🎛️ Demo data", key="demo_mode",
              help="ON: a fictional, fully-numeric universe so the whole board is alive (labelled "
                   "illustrative — no real companies). OFF: the real ASEAN base DB "
                   "(data/asean_universe.json) — panels light up as you add real numbers.")

    st.divider()
    st.markdown("**Retrieval (RAG)**")
    st.toggle("Live web retrieval", value=True, key="rag_enabled",
              help="Fetch DuckDuckGo results + its AI summary (ASEAN-scoped), rank them (TF-IDF), "
                   "and let the agent interpret them to ground the reasoning.")
    st.slider("Sources to ground on", 3, 10, 5, key="rag_top_k")

    st.divider()
    b_home, b_sample = st.columns(2)
    if b_home.button("🏠 Dashboard", use_container_width=True, help="Back to the monitoring board."):
        _reset(ss)
    if b_sample.button("🎬 Sample", use_container_width=True,
                       disabled=not os.path.exists(SAMPLE_FILE),
                       help="Pin the offline demo company (no network or key needed)."):
        sample = core.load_company_data(SAMPLE_FILE)
        sample["_origin"] = "sample"
        tk = _pin(ss, sample)
        with open(os.path.join(FIXTURES_DIR, "narrowed_question.json"), encoding="utf-8") as _f:
            ss.snapshots[tk]["narrowed_q"] = contracts.coerce_narrowed_question(json.load(_f))
        with open(os.path.join(FIXTURES_DIR, "stage2_answer.json"), encoding="utf-8") as _f:
            ss.snapshots[tk]["answer"] = contracts.coerce_stage2_answer(json.load(_f))
        _open_deep_dive(ss, tk)
    st.toggle("🐞 Debug (raw output)", key="debug")

_inject_css("dark" if ss.get("dark_mode") else "light")

# --- router ------------------------------------------------------------------- #
if ss.view == "deep_dive" and ss.get("company") is not None:
    _stepper(ss)
    _render_deep_dive(ss)
elif ss.view == "compare":
    _render_compare(ss)
else:
    ss.view = "dashboard"
    _render_dashboard(ss)
