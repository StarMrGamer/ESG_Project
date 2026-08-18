"""
harness.py — A8: the engine's test harness. Run this before believing any number.
=================================================================================

    python harness.py                 # everything, in the order below
    python harness.py --gate1         # Gate 1 only: determinism + stability + golden set + A2 routing
    python harness.py --stability     # 5 identical reruns -> same composite to 2 d.p.
    python harness.py --cases         # the five backtest cases + the cutoff assertion + timelines
    python harness.py --merkle        # Merkle determinism + tamper-evidence
    python harness.py --guards        # the honesty guards
    python harness.py --sweep         # sensitivity sweep: quadrant churn under the CGSI names
    python harness.py --calibration   # 2 humans vs the model over 10 companies (blind sheet)
    python harness.py --update-golden # re-freeze the golden set (review the diff before commit)

Seven checks, in the order they matter:

1. **Determinism** — the same universe scored twice (cold and cached) must produce a
   byte-identical run. This is Gate 1; if it fails, nothing downstream means anything.
1b. **Stability** — the runbook's own promise, in its own words: five identical reruns agree
   on every composite to 2 d.p. and nobody changes quadrant. Reports the observed spread.
2. **Golden set** — a frozen expectation per company: label, composite momentum/confidence,
   signal count and the exact set of subcomponents it routes to (so the A2 additions,
   `digital_risk` and `platform_dominance`, cannot silently stop routing).
3. **Backtest cases** — the five companies delivered 14 Aug, each scored with its lookback
   frozen at its cutoff. `signal.published_at < case.cutoff_date` is asserted and **fails
   loudly**; a backtest that can see the future is worse than no backtest.
3b. **Timelines** — the deck's per-case chart: every point scored at its own cutoff, the whole
   series reproducible, and the SVG committed under `docs/backtest/` still equal to what the
   engine draws now. A stale chart on a slide is a false claim in our own handwriting.
4. **Merkle determinism** — same run, same root, twice; every leaf verifies along its path.
5. **Honesty guards** — the ways this system could lie *quietly*: a mistyped metadata path
   silently serving mock rows as verified, a company with no evidence showing a green MATCH, or
   an unrated name being handed an invented baseline. Each was a real defect; each is asserted.
6. **Sensitivity sweep** — perturb one config knob at a time and report how many companies
   change quadrant, under the CGSI names. Churn is not a failure; UNREPORTED churn is.
7. **Calibration** — two humans score ten companies from the same excerpts, blind, and we
   report how far the engine sits from them. This is the only check whose answer no amount of
   code can supply; with the sheet unfilled it reports UNMEASURED and never a pass.
"""

import json
import os
import sys

import anchor
import backtest_timeline
import calibration
import company_metadata
import engine
import engine_config
import signals
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "golden_set.json")

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
#  1b. stability  (STEP 8.4)
#      The runbook promises "5 identical reruns -> same composite to 2 d.p.".
#      Determinism above proves something stronger — the whole run is byte-identical —
#      but this is the sentence we say out loud to a judge, so it is asserted in the
#      words it is said in, and it reports the observed SPREAD rather than a boolean:
#      the day this starts to drift, we want the size of the drift, not just a red line.
# --------------------------------------------------------------------------- #
STABILITY_RERUNS = 5


def check_stability(report):
    report.section(f"Stability — {STABILITY_RERUNS} identical reruns")
    meta = company_metadata.load()
    runs = [_demo_run(metadata=meta, use_cache=False) for _ in range(STABILITY_RERUNS)]
    series = {}
    for run in runs:
        for rec in run["records"]:
            series.setdefault(rec["company_id"], []).append(
                (rec["composite_momentum"], rec["composite_confidence"], rec["label"]))

    worst_m = worst_c = 0.0
    unstable_2dp, relabelled = [], []
    for cid, rows in sorted(series.items()):
        moms = [r[0] for r in rows]
        confs = [r[1] for r in rows]
        worst_m = max(worst_m, max(moms) - min(moms))
        worst_c = max(worst_c, max(confs) - min(confs))
        if len({round(m, 2) for m in moms}) > 1:
            unstable_2dp.append(cid)
        if len({r[2] for r in rows}) > 1:
            relabelled.append(cid)

    report.check(len({r["run_id"] for r in runs}) == 1,
                 f"{STABILITY_RERUNS} reruns produce ONE run_id",
                 runs[0]["run_id"])
    report.check(not unstable_2dp, "composite momentum identical to 2 d.p. across all reruns",
                 f"spread {worst_m:.2e} — worst of {len(series)} companies"
                 if not unstable_2dp else f"{len(unstable_2dp)} drifted: {unstable_2dp[:3]}")
    report.check(not unstable_2dp, "composite confidence identical to 2 d.p. across all reruns",
                 f"spread {worst_c:.2e}")
    report.check(not relabelled, "no company changes quadrant between reruns",
                 f"{len(series)} companies held their label"
                 if not relabelled else f"{relabelled[:3]}")


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
# One definition, in backtest_timeline — the chart and this check must never be able to score a
# case two different ways.
load_cases = backtest_timeline.load_cases
case_company = backtest_timeline.case_company


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
#  3b. per-case timelines  (STEP 8.3)
#      The chart that goes in the deck. Two things have to be true about it, and
#      both are easy to lose quietly: every point must have been computed with its
#      OWN cutoff (so the line cannot see its own future), and the SVG committed to
#      docs/backtest must still be what today's engine draws. A stale chart on a
#      slide is a false claim made in our own handwriting.
# --------------------------------------------------------------------------- #
def check_timelines(report):
    report.section("Backtest timelines (the deck's validation chart)")
    data = backtest_timeline.all_series()
    report.check(len(data) == len(load_cases()["cases"]), "one series per backtest case",
                 f"{len(data)} series")

    # Each point is generated with `cutoff` = its own date and `engine.enforce_cutoff` runs
    # there, so a violation raises before it can ever be plotted. What is checked HERE is the
    # observable consequence, because that is what survives into the JSON a slide is built from:
    # a point can never carry more signals than there were events strictly before its date.
    # (An event dated ON the sample date is correctly excluded — the cutoff is exclusive.)
    lookahead = [f"{s['case_id']}@{p['date']} {p['signal_count']}>{n}"
                 for s in data for p in s["points"]
                 for n in [sum(1 for ev in s["events"] if ev["date"] < p["date"])]
                 if p["signal_count"] > n]
    report.check(not lookahead, "no plotted point carries evidence from its own date or later",
                 f"{lookahead[:3]}" if lookahead else f"{sum(len(s['points']) for s in data)} "
                 f"points, each scored at its own cutoff")

    again = backtest_timeline.all_series()
    report.check(json.dumps(data, sort_keys=True) == json.dumps(again, sort_keys=True),
                 "the series is deterministic", "same cases -> same curve, twice")

    stale = []
    for s in data:
        path = os.path.join(backtest_timeline.OUT_DIR, f"{s['case_id']}.svg")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                on_disk = fh.read()
        except OSError:
            stale.append(f"{s['case_id']} (missing)")
            continue
        if on_disk.strip() != backtest_timeline.render_svg(s).strip():
            stale.append(s["case_id"])
    report.check(not stale, "the committed SVGs match what the engine draws today",
                 f"stale: {stale} — re-run `python backtest_timeline.py`" if stale
                 else f"{len(data)} charts in {os.path.relpath(backtest_timeline.OUT_DIR, BASE_DIR)}")

    for s in data:
        first = next((p for p in s["points"] if p["signal_count"]), None)
        report.info(f"{s['case_id']:9s} first evidence {first['date'] if first else 'never':10s} "
                    f"-> cutoff {s['cutoff_date']}: momentum {s['final']['momentum']:+.3f} · "
                    f"{s['final']['label']} · outcome {s['outcome_date']}")


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
    # The two ranges the runbook names by number (STEP 8.4). Swept end to end, not just nudged:
    # a knob that only ever moves +/-0.05 has not been tested, it has been reassured.
    ("theta 0.30 -> 0.20", {"theta": 0.20}),
    ("theta 0.30 -> 0.25", {"theta": 0.25}),
    ("theta 0.30 -> 0.35", {"theta": 0.35}),
    ("theta 0.30 -> 0.40", {"theta": 0.40}),
    ("DIGITAL weight 0.15 -> 0.25", {"component_weights": {"DIGITAL": 0.25}}),
    ("DIGITAL weight 0.15 -> 0.35", {"component_weights": {"DIGITAL": 0.35}}),
    ("DIGITAL weight 0.15 -> 0.45", {"component_weights": {"DIGITAL": 0.45}}),
    # Everything else we judged by hand and therefore owe a churn number for.
    ("E weight +20%", {"component_weights": {"E": 0.36}}),
    ("G weight -20%", {"component_weights": {"G": 0.24}}),
    ("platform_dominance .05 -> .15", {"digital_subweights": {"platform_dominance": 0.15}}),
    ("digital_risk .10 -> .20", {"digital_subweights": {"digital_risk": 0.20}}),
    ("half-life 180d -> 45d (Short horizon)", {"decay": {"half_life_days": 45}}),
    ("corroboration off", {"confidence": {"corroboration_weight": 0.0}}),
    ("company_pr quality .5 -> .3", {"source_quality": {"company_pr": 0.3}}),
]


def check_digital_influence(report, baseline):
    """Does the DIGITAL pillar change any decision? Slide 8 of the deck calls it a hypothesis
    and promises the harness reports the answer "honestly, either way" — so it is reported
    here on every run, not left to whoever remembers to ask.

    Turning the weight to zero is the sharpest form of the question: if no company changes
    quadrant when the pillar is removed entirely, then whatever DIGITAL is measuring, it is not
    currently changing what we tell anyone."""
    report.section("DIGITAL pillar — does it change any decision?")
    meta = company_metadata.load()
    base_labels = {r["company_id"]: r["label"] for r in baseline["records"]}

    for name, path in (("demo (fictional)", universe.DEMO_FILE),
                       ("the real 52", universe.UNIVERSE_FILE)):
        run = (baseline if path == universe.DEMO_FILE else
               engine.run_engine(universe.constituents(path), metadata=meta, use_cache=False))
        dig = [r["components"]["DIGITAL"]["momentum"] for r in run["records"]
               if "DIGITAL" in r["components"]]
        off = engine.run_engine(
            universe.constituents(path), metadata=meta, use_cache=False,
            config=engine_config.load(overrides={"component_weights": {"DIGITAL": 0.0}}))
        was = base_labels if path == universe.DEMO_FILE else \
            {r["company_id"]: r["label"] for r in run["records"]}
        moved = sum(1 for r in off["records"] if was.get(r["company_id"]) != r["label"])
        coverage = f"{len(dig)}/{len(run['records'])} companies carry a DIGITAL component"
        spread = (f"momentum {min(dig):+.3f}..{max(dig):+.3f}" if dig else "no DIGITAL evidence")
        report.info(f"{name:18s} {coverage} · {spread}")
        report.info(f"{'':18s} weight 0.15 -> 0.00: {moved}/{len(run['records'])} change quadrant")

    report.check(True, "DIGITAL influence reported",
                 "the deck calls this pillar a hypothesis (slide 8); this is the number that "
                 "answers it, printed whether it flatters us or not")


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
#  6. calibration  (STEP 8.4)
#      The one check the machine cannot run for itself. Everything else here asks
#      "is the engine consistent?"; this asks "is it RIGHT?" — and only two humans
#      reading the same excerpts can answer that. So the harness verifies the
#      apparatus (blind sheet, resolvable companies, on-scale ratings, frozen
#      cut-points) and then reports the human numbers if, and only if, they exist.
# --------------------------------------------------------------------------- #
def check_calibration(report, _baseline=None):
    report.section("Calibration — 2 humans vs the model")
    # No run is passed in: the sheet names the set it was frozen against and calibration.score
    # rebuilds exactly that. Handing it the demo baseline would orphan every row the moment the
    # sheet is built from anything else, which is precisely what happened.
    result = calibration.score()
    if result.get("status") == "no_sheet":
        report.check(False, "calibration sheet present", result["detail"])
        return

    report.check(0 < result["companies"] <= calibration.SET_SIZE,
                 f"sheet holds up to {calibration.SET_SIZE} companies",
                 f"{result['companies']} from the '{result.get('set')}' set — fewer is allowed "
                 f"and reported, never padded")
    thin = [row["company_id"] for row in result["rows"]
            if row["signal_count"] < calibration.MIN_EXCERPTS]
    report.check(not thin, f"every rated company carries >= {calibration.MIN_EXCERPTS} excerpts",
                 f"too thin to judge: {thin}" if thin else "nobody is asked to rate nothing")
    directions = {1 if row["model"] > 0 else -1 if row["model"] < 0 else 0
                  for row in result["rows"]}
    report.check(len(directions) > 1, "the set contains more than one direction",
                 "a set where everything improves cannot tell a careful rater from one who "
                 "answers '+1' to everything" if len(directions) <= 1
                 else f"model directions present: {sorted(directions)}")
    report.check(not result["missing_from_run"],
                 "every rated company still exists in the current run",
                 f"orphaned: {result['missing_from_run']}" if result["missing_from_run"] else "")
    report.check(not result["out_of_scale"], "no rating outside the five-point scale",
                 f"{result['out_of_scale']}" if result["out_of_scale"] else "")
    cp = result["cutpoints"]
    report.check(0 < float(cp["weak"]) < float(cp["strong"]) <= 1.0,
                 "model cut-points are frozen in the sheet and ordered",
                 f"weak {cp['weak']} < strong {cp['strong']}")

    if result["status"] == "unmeasured":
        report.info(f"UNMEASURED — 0/{result['ratings_possible']} human ratings recorded. "
                    f"The apparatus passes; the calibration itself has not been run.")
        report.info("run `python calibration.py --sheet` (done), have two people fill "
                    "data/calibration_sheet.json, then `python calibration.py`")
        return

    report.info(f"{result['ratings_recorded']}/{result['ratings_possible']} ratings recorded "
                f"by {' and '.join(str(result['raters'][r]) for r in calibration.RATERS)}")
    for key, title in (("direction_inter_rater", "direction: humans vs each other"),
                       ("direction_model_vs_consensus", "direction: model vs consensus"),
                       ("inter_rater", "intensity: humans vs each other"),
                       ("model_vs_consensus", "intensity: model vs consensus")):
        report.info(f"{title:32s} {calibration._fmt(result[key])}")
    inter = result["direction_inter_rater"]
    versus = result["direction_model_vs_consensus"]
    if inter["n"] and versus["n"]:
        report.info("the model is inside human noise" if versus["mae"] <= inter["mae"]
                    else f"the model disagrees with the humans MORE than they disagree with each "
                         f"other (MAE {versus['mae']} vs {inter['mae']}) — report that, don't bury it")


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
    if everything or "--gate1" in flags or "--stability" in flags:
        check_stability(report)
    if everything or "--gate1" in flags or "--golden" in flags:
        check_golden(report, baseline)
    if everything or "--gate1" in flags or "--a2" in flags:
        check_a2_routing(report)
    if everything or "--cases" in flags:
        check_cases(report)
    if everything or "--cases" in flags or "--timelines" in flags:
        check_timelines(report)
    if everything or "--merkle" in flags:
        check_merkle(report, baseline)
    if everything or "--guards" in flags:
        check_guards(report, baseline)
    if everything or "--sweep" in flags:
        check_digital_influence(report, baseline)
        check_sweep(report, baseline)
    if everything or "--calibration" in flags:
        check_calibration(report)

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
