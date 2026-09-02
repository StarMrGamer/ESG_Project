"""THE ROADMAP, COMPUTED — what better SOURCES would do to this engine, run through the engine.

WHAT THIS IS, AND THE ONE THING IT IS NOT
------------------------------------------
Every other forward-looking slide in a pitch deck is a number somebody typed. This one is not.
It takes the evidence the radar has actually gathered, changes ONE stated thing about it — where
each fact came from — and re-runs the real `engine.run_engine` to see what the output becomes.

So it is a **counterfactual, computed**, not a projection, and certainly not a measurement of
future performance. The distinction that matters:

  * it does NOT invent a single event, date, direction or company;
  * it does NOT claim any return, hit rate, or reduction in losses — nothing here touches price;
  * it DOES answer one precise question — "our confidence is capped by where our evidence comes
    from; how much is that costing us?" — by asking the engine instead of guessing.

Every scenario is labelled `illustrative: true` and carries the assumption that produced it, in
the same shape `data/claim_vs_evidence.json` uses for the same reason.

WHY SOURCE MIX IS THE RIGHT DIAL
---------------------------------
`engine_config.source_quality` caps a company's own press release at 0.5 and pays 1.0 for a
regulator action, 0.95 for an exchange filing, 0.9 for an index-provider decision. Confidence is

    coverage x [ mean_quality + (1 - mean_quality) x corroboration_weight x corroboration ]

so mean_quality sits in the middle of it. Measured on the live run: **301 of 369 signals are
company PR** and exactly **one** is a regulator action. That is the binding constraint on
`hidden_winners`, which needs `composite_confidence >= 0.5` — and it is a DATA SOURCING problem,
not a modelling one, which is precisely why it belongs on a roadmap slide rather than in a
backlog of algorithm tweaks.

THE SUBSTITUTION IS DETERMINISTIC
----------------------------------
No RNG anywhere: events are sorted by `event_id` and reassigned by taking every k-th one, so the
same scenario always produces the same run id and the same numbers. A roadmap that moved every
time you rebuilt it would be worth nothing to a reader checking it.

WHAT AN HONEST READER SHOULD TAKE FROM IT
------------------------------------------
That the ceiling is where we say it is. If the same facts arrived through a filing rather than a
press release, the engine would be more confident about them — by exactly this much. It does not
follow that the companies would perform differently, and this module never says they would.
"""
import json
import os
from collections import Counter

import company_metadata
import engine
import engine_config
import harvest
import universe

_ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(_ROOT, "data", "roadmap_scenario.json")

#: The source types a real alt-data contract would deliver, in the order they get used, with the
#: engine's own quality weight beside each so a reader can check the arithmetic.
UPGRADE_TARGETS = ("exchange_filing", "regulator", "index_provider", "external_reviewer")

#: The scenarios. `share` is the fraction of company-PR events reassigned to a better source.
#: Each names the real-world thing that would deliver it — a scenario without an acquisition
#: route attached is a wish, not a roadmap.
SCENARIOS = [
    {"key": "today", "share": 0.0,
     "title": "Today",
     "unlock": "What the radar has actually gathered: four-angle live search over public web "
               "sources.",
     "reality": "measured"},
    {"key": "filings", "share": 0.5,
     "title": "Exchange filings wired in",
     "unlock": "SGX / Bursa / IDX / SET publish structured sustainability filings. Half of what "
               "we currently read as a press release exists there as a filed document.",
     "reality": "counterfactual"},
    {"key": "altdata", "share": 0.8,
     "title": "Regulator + index-provider feeds",
     "unlock": "MAS / SC / OJK enforcement actions and index-provider inclusion decisions. These "
               "are the sources the confidence model pays full weight for, and the ones a "
               "company cannot author about itself.",
     "reality": "counterfactual"},
]


def _load():
    uni = universe.load_universe(os.path.join(_ROOT, "data", "asean_universe.json"))
    cons = harvest.apply_overlay(uni["constituents"], as_of=uni.get("as_of") or "")
    return cons, company_metadata.load(demo=False), engine_config.for_horizon("long")


def reassign(cons, share):
    """Return a COPY of `cons` with `share` of its company-PR events re-sourced.

    Deterministic by construction: events are ordered by `event_id` and every k-th one is taken,
    so there is no RNG and the scenario reproduces exactly. Nothing else about an event changes —
    same text, same date, same direction, same company. Only the provenance is varied, because
    provenance is the single thing the scenario is about.
    """
    out = []
    for c in cons:
        c2 = dict(c)
        events = list(c.get("events") or [])
        pr = sorted([e for e in events if e.get("source_type") == "company_pr"],
                    key=lambda e: str(e.get("event_id")))
        n = int(round(len(pr) * share))
        chosen = {id(e) for e in pr[:n]}
        new = []
        for i, e in enumerate(events):
            if id(e) in chosen:
                e = dict(e)
                # Round-robin across the upgrade targets so a scenario is a MIX of better
                # sources rather than an implausible cliff into one channel.
                e["source_type"] = UPGRADE_TARGETS[len(new) % len(UPGRADE_TARGETS)]
            new.append(e)
        c2["events"] = new
        out.append(c2)
    return out


def measure(cons, meta, cfg):
    """Run the real engine and pull out only what the roadmap claims: evidence quality effects.

    `use_cache=False` IS LOAD-BEARING AND MUST NOT BE REMOVED AS AN OPTIMISATION.

    `run_id` hashes signal IDs, not signal CONTENT, and `source_type` is not part of a signal id.
    So every scenario in this module produces the same run id as today's run while producing
    genuinely different confidences and labels — and with the cache on, `_read_cache` serves the
    FIRST scenario's records for all three. Measured: the 23%-PR scenario comes back with 11 of
    52 confident instead of 22, silently, under an id that says it is the same run.

    That is a latent engine bug rather than a fact about this module (see the note filed with it),
    and the fix — folding scoring-relevant signal fields into the id — moves every run id in the
    repo, so it is a sign-off decision. Until then this flag is the thing standing between the
    roadmap and a table of three identical rows.
    """
    run = engine.run_engine(cons, metadata=meta, config=cfg, use_cache=False)
    recs = run["records"]
    sig = [s for r in recs for s in r.get("signals", [])]
    types = Counter(s.get("source_type") for s in sig)
    conf = [s["confidence"] for s in sig]
    labels = Counter(r["label"] for r in recs)
    return {
        "run_id": run["run_id"],
        "companies": len(recs),
        "signals": len(sig),
        "mean_signal_confidence": round(sum(conf) / len(conf), 3) if conf else None,
        "company_pr_share": round(types.get("company_pr", 0) / len(sig), 3) if sig else None,
        "companies_confident": sum(1 for r in recs if r["composite_confidence"] >= 0.5),
        "mean_company_confidence": round(
            sum(r["composite_confidence"] for r in recs) / len(recs), 3) if recs else None,
        "hidden_winners": labels.get("hidden_winners", 0),
        "labels": dict(labels),
        "source_types": dict(types),
    }


def build():
    cons, meta, cfg = _load()
    rows = []
    for sc in SCENARIOS:
        c = cons if sc["share"] == 0 else reassign(cons, sc["share"])
        m = measure(c, meta, cfg)
        rows.append({**sc, **m})
    base = rows[0]
    for r in rows:
        r["confident_delta"] = r["companies_confident"] - base["companies_confident"]
        r["hidden_winner_delta"] = r["hidden_winners"] - base["hidden_winners"]
    return {
        "_note": "ILLUSTRATIVE COUNTERFACTUAL. Rows after the first are the REAL engine re-run "
                 "over the SAME evidence with only the SOURCE TYPE of some events changed, to "
                 "show how much of our confidence ceiling is set by where evidence comes from. "
                 "No event, date, direction or company is invented, and nothing here is a claim "
                 "about returns, performance or losses avoided.",
        "header": "Roadmap (illustrative — the real engine re-run over the same evidence under a "
                  "stated change of source mix; not a measurement and not a return forecast).",
        "deck_line": "Our confidence ceiling is a sourcing problem, not a modelling one — and we "
                     "can show you exactly what fixing it is worth, because we ran it.",
        "illustrative": True,
        "dial": "source_type only — text, dates, directions and companies are untouched",
        "source_quality": engine_config.for_horizon("long").get("source_quality", {}),
        "scenarios": rows,
    }


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="What better sources would do — computed.")
    ap.add_argument("--freeze", action="store_true", help="write data/roadmap_scenario.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    payload = build()
    if args.freeze:
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"wrote {OUT_JSON}")
    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
        return 0
    print("\nROADMAP — what better SOURCES would do (the real engine, re-run)")
    print("=" * 78)
    print(f"  dial: {payload['dial']}")
    print(f"\n  {'scenario':<34}{'PR share':>9}{'mean conf':>11}"
          f"{'confident':>11}{'hidden w.':>11}")
    for r in payload["scenarios"]:
        tag = "" if r["reality"] == "measured" else "  (counterfactual)"
        print(f"  {r['title']:<34}{r['company_pr_share']:>8.0%}"
              f"{r['mean_company_confidence']:>11.3f}"
              f"{r['companies_confident']:>8} /52{r['hidden_winners']:>11}{tag}")
    print(f"\n  {payload['header']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
