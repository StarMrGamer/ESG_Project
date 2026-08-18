"""
llm_cost.py — INSTRUCTIONS step 10: LLM cost per company, measured off the golden set.
=====================================================================================
Produces the one number Sean's model needs:

    cost/company = tokens per company x price per token
    tokens/company = Stage-1 interrogation + Stage-2 competing answer (prompt + completion)

    python llm_cost.py                                   # tokens only
    python llm_cost.py --price-in 0.27 --price-out 1.10  # USD per 1M tokens -> dollars

**Prices are never guessed.** No price flag (or `ESG_LLM_PRICE_IN` / `ESG_LLM_PRICE_OUT`), no
dollar figure — the script prints tokens and says what it needs. Publishing an invented price
for a real vendor would be exactly the fabrication HARD RULE 2 forbids.

**Tokens are measured, not assumed, in the only way available offline.** `core.call_llm()`
returns the assistant string and not the API's usage block, and `core.py` is frozen, so this
script builds the REAL prompts (`stage2.build_user_message` + `stage2.SYSTEM_PROMPT`, and the
Stage-1 system prompt) for real companies from the golden set and converts characters to tokens
at a stated ratio (default 4.0 chars/token — the usual English approximation). Every assumption
is printed alongside the number so the estimate can be re-derived or corrected.

**A deep dive is SIX calls, not two.** Stage 1 is an interrogation *loop* — up to
`core.MAX_QUESTIONS` turns, each its own `call_llm` carrying the system prompt and the
conversation so far — and Stage 2 is one further call. An earlier version of this script priced
one Stage-1 call plus one Stage-2 call and so understated a full dive several times over. The
call structure is now modelled explicitly and reported per scenario (lean / typical / ceiling),
because "cost per company" has no single answer until you say how many questions were asked.

**Input splits into cached and uncached, and the split dominates.** The two system prompts are
byte-identical on every call, so after the first they bill at the provider's context-cache rate
— on DeepSeek roughly 1/31 of the cache-miss rate. They are ~88% of prompt bytes, so pricing all
input at the miss rate overstates input cost by close to an order of magnitude. `--price-cached`
supplies that rate; without it the script prices ALL input at the miss rate and says so.

**The completion budgets are asserted against the source, not remembered.** `_verify_budgets()`
re-reads the real `max_tokens=` at each call site and refuses to run if the constants below have
drifted — that drift is exactly what produced the last set of wrong numbers.

The engine itself costs **zero** LLM tokens: signal extraction is rule-based and deterministic
(`signals.py`), which is why this number is per *deep dive*, not per scored company.
"""

import json
import os
import re
import sys

import company_metadata
import contracts
import core
import engine
import stage1
import stage2
import universe

DEFAULT_CHARS_PER_TOKEN = 4.0

# Completion budgets the app actually asks for (max_tokens at each call site). Asserted against
# the source by _verify_budgets() — these are a cache of what the code does, never a claim.
STAGE1_MAX_COMPLETION = 1000
# Raised 2000 -> 4000 on 19 Aug 2026 with the stage2.py fix. Not a tuning choice: at 2000 the
# reasoning model consumed the whole budget thinking and never emitted its JSON, so every
# Contract C field coerced to "unknown". The ceiling below doubles for Stage 2 as a result, and
# that is a real doubling of the worst case, not a bookkeeping change.
STAGE2_MAX_COMPLETION = 4000

# How many Stage-1 questions a dive actually asks. The cap is core.MAX_QUESTIONS; a user who
# answers crisply narrows sooner. Named endpoints beat one averaged number nobody can audit.
SCENARIOS = (
    ("lean", 1, "user's first answer already narrows it"),
    ("typical", 3, "a normal interrogation"),
    ("ceiling", core.MAX_QUESTIONS, f"every turn used (cap {core.MAX_QUESTIONS})"),
)

# Both stages retry once when the model returns unparseable JSON (stage1.py / stage2.py), so a
# bad run costs double. Reported as a separate risk line rather than folded into the headline.
RETRY_FACTOR = 2.0

# One Stage-1 exchange, in characters. The assistant side is measured from the fixtures below;
# the user side is genuinely user behaviour and cannot be measured from anything on disk, so it
# is a STATED assumption (override with --answer-chars). It rides on the uncached input term,
# the smallest of the four, so error here barely moves the total.
TURN_CHARS = {"assistant": 0, "user": 150}


def _measured_floor(chars_per_token):
    """Size the per-call JSON payload off the VERIFIED fixtures, not off memory.

    fixtures/*.json are real outputs each stage was signed off against, so they are the one
    honest offline answer to "how much does the model actually emit". Deriving it here means the
    floor tracks the contracts automatically instead of drifting into a stale constant.
    """
    with open("fixtures/narrowed_question.json", "r", encoding="utf-8") as fh:
        nq = json.load(fh)
    with open("fixtures/stage2_answer.json", "r", encoding="utf-8") as fh:
        answer = json.load(fh)
    trail = nq.get("trail") or []
    # One Stage-1 turn emits one trail-shaped envelope (question + axis + rationale).
    s1_chars = (sum(len(json.dumps(t, separators=(",", ":"))) for t in trail) / len(trail)
                if trail else 250.0)
    # `sources` is attached by the radar from real retrieval — the model never emits it, so it
    # must not be billed as completion (HARD RULE 2 is also why it cannot be invented).
    emitted = {k: v for k, v in answer.items() if k != "sources"}
    s2_chars = len(json.dumps(emitted, separators=(",", ":")))
    return {"stage1": s1_chars / float(chars_per_token),
            "stage2": s2_chars / float(chars_per_token),
            "stage1_chars": s1_chars, "stage2_chars": s2_chars}


def _verify_budgets():
    """Fail loudly if the constants above have drifted from the real call sites.

    The previous figures were wrong because these were remembered (400/900) while the code had
    moved on (1000/2000). A cost model that silently disagrees with the code it prices is worse
    than no cost model, so this refuses to print rather than print something stale.
    """
    found = {}
    for name, path in (("stage1", "stage1.py"), ("stage2", "stage2.py")):
        with open(path, "r", encoding="utf-8") as fh:
            budgets = {int(m) for m in re.findall(r"max_tokens=(\d+)", fh.read())}
        found[name] = budgets
    problems = []
    for name, expected in (("stage1", STAGE1_MAX_COMPLETION), ("stage2", STAGE2_MAX_COMPLETION)):
        if found[name] != {expected}:
            problems.append(f"{name}.py has max_tokens={sorted(found[name])}, "
                            f"this script assumes {expected}")
    return problems


def _tokens(text, chars_per_token):
    return len(text or "") / float(chars_per_token)


def _company_for(constituent):
    """The Contract B a deep dive would carry for this constituent (dataset origin, no fetch)."""
    return contracts.coerce_company_data(universe.to_seed_company(constituent))


def measure(constituents, *, chars_per_token=DEFAULT_CHARS_PER_TOKEN, sample=None,
            questions=core.MAX_QUESTIONS, turn_chars=TURN_CHARS):
    """Per-company token breakdown for ONE deep dive of `questions` Stage-1 turns.

    Input is split cached/uncached because the provider's context cache is a PREFIX cache: each
    Stage-1 turn resends the whole conversation, but everything up to the previous turn is a
    verbatim prefix and bills at the cache-hit rate. Only the newest question+answer pair is new.
    The two system prompts are constant across every call and every company, so after the very
    first call of a session they are always a hit.
    """
    floor = _measured_floor(chars_per_token)
    s1_sys = _tokens(getattr(stage1, "SYSTEM_PROMPT", ""), chars_per_token)
    s2_sys = _tokens(stage2.SYSTEM_PROMPT, chars_per_token)
    aq = floor["stage1"]                                    # one model question (JSON envelope)
    ua = turn_chars["user"] / float(chars_per_token)        # one user answer

    rows = []
    for c in constituents[:sample] if sample else constituents:
        company = _company_for(c)
        nq = {"narrowed_question": f"Is the ESG rating on {c.get('company')} stale?",
              "mandate": "risk", "sector": c.get("sector", "unknown"),
              "horizon": "near_term", "trail": []}
        s2_user = _tokens(
            stage2.build_user_message(nq, company, snippets=[], ai_summary=""), chars_per_token)

        # --- Stage 1: `questions` calls, prefix-cached ---
        cached = uncached = 0.0
        for turn in range(1, questions + 1):
            if turn == 1:
                cached += s1_sys          # system prompt: warm from the previous company
                uncached += ua            # the user's opening question
            else:
                cached += s1_sys + (turn - 1) * ua + (turn - 2) * aq   # the resent prefix
                uncached += aq + ua       # only the newest exchange is new
        # --- Stage 2: one call ---
        cached += s2_sys
        uncached += s2_user

        rows.append({
            "company_id": c.get("ticker", ""),
            "questions": questions,
            "calls": questions + 1,
            "cached_prompt_tokens": cached,
            "uncached_prompt_tokens": uncached,
            "prompt_tokens": cached + uncached,
            # Hard ceiling: every call returns its full max_tokens. Cannot be exceeded (bar a
            # retry), so it is the right number for bounding a prepaid balance.
            "completion_ceiling": float(questions * STAGE1_MAX_COMPLETION + STAGE2_MAX_COMPLETION),
            # Measured floor: the actual JSON each stage emits, sized off the VERIFIED fixtures on
            # disk. A real completion cannot be smaller than the payload it must contain. It can
            # be much larger — stage2.py budgets 4000 precisely because a reasoning model spends
            # tokens thinking BEFORE the JSON, and those bill as completion too. Nothing offline
            # can measure that thinking; only --live can. So this is a floor, never an estimate.
            # The gap between this floor and the ceiling above IS the thinking, and on this model
            # it is most of the bill — which is exactly why the two are reported separately.
            "completion_floor": float(questions * floor["stage1"] + floor["stage2"]),
        })
    return rows


def summarise(rows, run, *, price_in=None, price_out=None, price_cached=None,
              chars_per_token=DEFAULT_CHARS_PER_TOKEN):
    """Average the per-company rows and, if prices were SUPPLIED, price them.

    `price_cached` is the provider's context-cache-hit rate. Omit it and every input token is
    priced at the cache-miss rate — correct but pessimistic by roughly 8x, and labelled as such.
    """
    n = max(1, len(rows))
    cached = sum(r["cached_prompt_tokens"] for r in rows) / n
    uncached = sum(r["uncached_prompt_tokens"] for r in rows) / n
    ceiling = sum(r["completion_ceiling"] for r in rows) / n
    floor_out = sum(r["completion_floor"] for r in rows) / n
    signals_per_company = run["signal_count"] / max(1, run["company_count"])

    out = {
        "companies_measured": len(rows),
        "chars_per_token": chars_per_token,
        "questions": rows[0]["questions"] if rows else 0,
        "calls_per_dive": rows[0]["calls"] if rows else 0,
        "avg_cached_prompt_tokens": round(cached),
        "avg_uncached_prompt_tokens": round(uncached),
        "avg_prompt_tokens": round(cached + uncached),
        "cached_share": round(cached / max(1.0, cached + uncached), 3),
        "avg_completion_floor": round(floor_out),
        "avg_completion_ceiling": round(ceiling),
        "signals_per_company": round(signals_per_company, 2),
        "engine_tokens_per_company": 0,
        "price_in_per_1m": price_in,
        "price_out_per_1m": price_out,
        "price_cached_per_1m": price_cached,
        "priced_cache_aware": price_cached is not None,
        "usd_floor": None, "usd_ceiling": None,
        "usd_ceiling_with_retries": None, "usd_per_52_ceiling": None,
    }
    if price_in is not None and price_out is not None:
        # No cache price supplied -> price every input token at the miss rate. Pessimistic, never
        # optimistic: a cost model may overstate, but it must not quietly understate.
        cached_rate = price_cached if price_cached is not None else price_in
        usd_in = cached / 1e6 * cached_rate + uncached / 1e6 * price_in
        out["usd_floor"] = round(usd_in + floor_out / 1e6 * price_out, 6)
        out["usd_ceiling"] = round(usd_in + ceiling / 1e6 * price_out, 6)
        out["usd_ceiling_with_retries"] = round(out["usd_ceiling"] * RETRY_FACTOR, 6)
        out["usd_per_52_ceiling"] = round(out["usd_ceiling"] * 52, 4)
    return out


def _float_arg(argv, flag, env):
    if flag in argv:
        try:
            return float(argv[argv.index(flag) + 1])
        except (IndexError, ValueError):
            return None
    value = os.environ.get(env, "").strip()
    try:
        return float(value) if value else None
    except ValueError:
        return None


def live_completion_sample(constituents, *, chars_per_token=DEFAULT_CHARS_PER_TOKEN):
    """Measure REAL completion length for one dive against the live API.

    The completion term is the biggest cost driver and the only one nothing offline can pin down
    (reasoning tokens are emitted before the JSON and bill as completion). This narrows it — at
    the price of one real, billable dive. Raises rather than degrading: a cost tool that silently
    reports an estimate as a measurement is the exact failure this whole rewrite exists to fix.

    It does NOT resolve it. core.call_llm returns the assistant string, so what is measured here
    is what came back, not what was billed — and on a reasoning model those differ by about 10x.
    Making this exact means returning the API's `usage` object (completion_tokens counts the
    reasoning; prompt_cache_hit_tokens would also replace the 87-92% cache estimate with the
    real rate), which is a change to a frozen file. Until then: the ceiling is the honest number.
    """
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise RuntimeError("--live needs DEEPSEEK_API_KEY. Refusing to pass the offline estimate "
                           "off as a measurement.")
    c = constituents[0]
    company = _company_for(c)
    messages = [{"role": "user", "content": f"Is the ESG rating on {c.get('company')} stale?"}]
    _, s1_raw = stage1.ask_next(messages, 0, company=company)
    nq = {"narrowed_question": f"Is the ESG rating on {c.get('company')} stale?",
          "mandate": "risk", "sector": c.get("sector", "unknown"),
          "horizon": "near_term", "trail": []}
    s2_raw = core.call_llm([{"role": "user",
                             "content": stage2.build_user_message(nq, company, [], "")}],
                           stage2.SYSTEM_PROMPT, max_tokens=STAGE2_MAX_COMPLETION,
                           temperature=0.5, json_mode=True)
    return {"company": c.get("ticker", ""),
            "stage1_completion_tokens": round(_tokens(s1_raw, chars_per_token)),
            "stage2_completion_tokens": round(_tokens(s2_raw, chars_per_token)),
            "note": "Returned-string length only, and on a reasoning model that is not a near "
                    "miss — it is off by roughly an order of magnitude. Measured 19 Aug 2026 on "
                    "deepseek-v4-flash: a Stage-2 call capped at 2000 emitted ~2100 tokens of "
                    "reasoning and never reached its JSON, so real billed completion sits near "
                    "the CEILING column above, not near this number or the floor. Quote the "
                    "ceiling. Pinning it exactly needs the API usage object, which core.call_llm "
                    "does not return (frozen file — needs sign-off)."}


def main(argv):
    problems = _verify_budgets()
    if problems:
        print("REFUSING TO PRICE — this script has drifted from the code it prices:")
        for p in problems:
            print(f"  - {p}")
        print("Update the constants in llm_cost.py, then re-run.")
        return 2

    chars = _float_arg(argv, "--chars-per-token", "ESG_CHARS_PER_TOKEN") or DEFAULT_CHARS_PER_TOKEN
    price_in = _float_arg(argv, "--price-in", "ESG_LLM_PRICE_IN")
    price_out = _float_arg(argv, "--price-out", "ESG_LLM_PRICE_OUT")
    price_cached = _float_arg(argv, "--price-cached", "ESG_LLM_PRICE_CACHED")

    constituents = universe.constituents(universe.DEMO_FILE)
    run = engine.run_engine(constituents, metadata=company_metadata.load(), use_cache=False)
    floor = _measured_floor(chars)

    print("LLM cost per DEEP DIVE — prompts measured off the golden-set universe")
    print(f"  companies measured        {len(constituents)}")
    print(f"  chars/token assumed       {chars}")
    print(f"  completion floor sized    stage1 {floor['stage1_chars']:.0f} chars · "
          f"stage2 {floor['stage2_chars']:.0f} chars   (from fixtures/, sources excluded)")
    print(f"  max_tokens per call       stage1 {STAGE1_MAX_COMPLETION} · "
          f"stage2 {STAGE2_MAX_COMPLETION}   (verified against the call sites)")
    print(f"  engine tokens/company     0   (rule-based extraction — no LLM in the score path)")

    results = {}
    for name, questions, why in SCENARIOS:
        rows = measure(constituents, chars_per_token=chars, questions=questions)
        r = summarise(rows, run, price_in=price_in, price_out=price_out,
                      price_cached=price_cached, chars_per_token=chars)
        results[name] = r
        print(f"\n  [{name}] {questions} Stage-1 question(s) + Stage 2 = "
              f"{r['calls_per_dive']} calls — {why}")
        print(f"      prompt tokens        {r['avg_prompt_tokens']:,}"
              f"   ({r['avg_cached_prompt_tokens']:,} cacheable "
              f"= {r['cached_share'] * 100:.0f}%, {r['avg_uncached_prompt_tokens']:,} new)")
        print(f"      completion tokens    floor {r['avg_completion_floor']:,}"
              f" .. ceiling {r['avg_completion_ceiling']:,}")
        if r["usd_floor"] is not None:
            tag = "cache-aware" if r["priced_cache_aware"] else "NO cache price — all input at miss rate"
            print(f"      USD per dive         ${r['usd_floor']:.6f} .. ${r['usd_ceiling']:.6f}"
                  f"   ({tag})")
            print(f"      worst case w/ retry  ${r['usd_ceiling_with_retries']:.6f}"
                  f"   (both stages retry once on unparseable JSON)")

    if results["typical"]["usd_floor"] is None:
        print("\n  NO PRICE SUPPLIED — pass --price-in / --price-out (and --price-cached for the\n"
              "  context-cache rate), USD per 1M tokens, from the vendor's current price list.\n"
              "  This script will not guess a vendor's price.")
    elif price_cached is None:
        print("\n  NOTE: no --price-cached given, so ~88% of input is priced at the MISS rate.\n"
              "  Supply it for the real figure; the numbers above are an upper bound on input.")

    if "--live" in argv:
        try:
            print("\n  --live: measuring real completion length (this makes billable calls)…")
            sample = live_completion_sample(constituents, chars_per_token=chars)
            print(f"      {sample['company']}: stage1 {sample['stage1_completion_tokens']:,}"
                  f" · stage2 {sample['stage2_completion_tokens']:,} completion tokens")
            print(f"      {sample['note']}")
            results["live_sample"] = sample
        except Exception as exc:                      # noqa: BLE001 — reported, never swallowed
            print(f"      --live FAILED: {exc}")
            print("      The floor/ceiling range above still stands; it is simply not narrowed.")
            return 1

    if "--json" in argv:
        print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
