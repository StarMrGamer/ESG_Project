"""
demo_diversify.py — re-derive ONLY the enrichment blocks in `data/demo_universe.json`.
======================================================================================
Rewrites each demo constituent's `momentum`, `live_signals`, `news` and `trajectory` from the
current `demo_enrich`, and leaves everything else — `esg_score`, `esg_breakdown`,
`data_provenance`, `market`, `analyst_coverage`, `price_change_90d` — byte-identical.

Why not just re-run `build_demo_universe.py`? Because that re-derives the ESG scores from
whatever country table is reachable, and the committed file was built from a live pull rather
than the bundled fallback: a full rebuild silently moves 24 of the 36 scores. Those scores are
the MOCK baseline the whole disagreement matrix is measured against, so moving them would
change every percentile, every `disagreement` and every quadrant for reasons that have nothing
to do with this change.

    python demo_diversify.py            # rewrite in place
    python demo_diversify.py --dry-run  # show what would change

Deterministic (seeded off the company name), so re-running never churns the file.
"""

import json
import os
import sys

from scripts import demo_enrich

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_FILE = os.path.join(BASE_DIR, "data", "demo_universe.json")
PRESERVED = ("company", "ticker", "exchange", "country", "sector", "esg_score", "esg_as_of",
             "esg_breakdown", "data_provenance", "market", "analyst_coverage", "price_change_90d")


def diversify(universe):
    """Returns (universe, changes) with the enrichment blocks re-derived in place."""
    changes = []
    for c in universe["constituents"]:
        name = c["company"]
        traj = demo_enrich.trajectory(name)
        before = dict(momentum=c.get("momentum"), live_signals=c.get("live_signals"),
                      news=c.get("news"))
        c["momentum"] = demo_enrich.momentum(name, c["esg_breakdown"], traj)
        c["live_signals"] = demo_enrich.live_signals(name, traj)
        c["news"] = demo_enrich.news(name, traj)
        c["trajectory"] = traj
        if any(before[k] != c[k] for k in before):
            changes.append((c["ticker"], traj))
    universe["note"] = (
        "DEMO universe — fictional companies, scores DERIVED from real country-level "
        "OECD/World Bank indicators (sector-adjusted). Illustrative, not company disclosure. "
        "Each name carries one coherent trajectory (improving / mixed / deteriorating) so its "
        "momentum, live signals and headlines tell the same story.")
    return universe, changes


def main(argv):
    with open(DEMO_FILE, "r", encoding="utf-8") as fh:
        universe = json.load(fh)
    kept = {c["ticker"]: {k: c.get(k) for k in PRESERVED} for c in universe["constituents"]}

    universe, changes = diversify(universe)

    # the guarantee this script exists to make
    for c in universe["constituents"]:
        for key, value in kept[c["ticker"]].items():
            assert c.get(key) == value, f"{c['ticker']}.{key} must not move: {value} -> {c.get(key)}"

    counts = {}
    for _, traj in changes:
        counts[traj] = counts.get(traj, 0) + 1
    print(f"{len(changes)} of {len(universe['constituents'])} constituents re-derived: "
          + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print("preserved untouched: " + ", ".join(PRESERVED))

    if "--dry-run" in argv:
        print("\n--dry-run: nothing written.")
        return 0
    with open(DEMO_FILE, "w", encoding="utf-8") as fh:
        json.dump(universe, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(DEMO_FILE, BASE_DIR)} — re-run `python harness.py "
           "--update-golden` and review the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
