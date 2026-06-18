"""
stage3.py — STAGE 3: Render the answer (the decision tool).
===========================================================
Takes a Stage2Answer (Contract C) and presents it as a clear decision tool, led by the
VERDICT: the one-sentence disagreement, then the question → "market view vs reality" → the
one action to take, then the EVIDENCE the radar reasoned over (Layer B momentum cards, the
unique AI gap, the near-term catalyst, and where the sources disagree). The 5-Whys
interrogation chain is recapped alongside the answer. Render-only — NO LLM call here.
Re-reasoning would risk re-wording or fabricating the verified baton (HARD RULE 2).

The verdict stays ONE clean line (the brief's weakest criterion is "simple, clear output");
the supporting evidence sits below it. "Sophistication in how it thinks, simplicity in what
it says." Coloured surfaces are custom panels in the pitch-deck palette (navy / green / mint
+ a purple AI accent) and wrap to one column on narrow screens. All st.* calls live inside
render_answer() so the module imports cleanly.
"""

import html
from datetime import date, datetime


_FIELDS = (
    "question_to_ask", "what_rating_sees", "what_we_see",
    "check_before_monday", "competes_summary",
)

# Axis → icon for the 5-Whys recap (kept local so stage3 stays decoupled from stage1).
_AXIS_ICON = {
    "materiality": "🎯", "time_horizon": "⏱️", "mandate": "🧭", "blind_spot": "🕳️",
}

# Scoped styling in the deck palette. Left-accent + faint tint reads as designed; .esg-vs and
# .esg-mom are flex containers that wrap to a single column under ~600px (clean on a phone).
_CSS = """
<style>
.esg-vs{display:flex;flex-wrap:wrap;gap:.75rem;margin:.35rem 0 .25rem;}
.esg-panel{flex:1 1 280px;border-left:5px solid var(--c,#0B2545);border-radius:10px;
  padding:.8rem 1rem;background:var(--bg,rgba(11,37,69,.06));}
.esg-panel .esg-h{font-weight:600;font-size:.9rem;opacity:.85;margin-bottom:.3rem;}
.esg-panel .esg-b{line-height:1.5;margin:0;white-space:pre-wrap;}
.esg-panel ol{margin:.2rem 0 0;padding-left:1.15rem;}
.esg-panel ol li{margin:.18rem 0;line-height:1.4;}
.esg-verdict{--c:#7C5CFC;--bg:rgba(124,92,252,.10);border-left-width:7px;}
.esg-flip   {--c:#9aa6b2;--bg:rgba(154,166,178,.10);}
.esg-rating {--c:#0B2545;--bg:rgba(11,37,69,.06);}
.esg-we     {--c:#2FA36B;--bg:rgba(47,163,107,.12);}
.esg-check  {--c:#1F8A70;--bg:rgba(31,138,112,.12);}
.esg-trail  {--c:#7C5CFC;--bg:rgba(124,92,252,.06);}
.esg-conflict{--c:#E8A33D;--bg:rgba(232,163,61,.12);}
.esg-mom{display:flex;flex-wrap:wrap;gap:.5rem;margin:.3rem 0 .6rem;}
.esg-card{flex:1 1 130px;border:1px solid rgba(11,37,69,.18);border-radius:10px;
  padding:.5rem .7rem;background:rgba(11,37,69,.03);}
.esg-card .t{font-size:.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.03em;}
.esg-card .v{font-weight:700;font-size:1.05rem;line-height:1.3;}
.esg-card .s{font-size:.78rem;opacity:.75;}
.esg-card.up{border-color:#2FA36B;}
.esg-card.flat{border-color:#9aa6b2;}
.esg-card.down{border-color:#e0584f;}
.esg-card.ai{border-color:#7C5CFC;background:rgba(124,92,252,.08);}
.esg-evi{font-size:.9rem;line-height:1.65;margin:.2rem 0;}
</style>
"""


def _panel(st, cls, head, body):
    """One styled decision panel. Body is escaped — it's model output, never raw HTML."""
    st.markdown(
        f'<div class="esg-panel {cls}"><div class="esg-h">{head}</div>'
        f'<p class="esg-b">{html.escape(str(body or "unknown"))}</p></div>',
        unsafe_allow_html=True,
    )


def _dir(direction):
    """Map a momentum direction to a (css-class, arrow) pair."""
    d = (direction or "").lower()
    if d == "improving":
        return "up", "↑"
    if d == "declining":
        return "down", "↓"
    return "flat", "→"


def _months_stale(as_of):
    """Whole months between an as-of date (YYYY-MM-DD) and today; None if unparseable.
    Powers the one-line staleness call-out — no invented data, just the calendar."""
    try:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    months = (today.year - d.year) * 12 + (today.month - d.month) - (today.day < d.day)
    return max(months, 0)


def _falsifiability_line(company):
    """A deterministic 'what would change our mind' line, derived ONLY from the loaded
    Layer B data (no LLM, no invented facts) — the falsifiable flip-side of the verdict."""
    ai = ((company or {}).get("layer_b") or {}).get("digital_ai_signal") or {}
    disclosure = ai.get("ai_disclosure_level")
    velocity = ai.get("ai_governance_hiring_velocity")
    if not (disclosure and velocity):
        return None
    name = (company or {}).get("company") or "the company"
    return (
        f"{name} publishing a credible AI-governance disclosure (today: "
        f"“{disclosure}”), or the {velocity} hiring signal reversing — "
        "either would blunt our disagreement."
    )


def _render_trail_recap(st, narrowed):
    """Recap the ESG interrogation (the 5 Whys) packaged with the answer — visible thinking.
    Tucked in a collapsed expander so the verdict stays on top (criterion 02: clear output)."""
    trail = (narrowed or {}).get("trail") or []
    steps = [t for t in trail if t.get("type") in ("question", "challenge")]
    if not steps:
        return
    items = []
    for t in steps:
        icon = _AXIS_ICON.get(t.get("axis"), "🔍")
        axis = (t.get("axis") or "").replace("_", " ")
        items.append(
            f"<li><b>{icon} {html.escape(axis)}</b> — {html.escape(str(t.get('text') or ''))}</li>"
        )
    with st.expander(f"🧭 How we narrowed your question — the ESG interrogation ({len(steps)} steps)"):
        st.markdown("<ol>" + "".join(items) + "</ol>", unsafe_allow_html=True)


def _render_evidence(st, company):
    """The Layer B signal behind the verdict: momentum cards, the AI gap, the catalyst, and
    where the sources disagree. All from the loaded data — nothing invented, no contract change."""
    if not company:
        return
    lb = company.get("layer_b") or {}
    la = company.get("layer_a") or {}
    mom = lb.get("momentum") or {}
    ai = lb.get("digital_ai_signal") or {}
    conflict = lb.get("conflicting_signals") or {}
    catalyst = lb.get("near_term_catalyst")

    st.divider()
    st.markdown("#### 📡 The evidence the radar reasoned over")
    st.caption("The Layer B live signal behind the verdict — what a static rating can't see.")

    cards = []
    for key, name in (("E", "Environmental"), ("S", "Social"), ("G", "Governance")):
        m = mom.get(key) or {}
        cls, arrow = _dir(m.get("direction"))
        cards.append(
            f'<div class="esg-card {cls}"><div class="t">{name}</div>'
            f'<div class="v">{arrow} {html.escape(str(m.get("magnitude", "—")))}</div>'
            f'<div class="s">{html.escape(str(m.get("direction", "—")))}</div></div>'
        )
    cards.append(
        '<div class="esg-card ai"><div class="t">Digital / AI</div>'
        f'<div class="v">{html.escape(str(ai.get("ai_governance_hiring_velocity", "—")))}</div>'
        f'<div class="s">disclosure: {html.escape(str(ai.get("ai_disclosure_level", "—")))}</div></div>'
    )
    st.markdown('<div class="esg-mom">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    bits = []
    if ai.get("gap_note"):
        bits.append(f"🕳️ <b>The gap:</b> {html.escape(str(ai['gap_note']))}")
    if catalyst:
        bits.append(f"📅 <b>Near-term catalyst:</b> {html.escape(str(catalyst))}")
    if la.get("esg_score_static"):
        as_of = la.get("as_of_date")
        stale = _months_stale(as_of)
        stale_txt = f" — <b>{stale} months stale</b>" if stale is not None else ""
        bits.append(
            f"🗄️ <b>Stale baseline (Layer A):</b> {html.escape(str(la['esg_score_static']))} "
            f"(as of {html.escape(str(as_of or '—'))}){stale_txt}"
        )
    if bits:
        st.markdown('<div class="esg-evi">' + "<br>".join(bits) + "</div>", unsafe_allow_html=True)

    # Tightening #5: surface where the signals CONFLICT — sharper than a confidence score.
    if conflict:
        note = html.escape(str(conflict.get("conflict_note", "")))
        st.markdown(
            '<div class="esg-panel esg-conflict"><div class="esg-h">🔀 Where the sources '
            "disagree</div>"
            f'<p class="esg-b">News sentiment: '
            f'<b>{html.escape(str(conflict.get("news_sentiment", "—")))}</b> · '
            f'Behaviour trend: <b>{html.escape(str(conflict.get("behaviour_trend", "—")))}</b>'
            + (f"<br>{note}" if note else "")
            + "</p></div>",
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


def render_answer(answer, company=None, debug=False, narrowed=None):
    """Render a Stage2Answer (Contract C) dict as the decision panel.

    Leads with the VERDICT (competes_summary) — criterion 03's "show me something I
    don't know" moment — then the 5-Whys recap, the question, market-view-vs-reality, the
    check, and the Layer B evidence. Render-only: it never re-words or re-reasons the
    verified baton (HARD RULE 2). ``narrowed`` (Contract A) supplies the interrogation trail.
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
        flip = _falsifiability_line(company)
        if flip:
            _panel(st, "esg-flip", "🔄 What would change our mind", flip)
        st.divider()

    # The interrogation chain, packaged with the answer (visible thinking) — collapsed.
    _render_trail_recap(st, narrowed)

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

    # The Layer B evidence behind the verdict (momentum cards, AI gap, catalyst, conflict).
    # Gated on success: under a Stage-2 failure the warning already explains the gap, so
    # rendering Layer B cards beneath it reads as oddly contradictory.
    if not failed:
        _render_evidence(st, company)
        _render_export(st, answer, company)

    st.caption("We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.")
