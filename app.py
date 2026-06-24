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

import json
import os

import streamlit as st

import contracts
import core
import datasource
import stage1
import stage2
import stage3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")
SAMPLE_FILE = os.path.join(DATA_DIR, "hero_company.json")  # offline/demo safety net + test fixture

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


def _reset(ss):
    """Clear the whole analysis (company + relay batons) back to the start panel."""
    for _k in list(_DEFAULTS) + list(_TRANSIENT):
        ss.pop(_k, None)
    st.rerun()


# --------------------------------------------------------------------------- #
#  PAGE
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="ASEAN ESG Momentum Radar", page_icon="🛰️", layout="centered")

_DEFAULTS = {
    "company": None,    # Contract B (live-built / uploaded / sample) — None until chosen
    "s1_msgs": [],
    "s1_trail": [],
    "s1_turns": 0,
    "s1_done": False,
    "narrowed_q": None,
    "answer": None,
}
ss = st.session_state
for _k, _v in _DEFAULTS.items():
    ss.setdefault(_k, _v)

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
                ss.company = company_up
                st.success(f"Loaded **{company_up.get('company', up.name)}** ({meta['mode']}).")
                st.rerun()
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
        st.caption("Ask in the chat — e.g. *“I want to invest in Nvidia.”*")

    st.divider()
    st.markdown("**Retrieval (RAG)**")
    st.toggle("Live web retrieval", value=True, key="rag_enabled",
              help="Fetch DuckDuckGo results + its AI summary, rank them (TF-IDF), and let the "
                   "agent interpret them to ground the reasoning.")
    st.slider("Sources to ground on", 3, 10, 5, key="rag_top_k")

    st.divider()
    b_new, b_sample = st.columns(2)
    if b_new.button("↺ New", use_container_width=True, help="Start a new analysis."):
        _reset(ss)
    if b_sample.button("🎬 Sample", use_container_width=True,
                       disabled=not os.path.exists(SAMPLE_FILE),
                       help="Load the offline demo (no network or key needed)."):
        sample = core.load_company_data(SAMPLE_FILE)
        sample["_origin"] = "sample"
        ss.company = sample
        with open(os.path.join(FIXTURES_DIR, "narrowed_question.json"), encoding="utf-8") as _f:
            ss.narrowed_q = contracts.coerce_narrowed_question(json.load(_f))
        with open(os.path.join(FIXTURES_DIR, "stage2_answer.json"), encoding="utf-8") as _f:
            ss.answer = contracts.coerce_stage2_answer(json.load(_f))
        ss.s1_done = True
        st.rerun()
    st.toggle("🐞 Debug (raw output)", key="debug")

_inject_theme("dark" if ss.get("dark_mode") else "light")

# --- header ----------------------------------------------------------------- #
st.title("🛰️ ASEAN ESG Momentum Radar")
st.caption(
    "It interrogates, then competes — disagreeing with the stale rating using the live signal "
    "+ history it can't see, grounded in sources it fetches. It never says buy / sell / hold."
)
_stepper(ss)

company = ss.get("company")

# --- before a company is chosen: confirm a low-confidence build, else start -- #
if company is None:
    if ss.get("company_draft"):
        _confirm_company_panel(ss)
    else:
        _start_panel(ss)
    st.stop()

# --- a company is loaded: run the relay ------------------------------------- #
_company_header(company)
st.divider()

st.header("1 · Interrogate")
stage1.render(ss, company)

if ss.s1_done and ss.narrowed_q:
    nq = ss.narrowed_q
    st.success("**Narrowed question (Stage 1 → baton):**\n\n" + nq["narrowed_question"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Mandate", nq["mandate"])
    c2.metric("Sector", nq["sector"])
    c3.metric("Horizon", nq["horizon"])

    st.header("2 · Compete over data")
    if ss.answer is None:
        rag_on = bool(ss.get("rag_enabled", True))
        st.caption(
            "A FRESH DeepSeek agent now reasons over Layer A + its history + Layer B, "
            + ("grounded by context it fetches live (RAG). " if rag_on else "")
            + "It sees only the narrowed-question baton above — not the interrogation chat."
        )
        st.markdown(
            "👉 **Next:** "
            + ("retrieve live sources, then reason over the data to see where we disagree — "
               "with its chain of thought." if rag_on else
               "reason over the data to see where we disagree (live retrieval is off).")
        )
        clicked = st.button("Reason over the data →", type="primary")
        if clicked or ss.pop("s2_retry", False):
            _run_stage2(ss, nq, company)

    if ss.answer is not None:
        st.header("3 · The competing answer")
        stage3.render_answer(ss.answer, company, debug=bool(ss.get("debug")), narrowed=ss.narrowed_q)
        if st.button("🔄 Ask another question about this company"):
            for _k in ("s1_msgs", "s1_trail", "s1_turns", "s1_done", "narrowed_q", "answer"):
                ss.pop(_k, None)
            for _k in list(_TRANSIENT):
                ss.pop(_k, None)
            st.rerun()
