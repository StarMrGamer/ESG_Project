"""
app.py — Streamlit shell that wires the 3-stage relay.
======================================================
Runs the pipeline in sequence, each stage a FRESH DeepSeek agent handing the next only its
verified contract baton:

    vague question
      → Stage 1 interrogates ............ emits NarrowedQuestion (Contract A)
      → Stage 2 competes over data ...... emits Stage2Answer    (Contract C)
      → Stage 3 renders the answer ...... the decision panel

Stage 2 sees ONLY the NarrowedQuestion + CompanyData — never Stage 1's chat. This module
owns all st.session_state; each stage owns its own logic/UI. It also owns the cross-cutting
UX: a progress stepper, a first-load intro, clickable demos, a streaming Stage-2 status,
friendly error recovery, and a light "ask another" reset.

    pip install -r requirements.txt
    export DEEPSEEK_API_KEY="sk-..."
    streamlit run app.py
"""

import json
import os

import streamlit as st

import contracts
import core
import stage1
import stage2
import stage3

# --- company catalogue (Feature 2) ------------------------------------------ #
# label -> Contract-B filename in data/. Each file is validated OFFLINE by selftest.py.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")
HERO_FILE = "hero_company.json"
COMPANIES = {
    "DemoBank SG (illustrative)": HERO_FILE,
    "GreenChip Semi (illustrative)": "company_2.json",
}

# Stage-2 progress phases: as each Contract-C key appears in the streamed JSON, advance the
# status. This narrates the multi-second wait against REAL progress (not a fake timer).
_S2_PHASES = [
    ("what_rating_sees", "📊 Reading the stale rating…"),
    ("what_we_see", "🛰️ Checking the live signal the rating can't see…"),
    ("check_before_monday", "✅ Framing the check for your mandate…"),
    ("competes_summary", "⚔️ Forming the disagreement…"),
]

# Transient UI flags (not relay batons) that the Reset buttons should also clear.
_TRANSIENT = ("pending_user_input", "s2_retry")


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
            cells.append(f":violet[**🔵 {label}**]")  # purple = the AI-reasoning accent
        else:
            cells.append(f":gray[⚪ {label}]")
    st.markdown("  →  ".join(cells))


def _intro(ss):
    """A one-look orientation for a cold user — expanded only on first load."""
    with st.expander("ℹ️ How this works (30-second read)", expanded=not ss.get("s1_msgs")):
        st.markdown(
            "- **It interrogates first.** Instead of a dashboard, it asks a few sharp "
            "questions to pin down what you *really* want to know.\n"
            "- **It challenges weak framing.** Worried about a bank's carbon? It will push "
            "back — for a bank, governance & data security move value, not carbon.\n"
            "- **Then it competes.** It disagrees with the stale ESG rating using a live "
            "signal the rating can't see. 💡 The sharpest path steers toward the "
            "**undisclosed-AI** blind-spot.\n"
            "- It never says buy / sell / hold, and never gives a score."
        )


def _run_stage2(ss, nq, company):
    """Run Stage 2 with a streaming status, recovering gracefully from a live flop."""
    ok = False
    try:
        with st.status("Competing against the stale rating…", expanded=True) as status:
            seen = set()

            def on_delta(_delta, accumulated):
                for key, label in _S2_PHASES:
                    if key not in seen and f'"{key}"' in accumulated:
                        seen.add(key)
                        status.update(label=label)

            ss.answer = stage2.reason(nq, company, on_delta=on_delta)
            status.update(label="Done — here's where we compete.", state="complete")
        ok = True
    except core.LLMConfigError as e:
        st.error(str(e))
    except Exception as e:  # noqa: BLE001 — friendly recovery, never a raw traceback.
        st.warning(
            "⚠️ Something went wrong reaching the model — usually a network blip or a "
            "wrong model name (try setting DEEPSEEK_MODEL)."
        )
        with st.expander("Details"):
            st.code(f"{type(e).__name__}: {e}")
        if st.button("↻ Retry", key="s2_retry_btn"):
            ss["s2_retry"] = True
            st.rerun()
    if ok:
        st.rerun()  # re-render cleanly into Stage 3 with the stepper advanced.


st.set_page_config(page_title="ASEAN ESG Momentum Radar", page_icon="🛰️", layout="centered")

# --- session state (this module owns it) ----------------------------------- #
_DEFAULTS = {
    "s1_msgs": [],      # Stage-1 conversation (its own list — not shared downstream)
    "s1_trail": [],     # parsed envelopes = the visible reasoning trail
    "s1_turns": 0,      # questions asked so far
    "s1_done": False,   # Stage 1 finished?
    "narrowed_q": None,  # Contract A baton
    "answer": None,     # Contract C baton
}
ss = st.session_state
for _k, _v in _DEFAULTS.items():
    ss.setdefault(_k, _v)

# --- sidebar ---------------------------------------------------------------- #
with st.sidebar:
    # Company selector (Feature 2) — the FIRST control. Switching company invalidates the
    # relay batons: a narrowed question + answer belong to the company that produced them,
    # so we clear them on change (company_file is kept OUT of _DEFAULTS so it survives).
    st.subheader("Company under analysis")
    choice = st.selectbox("Dataset", list(COMPANIES), index=0, label_visibility="collapsed")
    chosen_file = COMPANIES[choice]
    if ss.get("company_file") != chosen_file:
        for _k in list(_DEFAULTS) + list(_TRANSIENT):
            ss.pop(_k, None)
        ss["company_file"] = chosen_file
        st.rerun()
    company = core.load_company_data(os.path.join(DATA_DIR, chosen_file))

    st.markdown(f"**{company['company']}** · `{company['ticker']}`")
    st.caption(company["sector"])
    st.caption("⚠️ Sample/placeholder data — not real facts about any real company.")
    st.divider()
    st.subheader("The four axes")
    for icon, name, desc in stage1.AXES.values():
        st.markdown(f"{icon} **{name}** — {desc}")
    st.divider()
    st.subheader("Demo inputs (vague on purpose)")
    st.caption("Tap one to start — the AI must NARROW it, not accept it.")
    _demo_locked = bool(ss.s1_msgs) or ss.s1_done
    for _i, _d in enumerate(stage1.DEMO_INPUTS):
        if st.button(_d, key=f"demo_{_i}", use_container_width=True, disabled=_demo_locked):
            ss["pending_user_input"] = _d
            st.rerun()
    if _demo_locked:
        st.caption("_Reset to try a different opener._")
    st.divider()
    ss["debug"] = st.checkbox("🐞 Show raw model output", value=bool(ss.get("debug")))
    # Feature 1 — offline demo-mode: render the full pipeline from the VERIFIED fixtures with
    # zero network calls, so the Compete moment survives a dead API or venue Wi-Fi. Seeding
    # BOTH batons skips Stage 1's live calls too. Gated to the hero company, since the
    # fixtures are ITS verified batons (a second company would need its own fixture pair).
    if chosen_file == HERO_FILE:
        if st.button("🎬 Load verified demo (offline, no network)", use_container_width=True):
            with open(os.path.join(FIXTURES_DIR, "narrowed_question.json"), encoding="utf-8") as _f:
                ss.narrowed_q = contracts.coerce_narrowed_question(json.load(_f))
            with open(os.path.join(FIXTURES_DIR, "stage2_answer.json"), encoding="utf-8") as _f:
                ss.answer = contracts.coerce_stage2_answer(json.load(_f))
            ss.s1_done = True
            st.rerun()
        st.caption("Renders the full pipeline from verified fixtures — bulletproof if the network drops.")
    if st.button("↺ Reset"):
        for _k in list(_DEFAULTS) + list(_TRANSIENT):
            ss.pop(_k, None)
        st.rerun()

# --- header ----------------------------------------------------------------- #
st.title("🛰️ ASEAN ESG Momentum Radar")
st.caption(
    "It interrogates, then competes — disagreeing with the stale rating using a signal "
    "the rating can't see. It never says buy / sell / hold."
)
_stepper(ss)
st.info(
    f"📍 Loaded company: **{company['company']}** ({company['sector']}). "
    "This radar analyses one company at a time — ask about this one."
)
_intro(ss)

# --- Stage 1: interrogate --------------------------------------------------- #
st.header("1 · Interrogate")
stage1.render(ss, company)

# --- Stage 1 baton + Stage 2 hand-off --------------------------------------- #
if ss.s1_done and ss.narrowed_q:
    nq = ss.narrowed_q
    st.success("**Narrowed question (Stage 1 → baton):**\n\n" + nq["narrowed_question"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Mandate", nq["mandate"])
    c2.metric("Sector", nq["sector"])
    c3.metric("Horizon", nq["horizon"])

    st.header("2 · Compete over data")
    if ss.answer is None:
        st.caption(
            "A FRESH DeepSeek agent now reasons over Layer A + Layer B. It sees only the "
            "narrowed-question baton above — not the interrogation chat."
        )
        st.markdown("👉 **Next:** reason over the data to see where we disagree with the rating.")
        clicked = st.button("Reason over the data →", type="primary")
        if clicked or ss.pop("s2_retry", False):
            _run_stage2(ss, nq, company)

    if ss.answer is not None:
        st.header("3 · The competing answer")
        stage3.render_answer(ss.answer, company, debug=bool(ss.get("debug")), narrowed=ss.narrowed_q)
        if st.button("🔄 Ask another question about this company"):
            for _k in list(_DEFAULTS) + list(_TRANSIENT):
                ss.pop(_k, None)
            st.rerun()
