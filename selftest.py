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
    assert universe.resolve("BCA")["country"] == "Indonesia", universe.resolve("BCA")
    assert universe.resolve("SET:KBANK")["company"] == "Kasikornbank", universe.resolve("SET:KBANK")
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
    classification, signals — the numbers behind the command center."""
    cons = universe.constituents(universe.DEMO_FILE)
    assert len(cons) >= 11, len(cons)
    banks = [c for c in cons if c["sector"] == "Financials — Banks"]
    assert len(banks) == 11, len(banks)
    avg, n = metrics.average_esg(banks)
    assert avg is not None and 25 <= avg <= 28 and n == 11, (avg, n)   # ~26.7 peer average
    pillars = {p["key"]: p for p in metrics.pillar_momentum(banks)}
    assert pillars["digital_ai"]["fast"] is True, pillars["digital_ai"]   # the orange riser card
    assert pillars["governance"]["value"] < 0, pillars["governance"]      # softening governance
    hw, peer, _ = metrics.hidden_winners(banks, top_n=5)
    assert hw and hw[0]["company"] == "DemoBank" and hw[0]["value"] == 28, hw[0]
    demo = next(c for c in banks if c["company"] == "DemoBank")
    assert metrics.classify(demo)["label"] == "HIDDEN WINNER", metrics.classify(demo)
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
