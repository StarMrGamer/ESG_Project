"""
calibration.py — A8 / STEP 8.4: two humans score ten companies, blind, against the model.
=========================================================================================

    python calibration.py --sheet      # write the BLIND rating sheet (refuses to clobber ratings)
    python calibration.py --sheet --universe cases   # ...backtest cases only (or real / demo)
    python calibration.py --rate rater_a --name "Your Name"   # rate them, one keypress each
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


import os as _os, sys as _sys
# tools/ -> repo root, BEFORE any app import below.
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import json
import os
import sys

import backtest_timeline
import company_metadata
import engine
import universe

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
UNIVERSES = {"pooled": "data/backtest_cases.json + data/asean_universe.json",
             "cases": "data/backtest_cases.json",
             "real": universe.UNIVERSE_FILE,
             "demo": universe.DEMO_FILE}
DEFAULT_UNIVERSE = "pooled"
MIN_EXCERPTS = 2       # below this there is nothing for a human to weigh

# What each candidate set is actually good for. Printed into the sheet and the report, because
# the honest reading of an agreement statistic depends entirely on which set produced it.
UNIVERSE_CAVEAT = {
    "pooled": "The backtest cases plus every real ASEAN name carrying at least two excerpts. "
              "The cases are what put a DETERIORATING company in the set (Top Glove) and a "
              "contested one (Adaro) — without them every rateable name is Future Leaders or "
              "Consensus, and a rater answering '+1' to everything would score well. Where a "
              "ticker appears in both, the case wins: its evidence is dated and cutoff-frozen. "
              "Mixed provenance, stated here rather than smoothed over.",
    "cases": "The backtest cases alone: real, dated, sourced prose, and the only set that "
             "contains BOTH directions. Fewer companies than the runbook's ten — that is all "
             "the evidence of this quality we hold, and padding it with one-sentence names "
             "would buy a rounder number and a worse test.",
    "real": "The real 52, restricted to names carrying at least two excerpts. Genuine prose, "
            "but every qualifying company is Future Leaders or Consensus: there is no "
            "deteriorating name in the set, so a rater who answers '+1' to everything scores "
            "well and the statistic cannot tell them apart from someone reading carefully.",
    "demo": "The demo fixture. CIRCULAR — its excerpts are the engine's own stored numbers "
            "rendered as text ('stored environment momentum +7%'), so a rater is handed the "
            "conclusion in words. Available for wiring tests; not a calibration.",
}


def _run(which=DEFAULT_UNIVERSE, config=None):
    """Score one candidate set and hand back a run-shaped dict.

    The default pools the backtest cases with the real 52, and that is a correctness choice
    rather than a preference — see UNIVERSE_CAVEAT for what each set is worth.
    """
    if which == "pooled":
        cases = _run("cases", config)
        real = _run("real", config)
        seen = {r["company_id"] for r in cases["records"]}
        return dict(cases, records=cases["records"] + [r for r in real["records"]
                                                       if r["company_id"] not in seen],
                    run_id="pooled-" + cases["config_hash"][:8],
                    company_count=len(cases["records"]) + len(real["records"]))
    if which == "cases":
        # Each case is scored with its lookback frozen at its own cutoff, exactly as the harness
        # scores it, so the record a rater is compared against is the one we already publish.
        records = []
        for case in backtest_timeline.load_cases()["cases"]:
            run = engine.run_engine([backtest_timeline.case_company(case)],
                                    cutoff=case["cutoff_date"], use_cache=False, config=config)
            records.append(run["records"][0])
        cfg_run = run
        return {"run_id": "cases-" + cfg_run["config_hash"][:8],
                "engine_version": cfg_run["engine_version"],
                "config_hash": cfg_run["config_hash"], "as_of": cfg_run["as_of"],
                "records": records, "labels": cfg_run["labels"],
                "company_count": len(records)}
    path = UNIVERSES.get(which, universe.UNIVERSE_FILE)
    demo = path == universe.DEMO_FILE
    cons = universe.constituents(path)
    if not demo:
        import harvest
        cons = harvest.apply_overlay(cons)     # rate what the board actually shows
    return engine.run_engine(cons, metadata=company_metadata.load(demo=demo),
                             use_cache=False, config=config)


def _universe_of(sheet):
    """Which set a sheet was frozen against — so a sheet is always scored against the same
    names it was written from, even after the default changes."""
    named = ((sheet or {}).get("frozen_against") or {}).get("universe") or ""
    for key, path in UNIVERSES.items():
        if named and (named == path or os.path.basename(path) == os.path.basename(named)):
            return key
    return DEFAULT_UNIVERSE


def select(run, size=SET_SIZE):
    """Pick the calibration set.

    Two rules, in order. First, a company must carry at least MIN_EXCERPTS excerpts — you
    cannot ask a human which way a company is heading and then show them nothing, and a
    one-line sheet produces a coin flip dressed as a judgement. Second, if more companies
    qualify than we need, take them round-robin across quadrants, alphabetical within each:
    a sheet of ten Hidden Winners would only tell us how well humans agree with the engine
    about companies the engine already feels strongly about, which is the easy half.

    If fewer qualify than `size`, the set is simply smaller. Padding it to a round number with
    names we hold one sentence about would buy the number and lose the measurement."""
    eligible = [r for r in run["records"] if r["signal_count"] >= MIN_EXCERPTS]
    if len(eligible) <= size:
        return sorted(eligible, key=lambda r: r["company_id"])
    by_label = {}
    for rec in sorted(eligible, key=lambda r: r["company_id"]):
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


def build_sheet(run, which=DEFAULT_UNIVERSE):
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
        "set": which,
        "_what_this_set_is_worth": UNIVERSE_CAVEAT[which],
        "frozen_against": {"run_id": run["run_id"], "engine_version": run["engine_version"],
                           "config_hash": run["config_hash"], "as_of": run["as_of"],
                           "universe": (os.path.relpath(UNIVERSES[which], BASE_DIR)
                                        if os.path.isabs(UNIVERSES[which])
                                        else UNIVERSES[which])},
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


def write_sheet(force=False, which=DEFAULT_UNIVERSE):
    run = _run(which)
    fresh = build_sheet(run, which)
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
    if len(fresh["companies"]) < SET_SIZE:
        print(f"  NOTE: {len(fresh['companies'])} companies, not {SET_SIZE} — only that many "
              f"carry >= {MIN_EXCERPTS} excerpts in the '{which}' set.")
    print(f"  set '{which}': {UNIVERSE_CAVEAT[which]}")
    return 0


def load_sheet(path=None):
    try:
        with open(path or SHEET_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- #
#  rating — the fast path
# --------------------------------------------------------------------------- #
KEYS = {"-2": -2, "2-": -2, "-1": -1, "1-": -1, "0": 0,
        "1": 1, "+1": 1, "2": 2, "+2": 2}


def rate(rater, name=None, path=None):
    """Walk the sheet one company at a time and take a single keypress per call.

    Hand-editing 108 excerpts of JSON is why calibration studies do not get done. This is the
    same sheet and the same blindness — it just removes the typing. It saves after every answer,
    so quitting halfway keeps what you did, and it never shows you the model's score.
    """
    if rater not in RATERS:
        print(f"unknown rater {rater!r} — expected one of {', '.join(RATERS)}")
        return 2
    sheet = load_sheet(path)
    if not sheet:
        print(f"no sheet at {os.path.relpath(path or SHEET_FILE, BASE_DIR)} — "
              f"run `python calibration.py --sheet` first")
        return 2
    if name:
        sheet.setdefault("raters", {}).setdefault(rater, {})["name"] = name

    companies = sheet.get("companies", [])
    print(f"\nRATING AS {rater}"
          f"{' (' + name + ')' if name else ''} — {len(companies)} companies, blind.")
    print("You are judging ONE thing: which way is this company's ESG heading over the next "
          "12 months,\non the evidence shown? The model's answer is not in this file and will "
          "not be shown to you.\n")

    for i, entry in enumerate(companies, 1):
        slot = entry.setdefault("ratings", {}).setdefault(rater, {"rating": None, "note": ""})
        if slot.get("rating") is not None:
            print(f"[{i}/{len(companies)}] {entry['company']} — already rated "
                  f"{slot['rating']:+d}, skipping")
            continue
        print("=" * 78)
        print(f"[{i}/{len(companies)}] {entry['company']} · {entry.get('sector', '?')} · "
              f"{entry.get('country', '?')} · {len(entry['evidence'])} excerpts")
        print("=" * 78)
        for ev in entry["evidence"]:
            print(f"  {ev['published_at']}  [{ev['source_type']}]  {ev['excerpt']}")
        print("\n  -2 strongly deteriorating   -1 deteriorating   0 flat/unclear"
              "\n  +1 improving                +2 strongly improving"
              "\n  s skip (honest abstention)  q save and quit")
        while True:
            try:
                answer = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "q"
                print()
            if answer in ("q", "quit"):
                _save(sheet, path)
                print(f"\nsaved. re-run the same command to pick up where you stopped.")
                return 0
            if answer in ("s", "skip", ""):
                print("  abstained — counted separately, not as a zero.\n")
                break
            if answer in KEYS:
                slot["rating"] = KEYS[answer]
                note = input("  why, in a few words (optional) > ").strip()
                if note:
                    slot["note"] = note
                _save(sheet, path)
                print(f"  recorded {KEYS[answer]:+d}\n")
                break
            print("  -2 / -1 / 0 / +1 / +2, or s to skip, q to quit")

    _save(sheet, path)
    done = sum(1 for c in companies if (c["ratings"].get(rater) or {}).get("rating") is not None)
    print(f"\ndone — {done}/{len(companies)} rated as {rater}.")
    print("Once BOTH raters have a column, `python calibration.py` scores it.")
    return 0


def _save(sheet, path=None):
    target = path or SHEET_FILE
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(sheet, fh, indent=1, ensure_ascii=False)


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
    run = run or _run(_universe_of(sheet))
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
        "set": sheet.get("set", _universe_of(sheet)),
        "set_caveat": sheet.get("_what_this_set_is_worth", ""),
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
    print(f"  set                       {result.get('set', '?')} "
          f"({result['frozen_against'].get('universe', '?')})")
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
    if result.get("set_caveat"):
        print(f"\n  WHAT THIS SET IS WORTH\n    {_wrap_c(result['set_caveat'], 4)}")
    print("\n  Read it honestly: if the model tracks the humans NO better than the humans track "
          "\n  each other, the engine is inside human noise — say that, don't claim more.")
    return 0


def _wrap_c(text, indent, width=92):
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width - indent:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    lines.append(cur)
    return ("\n" + " " * indent).join(lines)


def main(argv):
    args = argv[1:]
    flags = set(args)

    def _after(flag):
        i = args.index(flag) if flag in args else -1
        return args[i + 1] if 0 <= i < len(args) - 1 else None

    if "--sheet" in flags:
        return write_sheet(force="--force" in flags,
                           which=_after("--universe") or DEFAULT_UNIVERSE)
    if "--rate" in flags:
        return rate(_after("--rate") or "", _after("--name"))
    result = score()
    if "--json" in flags:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    return report(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
