"""sensitivity.py — what is this verdict standing on, and what would change it?

THE QUESTION THIS ANSWERS
-------------------------
A rating describes the past and a momentum reading describes the recent past. Neither can see
the future, and this module does not pretend to. What it can say — exactly, and without
guessing — is which pieces of evidence the current verdict is actually resting on, and how
close that verdict is to becoming a different one.

Two independent readings, because they fail differently:

  LEAVE-ONE-OUT   Re-score the company with one signal removed, once per signal. If the label
                  changes, that signal is load-bearing: the verdict exists because of it. If
                  nothing changes when any single signal goes, the verdict is corroborated and
                  the panel says so, which is the more reassuring answer.

  MARGINS         Every label boundary in `engine.label_for` is a number the record already
                  carries. The distance from each one is a fact, not a forecast: "momentum is
                  0.14 above the no-momentum line" tells a reader what would have to happen
                  without anyone predicting that it will.

PURE, LIKE THE ENGINE IT QUESTIONS
----------------------------------
No clock, no RNG, no network, no LLM. The same run and company always produce the same answer,
so this can be anchored and replayed alongside the run it describes (Gate 1).

THE COHORT IS PART OF THE ANSWER
--------------------------------
`momentum_percentile` is a RANK inside the scored universe, so removing a signal from one
company moves it relative to everybody else. The other companies did not change, so their
momenta are held fixed and only this one is re-ranked against them — which is precisely what
the next run would produce had that signal never been published. Re-scoring the company in
isolation would get the momentum right and the quadrant wrong.
"""
from typing import Any, Dict, List, Optional

import engine
import engine_config

# The label rules read these off the record; naming them here keeps the margin report and
# `engine.label_for` from drifting apart silently.
_BOUNDARY_NOTE = {
    "momentum": "Crossing zero flips improving to deteriorating, which changes the quadrant.",
    "rating_percentile": "The median rating splits the two left quadrants from the two right.",
    "disagreement": "Hidden Winners needs our percentile this far above the rating's.",
    "confidence": "Below this the evidence is too thin to claim a Hidden Winner.",
    "signal_count": "Hidden Winners needs at least this many independent signals.",
}


def _cohort_momenta(run: Dict[str, Any]) -> List[float]:
    """Every scored company's momentum, in the run's own record order."""
    return [float(r["composite_momentum"]) for r in run["records"]]


def _index_of(run: Dict[str, Any], company_id: str) -> int:
    for i, r in enumerate(run["records"]):
        if r["company_id"] == company_id:
            return i
    return -1


def _rescore(record: Dict[str, Any], signals: List[Dict[str, Any]], cfg: Dict[str, Any],
             as_of: str, momenta: List[float], idx: int) -> Dict[str, Any]:
    """Re-aggregate one company from a signal subset and re-label it inside the same cohort."""
    agg = engine._aggregate(signals, cfg, as_of)
    swapped = list(momenta)
    swapped[idx] = agg["composite_momentum"]
    mom_p = engine._percentiles(swapped)[idx]
    lseg_p = record["lseg_percentile"]
    probe = {
        "disagreement": round(mom_p - lseg_p, 6),
        "composite_confidence": agg["composite_confidence"],
        "signal_count": len(signals),
        "lseg_percentile": lseg_p,
        "composite_momentum": agg["composite_momentum"],
    }
    label = engine.label_for(probe, cfg)
    return {
        "label": label,
        "label_display": engine_config.display(cfg, label),
        "composite_momentum": agg["composite_momentum"],
        "composite_confidence": agg["composite_confidence"],
        "momentum_percentile": mom_p,
        "disagreement": probe["disagreement"],
        "signal_count": len(signals),
    }


def _margins(record: Dict[str, Any], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Signed distance from every boundary that decides this company's label.

    A margin is a measurement of the record as it stands, never a claim about where it is
    going. `distance` is how far the value would have to move to reach the line."""
    hw = cfg["labels"]["hidden_winners"]
    theta = engine_config.threshold(cfg, hw["min_disagreement"])
    rows = [
        ("momentum", "Live momentum", record["composite_momentum"], 0.0, "no momentum"),
        ("rating_percentile", "Rating percentile", record["lseg_percentile"], 0.5, "median rating"),
        ("disagreement", "Disagreement vs rating", record["disagreement"], theta,
         "Hidden Winner threshold"),
        ("confidence", "Evidence confidence", record["composite_confidence"],
         float(hw["min_confidence"]), "Hidden Winner minimum"),
        ("signal_count", "Signal count", float(record["signal_count"]),
         float(hw["min_signal_count"]), "Hidden Winner minimum"),
    ]
    out = []
    for key, label, value, line, line_name in rows:
        out.append({
            "key": key, "label": label, "value": round(value, 6),
            "boundary": round(line, 6), "boundary_name": line_name,
            "distance": round(value - line, 6),
            "side": "above" if value >= line else "below",
            "note": _BOUNDARY_NOTE[key],
        })
    # Closest first: the boundary a reader should actually watch is the nearest one.
    out.sort(key=lambda r: (abs(r["distance"]), r["key"]))
    return out


def flip_analysis(run: Dict[str, Any], company_id: str,
                  config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Leave-one-out + margins for one company in a finished run.

    Returns None when the company is not in the run. A company with no signals gets a valid
    answer with an empty `signals` list — "nothing is holding this up" is a real finding, not
    an error."""
    cfg = config or engine_config.load()
    idx = _index_of(run, company_id)
    if idx < 0:
        return None
    record = run["records"][idx]
    signals = list(record.get("signals") or [])
    as_of = run.get("as_of") or ""
    momenta = _cohort_momenta(run)
    current = record["label"]

    rows = []
    for s in signals:
        without = [x for x in signals if x["signal_id"] != s["signal_id"]]
        probe = _rescore(record, without, cfg, as_of, momenta, idx)
        rows.append({
            "signal_id": s["signal_id"],
            "published_at": s.get("published_at", ""),
            "source_type": s.get("source_type", ""),
            "source_url": s.get("source_url", ""),
            "rationale": s.get("rationale", ""),
            "excerpt": s.get("raw_text", ""),
            "component": s.get("component", ""),
            "direction": s.get("direction", 0),
            "momentum_without": probe["composite_momentum"],
            "momentum_delta": round(record["composite_momentum"] - probe["composite_momentum"], 6),
            "label_without": probe["label"],
            "label_without_display": probe["label_display"],
            "flips": probe["label"] != current,
        })
    # Biggest mover first, then by id so two equal deltas never swap between runs.
    rows.sort(key=lambda r: (-abs(r["momentum_delta"]), r["signal_id"]))

    load_bearing = [r for r in rows if r["flips"]]
    margins = _margins(record, cfg)

    # If no single signal decides it, how many of the heaviest would it take? Removing evidence
    # in |delta| order is the fastest honest route to the boundary; the count is the answer to
    # "how much would have to change", and None means not even all of them get there.
    smallest_flip = 1 if load_bearing else None
    if smallest_flip is None and rows:
        for k in range(2, len(rows) + 1):
            drop = {r["signal_id"] for r in rows[:k]}
            probe = _rescore(record, [s for s in signals if s["signal_id"] not in drop],
                             cfg, as_of, momenta, idx)
            if probe["label"] != current:
                smallest_flip = k
                break

    return {
        "company_id": company_id,
        "company": record["company"],
        "run_id": run["run_id"],
        "as_of": as_of,
        "label": current,
        "label_display": record["label_display"],
        "signal_count": len(signals),
        "signals": rows,
        "load_bearing_count": len(load_bearing),
        "smallest_flip_set": smallest_flip,
        "margins": margins,
        "verdict_note": _summary(record, len(signals), len(load_bearing), smallest_flip, margins),
        "disclaimer": ("Measurement of the evidence as it stands, not a forecast. It says what "
                       "this verdict rests on and how close it is to a boundary — never what "
                       "will happen next, and never a recommendation."),
    }


def _summary(record: Dict[str, Any], n: int, load_bearing: int,
             smallest: Optional[int], margins: List[Dict[str, Any]]) -> str:
    """One plain line a non-technical reader can act on.

    The count alone is ambiguous — "10 of 11 signals are load-bearing" does not mean ten
    important findings, it means the company is sitting on a boundary and almost anything tips
    it over. The nearest margin is what distinguishes the two, so it is read here."""
    near = margins[0] if margins else None
    edge = f" It is closest to the {near['boundary_name']} line." if near else ""
    if n == 0:
        return ("No signals carry this verdict yet, so there is nothing here to change. "
                "It rests on the rating alone.")
    if load_bearing == 1:
        return ("One signal decides this verdict on its own. Remove it and the label changes — "
                "so this is the row to watch, and the one to check hardest.")
    if n > 1 and load_bearing >= n - 1:
        return (f"This verdict is balanced on an edge: {load_bearing} of {n} signals change the "
                f"label on their own, so almost any single correction moves it.{edge}")
    if load_bearing > 1:
        return (f"{load_bearing} of {n} signals each change the label on their own. "
                f"The verdict is real but narrow — it stands on those specific findings.{edge}")
    if smallest and smallest >= n:
        return (f"No single signal decides it. Every one of the {n} would have to go before the "
                "label moved, so the verdict is corroborated rather than carried by any one "
                "finding.")
    if smallest:
        return (f"No single signal decides it: the {smallest} heaviest of {n} would all have to "
                "go before the label moved. The verdict is corroborated.")
    return (f"All {n} signals could be removed and the label would still hold — this verdict is "
            "coming from the rating gap, not from the evidence.")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: `python sensitivity.py <ticker> [--real] [--horizon long|short]`."""
    import argparse
    import json

    import company_metadata
    import universe

    ap = argparse.ArgumentParser(description="What would change this verdict?")
    ap.add_argument("ticker")
    ap.add_argument("--real", action="store_true", help="score the real ASEAN universe")
    ap.add_argument("--horizon", default=engine_config.DEFAULT_HORIZON)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    cfg = engine_config.for_horizon(a.horizon)
    path = universe.active_file(not a.real)
    run = engine.run_engine(universe.constituents(path),
                            metadata=company_metadata.load(), config=cfg)
    out = flip_analysis(run, a.ticker, cfg)
    if out is None:
        print(f"{a.ticker} is not in the scored universe.")
        return 1
    if a.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"{out['company']}  ({out['company_id']})")
    print(f"  verdict   {out['label_display']}   ·  {out['signal_count']} signals"
          f"  ·  run {out['run_id']}")
    print(f"  {out['verdict_note']}\n")
    print("  LEAVE-ONE-OUT")
    for r in out["signals"]:
        mark = "FLIPS ->" if r["flips"] else "        "
        print(f"    {mark} {r['momentum_delta']:+.4f}  {r['published_at']}  "
              f"{r['rationale'][:64]}")
        if r["flips"]:
            print(f"              without it: {r['label_without_display']}")
    print("\n  MARGINS (nearest boundary first)")
    for m in out["margins"]:
        print(f"    {m['label']:<24} {m['value']:>9.4f}  vs {m['boundary_name']}"
              f" {m['boundary']:.4f}   ({m['distance']:+.4f})")
    print(f"\n  {out['disclaimer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
