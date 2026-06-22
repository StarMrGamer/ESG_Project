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
import re
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
.esg-hist{--c:#0B2545;--bg:rgba(11,37,69,.05);}
.esg-hbars{display:flex;align-items:flex-end;gap:.6rem;height:84px;margin:.3rem 0 .2rem;}
.esg-hbar{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;flex:1 1 0;}
.esg-hbar-fill{width:60%;max-width:34px;border-radius:4px 4px 0 0;background:#7C5CFC;opacity:.85;}
.esg-hbar.now .esg-hbar-fill{background:#2FA36B;opacity:1;}
.esg-hbar-v{font-weight:700;font-size:.82rem;margin-top:.2rem;}
.esg-hbar-d{font-size:.68rem;opacity:.65;}
</style>
"""


_DISCLAIMER = {
    "sample": "⚠️ Illustrative sample — placeholder data, not real facts about any real company.",
    "live": "Built live from public sources; fields not found are “unknown”, never invented. "
            "Not investment advice.",
    "upload": "Built from your uploaded data. Not investment advice.",
}


def _disclaimer(company):
    """Honest, origin-aware disclaimer — real (live/upload) data is NOT called 'placeholder'."""
    origin = (company or {}).get("_origin", "sample")
    return _DISCLAIMER.get(origin, "Not investment advice.")


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


def _known(v):
    """True when a field carries a real value (not blank / not the 'unknown' sentinel)."""
    return bool(v) and str(v).strip().lower() != "unknown"


def _falsifiability_line(company):
    """A deterministic 'what would change our mind' line, derived ONLY from the loaded Layer B
    AI signal — only shown when that signal is actually known (skip it for sparse live data)."""
    ai = ((company or {}).get("layer_b") or {}).get("digital_ai_signal") or {}
    disclosure = ai.get("ai_disclosure_level")
    velocity = ai.get("ai_governance_hiring_velocity")
    if not (_known(disclosure) and _known(velocity)):
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
    """The structured Layer B signal behind the verdict — momentum cards, the AI gap, the
    catalyst, the conflict. Renders ONLY the fields that are actually known: for a sparse live
    company it shows a short note pointing to the sources instead of a wall of 'unknown'."""
    if not company:
        return
    lb = company.get("layer_b") or {}
    la = company.get("layer_a") or {}
    mom = lb.get("momentum") or {}
    ai = lb.get("digital_ai_signal") or {}
    conflict = lb.get("conflicting_signals") or {}
    catalyst = lb.get("near_term_catalyst")

    mom_known = any(_known((mom.get(k) or {}).get("direction")) or _known((mom.get(k) or {}).get("magnitude"))
                    for k in ("E", "S", "G"))
    ai_known = _known(ai.get("ai_governance_hiring_velocity")) or _known(ai.get("ai_disclosure_level"))
    conflict_known = (_known(conflict.get("news_sentiment")) or _known(conflict.get("behaviour_trend"))
                      or _known(conflict.get("conflict_note")))

    bits = []
    if _known(ai.get("gap_note")):
        bits.append(f"🕳️ <b>The gap:</b> {html.escape(str(ai['gap_note']))}")
    if _known(catalyst):
        bits.append(f"📅 <b>Near-term catalyst:</b> {html.escape(str(catalyst))}")
    if _known(la.get("esg_score_static")):
        as_of = la.get("as_of_date")
        stale = _months_stale(as_of)
        stale_txt = f" — <b>{stale} months stale</b>" if stale is not None else ""
        bits.append(
            f"🗄️ <b>Stale baseline (Layer A):</b> {html.escape(str(la['esg_score_static']))} "
            f"(as of {html.escape(str(as_of or '—'))}){stale_txt}"
        )

    # Sparse live build: no structured Layer A/B — don't render a wall of "unknown".
    if not (mom_known or ai_known or conflict_known or bits):
        st.divider()
        st.caption("ℹ️ No structured Layer A/B signals were available for this company "
                   "(grounded-only build) — the verdict rests on the retrieved sources below.")
        return

    st.divider()
    st.markdown("#### 📡 The evidence the radar reasoned over")
    st.caption("The live signal behind the verdict — what a static rating can't see.")

    cards = []
    if mom_known:
        for key, name in (("E", "Environmental"), ("S", "Social"), ("G", "Governance")):
            m = mom.get(key) or {}
            cls, arrow = _dir(m.get("direction"))
            cards.append(
                f'<div class="esg-card {cls}"><div class="t">{name}</div>'
                f'<div class="v">{arrow} {html.escape(str(m.get("magnitude", "—")))}</div>'
                f'<div class="s">{html.escape(str(m.get("direction", "—")))}</div></div>'
            )
    if ai_known:
        cards.append(
            '<div class="esg-card ai"><div class="t">Digital / AI</div>'
            f'<div class="v">{html.escape(str(ai.get("ai_governance_hiring_velocity", "—")))}</div>'
            f'<div class="s">disclosure: {html.escape(str(ai.get("ai_disclosure_level", "—")))}</div></div>'
        )
    if cards:
        st.markdown('<div class="esg-mom">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    if bits:
        st.markdown('<div class="esg-evi">' + "<br>".join(bits) + "</div>", unsafe_allow_html=True)

    # Surface where the signals CONFLICT — sharper than a confidence score (only if known).
    if conflict_known:
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


def _parse_score(value):
    """Pull the leading numeric score out of e.g. '22.4 (Medium Risk)'. None if absent."""
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", str(value or ""))
    return float(m.group(1)) if m else None


def _render_history(st, company):
    """A compact historical-vs-current bar strip for the static score, from layer_a_history.
    Shows the TREND a rating reports over time — the calm picture Layer B contradicts. From
    the loaded data only; the leading number is parsed, nothing is invented."""
    hist = (company or {}).get("layer_a_history") or {}
    series = hist.get("series") or []
    pts = [(p.get("as_of", ""), _parse_score(p.get("esg_score_static"))) for p in series]
    pts = [(d, v) for d, v in pts if v is not None]
    if len(pts) < 2:
        return
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    last_i = len(pts) - 1
    bars = []
    for i, (d, v) in enumerate(pts):
        px = int(28 + 52 * ((v - lo) / span))  # 28–80px tall, proportional to the score
        now = " now" if i == last_i else ""
        bars.append(
            f'<div class="esg-hbar{now}"><div class="esg-hbar-fill" style="height:{px}px"></div>'
            f'<div class="esg-hbar-v">{v:g}</div><div class="esg-hbar-d">{html.escape(str(d)[:7])}</div></div>'
        )
    first, last = vals[0], vals[-1]
    # Risk score: LOWER = better, so a falling line is "improving".
    trend = "↓ improving" if last < first else ("↑ worsening" if last > first else "→ flat")
    note = html.escape(str(hist.get("trend_note") or ""))
    st.markdown(
        '<div class="esg-panel esg-hist"><div class="esg-h">📈 Static score over time — '
        f"history → now ({html.escape(trend)}; lower = better)</div>"
        f'<div class="esg-hbars">{"".join(bars)}</div>'
        + (f'<p class="esg-b" style="margin-top:.3rem">{note}</p>' if note else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_reasoning(st, answer):
    """The radar's chain of thought — the steps behind the verdict, in a collapsed expander."""
    steps = answer.get("reasoning") or []
    if not steps:
        return
    with st.expander(f"🧠 Show the radar's reasoning — chain of thought ({len(steps)} steps)"):
        st.markdown(
            "<ol>" + "".join(f"<li>{html.escape(str(s))}</li>" for s in steps) + "</ol>",
            unsafe_allow_html=True,
        )


def _source_list(st, sources):
    for s in sources:
        title = s.get("title") or s.get("url") or "source"
        url = s.get("url") or ""
        st.markdown(f"- [{title}]({url})" if url else f"- {title}")


def _render_sources(st, answer, company=None):
    """Provenance: the live-retrieval citations behind the answer, plus (for live/uploaded
    data) the sources the company profile itself was built from. Real titles + URLs only."""
    sources = answer.get("sources") or []
    status = answer.get("_rag_status")
    st.divider()
    st.markdown("#### 🔗 Sources — live retrieval (RAG)")
    if sources:
        _source_list(st, sources)
        st.caption(
            "Fetched live and ranked by relevance (TF-IDF). Real external context used to "
            "ground the reasoning — never to fabricate company facts."
        )
    else:
        reason = {
            "offline": "the network was unavailable",
            "disabled": "live retrieval is turned off",
            "injected": "retrieval was bypassed",
        }.get(status, "nothing relevant was found")
        st.caption(
            f"No external sources for this run ({reason}). The verdict rests on the company "
            "data — the radar degrades gracefully and never invents a citation."
        )

    # For live/uploaded data, also show where the ESG PROFILE itself came from.
    build_sources = (company or {}).get("_sources") or []
    origin = (company or {}).get("_origin")
    if build_sources and origin in ("live", "upload"):
        st.markdown("**Profile built from:**")
        _source_list(st, build_sources)


def _card_text(answer, company):
    """Plain-text rendering of the four-line card — the artifact users copy / export."""
    if company:
        subj = (f"{company.get('company', '—')} ({company.get('ticker', '—')}) · "
                f"{company.get('sector', '—')}")
    else:
        subj = "—"
    lines = [
        f"ASEAN ESG Momentum Radar — {subj}",
        f"({_disclaimer(company)})",
        "",
        f"VERDICT: {answer.get('competes_summary', 'unknown')}",
        "",
        f"Question: {answer.get('question_to_ask', 'unknown')}",
        f"What the rating sees: {answer.get('what_rating_sees', 'unknown')}",
        f"What we see: {answer.get('what_we_see', 'unknown')}",
        f"Check before Monday: {answer.get('check_before_monday', 'unknown')}",
    ]
    reasoning = answer.get("reasoning") or []
    if reasoning:
        lines += ["", "Reasoning (chain of thought):"]
        lines += [f"  {i}. {s}" for i, s in enumerate(reasoning, 1)]
    sources = answer.get("sources") or []
    if sources:
        lines += ["", "Sources (live retrieval):"]
        lines += [f"  - {s.get('title') or s.get('url')} {s.get('url', '')}".rstrip() for s in sources]
    return "\n".join(lines) + "\n"


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
            f"`{company.get('ticker', '—')}` · {company.get('sector', '—')}  ·  "
            + _disclaimer(company)
        )

    # Surface a failed / empty Stage 2 instead of a wall of "unknown".
    all_unknown = all((answer.get(k) or "unknown") == "unknown" for k in _FIELDS)
    failed = bool(answer.get("_parse_failed") or all_unknown)
    if failed:
        origin = (company or {}).get("_origin", "sample")
        name = (company or {}).get("company") or "this company"
        rag_status = answer.get("_rag_status")
        offline = rag_status in ("offline", "disabled")
        if answer.get("_parse_failed"):
            st.warning(
                "⚠️ Stage 2 reached the model but couldn't parse a clean answer — usually a "
                "transient model hiccup or a wrong model name. Click **Reason over the data** "
                "again, or set `DEEPSEEK_MODEL` (e.g. `deepseek-chat`)."
            )
        elif origin == "live":
            st.warning(
                f"⚠️ Couldn't build a competing answer for **{name}** — the live profile came "
                "up too thin"
                + (" because live retrieval couldn't reach the network" if offline else
                   " (public sources didn't yield the signals needed)")
                + ". Grounded-only mode keeps anything it can't verify as “unknown”, so there "
                "wasn't enough to compete on.\n\n**Try:** check your connection and "
                "`DEEPSEEK_API_KEY` (run `python debug_llm.py`), reason again, **upload your "
                "own ESG data**, or load the **offline sample** from the sidebar."
            )
        elif origin == "upload":
            st.warning(
                f"⚠️ Couldn't build a competing answer from your uploaded data for **{name}** — "
                "it may be missing the Layer A / Layer B fields the reasoner needs. Check the "
                "JSON template in the sidebar, or add more detail to the file."
            )
        else:
            st.warning(
                f"Stage 2 couldn't produce an answer for **{name}**"
                + (" — live retrieval was offline." if offline else ".")
                + " Try reasoning again."
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
        _render_reasoning(st, answer)  # the chain of thought behind the verdict
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
        _render_history(st, company)        # historical static-score trend vs the live signal
        _render_sources(st, answer, company)  # RAG citations + how the profile was built
        _render_export(st, answer, company)

    st.caption("We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.")
