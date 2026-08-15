"""
harness.py — A8: the engine's test harness. Run this before believing any number.
=================================================================================

    python harness.py                 # everything, in the order below
    python harness.py --gate1         # Gate 1 only: determinism + cache + golden set + A2 routing
    python harness.py --cases         # the five backtest cases + the cutoff assertion
    python harness.py --merkle        # Merkle determinism + tamper-evidence
    python harness.py --guards        # the honesty guards
    python harness.py --sweep         # sensitivity sweep: quadrant churn under the CGSI names
    python harness.py --update-golden # re-freeze the golden set (review the diff before commit)

Six checks, in the order they matter:

1. **Determinism** — the same universe scored twice (cold and cached) must produce a
   byte-identical run. This is Gate 1; if it fails, nothing downstream means anything.
2. **Golden set** — a frozen expectation per company: label, composite momentum/confidence,
   signal count and the exact set of subcomponents it routes to (so the A2 additions,
   `digital_risk` and `platform_dominance`, cannot silently stop routing).
3. **Backtest cases** — the five companies delivered 14 Aug, each scored with its lookback
   frozen at its cutoff. `signal.published_at < case.cutoff_date` is asserted and **fails
   loudly**; a backtest that can see the future is worse than no backtest.
4. **Merkle determinism** — same run, same root, twice; every leaf verifies along its path.
5. **Honesty guards** — the ways this system could lie *quietly*: a mistyped metadata path
   silently serving mock rows as verified, a company with no evidence showing a green MATCH, or
   an unrated name being handed an invented baseline. Each was a real defect; each is asserted.
6. **Sensitivity sweep** — perturb one config knob at a time and report how many companies
   change quadrant, under the CGSI names. Churn is not a failure; UNREPORTED churn is.
"""

import json
import os
import sys

import anchor
import company_metadata
import engine
import engine_config
import signals
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "golden_set.json")
CASES_FILE = os.path.join(BASE_DIR, "data", "backtest_cases.json")

PASS, FAIL, INFO = "  PASS", "  FAIL", "  ····"


class Report:
    """Collects pass/fail lines so one run prints one verdict and exits with one code."""

    def __init__(self):
        self.failures = []
        self.checks = 0

    def check(self, ok, label, detail=""):
        self.checks += 1
        print(f"{PASS if ok else FAIL}  {label}" + (f"  — {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)
        return ok

    def info(self, line):
        print(f"{INFO}  {line}")

    def section(self, title):
        print(f"\n=== {title} " + "=" * max(0, 62 - len(title)))


def _demo_run(*, metadata=None, use_cache=False, config=None):
    return engine.run_engine(universe.constituents(universe.DEMO_FILE),
                             metadata=metadata, use_cache=use_cache, config=config)


# --------------------------------------------------------------------------- #
#  1. determinism  (Gate 1)
# --------------------------------------------------------------------------- #
def check_determinism(report):
    report.section("Gate 1 — determinism")
    meta = company_metadata.load()
    cold = _demo_run(metadata=meta, use_cache=False)
    again = _demo_run(metadata=meta, use_cache=False)
    cached = _demo_run(metadata=meta, use_cache=True)
    warm = _demo_run(metadata=meta, use_cache=True)

    d1, d2 = engine.digest(cold), engine.digest(again)
    report.check(d1 == d2, "same inputs -> byte-identical run", f"digest {d1[:16]}")
    report.check(engine.digest(cached) == d1, "cache round-trip is lossless",
                 f"run_id {cold['run_id']}")
    report.check(engine.digest(warm) == d1, "warm cache hit matches cold compute")
    report.check(cold["run_id"] == again["run_id"], "run_id is a pure function of the inputs")

    bumped = _demo_run(metadata=meta, use_cache=False,
                       config=engine_config.load(overrides={"theta": 0.31}))
    report.check(bumped["run_id"] != cold["run_id"],
                 "a changed config produces a DIFFERENT run_id", "no silent re-labelling")

    # The Phase B1 swap is a FILE, not a code change. If the id ignored the metadata, the
    # verified run would collide with the provisional one, a warm cache would serve the old
    # tiers under the same id, and anchor.py would hold one root for two evidence sets.
    swapped = dict(meta)
    victim = sorted(swapped)[0]
    swapped[victim] = dict(swapped[victim], traction_flag="Y", green_bond_status="cbi_certified")
    moved = _demo_run(metadata=swapped, use_cache=False)
    report.check(moved["run_id"] != cold["run_id"],
                 "a changed metadata file produces a DIFFERENT run_id",
                 f"{victim} edited -> {moved['run_id']} (was {cold['run_id']})")
    report.check(_demo_run(metadata=None, use_cache=False)["run_id"] != cold["run_id"],
                 "…and 'no metadata' is distinct from 'metadata supplied'",
                 "an unstamped run can never collide with a tiered one")
    report.info(f"{cold['company_count']} companies · {cold['signal_count']} signals · "
                f"as_of {cold['as_of']} · config {cold['config_hash']}")
    return cold


# --------------------------------------------------------------------------- #
#  2. golden set
# --------------------------------------------------------------------------- #
def _golden_from(run):
    return {
        "_note": "Frozen expectations for the demo universe. Regenerate with "
                 "`python harness.py --update-golden` and REVIEW THE DIFF — a change here is a "
                 "change in what the engine believes.",
        "engine_version": run["engine_version"],
        "config_version": run["config_version"],
        "config_hash": run["config_hash"],
        "run_id": run["run_id"],
        "digest": engine.digest(run),
        "as_of": run["as_of"],
        "label_counts": engine.label_counts(run),
        "companies": {
            r["company_id"]: {
                "label": r["label"],
                "composite_momentum": r["composite_momentum"],
                "composite_confidence": r["composite_confidence"],
                "signal_count": r["signal_count"],
                "components": {k: v["momentum"] for k, v in sorted(r["components"].items())},
                "subcomponents": sorted(f"{c}/{s}" for c, subs in r["subcomponents"].items()
                                        for s in subs),
            } for r in run["records"]
        },
    }


def update_golden(run):
    golden = _golden_from(run)
    with open(GOLDEN_FILE, "w", encoding="utf-8") as fh:
        json.dump(golden, fh, indent=1, sort_keys=True)
    print(f"  wrote {os.path.relpath(GOLDEN_FILE, BASE_DIR)} — "
          f"{len(golden['companies'])} companies, run_id {golden['run_id']}")
    return golden


def check_golden(report, run):
    report.section("Golden set")
    try:
        with open(GOLDEN_FILE, "r", encoding="utf-8") as fh:
            golden = json.load(fh)
    except (OSError, ValueError):
        report.check(False, "golden set present",
                     "missing — run `python harness.py --update-golden` once to seed it")
        return

    report.check(golden.get("config_hash") == run["config_hash"], "config unchanged since freeze",
                 f"{golden.get('config_hash')} vs {run['config_hash']}")
    report.check(golden.get("digest") == engine.digest(run), "run digest matches the frozen one")

    current = _golden_from(run)["companies"]
    expected = golden.get("companies", {})
    missing = sorted(set(expected) - set(current))
    added = sorted(set(current) - set(expected))
    report.check(not missing and not added, "same companies as the freeze",
                 f"missing {missing[:3]} added {added[:3]}" if (missing or added) else "")

    drifted = []
    for cid in sorted(set(expected) & set(current)):
        for field in ("label", "composite_momentum", "composite_confidence", "signal_count",
                      "components", "subcomponents"):
            if expected[cid].get(field) != current[cid].get(field):
                drifted.append(f"{cid}.{field}")
    report.check(not drifted, "no per-company drift",
                 f"{len(drifted)} field(s): {drifted[:4]}" if drifted else "")

    routed = sorted({s for row in current.values() for s in row["subcomponents"]})
    report.info(f"subcomponents exercised by the demo universe: {len(routed)} — "
                + ", ".join(routed))


# --------------------------------------------------------------------------- #
#  2b. A2 routing — asserted directly, not left to whatever the fixture happens
#      to contain. The demo universe carries no breach or platform language, so
#      a fixture-based check would pass vacuously the day the routing broke.
# --------------------------------------------------------------------------- #
def check_a2_routing(report):
    report.section("A2 — DIGITAL subcomponents")
    cfg = engine_config.load()

    breach = signals.make_signal(
        company_id="TEST:1", source_url="https://example.com/pdpa-breach", config=cfg,
        text="Regulator fined the group after a data breach exposed customer records in Mar 2023")
    report.check(bool(breach), "cyber/breach text produces a signal")
    if breach:
        routes = {(r["component"], r["subcomponent"]) for r in breach["routes"]}
        report.check(("DIGITAL", "digital_risk") in routes, "breach routes to DIGITAL/digital_risk")
        report.check(("G", "controversy") in routes,
                     "…alongside its existing G routing", "one record, two routes — no duplicate")
        report.check(breach["direction"] == -1, "digital_risk carries direction -1")

    platform = signals.make_signal(
        company_id="TEST:2", source_url="https://example.com/ar", config=cfg,
        text="The marketplace platform ecosystem now intermediates most group transactions")
    report.check(bool(platform) and platform["subcomponent"] == "platform_dominance",
                 "platform/marketplace/ecosystem language routes to platform_dominance",
                 f"weighted {cfg['digital_subweights']['platform_dominance']} — low, like disclosure")

    weights = {k: v for k, v in cfg["digital_subweights"].items() if not k.startswith("_")}
    report.check(abs(sum(weights.values()) - 1.0) < 1e-9, "digital sub-weights sum to 1.00",
                 " · ".join(f"{k} {v}" for k, v in weights.items()))

    # the two new subcomponents must survive aggregation, not just extraction
    run = engine.run_engine([{"company": "Routing probe", "ticker": "TEST:3", "as_of": "2023-06-30",
                              "events": [{"published_at": "2023-03-01", "source_type": "regulator",
                                          "text": "Data breach exposed customer records"},
                                         {"published_at": "2023-04-01", "source_type": "news",
                                          "text": "Its marketplace platform ecosystem expanded"}]}],
                            use_cache=False)
    subs = run["records"][0]["subcomponents"].get("DIGITAL", {})
    report.check("digital_risk" in subs and "platform_dominance" in subs,
                 "both A2 subcomponents reach the score record",
                 f"DIGITAL momentum {run['records'][0]['components']['DIGITAL']['momentum']:+.3f}")


# --------------------------------------------------------------------------- #
#  3. backtest cases  (+ the cutoff assertion)
# --------------------------------------------------------------------------- #
def load_cases():
    with open(CASES_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def case_company(case):
    """A backtest case as a company record the engine can score (its events are its evidence)."""
    return {"company": case["company"], "ticker": case["ticker"], "sector": case["sector"],
            "country": case.get("country", "unknown"), "as_of": case["cutoff_date"],
            "events": case["events"]}


def check_cases(report):
    report.section("Backtest cases (five, cutoff-frozen)")
    data = load_cases()
    report.info(f"source: {data['provenance']}")
    for case in data["cases"]:
        cutoff = case["cutoff_date"]
        label = f"{case['company']} ({case['ticker']}) @ {cutoff}"

        stale = [e["published_at"] for e in case["events"] if e["published_at"] >= cutoff]
        report.check(not stale, f"{case['case_id']}: case file has no post-cutoff event",
                     f"{stale}" if stale else "")

        run = engine.run_engine([case_company(case)], cutoff=cutoff, use_cache=False)
        try:
            engine.enforce_cutoff(run)
            cutoff_ok, detail = True, "no lookahead"
        except engine.CutoffViolation as exc:
            cutoff_ok, detail = False, str(exc).splitlines()[0]
        report.check(cutoff_ok, f"{case['case_id']}: cutoff assertion", detail)

        record = run["records"][0]
        expect = case["expect"]
        sign = 1 if record["composite_momentum"] > 0 else -1 if record["composite_momentum"] < 0 else 0
        report.check(sign == expect["momentum_sign"],
                     f"{case['case_id']}: momentum sign {sign:+d}",
                     f"momentum {record['composite_momentum']:+.3f}")
        report.check(record["signal_count"] >= expect["min_signals"],
                     f"{case['case_id']}: {record['signal_count']} signals in window",
                     f"expected >= {expect['min_signals']}")
        report.check(record["composite_confidence"] <= expect["max_confidence"],
                     f"{case['case_id']}: confidence {record['composite_confidence']:.3f} within band",
                     f"expected <= {expect['max_confidence']}")
        report.check(record["label"] == expect["label"],
                     f"{case['case_id']}: quadrant = {record['label_display']}",
                     f"expected {expect['label']}")
        if expect.get("is_known_failure"):
            report.info(f"{case['case_id']}: KNOWN FAILURE CASE — published, not hidden. "
                        f"{expect['note'][:96]}…")
        report.info(f"{label}: {record['label_display']} · momentum "
                    f"{record['composite_momentum']:+.3f} · confidence "
                    f"{record['composite_confidence']:.3f} · {record['signal_count']} signals")


# --------------------------------------------------------------------------- #
#  4. merkle determinism
# --------------------------------------------------------------------------- #
def check_merkle(report, run):
    report.section("Merkle / anchoring determinism")
    meta = company_metadata.load()
    first = anchor.build_anchor_record(run, meta)
    second = anchor.build_anchor_record(run, meta)
    report.check(first["root"] == second["root"], "same run -> same root, twice",
                 f"{first['root'][:24]}… over {first['leaf_count']} leaves")

    hashes = [leaf["hash"] for leaf in first["leaves"]]
    probes = sorted({0, 1, len(hashes) // 3, len(hashes) // 2, len(hashes) - 1})
    ok = all(anchor.verify_path(hashes[i], anchor.merkle_path(hashes, i), first["root"])
             for i in probes if 0 <= i < len(hashes))
    report.check(ok, "every probed leaf verifies along its path", f"probes {probes}")

    shuffled = list(reversed(first["leaves"]))
    report.check(anchor.merkle_root([leaf["hash"] for leaf in sorted(
        shuffled, key=lambda leaf: (leaf["leaf_id"], leaf["hash"]))]) == first["root"],
        "leaf order does not change the root", "sorted by leaf_id before pairing")

    tampered = list(hashes)
    tampered[0] = anchor._leaf_hash(first["leaves"][0]["preimage"] + " ")
    report.check(anchor.merkle_root(tampered) != first["root"],
                 "one changed character changes the root", "tamper-evidence holds")

    gb = [leaf for leaf in first["leaves"] if leaf["kind"] == "green_bond"]
    report.check(bool(gb), "green-bond rows are leaves too (B5)", f"{len(gb)} metadata leaves")


# --------------------------------------------------------------------------- #
#  4b. honesty guards — the two ways this system could lie quietly. Both were
#      real defects once; they stay fixed because they are asserted here.
# --------------------------------------------------------------------------- #
def check_guards(report, run):
    report.section("Honesty guards")

    missing = company_metadata.load("/nonexistent/metadata.csv")
    report.check(missing == {}, "an explicit missing CSV loads NOTHING",
                 "no silent fallback to the mock — a Phase B1 typo must not serve mock rows "
                 "as verified")
    report.check(len(company_metadata.load()) > 0, "…while the default lookup still resolves")

    # A config change gives the run a new id, so its anchor record may not exist yet; build it
    # locally (never pushed from the harness) exactly as the server does before verifying.
    anchor.anchor_run(run, company_metadata.load(), push=False)

    verdict = anchor.verify_company(run["run_id"], "NOT:AREALTICKER", check_chain=False)
    report.check(verdict["status"] == "no_evidence" and not verdict["ok"],
                 "verifying a company we hold no evidence for is NOT a MATCH",
                 f"status {verdict['status']}")

    known = run["records"][0]["company_id"]
    report.check(anchor.verify_company(run["run_id"], known, check_chain=False)["ok"],
                 f"…while real evidence still verifies ({known})")

    # Shrinkage: one unanimous signal must NOT read like twelve unanimous signals. Both probes
    # below are 100% positive, so `direction_consensus` is +1.0 for each — only the amount of
    # evidence separates them, which is exactly what composite_momentum has to reflect.
    def _probe(n):
        events = [{"published_at": f"2023-{m % 12 + 1:02d}-10", "source_type": "regulator",
                   "text": f"Issued an inaugural green bond tranche {m}"} for m in range(n)]
        return engine.run_engine([{"company": f"Probe {n}", "ticker": f"TEST:{n}",
                                   "as_of": "2023-12-31", "events": events}],
                                 as_of="2023-12-31", use_cache=False)["records"][0]

    thin, thick = _probe(1), _probe(12)
    report.check(abs(thin["direction_consensus"] - thick["direction_consensus"]) < 1e-9,
                 "unanimous evidence gives the same DIRECTION either way",
                 f"consensus {thin['direction_consensus']:+.3f} both")
    report.check(thin["composite_momentum"] < thick["composite_momentum"] / 2,
                 "…but one signal scores far below twelve",
                 f"{thin['composite_momentum']:+.3f} vs {thick['composite_momentum']:+.3f} "
                 f"(weights {thin['evidence_weight']:.2f} vs {thick['evidence_weight']:.2f})")
    report.check(abs(thin["composite_momentum"]) < 1.0 and abs(thick["composite_momentum"]) < 1.0,
                 "no company can reach a perfect +/-1.000 momentum",
                 "an extreme score has to be earned by substantial evidence")

    unrated = engine.run_engine([{"company": "No evidence at all", "ticker": "TEST:0"}],
                                use_cache=False)["records"][0]
    report.check(unrated["composite_confidence"] == 0.0 and unrated["signal_count"] == 0,
                 "a company with no signals scores zero CONFIDENCE, not zero momentum",
                 "absence of evidence is reported as absence, never as a negative verdict")
    report.check(unrated["baseline_basis"] == "unavailable",
                 "…and an unrated company gets no invented baseline",
                 f"percentile falls back to the median ({unrated['lseg_percentile']})")


# --------------------------------------------------------------------------- #
#  5. sensitivity sweep
# --------------------------------------------------------------------------- #
SWEEPS = [
    ("theta -0.05", {"theta": 0.25}),
    ("theta +0.05", {"theta": 0.35}),
    ("E weight +20%", {"component_weights": {"E": 0.36}}),
    ("G weight -20%", {"component_weights": {"G": 0.24}}),
    ("platform_dominance .05 -> .15", {"digital_subweights": {"platform_dominance": 0.15}}),
    ("digital_risk .10 -> .20", {"digital_subweights": {"digital_risk": 0.20}}),
    ("half-life 180d -> 45d (Short horizon)", {"decay": {"half_life_days": 45}}),
    ("corroboration off", {"confidence": {"corroboration_weight": 0.0}}),
    ("company_pr quality .5 -> .3", {"source_quality": {"company_pr": 0.3}}),
]


def check_sweep(report, baseline):
    report.section("Sensitivity sweep — quadrant churn (CGSI names)")
    base_labels = {r["company_id"]: r["label"] for r in baseline["records"]}
    display = baseline["labels"]
    report.info("baseline: " + " · ".join(
        f"{display.get(k, k)} {v}" for k, v in sorted(engine.label_counts(baseline).items())))
    meta = company_metadata.load()
    for name, patch in SWEEPS:
        cfg = engine_config.load(overrides=patch)
        run = _demo_run(metadata=meta, use_cache=False, config=cfg)
        moved = [(cid, base_labels[cid], r["label"])
                 for r in run["records"] for cid in [r["company_id"]]
                 if base_labels.get(cid) != r["label"]]
        pct = 100.0 * len(moved) / max(1, len(base_labels))
        counts = " · ".join(f"{display.get(k, k)} {v}"
                            for k, v in sorted(engine.label_counts(run).items()))
        report.info(f"{name:38s} churn {len(moved):2d}/{len(base_labels)} ({pct:4.1f}%)  {counts}")
        for cid, was, now in moved[:3]:
            report.info(f"{'':40s} {cid}: {display.get(was, was)} -> {display.get(now, now)}")
    report.check(True, "sweep completed and reported", f"{len(SWEEPS)} perturbations")


# --------------------------------------------------------------------------- #
def main(argv):
    flags = set(argv[1:])
    everything = not (flags - {"--quiet"})
    report = Report()

    if "--update-golden" in flags:
        print("=== Re-freezing the golden set " + "=" * 34)
        update_golden(_demo_run(metadata=company_metadata.load(), use_cache=False))
        return 0

    baseline = check_determinism(report) if (everything or "--gate1" in flags) else \
        _demo_run(metadata=company_metadata.load(), use_cache=False)
    if everything or "--gate1" in flags or "--golden" in flags:
        check_golden(report, baseline)
    if everything or "--gate1" in flags or "--a2" in flags:
        check_a2_routing(report)
    if everything or "--cases" in flags:
        check_cases(report)
    if everything or "--merkle" in flags:
        check_merkle(report, baseline)
    if everything or "--guards" in flags:
        check_guards(report, baseline)
    if everything or "--sweep" in flags:
        check_sweep(report, baseline)

    print("\n" + "=" * 70)
    if report.failures:
        print(f"FAILED — {len(report.failures)} of {report.checks} checks:")
        for name in report.failures:
            print(f"  · {name}")
        return 1
    print(f"ALL {report.checks} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
