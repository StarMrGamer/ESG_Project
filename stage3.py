"""
stage3.py — STAGE 3: Render the answer (the decision tool).
===========================================================
Takes a Stage2Answer (Contract C) and presents it as a clear decision tool: the question,
a simple "market view vs reality" panel, the one action to take, and the one-sentence
disagreement. Render-only — NO LLM call here. Re-reasoning would risk re-wording or
fabricating the verified baton (HARD RULE 2); Stage 3 just displays what Stage 2 verified.

Minimal polish, no charts — CGSI criterion 02 ("simple, clear output"). All st.* calls live
inside render_answer() so the module imports cleanly.
"""


_FIELDS = (
    "question_to_ask", "what_rating_sees", "what_we_see",
    "check_before_monday", "competes_summary",
)


def render_answer(answer, company=None, debug=False):
    """Render a Stage2Answer (Contract C) dict as the decision panel."""
    import streamlit as st

    if company:
        st.caption(
            f"Subject: **{company.get('company', '—')}** · "
            f"`{company.get('ticker', '—')}` · {company.get('sector', '—')}  "
            "·  ⚠️ placeholder data, not real facts."
        )

    # Surface a failed / empty Stage 2 instead of a wall of "unknown".
    all_unknown = all((answer.get(k) or "unknown") == "unknown" for k in _FIELDS)
    if answer.get("_parse_failed") or all_unknown:
        st.warning(
            "Stage 2 couldn't produce an answer from the data. This usually means the "
            f"narrowed question is about a company or issue the loaded data "
            f"({company.get('company') if company else 'the dataset'}) doesn't cover — "
            "the radar carries one company's data file. Try a question about that company."
        )
    if (debug or answer.get("_parse_failed")) and answer.get("_raw") is not None:
        with st.expander("🐞 raw Stage 2 output"):
            st.code(answer["_raw"] or "<empty>")

    st.subheader("🎯 The question")
    st.write(answer.get("question_to_ask", "unknown"))

    st.divider()
    st.markdown("### Market view vs. reality")
    left, right = st.columns(2)
    with left:
        st.markdown("#### 📊 What the rating sees")
        st.info(answer.get("what_rating_sees", "unknown"))
    with right:
        st.markdown("#### 🛰️ What we see")
        st.warning(answer.get("what_we_see", "unknown"))

    st.divider()
    st.markdown("#### ✅ Check before Monday")
    st.success(answer.get("check_before_monday", "unknown"))

    st.markdown("#### ⚔️ Where we compete")
    st.error(answer.get("competes_summary", "unknown"))

    st.caption("We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.")
