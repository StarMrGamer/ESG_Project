"""
phase_b.py — Playbook Phase B, steps 8 and 7: the two validation runs Rai owns.
===============================================================================

    python phase_b.py --template            # write the two input-file shapes, so the team
                                            #   knows exactly what to send us
    python phase_b.py --blind PICKS.json    # step 8: rank all 52 BLIND, then compare
    python phase_b.py --issuance FILE.json  # step 7: high momentum at t -> issuance at t+1
    python phase_b.py --blind PICKS.json --json      # machine-readable, for the slide

Both runs are blocked on data that has not arrived — CGSI's 17 picks, and dated green-bond
issuance/review events. The CODE is not blocked, so it is written now and sits ready: on the
day the file lands this is one command, not half a day of building under time pressure. That is
the whole premise of the Data-Arrival Playbook.

**Neither run will invent its input.** Point them at a file that is missing, malformed, or
holds companies we have no evidence for, and they say so and stop. A validation script that
degrades quietly into a plausible-looking result is worse than no validation script: it is the
one place in this project where a fabricated number would be believed without question.

**The blind run is blind by construction, not by promise.** The engine scores the universe and
the ranking is frozen BEFORE the picks file is opened — the comparison happens afterwards, on
an already-final `run_id` you can recompute yourself. The engine has no code path that can see
the picks, and this file is short enough to check that claim by reading it.
"""

import json
import os
import sys

import company_metadata
import engine
import engine_config
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "data", "phase_b")

# How we rank when asked "which names would you put forward?". Disclosed, and deliberately the
# same quantity the product argues about on screen: which way a company is heading, with
# confidence breaking ties so a loud single signal cannot outrank a well-evidenced one.
RANK_BY = ("composite_momentum", "composite_confidence", "signal_count")


class InputMissing(RuntimeError):
    """Raised rather than substituted. See the module docstring."""


# --------------------------------------------------------------------------- #
#  shared
# --------------------------------------------------------------------------- #
def _load_json(path, what):
    if not path:
        raise InputMissing(f"no {what} file given")
    if not os.path.exists(path):
        raise InputMissing(
            f"{what} file not found: {path}\n"
            f"    This run needs real data from CGSI. Nothing is substituted — run "
            f"`python phase_b.py --template` to see the exact shape to ask for.")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise InputMissing(f"{what} file is not valid JSON: {path}\n    {exc}") from exc


def _score_universe(demo=False):
    path = universe.DEMO_FILE if demo else universe.UNIVERSE_FILE
    cons = universe.constituents(path)
    if not demo:
        # Same evidence the board scores, or the blind test ranks a different universe than the
        # one the screen shows.
        import harvest
        cons = harvest.apply_overlay(cons)
    run = engine.run_engine(cons, metadata=company_metadata.load(demo=demo), use_cache=False)
    return run, os.path.relpath(path, BASE_DIR)


def _ranked(run):
    return sorted(run["records"], key=lambda r: tuple(-r[k] for k in RANK_BY) + (r["company_id"],))


def _why(record, top_n=3):
    """The evidenced reason for a disagreement — record fields plus the signals behind them."""
    sigs = sorted(record.get("signals") or [],
                  key=lambda s: (-float(s["materiality"]) * float(s["confidence"]),
                                 s["signal_id"]))[:top_n]
    return {
        "label": record["label_display"],
        "composite_momentum": record["composite_momentum"],
        "composite_confidence": record["composite_confidence"],
        "signal_count": record["signal_count"],
        "disagreement": record["disagreement"],
        "baseline_basis": record["baseline_basis"],
        "top_signals": [{"published_at": s.get("published_at", ""),
                         "source_type": s.get("source_type", ""),
                         "direction": s["direction"],
                         "excerpt": (s.get("raw_text") or "")[:160],
                         "rationale": s.get("rationale", ""),
                         "source_url": s.get("source_url", "")} for s in sigs],
    }


# --------------------------------------------------------------------------- #
#  step 8 — the blind run against CGSI's picks
# --------------------------------------------------------------------------- #
def _wrap(text, width):
    """Tiny greedy wrapper — `textwrap` for one paragraph, without the import."""
    words, line, out = (text or "").split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def _their_filters():
    """CGSI's own three filters for the high-conviction list, and what they mean for our number.

    Read from `data/cgsi_note_figures.json`, transcribed from their published note. Only the
    first filter is an ESG signal; the second is sell-side coverage and the third is a buy
    recommendation, which HARD RULE 4 forbids this system from ever forming. So the overlap
    measures agreement on one criterion out of three, and a low number is not a disagreement
    about ESG — it is two filters we cannot see."""
    path = os.path.join(BASE_DIR, "data", "cgsi_note_figures.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            block = json.load(fh).get("high_conviction_17", {})
    except (OSError, ValueError):
        return {}
    return {"filters": block.get("filters", []),
            "how_to_read": block.get("how_to_read_our_agreement", ""),
            "source": "CGSI research note, 29 Aug 2025"}


def blind_run(picks_path, demo=False):
    # ORDER MATTERS: score and rank first, open their list second.
    run, source = _score_universe(demo)
    ranked = _ranked(run)
    by_id = {r["company_id"]: r for r in run["records"]}

    payload = _load_json(picks_path, "CGSI picks")
    picks = payload.get("picks") if isinstance(payload, dict) else payload
    if not isinstance(picks, list) or not picks:
        raise InputMissing(f"{picks_path} holds no `picks` list")
    theirs = [p if isinstance(p, str) else p.get("company_id") for p in picks]
    theirs = [t for t in theirs if t]
    if not theirs:
        raise InputMissing(f"{picks_path}: every pick is missing a company_id")

    unknown = [t for t in theirs if t not in by_id]
    k = len(theirs)
    ours = [r["company_id"] for r in ranked[:k]]
    overlap = [c for c in ours if c in set(theirs)]

    covered = [t for t in theirs if t in by_id]
    return {
        "step": "Playbook step 8 — blind validation against CGSI's picks",
        "universe": source, "companies": run["company_count"],
        "run_id": run["run_id"], "config_hash": run["config_hash"], "as_of": run["as_of"],
        "ranked_by": list(RANK_BY),
        "blind": "the ranking above was computed and frozen before the picks file was opened; "
                 "recompute run_id from the universe alone and you get the same order",
        # Without this, the agreement percentage reads as "we disagree with CGSI about ESG",
        # which is not what it measures. CGSI's own note states the three filters behind the 17,
        # and two of them are invisible to this engine by construction.
        "their_filters": _their_filters(),
        "their_count": len(theirs), "our_top_k": k,
        "agreement_pct": round(100.0 * len(overlap) / len(theirs), 1),
        "agreed": sorted(overlap),
        "unknown_to_us": unknown,
        "they_picked_we_did_not": [
            {"company_id": t, "our_rank": next((i + 1 for i, r in enumerate(ranked)
                                                if r["company_id"] == t), None),
             **_why(by_id[t])}
            for t in covered if t not in set(ours)],
        "we_picked_they_did_not": [
            {"company_id": c, "our_rank": i + 1, **_why(by_id[c])}
            for i, c in enumerate(ours) if c not in set(theirs)],
    }


# --------------------------------------------------------------------------- #
#  step 7 — the green-bond issuance backtest
# --------------------------------------------------------------------------- #
def issuance_backtest(events_path, demo=False):
    """Did high momentum at t precede an issuance or a review at t+1?

    Every event is scored with `cutoff` set to its own date, so the momentum being tested is
    what the Radar would have said BEFORE the issuance — `enforce_cutoff` runs on each and fails
    loudly rather than quietly leaking the answer into the prediction.

    The scoring is done over the WHOLE universe at each distinct event date, not one company at
    a time. That matters: `lseg_percentile`, `momentum_percentile` and therefore `disagreement`
    are all cohort-relative, and a cohort of one is 0.5 by definition — score the companies
    singly and every `disagreement` collapses to zero, which reads on a slide as "the Radar
    never flagged anyone" when it actually means "we never asked it to rank anything"."""
    payload = _load_json(events_path, "issuance events")
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list) or not events:
        raise InputMissing(f"{events_path} holds no `events` list")

    cfg = engine_config.load()
    theta = cfg["theta"]
    path = universe.DEMO_FILE if demo else universe.UNIVERSE_FILE
    constituents = universe.constituents(path)
    known = {c.get("ticker", "") for c in constituents}
    meta = company_metadata.load()

    wanted, missing = [], []
    for ev in events:
        cid, date = ev.get("company_id"), ev.get("event_date")
        if not cid or not date:
            missing.append(f"{ev!r} (needs company_id + event_date)")
        elif cid not in known:
            missing.append(f"{cid} (not in {os.path.relpath(path, BASE_DIR)})")
        else:
            wanted.append((cid, date, ev))

    # one full-universe run per DISTINCT event date — the cohort is what makes the percentiles
    # (and so the disagreement) mean anything.
    runs = {}
    for _cid, date, _ev in wanted:
        if date not in runs:
            run = engine.run_engine(constituents, as_of=date, cutoff=date, metadata=meta,
                                    use_cache=False)
            engine.enforce_cutoff(run, cutoff=date)
            runs[date] = run

    rows = []
    for cid, date, ev in wanted:
        rec = engine.record_for(runs[date], cid)
        if rec is None:
            missing.append(f"{cid} (no record in the {date} run)")
            continue
        rows.append({
            "company_id": cid, "event_date": date,
            "event_type": ev.get("event_type", "unknown"),
            "source_url": ev.get("source_url", ""),
            "momentum_before": rec["composite_momentum"],
            "confidence_before": rec["composite_confidence"],
            "signals_before": rec["signal_count"],
            "label_before": rec["label_display"],
            "disagreement_before": rec["disagreement"],
            "cohort_run_id": runs[date]["run_id"],
            "flagged": rec["composite_momentum"] > 0 and rec["disagreement"] >= theta,
            "positive": rec["composite_momentum"] > 0,
        })

    scored = [r for r in rows if r["signals_before"]]
    blind_spots = [r for r in rows if not r["signals_before"]]
    return {
        "step": "Playbook step 7 — green-bond issuance backtest",
        "universe": os.path.relpath(path, BASE_DIR),
        "theta": theta, "config_hash": cfg["config_hash"],
        "events_supplied": len(events), "events_scored": len(rows),
        "cohort_size": len(constituents), "cohort_runs": {d: r["run_id"] for d, r in runs.items()},
        "scored_against": "the full universe at each event date, so percentiles and disagreement "
                          "are cohort-relative",
        "unusable": missing,
        "no_evidence_before_event": [r["company_id"] for r in blind_spots],
        "positive_momentum_pct": round(100.0 * sum(1 for r in scored if r["positive"])
                                       / len(scored), 1) if scored else None,
        "flagged_pct": round(100.0 * sum(1 for r in scored if r["flagged"])
                             / len(scored), 1) if scored else None,
        "rows": sorted(rows, key=lambda r: (r["event_date"], r["company_id"])),
        "reading": "positive_momentum_pct is the share of issuers our momentum was already "
                   "pointing up on BEFORE they issued. It is not a forecast accuracy: we do "
                   "not score the companies that never issued, so this measures recall, not "
                   "precision. Say that on the slide.",
    }


# --------------------------------------------------------------------------- #
#  templates — so the ask to CGSI is exact
# --------------------------------------------------------------------------- #
TEMPLATES = {
    "picks_template.json": {
        "_note": "Playbook step 8 input — CGSI's picks. Only `company_id` is used; it must "
                 "match the ticker in data/asean_universe.json exactly (e.g. SGX:U96). "
                 "Order is ignored. Anything else in a row is carried through untouched.",
        "picks": [{"company_id": "SGX:U96", "name": "(their name for it)", "note": ""},
                  {"company_id": "PSE:ACEN", "name": "", "note": ""}],
    },
    "issuance_events_template.json": {
        "_note": "Playbook step 7 input — dated green-bond issuance / review events. One row "
                 "per event. `event_date` is the date the market learned (exchange filing or "
                 "AsianBondsOnline listing date), NOT the settlement date: the backtest freezes "
                 "our lookback the instant before it, so a wrong date here silently grades us "
                 "on evidence we should not have had.",
        "events": [{"company_id": "SGX:U96", "event_date": "2021-09-29",
                    "event_type": "issuance", "source_url": "https://…"},
                   {"company_id": "PSE:ACEN", "event_date": "2022-11-07",
                    "event_type": "review", "source_url": "https://…"}],
    },
}


def write_templates():
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    for name, body in TEMPLATES.items():
        path = os.path.join(TEMPLATE_DIR, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=1, ensure_ascii=False)
        print(f"  wrote {os.path.relpath(path, BASE_DIR)}")
    print("\n  Send these two shapes to whoever is collecting the data. Both runs are one "
          "command\n  once a real file exists; neither will run on a template.")
    return 0


# --------------------------------------------------------------------------- #
#  reports
# --------------------------------------------------------------------------- #
def report_blind(result):
    print(f"BLIND VALIDATION — {result['companies']} companies ranked by "
          f"{', '.join(result['ranked_by'])}")
    print(f"  run {result['run_id']} · config {result['config_hash']} · as_of {result['as_of']}")
    print(f"  {result['blind']}\n")
    print(f"  their picks   {result['their_count']}")
    print(f"  our top {result['our_top_k']:<5} {len(result['agreed'])} of the same names")
    print(f"  AGREEMENT     {result['agreement_pct']}%\n")
    filters = result.get("their_filters") or {}
    if filters.get("filters"):
        print("  HOW TO READ THAT NUMBER — CGSI's own three filters for the 17:")
        for i, f in enumerate(filters["filters"], 1):
            print(f"    {i}. {f}")
        for line in _wrap(filters.get("how_to_read", ""), 92):
            print(f"    {line}")
        print()
    if result["unknown_to_us"]:
        print(f"  !! not in our universe at all: {result['unknown_to_us']}\n")
    for title, key in (("THEY PICKED, WE DID NOT", "they_picked_we_did_not"),
                       ("WE PICKED, THEY DID NOT", "we_picked_they_did_not")):
        rows = result[key]
        print(f"  {title} ({len(rows)})")
        for row in rows:
            print(f"    {row['company_id']:12s} our rank {str(row['our_rank']):>4s} · "
                  f"{row['label']} · momentum {row['composite_momentum']:+.3f} · confidence "
                  f"{row['composite_confidence']:.3f} · {row['signal_count']} signals")
            for s in row["top_signals"]:
                print(f"        {s['published_at']} [{s['source_type']}] {s['direction']:+d} "
                      f"{s['excerpt'][:88]}")
        print()
    print("  Every disagreement above carries its evidence. That is the deliverable — the "
          "agreement\n  percentage on its own says nothing a coin could not.")
    return 0


def report_issuance(result):
    print(f"ISSUANCE BACKTEST — {result['events_scored']}/{result['events_supplied']} events "
          f"scored · theta {result['theta']}")
    if result["unusable"]:
        print(f"  !! unusable rows ({len(result['unusable'])}): {result['unusable'][:4]}")
    if result["no_evidence_before_event"]:
        print(f"  !! no evidence before the event: {result['no_evidence_before_event']}")
    print()
    print(f"  scored against {result['cohort_size']} companies at each event date "
          f"({len(result['cohort_runs'])} cohort run(s))\n")
    print(f"  {'company':13s} {'event':11s} {'type':10s} {'momentum':>9s} {'disagr':>7s} "
          f"{'conf':>6s} {'n':>3s}  flagged")
    for row in result["rows"]:
        print(f"  {row['company_id']:13s} {row['event_date']:11s} {row['event_type']:10s} "
              f"{row['momentum_before']:+9.3f} {row['disagreement_before']:+7.3f} "
              f"{row['confidence_before']:6.3f} "
              f"{row['signals_before']:3d}  {'YES' if row['flagged'] else '·'}")
    print()
    print(f"  momentum already positive before the event   {result['positive_momentum_pct']}%")
    print(f"  ...and material enough to flag (>= theta)    {result['flagged_pct']}%")
    print(f"\n  {result['reading']}")
    return 0


def main(argv):
    args = argv[1:]
    demo = "--demo" in args

    def _after(flag):
        return args[args.index(flag) + 1] if flag in args and len(args) > args.index(flag) + 1 \
            else None

    try:
        if "--template" in args:
            return write_templates()
        if "--blind" in args:
            result = blind_run(_after("--blind"), demo)
            reporter = report_blind
        elif "--issuance" in args:
            result = issuance_backtest(_after("--issuance"), demo)
            reporter = report_issuance
        else:
            print(__doc__.split("Both runs are blocked")[0].strip())
            return 0
    except InputMissing as exc:
        print(f"BLOCKED — {exc}")
        return 2

    if "--json" in args:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    return reporter(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
