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
    "dataset": "Built from pre-scored local dataset values (not a live fetch); absent fields are "
               "“unknown”. Not investment advice.",
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


# --------------------------------------------------------------------------- #
#  INTERACTIVE CHARTS (Plotly) — graphs lead the evidence; HOVER explains each.
#  Lazy import + graceful fallback: if plotly isn't installed we drop back to the
#  HTML/CSS rendering below, so the app never hard-crashes on a missing dependency.
# --------------------------------------------------------------------------- #
_PALETTE = {"up": "#2FA36B", "flat": "#9aa6b2", "down": "#e0584f",
            "ai": "#7C5CFC", "navy": "#0B2545", "amber": "#E8A33D"}

_MOM_EXPLAIN = {
    "improving": "Momentum is improving — a live acceleration the static snapshot can't see yet.",
    "declining": "Momentum is declining — deterioration the stale rating hasn't caught up to.",
    "flat": "Momentum is flat — no live movement on this pillar.",
    "unknown": "Direction unknown from the available data.",
}
# Map a qualitative disclosure level to a 0–100 'how much is disclosed' bar height.
_DISCLOSURE_SCALE = (("none", 3), ("no ", 3), ("limited", 30), ("low", 25), ("partial", 55),
                     ("medium", 55), ("moderate", 55), ("high", 85), ("full", 100), ("strong", 90))
# Map a sentiment / behaviour word to a -1 … +1 axis position.
_SENT = {"positive": 1, "improving": 1, "up": 1, "negative": -1, "declining": -1, "down": -1,
         "mixed": 0, "neutral": 0, "flat": 0}


def _go():
    """Lazily import plotly.graph_objects; None if plotly isn't installed (HTML fallback)."""
    try:
        import plotly.graph_objects as go
        return go
    except Exception:  # noqa: BLE001 — plotly is optional; the HTML path covers its absence.
        return None


def _parse_pct(value):
    """Pull a signed number out of e.g. '+8%' / '-5%' / '+340% YoY'. None if absent."""
    m = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(m.group()) if m else None


def _risk_score(value):
    """The ESG RISK-RATING number from a messy string, anywhere in it — e.g. '12.2 (Low Risk)',
    'MSCI: AAA, Sustainalytics: 12.2', 'Sustainalytics 12.2 as of 2026'. Picks the first number
    in a plausible risk-rating range (0–60) so a year like 2026 is ignored. None if absent."""
    for tok in re.findall(r"\d+(?:\.\d+)?", str(value or "")):
        v = float(tok)
        if 0 <= v <= 60:
            return v
    return None


# MSCI-style ESG letter scale, WORST -> BEST (index = position). AAA leader … CCC laggard.
_MSCI_SCALE = ["CCC", "B", "BB", "BBB", "A", "AA", "AAA"]
_MSCI_BANDS = [(0, 2, "Laggard", "#E0584F"), (2, 5, "Average", "#E8A33D"), (5, 7, "Leader", "#2FA36B")]


def _msci_category(grade):
    """(tier, colour) for a grade on the MSCI scale (Laggard / Average / Leader)."""
    i = _MSCI_SCALE.index(grade)
    lo_hi = next((b for b in _MSCI_BANDS if b[0] <= i < b[1]), _MSCI_BANDS[1])
    return lo_hi[2], lo_hi[3]


def _letter_rating(value):
    """An MSCI-style ESG letter grade (AAA…CCC) from a messy string — e.g. 'MSCI: A',
    'MSCI rating AAA'. Returns the grade, or None (incl. when a numeric score is present, which
    the numeric gauge handles instead, or when a different scale like CDP is named)."""
    s = str(value or "").upper()
    if _risk_score(value) is not None or "CDP" in s:
        return None  # numeric score wins; skip non-MSCI letter scales to avoid mislabelling
    # Alternation is longest-first so 'AAA' wins over 'A'; \b stops matches inside words (MSCI).
    grades = [g for g in re.findall(r"\b(AAA|AA|BBB|BB|CCC|CC|A|B|C)\b", s) if g in _MSCI_SCALE]
    return grades[0] if grades else None


def _parse_date(value):
    """A date from 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' (month/day default to 01). None if absent."""
    s = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _months_between(d):
    """Whole months from date `d` to today (clamped at 0)."""
    t = date.today()
    return max((t.year - d.year) * 12 + (t.month - d.month) - (t.day < d.day), 0)


def _chart_theme(st):
    """Colours that read on both the light and the injected dark theme (app.py)."""
    dark = bool(st.session_state.get("dark_mode"))
    return {
        "fg": "#E6EAF1" if dark else "#0B2545",
        "muted": "#9AA6B2" if dark else "#5B6B7B",
        "grid": "rgba(255,255,255,.10)" if dark else "rgba(11,37,69,.10)",
    }


def _style(fig, theme, *, height=260, title=None, ygrid=True):
    """Shared, transparent, theme-aware layout so charts blend into the panel."""
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=42 if title else 14, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=theme["fg"], size=13), showlegend=False,
        title=dict(text=title, font=dict(size=14, color=theme["fg"]), x=0.0) if title else None,
        hoverlabel=dict(font_size=13, align="left"),
    )
    fig.update_xaxes(showgrid=False, color=theme["muted"], zeroline=False)
    fig.update_yaxes(showgrid=ygrid, gridcolor=theme["grid"], color=theme["muted"], zeroline=False)
    return fig


_DIR_SCORE = {"improving": 1, "declining": -1, "flat": 0, "unknown": 0}


def _fig_momentum(go, mom, theme):
    """E/S/G momentum as coloured bars; hover spells out the move and why it matters.

    Two modes so live (grounded-only) data still charts: if any pillar carries a numeric
    magnitude (e.g. '+8%'), plot the magnitudes; otherwise plot the qualitative DIRECTION
    (improving / flat / declining), which the grounded extractor can supply without numbers."""
    pillars = (("E", "Environmental"), ("S", "Social"), ("G", "Governance"))
    mags = {k: _parse_pct((mom.get(k) or {}).get("magnitude")) for k, _ in pillars}
    numeric = any(v is not None for v in mags.values())
    xs, ys, colors, texts, cdata = [], [], [], [], []
    for key, name in pillars:
        m = mom.get(key) or {}
        direction = (m.get("direction") or "unknown").lower()
        mag_known = _known(m.get("magnitude"))
        magnitude = str(m.get("magnitude")) if mag_known else "—"
        cls, arrow = _dir(direction)
        if numeric:
            ys.append(mags[key] if mags[key] is not None else 0.0)
            texts.append(magnitude if mag_known else arrow)
        else:
            ys.append(_DIR_SCORE.get(direction, 0))
            texts.append(f"{arrow} {direction}" if direction != "unknown" else "—")
        xs.append(name)
        colors.append(_PALETTE.get(cls, _PALETTE["flat"]))
        mag_line = f"Change: {magnitude}" if mag_known else "Change: not quantified in sources"
        cdata.append([f"{arrow} {direction}", mag_line,
                      _MOM_EXPLAIN.get(direction, _MOM_EXPLAIN["unknown"])])
    fig = go.Figure(go.Bar(
        x=xs, y=ys, marker_color=colors, customdata=cdata,
        text=texts, textposition="outside", cliponaxis=False,
        hovertemplate=("<b>%{x}</b>  ·  %{customdata[0]}<br>%{customdata[1]}"
                       "<br><i>%{customdata[2]}</i><extra></extra>"),
    ))
    if numeric:
        return _style(fig, theme, title="E / S / G momentum (live) — change %")
    fig.update_yaxes(range=[-1.35, 1.35], tickvals=[-1, 0, 1],
                     ticktext=["declining", "flat", "improving"])
    return _style(fig, theme, title="E / S / G momentum (live) — direction")


def _fig_ai_gap(go, ai, theme):
    """The AI-governance gap: how fast it's BUILDING capacity vs how much it DISCLOSES.
    The visual distance between the two bars is the story; hover gives the real readings."""
    velocity = str(ai.get("ai_governance_hiring_velocity") or "—")
    disclosure = str(ai.get("ai_disclosure_level") or "unknown")
    v = _parse_pct(velocity)
    hire = 100.0 if (v is not None and v >= 100) else (v if v is not None else
                                                       (60 if _known(velocity) else 0))
    dl = disclosure.lower()
    disc = next((s for kw, s in _DISCLOSURE_SCALE if kw in dl), 50 if _known(disclosure) else 0)
    fig = go.Figure(go.Bar(
        x=["Building AI-governance", "Disclosing AI-governance"], y=[hire, disc],
        marker_color=[_PALETTE["ai"], _PALETTE["amber"]],
        text=[velocity, disclosure], textposition="outside", cliponaxis=False,
        customdata=[[velocity, "How fast it is hiring / building AI-governance capacity."],
                    [disclosure, "How much it actually discloses about that governance."]],
        hovertemplate="<b>%{x}</b><br>Reading: %{customdata[0]}<br><i>%{customdata[1]}</i><extra></extra>",
    ))
    fig.update_yaxes(range=[0, 118], showticklabels=False, showgrid=False)
    return _style(fig, theme, title="The AI-governance gap — building vs. disclosing", ygrid=False)


def _fig_conflict(go, conflict, theme):
    """Press sentiment vs actual behaviour on one -/+ axis — where the signals disagree."""
    news = str(conflict.get("news_sentiment") or "unknown")
    behav = str(conflict.get("behaviour_trend") or "unknown")
    nv, bv = _SENT.get(news.lower(), 0), _SENT.get(behav.lower(), 0)
    fig = go.Figure(go.Bar(
        x=["News sentiment", "Behaviour trend"], y=[nv, bv],
        marker_color=[_PALETTE["up"] if nv >= 0 else _PALETTE["down"],
                      _PALETTE["up"] if bv >= 0 else _PALETTE["down"]],
        customdata=[[news, "What the headlines / press say."],
                    [behav, "What the company's actual behaviour shows."]],
        hovertemplate="<b>%{x}</b>: %{customdata[0]}<br><i>%{customdata[1]}</i><extra></extra>",
    ))
    fig.update_yaxes(range=[-1.35, 1.35], tickvals=[-1, 0, 1],
                     ticktext=["negative", "neutral", "positive"])
    return _style(fig, theme, title="Where the signals disagree — press vs. behaviour")


def _fig_history(go, pts, theme):
    """The static score the rating reports over time, as a trend line; last point highlighted."""
    xs = [d for d, _ in pts]
    ys = [v for _, v in pts]
    last = len(pts) - 1
    sizes = [9] * len(pts); sizes[last] = 15
    mcolors = [_PALETTE["ai"]] * len(pts); mcolors[last] = _PALETTE["up"]
    cdata = [[d, "Most recent reading. Lower = better (risk score)." if i == last
              else "Historical reading. Lower = better (risk score)."]
             for i, (d, v) in enumerate(pts)]
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers+text",
        line=dict(color=_PALETTE["ai"], width=3),
        marker=dict(size=sizes, color=mcolors, line=dict(width=0)),
        text=[f"{v:g}" for v in ys], textposition="top center",
        textfont=dict(color=theme["fg"]), customdata=cdata, cliponaxis=False,
        hovertemplate=("As of %{customdata[0]}<br>Static ESG risk score: %{y:g}"
                       "<br><i>%{customdata[1]}</i><extra></extra>"),
    ))
    return _style(fig, theme, title="Static score the rating reports over time (lower = better)")


def _fig_rating_timeline(go, score, asof, theme):
    """One grounded ESG reading (live data has no real history series), held FROZEN from its
    as-of date to today — visualising how stale the static rating is. Hover explains each point."""
    today = date.today()
    months = _months_between(asof)
    axis_max = max(40, (int(score // 10) + 2) * 10)
    fig = go.Figure()
    fig.add_vrect(x0=asof.isoformat(), x1=today.isoformat(), fillcolor=_PALETTE["flat"],
                  opacity=0.08, line_width=0, layer="below", annotation_text="no update since",
                  annotation_position="top left", annotation_font_size=10,
                  annotation_font_color=theme["muted"])
    fig.add_trace(go.Scatter(  # the rating, treated as current all the way to today (dashed)
        x=[asof.isoformat(), today.isoformat()], y=[score, score], mode="lines",
        line=dict(color=_PALETTE["ai"], width=3, dash="dash"), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(  # the single grounded reading
        x=[asof.isoformat()], y=[score], mode="markers+text",
        marker=dict(size=15, color=_PALETTE["up"]), text=[f"{score:g}"], textposition="top center",
        textfont=dict(color=theme["fg"]), customdata=[[asof.isoformat()]],
        hovertemplate=("Rating set: <b>%{y:g}</b><br>As of %{customdata[0]}"
                       "<br><i>The one grounded reading — lower = better.</i><extra></extra>"),
        showlegend=False))
    fig.add_trace(go.Scatter(  # today — still no update
        x=[today.isoformat()], y=[score], mode="markers+text",
        marker=dict(size=13, color=_PALETTE["flat"], symbol="circle-open", line=dict(width=2, color=_PALETTE["flat"])),
        text=["today"], textposition="top center", textfont=dict(color=theme["muted"]),
        customdata=[[months]],
        hovertemplate=("Today — <b>no update</b><br>~%{customdata[0]} months since the rating"
                       "<br><i>The market still treats it as current.</i><extra></extra>"),
        showlegend=False))
    fig.update_yaxes(range=[0, axis_max])
    return _style(fig, theme, height=235,
                  title="Static ESG score over time — frozen at its as-of date (lower = better)")


# Sustainalytics-style ESG Risk Rating bands (LOWER = better): (lo, hi, label, colour).
_RISK_BANDS = [(0, 10, "Negligible", "#2FA36B"), (10, 20, "Low", "#7FC241"),
               (20, 30, "Medium", "#E8A33D"), (30, 40, "High", "#E0584F"),
               (40, 50, "Severe", "#B3261E")]


def _fig_risk_rating(go, score, as_of, theme):
    """The Layer A static ESG RISK RATING on a banded 0–40+ scale (lower = better). Renders for
    live companies (where the rating is grounded from a real source) as well as the sample.
    Hover gives the score, the risk band, and the as-of date."""
    axis_max = max(50, (int(score // 10) + 1) * 10)
    band = next((lbl for lo, hi, lbl, _ in _RISK_BANDS if lo <= score < hi), "—")
    color = next((c for lo, hi, lbl, c in _RISK_BANDS if lo <= score < hi), _PALETTE["navy"])
    fig = go.Figure(go.Bar(
        x=[score], y=["ESG Risk"], orientation="h", width=0.55, marker_color=color,
        text=[f"{score:g} · {band} Risk"], textposition="outside", cliponaxis=False,
        customdata=[[f"{score:g}", band, as_of or "—"]],
        hovertemplate=("ESG Risk Rating: <b>%{customdata[0]}</b> (%{customdata[1]} risk)"
                       "<br>As of %{customdata[2]}<br><i>Lower = better — the stale snapshot "
                       "Layer B competes with.</i><extra></extra>"),
    ))
    for lo, hi, lbl, c in _RISK_BANDS:  # faint banded background so the score reads in context
        if lo >= axis_max:
            break
        fig.add_vrect(x0=lo, x1=min(hi, axis_max), fillcolor=c, opacity=0.10, line_width=0,
                      layer="below", annotation_text=lbl, annotation_position="top",
                      annotation_font_size=10, annotation_font_color=theme["muted"])
    fig.update_xaxes(range=[0, axis_max], showgrid=False)
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return _style(fig, theme, height=185,
                  title="ESG Risk Rating — what the market sees (lower = better)", ygrid=False)


def _fig_letter_rating(go, grade, as_of, theme):
    """The Layer A static ESG LETTER rating on the MSCI AAA→CCC scale (AAA best). For companies
    whose grounded rating is a letter, not a number (e.g. 'MSCI: A'). Hover gives the tier."""
    idx = _MSCI_SCALE.index(grade)
    n = len(_MSCI_SCALE)
    tier, color = _msci_category(grade)
    fig = go.Figure(go.Scatter(
        x=[idx + 0.5], y=["ESG Rating"], mode="markers+text",
        marker=dict(size=30, color=color, line=dict(width=2, color="#FFFFFF")),
        text=[f"{grade} · {tier}"], textposition="top center", textfont=dict(color=theme["fg"]),
        customdata=[[grade, tier, as_of or "—"]],
        hovertemplate=("ESG Rating: <b>%{customdata[0]}</b> (%{customdata[1]})<br>As of "
                       "%{customdata[2]}<br><i>AAA = leader, CCC = laggard — higher is better. "
                       "The stale snapshot Layer B competes with.</i><extra></extra>"),
    ))
    for lo, hi, lbl, c in _MSCI_BANDS:
        fig.add_vrect(x0=lo, x1=hi, fillcolor=c, opacity=0.10, line_width=0, layer="below",
                      annotation_text=lbl, annotation_position="top", annotation_font_size=10,
                      annotation_font_color=theme["muted"])
    fig.update_xaxes(range=[0, n], tickvals=[i + 0.5 for i in range(n)], ticktext=_MSCI_SCALE,
                     showgrid=False)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[-0.5, 0.9])
    return _style(fig, theme, height=185,
                  title="ESG Rating — what the market sees (AAA best · CCC worst)", ygrid=False)


# The signals a full profile carries — used by the coverage meter to show how much is grounded.
_COVERAGE_SIGNALS = [
    ("static ESG rating", ("layer_a", "esg_score_static")),
    ("rating as-of date", ("layer_a", "as_of_date")),
    ("E momentum", ("layer_b", "momentum", "E", "direction")),
    ("S momentum", ("layer_b", "momentum", "S", "direction")),
    ("G momentum", ("layer_b", "momentum", "G", "direction")),
    ("AI disclosure", ("layer_b", "digital_ai_signal", "ai_disclosure_level")),
    ("AI hiring velocity", ("layer_b", "digital_ai_signal", "ai_governance_hiring_velocity")),
    ("news sentiment", ("layer_b", "conflicting_signals", "news_sentiment")),
    ("behaviour trend", ("layer_b", "conflicting_signals", "behaviour_trend")),
    ("near-term catalyst", ("layer_b", "near_term_catalyst")),
]


def _sig_known(company, path):
    """True when the value at a nested key `path` is grounded (not blank / 'unknown')."""
    cur = company or {}
    for p in path[:-1]:
        cur = cur.get(p) or {}
    return _known(cur.get(path[-1]))


def _fig_coverage(go, grounded, total, missing, theme):
    """How much of the profile is grounded — a 0…total bar; hover lists what's missing."""
    ratio = grounded / total if total else 0
    color = _PALETTE["up"] if ratio >= 0.66 else (_PALETTE["amber"] if ratio >= 0.33 else _PALETTE["down"])
    miss = ", ".join(missing) if missing else "none — every signal is grounded"
    fig = go.Figure(go.Bar(
        x=[grounded], y=["Coverage"], orientation="h", width=0.5, marker_color=color,
        text=[f"{grounded}/{total} signals grounded"], textposition="outside", cliponaxis=False,
        customdata=[[miss]],
        hovertemplate=("<b>%{x} of " + str(total) + " signals grounded</b>"
                       "<br><i>Not grounded: %{customdata[0]}</i><extra></extra>"),
    ))
    fig.add_vrect(x0=0, x1=total, fillcolor=theme["muted"], opacity=0.06, line_width=0, layer="below")
    fig.update_xaxes(range=[0, total], showgrid=False)
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return _style(fig, theme, height=130, title="Live data coverage — how much the radar grounded",
                  ygrid=False)


def _render_coverage(st, go, company):
    """A coverage meter so users see how complete the (esp. live) profile is — honest about gaps."""
    total = len(_COVERAGE_SIGNALS)
    missing = [name for name, path in _COVERAGE_SIGNALS if not _sig_known(company, path)]
    grounded = total - len(missing)
    if go is not None:
        st.plotly_chart(_fig_coverage(go, grounded, total, missing, _chart_theme(st)),
                        use_container_width=True, config={"displayModeBar": False, "responsive": True})
    else:
        st.progress(grounded / total, text=f"Live data coverage: {grounded}/{total} signals grounded")
        if missing:
            st.caption("Not grounded: " + ", ".join(missing) + ".")


def _render_controversies(st, company):
    """🚩 Recent news flagging controversy/risk — the 'behaviour' side of the conflict. Real
    links the radar surfaced; framed as leads to check, never as a verified verdict."""
    items = (company or {}).get("_controversies") or []
    if not items:
        return
    st.divider()
    st.markdown(f"#### 🚩 Red flags — recent items mentioning controversy / risk ({len(items)})")
    st.caption("Live news the radar surfaced that mention controversy, fines, probes or "
               "incidents — leads to check, not verified findings and not our verdict.")
    for it in items:
        title = it.get("title") or it.get("url") or "source"
        url = it.get("url") or ""
        st.markdown(f"- [{title}]({url})" if url else f"- {title}")
        snippet = (it.get("snippet") or "").strip()
        if snippet and snippet.lower() != (title or "").lower():
            st.caption(snippet)


def _render_charts(st, go, company):
    """Graph-led evidence: the Layer A rating gauge + the live Layer B signal as interactive
    charts (hover explains each). Returns True if any chart was drawn (caller skips HTML cards)."""
    la = (company or {}).get("layer_a") or {}
    lb = (company or {}).get("layer_b") or {}
    mom = lb.get("momentum") or {}
    ai = lb.get("digital_ai_signal") or {}
    conflict = lb.get("conflicting_signals") or {}
    mom_known = any(_known((mom.get(k) or {}).get("direction")) or _known((mom.get(k) or {}).get("magnitude"))
                    for k in ("E", "S", "G"))
    ai_known = _known(ai.get("ai_governance_hiring_velocity")) or _known(ai.get("ai_disclosure_level"))
    conflict_known = _known(conflict.get("news_sentiment")) or _known(conflict.get("behaviour_trend"))

    theme = _chart_theme(st)
    cfg = {"displayModeBar": False, "responsive": True}
    drawn = False
    # Layer A: the static ESG rating gauge (grounded from a real source for live data) — a
    # numeric risk score if we have one, else the MSCI-style letter grade.
    score = _risk_score(la.get("esg_score_static"))
    grade = _letter_rating(la.get("esg_score_static")) if score is None else None
    if score is not None:
        st.plotly_chart(_fig_risk_rating(go, score, la.get("as_of_date"), theme),
                        use_container_width=True, config=cfg)
        st.caption("🗄️ The static ESG risk rating the market sees — hover for the band and as-of date.")
        drawn = True
    elif grade is not None:
        st.plotly_chart(_fig_letter_rating(go, grade, la.get("as_of_date"), theme),
                        use_container_width=True, config=cfg)
        st.caption("🗄️ The static ESG letter rating the market sees — hover for the tier and as-of date.")
        drawn = True
    if mom_known:
        st.plotly_chart(_fig_momentum(go, mom, theme), use_container_width=True, config=cfg)
        st.caption("📊 Live ESG momentum a static rating can't see — hover any bar for what the move means.")
        drawn = True
    side = [k for k, ok in (("ai", ai_known), ("conflict", conflict_known)) if ok]
    if side:
        cols = st.columns(len(side))
        for col, kind in zip(cols, side):
            with col:
                fig = _fig_ai_gap(go, ai, theme) if kind == "ai" else _fig_conflict(go, conflict, theme)
                st.plotly_chart(fig, use_container_width=True, config=cfg)
        drawn = True
    return drawn


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
    st.caption("The live signal behind the verdict, in charts — what a static rating can't see.")

    # Graphs first (the user-facing medium). If plotly is missing, _go() is None and we drop
    # back to the HTML cards so a missing dependency never breaks the panel.
    go = _go()
    _render_coverage(st, go, company)  # how much of the profile is grounded (honest about gaps)
    charts_drawn = _render_charts(st, go, company) if go is not None else False

    if not charts_drawn:  # HTML fallback — the original momentum/AI cards.
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

    # The conflict note (qualitative). The chart shows the directions; this adds the words.
    # When there are no charts, render the original full conflict panel instead.
    if conflict_known:
        note = html.escape(str(conflict.get("conflict_note", "")))
        if charts_drawn:
            if note:
                st.caption(f"🔀 Where the sources disagree — {note}")
        else:
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


def _render_rating_timeline(st, company):
    """Live fallback for 'static score over time': one grounded reading held frozen to today,
    so the staleness is visible even without a real history series. Plotly-only (skips on
    HTML fallback / non-numeric ratings / unparseable dates)."""
    la = (company or {}).get("layer_a") or {}
    score = _risk_score(la.get("esg_score_static"))
    asof = _parse_date(la.get("as_of_date"))
    go = _go()
    if score is None or asof is None or go is None:
        return
    st.markdown("#### 📈 Static score over time — one reading, frozen")
    st.plotly_chart(_fig_rating_timeline(go, score, asof, _chart_theme(st)),
                    use_container_width=True, config={"displayModeBar": False, "responsive": True})
    st.caption(
        f"Only one grounded ESG reading exists ({score:g}, set {asof.isoformat()}); no real "
        f"history series is published. The market still treats it as current ~{_months_between(asof)} "
        "months on — exactly the stale snapshot Layer B is built to challenge."
    )


def _render_history(st, company):
    """The static score's TREND over time (from layer_a_history) — the calm picture Layer B
    contradicts. A Plotly line chart with hover when available; the HTML bar strip otherwise.
    From the loaded data only; the leading number is parsed, nothing is invented."""
    hist = (company or {}).get("layer_a_history") or {}
    series = hist.get("series") or []
    pts = [(str(p.get("as_of", ""))[:7], _parse_score(p.get("esg_score_static"))) for p in series]
    pts = [(d, v) for d, v in pts if v is not None]
    if len(pts) < 2:
        _render_rating_timeline(st, company)  # live data has no series: show the single reading
        return
    vals = [v for _, v in pts]
    first, last = vals[0], vals[-1]
    # Risk score: LOWER = better, so a falling line is "improving".
    trend = "↓ improving" if last < first else ("↑ worsening" if last > first else "→ flat")
    note = str(hist.get("trend_note") or "")

    go = _go()
    if go is not None:
        st.markdown("#### 📈 Static score over time — the trend the rating reports")
        st.plotly_chart(_fig_history(go, pts, _chart_theme(st)), use_container_width=True,
                        config={"displayModeBar": False, "responsive": True})
        cap = f"Trend: {trend} · lower = better. Hover a point for the date and reading."
        st.caption(cap + (f"  {note}" if note else ""))
        return

    # HTML fallback (no plotly): the original proportional bar strip.
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    last_i = len(pts) - 1
    bars = []
    for i, (d, v) in enumerate(pts):
        px = int(28 + 52 * ((v - lo) / span))  # 28–80px tall, proportional to the score
        now = " now" if i == last_i else ""
        bars.append(
            f'<div class="esg-hbar{now}"><div class="esg-hbar-fill" style="height:{px}px"></div>'
            f'<div class="esg-hbar-v">{v:g}</div><div class="esg-hbar-d">{html.escape(str(d))}</div></div>'
        )
    note_esc = html.escape(note)
    st.markdown(
        '<div class="esg-panel esg-hist"><div class="esg-h">📈 Static score over time — '
        f"history → now ({html.escape(trend)}; lower = better)</div>"
        f'<div class="esg-hbars">{"".join(bars)}</div>'
        + (f'<p class="esg-b" style="margin-top:.3rem">{note_esc}</p>' if note_esc else "")
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


def _render_ai_summary(st, answer):
    """Show the DuckDuckGo AI summary the radar INTERPRETED (collapsed). Real, sourced text —
    presented as context we read, never copied as a verified company fact."""
    ai = answer.get("_ai_summary") or {}
    summary = (ai.get("summary") or "").strip()
    if not summary:
        return
    with st.expander("🦆 DuckDuckGo AI summary — the synthesized context we interpreted"):
        st.markdown(html.escape(summary))
        src, url = (ai.get("source") or "DuckDuckGo"), (ai.get("url") or "")
        if url:
            st.caption(f"Source: [{src}]({url}) · interpreted by the radar and cross-checked "
                       "against the ranked sources below — never copied as fact.")
        else:
            st.caption(f"Source: {src} · interpreted, never copied as fact.")


def _render_sources(st, answer, company=None):
    """Provenance: the live-retrieval citations behind the answer, plus (for live/uploaded
    data) the sources the company profile itself was built from. Real titles + URLs only."""
    sources = answer.get("sources") or []
    status = answer.get("_rag_status")
    st.divider()
    # [3.9] source-count badge so the reader sees how many citations ground the answer.
    badge = f"  ·  **{len(sources)} source{'s' if len(sources) != 1 else ''}**" if sources else ""
    st.markdown(f"#### 🔗 Sources — live retrieval (DuckDuckGo){badge}")
    if sources:
        _source_list(st, sources)
        st.caption(
            "Fetched live from DuckDuckGo and ranked by relevance (TF-IDF). Real external "
            "context used to ground the reasoning — never to fabricate company facts."
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
        st.markdown(f"**Profile built from:**  ·  {len(build_sources)} source"
                    f"{'s' if len(build_sources) != 1 else ''}")
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


def _card_md(answer, company):
    """Markdown rendering of the full card — suitable for sharing as a report."""
    today = date.today().isoformat()
    if company:
        name = company.get("company", "—")
        ticker = company.get("ticker", "—")
        sector = company.get("sector", "—")
        subj = f"{name} (`{ticker}`) · {sector}"
    else:
        name, subj = "—", "—"

    lines = [
        f"# ASEAN ESG Momentum Radar — {name}",
        f"**{subj}**  ·  _{today}_",
        f"> _{_disclaimer(company)}_",
        "",
        "---",
        "",
        "## ⚔️ Verdict",
        f"> {answer.get('competes_summary', 'unknown')}",
        "",
        "---",
        "",
        f"**Question:** {answer.get('question_to_ask', 'unknown')}",
        "",
        "## Market view vs. reality",
        "",
        f"**📊 What the rating sees**  ",
        answer.get("what_rating_sees", "unknown"),
        "",
        f"**🛰️ What we see**  ",
        answer.get("what_we_see", "unknown"),
        "",
        "---",
        "",
        "## ✅ Check before Monday",
        answer.get("check_before_monday", "unknown"),
        "",
    ]

    lb = (company or {}).get("layer_b") or {}
    mom = lb.get("momentum") or {}
    dig = lb.get("digital_ai_signal") or {}
    # Only emit signals that are actually KNOWN. coerce_company_data always materialises
    # momentum/digital_ai with "unknown" defaults, so a bare `if mom:` would dump rows of
    # "unknown" for sparse/live companies — mirror _render_evidence's _known() gating instead.
    mom_rows = []
    for pillar in ("E", "S", "G"):
        data = mom.get(pillar) or {}
        direction, magnitude = data.get("direction"), data.get("magnitude")
        if not (_known(direction) or _known(magnitude)):
            continue
        mag_str = f" ({magnitude})" if _known(magnitude) else ""
        mom_rows.append(f"- **{pillar}**: {direction if _known(direction) else 'unknown'}{mag_str}")
    ai_rows = []
    if _known(dig.get("ai_governance_hiring_velocity")):
        ai_rows.append(f"- **Digital/AI hiring velocity**: {dig['ai_governance_hiring_velocity']}")
    if _known(dig.get("ai_disclosure_level")):
        ai_rows.append(f"- **AI disclosure level**: {dig['ai_disclosure_level']}")
    if _known(dig.get("gap_note")):
        ai_rows.append(f"  > _{dig['gap_note']}_")
    if mom_rows or ai_rows:
        lines += ["---", "", "## 📊 ESG pillar signals", ""] + mom_rows + ai_rows + [""]

    reasoning = answer.get("reasoning") or []
    if reasoning:
        lines += ["---", "", "## 🧠 Chain of thought", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(reasoning, 1)]
        lines.append("")

    sources = answer.get("sources") or []
    if sources:
        lines += ["---", "", "## 🔗 Sources (live retrieval)", ""]
        for s in sources:
            title = s.get("title") or s.get("url") or "source"
            url = s.get("url", "")
            lines.append(f"- [{title}]({url})" if url else f"- {title}")
        lines.append("")

    lines += ["---", "", "_Not investment advice. Generated by ASEAN ESG Momentum Radar._"]
    return "\n".join(lines) + "\n"


def _render_export(st, answer, company):
    """Prominent download strip right after the verdict, plus a full-text expander below."""
    name = (company or {}).get("company", "esg_radar")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    col1, col2 = st.columns(2)
    col1.download_button(
        "⬇️ Download report (.md)", data=_card_md(answer, company),
        file_name=f"{slug}_esg_report.md", mime="text/markdown",
        use_container_width=True,
    )
    col2.download_button(
        "⬇️ Download card (.txt)", data=_card_text(answer, company),
        file_name=f"{slug}_esg_card.txt", mime="text/plain",
        use_container_width=True,
    )

    with st.expander("📋 Preview / copy the text card"):
        st.code(_card_text(answer, company), language=None)


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
        _render_export(st, answer, company)
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
        _render_controversies(st, company)  # 🚩 red flags — recent controversy/risk news
        _render_ai_summary(st, answer)      # the DuckDuckGo AI summary we interpreted
        _render_sources(st, answer, company)  # RAG citations + how the profile was built

    st.caption("We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.")
