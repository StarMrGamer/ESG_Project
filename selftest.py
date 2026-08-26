"""
selftest.py — offline end-to-end check for the relay. No network, no API key.
=============================================================================
Proves the contracts and the wiring without calling DeepSeek OR the network:
  1. The on-disk batons (data + fixtures) conform to their contracts.
  2. Stage 1's builder turns a trail into a valid NarrowedQuestion (Contract A).
  3. Stage 2's chain (core.call_llm monkeypatched to return the fixture, RAG bypassed) yields
     a valid Stage2Answer (Contract C) that cites the Layer B AI gap + the MAS catalyst.
  4. The RAG retriever (core.http_get monkeypatched) fetches DuckDuckGo results + TF-IDF-ranks,
     and degrades gracefully to "offline" when the network is down.

    python selftest.py
"""

import json
import os
import sys

import core
import contracts
import datasource
import rag
import stage1
import stage2
import stage3
import universe
import metrics

# A canned DuckDuckGo HTML results payload so the RAG tests need no network. The result links
# are DDG's '//duckduckgo.com/l/?uddg=<encoded real url>' redirects (the parser unwraps them).
_FAKE_DDG_HTML = """<html><body>
<div class="result results_links">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fmas-ai&amp;rut=a">MAS finalises AI risk management guidelines for banks</a>
  <a class="result__snippet" href="https://example.com/mas-ai">Singapore regulator MAS sets AI governance disclosure rules for financial institutions</a>
</div>
<div class="result results_links">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fsport&amp;rut=b">Local football derby ends two one</a>
  <a class="result__snippet" href="https://example.com/sport">A football match result unrelated to ESG or governance</a>
</div>
</body></html>"""

ROOT = os.path.dirname(os.path.abspath(__file__))
# `esg_data` / `esg_scoring` are the pre-rewrite July modules. Nothing in the app imports
# them any more, so they live in legacy/ — kept only because these tests still cover them.
# Deleting them is a decision, not a tidy-up.
sys.path.insert(0, os.path.join(ROOT, "legacy"))


class Skipped(Exception):
    """A check that could not run (an optional dependency is absent).

    Raised rather than `return`ed so the run reports SKIP instead of a green PASS — a check
    that did not execute must never read as a check that succeeded."""


def _load(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return json.load(f)


def test_on_disk_contracts():
    contracts.validate_company_data(_load("data/hero_company.json"))  # the offline/sample fixture
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


def test_stage1_suggestions():
    """Dynamic quick-reply suggestions normalise to <=3 short, de-duped strings."""
    env = stage1._envelope_defaults({
        "type": "question", "axis": "mandate",
        "suggested_replies": ["Risk", "  ", "Risk", {"text": "Return"}, "X", "Y", "Z"],
    })
    assert env["suggested_replies"] == ["Risk", "Return", "X"], env["suggested_replies"]
    bad = stage1._envelope_defaults({"type": "question", "suggested_replies": None})
    assert bad["suggested_replies"] == [], bad  # non-list -> empty, never crashes


def test_stage2_chain(monkeypatch_return):
    """Run stage2.reason with the LLM mocked to return the fixture answer."""
    company = _load("data/hero_company.json")
    narrowed = _load("fixtures/narrowed_question.json")
    fixture_answer = _load("fixtures/stage2_answer.json")

    original = core.call_llm
    core.call_llm = lambda *a, **k: monkeypatch_return  # no LLM network
    try:
        # context injected (RAG bypassed) so the test never touches the network.
        answer = stage2.reason(
            narrowed, company,
            context={"snippets": [], "status": "disabled", "doc_count": 0, "query": ""},
        )
    finally:
        core.call_llm = original

    contracts.validate_stage2_answer(answer)
    contract = {k: answer[k] for k in contracts.STAGE2_ANSWER_KEYS}  # drop debug-only keys
    assert contract == fixture_answer, "coerced answer should round-trip the fixture exactly"
    assert answer["_parse_failed"] is False, "fixture parses cleanly"
    assert answer["sources"] == [], "no snippets injected -> no sources (never fabricated)"
    assert isinstance(answer["reasoning"], list) and answer["reasoning"], "CoT must survive"
    # the differentiator must survive the chain: Layer B AI gap + MAS catalyst.
    blob = json.dumps(contract)
    assert "+340% YoY" in blob, "must cite the AI-governance hiring velocity"
    assert "MAS" in blob, "must cite the MAS near-term catalyst"
    assert "Medium Risk" in answer["what_rating_sees"], "must name the stale Layer A view"


def test_rag_retrieval():
    """RAG fetch (DuckDuckGo) + TF-IDF rank, with core.http_get mocked (no network)."""
    original = core.http_get
    core.http_get = lambda *a, **k: _FAKE_DDG_HTML
    try:
        docs, status, error = rag.fetch_documents("MAS AI governance banks", use_cache=False)
    finally:
        core.http_get = original
    assert status == "live" and len(docs) >= 2 and error is None, (status, docs, error)
    # the '//duckduckgo.com/l/?uddg=' redirect must be unwrapped to the real URL.
    assert docs[0]["url"] == "https://example.com/mas-ai", docs[0]
    snippets = rag.retrieve("MAS AI governance disclosure for banks", docs, k=2)
    assert snippets, "TF-IDF should return at least one ranked snippet"
    # the relevant (MAS) item must out-rank the unrelated football item.
    assert "MAS" in snippets[0]["snippet"], snippets[0]
    assert snippets[0]["url"] == "https://example.com/mas-ai", snippets[0]


def test_rag_gather_context_shape():
    """gather_context returns the new shape incl. ai_summary; a non-JSON instant-answer
    response degrades the AI summary to None without breaking the search snippets."""
    original = core.http_get
    core.http_get = lambda *a, **k: _FAKE_DDG_HTML  # search parses; instant-answer JSON fails
    try:
        ctx = rag.gather_context("MAS AI governance banks", k=2, use_cache=False)
    finally:
        core.http_get = original
    assert ctx["status"] == "live" and ctx["snippets"], ctx
    assert ctx["ai_summary"] is None, ctx["ai_summary"]  # HTML isn't valid IA JSON -> graceful
    assert set(ctx) >= {"snippets", "ai_summary", "status", "doc_count", "query"}, ctx


def test_rag_offline_graceful():
    """A dead network degrades to ([], 'offline') — never an exception."""
    original = core.http_get

    def boom(*a, **k):
        raise core.FetchError("simulated network failure")

    core.http_get = boom
    try:
        docs, status, error = rag.fetch_documents("anything", use_cache=False)
    finally:
        core.http_get = original
    assert docs == [] and status == "offline" and error, (docs, status, error)


def test_contract_c_coercion():
    """Contract C tolerates a messy model dict: reasoning/sources normalise to clean lists."""
    out = contracts.coerce_stage2_answer({
        "question_to_ask": "Q?",
        "reasoning": ["step one", "  ", {"step": "step two"}, ""],
        "sources": [{"title": "T", "url": "https://e.com"}, {"junk": 1}, "nope"],
    })
    assert out["reasoning"] == ["step one", "step two"], out["reasoning"]
    assert out["sources"] == [{"title": "T", "url": "https://e.com"}], out["sources"]
    assert out["what_we_see"] == "unknown", out  # missing text key -> explicit unknown


def test_coerce_fills_unknown():
    out = contracts.coerce_stage2_answer({"question_to_ask": "Q?"})
    assert out["what_we_see"] == "unknown", out  # missing -> explicit unknown, never invented
    assert set(out) == set(contracts.STAGE2_ANSWER_KEYS), out


def test_company_data_coercion():
    """coerce_company_data builds the full nested shape, filling gaps with 'unknown'."""
    out = contracts.coerce_company_data({"company": "Acme", "sector": "Tech"}, origin="live")
    contracts.validate_company_data(out)  # full shape present
    assert out["company"] == "Acme" and out["_origin"] == "live", out
    assert out["layer_a"]["esg_score_static"] == "unknown", out  # missing -> unknown
    assert out["layer_b"]["momentum"]["G"]["direction"] == "unknown", out
    assert out["layer_b"]["near_term_catalyst"] == "unknown", out


def test_upload_json_authoritative():
    """A .json upload is used as-is (coerced), no LLM involved."""
    payload = json.dumps({"company": "MyCo", "ticker": "X:MYCO", "sector": "Energy",
                          "layer_b": {"near_term_catalyst": "Some 2026 rule"}})
    company, meta = datasource.load_upload("mine.json", payload.encode("utf-8"))
    contracts.validate_company_data(company)
    assert meta["mode"] == "json" and company["_origin"] == "upload", (meta, company["_origin"])
    assert company["company"] == "MyCo", company
    assert company["layer_b"]["near_term_catalyst"] == "Some 2026 rule", company


def test_live_company_grounded(monkeypatch_extract):
    """build_live_company: RAG mocked + LLM mocked → grounded Contract B with provenance."""
    orig_gather, orig_fetch, orig_llm = rag.gather_context, rag.fetch_documents, core.call_llm
    rag.gather_context = lambda *a, **k: {
        "snippets": [{"title": "MAS AI rules", "url": "https://e.com/mas", "snippet": "MAS AI governance"}],
        "ai_summary": None, "status": "live", "doc_count": 1, "query": "x",
    }
    rag.fetch_documents = lambda *a, **k: ([], "offline", None)  # ESG-rating fetch: offline (no net)
    core.call_llm = lambda *a, **k: monkeypatch_extract
    try:
        company, meta = datasource.build_live_company("I want to invest in Nvidia")
    finally:
        rag.gather_context, rag.fetch_documents, core.call_llm = orig_gather, orig_fetch, orig_llm
    contracts.validate_company_data(company)
    assert company["_origin"] == "live" and meta["status"] == "live", (company["_origin"], meta)
    assert company["company"] == "NVIDIA", company
    assert company["_sources"] == [{"title": "MAS AI rules", "url": "https://e.com/mas"}], company["_sources"]
    # the extractor's "unknown" must survive (never silently invented)
    assert company["layer_a"]["esg_score_static"] == "unknown", company


def test_universe_loads_and_resolves():
    """The ASEAN base DB loads, filters, and maps chat phrases onto real constituents."""
    uni = universe.load_universe()
    cons = uni["constituents"]
    assert len(cons) >= 5, len(cons)
    assert uni["benchmark"] and "constituents" not in uni["benchmark"], uni["benchmark"]
    # every constituent carries the country/exchange the ASEAN-scoped fetch needs
    assert all(c["country"] != "unknown" and c["exchange"] != "unknown" for c in cons), cons[:3]
    # resolve maps names / tickers / parenthetical aliases; nonsense -> None (stays in-universe)
    dbs = universe.resolve("DBS")
    assert dbs and dbs["ticker"].startswith("SGX"), dbs
    # Short-form aliases must survive CGSI's terser legal names ("Bank Central Asia", not
    # "Bank Central Asia (BCA)") — the basket carries an `aliases` list for exactly this.
    assert universe.resolve("BCA")["country"] == "Indonesia", universe.resolve("BCA")
    assert universe.resolve("Maybank")["ticker"] == "KLSE:MAY", universe.resolve("Maybank")
    assert universe.resolve("SET:PTT")["company"] == "PTT", universe.resolve("SET:PTT")
    assert universe.resolve("totally fake nonexistent xyz") is None
    sg = universe.filter_constituents(country="Singapore")
    assert sg and all(c["country"] == "Singapore" for c in sg), sg
    assert universe.scope_terms(dbs) == "Singapore SGX ASEAN", universe.scope_terms(dbs)


def test_snapshot_shape():
    """snapshot_from_company turns a Contract B into compact card data (no network/LLM)."""
    company = _load("data/hero_company.json")
    company["_origin"] = "sample"
    snap = datasource.snapshot_from_company(company)
    assert snap["band"] == "Medium Risk" and snap["rating_num"] == "22.4", snap
    assert snap["arrows"]["E"] == "▲" and snap["arrows"]["S"] == "—", snap  # improving / flat
    assert snap["red_flags"] == 2, snap                      # the two illustrative sample red flags
    assert 0 < snap["coverage"] <= snap["coverage_total"] == 10, snap


def test_constituent_build_grounded(monkeypatch_extract):
    """build_company_from_constituent: identity is AUTHORITATIVE (base DB wins over the extractor),
    retrieval mocked, country/exchange stamped for ASEAN scoping."""
    c = {"company": "Kasikornbank", "ticker": "SET:KBANK", "exchange": "SET",
         "country": "Thailand", "sector": "Financials — Banks"}
    orig_gather, orig_fetch, orig_llm = rag.gather_context, rag.fetch_documents, core.call_llm
    rag.gather_context = lambda *a, **k: {
        "snippets": [{"title": "KBank ESG", "url": "https://e.com/k", "snippet": "ESG governance"}],
        "ai_summary": None, "status": "live", "doc_count": 1, "query": "x"}
    rag.fetch_documents = lambda *a, **k: ([], "offline", None)
    core.call_llm = lambda *a, **k: monkeypatch_extract     # returns a WRONG identity (NVIDIA)
    try:
        company, meta = datasource.build_company_from_constituent(c)
    finally:
        rag.gather_context, rag.fetch_documents, core.call_llm = orig_gather, orig_fetch, orig_llm
    contracts.validate_company_data(company)
    assert company["company"] == "Kasikornbank", company["company"]   # base DB overrides extractor
    assert company["ticker"] == "SET:KBANK", company["ticker"]
    assert company["_country"] == "Thailand" and company["_exchange"] == "SET", company
    assert company["_origin"] == "live", company


def test_metrics_aggregates():
    """metrics.* over the demo universe: avg ESG per industry, pillar momentum, hidden winners,
    classification, signals — the numbers behind the command center (0-100, higher=better)."""
    cons = universe.constituents(universe.DEMO_FILE)
    assert len(cons) == 36, len(cons)
    banks = [c for c in cons if c["sector"] == "Financials — Banks"]
    assert len(banks) == 9, len(banks)
    avg, n = metrics.average_esg(banks)
    assert avg is not None and 55 <= avg <= 64 and n == 9, (avg, n)   # 0-100 higher=better; ~59.5
    pillars = {p["key"]: p for p in metrics.pillar_momentum(banks)}
    assert pillars["digital_ai"]["fast"] is True, pillars["digital_ai"]   # the orange riser card
    assert all(pillars[k]["value"] is not None
               for k in ("environment", "social", "governance", "digital_ai")), pillars
    hw, peer, hn = metrics.hidden_winners(banks, top_n=5)
    assert len(hw) == 5, hw
    assert hw == sorted(hw, key=lambda r: r["value"], reverse=True), hw   # ranked desc by signal
    assert peer == avg and hn == n, (peer, avg, hn, n)                    # peer avg == set average
    labels = {metrics.classify(c)["label"] for c in banks}
    assert labels <= {"HIDDEN WINNER", "IN LINE", "WATCH — GAP RISK", "AWAITING DATA"}, labels
    assert "HIDDEN WINNER" in labels, labels                             # the radar surfaces winners
    demo = next(c for c in banks if c["company"] == "DemoBank")
    assert any(s["label"] == "AI hiring surge" for s in metrics.live_signals(demo)), demo
    # filtering to a different industry recomputes the average (the user's key requirement)
    energy = [c for c in cons if c["sector"].startswith("Energy")]
    eavg, _ = metrics.average_esg(energy)
    assert eavg is not None and eavg != avg, (eavg, avg)


def test_metrics_graceful():
    """No numeric data → every metric degrades to None/[] (the real starter universe path)."""
    bare = [{"company": "X", "ticker": "T:X", "sector": "S"}]
    assert metrics.has_numbers(bare) is False
    assert metrics.average_esg(bare) == (None, 0)
    assert all(p["value"] is None for p in metrics.pillar_momentum(bare))
    assert metrics.hidden_winners(bare)[0] == []
    assert metrics.classify(bare[0])["label"] == "AWAITING DATA"
    assert metrics.live_signals(bare[0]) == []
    assert metrics.num("+12%") == 12.0 and metrics.num("−2%") == -2.0 and metrics.num("x") is None


def test_company_from_numeric():
    """company_from_numeric maps a constituent's numbers -> a valid Contract B (no network/LLM),
    so the chatbot can run the relay on demo / pre-scored data."""
    c = {"company": "DemoBank", "ticker": "SGX:DEMO", "sector": "Financials — Banks",
         "country": "Singapore", "exchange": "SGX", "esg_score": 22.4, "esg_as_of": "2023",
         "momentum": {"environment": 18, "social": 0, "governance": -5, "digital_ai": 28},
         "live_signals": {"ai_hiring_surge": "+340%", "board_ai_policy": True, "controversy_flags": 0}}
    comp = datasource.company_from_numeric(c, origin="sample")
    contracts.validate_company_data(comp)
    assert comp["company"] == "DemoBank" and comp["_origin"] == "sample", comp
    assert comp["_country"] == "Singapore", comp
    mom = comp["layer_b"]["momentum"]
    assert mom["E"]["direction"] == "improving", mom        # +18 -> improving
    assert mom["S"]["direction"] == "flat", mom             # 0 -> flat
    assert mom["G"]["direction"] == "declining", mom        # -5 -> declining
    assert "340" in comp["layer_b"]["digital_ai_signal"]["ai_governance_hiring_velocity"], comp
    assert comp["layer_a"]["esg_score_static"] == "22.4", comp["layer_a"]


def test_evidence_mode():
    """metrics.parse_evidence extracts ONLY credentials the text cites (grounded, no invention),
    and the evidence-mode aggregates work over the real universe."""
    p = metrics.parse_evidence("MSCI ESG AA; DJSI World member; CDP A List; FTSE4Good ASEAN 5", "high")
    assert p["rating"] == "AA", p
    labels = {c["label"] for c in p["credentials"]}
    assert {"MSCI ESG", "DJSI", "CDP", "FTSE4Good"} <= labels, labels
    assert p["score"] > 0, p
    # a basis naming NO recognised rating -> no fabricated credentials, no rating
    p2 = metrics.parse_evidence("Generally seen as a responsible operator in its market.", "low")
    assert p2["credentials"] == [] and p2["rating"] is None, p2
    # over the real universe (every name has esg_basis): leadership aggregates are sane
    cons = universe.constituents(universe.UNIVERSE_FILE)
    if any(c.get("esg_basis") for c in cons):
        avg, nn = metrics.evidence_average(cons)
        assert avg is not None and nn >= 1 and 0 <= avg <= 100, (avg, nn)
        cov = metrics.credential_coverage(cons)
        assert len(cov) == 4 and all(0 <= (c["pct"] or 0) <= 100 for c in cov), cov
        lead = metrics.evidence_leaders(cons, top_n=3)
        assert lead and lead[0]["value"] >= lead[-1]["value"], lead
        assert metrics.classify_evidence(cons[0])["label"] in (
            "ESG LEADER", "STRONG IMPROVER", "ESTABLISHED", "EMERGING", "AWAITING DATA")


# --------------------------------------------------------------------------- #
#  REGRESSION TESTS — added 2026-06-29 for the audit fix-pass (each reproduces a
#  real bug found in the codebase audit, then guards it against regression).
# --------------------------------------------------------------------------- #
def test_msci_rating_extraction():
    """parse_evidence must read the MSCI letter grade GROUNDED in the real esg_basis text:
    the post-upgrade rating in 'X->Y'/'to Y' phrasing, and NEVER the English article 'a'."""
    pe = lambda b: metrics.parse_evidence(b)["rating"]
    # upgrade phrasing — the POST-upgrade rating wins, not the stale pre-upgrade one
    assert pe("MSCI ESG rating upgraded BBB->A (announced May)") == "A"          # Sunway / BRI
    assert pe("MSCI upgrading BB->BBB and Sustainalytics ESG") == "BBB"          # Chandra Asri
    assert pe("MSCI upgrade from 'B' to 'BB', a clear documented path") == "BB"  # Manila Water
    assert pe("MSCI ESG rating upgraded to 'BBB' (from 'BB')") == "BBB"          # PLDT
    # multi-hop trajectory — the CURRENT rating is the LAST hop, not the first
    assert pe("MSCI ESG rating on an upward path off a 2023 baseline (BBB -> A -> AA)") == "AA"  # Tenaga
    # the English article 'a' must NOT be misread as an 'A' rating when NO grade is cited
    assert pe("MSCI ESG profile improving on a documented upward path") is None
    # plain / quoted ratings still parse correctly (no regression)
    assert pe("MSCI ESG 'AA' (Leader)") == "AA"                                  # UOB
    assert pe("MSCI ESG AAA since 2020 — a clear leader") == "AAA"               # Keppel
    assert pe("MSCI ESG 'A' (Jan 2022)") == "A"                                  # Wilmar
    assert pe("MSCI 'A' rating and an S&P Global score") == "A"                  # BCA


def test_momentum_series_single_point():
    """momentum_series(points=1) must not raise ZeroDivisionError."""
    cons = universe.constituents(universe.DEMO_FILE)
    banks = [c for c in cons if c["sector"] == "Financials — Banks"]
    series = metrics.momentum_series(banks, points=1)  # must not raise
    assert all(len(v) == 1 for v in series.values()), series


def test_metrics_new_flag_param():
    """is_new comes from a passed new_tickers set, not a cached-dict mutation (kills the leak)."""
    cons = universe.constituents(universe.DEMO_FILE)
    banks = [c for c in cons if c["sector"] == "Financials — Banks"]
    hw, _, _ = metrics.hidden_winners(banks, top_n=5)
    assert all(r["is_new"] is False for r in hw), hw  # no mutation -> nothing 'new' by default
    target = hw[0]["ticker"]
    hw2, _, _ = metrics.hidden_winners(banks, top_n=5, new_tickers={target})
    assert any(r["ticker"] == target and r["is_new"] for r in hw2), hw2
    real = universe.constituents(universe.UNIVERSE_FILE)
    lead0 = metrics.evidence_leaders(real, top_n=3)
    if lead0:
        tgt = lead0[0]["ticker"]
        lead1 = metrics.evidence_leaders(real, top_n=3, new_tickers={tgt})
        assert any(r["ticker"] == tgt and r["is_new"] for r in lead1), lead1


def test_snapshot_numeric_score():
    """snapshot_from_company must not crash when esg_score_static is numeric (uploaded JSON)."""
    company = {"layer_a": {"esg_score_static": 22.4, "as_of_date": "2023"},
               "layer_b": {"momentum": {"E": {}, "S": {}, "G": {}}}}
    snap = datasource.snapshot_from_company(company)  # must not raise TypeError
    assert snap["band"] == "Medium Risk", snap
    assert snap["rating_num"] == "22.4", snap


def test_upload_nonobject_json_rejected():
    """A .json upload that is valid JSON but NOT an object raises a clean ValueError (not a crash)."""
    for payload in ("[1, 2, 3]", "42", '"hello"', "null"):
        try:
            datasource.load_upload("x.json", payload.encode("utf-8"))
        except ValueError:
            continue  # expected
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"{payload!r} raised {type(e).__name__}, want ValueError") from e
        raise AssertionError(f"{payload!r} should have raised ValueError")


def test_company_data_coercion_wrong_types():
    """coerce_company_data must degrade wrong-typed nested fields to 'unknown', never crash."""
    out = contracts.coerce_company_data(
        {"company": "X", "layer_a": "22.4 medium",          # string where dict expected
         "layer_b": {"momentum": {"E": "improving"}}},      # string where momentum-dict expected
        origin="upload")
    contracts.validate_company_data(out)
    assert out["layer_a"]["esg_score_static"] == "unknown", out["layer_a"]
    assert out["layer_b"]["momentum"]["E"]["direction"] == "unknown", out["layer_b"]["momentum"]
    # a momentum that is a list (not a dict) must also coerce, not crash
    out2 = contracts.coerce_company_data({"layer_b": {"momentum": ["E", "S", "G"]}}, origin="upload")
    contracts.validate_company_data(out2)


def test_universe_nondict_json_graceful():
    """A valid-but-non-dict/non-list universe file degrades to an empty universe, never crashes."""
    import tempfile
    for payload in ("42", "null", '"foo"', "true"):
        fd, p = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        try:
            uni = universe.load_universe(p)  # must not raise AttributeError
            assert uni["constituents"] == [], (payload, uni)
        finally:
            os.remove(p)


def test_universe_accessors_dont_leak():
    """get()/resolve() must return copies so a caller mutating the result can't poison the cache."""
    c1 = universe.resolve("DBS")
    assert c1, "DBS should resolve"
    c1["_new"] = True
    c2 = universe.resolve("DBS")
    assert "_new" not in c2, "resolve() leaked a mutation into the shared cache"
    g1 = universe.get(c1["ticker"])
    g1["_zzz"] = 1
    g2 = universe.get(c1["ticker"])
    assert "_zzz" not in g2, "get() leaked a mutation into the shared cache"


def test_ddg_instant_nonobject_graceful():
    """A valid-JSON-but-non-object instant-answer payload degrades to None, never raises."""
    original = core.http_get
    core.http_get = lambda *a, **k: "[1, 2, 3]"  # valid JSON, not an object
    try:
        assert rag._fetch_ddg_instant("anything") is None
    finally:
        core.http_get = original


def test_cache_read_nonobject_graceful():
    """A cache file containing valid non-object JSON degrades to None, never raises."""
    key = "selftest-nonobject-cache-key"
    p = rag._cache_path(key)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("[1, 2, 3]")
    try:
        assert rag._cache_read(key) is None
    finally:
        os.remove(p)


def test_envelope_axis_coercion():
    """A malformed LLM axis (list/dict) is coerced to None so hashable lookups never crash."""
    assert stage1._envelope_defaults({"axis": ["materiality"], "type": "question"})["axis"] is None
    assert stage1._envelope_defaults({"axis": {"k": 1}})["axis"] is None
    assert stage1._envelope_defaults({"axis": "mandate"})["axis"] == "mandate"  # valid str preserved
    badge = stage1._axis_badge(stage1._envelope_defaults({"axis": ["x"], "type": "question"}))
    assert isinstance(badge, str) and badge, badge  # the hashable lookup must not raise


def test_parse_json_robust():
    """parse_json survives trailing prose with a brace, and never corrupts fences inside values."""
    # trailing prose containing a '}' must not defeat the parse
    assert core.parse_json('{"a": 1}. Note about {curly} braces.') == {"a": 1}
    # a code fence inside a string VALUE must survive intact (not stripped to corruption)
    out = core.parse_json('Here you go: {"note": "see ```json fenced``` block"} thanks')
    assert out == {"note": "see ```json fenced``` block"}, out
    # the normal fenced-block case still parses
    assert core.parse_json('```json\n{"x": 2}\n```') == {"x": 2}


def test_env_float_guarded():
    """core._env_float never lets a non-numeric env var crash import — it falls back to default."""
    os.environ["ESG_SELFTEST_TMO"] = "8s"
    try:
        assert core._env_float("ESG_SELFTEST_TMO", 10.0) == 10.0  # non-numeric -> default
        os.environ["ESG_SELFTEST_TMO"] = "7.5"
        assert core._env_float("ESG_SELFTEST_TMO", 10.0) == 7.5   # numeric -> parsed
    finally:
        os.environ.pop("ESG_SELFTEST_TMO", None)
    assert core._env_float("ESG_SELFTEST_TMO", 10.0) == 10.0      # missing -> default


def test_card_md_gates_unknown_signals():
    """stage3._card_md must NOT emit a pillar-signals section that is just rows of 'unknown'."""
    answer = {"competes_summary": "x", "question_to_ask": "q", "what_rating_sees": "r",
              "what_we_see": "w", "check_before_monday": "c", "reasoning": [], "sources": []}
    sparse = contracts.coerce_company_data({"company": "Sparse Co"}, origin="live")  # all 'unknown'
    md = stage3._card_md(answer, sparse)
    assert "ESG pillar signals" not in md, "must not render an all-unknown pillar section"
    assert "- **E**: unknown" not in md and "hiring velocity**: unknown" not in md, md
    # but a company WITH real momentum still gets the section
    rich = contracts.coerce_company_data(
        {"company": "Rich Co", "layer_b": {"momentum": {"E": {"direction": "improving", "magnitude": "+8%"}}}},
        origin="live")
    md2 = stage3._card_md(answer, rich)
    assert "ESG pillar signals" in md2 and "improving" in md2, md2


def test_board_ai_policy_tristate():
    """[3.13] board_ai_policy supports Yes / No / Partial (was boolean-only)."""
    def pol(v):
        rows = metrics.live_signals({"live_signals": {"board_ai_policy": v}})
        return next(r["value"] for r in rows if r["label"] == "Board AI policy")
    assert pol(True) == "Yes", pol(True)
    assert pol(False) == "No", pol(False)
    assert pol("partial") == "Partial", pol("partial")
    assert pol("Partial") == "Partial"  # case-insensitive


def test_universe_banner():
    """[1.9] banner = '<quarter> · <n> companies · Top 5', quarter derived from as_of."""
    assert metrics._as_quarter("2026-06-25") == "Q2 2026"
    assert metrics._as_quarter("2026-01-10") == "Q1 2026"
    assert metrics._as_quarter("Q1 2026") == "Q1 2026"   # already a quarter -> unchanged
    assert metrics._as_quarter("") == ""
    b = metrics.universe_banner({"as_of": "2026-06-25", "constituents": [{}] * 52})
    assert b == "Q2 2026 · 52 companies · Top 5", b


def test_dataset_origin_disclaimer():
    """A locally-computed numeric build (origin 'dataset') must NOT claim it was fetched live."""
    text = stage3._disclaimer({"_origin": "dataset"})
    assert "not a live fetch" in text.lower(), text
    assert "public sources" not in text.lower(), text  # the misleading 'live/fetched' claim is gone
    # the real origins are still honest
    assert "public sources" in stage3._disclaimer({"_origin": "live"}).lower()
    assert "placeholder" in stage3._disclaimer({"_origin": "sample"}).lower()


def test_compare_companies():
    """[#2] Pure extraction of comparable numeric series from Contract B dicts for the compare
    graphs. Grounded only in the data — a missing/unknown field is None, never fabricated."""
    a = {
        "company": "DemoBank SG", "ticker": "SGX:DEMO",
        "layer_a": {"esg_score_static": "22.4 (Medium Risk)"},
        "layer_b": {"momentum": {"E": {"magnitude": "+8%"}, "S": {"magnitude": "0%"},
                                 "G": {"magnitude": "+15%"}}},
    }
    b = {  # evidence-only / unknown -> all None, no chart fabricated
        "company": "Real Co", "ticker": "KLSE:REAL",
        "layer_a": {"esg_score_static": "unknown"},
        "layer_b": {"momentum": {"E": {"magnitude": "unknown"}, "S": {}, "G": {}}},
    }
    out = metrics.compare_companies([a, b])
    assert out["pillars"] == ["E", "S", "G"], out["pillars"]
    ra, rb = out["rows"]
    assert ra["company"] == "DemoBank SG" and ra["ticker"] == "SGX:DEMO"
    assert ra["esg_score"] == 22.4, ra["esg_score"]
    assert ra["momentum"] == {"E": 8.0, "S": 0.0, "G": 15.0}, ra["momentum"]
    assert rb["esg_score"] is None
    assert rb["momentum"] == {"E": None, "S": None, "G": None}, rb["momentum"]
    assert out["has_momentum"] is True and out["has_score"] is True
    # all-unknown set -> no data flags both False (renders 'awaiting data', no chart)
    empty = metrics.compare_companies([b])
    assert empty["has_momentum"] is False and empty["has_score"] is False
    # robust to junk input
    assert metrics.compare_companies(None)["rows"] == []
    assert metrics.compare_companies(["junk"])["rows"][0]["esg_score"] is None


def test_demo_roster_valid():
    from scripts import demo_roster
    import esg_data
    cfg = demo_roster.load_config()
    assert len(cfg) == 36
    tickers = [c["ticker"] for c in cfg]
    assert len(set(tickers)) == 36, "tickers unique"
    valid_countries = set(esg_data.COUNTRIES.values())
    for c in cfg:
        assert c["country"] in valid_countries
        for key in ("name", "country", "sector", "real_world_basis", "ticker", "exchange"):
            assert key in c
    # every country represented
    assert valid_countries <= {c["country"] for c in cfg}


def test_demo_roster_rejects_malformed():
    """Each of load_config's three guards must raise ValueError (not KeyError / silent pass)."""
    from scripts import demo_roster
    import tempfile
    _ok = lambda **kw: {"name": "X", "country": "Singapore", "sector": "S",
                        "real_world_basis": "RWB", "ticker": "SGX:X", "exchange": "SGX", **kw}
    missing_key = _ok()
    del missing_key["ticker"]                                # (1) missing required key
    bad_country = _ok(ticker="SGX:Y", country="Atlantis")   # (2) country not one of the 6
    dup_a = _ok(ticker="SGX:DUP")
    dup_b = _ok(name="Y", ticker="SGX:DUP")                 # (3) duplicate ticker
    cases = ([missing_key], [bad_country], [dup_a, dup_b])
    for companies in cases:
        fd, p = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"companies": companies}, f)
        try:
            demo_roster.load_config(path=p)
        except ValueError:
            continue  # expected
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"{companies} raised {type(e).__name__}, want ValueError") from e
        finally:
            os.remove(p)
        raise AssertionError(f"{companies} should have raised ValueError")


import universe  # noqa: E402 — used by the grounded data-backed tests below


def test_demo_enrich_deterministic_and_labelled():
    from scripts import demo_enrich
    bd = {"e_score": 60.0, "s_score": 55.0, "g_score": 70.0, "overall": 61.0}
    m1 = demo_enrich.momentum("DemoBank", bd)
    m2 = demo_enrich.momentum("DemoBank", bd)
    assert m1 == m2 and set(m1) == {"environment", "social", "governance", "digital_ai"}
    news = demo_enrich.news("DemoBank")
    assert news and all("url" not in n for n in news), "no fabricated URLs (HARD RULE 2)"
    assert any("illustrative" in n["source"].lower() for n in news)
    mk = demo_enrich.market("DemoBank", "SGX")
    assert mk["currency"] == "SGD" and isinstance(mk["price"], float)
    assert mk["low"] <= mk["open"] <= mk["high"] and mk["low"] <= mk["price"] <= mk["high"], mk
    assert mk["week52_low"] <= mk["low"] and mk["high"] <= mk["week52_high"], mk


def _demo_row(name):
    for c in universe.load_universe(universe.DEMO_FILE)["constituents"]:
        if c["company"] == name:
            return c
    raise AssertionError(f"{name} not in demo universe")


# --- #17 share price · 90 days -------------------------------------------------
def test_price_change_pct():
    assert metrics.price_change_pct({"price_change_90d": "+9.4%"}) == 9.4
    assert metrics.price_change_pct({"price_change_90d": "-5%"}) == -5.0
    assert metrics.price_change_pct({}) is None
    assert metrics.price_change_pct(None) is None
    assert metrics.price_change_pct({"price_change_90d": "unknown"}) is None


def test_price_series():
    s = metrics.price_series(9.4)
    assert len(s) == 10 and s[0] == 100.0 and s[-1] == 109.4, s
    assert all(s[i] < s[i + 1] for i in range(len(s) - 1)), s
    assert metrics.price_series(-6)[-1] < 100
    assert metrics.price_series(None) == []
    assert metrics.price_series(5, points=1) == [100.0]


def test_price_series_grounded():
    db = _demo_row("DemoBank")
    assert metrics.price_change_pct(db) is not None
    assert metrics.price_series(metrics.price_change_pct(db))[-1] > 100
    for c in universe.load_universe(universe.UNIVERSE_FILE)["constituents"]:
        assert metrics.price_change_pct(c) is None, c.get("company")  # HARD RULE 2


# --- #10/2.3 financial snapshot -----------------------------------------------
_DEMO_MARKET = {"currency": "SGD", "price": 14.82, "prev_close": 14.58, "open": 14.60,
                "high": 14.95, "low": 14.55, "market_cap": "S$42.1B", "pe_ratio": 11.4,
                "dividend_yield": "4.8%", "week52_high": 15.40, "week52_low": 11.20,
                "as_of": "2026-01-15"}


def test_financial_snapshot_have_format():
    fs = metrics.financial_snapshot({"market": _DEMO_MARKET, "price_change_90d": "+9.4%"})
    assert fs["have"] is True
    assert fs["currency"] == "SGD"
    assert fs["price"] == "SGD 14.82", fs["price"]
    assert fs["price_change_90d"] == "+9.4%", fs["price_change_90d"]
    assert fs["range_52w"] == "11.20 – 15.40", fs["range_52w"]
    labels = [r["label"] for r in fs["rows"]]
    for L in ("Open", "Market cap", "P / E", "52-week range"):
        assert L in labels, (L, labels)
    slabels = [r["label"] for r in fs["simple"]]
    assert len(fs["simple"]) <= 3 and "Price" in slabels and "90-day change" in slabels, slabels
    mc = [r["value"] for r in fs["rows"] if r["label"] == "Market cap"][0]
    assert mc == "S$42.1B"  # pre-formatted, passed through verbatim
    dy = [r["value"] for r in fs["rows"] if r["label"] == "Dividend yield"][0]
    assert dy == "4.8%"


def test_financial_snapshot_awaiting():
    for obj in ({}, {"company": "DBS Group Holdings", "esg_basis": "MSCI AA"}):
        fs = metrics.financial_snapshot(obj)
        assert fs["have"] is False and fs["rows"] == [] and fs["simple"] == []


def test_financial_snapshot_reads_market():
    fs = metrics.financial_snapshot({"_market": _DEMO_MARKET, "_price_change_90d": "+9.4%"})
    assert fs["have"] is True and fs["price"] == "SGD 14.82" and fs["price_change_90d"] == "+9.4%"


def test_company_from_numeric_rides_market():
    c = {"company": "X", "ticker": "T", "sector": "S", "esg_score": 22,
         "momentum": {"environment": 5, "social": 1, "governance": 2, "digital_ai": 10},
         "market": _DEMO_MARKET, "price_change_90d": "+9.4%"}
    comp = datasource.company_from_numeric(c, origin="sample")
    assert comp["_market"] == _DEMO_MARKET
    assert comp["_price_change_90d"] == "+9.4%"
    comp2 = datasource.company_from_numeric({"company": "Y", "ticker": "Y", "sector": "S"})
    assert "_market" not in comp2 and "_price_change_90d" not in comp2  # no None leak


# --- #11 news card ------------------------------------------------------------
def test_news_card_demo():
    nc = metrics.news_card({"company": "DemoBank",
                            "news": [{"title": "X", "source": "DemoWire", "date": "2026-06-12"}]})
    assert nc["illustrative"] is True and nc["status"] == "demo"
    assert len(nc["headlines"]) == 1
    assert nc["headlines"][0]["title"] == "X" and nc["headlines"][0]["source"] == "DemoWire"
    assert nc["youtube_url"] and "youtube.com" in nc["youtube_url"]


def test_news_card_real_awaiting():
    nc = metrics.news_card({"company": "DBS Group Holdings"})
    assert nc["illustrative"] is False and nc["status"] == "awaiting" and nc["headlines"] == []
    assert nc["youtube_url"] and nc["news_url"]


def test_youtube_search_url():
    u = metrics.youtube_search_url("DemoBank")
    assert u.startswith("https://www.youtube.com/results?search_query=")
    assert "DemoBank" in u
    assert metrics.youtube_search_url("DemoBank") == metrics.youtube_search_url("DemoBank")


def test_news_card_robust():
    assert metrics.news_card(None)["status"] == "awaiting"
    nc = metrics.news_card({"company": "X", "news": "notalist"})
    assert nc["status"] == "awaiting" and nc["headlines"] == []


def test_demo_universe_news_seeded():
    cons = universe.load_universe(universe.DEMO_FILE)["constituents"]
    for c in cons:
        nw = c.get("news")
        if nw is not None:
            assert isinstance(nw, list), c["company"]
            for it in nw:
                assert isinstance(it, dict) and "title" in it and "url" not in it, c["company"]
    assert _demo_row("DemoBank").get("news")


# --- #18/3.17 analyst coverage ------------------------------------------------
def test_analyst_coverage():
    ac = metrics.analyst_coverage({"analyst_coverage": {"analysts": 22, "as_of": "Q1 2026"}})
    assert ac["covered"] is True and ac["analysts"] == 22 and ac["as_of"] == "Q1 2026"
    assert ac["label"] == "22 analysts covering" and ac["illustrative"] is True
    assert metrics.analyst_coverage({"analyst_coverage": {"analysts": 1}})["label"] == "1 analyst covering"
    zero = metrics.analyst_coverage({"analyst_coverage": {"analysts": 0}})
    assert zero["covered"] is False and zero["illustrative"] is True
    absent = metrics.analyst_coverage({})
    assert absent["covered"] is False and absent["analysts"] is None
    assert absent["label"] == "awaiting data" and absent["illustrative"] is False
    assert metrics.analyst_coverage({"analyst_coverage": "x"})["covered"] is False
    assert metrics.analyst_coverage({"analyst_coverage": {"analysts": "x"}})["covered"] is False
    for w in ("buy", "sell", "hold"):
        assert w not in ac["label"].lower()  # HARD RULE 4


def test_analyst_coverage_fabrication_guard():
    for c in universe.load_universe(universe.UNIVERSE_FILE)["constituents"]:
        assert "analyst_coverage" not in c
        assert metrics.analyst_coverage(c)["covered"] is False
    du = universe.load_universe(universe.DEMO_FILE)["constituents"]
    assert any(metrics.analyst_coverage(c)["covered"] and metrics.analyst_coverage(c)["illustrative"]
               for c in du)


# --- 2.1 plain summary --------------------------------------------------------
def test_plain_summary():
    hw = _demo_row("Selat Bank")               # a demo hidden winner (classify -> HIDDEN WINNER)
    ps = metrics.plain_summary(hw)
    assert ps["tone"] == "good" and ps["label"] == "HIDDEN WINNER", ps["label"]
    assert "Selat Bank" in ps["body"] and not any(ch.isdigit() for ch in ps["body"])
    assert ps["verdict"] == ""
    ps2 = metrics.plain_summary(hw, {"competes_summary": "Rating understates the live AI build."})
    assert ps2["verdict"] == "Rating understates the live AI build."
    assert metrics.plain_summary(hw, {"competes_summary": "unknown"})["verdict"] == ""
    real = [c for c in universe.load_universe(universe.UNIVERSE_FILE)["constituents"]
            if c.get("esg_basis")][0]
    psr = metrics.plain_summary(real)
    assert psr["label"] in ("ESG LEADER", "STRONG IMPROVER", "ESTABLISHED", "EMERGING"), psr["label"]
    assert "/100" not in psr["body"] and "%" not in psr["body"]
    ps4 = metrics.plain_summary({"company": "X"})
    assert ps4["label"] == "AWAITING DATA" and ps4["headline"]


# --- #5 check before Monday ---------------------------------------------------
def test_focused_check_before_monday():
    snaps = {"SGX:DEMO": {"answer": {"check_before_monday": "Confirm the MAS AI guidance timeline",
                                     "competes_summary": "We disagree with the stale BBB"}}}
    assert metrics.focused_answer_action(snaps, "SGX:DEMO") == {
        "check": "Confirm the MAS AI guidance timeline",
        "verdict": "We disagree with the stale BBB", "has": True}
    assert metrics.focused_answer_action({"T": {"answer": None}}, "T")["has"] is False
    assert metrics.focused_answer_action(snaps, "NOPE")["has"] is False
    j = metrics.focused_answer_action({"T": {"answer": {"check_before_monday": "unknown"}}}, "T")
    assert j["has"] is False and j["check"] == ""
    assert metrics.focused_answer_action(None, "X")["has"] is False
    assert metrics.focused_answer_action({"T": {"answer": "junk"}}, "T")["has"] is False


# --- 1.11 freshness -----------------------------------------------------------
def test_fmt_elapsed():
    assert metrics.fmt_elapsed(1000, 1000) == "just now"
    assert metrics.fmt_elapsed(1000, 970) == "just now"
    assert metrics.fmt_elapsed(1000, 940) == "1 min ago"
    assert metrics.fmt_elapsed(1180, 1000) == "3 min ago"
    assert metrics.fmt_elapsed(4600, 1000) == "1 hr ago"
    assert metrics.fmt_elapsed(91000, 1000) == "1d ago"
    assert metrics.fmt_elapsed(1000, None) == ""
    assert metrics.fmt_elapsed(1000, 2000) == "just now"  # negative skew clamped


# --- 2.2 chatbot copy ---------------------------------------------------------
def test_chat_copy_indepth_regression():
    assert metrics.chat_relay_msg("DBS", "compete", False) == \
        "Running the 3-stage ESG relay on DBS (compete mode)…"
    assert metrics.chat_relay_msg("DBS", "compete", False, focused=True) == \
        "Running the 3-stage relay on the focused company (compete mode)…"
    assert metrics.chat_relay_msg("X", "interrogate", False, live=True) == \
        "Built X live (ASEAN) — running the 3-stage relay (interrogation mode)…"
    assert metrics.chat_filter_msg(["Singapore", "Banks"], False) == "Filtered to Singapore · Banks."
    assert metrics.chat_focus_msg("X", "Banks", False, avg=22.4, digital_pct="+340%") == \
        "Focused X — scored against Banks peers, Digital/AI +340% vs avg ESG 22.4. Added to the grid."
    assert metrics.chat_focus_msg("X", "Banks", False, avg=None) == "Focused X. Added to the grid."
    assert metrics.chat_fallback_msg(False) == \
        ("I can filter (“show banks”, “Singapore”, “all ASEAN”) or focus "
         "a company (“DemoBank”, “add GreenChip Bank”).")
    assert metrics.chat_relay_help(False) == \
        ("Name a company to analyse — e.g. “analyze DBS”, “interrogate "
         "Maybank”, or a live ASEAN name like “analyze Grab”.")
    assert metrics.chat_cant_analyse_msg("Z", False) == "Couldn't analyse “Z”."


def test_chat_copy_simplified():
    forbidden = ("relay", "compete mode", "interrogate mode", "3-stage", "Digital/AI", "avg ESG")
    outs = [
        metrics.chat_relay_msg("DBS", "compete", True),
        metrics.chat_relay_msg("DBS", "interrogate", True, focused=True),
        metrics.chat_focus_msg("X", "Banks", True, avg=22.4, digital_pct="+340%"),
        metrics.chat_filter_msg(["Singapore"], True),
        metrics.chat_relay_help(True),
        metrics.chat_fallback_msg(True),
        metrics.chat_cant_analyse_msg("Z", True),
    ]
    for o in outs:
        assert isinstance(o, str) and o
        for f in forbidden:
            assert f not in o, (f, o)
    foc = metrics.chat_focus_msg("X", "Banks", True, avg=22.4, digital_pct="+340%")
    assert "X" in foc and "22.4" not in foc and "340" not in foc and "Digital" not in foc and "ESG" not in foc
    # differs from In-Depth for the same inputs
    assert metrics.chat_filter_msg(["Singapore"], True) != metrics.chat_filter_msg(["Singapore"], False)
    # robustness
    metrics.chat_filter_msg([], True)
    metrics.chat_filter_msg([], False)
    metrics.chat_cant_analyse_msg("", True)


# --- 14/3.7 suggested follow-ups ----------------------------------------------
def test_suggested_followups():
    foc_s = metrics.suggested_followups(focused_name="DemoBank", focused_sector="Banks",
                                        has_focus=True, simplified=True)
    foc_d = metrics.suggested_followups(focused_name="DemoBank", focused_sector="Banks",
                                        has_focus=True, simplified=False)
    assert [c["prompt"] for c in foc_s] == ["Analyze DemoBank", "Interrogate DemoBank", "Show Banks"]
    assert [c["prompt"] for c in foc_d] == [c["prompt"] for c in foc_s]  # prompts identical
    assert [c["label"] for c in foc_s] != [c["label"] for c in foc_d]    # labels differ by mode
    no = metrics.suggested_followups(has_focus=False, simplified=True,
                                     sample_sector="Banks", sample_country="Malaysia")
    assert [c["prompt"] for c in no] == ["Show Banks", "Malaysia", "Show all ASEAN"]
    allind = metrics.suggested_followups(focused_name="DemoBank", focused_sector="All industries",
                                         has_focus=True, simplified=True)
    assert allind[2]["prompt"] == "Show all ASEAN"
    for chips in (foc_s, foc_d, no, allind):
        assert len(chips) <= 3
        for c in chips:
            blob = (c["label"] + " " + c["prompt"]).lower()
            for w in ("buy", "sell", "hold", "score"):
                assert w not in blob, (w, c)


def test_get_country_table_live_then_fallback(tmp_path=None):
    import esg_data, core, json, tempfile
    # Hermetic: redirect the live cache to a throwaway temp path so the success sub-test's
    # cache write can't leak into the bundled-fallback assertion below.
    orig_cache = esg_data._LIVE_CACHE_CSV
    fd, cache_p = tempfile.mkstemp(suffix=".csv"); os.close(fd); os.remove(cache_p)  # no cache yet
    esg_data._LIVE_CACHE_CSV = cache_p
    orig = core.http_get
    try:
        # --- success path: mock returns a valid WB payload for any indicator ---
        def fake_ok(url, params=None, **kw):
            # derive indicator from url tail; return the same value for all 6 countries
            rows = [{"countryiso3code": iso, "date": "2024", "value": 1.0}
                    for iso in esg_data.COUNTRIES]
            return json.dumps([{"page": 1}, rows])
        core.http_get = fake_ok
        table, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "live"
        assert set(table.keys()) == set(esg_data.COUNTRIES.values())
        # drop the cache the success path wrote so the fallback below reads the BUNDLED CSV
        if os.path.exists(cache_p):
            os.remove(cache_p)
        # --- failure path: mock raises -> fallback (bundled), never raises ---
        def fake_fail(url, params=None, **kw):
            raise RuntimeError("network down")
        core.http_get = fake_fail
        table, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "fallback"
        assert abs(table["Singapore"]["rule_of_law"] - 78.62) < 0.1  # normalized BUNDLED fallback
    finally:
        core.http_get = orig
        esg_data._LIVE_CACHE_CSV = orig_cache
        if os.path.exists(cache_p):
            os.remove(cache_p)


def test_cache_becomes_next_fallback():
    """The last successful live pull is cached and BECOMES the next fallback automatically:
    a subsequent failed pull returns the CACHED value, not the bundled CSV."""
    import esg_data, core, json, tempfile
    orig_cache = esg_data._LIVE_CACHE_CSV
    fd, cache_p = tempfile.mkstemp(suffix=".csv"); os.close(fd); os.remove(cache_p)  # fresh, no cache
    esg_data._LIVE_CACHE_CSV = cache_p
    orig = core.http_get
    try:
        # successful pull with a DISTINCTIVE value (2.0) -> origin 'live', cache written
        def fake_ok(url, params=None, **kw):
            rows = [{"countryiso3code": iso, "date": "2024", "value": 2.0}
                    for iso in esg_data.COUNTRIES]
            return json.dumps([{"page": 1}, rows])
        core.http_get = fake_ok
        _t, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "live", origin
        assert os.path.exists(cache_p) and os.path.getsize(cache_p) > 0, "live pull must cache"
        # now the network fails -> fallback must read the CACHED pull, not the bundled CSV
        def fake_fail(url, params=None, **kw):
            raise RuntimeError("network down")
        core.http_get = fake_fail
        table, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "fallback", origin
        # cached 2.0 normalizes to (2.0+2.5)/5*100 = 90.0 — NOT the bundled 78.62
        assert abs(table["Singapore"]["rule_of_law"] - 90.0) < 0.1, table["Singapore"]["rule_of_law"]
    finally:
        core.http_get = orig
        esg_data._LIVE_CACHE_CSV = orig_cache
        if os.path.exists(cache_p):
            os.remove(cache_p)


def test_get_country_table_never_raises_when_data_missing():
    """Even with BOTH the cache and the bundled CSV absent/unreadable, get_country_table must
    not raise: it degrades to an empty-but-valid (table, 'fallback') result ('never raises').
    The bundled read failure is simulated by making load_fallback raise (a missing/unreadable
    FALLBACK_CSV in a clean clone), with the cache path pointed at a guaranteed-absent file."""
    import esg_data, tempfile
    orig_load, orig_cache = esg_data.load_fallback, esg_data._LIVE_CACHE_CSV
    fd, missing = tempfile.mkstemp(suffix=".csv"); os.close(fd); os.remove(missing)  # guaranteed gone
    esg_data._LIVE_CACHE_CSV = missing + ".cache"         # nonexistent cache path -> skip cache branch

    def boom(*a, **k):                                    # missing/unreadable bundled CSV
        raise FileNotFoundError("bundled CSV missing")
    esg_data.load_fallback = boom
    try:
        out = esg_data.get_country_table(allow_live=False, log=lambda *a: None)  # must NOT raise
        assert isinstance(out, tuple) and len(out) == 2, out
        table, origin = out
        assert origin == "fallback", origin
        assert isinstance(table, dict), table  # empty {} is acceptable
    finally:
        esg_data.load_fallback, esg_data._LIVE_CACHE_CSV = orig_load, orig_cache


def test_esg_data_fallback_roundtrip():
    import esg_data, tempfile
    t = esg_data.load_fallback()
    assert set(t.keys()) == set(esg_data.COUNTRIES.values()), "6 countries by name"
    assert abs(t["Singapore"]["rule_of_law"] - 1.431) < 1e-6
    assert t["Singapore"]["env_policy"] is None, "missing cell -> None"
    # round-trip: save then reload equals original
    fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
    esg_data.save_fallback(t, p)
    t2 = esg_data.load_fallback(p)
    assert t2["Vietnam"]["gender_lfp_ratio"] == t["Vietnam"]["gender_lfp_ratio"]
    assert t2["Philippines"]["injury_rate"] is None
    os.remove(p)


def test_esg_data_normalize():
    import esg_data
    raw = esg_data.load_fallback()
    norm = esg_data.normalize(raw)
    sg = norm["Singapore"]
    # WGI: (1.431+2.5)/5*100 = 78.62
    assert abs(sg["rule_of_law"] - 78.62) < 0.1
    # CO2 inverted, cap 20: (1-12.605/20)*100 = 36.975
    assert abs(sg["co2_pc"] - 36.975) < 0.05
    # renew cap 50: 1.1/50*100 = 2.2
    assert abs(sg["renew_share"] - 2.2) < 0.05
    # missing stays None
    assert sg["env_policy"] is None and sg["injury_rate"] is None
    # all present values within [0,100]
    for c in norm.values():
        for v in c.values():
            assert v is None or (0.0 <= v <= 100.0)


def test_esg_data_parse_upload():
    import esg_data
    csv_text = ("country,rule_of_law,co2_pc\n"
                "Singapore,2.0,10\n"
                "Vietnam,-0.5,6\n")
    t = esg_data.parse_upload(csv_text)
    assert abs(t["Singapore"]["rule_of_law"] - 2.0) < 1e-6
    assert abs(t["Vietnam"]["co2_pc"] - 6.0) < 1e-6
    assert t["Singapore"]["renew_share"] is None  # absent column -> None


def test_esg_scoring_deterministic_and_bounded():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Singapore"]
    a = esg_scoring.score_company(row, "Financials — Banks", name="DemoBank", country="Singapore")
    b = esg_scoring.score_company(row, "Financials — Banks", name="DemoBank", country="Singapore")
    assert a == b, "deterministic: same name -> identical scores"
    for k in ("e_score", "s_score", "g_score", "overall"):
        assert 0.0 <= a[k] <= 100.0
    # breakdown mirrors top-level
    assert a["breakdown"]["overall"] == a["overall"]
    # provenance present, no real_world_basis leak possible (name only)
    assert "country-level" in a["data_provenance"].lower()

def test_esg_scoring_sector_multiplier_effect():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Singapore"]
    bank = esg_scoring.score_company(row, "Financials — Banks", name="X Bank")
    power = esg_scoring.score_company(row, "Energy — Power & Renewables", name="X Bank")
    # banks tilt G up vs energy; energy tilts E up vs banks (same base row, same seed)
    assert bank["g_score"] > power["g_score"]
    assert power["e_score"] > bank["e_score"]

def test_esg_scoring_variance_differs_by_name():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Malaysia"]
    s1 = esg_scoring.score_company(row, "Real Estate", name="Alpha")
    s2 = esg_scoring.score_company(row, "Real Estate", name="Beta")
    assert s1["overall"] != s2["overall"], "seeded variance separates same-country peers"


def test_build_demo_universe_schema_and_no_leak():
    from scripts import build_demo_universe
    uni = build_demo_universe.build(allow_live=False)   # offline -> bundled CSV
    cons = uni["constituents"]
    assert len(cons) == 36
    for c in cons:
        assert "real_world_basis" not in c, "internal field must never leak"
        assert 0.0 <= c["esg_score"] <= 100.0, "0-100 higher=better"
        assert set(c["esg_breakdown"]) == {"e_score", "s_score", "g_score", "overall"}
        assert "data_provenance" in c and c["data_provenance"]
        for k in ("momentum", "market", "news", "live_signals"):
            assert k in c
    # serialized JSON also has no leak
    import json
    assert "real_world_basis" not in json.dumps(uni)


def test_company_from_numeric_rides_breakdown_and_note():
    import datasource
    c = {"company": "DemoBank", "ticker": "SGX:DBKO", "sector": "Financials — Banks",
         "esg_score": 64.0, "esg_as_of": "2024",
         "esg_breakdown": {"e_score": 19.0, "s_score": 79.0, "g_score": 95.0, "overall": 64.0},
         "data_provenance": "Derived from country-level proxies.",
         "momentum": {"environment": 5, "social": 3, "governance": 8, "digital_ai": 20}}
    cd = datasource.company_from_numeric(c)
    assert "HIGHER" in cd["layer_a"]["note"], "note flipped to higher=better"
    assert cd.get("_esg_breakdown", {}).get("g_score") == 95.0
    assert "country-level" in cd.get("_data_provenance", "").lower()


def test_metrics_esg_breakdown_passthrough():
    import metrics
    comp = {"esg_breakdown": {"e_score": 1, "s_score": 2, "g_score": 3, "overall": 4}}
    assert metrics.esg_breakdown(comp)["g_score"] == 3
    assert metrics.esg_breakdown({}) is None


def test_snapshot_band_direction_aware():
    # a demo performance score (higher=better) must NOT read as a risk band
    demo = datasource.company_from_numeric(
        {"company": "Lead", "ticker": "X:LEAD", "sector": "Financials — Banks",
         "esg_score": 64.9, "esg_as_of": "2024", "momentum": {"environment": 5}}, origin="sample")
    snap = datasource.snapshot_from_company(demo)
    assert snap["score_higher_better"] is True, snap
    assert snap["band_tone"] == "good" and "Risk" not in snap["band"], (snap["band"], snap["band_tone"])
    # a risk-style bare number (lower=better, no marker) keeps the Sustainalytics band
    risk = {"layer_a": {"esg_score_static": "45", "as_of_date": "2024"}, "layer_b": {}}
    rsnap = datasource.snapshot_from_company(risk)
    assert rsnap["band"] == "Severe Risk" and rsnap["band_tone"] == "bad", rsnap


# --- CGSI verified basket (2026-08-21 data swap) ------------------------------
def test_cost_model_prices_cache_hits_rather_than_writing_them_off():
    """A cache hit is a cheaper RATE, not free — and the cache never touches output.

    DeepSeek bill a hit at $0.007/1M against $0.22 on a miss: 31x cheaper, not zero. Modelling
    the cache as "those tokens are free" overstates the saving, and applying a flat percentage
    off the whole prompt overstates it far worse. Both mistakes flatter a cost model, which is
    the one place this project cannot afford to be generous with itself."""
    import cost_model

    measured = {"prompt_tokens_per_company_per_sweep": 10000,
                "output_tokens_per_company_per_sweep": 1000,
                "cacheable_prompt_share_pct": 50.0}
    kw = dict(price_hit=0.007, price_miss=0.22, price_out=0.66, fx=1.0, sweeps_per_month=1)

    full = cost_model.unit_economics(measured, cache_hit=1.0, **kw)
    none = cost_model.unit_economics(measured, cache_hit=0.0, **kw)

    # with a perfect hit rate only the CACHEABLE half moves to the hit rate
    assert full["cache_hit_tokens_per_sweep"] == 5000, full
    assert full["cache_miss_tokens_per_sweep"] == 5000, full
    # ...and it still costs something: 5000 tokens at $0.007/1M is not zero
    hit_cost = 5000 / 1e6 * 0.007
    expected = hit_cost + 5000 / 1e6 * 0.22 + 1000 / 1e6 * 0.66
    assert abs(full["usd_per_company_per_sweep"] - expected) < 1e-9, full
    assert full["usd_per_company_per_sweep"] > 0

    # no cache at all -> the whole prompt bills at the miss rate
    assert none["cache_miss_tokens_per_sweep"] == 10000, none
    assert none["usd_per_company_per_sweep"] > full["usd_per_company_per_sweep"]

    # output is never discounted by the cache
    out_only = 1000 / 1e6 * 0.66
    assert full["usd_per_company_per_sweep"] > out_only

    # the scoring path is structurally zero-token, and the model must keep saying so
    inputs = cost_model.measured_inputs()
    if inputs.get("available"):
        assert inputs["tokens_per_signal_scoring_path"] == 0, inputs

    # and it refuses to run without prices
    try:
        cost_model.main(["--price-hit", "0.007"])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("cost_model ran without being given every price")


def test_every_real_surface_scores_the_same_run():
    """The board, the money slide, the anchor and the blind test must agree on ONE run.

    The moment harvested evidence merges into the real basket, any surface that forgets the
    overlay silently describes a DIFFERENT universe. The consequences are not cosmetic: the
    money slide would print an M the screen contradicts, and — worse — `anchor.py` would hash a
    run the verification page cannot reproduce, so the page would report NO MATCH on evidence
    nobody had tampered with. That is the tamper-evidence claim failing in the direction that
    destroys it. So this asserts they all land on the same `run_id`."""
    import company_metadata, engine, engine_config, harvest, pipeline_counts, server

    cfg = engine_config.load()
    meta = company_metadata.load()
    cons = harvest.apply_overlay(universe.constituents())
    expected = engine.run_engine(cons, metadata=meta, config=cfg, use_cache=False)["run_id"]

    board_run, _meta, _cfg = server._engine_run(False)
    assert board_run["run_id"] == expected, ("board", board_run["run_id"], expected)

    # the counts must be computed over that same run
    counts = pipeline_counts.counts(board_run, meta, cfg)
    assert counts["N"] == 13, counts

    # and if a harvest exists at all, it must actually be reaching the engine
    overlay = harvest.load_overlay()
    if overlay:
        bare = engine.run_engine(universe.constituents(), metadata=meta, config=cfg,
                                 use_cache=False)
        assert board_run["run_id"] != bare["run_id"], \
            "harvested evidence exists but the board's run is identical to the bare one"
        harvested_signals = sum(r["signal_count"] for r in board_run["records"])
        bare_signals = sum(r["signal_count"] for r in bare["records"])
        assert harvested_signals > bare_signals, (harvested_signals, bare_signals)
        # and the decay reference must NOT have moved (the 2050 bug)
        assert board_run["as_of"] == bare["as_of"], (board_run["as_of"], bare["as_of"])


def test_traction_screen_states_and_rule():
    """§B.4's four tests, and the distinction that matters: unknown is not failure."""
    import traction

    rows = traction.loss_makers()
    assert set(rows) == {"KLSE:PCHEM", "SET:PTTGC"}, sorted(rows)

    row = rows["SET:PTTGC"]
    # nothing answered -> the screen has NOT run; the company is neither cleared nor disqualified
    blank = traction.screen(row)
    assert blank["verdict"] == "screen_not_run" and blank["traction_flag"] is False, blank
    assert blank["unknown"] == 4

    # two met -> flag; the rule is >= 2 of 4
    two = traction.screen(row, {"revenue_growth": "met", "order_book": "met",
                                "cash_flow": "not_met", "green_pipeline": "not_met"})
    assert two["verdict"] == "traction" and two["traction_flag"] is True, two
    one = traction.screen(row, {"revenue_growth": "met", "order_book": "not_met",
                                "cash_flow": "not_met", "green_pipeline": "not_met"})
    assert one["verdict"] == "insufficient_traction" and one["traction_flag"] is False, one
    none = traction.screen(row, {k: "not_met" for k, _, _ in traction.TESTS})
    assert none["verdict"] == "disqualified", none

    # a verdict is reached as soon as two tests are met, even with a blank cell left over:
    # the remaining tests cannot unsatisfy a rule that is already satisfied
    partial = traction.screen(row, {"revenue_growth": "met", "cash_flow": "met"})
    assert partial["verdict"] == "traction" and partial["unknown"] == 2, partial

    # integrity: a flag written into the metadata must carry the evidence behind it
    for cid, meta_row in traction.loss_makers().items():
        if meta_row.get("traction_flag"):
            assert meta_row.get("traction_evidence"), (cid, "flag with no evidence")

    # the label travels — these thresholds are ours and the panel never confirmed them
    assert "team-designed" in blank["label"].lower(), blank["label"]
    assert "not credit analysis" in blank["label"].lower(), blank["label"]

    # net income is READ but never counted as one of the four (it is not operating cash flow)
    ni = blank["net_income"]
    assert ni["direction"] == "narrowing", ni      # -THB29.8b -> -THB14.6b
    assert "not" in ni["note"].lower() and "cash flow" in ni["note"].lower(), ni["note"]
    # the fiscal-year label must not be parsed as the amount
    assert traction._net_income_trend(rows["KLSE:PCHEM"])["direction"] == "swung to loss"


def test_harvest_guards_reject_ungrounded_events():
    """The model may only cite what it was shown, and may not date what the source did not."""
    import engine_config, harvest

    allowed = {"https://reuters.com/a", "https://sgx.com/b"}
    raw = [
        {"text": "A properly dated, properly cited emissions reduction of 25% versus 2020.",
         "published_at": "2024-06-01", "source_url": "https://reuters.com/a"},
        # guard 1 — a URL it was never given
        {"text": "A plausible-sounding fact with a fabricated citation attached to it.",
         "published_at": "2024-06-01", "source_url": "https://invented.example/x"},
        # guard 2 — no date
        {"text": "An undated claim about a sustainability programme with no year at all.",
         "published_at": "", "source_url": "https://reuters.com/a"},
        # guard 2 — a date shape that is not a date
        {"text": "Another claim, this time with a garbage date field attached to it.",
         "published_at": "sometime in 2024", "source_url": "https://reuters.com/a"},
        # too short to be a checkable fact
        {"text": "Good ESG.", "published_at": "2024-06-01", "source_url": "https://reuters.com/a"},
    ]
    kept = harvest._clean_events(raw, allowed, "SGX:TEST")
    assert len(kept) == 1, [k["text"] for k in kept]
    assert kept[0]["source_url"] == "https://reuters.com/a"

    # guard 2b — a TARGET year is not a publication date, and letting one through is not a
    # small error. `engine._as_of_from` takes the newest date in the data as the decay
    # reference, so a single "net zero by 2050" event dated 2050-12-31 moved as_of 24 years
    # forward, decayed every genuine signal in the basket to zero weight, and took composite
    # momentum for the WHOLE universe to 0.000 — with every signal_count still showing intact.
    future = [{"text": "The company aims to reach net zero across all scopes by twenty fifty.",
               "published_at": "2050-12-31", "source_url": "https://reuters.com/a"}]
    assert harvest._clean_events(future, allowed, "SGX:TEST", "2026-08-20") == []
    assert len(harvest._clean_events(raw, allowed, "SGX:TEST", "2026-08-20")) == 1

    # and the end-to-end consequence: merging the overlay must not move the run's as_of
    import engine
    base = universe.constituents()
    cap = max(str(c.get("as_of") or "")[:10] for c in base)
    for events in harvest.load_overlay().values():
        for e in events:
            assert e["published_at"] <= cap, ("harvested event post-dates the basket", e)

    # guard 3 — source_type comes from the DOMAIN, never from the model
    assert harvest._source_type_for("https://www.mas.gov.sg/news/x") == "regulator"
    assert harvest._source_type_for("https://links.sgx.com/filing") == "exchange_filing"
    assert harvest._source_type_for("https://www.reuters.com/x") == "news"
    assert harvest._source_type_for("https://someissuer.com/press") == "company_pr"
    assert harvest._source_type_for("") == "unknown"
    # every type it can emit must be priced in the config, or a signal silently scores at 0
    quality = engine_config.load()["source_quality"]
    for fragments, kind in harvest._DOMAIN_RULES:
        assert kind in quality, kind

    # guard 4 — the overlay never mutates the basket on disk
    cons = universe.constituents()
    before = [len(c.get("events") or []) for c in cons]
    merged = harvest.apply_overlay(cons, {cons[0]["ticker"]: [dict(kept[0])]})
    assert [len(c.get("events") or []) for c in universe.constituents()] == before
    assert len(merged[0]["events"]) == before[0] + 1


def test_lseg_never_serves_another_companys_scores():
    """A lookup returns THIS issuer's numbers or nothing. Never a near-miss.

    Regression for 2026-08-22, found by clicking a delisted name. Malaysia Airports Holdings
    resolved to `IBHD.KL` and rendered **I-Bhd's** ESG breakdown under Malaysia Airports' name.
    Two independent holes lined up: `_norm("I-Bhd")` is the single letter "i", which the
    containment tier matched as a raw substring of "malaysia airports"; and an explicit RIC
    passed in from the basket was fetched without ever checking it was a covered issuer. Both
    are HARD RULE 2 violations that look completely normal on screen, which is what makes them
    worth a test rather than a fix."""
    import lseg

    # a one-letter normalised name must not match inside a longer one
    assert lseg._norm("I-Bhd") == "i", lseg._norm("I-Bhd")
    assert not lseg._covers("malaysia airports", "i")
    assert lseg._covers("malayan banking", "malayan banking")
    assert lseg._covers("oversea chinese banking corporation", "chinese banking")
    # word-boundary, not substring: "sea" is not "oversea"
    assert not lseg._covers("oversea chinese banking", "sea")

    # the payload cross-check rejects a different issuer, accepts spelling drift
    assert lseg._same_issuer("Malayan Banking Berhad", "Malayan Banking Bhd")
    assert lseg._same_issuer("PTT PCL", "PTT")
    assert not lseg._same_issuer("I-Bhd", "Malaysia Airports Holdings Bhd")

    # And the end-to-end guard, when the covered list is available locally (it is cached; on a
    # cold machine with no network there is nothing to check against and the test says so
    # rather than pretending). A RIC that is not a covered issuer must resolve to nothing —
    # this is the assertion that would have caught MAHB.
    covered = {r["ricCode"] for r in lseg.fetch_covered_universe()}
    if not covered:
        raise Skipped("LSEG covered-issuer list not cached locally — nothing to check a RIC against")
    assert "MAHB.KL" not in covered, "MAHB is delisted; it should not be a covered issuer"
    assert lseg.resolve_ric("Malaysia Airports Holdings Bhd", "KLSE") is None, \
        "a delisted issuer resolved to SOMETHING — check which company it just claimed to be"


def test_metadata_follows_its_universe():
    """The demo universe joins the MOCK rows; the real basket joins the VERIFIED CSV.

    Regression for 2026-08-22. `active_file` preferred the real CSV as soon as it existed, so
    the fictional demo tickers joined 52 real companies and matched none of them — every demo
    badge silently went unverified and the demo board reported N 0 · M 0. A join miss rendered
    as an origination finding is exactly the failure this module exists to prevent, arriving
    through the other door, and nothing raised."""
    import company_metadata, engine, engine_config, pipeline_counts

    real_rows, demo_rows = company_metadata.load(), company_metadata.load(demo=True)
    assert real_rows and demo_rows, (len(real_rows), len(demo_rows))
    assert company_metadata.load_report()["path"].endswith("company_metadata.csv")
    assert company_metadata.load_report(demo=True)["path"].endswith("_mock.csv")
    # They are different row sets. (They are not disjoint — the mock file also carries the real
    # ASEAN tickers our earlier universe used — so the meaningful assertion is the join coverage
    # below, not an emptiness check here.)
    assert real_rows != demo_rows

    cfg = engine_config.load()
    for demo, rows in ((False, real_rows), (True, demo_rows)):
        cons = universe.constituents(universe.active_file(demo))
        matched = sum(1 for c in cons if c["ticker"] in rows)
        assert matched >= len(cons) * 0.9, (
            f"{'demo' if demo else 'real'} universe joined only {matched}/{len(cons)} "
            "metadata rows — the metadata file does not describe this universe")
        run = engine.run_engine(cons, metadata=rows, config=cfg, use_cache=False)
        counts = pipeline_counts.counts(run, rows, cfg)
        # N is a straight read of a verified column; zero here means the join failed, not that
        # a 52-name ASEAN basket contains no green-bond issuers.
        assert counts["N"] > 0, (demo, counts)


def test_cgsi_basket_adapts_onto_the_frozen_schema():
    """The real 52 load, N reproduces CGSI's own count, and the frozen header still holds.

    The handover note claimed "same schema, zero code changes"; it is a 23-column file against
    our 29-column frozen contract, so this pins that the ADAPTER — not a loosened header — is
    what absorbed the difference."""
    import company_metadata, pipeline_counts, engine, engine_config
    rows = company_metadata.load()
    report = company_metadata.load_report()
    assert len(rows) == 52, len(rows)
    assert report["ok"] and not report["missing_columns"], report
    assert report["provisional"] == 0 and report["verified"], report
    # the honesty layer the panel asked for: verified BY US is not CGSI-confirmed
    assert "not CGSI-confirmed" in report["header"], report["header"]
    assert report["review_chip"] == "AI-assisted \u00b7 human-reviewed", report["review_chip"]

    cons = universe.constituents()
    assert len(cons) == 52, len(cons)
    assert sum(1 for c in cons if c.get("high_conviction")) == 17
    assert sorted(c["ticker"] for c in cons if c.get("delisted")) == ["KLSE:MAHB", "SET:INTUCH"]
    # every constituent carries a DATED baseline, which is what keeps the engine pure while
    # using a real number instead of the old mock
    assert all(c.get("esg_score") and c.get("esg_score_basis") for c in cons)

    cfg = engine_config.load()
    run = engine.run_engine(cons, metadata=rows, config=cfg, use_cache=False)
    assert {r["baseline_origin"] for r in run["records"]} == {"SUPPLIED"}
    counts = pipeline_counts.counts(run, rows, cfg)
    assert counts["N"] == 13, counts          # CGSI computed 13 independently; so do we
    # M excludes the delisted and the already-priced-in, by rule not by luck
    assert not ({"KLSE:MAHB", "SET:INTUCH"} & set(counts["members"]["M"])), counts["members"]
    assert not (set(counts["members"]["N"]) & set(counts["members"]["M"])), counts["members"]

    # no reviewer is ever named "none" — Keppel's cell reads "none (SL framework...)"
    bogus = [e["text"] for c in cons for e in (c.get("events") or [])
             if "from none" in e["text"].lower()]
    assert not bogus, bogus


def test_sector_benchmark_joins_directly_and_refuses_to_guess():
    """The Eurostat bar joins on CGSI's own industry label, and an unknown industry says so."""
    import benchmarks
    banks = benchmarks.sector_benchmark("Banks")
    assert banks["available"] and banks["intensity"] == 7.89, banks
    assert banks["nace_code"] == "K" and banks["geo"] == "EU-27", banks
    # the wording rule: OECD-Europe, named dataset, and the Germany fallback stays flagged
    assert "OECD-Europe (EU-27) benchmark" in banks["attribution"], banks["attribution"]
    assert "env_ac_aeint_r2" in banks["attribution"], banks["attribution"]
    air = benchmarks.sector_benchmark("Airlines")
    assert air["is_fallback"] and "Germany fallback" in air["attribution"], air
    # a banks row must carry the financed-emissions caveat, not just the operational number
    assert "financed emissions" in banks["caveat"].lower(), banks["caveat"]
    # no nearest-bucket guessing
    miss = benchmarks.sector_benchmark("Underwater Basket Weaving")
    assert not miss["available"] and "no benchmark row" in miss["reason"], miss


def test_merkle_covers_the_yardstick_and_detects_a_swap():
    """leaf-v2: the benchmark FILE is a leaf, so the bar cannot be quietly swapped."""
    import anchor, company_metadata, engine, tempfile, shutil
    meta = company_metadata.load()
    run = engine.run_engine(universe.constituents(), metadata=meta, use_cache=False)
    leaves = anchor.leaves_for_run(run, meta)
    kinds = {}
    for leaf in leaves:
        kinds[leaf["kind"]] = kinds.get(leaf["kind"], 0) + 1
    assert kinds.get("benchmark", 0) >= 1, kinds
    assert kinds.get("green_bond", 0) == 52, kinds
    root = anchor.merkle_root([l["hash"] for l in leaves])

    # swap one character of the yardstick -> the root moves
    path = anchor.BENCHMARK_FILES[0]
    backup = path + ".selftest-bak"
    shutil.copyfile(path, backup)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(blob.replace("7.89", "7.88", 1))
        tampered = anchor.merkle_root(
            [l["hash"] for l in anchor.leaves_for_run(run, meta)])
        assert tampered != root, "a swapped benchmark left the root unchanged"
    finally:
        shutil.move(backup, path)
    # and it comes back
    assert anchor.merkle_root([l["hash"] for l in anchor.leaves_for_run(run, meta)]) == root
    # an absent benchmark contributes NO leaf rather than a leaf over the empty string
    assert anchor.benchmark_preimage("data/definitely-not-a-benchmark.csv") == ""


def test_claim_vs_evidence_is_labelled_illustrative_per_row():
    """§6's panel must never present an un-run check as a finding."""
    blob = _load("data/claim_vs_evidence.json")
    rows = blob["rows"]
    assert len(rows) == 3, len(rows)
    assert "illustrative" in blob["header"].lower() and "not a live feed" in blob["header"].lower()
    verdicts = set(blob["verdicts"])
    for row in rows:
        assert row["verdict"] in verdicts, row["verdict"]
        for side in ("claim", "evidence"):
            assert isinstance(row[side]["checked"], bool) and row[side]["basis"], row
        # an unchecked verdict must say so in its own note, not lean on the panel header
        if not row["verdict_checked"]:
            assert "not a finding" in row["verdict_note"].lower() or \
                   "realistic outcome" in row["verdict_note"].lower(), row["verdict_note"]
    # the honest negative is a REAL determination and has to stay one
    negative = [r for r in rows if r["verdict"] == "no_independent_data"]
    assert len(negative) == 1 and negative[0]["verdict_checked"], negative
    # nobody claims a satellite query was run
    assert not any(r["evidence"]["checked"] and "forest" in r["evidence"]["source"].lower()
                   for r in rows)


def test_api_smoke():
    """Exercise the primary FastAPI boundary without network, LLM, or a browser."""
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:
        # Optional for the lightweight offline selftest — but this is the ONLY coverage of the
        # primary boundary, so an absent dependency must be visible, not a silent green.
        raise Skipped(f"fastapi/httpx not installed ({exc})") from exc
    import server

    original_llm = core.call_llm
    fixture_answer = json.dumps(_load("fixtures/stage2_answer.json"))
    stage1_envelope = json.dumps({
        "axis": None, "type": "narrowed", "text": "Is the bank's ESG gap a near-term risk?",
        "rationale": "The mandate and horizon are now clear.", "suggested_replies": [],
        "done": True, "mandate": "risk", "sector": "Financials — Banks",
        "horizon": "near_term",
    })
    calls = {"stage1": False}

    def fake_llm(*args, **kwargs):
        if calls["stage1"]:
            return fixture_answer
        calls["stage1"] = True
        return stage1_envelope

    core.call_llm = fake_llm
    try:
        with TestClient(server.app) as client:
            assert client.get("/api/health").status_code == 200
            board = client.get("/api/board").json()
            assert board["counts"]["total"] > 0
            assert client.post("/api/chat", json={"text": "show banks"}).status_code == 200

            sampled = client.post("/api/sample")
            assert sampled.status_code == 200, sampled.text
            ticker = sampled.json()["ticker"]
            assert client.get(f"/api/entry/{ticker}").status_code == 200
            assert client.get("/api/watchlist").status_code == 200

            asked = client.post("/api/stage1/ask", json={"messages": [], "turns": 0,
                                                          "force": True})
            assert asked.status_code == 200 and asked.json()["envelope"]["done"]
            narrowed = client.post("/api/stage1/narrow", json={
                "trail": [], "final_env": json.loads(stage1_envelope)})
            assert narrowed.status_code == 200

            quick = client.post("/api/stage2/quick", json={"ticker": ticker, "use_rag": False})
            assert quick.status_code == 200, quick.text
            compare = client.post("/api/compare", json={"tickers": [ticker, ticker]})
            assert compare.status_code == 200, compare.text
            assert client.delete(f"/api/monitor/{ticker}").status_code == 200
    finally:
        core.call_llm = original_llm



# --------------------------------------------------------------------------- #
#  BENCHMARKS + QUOTES  (industry comparison and the market-quote strip)
# --------------------------------------------------------------------------- #
def test_benchmark_crosswalk_order_and_refusal():
    """The sector -> ISIC crosswalk resolves the overlapping cases, and refuses the rest."""
    import benchmarks

    # Real-estate rules are checked before the trade/transport ones: a landlord letting shop
    # space is a real-estate business, and both of these strings contain a trade word.
    for sector, want in (("Real Estate — Retail Malls", "L"),
                         ("Real Estate — Industrial & Logistics REIT", "L"),
                         ("Consumer Staples — Palm Oil Plantations", "A"),
                         ("Materials — Metals & Mining (Nickel/Gold)", "BTE"),
                         ("Financials — Banks", "K"),
                         ("Communication Services — Telecom", "J")):
        hit = benchmarks.isic_for_sector(sector)
        assert hit and hit["code"] == want, f"{sector} -> {hit} (wanted {want})"

    # Never guessed into the nearest bucket.
    for sector in ("", "unknown", "All", "Fictional — Nonsense Industry"):
        assert benchmarks.isic_for_sector(sector) is None, sector


def test_benchmark_oecd_table_is_real_and_ordered():
    """The bundled OECD table parses, carries its provenance, and ranks cleanest-first."""
    import benchmarks

    book = benchmarks.load_oecd()
    assert book["available"], "no OECD benchmark file — run scripts/build_oecd_benchmark.py"
    rows = book["rows"]
    assert len(rows) >= 8, len(rows)
    ints = [r["intensity_t_per_musd"] for r in rows]
    assert ints == sorted(ints), "rows must be ordered cleanest-first"
    assert all(r["rank_cleanest"] == i + 1 for i, r in enumerate(rows))
    # Provenance is not optional: every number on screen has to be traceable.
    for key in ("basis", "retrieved", "emissions", "value_added"):
        assert book["meta"].get(key), f"missing provenance: {key}"
    # A sanity anchor on the physics: finance is not more emissions-intense than agriculture.
    by_code = {r["isic_code"]: r["intensity_t_per_musd"] for r in rows}
    assert by_code["K"] < by_code["C"] < by_code["A"], by_code


def test_benchmark_refuses_to_difference_unlike_measures():
    """A static score and an evidence-leadership index are both 0-100 and still not comparable."""
    import benchmarks

    static_peers = {"available": True, "average": 59.5, "n": 9,
                    "metric": "mean static ESG score", "metric_kind": "static", "unit": "0-100"}
    evidence_peers = dict(static_peers, metric_kind="evidence",
                          metric="mean ESG-leadership (derived from cited ratings)")

    def compare(peers):
        saved = benchmarks.asean_for_sector
        benchmarks.asean_for_sector = lambda *a, **k: peers
        try:
            return benchmarks.compare_company(
                {"company": "X", "sector": "Financials — Banks", "esg_score": 72.0})
        finally:
            benchmarks.asean_for_sector = saved

    same = compare(static_peers)
    assert same["gap_vs_asean"] == 12.5, same["gap_vs_asean"]
    assert "Ahead" in same["verdict"]

    unlike = compare(evidence_peers)
    assert unlike["own_score"] == 72.0, "both numbers still shown"
    assert unlike["gap_vs_asean"] is None, "must not difference unlike measures"
    assert "Not differenced" in unlike["own_score_note"]


def test_benchmark_never_reads_a_static_rating_of_unknown_direction():
    """An incumbent risk score runs the other way; it is reported unknown, not differenced."""
    import benchmarks

    company = {"company": "Y", "sector": "Financials — Banks",
               "layer_a": {"esg_score_static": "22.4 (Medium Risk)"}}
    blind = benchmarks.compare_company(company)
    assert blind["own_score"] is None, blind["own_score"]
    assert "direction is not known" in blind["own_score_note"]
    # With the snapshot's direction verdict in hand, the same number becomes usable.
    told = benchmarks.compare_company(company, higher_better=True)
    assert told["own_score"] == 22.4, told["own_score"]


def test_upload_carries_its_peer_score():
    """An uploaded esg_score rides through coercion so the benchmark has something to compare."""
    import datasource

    payload = json.dumps({"company": "Uploaded Co", "ticker": "SGX:UPLD",
                          "sector": "Financials — Banks", "esg_score": 72.0}).encode()
    company, meta = datasource.load_upload("x.json", payload)
    assert meta["mode"] == "json"
    assert company.get("esg_score") == 72.0, company.get("esg_score")
    assert company.get("_score_higher_better") is True
    # Out-of-range or non-numeric values are dropped rather than carried through.
    for bad in (None, "n/a", 420, True):
        body = json.dumps({"company": "C", "ticker": "T", "sector": "S", "esg_score": bad}).encode()
        c, _ = datasource.load_upload("x.json", body)
        assert "esg_score" not in c, bad


def test_quotes_mapping_gaps_and_offline():
    """Ticker mapping, the documented gaps, and best-effort failure — all without a network."""
    import quotes

    assert quotes.yahoo_symbol("SGX:D05") == "D05.SI"
    assert quotes.yahoo_symbol("IDX:BBRI") == "BBRI.JK"
    # PSE is not on the Yahoo path at all — it has its own provider, so no symbol is guessed.
    assert quotes.yahoo_symbol("PSE:AC") is None, "PSE is not keyed by a Yahoo symbol"
    assert quotes.yahoo_symbol("nonsense") is None

    # The fictional demo universe must never be handed a price.
    demo = quotes.quote("SGX:DBKO", demo=True)
    assert demo["available"] is False and "fictional" in demo["reason"]

    # PSE used to be a documented gap: the only instruments on the main source are US OTC ADRs,
    # a different security, and showing one under the local ticker would be a quiet substitution.
    # It is now served from the PSE's OWN board instead — a real local line in PHP, and the
    # company name is read back and compared to ours before any price is shown.
    ph = quotes.quote("PSE:AC", company="Ayala Corporation")
    assert ph["available"] and ph["currency"] == "PHP", ph
    assert ph["exchange"] == "Philippine Stock Exchange", ph
    # The stored snapshot answers first and is trusted — it was written only AFTER the name check
    # passed at capture time — so the guard itself is exercised on the live path, not through it.
    saved_prices, quotes._PRICES = quotes._PRICES, {}
    try:
        wrong = quotes.quote("PSE:AC", company="Some Other Company Bhd")
        assert wrong["available"] is False, "a name that is not ours must never return a price"
    finally:
        quotes._PRICES = saved_prices

    # A gap that remains a gap still explains itself rather than saying "unavailable".
    assert "Vietnamese" in (quotes.gap_reason("HOSE:REE") or "")

    # A dead network degrades, never raises (HARD RULE 1).
    saved = quotes.core.http_get
    quotes._CACHE.clear()
    quotes.core.http_get = lambda *a, **k: (_ for _ in ()).throw(core.FetchError("boom"))
    try:
        out = quotes.quote("SGX:D05")
    finally:
        quotes.core.http_get = saved
        quotes._CACHE.clear()
    assert out["available"] is False and "D05.SI" in out["reason"]


def test_lseg_shape_cache_bust_and_offline():
    """LSEG's public ESG scores: the wire shape, the cache-busting URL, and degradation.

    Three things are pinned here because all three are load-bearing and none is obvious:

    1. **The RIC has to sit in the URL PATH.** LSEG's dispatcher caches
       `esg_ratings_copy.details.json` by path and ignores `?ricCode=`, so a plain querystring
       call returns whichever company was asked for FIRST — under that company's own name, so
       nothing looks broken. Wiring it up naively paints one issuer's rating onto another
       issuer's card. If someone "simplifies" `_details_url` back to a bare querystring, this
       test is what stops it reaching a demo.
    2. **An uncovered company is `{}`, never zeros.** LSEG answer 200-with-empty-body for a
       name they do not cover; turning that into a wall of 0.0 scores would be fabrication
       (rule 2).
    3. **A dead network degrades** to None rather than raising (rule 1).
    """
    import lseg

    ric = "DBSM.SI"
    url = lseg._details_url(ric)
    # The RIC must be in the path, not only the querystring — see point 1.
    assert ".details.dbsm-si.json" in url, url
    assert url.split("?")[0].endswith(".details.dbsm-si.json")
    assert "ricCode=DBSM.SI" in url, "the servlet still reads the param; the path is for the cache"

    wire = {
        "TR.ESGScore": "3.3",
        "TR.EnvironmentalPillarESGScore": "3.8", "TR.ClimateTransitionThemeScore": "4",
        "TR.EnergyandResourceUseThemeScore": "3", "TR.BiodiversityThemeScore": "3",
        "TR.WaterUseThemeScore": "3", "TR.WasteandPollutionThemeScore": "2",
        "TR.SocialPillarESGScore": "5.0", "TR.LabourRelationsThemeScore": "5",
        "TR.HealthandSafetyThemeScore": "2", "TR.HumanRightsandCommunityThemeScore": "5",
        "TR.GovernancePillarESGScore": "2.9", "TR.BoardandManagementThemeScore": "3",
        "TR.ShareholdersRightsThemeScore": "1", "TR.ConductandAntiCorruptionThemeScore": "3",
        "TR.TaxTransparencyandAccountingThemeScore": "4",
        "TR.CommonName": "DBS Group Holdings Ltd", "industryType": "Banking Services",
        "periodenddate": "2025", "esgLsegRank": "70", "esgLsegTotalIndustries": "936",
    }

    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        seen["headers"] = kw.get("headers") or {}
        return json.dumps(wire)

    saved = lseg.core.http_get
    lseg.core.http_get = fake_get
    try:
        out = lseg.fetch_scores(ric, use_cache=False)
    finally:
        lseg.core.http_get = saved

    # The Referer is mandatory: without it the endpoint 200s with an empty body.
    assert "Referer" in seen["headers"], "the endpoint returns {} with no Referer"

    assert out["company"] == "DBS Group Holdings Ltd"
    assert out["esg_score"] == 3.3 and out["scale_max"] == 5
    assert out["band"] == "Established", out["band"]          # LSEG's own 0-5 legend
    assert out["fiscal_year"] == "2025" and out["industry"] == "Banking Services"
    assert out["rank"] == 70 and out["rank_total"] == 936 and out["rank_top_pct"] == 7.5
    assert out["_origin"] == "lseg-public" and out["attribution"]

    # Twelve themes under three pillars — LSEG's taxonomy, in their order.
    assert [p["label"] for p in out["pillars"]] == ["Environmental", "Social", "Governance"]
    assert [len(p["themes"]) for p in out["pillars"]] == [5, 3, 4]
    assert out["pillars"][1]["score"] == 5.0 and out["pillars"][1]["band"] == "Leading"

    # An uncovered issuer is empty, and empty is None — never a wall of zeros (point 2).
    lseg.core.http_get = lambda *a, **k: "{}"
    try:
        assert lseg.fetch_scores("NOPE.XX", use_cache=False) is None
    finally:
        lseg.core.http_get = saved

    # A dead network degrades rather than raising (point 3).
    lseg.core.http_get = lambda *a, **k: (_ for _ in ()).throw(core.FetchError("boom"))
    try:
        assert lseg.fetch_scores(ric, use_cache=False) is None
        assert lseg.fetch_covered_universe(use_cache=False) == []
        assert lseg.resolve_ric("DBS Group Holdings", "SGX", use_cache=False) is None
    finally:
        lseg.core.http_get = saved


def test_lseg_resolves_asean_names_without_a_network():
    """Name -> RIC matching, on a stubbed cover list. Strict on purpose.

    A loose matcher does not fail loudly — it silently returns a DIFFERENT company's rating,
    which is worse than returning nothing. So the ASEAN legal-form noise ('Malayan Banking
    (Maybank)' vs 'Malayan Banking Bhd') must resolve, an unrelated name must not, and the
    exchange must scope the search so two markets cannot cross-match.
    """
    import lseg

    rows = [
        {"companyName": "DBS Group Holdings Ltd", "ricCode": "DBSM.SI"},
        {"companyName": "Malayan Banking Bhd", "ricCode": "MBBM.KL"},
        {"companyName": "Bank Central Asia Tbk PT", "ricCode": "BBCA.JK"},
        {"companyName": "Antam (Persero) Tbk PT", "ricCode": "ANTM.JK"},
        {"companyName": "DBS Bank India Ltd", "ricCode": "DBSI.NS"},
    ]
    saved = lseg.core.http_get
    lseg.core.http_get = lambda *a, **k: json.dumps(rows)
    try:
        r = lambda n, x="": lseg.resolve_ric(n, x, use_cache=False)  # noqa: E731
        assert r("DBS Group Holdings", "SGX") == "DBSM.SI"
        assert r("Malayan Banking (Maybank)", "Bursa Malaysia") == "MBBM.KL"
        assert r("Bank Central Asia (BCA)", "IDX") == "BBCA.JK"
        # The one name the fuzzy matcher cannot reach is a hand-checked override, not a guess.
        assert r("Aneka Tambang (ANTAM)", "IDX") == "ANTM.JK"
        # The exchange scopes the pool, so an Indian DBS listing cannot answer for the SGX one.
        assert r("DBS Group Holdings", "SGX") != "DBSI.NS"
        # Nothing plausible -> nothing, rather than the nearest row.
        assert r("Totally Unrelated Mining Corp", "SGX") is None
    finally:
        lseg.core.http_get = saved


def test_sensitivity_is_pure_and_finds_load_bearing_signals():
    """Leave-one-out over the evidence: pure, cohort-aware, and it actually discriminates.

    Four things are pinned, because each is a way this could be quietly wrong:

    1. PURE. `flip_analysis` on the same run twice is byte-identical. It re-runs the aggregation
       and the label rules, so if it ever picked up a clock or a random tie-break the "what
       would change this verdict" panel would change on its own — which is precisely the failure
       we accuse a stale rating of.
    2. IT DOES NOT MUTATE THE RUN. The analysis re-scores the company many times; a re-score
       that wrote back would corrupt the run every panel on the board reads from.
    3. THE COHORT IS HELD. `momentum_percentile` is a RANK, so a leave-one-out that re-scored the
       company in isolation would get the momentum right and the QUADRANT wrong. Removing a
       signal must move only this company's slot in the cohort.
    4. IT DISCRIMINATES. A check that only proves it runs would pass on a function that returns
       "nothing is load-bearing" for everybody. The demo universe must contain both a company
       whose label survives every single removal and one where at least one signal decides it.
    """
    import copy

    import engine
    import engine_config
    import sensitivity
    import universe

    cfg = engine_config.for_horizon(engine_config.DEFAULT_HORIZON)
    path = universe.active_file(True)
    run = engine.run_engine(universe.constituents(path), metadata={}, config=cfg)
    assert run["records"], "demo universe scored no companies"

    first = run["records"][0]["company_id"]
    before = copy.deepcopy(run)

    a = sensitivity.flip_analysis(run, first, cfg)
    b = sensitivity.flip_analysis(run, first, cfg)
    assert a == b, "flip_analysis is not deterministic"
    assert run == before, "flip_analysis mutated the run it was given"

    assert sensitivity.flip_analysis(run, "NOT:AREAL:TICKER", cfg) is None

    # Every row re-labels inside the cohort, so `label_without` has to be a real label key.
    valid = set(engine_config.label_order(cfg))
    for row in a["signals"]:
        assert row["label_without"] in valid, row["label_without"]
        assert row["published_at"] or row["published_at"] == ""
    assert len(a["margins"]) == 5
    # Nearest first — the panel leads with the boundary worth watching.
    dists = [abs(m["distance"]) for m in a["margins"]]
    assert dists == sorted(dists), "margins are not ordered by distance"

    solid = narrow = 0
    for record in run["records"]:
        out = sensitivity.flip_analysis(run, record["company_id"], cfg)
        assert out["load_bearing_count"] == sum(1 for r in out["signals"] if r["flips"])
        if out["signal_count"] and out["load_bearing_count"] == 0:
            solid += 1
        elif out["load_bearing_count"]:
            narrow += 1
    assert solid and narrow, (
        f"analysis does not discriminate: {solid} corroborated, {narrow} load-bearing")


def test_backtest_series_on_disk_is_shaped_for_the_panel():
    """The track-record panel draws straight off docs/backtest/series.json.

    It is checked here rather than trusted because the file is REGENERATED by
    `backtest_timeline.py`, so a change there could silently drop a field the panel needs and the
    only symptom would be an empty chart in front of a judge. The known-failure case is asserted
    to still be present: a backtest you can only pass is not a backtest."""
    path = os.path.join(ROOT, "docs", "backtest", "series.json")
    blob = json.load(open(path, encoding="utf-8"))
    cases = blob.get("cases") or []
    assert len(cases) >= 5, f"expected the five validation cases, got {len(cases)}"
    for c in cases:
        for key in ("case_id", "company", "ticker", "cutoff_date", "outcome",
                    "outcome_date", "baseline", "points", "final", "is_known_failure"):
            assert key in c, f"{c.get('case_id')} is missing {key}"
        assert c["points"], f"{c['case_id']} has no series points"
        for p in c["points"]:
            assert set(("date", "momentum", "label")) <= set(p), p
            assert -1.0 <= p["momentum"] <= 1.0, p
        # Every point must be scored from evidence dated before the cutoff.
        assert max(p["date"] for p in c["points"]) <= c["cutoff_date"], c["case_id"]
        assert "value" in c["baseline"] and "note" in c["baseline"]
    assert any(c["is_known_failure"] for c in cases), (
        "the case we got wrong has been dropped from the set")



def test_financial_parse_traps():
    """The three ways a net-income cell produced a confidently WRONG growth rate.

    Every one of these shipped a plausible number under a real company's name, which is the
    failure mode this codebase keeps getting bitten by — nothing looks broken on screen.
    """
    import financials

    # (1) A parenthetical figure on a DIFFERENT scale. "S$789m (S$1.1b cont. ops)" read the "b"
    # from the parenthetical and multiplied the 789 MILLION by a thousand -> +83,836% growth.
    assert financials.parse_amount("FY2025 S$789m (S$1.1b cont. ops)") == 789.0
    assert financials.parse_amount("FY2024 S$940m") == 940.0

    # (2) A RANGE. "~RM3.3-3.4b" took 3.3 with no unit (3.3 million) against a RM3.1 BILLION
    # prior year -> -99.9%, which read as a bank that had almost stopped earning.
    mid = financials.parse_amount("FY2025 ~RM3.3-3.4b")
    assert mid is not None and 3300.0 < mid < 3400.0, mid

    # (3) A PART-YEAR figure. "9M2024" has no word boundary before the year, so the fiscal-year
    # stripper missed it and the leading "9" was taken as the amount -> -98.3%. A nine-month
    # figure is not comparable to a full year at all, so the growth rate must be SUPPRESSED
    # rather than computed off two different period lengths.
    read = financials.earnings_read({"fy_minus1_net_income": "9M2024 RM606m (last public)",
                                     "fy_minus2_net_income": "FY2023 RM543m"})
    assert read["growth_pct"] is None, read
    assert read["direction"] == "not comparable", read

    # A loss-maker is never auto-failed: the traction screen decides, and an unrun screen is
    # `unknown`, not `weak`. Scoring our own missing data as the company's failure is the exact
    # error `traction.py` exists to refuse.
    v = financials.viability({"profitability_flag": "loss_making",
                              "fy_minus1_net_income": "FY2025 -THB14.6b LOSS",
                              "fy_minus2_net_income": "FY2024 -THB29.8b LOSS"})
    assert v["verdict"] == "unknown", v


def test_financials_never_reach_the_engine():
    """The financial read is a GATE and must stay outside the score.

    `engine.py` and `signals.py` must not import `financials` or `rationale`, directly or
    transitively. If either ever did, momentum would silently carry an earnings term and
    `disagreement` would stop meaning what every surface says it means.
    """
    import engine
    import signals
    for mod in (engine, signals):
        names = {getattr(v, "__name__", "") for v in vars(mod).values()}
        assert "financials" not in names, f"{mod.__name__} imports financials"
        assert "rationale" not in names, f"{mod.__name__} imports rationale"


def test_rationale_always_states_the_case_against():
    """A case that only lists reasons to agree is marketing.

    The strongest company in the set must still carry cons, and a company with NO evidence must
    say that plainly rather than rendering as a clean sheet.
    """
    import rationale

    strong = rationale.build(
        {"company_id": "X:Y", "company": "Test", "label": "hidden_winners",
         "label_display": "Hidden Winners", "composite_momentum": 0.9,
         "composite_confidence": 0.8, "signal_count": 12, "disagreement": 0.7,
         "lseg_percentile": 0.1, "breadth": 5, "coverage": 1.0, "corroboration": 1.0,
         "components": {"E": 1.0}, "signals": [{"source_type": "regulator",
                                                "published_at": "2026-01-01"}]},
        {"profitability_flag": "profitable", "fy_minus1_net_income": "FY2025 S$2b",
         "fy_minus2_net_income": "FY2024 S$1b"})
    assert strong["esg"]["cons"], "a verdict with no counter-evidence listed is marketing"
    assert strong["watch_outs"], "every case must say what would change it"

    empty = rationale.build(
        {"company_id": "X:Z", "company": "Nothing", "label": "consensus",
         "label_display": "Consensus", "composite_momentum": 0.0, "composite_confidence": 0.0,
         "signal_count": 0, "disagreement": 0.0, "lseg_percentile": 0.5, "breadth": 0,
         "components": {}, "signals": []}, {})
    joined = " ".join(empty["esg"]["cons"]).lower()
    assert "absence of evidence" in joined, empty["esg"]["cons"]



def test_failed_harvest_cannot_erase_stored_evidence():
    """A rate-limited sweep must never empty a company's stored harvest.

    This shipped: the first full 52-company sweep was throttled partway through, 14 companies
    returned every angle `offline`, and because `save` overwrote, the empty results replaced good
    evidence. Total 2025 events fell 63 -> 48 and nothing said so, because a company with no
    evidence is indistinguishable on screen from one that was never swept. An absence rendered as
    a finding -- the same shape as every other trap in this codebase.
    """
    import json
    import os
    import harvest

    os.makedirs(harvest.HARVEST_DIR, exist_ok=True)
    path = os.path.join(harvest.HARVEST_DIR, "SELFTEST_X.json")
    stored = [{"text": "a real dated event", "source_url": "https://x/1",
               "published_at": "2025-01-01"}]
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"company_id": "SELFTEST:X", "events": stored}, fh)

        # A failed sweep keeps nothing. It must not win.
        harvest.save({"company_id": "SELFTEST:X", "events": [], "status": "emissions: offline"})
        with open(path, encoding="utf-8") as fh:
            after = json.load(fh)
        assert len(after["events"]) == 1, after
        assert "kept prior evidence" in after["status"], after["status"]

        # Even an explicit replace cannot empty it -- there is no legitimate reason for a failed
        # fetch to delete data it did not replace.
        harvest.save({"company_id": "SELFTEST:X", "events": [], "status": "offline"}, replace=True)
        with open(path, encoding="utf-8") as fh:
            assert len(json.load(fh)["events"]) == 1

        # A successful sweep UNIONS rather than overwrites, deduped.
        harvest.save({"company_id": "SELFTEST:X", "status": "ok", "events": stored + [
            {"text": "a second dated event", "source_url": "https://x/2",
             "published_at": "2025-02-02"}]})
        with open(path, encoding="utf-8") as fh:
            assert len(json.load(fh)["events"]) == 2
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_board_never_says_awaiting_data_at_its_own_engine_record():
    """The classification strip and the RadarHub chip read the ENGINE, not the demo momentum block.

    `metrics.classify` reads a `momentum` block only the FICTIONAL demo set carries, so once the
    real basket landed every real company classified as "AWAITING DATA" — printed directly above
    a rationale panel naming the engine's verdict for that same company. Two adjacent widgets
    disagreeing about whether we hold data is worse than either answer alone.
    """
    import server
    run, _meta, _cfg = server._engine_run(False, "long")
    recs = {r["company_id"]: r for r in run["records"]}
    cons = universe.constituents()
    hlbk = next(c for c in cons if c["ticker"] == "KLSE:HLBK")

    # the false negative this exists to stop: the raw classifier still cannot see the evidence
    assert metrics.classify(hlbk)["label"] == "AWAITING DATA", metrics.classify(hlbk)

    card = metrics.classify_from_record(recs["KLSE:HLBK"])
    assert card and card["label"] == recs["KLSE:HLBK"]["label_display"], card
    assert card["label"] != "AWAITING DATA", card
    assert "8 dated signals" in card["line"], card          # the count the engine actually holds
    assert "71st" in card["line"] and "71th" not in card["line"], card   # ordinals, not "71th"

    # tone is not decoration: the two negative quadrants must never render as good news
    assert metrics.classify_from_record(recs["SET:PTT"])["tone"] == "bad", "PTT is overrated_leaders"
    assert metrics.classify_from_record(recs["KLSE:RHBBANK"])["tone"] == "good", "RHB is a winner"

    # no record -> no verdict invented; the honest "awaiting data" has to survive
    assert metrics.classify_from_record(None) is None
    assert metrics.classify_from_record({}) is None
    assert metrics.classify_from_record({"label_display": "X"}) is None   # nothing to say -> None


def test_market_symbols_are_a_column_not_a_name_search():
    """Prices resolve through an audited column, and only for confirmed EQUITIES.

    Our tickers carry mnemonics; Singapore and Malaysia key their listings by the exchange's own
    code, so "DBS.SI" and "RHBBANK.KL" do not exist and 32 of 52 had no price. The gap is closed
    by `data/market_symbols.csv`, resolved once offline — never by a runtime name search, which
    is how Malaysia Airports once rendered I-Bhd's data under Malaysia Airports' name.
    """
    import csv as _csv
    import quotes
    from scripts.resolve_market_symbols import matches

    with open(os.path.join(ROOT, "data/market_symbols.csv"), newline="", encoding="utf-8") as fh:
        rows = list(_csv.DictReader(fh))
    assert len(rows) == 52, len(rows)
    resolved = [r for r in rows if r["symbol"]]
    assert len(resolved) >= 43, len(resolved)

    # the column, not the naive construction, is what the runtime reads
    assert quotes.yahoo_symbol("SGX:DBS") == "D05.SI", quotes.yahoo_symbol("SGX:DBS")
    assert quotes.yahoo_symbol("KLSE:RHBBANK") == "1066.KL"
    assert quotes.yahoo_symbol("SET:PTT") == "PTT.BK"        # already right, left alone

    # the two DELISTED names must never carry a symbol, and PSE is not on this source at all
    for tk in ("KLSE:MAHB", "SET:INTUCH"):
        assert not [r for r in resolved if r["ticker"] == tk], tk
    assert not [r for r in resolved if r["ticker"].startswith("PSE:")]

    # ...but the Philippine names DO have prices, from the PSE's own board rather than from a
    # US OTC ADR standing in for the local line. Verified by NAME before a price is shown.
    prices = json.load(open(os.path.join(ROOT, "data/market_prices.json"), encoding="utf-8"))
    stored_quotes = prices.get("quotes") or {}
    for tk in ("PSE:AC", "PSE:BDO", "PSE:SMPH"):
        row = stored_quotes.get(tk)
        assert row and row.get("currency") == "PHP", (tk, row)
        assert row.get("exchange") == "Philippine Stock Exchange", row
        assert "phisix" in (row.get("source") or ""), row
    # the guard: a code whose name is not our company yields nothing
    assert quotes._pse_quote("PSE:AC", "Totally Different Company") is None
    assert quotes._same_company("SM Investments Corp", "SM Investments Corporation")
    assert not quotes._same_company("Ayala Corporation", "Ayala Land, Inc.")

    # a delisted constituent has no price ANYWHERE, and that is the finding, not a gap
    for tk in ("KLSE:MAHB", "SET:INTUCH"):
        assert tk not in stored_quotes, tk
    assert len(stored_quotes) == 50, len(stored_quotes)

    # every resolved row names the company the EXCHANGE files it under, and it has to be ours
    for r in resolved:
        ok, why = matches(r["company"], r["resolved_name"])
        assert ok or r["basis"].startswith("manual"), (r["ticker"], r["resolved_name"], why)
        assert r["currency"], r["ticker"]

    # the trap this exists to stop: a fund that merely MENTIONS the company is not the company
    assert not matches("OCBC", "Lion-OCBC Securities APAC Financials Dividend Plus ETF")[0]
    assert matches("OCBC", "Oversea-Chinese Banking Corporation Limited")[0]
    assert matches("Bangkok Dusit Med Service",
                   "Bangkok Dusit Medical Services Public Company Limited")[0]


def test_news_is_gathered_never_written():
    """Headlines are copied from search results, guarded, and a blocked sweep cannot erase them.

    There is no LLM anywhere in `news.py`: a search result already IS a title and a URL, so asking
    a model to produce one would only create a chance to invent one. The guards are the module.
    """
    import news

    # 1 - the headline has to name THIS company. A search for a mid-cap returns its neighbours,
    #     and a story about the wrong one under this one's name is the resolve_ric failure again.
    assert news.names_the_company("RHB gets BNM nod on insurance disposal", "RHB Bank Bhd")
    assert not news.names_the_company("Maybank posts record quarter", "RHB Bank Bhd")

    # 2 - a stock-quote page is not a story, however well it matches the name
    assert not news.is_article("DBS Group Holdings Ltd | Reuters", "DBS Group")
    assert not news.is_article("RHB Bank Bhd: Official Announcements - Stock Market News", "RHB Bank Bhd")
    assert news.is_article("Higher total income buoys RHB Bank showing - The Star", "RHB Bank Bhd")

    # 3 - a date is the article's own or it is absent; a future date is never a publication date
    today = "2026-08-25"
    assert news._dated("18 April 2024 the bank said", today) == "2024-04-18"
    assert news._dated("aims for net zero by 2050", today) is None      # the harvest's own bug
    assert news._dated("no date here at all", today) is None
    # A bare year resolves to a mid-year placeholder (`stated_year`), which is an ordering aid and
    # NOT a publication date. The card would print it as one, so it is refused.
    assert news._dated("in 2024 the bank raised", today) is None

    # 4 - THE ONE THAT MATTERS: a throttled sweep must not replace real headlines with nothing.
    blocked = {"ticker": "TEST:X", "items": [], "blocked": True}
    saved, why = news.save_unless_worse(blocked)
    assert saved is None and "blocked" in (why or ""), (saved, why)

    # and the green-bond angle is in the list, because issuance is what moves N to M
    assert any("green bond" in a for a in news.ANGLES), news.ANGLES
    assert len(news.ANGLES) == 3, news.ANGLES


def test_pipeline_bucket_is_on_the_company_not_just_the_total():
    """N/M/K is readable per company, the three are disjoint, and the badge carries its own rule.

    The counts strip has shown N/M/K since B2, but a reader looking at ONE company could not tell
    which bucket it was in — the most commercially interesting label in the product existed only
    as a total. This is a display join over the same run: no new scoring, no new run id.
    """
    import pipeline_counts
    import server

    run, meta, cfg = server._engine_run(False, "long")
    nmk = pipeline_counts.counts(run, meta, cfg)
    buckets = pipeline_counts.bucket_of(nmk)

    # the map must reproduce the counts exactly, or the badge and the strip disagree on screen
    for key in ("N", "M", "K"):
        assert sum(1 for v in buckets.values() if v == key) == nmk[key], key

    # disjoint by construction: M excludes existing issuers, K is the explicit remainder
    members = nmk["members"]
    assert not (set(members["N"]) & set(members["M"])), "an issuer cannot also be a lead"
    assert not (set(members["K"]) & (set(members["N"]) | set(members["M"])))

    # every badge states the rule that put it there, so it can be defended on a slide
    for tk, bucket in buckets.items():
        badge = pipeline_counts.bucket_badge(bucket, nmk)
        assert badge["bucket"] == bucket and badge["note"], (tk, badge)

    # a company in none of the three says so, rather than rendering blank
    none_badge = pipeline_counts.bucket_badge("", nmk)
    assert none_badge["bucket"] == "" and "Not in the pipeline" in none_badge["display"]

    # and the board actually ships it
    block = server._engine_block(False, universe.constituents(), "long")
    assert block["badges"]["KLSE:RHBBANK"]["pipeline"]["bucket"] == "M"
    assert block["badges"]["SGX:UOB"]["pipeline"]["bucket"] == "N"



def test_client_brief_prepares_evidence_and_never_recommends():
    """The analyst's book. The brief is the one surface where HARD RULE 4 would be most tempting
    to break — "prepare me for this client meeting" reads like an invitation to say what to
    pitch — so the guard is pinned here rather than trusted to review."""
    import brief
    import clients

    book = clients.load_all()
    assert book, "the fictional client book should ship with the repo"
    # 1 - the roster is FICTIONAL and says so on every record, the hero_company.json discipline.
    for c in book:
        assert c.get("_origin") == "fictional", c.get("client_id")

    run = {
        "run_id": "run_now", "as_of": "2026-08-20",
        "records": [
            {"company_id": "X:A", "company": "Alpha", "label": "hidden_winners",
             "label_display": "Hidden Winners", "composite_momentum": 0.7,
             "composite_confidence": 0.8, "signal_count": 12, "disagreement": 0.6,
             "momentum_percentile": 0.9, "lseg_percentile": 0.3, "country": "SG",
             "industry": "Banks", "signals": []},
            {"company_id": "X:B", "company": "Beta", "label": "consensus",
             "label_display": "Consensus", "composite_momentum": 0.1,
             "composite_confidence": 0.2, "signal_count": 0, "disagreement": 0.05,
             "momentum_percentile": 0.4, "lseg_percentile": 0.35, "country": "TH",
             "industry": "Cement", "signals": []},
        ],
    }
    client = {
        "client_id": "t", "name": "Test Account", "account_type": "long_only",
        "desk": "d", "mandate": "return", "coverage": ["X:A", "X:B"], "_origin": "fictional",
        "meetings": [{
            "date": "2026-08-01", "run_id": "run_then", "as_of": "2026-08-01",
            "follow_ups": [{"text": "send the sources", "done": False}],
            "snapshot": {
                "X:A": {"label": "consensus", "label_display": "Consensus",
                        "composite_momentum": 0.2, "composite_confidence": 0.3,
                        "signal_count": 4, "disagreement": 0.6, "company": "Alpha"},
                "X:B": {"label": "consensus", "label_display": "Consensus",
                        "composite_momentum": 0.1, "composite_confidence": 0.2,
                        "signal_count": 0, "disagreement": 0.05, "company": "Beta"},
            },
        }],
    }

    # 2 - THE DELTA. A crossed quadrant boundary outranks everything else, because it is the only
    #     move that changes what we are CLAIMING about the company.
    d = clients.delta(client, run)
    assert d["has_baseline"] and d["since"] == "2026-08-01"
    assert d["changes"][0]["company_id"] == "X:A"
    assert d["changes"][0]["kind"] == "label_move"
    assert d["changes"][0]["signals_delta"] == 8
    # a name that did not move is counted, not listed
    assert d["unchanged"] == 1 and len(d["changes"]) == 1

    # 3 - a FIRST meeting has no baseline and must say so. Diffing against an implied zero would
    #     report every position as a dramatic move on the day you met them.
    fresh = dict(client, meetings=[])
    d0 = clients.delta(fresh, run)
    assert d0["has_baseline"] is False and d0["changes"] == [] and d0.get("note")

    # 4 - the snapshot stores only what the client was SHOWN, never the whole record.
    snap = clients.snapshot_for(run, ["X:A"])
    assert set(snap["X:A"]) <= set(clients.SNAP_FIELDS) | {"company"}
    assert "signals" not in snap["X:A"] and "components" not in snap["X:A"]

    b = brief.build(client, run, {}, None, with_flip=False)

    # 5 - THE ONE THAT MATTERS: no recommendation, anywhere in the rendered document. The brief
    #     prepares evidence; the analyst forms the view.
    md = brief.to_markdown(b).lower()
    for banned in ("buy", "sell", "overweight", "underweight", "we recommend", "price target",
                   "outperform", "accumulate"):
        assert banned not in md, "brief must never carry a recommendation: %r" % banned
    assert "not investment advice" in md

    # 6 - the case AGAINST is present and is never dropped, and a zero-evidence name is reported
    #     as having nothing to disagree with rather than as a quiet blank.
    assert b["objections"], "a brief with no challenges gets the analyst ambushed"
    gaps = " ".join(u["gap"] for u in b["unknowns"])
    assert "no dated evidence" in gaps.lower()

    # 7 - composed by rule, so the same run always yields the same document.
    assert b["no_llm"] is True
    assert brief.to_markdown(brief.build(client, run, {}, None, with_flip=False)) == \
        brief.to_markdown(b)

    # 8 - section numbering follows what is EMITTED. The first-meeting brief has no follow-ups
    #     section, and the numbering must not skip over the hole.
    md2 = brief.to_markdown(brief.build(fresh, run, {}, None, with_flip=False))
    heads = [ln for ln in md2.splitlines() if ln.startswith("## ")]
    assert [h.split(" ")[1] for h in heads] == [str(i + 1) for i in range(len(heads))], heads


def test_industry_bar_joins_directly_and_carries_its_unit():
    """The industry table read the ISIC CROSSWALK, which resolves 4 of 22 industries — so 18 read
    "unmatched", including Banks, the largest bucket at 15 companies, while the per-company panel
    on the same board showed that industry's bar correctly. One board, two answers."""
    import benchmarks

    table = benchmarks.industry_table()
    priced = [r for r in table if r["bench_intensity"] is not None]
    assert len(priced) == len(table), (
        "every industry in the basket has a direct benchmark row: %d of %d"
        % (len(priced), len(table)))

    # the direct join is on CGSI's OWN industry label, so Banks resolves to the Eurostat figure
    banks = next(r for r in table if r["sector"] == "Banks")
    assert banks["bench_basis"] == "direct"
    assert abs(banks["bench_intensity"] - 7.89) < 0.01

    # THE UNIT TRAVELS WITH THE NUMBER. The fallback source is on a different denominator
    # entirely (t CO2e/US$m against g CO2e/EUR); a unit in the column header would silently
    # relabel it, which is the same class of error as differencing an ESG score against an
    # emissions intensity.
    for r in priced:
        assert r["bench_unit"], r["sector"]
        assert r["bench_basis"] in ("direct", "crosswalk")
    assert all(r["bench_unit"] == "g CO2e / EUR GVA" for r in priced if r["bench_basis"] == "direct")

    # and the two sources are still kept apart: the crosswalk fields remain readable and are
    # still mostly empty, which is exactly why they are no longer the primary.
    assert sum(1 for r in table if r["oecd_intensity"] is not None) < len(table)


def main():
    raw_fixture = open(os.path.join(ROOT, "fixtures/stage2_answer.json"), encoding="utf-8").read()
    # Mocked grounded-extractor output (what the LLM would return for build_live_company).
    raw_extract = json.dumps({
        "company": "NVIDIA", "ticker": "unknown", "sector": "Technology — Semiconductors",
        "layer_a": {"esg_score_static": "unknown", "as_of_date": "unknown", "note": "Per sources, AI governance is in focus."},
        "layer_b": {"momentum": {"E": {"direction": "unknown", "magnitude": "unknown"},
                                 "S": {"direction": "unknown", "magnitude": "unknown"},
                                 "G": {"direction": "unknown", "magnitude": "unknown"}},
                    "digital_ai_signal": {"ai_governance_hiring_velocity": "unknown",
                                          "ai_disclosure_level": "unknown",
                                          "gap_note": "Sources discuss AI governance scrutiny."},
                    "conflicting_signals": {"news_sentiment": "unknown", "behaviour_trend": "unknown", "conflict_note": ""},
                    "near_term_catalyst": "unknown"}})
    checks = [
        ("on-disk contracts", lambda: test_on_disk_contracts()),
        ("stage 1 builder -> Contract A", lambda: test_stage1_builder()),
        ("stage 1 dynamic quick-reply suggestions", lambda: test_stage1_suggestions()),
        ("stage 2 chain -> Contract C (mocked LLM, RAG bypassed)", lambda: test_stage2_chain(raw_fixture)),
        ("coerce fills 'unknown'", lambda: test_coerce_fills_unknown()),
        ("Contract C coercion (reasoning/sources)", lambda: test_contract_c_coercion()),
        ("CompanyData coercion (full shape, unknowns)", lambda: test_company_data_coercion()),
        ("upload .json is authoritative", lambda: test_upload_json_authoritative()),
        ("live company built grounded (mocked)", lambda: test_live_company_grounded(raw_extract)),
        ("ASEAN universe loads + resolves", lambda: test_universe_loads_and_resolves()),
        ("snapshot_from_company shape", lambda: test_snapshot_shape()),
        ("constituent build identity authoritative (mocked)", lambda: test_constituent_build_grounded(raw_extract)),
        ("metrics aggregates (avg ESG, pillars, hidden winners)", lambda: test_metrics_aggregates()),
        ("metrics graceful with no numeric data", lambda: test_metrics_graceful()),
        ("evidence-mode parse + aggregates (grounded)", lambda: test_evidence_mode()),
        ("company_from_numeric -> Contract B (offline relay input)", lambda: test_company_from_numeric()),
        ("RAG fetch (DuckDuckGo) + TF-IDF rank (mocked http_get)", lambda: test_rag_retrieval()),
        ("RAG gather_context shape (+ AI summary degrade)", lambda: test_rag_gather_context_shape()),
        ("RAG offline graceful fallback", lambda: test_rag_offline_graceful()),
        # --- audit fix-pass regression tests (2026-06-29) ---
        ("MSCI rating extraction grounded (no article 'a', post-upgrade token)", lambda: test_msci_rating_extraction()),
        ("momentum_series(points=1) no ZeroDivisionError", lambda: test_momentum_series_single_point()),
        ("is_new from new_tickers param (no cache mutation)", lambda: test_metrics_new_flag_param()),
        ("snapshot_from_company tolerates numeric esg score", lambda: test_snapshot_numeric_score()),
        ("upload non-object .json rejected with ValueError", lambda: test_upload_nonobject_json_rejected()),
        ("coerce_company_data degrades wrong-typed fields", lambda: test_company_data_coercion_wrong_types()),
        ("load_universe graceful on non-dict/list JSON", lambda: test_universe_nondict_json_graceful()),
        ("universe get/resolve return copies (no leak)", lambda: test_universe_accessors_dont_leak()),
        ("ddg_instant graceful on non-object JSON", lambda: test_ddg_instant_nonobject_graceful()),
        ("cache_read graceful on non-object JSON", lambda: test_cache_read_nonobject_graceful()),
        ("stage1 axis coercion (non-string -> None)", lambda: test_envelope_axis_coercion()),
        ("parse_json robust (trailing brace, fenced value)", lambda: test_parse_json_robust()),
        ("core._env_float guarded against non-numeric env", lambda: test_env_float_guarded()),
        ("stage3._card_md gates all-unknown pillar section", lambda: test_card_md_gates_unknown_signals()),
        ("dataset-origin disclaimer not mislabeled 'live'", lambda: test_dataset_origin_disclaimer()),
        ("[3.13] board_ai_policy tri-state Yes/No/Partial", lambda: test_board_ai_policy_tristate()),
        ("[1.9] universe banner string", lambda: test_universe_banner()),
        ("[#2] compare_companies pure series (no fabrication)", lambda: test_compare_companies()),
        # --- feature backlog pass (2026-06-30) ---
        ("[#17] price_change_pct parses signed %", lambda: test_price_change_pct()),
        ("[#17] price_series illustrative 90d path", lambda: test_price_series()),
        ("[#17] price_series grounded (demo only, real None)", lambda: test_price_series_grounded()),
        ("[#10] financial_snapshot format (market + 90d)", lambda: test_financial_snapshot_have_format()),
        ("[#10] financial_snapshot awaiting (no market)", lambda: test_financial_snapshot_awaiting()),
        ("[#10] financial_snapshot reads _market ride", lambda: test_financial_snapshot_reads_market()),
        ("[#10] company_from_numeric rides _market", lambda: test_company_from_numeric_rides_market()),
        ("[#11] news_card demo headlines", lambda: test_news_card_demo()),
        ("[#11] news_card real -> awaiting (no fab)", lambda: test_news_card_real_awaiting()),
        ("[#11] youtube_search_url deterministic", lambda: test_youtube_search_url()),
        ("[#11] news_card robust to junk", lambda: test_news_card_robust()),
        ("[#11] demo universe news seeded (no url)", lambda: test_demo_universe_news_seeded()),
        ("[#18] analyst_coverage count-only (no verb)", lambda: test_analyst_coverage()),
        ("[#18] analyst_coverage fabrication guard", lambda: test_analyst_coverage_fabrication_guard()),
        ("[2.1] plain_summary (no number leak)", lambda: test_plain_summary()),
        ("[#5] focused check-before-Monday surface", lambda: test_focused_check_before_monday()),
        ("[1.11] fmt_elapsed freshness string", lambda: test_fmt_elapsed()),
        ("[2.2] chat copy In-Depth regression (byte-exact)", lambda: test_chat_copy_indepth_regression()),
        ("[2.2] chat copy Simplified (jargon-free)", lambda: test_chat_copy_simplified()),
        ("[3.7] suggested follow-up chips (context+mode)", lambda: test_suggested_followups()),
        ("esg_data fallback CSV load/save round-trip", lambda: test_esg_data_fallback_roundtrip()),
        ("esg_data normalize indicators to 0-100", lambda: test_esg_data_normalize()),
        ("esg_data parse_upload CSV override", lambda: test_esg_data_parse_upload()),
        ("esg_data get_country_table live->fallback (mocked)", lambda: test_get_country_table_live_then_fallback()),
        ("esg_data cache becomes next fallback (mocked)", lambda: test_cache_becomes_next_fallback()),
        ("esg_data get_country_table never raises when data missing", lambda: test_get_country_table_never_raises_when_data_missing()),
        ("esg_scoring deterministic and bounded [0,100]", lambda: test_esg_scoring_deterministic_and_bounded()),
        ("esg_scoring sector multiplier effect (E/G tilt)", lambda: test_esg_scoring_sector_multiplier_effect()),
        ("esg_scoring variance differs by name (seeded hash)", lambda: test_esg_scoring_variance_differs_by_name()),
        ("demo_enrich deterministic and labelled (no fabricated URLs)", lambda: test_demo_enrich_deterministic_and_labelled()),
        ("demo roster 36 companies, all tickers unique, all countries represented", lambda: test_demo_roster_valid()),
        ("demo roster rejects malformed (missing key / bad country / dup ticker)", lambda: test_demo_roster_rejects_malformed()),
        ("build_demo_universe schema + no real_world_basis leak", lambda: test_build_demo_universe_schema_and_no_leak()),
        ("[task-9] company_from_numeric rides esg_breakdown+provenance and flips note", lambda: test_company_from_numeric_rides_breakdown_and_note()),
        ("[task-9] metrics.esg_breakdown passthrough helper", lambda: test_metrics_esg_breakdown_passthrough()),
        ("snapshot band direction-aware (higher=better demo vs lower=better risk)", lambda: test_snapshot_band_direction_aware()),
        ("benchmark crosswalk order + refuses to guess", lambda: test_benchmark_crosswalk_order_and_refusal()),
        ("OECD industry table parses, ranks and carries provenance", lambda: test_benchmark_oecd_table_is_real_and_ordered()),
        ("benchmark refuses to difference unlike measures", lambda: test_benchmark_refuses_to_difference_unlike_measures()),
        ("benchmark never reads a static rating of unknown direction", lambda: test_benchmark_never_reads_a_static_rating_of_unknown_direction()),
        ("upload carries its peer score through coercion", lambda: test_upload_carries_its_peer_score()),
        ("quotes: mapping, documented gaps, offline degradation", lambda: test_quotes_mapping_gaps_and_offline()),
        ("LSEG scores: wire shape, path cache-bust, no-zeros, offline", lambda: test_lseg_shape_cache_bust_and_offline()),
        ("LSEG name -> RIC resolution (strict, exchange-scoped)", lambda: test_lseg_resolves_asean_names_without_a_network()),
        ("sensitivity: pure, cohort-aware, discriminating",
         lambda: test_sensitivity_is_pure_and_finds_load_bearing_signals()),
        ("backtest series shaped for the track-record panel",
         lambda: test_backtest_series_on_disk_is_shaped_for_the_panel()),
        ("cost model prices cache hits, never writes them off",
         lambda: test_cost_model_prices_cache_hits_rather_than_writing_them_off()),
        ("every real surface scores the same run",
         lambda: test_every_real_surface_scores_the_same_run()),
        ("traction screen: four tests, unknown is not failure",
         lambda: test_traction_screen_states_and_rule()),
        ("harvest guards reject ungrounded events",
         lambda: test_harvest_guards_reject_ungrounded_events()),
        ("LSEG never serves another company's scores",
         lambda: test_lseg_never_serves_another_companys_scores()),
        ("metadata follows its universe (demo -> mock, real -> verified)",
         lambda: test_metadata_follows_its_universe()),
        ("CGSI verified 52 adapts onto the frozen schema (N=13 reproduces)",
         lambda: test_cgsi_basket_adapts_onto_the_frozen_schema()),
        ("sector benchmark joins directly and refuses to guess",
         lambda: test_sector_benchmark_joins_directly_and_refuses_to_guess()),
        ("merkle covers the yardstick and detects a swap",
         lambda: test_merkle_covers_the_yardstick_and_detects_a_swap()),
        ("claim vs evidence labelled illustrative per row",
         lambda: test_claim_vs_evidence_is_labelled_illustrative_per_row()),
        ("financial cell parsing survives ranges, part-years and scale traps",
         lambda: test_financial_parse_traps()),
        ("the financial read never reaches the engine",
         lambda: test_financials_never_reach_the_engine()),
        ("every case states the case against itself",
         lambda: test_rationale_always_states_the_case_against()),
        ("a failed harvest cannot erase stored evidence",
         lambda: test_failed_harvest_cannot_erase_stored_evidence()),
        ("board reads its own engine record, never \"awaiting data\"",
         lambda: test_board_never_says_awaiting_data_at_its_own_engine_record()),
        ("market symbols are an audited column, equities only",
         lambda: test_market_symbols_are_a_column_not_a_name_search()),
        ("news is gathered and guarded, never written by a model",
         lambda: test_news_is_gathered_never_written()),
        ("N/M/K is readable on the company, not only as a total",
         lambda: test_pipeline_bucket_is_on_the_company_not_just_the_total()),
        ("client brief prepares evidence and never recommends",
         lambda: test_client_brief_prepares_evidence_and_never_recommends()),
        ("industry bar joins directly and carries its unit",
         lambda: test_industry_bar_joins_directly_and_carries_its_unit()),
        ("FastAPI primary boundary smoke tests", lambda: test_api_smoke()),
    ]
    failures = skipped = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped += 1
            print(f"  SKIP  {name}: {e}")
        except Exception as e:  # noqa: BLE001 — selftest reports any failure
            failures += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    if failures:
        print(f"FAILED — {failures} check(s) failed.")
        raise SystemExit(1)
    tail = f" ({skipped} skipped — see above)" if skipped else ""
    print("OK — all checks passed (relay wiring + contracts verified, no network used)"
          f"{tail}.")


if __name__ == "__main__":
    main()
