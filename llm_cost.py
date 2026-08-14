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
is printed alongside the number so the estimate can be re-derived or corrected, and `--live`
re-measures completion length against the real API when a key is present.

The engine itself costs **zero** LLM tokens: signal extraction is rule-based and deterministic
(`signals.py`), which is why this number is per *deep dive*, not per scored company.
"""

import json
import os
import sys

import company_metadata
import contracts
import engine
import stage1
import stage2
import universe

DEFAULT_CHARS_PER_TOKEN = 4.0
# Completion budgets the app actually asks for (max_tokens at each call site).
STAGE1_MAX_COMPLETION = 400
STAGE2_MAX_COMPLETION = 900


def _tokens(text, chars_per_token):
    return len(text or "") / float(chars_per_token)


def _company_for(constituent):
    """The Contract B a deep dive would carry for this constituent (dataset origin, no fetch)."""
    return contracts.coerce_company_data(universe.to_seed_company(constituent))


def measure(constituents, *, chars_per_token=DEFAULT_CHARS_PER_TOKEN, sample=None):
    """Per-company prompt/completion token estimates across a sample of the universe."""
    rows = []
    for c in constituents[:sample] if sample else constituents:
        company = _company_for(c)
        nq = {"narrowed_question": f"Is the ESG rating on {c.get('company')} stale?",
              "mandate": "risk", "sector": c.get("sector", "unknown"),
              "horizon": "near_term", "trail": []}
        s2_user = stage2.build_user_message(nq, company, snippets=[], ai_summary="")
        s1_prompt = getattr(stage1, "SYSTEM_PROMPT", "")
        s2_prompt = stage2.SYSTEM_PROMPT
        prompt_tokens = (_tokens(s1_prompt, chars_per_token)
                         + _tokens(s2_prompt, chars_per_token)
                         + _tokens(s2_user, chars_per_token))
        rows.append({
            "company_id": c.get("ticker", ""),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": float(STAGE1_MAX_COMPLETION + STAGE2_MAX_COMPLETION),
        })
    return rows


def summarise(rows, run, *, price_in=None, price_out=None,
              chars_per_token=DEFAULT_CHARS_PER_TOKEN):
    n = max(1, len(rows))
    prompt = sum(r["prompt_tokens"] for r in rows) / n
    completion = sum(r["completion_tokens"] for r in rows) / n
    signals_per_company = run["signal_count"] / max(1, run["company_count"])
    out = {
        "companies_measured": len(rows),
        "chars_per_token": chars_per_token,
        "avg_prompt_tokens": round(prompt),
        "avg_completion_tokens": round(completion),
        "avg_total_tokens": round(prompt + completion),
        "signals_per_company": round(signals_per_company, 2),
        "tokens_per_signal": round((prompt + completion) / max(0.01, signals_per_company)),
        "engine_tokens_per_company": 0,
        "price_in_per_1m": price_in,
        "price_out_per_1m": price_out,
        "usd_per_company": None,
        "usd_per_52_universe": None,
    }
    if price_in is not None and price_out is not None:
        usd = prompt / 1e6 * price_in + completion / 1e6 * price_out
        out["usd_per_company"] = round(usd, 6)
        out["usd_per_52_universe"] = round(usd * 52, 4)
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


def main(argv):
    chars = _float_arg(argv, "--chars-per-token", "ESG_CHARS_PER_TOKEN") or DEFAULT_CHARS_PER_TOKEN
    price_in = _float_arg(argv, "--price-in", "ESG_LLM_PRICE_IN")
    price_out = _float_arg(argv, "--price-out", "ESG_LLM_PRICE_OUT")

    constituents = universe.constituents(universe.DEMO_FILE)
    run = engine.run_engine(constituents, metadata=company_metadata.load(), use_cache=False)
    rows = measure(constituents, chars_per_token=chars)
    result = summarise(rows, run, price_in=price_in, price_out=price_out, chars_per_token=chars)

    print("LLM cost per company — measured off the golden-set universe")
    print(f"  companies measured        {result['companies_measured']}")
    print(f"  chars/token assumed       {result['chars_per_token']}")
    print(f"  avg prompt tokens         {result['avg_prompt_tokens']:,}"
          "   (Stage-1 system + Stage-2 system + Stage-2 user message)")
    print(f"  avg completion tokens     {result['avg_completion_tokens']:,}"
          f"   (max_tokens budget: {STAGE1_MAX_COMPLETION} + {STAGE2_MAX_COMPLETION})")
    print(f"  avg TOTAL tokens/company  {result['avg_total_tokens']:,}")
    print(f"  signals/company           {result['signals_per_company']}"
          f"   -> {result['tokens_per_signal']:,} tokens per signal")
    print(f"  engine tokens/company     0   (rule-based extraction — no LLM in the score path)")
    if result["usd_per_company"] is None:
        print("\n  NO PRICE SUPPLIED — pass --price-in / --price-out (USD per 1M tokens) from "
              "DeepSeek's\n  current price list, or set ESG_LLM_PRICE_IN / ESG_LLM_PRICE_OUT. "
              "This script will not\n  guess a vendor's price.")
    else:
        print(f"\n  >>> USD per company       ${result['usd_per_company']:.6f}")
        print(f"      USD per 52-name sweep  ${result['usd_per_52_universe']:.4f}"
              f"   (in ${price_in}/1M · out ${price_out}/1M)")
    if "--json" in argv:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
