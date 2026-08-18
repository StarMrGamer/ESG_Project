"""
calibration.py — A8 / STEP 8.4: two humans score ten companies, blind, against the model.
=========================================================================================

    python calibration.py --sheet      # write the BLIND rating sheet (refuses to clobber ratings)
    python calibration.py              # score whatever ratings the sheet now holds
    python calibration.py --json       # the same report as JSON, for the eval appendix

Why this exists, and why it is built the way it is
--------------------------------------------------
The sensitivity sweep answers "is the engine stable?". Calibration answers a different and
harder question: **does the engine agree with a human reading the same evidence?** A model that
is perfectly reproducible and perfectly wrong passes every other check in the harness.

Two design choices carry the whole thing:

1. **The sheet is blind.** Raters see the evidence the engine saw — date, source type, the
   excerpt, the URL — and nothing else. No direction, no materiality, no confidence, no
   rationale, no composite. If the sheet showed the model's answer, the raters would be
   scoring their agreement with a number they had already been told, and the agreement
   statistic would measure suggestibility rather than calibration.

2. **The model's score is never stored in the sheet.** It is recomputed from the engine at
   report time. So the comparison is always against the CURRENT engine, and a sheet filled in
   last week keeps its value when a config knob moves — the disagreement simply changes, which
   is the interesting part.

Nothing here fabricates a human. With the rater slots empty the report says UNMEASURED and the
harness says so too; it never quietly reports "calibrated" on zero human ratings.
"""

import json
import os
import sys

import company_metadata
import engine
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_FILE = os.path.join(BASE_DIR, "data", "calibration_sheet.json")

SET_SIZE = 10
RATERS = ("rater_a", "rater_b")

# The five-point ordinal both sides answer on. Humans pick a word; the engine's continuous
# composite is bucketed onto the same five points by the cut-points below, which are frozen
# INTO the sheet so a later edit cannot quietly move the goalposts after the humans have voted.
SCALE = {
    -2: "strongly deteriorating",
    -1: "deteriorating",
    0: "flat / unclear",
    1: "improving",
    2: "strongly improving",
}
# |composite| below WEAK is "flat"; between WEAK and STRONG is one step; above STRONG is two.
# Both numbers are read off what the composite MEANS, not fitted to make the buckets look even.
# composite = direction_consensus x shrinkage, and consensus is the share of evidence weight
# pointing one way mapped onto [-1,+1]: 0.10 is the point where the evidence stops being
# essentially balanced (55/45), and 0.45 is roughly a 72/28 majority once a company carries
# enough evidence for shrinkage to stop biting. Frozen into the sheet before anyone votes.
DEFAULT_CUTPOINTS = {"weak": 0.10, "strong": 0.45}


# --------------------------------------------------------------------------- #
#  the set
# --------------------------------------------------------------------------- #
def _demo_run(config=None):
    return engine.run_engine(universe.constituents(universe.DEMO_FILE),
                             metadata=company_metadata.load(), use_cache=False, config=config)


def select(run, size=SET_SIZE):
    """Pick the calibration set: round-robin across quadrants, alphabetical within each.

    Deterministic, and deliberately NOT "the ten most interesting names" — a sheet of ten
    Hidden Winners would tell us how well humans and the engine agree about companies the
    engine already feels strongly about, which is the easy half of the question."""
    by_label = {}
    for rec in sorted(run["records"], key=lambda r: r["company_id"]):
        by_label.setdefault(rec["label"], []).append(rec)
    picked, i = [], 0
    while len(picked) < size and any(len(v) > i for v in by_label.values()):
        for label in sorted(by_label):
            if len(by_label[label]) > i and len(picked) < size:
                picked.append(by_label[label][i])
        i += 1
    return picked


def _evidence_for(record):
    """The excerpts a rater reads — and ONLY those. Everything the engine concluded is stripped
    here on purpose (see the module docstring): direction, materiality, confidence, the routing
    and the rationale are all the model's answer, not the evidence."""
    return [{"published_at": s.get("published_at", ""),
             "source_type": s.get("source_type", ""),
             "excerpt": s.get("raw_text", ""),
             "source_url": s.get("source_url", "")}
            for s in sorted(record.get("signals") or [],
                            key=lambda s: (s.get("published_at", ""), s["signal_id"]))]


def build_sheet(run):
    return {
        "_note": "BLIND calibration sheet (A8 / STEP 8.4). Two raters score each company's "
                 "12-month ESG DIRECTION from the excerpts below — the same evidence the engine "
                 "saw — on the five-point scale in `scale`. The engine's own score is NOT in "
                 "this file, by design: it is recomputed at report time so the rating cannot be "
                 "anchored to it. Fill `rating` (-2..+2) and, please, `note`.",
        "_how_to_fill": "Set `raters.rater_a.name` (and rater_b) to who scored it, then for each "
                        "company set `ratings.<rater>.rating` to one of -2,-1,0,1,2. Leave a "
                        "company null if you genuinely cannot call it — an honest abstention "
                        "beats a coin flip, and the report counts it separately.",
        "scale": {str(k): v for k, v in SCALE.items()},
        "model_cutpoints": dict(DEFAULT_CUTPOINTS),
        "_cutpoints_note": "How the engine's continuous composite is put on the humans' five "
                           "points: |m| < weak -> 0; weak <= |m| < strong -> +/-1; "
                           "|m| >= strong -> +/-2. Frozen here with the sheet.",
        "_what_is_graded": "The headline number is DIRECTION agreement (-/0/+) — that is the "
                           "claim the product makes. The five-point intensity agreement is "
                           "reported underneath it as detail. Score the direction carefully; "
                           "give the intensity your honest best guess and move on.",
        "frozen_against": {"run_id": run["run_id"], "engine_version": run["engine_version"],
                           "config_hash": run["config_hash"], "as_of": run["as_of"],
                           "universe": os.path.relpath(universe.DEMO_FILE, BASE_DIR)},
        "raters": {r: {"name": None, "rated_at": None} for r in RATERS},
        "companies": [
            {"company_id": rec["company_id"], "company": rec["company"],
             "sector": rec.get("sector", "unknown"), "country": rec.get("country", "unknown"),
             "signal_count": rec["signal_count"],
             "evidence": _evidence_for(rec),
             "ratings": {r: {"rating": None, "note": ""} for r in RATERS}}
            for rec in select(run)
        ],
    }


def write_sheet(force=False):
    run = _demo_run()
    fresh = build_sheet(run)
    if os.path.exists(SHEET_FILE) and not force:
        existing = load_sheet()
        filled = sum(1 for c in existing.get("companies", [])
                     for r in RATERS if c.get("ratings", {}).get(r, {}).get("rating") is not None)
        if filled:
            print(f"REFUSING to overwrite {os.path.relpath(SHEET_FILE, BASE_DIR)} — it already "
                  f"holds {filled} human rating(s). Re-run with --force if you really mean to "
                  f"throw away someone's work.")
            return 2
    os.makedirs(os.path.dirname(SHEET_FILE), exist_ok=True)
    with open(SHEET_FILE, "w", encoding="utf-8") as fh:
        json.dump(fresh, fh, indent=1, ensure_ascii=False)
    print(f"  wrote {os.path.relpath(SHEET_FILE, BASE_DIR)} — {len(fresh['companies'])} companies, "
          f"{sum(len(c['evidence']) for c in fresh['companies'])} excerpts, "
          f"{len(RATERS)} blank rater columns")
    return 0


def load_sheet(path=None):
    try:
        with open(path or SHEET_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- #
#  scoring
# --------------------------------------------------------------------------- #
def bucket(momentum, cutpoints=None):
    """The engine's continuous composite, placed on the humans' five points."""
    cp = cutpoints or DEFAULT_CUTPOINTS
    m = float(momentum)
    sign = 1 if m > 0 else -1 if m < 0 else 0
    a = abs(m)
    if a < float(cp["weak"]):
        return 0
    return sign * (2 if a >= float(cp["strong"]) else 1)


def cohens_kappa(pairs):
    """Plain Cohen's kappa over paired ordinal ratings. 1.0 = perfect, 0.0 = chance."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    cats = sorted({v for pair in pairs for v in pair})
    expected = sum((sum(1 for a, _ in pairs if a == c) / n) *
                   (sum(1 for _, b in pairs if b == c) / n) for c in cats)
    if expected >= 1.0:                     # everyone always said the same thing
        return 1.0 if observed >= 1.0 else 0.0
    return round((observed - expected) / (1.0 - expected), 3)


def _sign(v):
    return 0 if v == 0 else (1 if v > 0 else -1)


def _agreement(pairs):
    n = len(pairs)
    if n == 0:
        return {"n": 0, "exact": None, "within_1": None, "kappa": None, "mae": None}
    return {
        "n": n,
        "exact": round(100.0 * sum(1 for a, b in pairs if a == b) / n, 1),
        "within_1": round(100.0 * sum(1 for a, b in pairs if abs(a - b) <= 1) / n, 1),
        "kappa": cohens_kappa(pairs),
        "mae": round(sum(abs(a - b) for a, b in pairs) / n, 2),
    }


def score(sheet=None, run=None):
    """Compare the sheet's human ratings against the CURRENT engine. Never invents a rater."""
    sheet = sheet if sheet is not None else load_sheet()
    if not sheet:
        return {"status": "no_sheet",
                "detail": f"{os.path.relpath(SHEET_FILE, BASE_DIR)} is missing — "
                          f"run `python calibration.py --sheet`"}
    run = run or _demo_run()
    cutpoints = sheet.get("model_cutpoints") or DEFAULT_CUTPOINTS
    by_id = {r["company_id"]: r for r in run["records"]}

    rows, missing, out_of_scale = [], [], []
    for entry in sheet.get("companies", []):
        cid = entry["company_id"]
        rec = by_id.get(cid)
        if rec is None:
            missing.append(cid)
            continue
        row = {"company_id": cid, "company": entry.get("company", cid),
               "model_momentum": rec["composite_momentum"],
               "model": bucket(rec["composite_momentum"], cutpoints),
               "label": rec["label_display"], "signal_count": rec["signal_count"]}
        for rater in RATERS:
            v = (entry.get("ratings", {}).get(rater) or {}).get("rating")
            if v is not None and (not isinstance(v, int) or v not in SCALE):
                out_of_scale.append(f"{cid}/{rater}={v!r}")
                v = None
            row[rater] = v
        rows.append(row)

    rated = sum(1 for row in rows for r in RATERS if row[r] is not None)
    result = {
        "status": "measured" if rated else "unmeasured",
        "companies": len(rows), "ratings_recorded": rated,
        "ratings_possible": len(rows) * len(RATERS),
        "raters": {r: (sheet.get("raters", {}).get(r) or {}).get("name") for r in RATERS},
        "missing_from_run": missing, "out_of_scale": out_of_scale,
        "cutpoints": cutpoints, "rows": rows,
        "frozen_against": sheet.get("frozen_against", {}),
        "run": {"run_id": run["run_id"], "config_hash": run["config_hash"]},
    }
    a, b = RATERS
    both = [row for row in rows if row[a] is not None and row[b] is not None]
    result["inter_rater"] = _agreement([(row[a], row[b]) for row in both])
    for rater in RATERS:
        result[f"model_vs_{rater}"] = _agreement([(row["model"], row[rater]) for row in rows
                                                  if row[rater] is not None])

    # DIRECTION is the headline, and the five-point scale is the detail underneath it. The
    # product claims which way a company is HEADING, not how hard; and on the demo fixture every
    # name carries one coherent trajectory, so |composite| clusters in a narrow band and the
    # intensity half of the scale has almost nothing to separate. Grading ourselves on intensity
    # there would measure the fixture, not the engine.
    result["direction_inter_rater"] = _agreement(
        [(_sign(row[a]), _sign(row[b])) for row in both])
    for rater in RATERS:
        result[f"direction_model_vs_{rater}"] = _agreement(
            [(_sign(row["model"]), _sign(row[rater])) for row in rows if row[rater] is not None])
    # Against the raters' consensus, counting only companies BOTH humans called — a company one
    # human abstained on is not a consensus, and averaging one vote into a "consensus" would
    # quietly upgrade a single opinion.
    consensus = []
    for row in rows:
        if row[a] is None or row[b] is None:
            continue
        mean = (row[a] + row[b]) / 2.0
        consensus.append((row["model"], int(mean) if mean == int(mean)
                          else int(mean + (0.5 if mean > 0 else -0.5))))
    result["model_vs_consensus"] = _agreement(consensus)
    result["direction_model_vs_consensus"] = _agreement(
        [(_sign(m), _sign(h)) for m, h in consensus])
    spread = [abs(row["model_momentum"]) for row in rows]
    result["model_momentum_band"] = (
        {"min": round(min(spread), 3), "max": round(max(spread), 3)} if spread else {})
    return result


# --------------------------------------------------------------------------- #
#  report
# --------------------------------------------------------------------------- #
def _fmt(stats):
    if not stats or not stats["n"]:
        return "no paired ratings"
    return (f"n={stats['n']:2d}  exact {stats['exact']:5.1f}%  within-1 {stats['within_1']:5.1f}%  "
            f"kappa {stats['kappa']}  MAE {stats['mae']}")


def report(result=None):
    result = result or score()
    if result.get("status") == "no_sheet":
        print("CALIBRATION — " + result["detail"])
        return 2

    print(f"CALIBRATION — {result['companies']} companies, {len(RATERS)} raters, "
          f"5-point direction scale")
    names = " · ".join(f"{r}: {result['raters'][r] or '(unnamed)'}" for r in RATERS)
    print(f"  raters                    {names}")
    print(f"  ratings recorded          {result['ratings_recorded']}/{result['ratings_possible']}")
    cp = result["cutpoints"]
    print(f"  model cut-points          |m| < {cp['weak']} -> 0 · < {cp['strong']} -> +/-1 · "
          f"else +/-2")
    print(f"  scored against            run {result['run']['run_id']} "
          f"(config {result['run']['config_hash']})")
    if result["missing_from_run"]:
        print(f"  !! not in the current run  {result['missing_from_run']}")
    if result["out_of_scale"]:
        print(f"  !! off-scale ratings       {result['out_of_scale']}")

    if result["status"] == "unmeasured":
        print("\n  UNMEASURED — no human has scored this sheet yet. Calibration is the one check "
              "\n  in the harness that cannot be run by the machine: fill "
              f"{os.path.relpath(SHEET_FILE, BASE_DIR)}"
              "\n  and re-run. Until then this reports nothing, rather than reporting a pass.")
        return 0

    print()
    a, b = RATERS
    print(f"  {'company':26s} {'model':>7s} {'':2s} {a:>8s} {b:>8s}   quadrant")
    for row in result["rows"]:
        show = lambda v: "  ·" if v is None else f"{v:+d}"          # noqa: E731
        print(f"  {row['company'][:26]:26s} {show(row['model']):>7s} "
              f"({row['model_momentum']:+.2f}) {show(row[a]):>8s} {show(row[b]):>8s}   {row['label']}")
    band = result.get("model_momentum_band") or {}
    print()
    print("  DIRECTION (the claim the product actually makes: which way, not how hard)")
    print(f"    inter-rater (a vs b)    {_fmt(result['direction_inter_rater'])}")
    print(f"    model vs {a:13s}  {_fmt(result[f'direction_model_vs_{a}'])}")
    print(f"    model vs {b:13s}  {_fmt(result[f'direction_model_vs_{b}'])}")
    print(f"    model vs consensus      {_fmt(result['direction_model_vs_consensus'])}")
    print()
    print("  INTENSITY (the full five points — secondary, and read it with the band in mind)")
    print(f"    inter-rater (a vs b)    {_fmt(result['inter_rater'])}")
    print(f"    model vs {a:13s}  {_fmt(result[f'model_vs_{a}'])}")
    print(f"    model vs {b:13s}  {_fmt(result[f'model_vs_{b}'])}")
    print(f"    model vs consensus      {_fmt(result['model_vs_consensus'])}")
    if band:
        print(f"    |composite| on this set spans {band['min']:.2f}..{band['max']:.2f} — a narrow "
              f"band, so\n    intensity has little to separate and mostly reads out the fixture.")
    print("\n  Read it honestly: if the model tracks the humans NO better than the humans track "
          "\n  each other, the engine is inside human noise — say that, don't claim more.")
    return 0


def main(argv):
    flags = set(argv[1:])
    if "--sheet" in flags:
        return write_sheet(force="--force" in flags)
    result = score()
    if "--json" in flags:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    return report(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
