"""
stage3.py — STAGE 3: Render the answer (the decision tool).
===========================================================
Takes a Stage2Answer (Contract C) and presents it as a clear decision tool, led by the
VERDICT: the one-sentence disagreement, then question → "market view vs reality" → the one
action to take. Render-only — NO LLM call here. Re-reasoning would risk re-wording or
fabricating the verified baton (HARD RULE 2); Stage 3 just displays what Stage 2 verified.

Minimal but intentional polish — CGSI criterion 02 ("simple, clear output"). The coloured
surfaces are custom panels (not stock st.error/info boxes) that wrap cleanly to one column
on narrow screens. All st.* calls live inside render_answer() so the module imports cleanly.
"""

import html


_FIELDS = (
    "question_to_ask", "what_rating_sees", "what_we_see",
    "check_before_monday", "competes_summary",
)

# Scoped styling for the decision panels. Left-accent + faint tint reads as designed rather
# than stock-Streamlit; the .esg-vs flex container wraps to a single column under ~600px so
# the "market view vs reality" pair stacks cleanly on a phone (no fixed columns to squish).
_CSS = """
<style>
.esg-vs{display:flex;flex-wrap:wrap;gap:.75rem;margin:.35rem 0 .25rem;}
.esg-panel{flex:1 1 280px;border-left:5px solid var(--c,#888);border-radius:10px;
  padding:.8rem 1rem;background:var(--bg,rgba(136,136,136,.08));}
.esg-panel .esg-h{font-weight:600;font-size:.9rem;opacity:.85;margin-bottom:.3rem;}
.esg-panel .esg-b{line-height:1.5;margin:0;white-space:pre-wrap;}
.esg-verdict{--c:#e0584f;--bg:rgba(224,88,79,.10);border-left-width:7px;}
.esg-rating {--c:#5b8def;--bg:rgba(91,141,239,.10);}
.esg-we     {--c:#15a39a;--bg:rgba(21,163,154,.12);}
.esg-check  {--c:#2faa5e;--bg:rgba(47,170,94,.12);}
</style>
"""


def _panel(st, cls, head, body):
    """One styled decision panel. Body is escaped — it's model output, never raw HTML."""
    st.markdown(
        f'<div class="esg-panel {cls}"><div class="esg-h">{head}</div>'
        f'<p class="esg-b">{html.escape(str(body or "unknown"))}</p></div>',
        unsafe_allow_html=True,
    )


def _card_text(answer, company):
    """Plain-text rendering of the four-line card — the artifact users copy / export."""
    if company:
        subj = (f"{company.get('company', '—')} ({company.get('ticker', '—')}) · "
                f"{company.get('sector', '—')}")
    else:
        subj = "—"
    return (
        f"ASEAN ESG Momentum Radar — {subj}\n"
        "(Illustrative scenario; placeholder data, not real facts about any real company.)\n\n"
        f"VERDICT: {answer.get('competes_summary', 'unknown')}\n\n"
        f"Question: {answer.get('question_to_ask', 'unknown')}\n"
        f"What the rating sees: {answer.get('what_rating_sees', 'unknown')}\n"
        f"What we see: {answer.get('what_we_see', 'unknown')}\n"
        f"Check before Monday: {answer.get('check_before_monday', 'unknown')}\n"
    )


def _render_export(st, answer, company):
    """Copy/export the card so people leave with the artifact (feels like a real tool)."""
    with st.expander("📋 Copy / export this card"):
        text = _card_text(answer, company)
        st.code(text, language=None)  # st.code ships a built-in copy-to-clipboard button
        st.download_button(
            "⬇️ Download as .txt", data=text,
            file_name="esg_momentum_card.txt", mime="text/plain",
        )


def render_answer(answer, company=None, debug=False):
    """Render a Stage2Answer (Contract C) dict as the decision panel.

    Leads with the VERDICT (competes_summary) — criterion 03's "show me something I
    don't know" moment — then question → what the rating sees → what we see → the check.
    Render-only: it never re-words or re-reasons the verified baton (HARD RULE 2).
    """
    import streamlit as st

    st.markdown(_CSS, unsafe_allow_html=True)

    if company:
        st.caption(
            f"Subject: **{company.get('company', '—')}** · "
            f"`{company.get('ticker', '—')}` · {company.get('sector', '—')}  "
            "·  ⚠️ Illustrative scenario — placeholder data modelled on a real-world "
            "pattern, not real facts about any real company."
        )

    # Surface a failed / empty Stage 2 instead of a wall of "unknown".
    all_unknown = all((answer.get(k) or "unknown") == "unknown" for k in _FIELDS)
    failed = bool(answer.get("_parse_failed") or all_unknown)
    if failed:
        st.warning(
            "Stage 2 couldn't produce an answer from the data. This usually means the "
            f"narrowed question is about a company or issue the loaded data "
            f"({company.get('company') if company else 'the dataset'}) doesn't cover — "
            "the radar carries one company's data file. Try a question about that company."
        )
    if (debug or answer.get("_parse_failed")) and answer.get("_raw") is not None:
        with st.expander("🐞 raw Stage 2 output"):
            st.code(answer["_raw"] or "<empty>")

    # --- THE VERDICT, FIRST ------------------------------------------------- #
    # A decision tool leads with the punchline. Skip it on failure — the warning
    # above already explains why there's nothing to assert.
    if not failed:
        st.markdown("### ⚔️ The verdict — where we disagree with the rating")
        _panel(st, "esg-verdict", "⚔️ Where we compete", answer.get("competes_summary", "unknown"))
        st.divider()

    st.subheader("🎯 The question")
    st.write(answer.get("question_to_ask", "unknown"))

    st.divider()
    st.markdown("### Market view vs. reality")
    st.markdown(
        '<div class="esg-vs">'
        '<div class="esg-panel esg-rating"><div class="esg-h">📊 What the rating sees</div>'
        f'<p class="esg-b">{html.escape(str(answer.get("what_rating_sees", "unknown")))}</p></div>'
        '<div class="esg-panel esg-we"><div class="esg-h">🛰️ What we see</div>'
        f'<p class="esg-b">{html.escape(str(answer.get("what_we_see", "unknown")))}</p></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("#### ✅ Check before Monday")
    _panel(st, "esg-check", "✅ Do this first", answer.get("check_before_monday", "unknown"))

    if not failed:
        _render_export(st, answer, company)

    st.caption("We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.")
