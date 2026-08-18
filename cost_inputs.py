"""
cost_inputs.py — STEP 8.5: the three numbers Sean's cost model is still missing.
================================================================================

    python cost_inputs.py            # the three numbers, measured
    python cost_inputs.py --json     # the same, machine-readable, to paste into the model

The runbook asks Rai to send Sean, by Fri 21 Aug: **signals per company per month · tokens per
signal · cache hit rate** — "the last yellow cells in the cost model". This script measures all
three off the artefacts we actually hold, and refuses to fill a cell it cannot measure.

Two of the three come back with an answer the cost model was probably not expecting, and both
change its shape rather than just its numbers:

* **tokens/signal is zero.** The extractor is `rules-v1` — deterministic keyword routing, no
  model call anywhere in the scoring path. That is not a shortcut taken to save money; it is
  what makes Gate 1 possible, because a model call would put sampling noise inside the number
  we promise is reproducible. So the LLM spend does not scale with the universe or with the
  signal count at all. It scales with **questions asked** — i.e. with sessions, which is a
  usage driver, not a data driver. `llm_cost.py` prices that side.

* **signals/company/month is a floor, not a rate.** The only real, dated, sourced evidence we
  hold is the five backtest cases, and those events were curated to tell five stories — not
  swept exhaustively. The demo universe has 390 signals sitting on four distinct dates, which
  makes it a fixture and not a time series; it is reported here only to be ruled out.

Run it, read the caveats, and send the whole output rather than the three numbers alone — a
figure this soft is worse than useless once it is separated from what it means.
"""

import json
import os
import sys

import company_metadata
import engine
import harness
import llm_cost
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _months_between(later, earlier):
    return ((int(later[:4]) * 12 + int(later[5:7])) -
            (int(earlier[:4]) * 12 + int(earlier[5:7])))


# --------------------------------------------------------------------------- #
#  1. signals per company per month
# --------------------------------------------------------------------------- #
def signals_per_company_month():
    """From the backtest cases — the only evidence we hold that is real, dated and sourced."""
    cases = harness.load_cases()["cases"]
    per_case, signals, months = [], 0, 0
    for case in cases:
        first = min(e["published_at"] for e in case["events"])
        span = max(1, _months_between(case["cutoff_date"], first))
        run = engine.run_engine([harness.case_company(case)], cutoff=case["cutoff_date"],
                                use_cache=False)
        n = run["records"][0]["signal_count"]
        signals += n
        months += span
        per_case.append({"case_id": case["case_id"], "ticker": case["ticker"],
                         "events": len(case["events"]), "signals": n, "months": span,
                         "rate": round(n / span, 3)})

    # The demo universe, measured only so it can be explicitly ruled out.
    demo = engine.run_engine(universe.constituents(universe.DEMO_FILE),
                             metadata=company_metadata.load(), use_cache=False)
    demo_dates = {s["published_at"] for r in demo["records"] for s in r["signals"]
                  if s.get("published_at")}
    stamped = sum(1 for r in demo["records"] for s in r["signals"]
                  if s.get("date_basis") == "dataset_as_of")

    return {
        "value": round(signals / months, 3),
        "unit": "scored signals per company per month",
        "basis": "the five backtest cases (data/backtest_cases.json), each scored with its "
                 "lookback frozen at its own cutoff",
        "sample": {"companies": len(cases), "signals": signals, "company_months": months},
        "per_case": per_case,
        "caveat": "A FLOOR, not an arrival rate. These events were transcribed from a research "
                  "handoff that picked what told each story; nobody swept those five companies "
                  "exhaustively. A production crawl produces more signals per month than this, "
                  "so use it to bound the LOW end and mark the cell as a floor.",
        "excluded": {
            "source": os.path.relpath(universe.DEMO_FILE, BASE_DIR),
            "signals": demo["signal_count"], "companies": demo["company_count"],
            "distinct_dates": len(demo_dates), "stamped_dataset_as_of": stamped,
            "why": f"{demo['signal_count']} signals on {len(demo_dates)} distinct dates "
                   f"({stamped} of them stamped with the dataset's as-of date rather than a "
                   f"published date). That is a fixture, not a time series — dividing it by a "
                   f"span would manufacture a rate out of a stamp.",
        },
    }


# --------------------------------------------------------------------------- #
#  2. tokens per signal
# --------------------------------------------------------------------------- #
def tokens_per_signal():
    run = engine.run_engine(universe.constituents(universe.DEMO_FILE),
                            metadata=company_metadata.load(), use_cache=False)
    rows = llm_cost.measure(universe.constituents(universe.DEMO_FILE), questions=3)
    avg_prompt = sum(r["prompt_tokens"] for r in rows) / len(rows)
    avg_floor = sum(r["completion_floor"] for r in rows) / len(rows)
    avg_ceiling = sum(r["completion_ceiling"] for r in rows) / len(rows)
    return {
        "value": 0,
        "unit": "LLM tokens per extracted signal",
        "basis": f"extractor {run['extractor_version']} — deterministic keyword routing in "
                 f"signals.py; `core.call_llm` is never reached from the scoring path",
        "verified": "run_engine is a pure function: no clock, no RNG, no network, no LLM. "
                    "That is Gate 1, and the harness asserts it on every run.",
        "consequence": "LLM spend does not scale with universe size, company count or signal "
                       "count. It scales with QUESTIONS ASKED — i.e. with user sessions.",
        "where_the_tokens_are": {
            "path": "the Stage 1 -> Stage 2 deep dive (stage1.py + stage2.py)",
            "scenario": "typical: 3 Stage-1 questions + Stage 2 = 4 calls",
            "prompt_tokens_per_dive": round(avg_prompt),
            "completion_tokens_per_dive": f"{round(avg_floor):,} floor .. {round(avg_ceiling):,} ceiling",
            "priced_by": "llm_cost.py (pass --price-in / --price-out / --price-cached)",
        },
        "signals_scored_for_free": run["signal_count"],
    }


# --------------------------------------------------------------------------- #
#  3. cache hit rate
# --------------------------------------------------------------------------- #
def cache_hit_rate():
    """Three caches, three different meanings. The cost model wants the first one."""
    scenarios = {}
    for name, questions, _why in llm_cost.SCENARIOS:
        rows = llm_cost.measure(universe.constituents(universe.DEMO_FILE), questions=questions)
        cached = sum(r["cached_prompt_tokens"] for r in rows) / len(rows)
        total = sum(r["prompt_tokens"] for r in rows) / len(rows)
        scenarios[name] = {"questions": questions, "calls": questions + 1,
                           "prompt_tokens": round(total), "cacheable": round(cached),
                           "hit_rate_pct": round(100.0 * cached / total, 1)}

    # The engine's own run cache, measured rather than asserted — and measured from COLD, in a
    # throwaway directory, so the first lookup genuinely misses. Pointing it at the real
    # .cache would have reported 100% simply because this session had already run the engine,
    # which is the number you get by asking the question badly.
    constituents = universe.constituents(universe.DEMO_FILE)
    meta = company_metadata.load()
    repeats = 5
    cold_dir = os.path.join(BASE_DIR, ".cache", "engine", "_cost_inputs_probe")
    for stale in (os.listdir(cold_dir) if os.path.isdir(cold_dir) else []):
        os.remove(os.path.join(cold_dir, stale))
    os.makedirs(cold_dir, exist_ok=True)

    lookups = hits = 0
    original = engine._read_cache                                        # noqa: SLF001

    def counting_read(path):
        nonlocal lookups, hits
        lookups += 1
        got = original(path)
        hits += 1 if got else 0
        return got

    engine._read_cache = counting_read                                   # noqa: SLF001
    try:
        for _ in range(repeats):
            engine.run_engine(constituents, metadata=meta, use_cache=True, cache_dir=cold_dir)
    finally:
        engine._read_cache = original                                    # noqa: SLF001

    return {
        "llm_prompt_cache": {
            "value_pct": scenarios["typical"]["hit_rate_pct"],
            "unit": "% of prompt tokens billable at the cache-HIT rate",
            "basis": "the provider's context cache is a PREFIX cache. The two system prompts "
                     "(stage1 + stage2) are byte-identical on every call and every company, and "
                     "each Stage-1 turn resends the conversation so far — only the newest "
                     "question/answer pair is new.",
            "by_scenario": scenarios,
            "caveat": "This is the CACHEABLE share, computed from the prompt structure — it is "
                      "what the cache can serve, and it holds only while calls stay warm inside "
                      "the provider's TTL. A cold first call of a session pays full rate for the "
                      "system prompt. Treat it as the ceiling on the hit rate, not the observed "
                      "hit rate; nothing offline can observe the provider's cache.",
        },
        "engine_run_cache": {
            "value_pct": round(100.0 * hits / lookups, 1) if lookups else 0.0,
            "unit": "% of run lookups served from .cache/engine",
            "measured": f"{hits}/{lookups} lookups over {repeats} identical runs from COLD "
                        f"(the first necessarily misses)",
            "note": "Saves compute, not tokens — there are no tokens in the score path to save. "
                    "Relevant to Sean only as 'repeat scoring is free'. The rate is just "
                    "1 - 1/repeats: every rerun of an unchanged universe hits.",
        },
        "rag_fetch_cache": {
            "value_pct": None,
            "unit": "% of retrieval fetches served from .cache",
            "why_unmeasured": "Retrieval hit rate depends on how often two users ask about the "
                              "same company inside the TTL, which no offline run can observe. "
                              "The TTL is ESG_RAG_TTL (default 6h). Left blank rather than "
                              "guessed — a made-up hit rate here would flatter the model.",
        },
    }


# --------------------------------------------------------------------------- #
def collect():
    return {
        "_for": "Sean — the three yellow cells in the cost model (runbook STEP 8.5)",
        "_from": "Rai · ASEAN ESG Momentum Radar prototype",
        "_reproduce": "python cost_inputs.py --json",
        "signals_per_company_month": signals_per_company_month(),
        "tokens_per_signal": tokens_per_signal(),
        "cache_hit_rate": cache_hit_rate(),
    }


def report(data):
    sig, tok, cache = (data["signals_per_company_month"], data["tokens_per_signal"],
                       data["cache_hit_rate"])
    print("COST-MODEL INPUTS — the three yellow cells (runbook STEP 8.5)\n")

    print(f"1. SIGNALS PER COMPANY PER MONTH      {sig['value']}")
    s = sig["sample"]
    print(f"     measured over            {s['signals']} signals · {s['companies']} companies · "
          f"{s['company_months']} company-months")
    print(f"     basis                    {sig['basis']}")
    for row in sig["per_case"]:
        print(f"       {row['case_id']:9s} {row['signals']} signals / {row['months']:2d} months "
              f"= {row['rate']:.3f}")
    print(f"     CAVEAT                   {_wrap(sig['caveat'], 30)}")
    ex = sig["excluded"]
    print(f"     ruled out                {ex['source']}:")
    print(f"                              {_wrap(ex['why'], 30)}\n")

    print(f"2. TOKENS PER SIGNAL                  {tok['value']}")
    print(f"     basis                    {_wrap(tok['basis'], 30)}")
    print(f"     verified                 {_wrap(tok['verified'], 30)}")
    print(f"     signals scored for free  {tok['signals_scored_for_free']} in the demo run")
    w = tok["where_the_tokens_are"]
    print(f"     the tokens are here      {w['path']}")
    print(f"                              {w['scenario']} · {w['prompt_tokens_per_dive']:,} prompt "
          f"· {w['completion_tokens_per_dive']} completion")
    print(f"     CONSEQUENCE              {_wrap(tok['consequence'], 30)}\n")

    llm = cache["llm_prompt_cache"]
    print(f"3. CACHE HIT RATE                     {llm['value_pct']}%   (LLM prompt cache, typical dive)")
    for name, row in llm["by_scenario"].items():
        print(f"       {name:8s} {row['calls']} calls · {row['prompt_tokens']:>6,} prompt tokens · "
              f"{row['cacheable']:>6,} cacheable = {row['hit_rate_pct']:4.1f}%")
    print(f"     basis                    {_wrap(llm['basis'], 30)}")
    print(f"     CAVEAT                   {_wrap(llm['caveat'], 30)}")
    eng = cache["engine_run_cache"]
    print(f"     engine run cache         {eng['value_pct']}% — {eng['measured']}")
    print(f"                              {_wrap(eng['note'], 30)}")
    rag = cache["rag_fetch_cache"]
    print(f"     retrieval cache          not measured")
    print(f"                              {_wrap(rag['why_unmeasured'], 30)}")

    print("\n  Send the whole output, not the three numbers. Two of them (a floor, and a "
          "\n  cacheable-share ceiling) mean the opposite of what a bare figure implies.")
    return 0


def _wrap(text, indent, width=94):
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
    data = collect()
    if "--json" in argv[1:]:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    return report(data)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
