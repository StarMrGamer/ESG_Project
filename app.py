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
owns all st.session_state; each stage owns its own logic/UI.

    pip install -r requirements.txt
    export DEEPSEEK_API_KEY="sk-..."
    streamlit run app.py
"""

import streamlit as st

import core
import stage1
import stage2
import stage3

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

company = core.load_company_data()

# --- sidebar ---------------------------------------------------------------- #
with st.sidebar:
    st.subheader("Company under analysis")
    st.markdown(f"**{company['company']}** · `{company['ticker']}`")
    st.caption(company["sector"])
    st.caption("⚠️ Sample/placeholder data — not real facts about any real company.")
    st.divider()
    st.subheader("The four axes")
    for icon, name, desc in stage1.AXES.values():
        st.markdown(f"{icon} **{name}** — {desc}")
    st.divider()
    st.subheader("Demo inputs (vague on purpose)")
    for d in stage1.DEMO_INPUTS:
        st.markdown(f"- _{d}_")
    st.divider()
    ss["debug"] = st.checkbox("🐞 Show raw model output", value=bool(ss.get("debug")))
    if st.button("↺ Reset"):
        for _k in _DEFAULTS:
            ss.pop(_k, None)
        st.rerun()

# --- header ----------------------------------------------------------------- #
st.title("🛰️ ASEAN ESG Momentum Radar")
st.caption(
    "It interrogates, then competes — disagreeing with the stale rating using a signal "
    "the rating can't see. It never says buy / sell / hold."
)
st.info(
    f"📍 Loaded company: **{company['company']}** ({company['sector']}). "
    "This radar analyses one company at a time — ask about this one."
)

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
        if st.button("Reason over the data →", type="primary"):
            try:
                with st.spinner("Competing against the stale rating…"):
                    ss.answer = stage2.reason(nq, company)
                st.rerun()
            except core.LLMConfigError as e:
                st.error(str(e))

    if ss.answer is not None:
        st.header("3 · The competing answer")
        stage3.render_answer(ss.answer, company, debug=bool(ss.get("debug")))
