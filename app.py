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
# Always-on base fixes (apply in BOTH themes). Streamlit's chat_input renders its field dark
# under a custom theme — force a clean, readable field. Dark mode overrides the colours below.
_BASE_CSS = """
<style>
[data-testid="stChatInput"]{background:transparent !important;}
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"]{
  background:#FFFFFF !important;border-radius:10px !important;}
[data-testid="stChatInput"] textarea{
  background:#FFFFFF !important;color:#0B2545 !important;-webkit-text-fill-color:#0B2545 !important;}
[data-testid="stChatInput"] textarea::placeholder{
  color:#8A97A6 !important;-webkit-text-fill-color:#8A97A6 !important;}
</style>
"""

_DARK_CSS = """
<style>
:root{ --esgd-bg:#0E1117; --esgd-panel:#1B2230; --esgd-side:#161B26; --esgd-fg:#E6EAF1;
       --esgd-muted:#9AA6B2; --esgd-acc:#9B8CFF; --esgd-line:rgba(255,255,255,.12); }
[data-testid="stAppViewContainer"]{background:var(--esgd-bg);}
[data-testid="stHeader"]{background:rgba(14,17,23,.6);}
[data-testid="stSidebar"]{background:var(--esgd-side);border-right:1px solid var(--esgd-line);}
[data-testid="stAppViewContainer"], [data-testid="stSidebar"]{color:var(--esgd-fg);}
/* body text — !important so the default (navy) theme text stays readable on dark */
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] label, [data-testid="stWidgetLabel"] *,
[data-testid="stSidebar"] *{color:var(--esgd-fg) !important;}
h1,h2,h3,h4,h5,h6{color:#F5F7FA !important;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, small{color:var(--esgd-muted) !important;}
hr,[data-testid="stDivider"]{border-color:var(--esgd-line) !important;}
/* buttons — secondary dark, primary keeps the accent */
.stButton>button, [data-testid="stBaseButton-secondary"]{
  background:var(--esgd-panel) !important;color:var(--esgd-fg) !important;
  border:1px solid var(--esgd-line) !important;}
.stButton>button:hover, [data-testid="stBaseButton-secondary"]:hover{
  border-color:var(--esgd-acc) !important;color:#fff !important;}
[data-testid="stBaseButton-primary"]{background:var(--esgd-acc) !important;color:#190f33 !important;
  border:0 !important;font-weight:600;}
/* inputs / chat / selects / uploader */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-testid="stChatInput"] textarea, [data-baseweb="select"]>div{
  background:var(--esgd-panel) !important;color:var(--esgd-fg) !important;}
[data-testid="stChatInput"]{background:var(--esgd-side) !important;}
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"]{background:var(--esgd-panel) !important;}
[data-testid="stChatInput"] textarea{background:var(--esgd-panel) !important;
  color:var(--esgd-fg) !important;-webkit-text-fill-color:var(--esgd-fg) !important;}
[data-testid="stFileUploaderDropzone"]{background:var(--esgd-panel) !important;}
/* metrics */
[data-testid="stMetric"]{background:var(--esgd-panel);border:1px solid var(--esgd-line);
  border-radius:10px;padding:.5rem .7rem;}
[data-testid="stMetricValue"]{color:var(--esgd-fg) !important;}
[data-testid="stMetricLabel"] *{color:var(--esgd-muted) !important;}
/* expanders / code / notifications / chat msgs */
[data-testid="stExpander"]{background:var(--esgd-side);border:1px solid var(--esgd-line);border-radius:10px;}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary *{color:var(--esgd-fg) !important;}
code, pre{background:#11151D !important;color:#E6EAF1 !important;}
[data-testid="stNotification"]{background:var(--esgd-panel) !important;}
[data-testid="stChatMessage"]{background:var(--esgd-side);border:1px solid rgba(255,255,255,.06);border-radius:10px;}
/* our esg panels / cards / history */
.esg-panel, .esg-card{color:var(--esgd-fg) !important;}
.esg-card{background:rgba(255,255,255,.05);border-color:var(--esgd-line);}
.esg-h, .esg-b{color:var(--esgd-fg) !important;}
.esg-card .t, .esg-card .s, .esg-hbar-d{color:var(--esgd-muted) !important;}
</style>
"""


def _inject_theme(theme):
    st.markdown(_BASE_CSS, unsafe_allow_html=True)  # base fixes apply in both themes
    if theme == "dark":
        st.markdown(_DARK_CSS, unsafe_allow_html=True)


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


_ORIGIN_BADGE = {"live": "🌐 Live (fetched)", "upload": "📤 Uploaded", "sample": "🧪 Sample"}
_ORIGIN_DISCLAIMER = {
    "live": "Built live from public sources — fields not found are shown as “unknown”, never "
            "invented. Not investment advice.",
    "upload": "Built from your uploaded data. Not investment advice.",
    "sample": "⚠️ Illustrative sample — placeholder data, not real facts about any real company.",
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


def _blank_if_unknown(v):
    return "" if (v is None or str(v).strip().lower() in ("", "unknown")) else str(v)


def _needs_confirmation(company):
    """True when the live build is unsure about IDENTITY — so we ask the user to confirm
    instead of silently carrying 'unknown' into the interrogation."""
    def unsure(v):
        return v is None or str(v).strip().lower() in ("", "unknown")
    return (unsure(company.get("company")) or unsure(company.get("sector"))
            or company.get("_build_status") in ("thin", "offline"))


def _begin_live(ss, text):
    """Identify + build a live company from the user's text. If the build is confident, hand
    it straight to Stage 1; if not, stash it as a draft and ask the user to confirm."""
    try:
        with st.spinner("🌐 Identifying the company and building a live ESG profile…"):
            company, _meta = datasource.build_live_company(
                text, use_rag=bool(ss.get("rag_enabled", True)), k=int(ss.get("rag_top_k", 5))
            )
    except core.LLMConfigError as e:
        st.error(str(e))
        return
    except Exception as e:  # noqa: BLE001 — keep a live flop friendly.
        st.warning("⚠️ Couldn't build a live profile just now — usually a network blip or a "
                   "wrong model name (try setting DEEPSEEK_MODEL).")
        with st.expander("Details"):
            st.code(f"{type(e).__name__}: {e}")
        return
    if _needs_confirmation(company):
        ss.company_draft = company       # park it; the confirm panel will commit it
        ss.live_question = text
    else:
        ss.company = company
        ss.pending_user_input = text     # Stage 1 narrows this as the first turn
    st.rerun()


def _confirm_company_panel(ss):
    """Low-confidence live build → let the user confirm/correct identity before Stage 1."""
    draft = ss.company_draft
    st.subheader("🔎 Confirm the company")
    st.caption("I fetched what I could but wasn't fully sure about some details — confirm or "
               "correct them so the interrogation is anchored to the right company and sector. "
               "Leave a box blank only if it's genuinely unknown.")
    name = st.text_input("Company", value=_blank_if_unknown(draft.get("company")),
                         placeholder="e.g. DBS Bank Ltd")
    c1, c2 = st.columns(2)
    ticker = c1.text_input("Ticker", value=_blank_if_unknown(draft.get("ticker")),
                           placeholder="e.g. SGX:D05")
    sector = c2.text_input("Sector", value=_blank_if_unknown(draft.get("sector")),
                           placeholder="e.g. Financials — Banks")
    srcs = draft.get("_sources") or []
    if srcs:
        with st.expander(f"🔗 What I found ({len(srcs)} source(s))"):
            for s in srcs[:6]:
                t, u = (s.get("title") or s.get("url") or "source"), (s.get("url") or "")
                st.markdown(f"- [{t}]({u})" if u else f"- {t}")
    go, cancel = st.columns([3, 1])
    if go.button("Confirm & interrogate →", type="primary", use_container_width=True):
        draft["company"] = name.strip() or "unknown"
        draft["ticker"] = ticker.strip() or "unknown"
        draft["sector"] = sector.strip() or "unknown"
        ss.company = draft
        ss.pending_user_input = ss.get("live_question") or draft["company"]
        ss.pop("company_draft", None)
        ss.pop("live_question", None)
        st.rerun()
    if cancel.button("↺ Cancel", use_container_width=True):
        ss.pop("company_draft", None)
        ss.pop("live_question", None)
        st.rerun()


def _start_panel(ss):
    """Shown before a company is loaded: live-chat entry (or a nudge to upload)."""
    mode = ss.get("data_mode", "live")
    if mode == "upload":
        st.subheader("📤 Upload your ESG data")
        st.write("Use the **uploader in the sidebar** (`.json`, `.csv`, or `.txt`). Once it "
                 "loads, ask your question here.")
        st.caption("`.json` is used as-is (a template is in the sidebar). `.csv`/`.txt` are "
                   "read by the AI — grounded only in your file.")
        return

    st.subheader("Start an analysis")
    st.write("Tell the radar what you want to invest in or understand. It identifies the "
             "company, builds a **live** ESG profile from public sources, then interrogates "
             "your question.")
    examples = ["I want to invest in Nvidia",
                "Is Tesla a sustainable buy?",
                "Should I worry about DBS Bank's governance?"]
    cols = st.columns(len(examples))
    for i, ex in enumerate(examples):
        if cols[i].button(ex, key=f"ex_{i}", use_container_width=True):
            _begin_live(ss, ex)
    txt = st.chat_input("e.g. “I want to invest in Nvidia”")
    if txt:
        _begin_live(ss, txt)


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


def _snap_line(snap):
    """One-line at-a-glance card summary: band+rating · E·S·G arrows · red flags · coverage."""
    rating = snap.get("rating") if _known(snap.get("rating")) else "no rating yet"
    ar = snap.get("arrows", {})
    cov = f'{snap.get("coverage", 0)}/{snap.get("coverage_total", 10)}'
    return (f'{_band_emoji(snap)} **{rating}**  ·  E{ar.get("E","·")} S{ar.get("S","·")} '
            f'G{ar.get("G","·")}  ·  🚩 {snap.get("red_flags", 0)}  ·  ▣ {cov}')


def _pin(ss, company):
    """Compute a snapshot for an already-built CompanyData and add it to the monitored board."""
    snap = datasource.snapshot_from_company(company)
    tk = company.get("ticker") or company.get("_constituent_ticker") or snap.get("ticker") or "unknown"
    ss.snapshots[tk] = {"company": company, "snap": snap, "answer": None, "narrowed_q": None}
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
    """Return the ticker of a constituent's snapshot, building+pinning it first if needed."""
    tk = constituent.get("ticker") or constituent.get("id")
    if tk in ss.snapshots:
        return tk
    return _build_and_pin_constituent(ss, constituent)


def _add_from_text(ss, text):
    """Chatbot 'add a stock' path: resolve free text onto an ASEAN constituent, build, pin."""
    c = universe.resolve(text)
    if not c:
        st.warning(f"“{text.strip()}” isn't in the ASEAN universe (52 ESG improvers). Try a name "
                   "or ticker like **DBS**, **BCA**, **PTT**, **Maybank** — or browse the grid below.")
        return
    if (c.get("ticker") or c.get("id")) in ss.snapshots:
        st.info(f"📌 **{c['company']}** is already on your board.")
        return
    tk = _build_and_pin_constituent(ss, c)
    if tk:
        st.success(f"📌 Now monitoring **{c['company']}** ({c['ticker']}). Open it for the deep dive.")


def _default_nq(company):
    """A sensible default NarrowedQuestion so a deep dive can 'compete' without interrogation."""
    name = company.get("company", "this company")
    return contracts.coerce_narrowed_question({
        "narrowed_question": (f"Is {name}'s ESG profile as solid as its static rating and "
                              "2019–2023 improvement imply, once you weigh the live AI / news / "
                              "behaviour signals the rating can't see?"),
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


def _render_monitored_board(ss):
    """The ⭐ Monitored watchlist — chatbot-added cards, click to deep-dive."""
    st.markdown(f"#### ⭐ Monitored  ·  {len(ss.watchlist)} compan"
                f"{'y' if len(ss.watchlist) == 1 else 'ies'}")
    if not ss.watchlist:
        st.info("Nothing monitored yet — add a company via the chat above, or **➕ Monitor** one "
                "from the ASEAN universe below.")
        return
    ncol = 3
    tickers = list(ss.watchlist)
    for i in range(0, len(tickers), ncol):
        cols = st.columns(ncol)
        for j, tk in enumerate(tickers[i:i + ncol]):
            with cols[j]:
                with st.container(border=True):
                    entry = ss.snapshots.get(tk)
                    if entry:
                        snap = entry["snap"]
                        st.markdown(f"**{snap['company']}**")
                        st.caption(f"`{snap['ticker']}` · {snap.get('country','—')} · {snap.get('sector','—')}")
                        st.markdown(_snap_line(snap))
                        b1, b2, b3 = st.columns([3, 2, 1])
                        if b1.button("🔬 Deep dive", key=f"mdd_{tk}", use_container_width=True,
                                     type="primary"):
                            _open_deep_dive(ss, tk)
                        if b2.button("🔄", key=f"mrf_{tk}", use_container_width=True,
                                     help="Rebuild the live snapshot"):
                            c = universe.get(tk)
                            if c:
                                _build_and_pin_constituent(ss, c)
                            st.rerun()
                        if b3.button("✕", key=f"mun_{tk}", use_container_width=True,
                                     help="Stop monitoring"):
                            _unpin(ss, tk)
                            st.rerun()
                    else:  # pinned (persisted from disk) but not built this session
                        c = universe.get(tk)
                        st.markdown(f"**{(c or {}).get('company', tk)}**")
                        st.caption(f"`{tk}` · 📌 pinned — snapshot not built yet")
                        b1, b2 = st.columns([3, 1])
                        if b1.button("⛏️ Build snapshot", key=f"bld_{tk}", use_container_width=True,
                                     type="primary", disabled=c is None):
                            if c:
                                _build_and_pin_constituent(ss, c)
                            st.rerun()
                        if b2.button("✕", key=f"pun_{tk}", use_container_width=True):
                            _unpin(ss, tk)
                            st.rerun()


# --- command center: CSS + small helpers ----------------------------------- #
_CC_CSS = """
<style>
.cc-title{font-size:30px;font-weight:800;color:#34d399;line-height:1.1;letter-spacing:.3px;}
.cc-sub2{color:#8aa0b8;font-size:13px;margin-top:2px;}
.cc-live{float:right;background:#123a2a;color:#34d399;border:1px solid #1f7a55;border-radius:20px;
  padding:4px 14px;font-weight:700;font-size:13px;}
.cc-h{color:#34d399;font-weight:700;font-size:15px;margin:2px 0 6px;}
.cc-muted{color:#8aa0b8;font-size:12px;margin-top:4px;}
.cc-card,.cc-pill{background:#16203a;border:1px solid rgba(255,255,255,.08);border-radius:14px;
  padding:12px 14px;margin-bottom:10px;}
.cc-pill{min-height:104px;}
.cc-pill.cc-fast{border:2px solid #f59e0b;}
.cc-pill-h{color:#aab6c6;font-size:13px;}
.cc-big{font-size:32px;font-weight:800;line-height:1.15;margin-top:2px;}
.cc-pill.cc-fast .cc-big{color:#f59e0b !important;}
.cc-pos{color:#34d399;} .cc-neg{color:#f87171;} .cc-flat{color:#e6eaf1;} .cc-warn{color:#f59e0b;}
.cc-pill-sub{color:#8aa0b8;font-size:12px;margin-top:4px;}
.cc-hwwrap{background:#16203a;border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px 14px;}
.cc-hw{display:flex;align-items:center;gap:8px;margin:7px 0;}
.cc-hw-name{flex:0 0 38%;color:#e6eaf1;font-size:13px;font-weight:600;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;}
.cc-new{background:#1f7a55;color:#d6ffe9;font-style:normal;font-size:10px;padding:1px 5px;
  border-radius:6px;margin-left:5px;}
.cc-hw-track{flex:1;background:rgba(255,255,255,.08);border-radius:6px;height:13px;overflow:hidden;}
.cc-hw-fill{height:13px;border-radius:6px;}
.cc-hw-fill.cc-pos{background:#34d399;} .cc-hw-fill.cc-neg{background:#f87171;}
.cc-hw-val{flex:0 0 48px;text-align:right;font-size:13px;font-weight:700;}
.cc-class{border-radius:14px;padding:12px 16px;margin-top:6px;border-left:5px solid #34d399;}
.cc-class-good{background:#10301f;border-left-color:#34d399;}
.cc-class-bad{background:#3a1414;border-left-color:#f87171;}
.cc-class-neutral{background:#16203a;border-left-color:#60a5fa;}
.cc-class-h{font-size:15px;color:#cbd6e2;font-weight:600;}
.cc-class-h b{color:#f59e0b;font-size:17px;letter-spacing:.5px;}
.cc-class-line{color:#cdd8e4;font-size:13px;margin-top:5px;line-height:1.45;}
.cc-sigwrap{background:#16203a;border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:6px 14px;}
.cc-sig{display:flex;justify-content:space-between;align-items:center;padding:8px 0;
  border-bottom:1px solid rgba(255,255,255,.06);font-size:13px;color:#cbd6e2;}
.cc-sig:last-child{border-bottom:0;} .cc-sig b{font-size:14px;}
.cc-panel-body{background:#16203a;border:1px solid rgba(255,255,255,.08);border-radius:14px;
  padding:12px 14px;color:#cdd8e4;font-size:13px;line-height:1.5;}
.cc-bubble{border-radius:10px;padding:7px 11px;margin:5px 0;font-size:13px;line-height:1.4;}
.cc-bubble-u{background:#16203a;color:#cbd6e2;border:1px solid rgba(255,255,255,.08);}
.cc-bubble-a{background:#241a44;color:#e7defc;border:1px solid #5b46a8;}
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


def _chat_act(ss, text, path):
    """The AI assistant: parse a line into filter / focus / add actions and log a short reply."""
    t = (text or "").strip()
    if not t:
        return
    low = t.lower()
    ss.chat_log.append({"role": "user", "text": t})
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
        ss.focus_ticker = comp["ticker"]
        comp["_new"] = True
        peers = [c for c in universe.constituents(path) if c["sector"] == comp["sector"]]
        avg, _ = metrics.average_esg(peers)
        d = metrics.num((comp.get("momentum") or {}).get("digital_ai"))
        if not ss.get("demo_mode") and comp["ticker"] not in ss.watchlist:
            _build_and_pin_constituent(ss, comp)      # real mode: also build a live snapshot
        peer_txt = (f" — scored against {_short_sector(comp['sector'])} peers, "
                    f"Digital/AI {metrics.fmt_pct(d)} vs avg ESG {avg}." if avg is not None else ".")
        ss.chat_log.append({"role": "assistant",
                            "text": f"Focused {comp['company']}{peer_txt} Added to the grid."})
        return

    if bits:
        ss.chat_log.append({"role": "assistant", "text": "Filtered to " + " · ".join(bits) + "."})
    else:
        ss.chat_log.append({"role": "assistant",
                            "text": "I can filter (“show banks”, “Singapore”, “all ASEAN”) or focus "
                                    "a company (“DemoBank”, “add GreenChip Bank”)."})


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
    hw, _, _ = metrics.hidden_winners(filtered, top_n=1)   # else the strongest live signal in view
    if hw:
        return universe.get(hw[0]["ticker"], path) or (filtered[0] if filtered else None)
    return filtered[0] if filtered else None


def _why_wrong(focused):
    if not focused:
        return "Add or focus a company to see where its live signal diverges from the stale rating."
    s = focused.get("live_signals") or {}
    d = metrics.num((focused.get("momentum") or {}).get("digital_ai"))
    cls = metrics.classify(focused)
    name = focused.get("company", "This company")
    score, as_of = focused.get("esg_score"), (focused.get("esg_as_of") or "")
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
def _render_pillars(filtered):
    cols = st.columns(4)
    for col, p in zip(cols, metrics.pillar_momentum(filtered)):
        cls = "cc-pill cc-fast" if p["fast"] else "cc-pill"
        col.markdown(
            f'<div class="{cls}"><div class="cc-pill-h">{_esc(p["label"])}</div>'
            f'<div class="cc-big {_sign_class(p["value"])}">{_esc(metrics.fmt_pct(p["value"]))}</div>'
            f'<div class="cc-pill-sub">{p["arrow"]} {_esc(p["trend"])}</div></div>',
            unsafe_allow_html=True)


def _render_momentum_chart(ss, filtered):
    st.markdown('<div class="cc-h">ESG momentum · 90 days</div>', unsafe_allow_html=True)
    series = metrics.momentum_series(filtered)
    if not series:
        st.caption("No momentum data for this filter yet.")
        return
    colors = {"digital_ai": "#f59e0b", "environment": "#34d399",
              "governance": "#f87171", "social": "#60a5fa"}
    go = _go()
    if go:
        fig = go.Figure()
        for key, vals in series.items():
            fig.add_trace(go.Scatter(
                y=vals, mode="lines", name=metrics.PILLAR_LABEL[key],
                line=dict(color=colors.get(key, "#9aa6b2"), width=3),
                hovertemplate=metrics.PILLAR_LABEL[key] + ": %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=240, margin=dict(l=8, r=8, t=8, b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=10, color="#aab6c6")),
            xaxis=dict(visible=False),
            yaxis=dict(zeroline=True, zerolinecolor="rgba(255,255,255,.2)",
                       gridcolor="rgba(255,255,255,.07)", ticksuffix="%",
                       tickfont=dict(size=9, color="#8aa0b8")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.line_chart({metrics.PILLAR_LABEL[k]: v for k, v in series.items()}, height=240)


def _render_hidden_winners(filtered):
    hw, peer, _ = metrics.hidden_winners(filtered, top_n=5)
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


def _render_classification(focused, cls=None):
    cls = cls or metrics.classify(focused or {})
    tone = {"good": "cc-class-good", "bad": "cc-class-bad", "neutral": "cc-class-neutral"}[cls["tone"]]
    st.markdown(
        f'<div class="cc-class {tone}"><div class="cc-class-h">Classification &nbsp; '
        f'<b>{_esc(cls["label"])}</b> &nbsp;<span class="cc-muted">· '
        f'{_esc((focused or {}).get("company", "—"))}</span></div>'
        f'<div class="cc-class-line">{_esc(cls["line"])}</div></div>', unsafe_allow_html=True)


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


def _render_bars(title, subtitle, rows, *, maxabs, suffix="", footer=""):
    """Shared horizontal-bar panel (hidden winners / evidence leaders)."""
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
        new = '<em class="cc-new">new</em>' if r.get("is_new") else ""
        val = metrics.fmt_pct(r["value"]) if suffix == "%" else f'{r["value"]}{suffix}'
        out.append(f'<div class="cc-hw"><div class="cc-hw-name">{_esc(r["company"])}{new}</div>'
                   f'<div class="cc-hw-track"><div class="cc-hw-fill {sign}" style="width:{w}%"></div></div>'
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
def _cc_left(ss, uni, cons, filtered, sectors, countries, path):
    st.markdown('<div class="cc-h">Filters</div>', unsafe_allow_html=True)
    st.selectbox("Industry", sectors, key="flt_sector", format_func=_short_sector)
    st.selectbox("Country", countries, key="flt_country",
                 format_func=lambda c: "All ASEAN" if c == "All" else c)
    st.caption(f"Universe: {len(cons)} listed · showing {len(filtered)}")

    avg, an = metrics.average_esg(filtered)
    st.markdown(
        f'<div class="cc-card"><div class="cc-pill-h">Avg ESG · {_esc(_short_sector(ss.flt_sector))}'
        f'</div><div class="cc-big cc-flat">{avg if avg is not None else "—"}</div>'
        f'<div class="cc-muted">{("mean static score · " + str(an) + " names") if avg is not None else "awaiting data"}</div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="cc-h">⭐ Monitored</div>', unsafe_allow_html=True)
    if ss.watchlist:
        for tk in ss.watchlist:
            e = ss.snapshots.get(tk)
            name = e["snap"]["company"] if e else ((universe.get(tk, path) or {}).get("company") or tk)
            label = f"🔬 {name}" if e else f"⛏️ {name}"
            if st.button(label, key=f"cclm_{tk}", use_container_width=True):
                if e:
                    _open_deep_dive(ss, tk)
                else:
                    c = universe.get(tk, path)
                    if c:
                        _build_and_pin_constituent(ss, c)
                    st.rerun()
    else:
        st.caption("Nothing pinned yet — ask the assistant to *add* a company (real mode), or use "
                   "the browse panel below.")


def _cc_center(ss, filtered, focused):
    _render_pillars(filtered)
    st.write("")
    c1, c2 = st.columns([1.15, 1], gap="medium")
    with c1:
        _render_momentum_chart(ss, filtered)
    with c2:
        _render_hidden_winners(filtered)
    _render_classification(focused)


def _cc_right(ss, filtered, focused, path):
    st.markdown('<div class="cc-h">💬 AI assistant</div>', unsafe_allow_html=True)
    st.caption("Ask me to filter (“show banks”, “Singapore”, “all ASEAN”) or focus a company.")
    for m in ss.chat_log[-6:]:
        css = "cc-bubble-u" if m["role"] == "user" else "cc-bubble-a"
        st.markdown(f'<div class="cc-bubble {css}">{_esc(m["text"])}</div>', unsafe_allow_html=True)
    with st.form("cc_chat", clear_on_submit=True):
        msg = st.text_input("ask", key="cc_chat_in", label_visibility="collapsed",
                            placeholder="Add a company or ask…")
        sent = st.form_submit_button("Send  ➤", use_container_width=True, type="primary")
    if sent and (msg or "").strip():
        ss.pending_chat = msg.strip()
        st.rerun()

    st.divider()
    _render_live_signals(focused)
    st.divider()
    st.markdown('<div class="cc-h">Why the rating may be wrong</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-panel-body">{_esc(_why_wrong(focused))}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-muted">Focused: {_esc((focused or {}).get("company", "—"))} · '
                f'{len(metrics.live_signals(focused or {}))} signals</div>', unsafe_allow_html=True)

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
    focused = _cc_focused(ss, filtered, path)

    st.markdown(_CC_CSS, unsafe_allow_html=True)
    n, ind = len(cons), len({c["sector"] for c in cons if c["sector"] != "unknown"})
    head_l, head_r = st.columns([4, 1])
    head_l.markdown(f'<div class="cc-title">🛰️ ASEAN ESG Momentum Radar</div>'
                    f'<div class="cc-sub2">{_esc(uni.get("as_of", ""))} · {n} listed companies · '
                    f'{ind} industries</div>', unsafe_allow_html=True)
    head_r.markdown('<div class="cc-live">● Live</div>', unsafe_allow_html=True)
    if ss.get("demo_mode"):
        st.caption("🎛️ **Demo data** — fictional companies + invented numbers so the board is alive. "
                   "Toggle it off in the sidebar to drive these panels from the real ASEAN base DB.")
    elif not metrics.has_numbers(cons):
        st.caption("ℹ️ The real universe has no numeric ESG/momentum yet — panels show “awaiting "
                   "data”. Drop scores into `data/asean_universe.json` and they light up.")

    left, center, right = st.columns([1.15, 2.25, 1.4], gap="medium")
    with left:
        _cc_left(ss, uni, cons, filtered, sectors, countries, path)
    with center:
        _cc_center(ss, filtered, focused)
    with right:
        _cc_right(ss, filtered, focused, path)

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
    "view": "dashboard",     # "dashboard" (home) | "deep_dive"
    "active_ticker": None,   # which monitored company the deep dive is showing
    "watchlist": None,       # list of pinned tickers (loaded from disk on first run)
    "snapshots": {},         # ticker -> {"company": ContractB, "snap": {...}, "answer", "narrowed_q"}
    "flt_country": "All",
    "flt_sector": "All",
    "flt_search": "",
    # --- command-center state ---
    "demo_mode": True,       # start in the fictional demo universe so the board is alive on first load
    "focus_ticker": None,    # the company featured in the classification / live-signals / why-wrong panels
    "chat_log": [],          # [{role, text}] for the right-rail AI assistant
    "pending_chat": None,    # a submitted chat line, applied at the TOP of the next run (before widgets)
}
ss = st.session_state
for _k, _v in _DEFAULTS.items():
    ss.setdefault(_k, _v)
if ss.watchlist is None:                       # one-time load of persisted pins
    ss.watchlist = _load_watchlist()

# --- sidebar = the control panel ------------------------------------------- #
# Every widget owns its state via an explicit key= (NO value-from-session_state round-trip),
# so a single click registers — the old pattern changed each widget's identity and lagged.
with st.sidebar:
    st.markdown("### 🛰️ ESG Radar")
    st.caption("Control panel")
    st.toggle("🌗 Dark mode", key="dark_mode", help="Switch between light and dark.")

    st.divider()
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

_inject_theme("dark" if ss.get("dark_mode") else "light")

# --- header ----------------------------------------------------------------- #
st.title("🛰️ ASEAN ESG Momentum Radar")
st.caption(
    "Monitors a basket of ASEAN ESG improvers and competes with their stale ratings — "
    "disagreeing with the live signal the rating can't see (AI adoption, news/behaviour, "
    "real-time vs annual-report lag). It never says buy / sell / hold."
)

# --- router: the dashboard (home) or a single-company deep dive -------------- #
if ss.view == "deep_dive" and ss.get("company") is not None:
    _stepper(ss)
    _render_deep_dive(ss)
else:
    ss.view = "dashboard"
    _render_dashboard(ss)
