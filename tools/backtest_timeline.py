"""
backtest_timeline.py — A8 / STEP 8.3: the per-case validation chart.
====================================================================

    python backtest_timeline.py                # write docs/backtest/*.svg + series.json
    python backtest_timeline.py --print        # the series as text, no files
    python backtest_timeline.py --case adaro   # just one

One chart per backtest case: **the LSEG baseline flat in grey, our momentum moving in the
accent, the outcome after the cutoff.** It is the deck's validation visual and it makes one
claim — that the signal moved while the incumbent view did not — so the drawing has to be
honest about both halves of that.

**The grey line is flat at zero, and that is a statement of evidence, not a graphic choice.**
We hold no dated rating action for any of these five companies inside their lookback windows —
for Top Glove the record is explicitly that it stayed on the DJSI throughout; for Sembcorp the
handoff says the MSCI path is unverified. So the honest baseline is "no dated rating movement we
can evidence", drawn as no movement, and labelled with the basis the engine actually recorded.
It is not a licensed LSEG series and the chart says so on its face.

Every point is a real engine run with `cutoff` set to that point's own date, so the line can
never see its own future: the value plotted for March is what the Radar would have said in
March. That is the whole reason the chart is worth showing.
"""


import os as _os, sys as _sys
# tools/ -> repo root, BEFORE any app import below.
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import json
import os
import sys

import engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "docs", "backtest")
CASES_FILE = os.path.join(BASE_DIR, "data", "backtest_cases.json")

LOOKBACK_MONTHS = 30          # generous: every case's first event falls inside it
W, H = 760, 322
PAD_L, PAD_R, PAD_T, PAD_B = 58, 132, 26, 62

# The deck <-> product colour law (runbook STEP 10): grey = the incumbent baseline,
# accent = our momentum, and confidence is carried by opacity rather than a second line.
INK = "#3D3D3A"
GREY = "#9A9A93"
ACCENT = "#2F7D62"
WARN = "#B4553F"
FAINT = "#E4E2DC"


# The cases live here rather than in harness.py so the dependency runs one way — harness
# imports this module for the timeline check, and a cycle would load harness twice when it is
# run as a script. One definition, one direction, no drift between the chart and the check.
def load_cases():
    with open(CASES_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def case_company(case):
    """A backtest case as a company record the engine can score (its events are its evidence).

    `esg_score`/`esg_score_basis` carry the case's MOCKED MEDIAN baseline. A case is scored alone,
    so its percentile is 0.5 whatever the number is — but stating it matters: without it the
    baseline reads UNAVAILABLE and `engine.label_for` correctly refuses to give the case a
    quadrant, because a company with no incumbent rating cannot disagree with one. The cases were
    always scored against an implied median (the topglove note says so in as many words); this
    writes it down so a case is distinguishable from a company we genuinely hold no rating for.
    """
    return {"company": case["company"], "ticker": case["ticker"], "sector": case["sector"],
            "country": case.get("country", "unknown"), "as_of": case["cutoff_date"],
            "esg_score": case.get("esg_score"), "esg_score_basis": case.get("esg_score_basis"),
            "events": case["events"]}


# --------------------------------------------------------------------------- #
#  dates — plain arithmetic, no clock. The chart must be as reproducible as the engine.
# --------------------------------------------------------------------------- #
def _ym(iso):
    return int(iso[:4]), int(iso[5:7])


def _month_end(year, month):
    days = [31, 29 if (year % 4 == 0 and (year % 100 or year % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return f"{year:04d}-{month:02d}-{days:02d}"


def _months_back(iso, n):
    y, m = _ym(iso)
    total = y * 12 + (m - 1) - n
    return total // 12, total % 12 + 1


def sample_dates(case):
    """Month-ends across the lookback, ending exactly on the cutoff."""
    cutoff = case["cutoff_date"]
    first_event = min((e["published_at"] for e in case["events"]), default=cutoff)
    sy, sm = _months_back(cutoff, LOOKBACK_MONTHS)
    if (sy, sm) > _ym(first_event):
        sy, sm = _ym(first_event)
    dates, (y, m) = [], (sy, sm)
    while (y, m) <= _ym(cutoff):
        end = _month_end(y, m)
        dates.append(min(end, cutoff))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if dates[-1] != cutoff:
        dates.append(cutoff)
    return sorted(set(dates))


# --------------------------------------------------------------------------- #
#  the series
# --------------------------------------------------------------------------- #
def series_for(case):
    """Score the case once per sample date, each with its OWN cutoff — no lookahead, ever."""
    company = case_company(case)
    points = []
    for date in sample_dates(case):
        run = engine.run_engine([dict(company, as_of=date)], as_of=date, cutoff=date,
                                use_cache=False)
        engine.enforce_cutoff(run, cutoff=date)
        rec = run["records"][0]
        points.append({"date": date,
                       "momentum": rec["composite_momentum"],
                       "confidence": rec["composite_confidence"],
                       "signal_count": rec["signal_count"],
                       "label": rec["label_display"]})
    final = points[-1]
    return {
        "case_id": case["case_id"], "company": case["company"], "ticker": case["ticker"],
        "profile": case["profile"], "cutoff_date": case["cutoff_date"],
        "outcome_date": case["outcome_date"], "outcome": case["outcome"],
        "outcome_source": case["outcome_source"],
        "is_known_failure": bool(case["expect"].get("is_known_failure")),
        "baseline": {
            "value": 0.0,
            "basis": _baseline_basis(company),
            "note": "No rating action is dated in our evidence for this window; the incumbent "
                    "view is drawn as no movement. MOCK stand-in, not a licensed LSEG series.",
        },
        "events": [{"date": e["published_at"], "text": e["text"],
                    "source_type": e.get("source_type", "unknown")}
                   for e in sorted(case["events"], key=lambda e: e["published_at"])],
        "points": points,
        "final": {"momentum": final["momentum"], "confidence": final["confidence"],
                  "signal_count": final["signal_count"], "label": final["label"]},
    }


def _baseline_basis(company):
    run = engine.run_engine([company], use_cache=False)
    return run["records"][0]["baseline_basis"]


def all_series(case_ids=None):
    cases = load_cases()["cases"]
    return [series_for(c) for c in cases if not case_ids or c["case_id"] in case_ids]


# --------------------------------------------------------------------------- #
#  the drawing
# --------------------------------------------------------------------------- #
def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _x_scale(series):
    """Dates -> x. The axis runs from the first sample to the OUTCOME, so the outcome marker
    sits where it belongs: outside the lookback, on the far side of the cutoff line."""
    dates = [p["date"] for p in series["points"]] + [series["outcome_date"]]
    lo, hi = min(dates), max(dates)
    lo_d, hi_d = engine._days_between(hi, lo) or 1, 0          # noqa: SLF001 — same repo

    def x(date):
        return PAD_L + (W - PAD_L - PAD_R) * (engine._days_between(date, lo) / lo_d)  # noqa: SLF001
    return x, lo, hi


def _y_scale():
    top, bottom = PAD_T, H - PAD_B

    def y(value):
        return bottom - (bottom - top) * ((float(value) + 1.0) / 2.0)
    return y


def render_svg(series):
    x, lo, _hi = _x_scale(series)
    y = _y_scale()
    zero, cutoff_x, outcome_x = y(0.0), x(series["cutoff_date"]), x(series["outcome_date"])
    accent = WARN if series["final"]["momentum"] < 0 else ACCENT
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
        f'role="img" aria-label="{_esc(series["company"])} momentum vs baseline">',
        f'<rect width="{W}" height="{H}" fill="#FAF9F5"/>',
    ]

    # y grid
    for v, label in ((1.0, "+1"), (0.5, "+0.5"), (0.0, "0"), (-0.5, "-0.5"), (-1.0, "-1")):
        gy = y(v)
        parts.append(f'<line x1="{PAD_L}" y1="{gy:.1f}" x2="{W - PAD_R}" y2="{gy:.1f}" '
                     f'stroke="{FAINT}" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_L - 8}" y="{gy + 3.5:.1f}" font-size="9" fill="{GREY}" '
                     f'text-anchor="end">{label}</text>')

    # the lookback window, then the cutoff wall
    parts.append(f'<rect x="{PAD_L}" y="{PAD_T}" width="{cutoff_x - PAD_L:.1f}" '
                 f'height="{H - PAD_B - PAD_T}" fill="{INK}" opacity="0.025"/>')
    parts.append(f'<line x1="{cutoff_x:.1f}" y1="{PAD_T}" x2="{cutoff_x:.1f}" y2="{H - PAD_B}" '
                 f'stroke="{INK}" stroke-width="1.25" stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{cutoff_x - 5:.1f}" y="{PAD_T + 10}" font-size="9" fill="{INK}" '
                 f'text-anchor="end">cutoff {series["cutoff_date"]}</text>')

    # every event that fed the line, as a tick on the floor
    for ev in series["events"]:
        ex = x(ev["date"])
        parts.append(f'<line x1="{ex:.1f}" y1="{H - PAD_B}" x2="{ex:.1f}" y2="{H - PAD_B + 6}" '
                     f'stroke="{GREY}" stroke-width="1"><title>{_esc(ev["date"])} · '
                     f'{_esc(ev["source_type"])} — {_esc(ev["text"])}</title></line>')

    for date, anchor_at in ((series["points"][0]["date"], "start"),
                            (series["cutoff_date"], "end")):
        parts.append(f'<text x="{x(date):.1f}" y="{H - PAD_B + 18}" font-size="8.5" '
                     f'fill="{GREY}" text-anchor="{"start" if anchor_at == "start" else "end"}">'
                     f'{date}</text>')

    # the incumbent baseline: flat, grey, and labelled for what it is
    parts.append(f'<line x1="{PAD_L}" y1="{zero:.1f}" x2="{cutoff_x:.1f}" y2="{zero:.1f}" '
                 f'stroke="{GREY}" stroke-width="2.5"/>')

    # Our momentum. The stretch BEFORE the first dated signal is drawn faint and dashed, not
    # solid: with no evidence the composite is 0.000, which lands exactly on the grey baseline,
    # and a solid line there would read as "we agreed with the rating" when what it means is
    # "we had nothing to say yet". Those are different claims and the chart must not blur them.
    first_signal = next((i for i, p in enumerate(series["points"]) if p["signal_count"]),
                        len(series["points"]))
    if first_signal:
        quiet = " ".join(f"{x(p['date']):.1f},{y(p['momentum']):.1f}"
                         for p in series["points"][:first_signal + 1])
        parts.append(f'<polyline points="{quiet}" fill="none" stroke="{accent}" '
                     f'stroke-width="1.5" stroke-dasharray="3 4" opacity="0.45"/>')
        qx = x(series["points"][max(0, first_signal - 1)]["date"])
        parts.append(f'<text x="{(PAD_L + qx) / 2:.1f}" y="{zero - 7:.1f}" font-size="8" '
                     f'fill="{GREY}" text-anchor="middle" opacity="0.9">no evidence yet</text>')
    live = " ".join(f"{x(p['date']):.1f},{y(p['momentum']):.1f}"
                    for p in series["points"][first_signal:])
    if live:
        parts.append(f'<polyline points="{live}" fill="none" stroke="{accent}" '
                     f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
    for p in series["points"][first_signal:]:
        r = 2.4 + 3.2 * min(1.0, float(p["confidence"]))
        parts.append(f'<circle cx="{x(p["date"]):.1f}" cy="{y(p["momentum"]):.1f}" r="{r:.2f}" '
                     f'fill="{accent}" opacity="{0.35 + 0.65 * min(1.0, float(p["confidence"])):.2f}">'
                     f'<title>{_esc(p["date"])} · momentum {p["momentum"]:+.3f} · confidence '
                     f'{p["confidence"]:.3f} · {p["signal_count"]} signals</title></circle>')

    # the outcome, on the far side of the wall
    parts.append(f'<line x1="{outcome_x:.1f}" y1="{PAD_T + 16}" x2="{outcome_x:.1f}" '
                 f'y2="{H - PAD_B}" stroke="{INK}" stroke-width="1" opacity="0.35"/>')
    parts.append(f'<circle cx="{outcome_x:.1f}" cy="{PAD_T + 16}" r="4.5" fill="{INK}">'
                 f'<title>{_esc(series["outcome_date"])} — {_esc(series["outcome"])}</title></circle>')
    parts.append(f'<text x="{outcome_x + 8:.1f}" y="{PAD_T + 19}" font-size="9" fill="{INK}">'
                 f'outcome {series["outcome_date"]}</text>')

    # captions
    flag = "  — KNOWN FAILURE CASE" if series["is_known_failure"] else ""
    parts.append(f'<text x="{PAD_L}" y="16" font-size="11.5" fill="{INK}" font-weight="600">'
                 f'{_esc(series["company"])} ({_esc(series["ticker"])}){_esc(flag)}</text>')
    final = series["final"]
    parts.append(f'<text x="{PAD_L}" y="{H - 32}" font-size="9" fill="{INK}">'
                 f'at cutoff: momentum {final["momentum"]:+.3f} · confidence '
                 f'{final["confidence"]:.3f} · {final["signal_count"]} signals · '
                 f'{_esc(final["label"])}</text>')
    parts.append(f'<text x="{PAD_L}" y="{H - 20}" font-size="8" fill="{GREY}">'
                 f'grey = incumbent baseline, flat: no rating action dated in this window '
                 f'(basis {_esc(series["baseline"]["basis"])}) · MOCK, not licensed LSEG</text>')
    parts.append(f'<text x="{PAD_L}" y="{H - 9}" font-size="8" fill="{GREY}">'
                 f'dashed = no evidence yet, not agreement · the drift back toward 0 between '
                 f'signals is time-decay, not recovery · dot size = confidence</text>')
    parts.append(f'<text x="{W - PAD_R + 10}" y="{zero - 6:.1f}" font-size="9" fill="{GREY}">'
                 f'LSEG baseline</text>')
    parts.append(f'<text x="{W - PAD_R + 10}" y="{y(series["points"][-1]["momentum"]) + 3:.1f}" '
                 f'font-size="9" fill="{accent}">our momentum</text>')
    parts.append(f'<text x="{W - PAD_R + 10}" y="{H - PAD_B - 4}" font-size="8" fill="{GREY}">'
                 f'ticks = dated evidence</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
def write_all(case_ids=None):
    data = all_series(case_ids)
    os.makedirs(OUT_DIR, exist_ok=True)
    for s in data:
        path = os.path.join(OUT_DIR, f"{s['case_id']}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_svg(s) + "\n")
        print(f"  {os.path.relpath(path, BASE_DIR):34s} {len(s['points']):2d} points · "
              f"{s['points'][0]['date']} -> {s['cutoff_date']} · "
              f"momentum {s['final']['momentum']:+.3f} · {s['final']['label']}")
    series_path = os.path.join(OUT_DIR, "series.json")
    with open(series_path, "w", encoding="utf-8") as fh:
        json.dump({"_note": "Per-case momentum series behind docs/backtest/*.svg. Every point is "
                            "a real engine run with its own cutoff — the value at date D is what "
                            "the Radar would have said on D. Regenerate: "
                            "`python backtest_timeline.py`.",
                   "generated_from": "data/backtest_cases.json",
                   "lookback_months": LOOKBACK_MONTHS,
                   "cases": data}, fh, indent=1, ensure_ascii=False)
    print(f"  {os.path.relpath(series_path, BASE_DIR):34s} the numbers behind the charts")
    return data


def print_series(data):
    for s in data:
        print(f"\n{s['company']} ({s['ticker']}) — {s['profile']}")
        print(f"  baseline: flat 0.000 (basis {s['baseline']['basis']}) · "
              f"cutoff {s['cutoff_date']} · outcome {s['outcome_date']}")
        for p in s["points"]:
            bar = int(round(abs(p["momentum"]) * 28))
            side = ("·" * (28 - bar) + "#" * bar) if p["momentum"] < 0 else \
                   (" " * 28 + "#" * bar)
            print(f"   {p['date']}  {p['momentum']:+.3f}  conf {p['confidence']:.2f}  "
                  f"n={p['signal_count']:2d}  |{side}")
        print(f"  -> {s['final']['label']}  ({s['outcome']})")


def main(argv):
    args = argv[1:]
    ids = None
    if "--case" in args:
        ids = {args[args.index("--case") + 1]}
    if "--print" in args:
        print_series(all_series(ids))
        return 0
    print("Backtest timelines — LSEG baseline (flat, grey) vs momentum (moving, accent)")
    write_all(ids)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
