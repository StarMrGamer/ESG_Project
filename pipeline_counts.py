"""
pipeline_counts.py — A6 / B2: the three origination counts, N · M · K.
======================================================================
One function the dashboard calls live, and one script that freezes the same numbers for the
money slide. They share this code precisely so the slide and the screen can never disagree.

    N  issuers (priced in)  green_bond_status in {cbi_certified, labelled_reviewed}
    M  pipeline             matches the Balanced tier (A5) — the origination opportunity
    K  review list          we disagree (>= theta) but N and M both exclude it; a human looks

Definitions live in `data/engine_config.json` under `pipeline_counts`, not here.

    python pipeline_counts.py                 # print the counts for the demo universe
    python pipeline_counts.py --real          # the real ASEAN base DB
    python pipeline_counts.py --freeze        # write data/nmk_frozen.json (run id + date)

**Counts reproduce from the stored records** (B2): every input is either in the run record or in
the metadata CSV, so re-running the freeze on the same files reproduces the same three numbers.
"""

import json
import os
import sys

import company_metadata
import engine
import engine_config
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN_FILE = os.path.join(BASE_DIR, "data", "nmk_frozen.json")


def counts(run, metadata, cfg=None):
    """`{N, M, K, labels, members}` for a scored run. `members` lists the company ids behind each
    number so any count on a slide can be opened up and defended."""
    cfg = cfg or engine_config.load()
    rules = cfg["pipeline_counts"]
    theta = engine_config.threshold(cfg, rules["K"]["min_disagreement"])
    buckets = {"N": [], "M": [], "K": []}

    for record in run.get("records", []):
        meta = (metadata or {}).get(record["company_id"], {})
        status = meta.get("green_bond_status", "unknown")
        tiers = record.get("tiers") or engine.apply_tiers(dict(record), meta, cfg)["tiers"]

        in_n = status in rules["N"]["green_bond_status_in"]
        in_m = bool(tiers.get(rules["M"]["tier"]))
        if in_n:
            buckets["N"].append(record["company_id"])
        if in_m:
            buckets["M"].append(record["company_id"])
        if not in_n and not in_m and record["disagreement"] >= theta:
            buckets["K"].append(record["company_id"])

    return {
        "N": len(buckets["N"]), "M": len(buckets["M"]), "K": len(buckets["K"]),
        "labels": {k: rules[k]["label"] for k in ("N", "M", "K")},
        "rules": {k: rules[k]["rule"] for k in ("N", "M", "K")},
        "members": buckets,
        "universe_size": run.get("company_count", 0),
        "theta": theta,
    }


def freeze(run, metadata, cfg=None, frozen_at=""):
    """The record handed to Brina/Grace: the counts plus everything needed to re-derive them."""
    result = counts(run, metadata, cfg)
    cfg = cfg or engine_config.load()
    report = company_metadata.load_report()
    return {
        "_note": "Frozen N/M/K for the money slide (B2). Re-derivable: same run_id + same "
                 "metadata file -> same three numbers.",
        "run_id": run["run_id"],
        "engine_version": run["engine_version"],
        "config_version": cfg["config_version"],
        "config_hash": run["config_hash"],
        "as_of": run["as_of"],
        "frozen_at": frozen_at,
        "metadata_file": report.get("path", ""),
        "metadata_rows": report.get("rows", 0),
        "metadata_provisional": report.get("provisional", 0),
        "counts": {k: result[k] for k in ("N", "M", "K")},
        "labels": result["labels"],
        "rules": result["rules"],
        "members": result["members"],
        "universe_size": result["universe_size"],
        "caveat": ("Counts derived from PROVISIONAL metadata — every green-bond field is "
                   "unverified until the Phase B1 CSV swap."
                   if report.get("provisional") else ""),
    }


def _today():
    """Wall-clock date, used ONLY to stamp a freeze record. No engine input reads a clock."""
    import datetime
    return datetime.date.today().isoformat()


def main(argv):
    real = "--real" in argv
    cfg = engine_config.load()
    metadata = company_metadata.load()
    source = universe.active_file(demo=not real)
    run = engine.run_engine(universe.constituents(source), metadata=metadata, use_cache=False)
    result = counts(run, metadata, cfg)

    scope = "real ASEAN base DB" if real else "demo universe (fictional)"
    print(f"N/M/K — {scope} · run {run['run_id']} · as_of {run['as_of']}")
    for key in ("N", "M", "K"):
        print(f"  {key} = {result[key]:3d}  {result['labels'][key]:<22s} {result['rules'][key]}")
    print(f"  universe {result['universe_size']} · theta {result['theta']}")

    if "--freeze" in argv:
        record = freeze(run, metadata, cfg, frozen_at=_today())
        with open(FROZEN_FILE, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, sort_keys=True)
        print(f"\nfroze -> {os.path.relpath(FROZEN_FILE, BASE_DIR)} "
              f"(run {record['run_id']}, {record['frozen_at']})")
        if record["caveat"]:
            print(f"  CAVEAT: {record['caveat']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
