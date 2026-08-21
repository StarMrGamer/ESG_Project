"""
cost_model.py — the unit economics, computed from measured numbers and nothing else.
====================================================================================

`04_BUSINESS_SEAN_CAYDEN/ESG_Radar_Cost_and_Scale_Model.xlsx` is a skeleton: labels, a colour
convention, and prose descriptions of formulas ("day rate x weeks x days/week x FTE"). It holds
no formulas and no values. This module is the calculating half, built the way everything else
in this repo is built — every input either measured here, or REQUIRED from the caller with a
source, and never guessed.

THE ASSUMPTION IN THE SKELETON IS WRONG FOR THIS ARCHITECTURE
-------------------------------------------------------------
The workbook assumes **40 signals per company per month at 1500 tokens per signal**. That
describes a system where a model does the scoring. Ours does not:

* **the scoring path costs ZERO tokens.** `signals.py` routes by rule and `engine.py` scores
  deterministically. No LLM is reachable from it. Per-signal token cost is not a small number
  here — it is structurally zero, and that is a claim worth making on stage.
* **all LLM cost sits in GATHERING** (`harvest.py`), and it is charged per SWEEP of a company,
  not per signal. Measured: 4 calls and ~6,059 tokens per company per sweep, yielding ~5.3
  dated, sourced facts.

So the model's variable-cost line should read *tokens per company per sweep x sweeps per month*,
not *signals x tokens per signal*. Those two produce very different numbers, and only one of
them describes what the code does.

WHAT THIS REFUSES TO DO
-----------------------
Guess a price. `--price-hit` / `--price-miss` / `--price-out` are REQUIRED, exactly as in
`llm_cost.py`: a made-up
per-token price flatters a cost model more effectively than any other single number, and the
whole pitch rests on not doing that. Day rates, licence quotes and the price point are business
inputs and are reported as MISSING with the document that would settle each one, rather than
filled with something plausible.

    # DeepSeek's published card, off-peak: hit 0.007 / miss 0.22 / output 0.66 per 1M
    python cost_model.py --price-hit 0.007 --price-miss 0.22 --price-out 0.66 --window off-peak
    python cost_model.py --price-hit 0.014 --price-miss 0.44 --price-out 1.32 --window peak
    python cost_model.py ... --csv                               # paste-ready for the workbook
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#: Business inputs this module will not invent. Each names the document that settles it.
MISSING_INPUTS = (
    ("Data / ML engineer day rate", "SGD/day",
     "MyCareersFuture or Michael Page SG salary guide 2026"),
    ("Full-stack engineer day rate", "SGD/day", "same"),
    ("Domain / ESG analyst day rate", "SGD/day", "same"),
    ("Project manager day rate", "SGD/day", "same"),
    ("LSEG / baseline ESG feed, pilot scope", "SGD total",
     "quote from LSEG or CGSI — no reply yet; model from comparables and SAY SO"),
    ("Licensed job-posting feed", "SGD total", "quote — licensed feeds only, no scraping"),
    ("Annual price per firm", "SGD/year",
     "anchor to a public ESG subscription comparable and cite it"),
    ("Milestone the ask buys", "text",
     "a specific, checkable outcome — not 'build the product'"),
)


def measured_inputs() -> Dict[str, Any]:
    """The cells the workbook marks 'NEEDS TEAM NUMBER from Rai'. Measured, not estimated."""
    import harvest                                             # noqa: PLC0415

    # Read the PERSISTED measurement. Re-measuring rebuilds every prompt (4 retrieval calls per
    # company), which is slow enough to be its own problem and needs a warm cache to work at
    # all — so it is a deliberate step (`harvest.py --cost`), not something this model triggers.
    profile = harvest.load_cost_profile()
    if not profile.get("companies"):
        return {"available": False,
                "reason": ("No measured harvest cost on disk. Run `python harvest.py --cost` "
                           "once (it writes data/harvest_cost.json), then re-run this.")}
    return {
        "available": True,
        "companies_measured": profile["companies"],
        "calls_per_company_per_sweep": profile["calls_per_company_per_sweep"],
        "prompt_tokens_per_company_per_sweep": profile["avg_prompt_tokens_per_company"],
        "output_tokens_per_company_per_sweep": profile["avg_output_tokens_per_company"],
        "tokens_per_company_per_sweep": profile["avg_total_tokens_per_company"],
        "cacheable_prompt_share_pct": profile["cacheable_prompt_share"],
        "facts_kept_per_company_per_sweep": profile["avg_events_kept"],
        "tokens_per_signal_scoring_path": 0,
        "basis": profile["basis"],
    }


def unit_economics(measured: Dict[str, Any], *, price_hit: float, price_miss: float,
                   price_out: float, fx: float, sweeps_per_month: float,
                   cache_hit: float) -> Dict[str, Any]:
    """Cost to cover ONE company for one month, in SGD.

    DeepSeek bills a cache HIT at its own rate rather than as a discount — on the published card
    that is $0.007 per 1M against $0.22 on a miss, a 31x difference on the cached slice, not a
    write-off. Modelling the cache as "those tokens are free" overstates the saving; modelling it
    as a flat percentage off the whole prompt overstates it far worse. So the prompt is split:

        cached slice   = prompt x cacheable_share x cache_hit   -> billed at `price_hit`
        everything else                                          -> billed at `price_miss`

    `cache_hit` applies ONLY to the cacheable share, never to output, and the cacheable share is
    a measured property of the prompt (the byte-identical system prompt), not an aspiration."""
    prompt = measured["prompt_tokens_per_company_per_sweep"]
    output = measured["output_tokens_per_company_per_sweep"]
    cacheable = prompt * measured["cacheable_prompt_share_pct"] / 100.0
    hit_tokens = cacheable * cache_hit
    miss_tokens = prompt - hit_tokens

    usd_per_sweep = ((hit_tokens / 1e6) * price_hit
                     + (miss_tokens / 1e6) * price_miss
                     + (output / 1e6) * price_out)
    sgd_per_sweep = usd_per_sweep * fx
    return {
        "sweeps_per_month": sweeps_per_month,
        "cache_hit_tokens_per_sweep": round(hit_tokens),
        "cache_miss_tokens_per_sweep": round(miss_tokens),
        "output_tokens_per_sweep": output,
        "usd_per_company_per_sweep": round(usd_per_sweep, 7),
        "sgd_per_company_per_sweep": round(sgd_per_sweep, 6),
        "sgd_per_company_per_month": round(sgd_per_sweep * sweeps_per_month, 6),
        "sgd_per_company_per_year": round(sgd_per_sweep * sweeps_per_month * 12, 4),
        "cache_hit_applied": cache_hit,
        "note": ("Inference only. Excludes the fixed data licence, which is the cost that FALLS "
                 "per company as clients are added — that curve is the scalability story, and "
                 "it cannot be drawn until a licence quote exists."),
    }


def scale(unit: Dict[str, Any], companies: List[int]) -> List[Dict[str, Any]]:
    """Annual inference run-rate at several coverage levels.

    Deliberately NOT the marginal-cost-per-company chart the workbook asks for: inference is
    linear in companies, so that line is FLAT on this cost alone. It only falls once the fixed
    data licence is spread across clients, and nobody has a licence quote yet. Drawing a falling
    line before that number exists would be drawing the conclusion first."""
    per_year = unit["sgd_per_company_per_year"]
    return [{"companies": n, "inference_sgd_per_year": round(per_year * n, 2),
             "inference_sgd_per_company_per_year": round(per_year, 4)} for n in companies]


def build(*, price_hit: float, price_miss: float, price_out: float, fx: float, sweeps: float,
          cache_hit: float, companies: List[int], window: str = "") -> Dict[str, Any]:
    measured = measured_inputs()
    if not measured.get("available"):
        return {"available": False, "reason": measured.get("reason")}
    unit = unit_economics(measured, price_hit=price_hit, price_miss=price_miss,
                          price_out=price_out, fx=fx, sweeps_per_month=sweeps,
                          cache_hit=cache_hit)
    return {
        "available": True,
        "prices": {"usd_per_1m_input_cache_hit": price_hit,
                   "usd_per_1m_input_cache_miss": price_miss,
                   "usd_per_1m_output": price_out, "usd_sgd": fx, "window": window,
                   "source": "SUPPLIED BY CALLER — this module never guesses a price"},
        "measured": measured,
        "unit_economics": unit,
        "scale": scale(unit, companies),
        "missing": [{"input": a, "unit": b, "settled_by": c} for a, b, c in MISSING_INPUTS],
    }


def _print(model: Dict[str, Any]) -> None:
    m, u = model["measured"], model["unit_economics"]
    print("COST MODEL — measured inputs, supplied prices, nothing guessed\n")
    print("MEASURED (the workbook's 'NEEDS TEAM NUMBER from Rai' cells)")
    print("  companies measured over                 %8d" % m["companies_measured"])
    print("  LLM calls per company per sweep         %8d" % m["calls_per_company_per_sweep"])
    print("  tokens per company per sweep            %8d  (%d prompt + %d output)"
          % (m["tokens_per_company_per_sweep"], m["prompt_tokens_per_company_per_sweep"],
             m["output_tokens_per_company_per_sweep"]))
    print("  cacheable prompt share                  %7.1f%%" % m["cacheable_prompt_share_pct"])
    print("  dated facts kept per company per sweep  %8.1f" % m["facts_kept_per_company_per_sweep"])
    print("  TOKENS PER SIGNAL, SCORING PATH         %8d  <- rule-based; structurally zero"
          % m["tokens_per_signal_scoring_path"])
    print("\n  %s" % m["basis"])

    p = model["prices"]
    print("\nPRICES (supplied, not guessed)%s"
          % (" — %s window" % p["window"] if p["window"] else ""))
    print("  USD / 1M input, cache HIT   %8.4f" % p["usd_per_1m_input_cache_hit"])
    print("  USD / 1M input, cache MISS  %8.4f" % p["usd_per_1m_input_cache_miss"])
    print("  USD / 1M output             %8.4f      USD:SGD %.3f"
          % (p["usd_per_1m_output"], p["usd_sgd"]))

    print("\nUNIT ECONOMICS — inference only")
    print("  sweeps per company per month            %8.1f" % u["sweeps_per_month"])
    print("  cache hit applied to cacheable prompt   %7.0f%%" % (u["cache_hit_applied"] * 100))
    print("  prompt tokens billed at HIT rate        %8d" % u["cache_hit_tokens_per_sweep"])
    print("  prompt tokens billed at MISS rate       %8d" % u["cache_miss_tokens_per_sweep"])
    print("  USD per company per sweep               %12.7f" % u["usd_per_company_per_sweep"])
    print("  SGD per company per sweep               %12.6f" % u["sgd_per_company_per_sweep"])
    print("  SGD per company per MONTH               %12.6f" % u["sgd_per_company_per_month"])
    print("  SGD per company per YEAR                %12.4f" % u["sgd_per_company_per_year"])
    print("\n  %s" % u["note"])

    print("\nSCALE — annual inference run-rate")
    print("  %-12s %18s %26s" % ("companies", "inference SGD/yr", "SGD per company per yr"))
    for row in model["scale"]:
        print("  %-12d %18.2f %26.4f"
              % (row["companies"], row["inference_sgd_per_year"],
                 row["inference_sgd_per_company_per_year"]))
    print("\n  This line is FLAT, and that is correct: inference is linear in companies. It only")
    print("  falls once the fixed data licence is spread across clients — and no licence quote")
    print("  exists yet. A falling line drawn before that number arrives is the conclusion drawn")
    print("  first, which is the one thing the model is supposed to prevent.")

    print("\nSTILL MISSING — business inputs this module will not invent")
    for row in model["missing"]:
        print("  %-42s %-12s %s" % (row["input"], row["unit"], row["settled_by"]))


def _csv(model: Dict[str, Any]) -> None:
    m, u = model["measured"], model["unit_economics"]
    print("section,line,value,unit,source")
    for line, val, unit in (
            ("LLM calls per company per sweep", m["calls_per_company_per_sweep"], "calls"),
            ("Tokens per company per sweep", m["tokens_per_company_per_sweep"], "tokens"),
            ("Cacheable prompt share", m["cacheable_prompt_share_pct"], "%"),
            ("Facts kept per company per sweep", m["facts_kept_per_company_per_sweep"], "facts"),
            ("Tokens per signal (scoring path)", 0, "tokens")):
        print('Measured,"%s",%s,%s,"measured by harvest.py --cost over %d companies"'
              % (line, val, unit, m["companies_measured"]))
    for line, val, unit in (
            ("SGD per company per sweep", u["sgd_per_company_per_sweep"], "SGD"),
            ("SGD per company per month", u["sgd_per_company_per_month"], "SGD"),
            ("SGD per company per year", u["sgd_per_company_per_year"], "SGD")):
        print('Unit economics,"%s",%s,%s,"computed from measured tokens x supplied price"'
              % (line, val, unit))
    for row in model["missing"]:
        print('MISSING,"%s",,%s,"%s"' % (row["input"], row["unit"], row["settled_by"]))


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--price-hit", type=float, required=True,
                    help="USD per 1M INPUT tokens on a CACHE HIT. Required — never guessed.")
    ap.add_argument("--price-miss", type=float, required=True,
                    help="USD per 1M INPUT tokens on a CACHE MISS. Required — never guessed.")
    ap.add_argument("--price-out", type=float, required=True,
                    help="USD per 1M OUTPUT tokens. Required — never guessed.")
    ap.add_argument("--window", default="", help="peak / off-peak, for the record")
    ap.add_argument("--fx", type=float, default=1.35, help="USD:SGD (default 1.35)")
    ap.add_argument("--sweeps", type=float, default=4.0,
                    help="Harvest sweeps per company per month (default 4 — weekly)")
    ap.add_argument("--cache-hit", type=float, default=0.9,
                    help="Share of the CACHEABLE prompt actually served warm (default 0.9)")
    ap.add_argument("--companies", type=int, nargs="*", default=[52, 500, 2000])
    ap.add_argument("--csv", action="store_true", help="paste-ready rows for the workbook")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    model = build(price_hit=a.price_hit, price_miss=a.price_miss, price_out=a.price_out,
                  fx=a.fx, sweeps=a.sweeps, cache_hit=a.cache_hit, companies=a.companies,
                  window=a.window)
    if not model.get("available"):
        print(model.get("reason", "no measured inputs available"))
        return 1
    if a.json:
        print(json.dumps(model, indent=1))
    elif a.csv:
        _csv(model)
    else:
        _print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
