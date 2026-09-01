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


def _sector_peer_averages(run):
    """`{industry: mean baseline score}` over the run's own records.

    Computed from the RUN, not from the universe file, so the peer bar a company is measured
    against is exactly the cohort it was ranked in — and a filtered or backtested run cannot
    silently compare against a different set of peers."""
    buckets = {}
    for record in run.get("records", []):
        score = record.get("baseline_score")
        if score is None:
            continue
        buckets.setdefault(record.get("industry") or record.get("sector"), []).append(score)
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


def _is_bond_ready(record, meta, rule, peer_avg):
    """M: the origination pipeline — a company with a fundable gap and evidence it is closing it.

    Five conditions, all from `data/engine_config.json` (see the `_note` there for why "below
    sector benchmark" is measured in ESG-score terms and not in the Eurostat GHG intensity):

      1. not delisted            — a stale basket member is a finding, never a recommendation
      2. below its peer average  — the gap the use-of-proceeds would close
      3. positive momentum       — evidence that management is actually moving
      4. passes the financial screen — profitable, or loss_making WITH traction
      5. not already an issuer   — N is priced in; M is the opportunity that is not

    This screen sets ISSUER SELECTION and ORIGINATION PRIORITY. Eligibility is a bond-level
    question that attaches to use-of-proceeds, framework and external review under ICMA /
    ASEAN GBS — never to the company, and never to this number."""
    if rule.get("exclude_delisted") and record.get("delisted"):
        return False

    if rule.get("below_sector_peer_average"):
        score = record.get("baseline_score")
        average = peer_avg.get(record.get("industry") or record.get("sector"))
        if score is None or average is None or score >= average:
            return False

    if record.get("composite_momentum", 0.0) <= rule.get("min_momentum_exclusive", 0.0):
        return False

    profitability = meta.get("profitability_flag", "unknown")
    if profitability not in rule.get("profitability_in", ["profitable"]):
        # The traction screen (playbook step 4): a loss-maker is routed here rather than being
        # failed on the profit flag. Thresholds are the TEAM's, never CGSI-approved, and an
        # unrun screen is a miss — `has_traction` is False until somebody fills the column.
        if not (profitability == "loss_making"
                and rule.get("loss_making_requires_traction")
                and meta.get("has_traction")):
            return False

    if meta.get("green_bond_status") in rule.get("exclude_green_bond_status_in", []):
        return False
    return True


def counts(run, metadata, cfg=None):
    """`{N, M, K, labels, members}` for a scored run. `members` lists the company ids behind each
    number so any count on a slide can be opened up and defended."""
    cfg = cfg or engine_config.load()
    rules = cfg["pipeline_counts"]
    theta = engine_config.threshold(cfg, rules["K"]["min_disagreement"])
    buckets = {"N": [], "M": [], "K": []}

    peer_avg = _sector_peer_averages(run)

    for record in run.get("records", []):
        meta = (metadata or {}).get(record["company_id"], {})
        status = meta.get("green_bond_status", "unknown")

        in_n = status in rules["N"]["green_bond_status_in"]
        in_m = _is_bond_ready(record, meta, rules["M"], peer_avg)
        if in_n:
            buckets["N"].append(record["company_id"])
        if in_m:
            buckets["M"].append(record["company_id"])
        # K IS A DISAGREEMENT, SO IT NEEDS SOMETHING TO DISAGREE WITH.
        #
        # `disagreement` is `momentum_percentile - lseg_percentile`, and a company with no
        # incumbent rating has its percentile DEFAULTED to 0.5 by `engine._percentiles` — so its
        # "disagreement" is just its momentum rank minus a half, against a rating that does not
        # exist. On the index universe (185 names, none rated) that put 17 companies on a human
        # review list for disagreeing with nobody.
        #
        # `engine.label_for` already refuses to give these a quadrant for the same reason; this
        # is the same rule, one module over, so the screen and the money slide cannot disagree
        # about what a disagreement is.
        rated = record.get("baseline_origin") != "UNAVAILABLE"
        if not in_n and not in_m and rated and record["disagreement"] >= theta:
            buckets["K"].append(record["company_id"])

    return {
        "N": len(buckets["N"]), "M": len(buckets["M"]), "K": len(buckets["K"]),
        "labels": {k: rules[k]["label"] for k in ("N", "M", "K")},
        "rules": {k: rules[k]["rule"] for k in ("N", "M", "K")},
        "members": buckets,
        "universe_size": run.get("company_count", 0),
        "theta": theta,
    }


#: How a bucket reads on a company's own card. The counts strip beside the matrix has carried
#: N/M/K since B2, but a reader looking at ONE company had no way to tell which bucket it was in
#: — the single most commercially interesting label in the product was only ever a total.
BUCKET_BADGE = {
    "N": ("N · Issuer", "neutral"),
    "M": ("M · Bond-ready", "good"),
    "K": ("K · Review list", "warn"),
}


def bucket_of(counts_result):
    """`{company_id: 'N' | 'M' | 'K'}` for one `counts()` result.

    The three are disjoint by construction and not by convention: `M` excludes anything already
    reviewed or certified (that is what makes it a PIPELINE rather than a ranking), and `K` is
    explicitly the remainder that we disagree about but cannot place. So a company has at most
    one bucket, and a company in none of them is a legitimate answer, not a gap.
    """
    out = {}
    for key in ("N", "M", "K"):
        for company_id in (counts_result or {}).get("members", {}).get(key, []):
            out[company_id] = key
    return out


def bucket_badge(bucket, counts_result=None):
    """The display payload for one company's bucket. Empty bucket -> a stated 'not in it'."""
    rules = (counts_result or {}).get("rules") or {}
    if bucket not in BUCKET_BADGE:
        return {"bucket": "", "display": "Not in the pipeline", "tone": "neutral",
                "note": "Not a current issuer, not bond-ready on this run, and not far enough "
                        "from its rating to need a look. That is an answer, not a gap."}
    display, tone = BUCKET_BADGE[bucket]
    return {"bucket": bucket, "display": display, "tone": tone,
            "note": rules.get(bucket, "")}


def freeze(run, metadata, cfg=None, frozen_at="", demo=False, evidence_basis=""):
    """The record handed to Brina/Grace: the counts plus everything needed to re-derive them."""
    result = counts(run, metadata, cfg)
    cfg = cfg or engine_config.load()
    report = company_metadata.load_report(demo=demo)
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
        # WHICH evidence produced these counts. A frozen number that does not say what it was
        # computed over cannot be reconciled against the screen six weeks later.
        "evidence_basis": evidence_basis or "verified basket only",
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
    # Metadata follows the universe: the mock rows describe the fictional set, the verified CSV
    # describes the real 52, and crossing them joins nothing.
    metadata = company_metadata.load(demo=not real)
    source = universe.active_file(demo=not real)
    cons = universe.constituents(source)
    if real:
        # The board merges harvested evidence for the real basket, so this must too — otherwise
        # the money slide and the screen quietly report different M, which is the one thing this
        # module exists to prevent.
        import harvest
        cons = harvest.apply_overlay(cons)
    run = engine.run_engine(cons, metadata=metadata, use_cache=False)
    result = counts(run, metadata, cfg)

    scope = "real ASEAN base DB" if real else "demo universe (fictional)"
    print(f"N/M/K — {scope} · run {run['run_id']} · as_of {run['as_of']}")
    for key in ("N", "M", "K"):
        print(f"  {key} = {result[key]:3d}  {result['labels'][key]:<22s} {result['rules'][key]}")
    print(f"  universe {result['universe_size']} · theta {result['theta']}")

    if "--freeze" in argv:
        basis = "verified basket only"
        if real:
            import harvest
            overlay = harvest.load_overlay()
            events = sum(len(v) for v in overlay.values())
            if events:
                basis = ("verified basket + %d harvested events across %d companies"
                         % (events, len(overlay)))
        record = freeze(run, metadata, cfg, frozen_at=_today(), demo=not real,
                        evidence_basis=basis)
        with open(FROZEN_FILE, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, sort_keys=True)
        print(f"\nfroze -> {os.path.relpath(FROZEN_FILE, BASE_DIR)} "
              f"(run {record['run_id']}, {record['frozen_at']})")
        if record["caveat"]:
            print(f"  CAVEAT: {record['caveat']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
