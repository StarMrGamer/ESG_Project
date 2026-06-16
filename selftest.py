"""
selftest.py — offline end-to-end check for the relay. No network, no API key.
=============================================================================
Proves the contracts and the wiring without calling DeepSeek:
  1. The on-disk batons (data + fixtures) conform to their contracts.
  2. Stage 1's builder turns a trail into a valid NarrowedQuestion (Contract A).
  3. Stage 2's chain (core.call_llm monkeypatched to return the fixture) yields a valid
     Stage2Answer (Contract C) that actually cites the Layer B AI gap + the MAS catalyst.

    python selftest.py
"""

import json
import os

import core
import contracts
import stage1
import stage2

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return json.load(f)


def test_on_disk_contracts():
    contracts.validate_company_data(_load("data/hero_company.json"))
    contracts.validate_narrowed_question(_load("fixtures/narrowed_question.json"))
    contracts.validate_stage2_answer(_load("fixtures/stage2_answer.json"))


def test_stage1_builder():
    final_env = {
        "type": "narrowed",
        "axis": None,
        "text": "Is the bank's undisclosed AI-governance gap a near-term capital risk?",
        "mandate": "risk",
        "sector": "Financials — Banks",
        "horizon": "near_term",
        "done": True,
    }
    trail = [
        {"axis": "mandate", "type": "question", "text": "Risk, return, or compliance?"},
        final_env,
    ]
    nq = stage1.build_narrowed_question(trail, final_env)
    contracts.validate_narrowed_question(nq)
    assert nq["mandate"] == "risk", nq
    assert nq["horizon"] == "near_term", nq
    assert len(nq["trail"]) == 2, nq


def test_stage2_chain(monkeypatch_return):
    """Run stage2.reason with the LLM mocked to return the fixture answer."""
    company = _load("data/hero_company.json")
    narrowed = _load("fixtures/narrowed_question.json")
    fixture_answer = _load("fixtures/stage2_answer.json")

    original = core.call_llm
    core.call_llm = lambda *a, **k: monkeypatch_return  # no network
    try:
        answer = stage2.reason(narrowed, company)
    finally:
        core.call_llm = original

    contracts.validate_stage2_answer(answer)
    contract = {k: answer[k] for k in contracts.STAGE2_ANSWER_KEYS}  # drop debug-only keys
    assert contract == fixture_answer, "coerced answer should round-trip the fixture exactly"
    assert answer["_parse_failed"] is False, "fixture parses cleanly"
    # the differentiator must survive the chain: Layer B AI gap + MAS catalyst.
    blob = json.dumps(contract)
    assert "+340% YoY" in blob, "must cite the AI-governance hiring velocity"
    assert "MAS" in blob, "must cite the MAS near-term catalyst"
    assert "Medium Risk" in answer["what_rating_sees"], "must name the stale Layer A view"


def test_coerce_fills_unknown():
    out = contracts.coerce_stage2_answer({"question_to_ask": "Q?"})
    assert out["what_we_see"] == "unknown", out  # missing -> explicit unknown, never invented
    assert set(out) == set(contracts.STAGE2_ANSWER_KEYS), out


def main():
    raw_fixture = open(os.path.join(ROOT, "fixtures/stage2_answer.json"), encoding="utf-8").read()
    checks = [
        ("on-disk contracts", lambda: test_on_disk_contracts()),
        ("stage 1 builder -> Contract A", lambda: test_stage1_builder()),
        ("stage 2 chain -> Contract C (mocked LLM)", lambda: test_stage2_chain(raw_fixture)),
        ("coerce fills 'unknown'", lambda: test_coerce_fills_unknown()),
    ]
    failures = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001 — selftest reports any failure
            failures += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    if failures:
        print(f"FAILED — {failures} check(s) failed.")
        raise SystemExit(1)
    print("OK — all checks passed (relay wiring + contracts verified, no network used).")


if __name__ == "__main__":
    main()
