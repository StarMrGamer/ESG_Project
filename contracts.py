"""
contracts.py — FROZEN handoff shapes for the relay (the glue).
==============================================================
These are the batons that travel down the pipeline. Shapes are verbatim from CLAUDE.md.

Contract A — NarrowedQuestion (Stage 1 -> Stage 2)
    { "narrowed_question": str,
      "mandate": "risk" | "return" | "compliance",
      "sector": str,
      "horizon": "near_term" | "structural",
      "trail": [ {"axis": str|None, "type": str, "text": str}, ... ] }

Contract B — CompanyData (data -> Stage 2), stored in data/hero_company.json
    { "company", "ticker", "sector", "layer_a": {...}, "layer_b": {...},
      "layer_a_history": { "note": str, "series": [ {"as_of", "esg_score_static"}, ... ],
                           "trend_note": str }   # ADDITIVE, optional — historical baseline }

Contract C — Stage2Answer (Stage 2 -> Stage 3)
    { "question_to_ask", "what_rating_sees", "what_we_see",
      "check_before_monday", "competes_summary",
      "reasoning": [str, ...],                    # ADDITIVE — visible chain-of-thought
      "sources":   [ {"title", "url"}, ... ] }    # ADDITIVE — RAG provenance (real URLs)

ADDITIONS (sign-off 2026-06-23, production pass): Contract B gains optional `layer_a_history`
(historical static-score series) so Stage 2 can reason about TREND, not just a snapshot.
Contract C gains `reasoning` (the chain-of-thought, a list of short steps) and `sources`
(the live-retrieval citations — real titles + URLs, never invented). Both are additive: the
original keys are unchanged, so older batons still validate after coercion.

The coerce_* helpers keep stages robust to a sloppy LLM response: they retain only the
contract keys and fill anything missing with "unknown". This enforces HARD RULE 2 —
never invent; an absent field becomes an explicit "unknown", never a fabricated value.

DO NOT edit without sign-off (frozen).
"""

MANDATES = ("risk", "return", "compliance")
HORIZONS = ("near_term", "structural")
UNKNOWN = "unknown"

NARROWED_QUESTION_KEYS = ("narrowed_question", "mandate", "sector", "horizon", "trail")
# Contract C: the five text fields are the answer; reasoning/sources are additive (CoT + RAG).
STAGE2_TEXT_KEYS = (
    "question_to_ask",
    "what_rating_sees",
    "what_we_see",
    "check_before_monday",
    "competes_summary",
)
STAGE2_LIST_KEYS = ("reasoning", "sources")
STAGE2_ANSWER_KEYS = STAGE2_TEXT_KEYS + STAGE2_LIST_KEYS
COMPANY_DATA_KEYS = ("company", "ticker", "sector", "layer_a", "layer_b")


# --------------------------------------------------------------------------- #
#  COERCERS  (make a raw dict conform to the contract; missing -> "unknown")
# --------------------------------------------------------------------------- #
def coerce_narrowed_question(d):
    """Return a Contract A dict, keeping only contract keys and filling gaps."""
    d = d or {}
    trail = d.get("trail") or []
    clean_trail = [
        {
            "axis": t.get("axis"),
            "type": t.get("type") or "question",
            "text": t.get("text") or "",
            "rationale": t.get("rationale") or "",  # CoT: why this axis was probed (optional)
        }
        for t in trail
        if isinstance(t, dict)
    ]
    return {
        "narrowed_question": d.get("narrowed_question") or d.get("text") or UNKNOWN,
        "mandate": d.get("mandate") or UNKNOWN,
        "sector": d.get("sector") or UNKNOWN,
        "horizon": d.get("horizon") or UNKNOWN,
        "trail": clean_trail,
    }


def _coerce_reasoning(val):
    """Contract C `reasoning`: a list of short chain-of-thought step strings (blanks dropped).
    Tolerates a single string or a list of {"step"/"text"} dicts. Never invents."""
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, list):
        return []
    steps = []
    for s in val:
        if isinstance(s, dict):
            s = s.get("text") or s.get("step") or s.get("reason") or ""
        s = str(s).strip()
        if s:
            steps.append(s)
    return steps


def _coerce_sources(val):
    """Contract C `sources`: a list of {"title", "url"} provenance dicts (real entries only).
    These come from live retrieval, not the model — we never fabricate a citation."""
    if not isinstance(val, list):
        return []
    out = []
    for s in val:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()
        url = str(s.get("url") or "").strip()
        if title or url:
            out.append({"title": title or url, "url": url})
    return out


def coerce_stage2_answer(d):
    """Return a Contract C dict: the five text fields ('unknown' if missing) + reasoning + sources."""
    d = d or {}
    out = {k: (d.get(k) or UNKNOWN) for k in STAGE2_TEXT_KEYS}
    out["reasoning"] = _coerce_reasoning(d.get("reasoning"))
    out["sources"] = _coerce_sources(d.get("sources"))
    return out


def _coerce_momentum(x):
    x = x or {}
    return {"direction": x.get("direction") or UNKNOWN, "magnitude": x.get("magnitude") or UNKNOWN}


def coerce_company_data(d, origin="unknown"):
    """Return a Contract B dict in the full nested shape, filling every gap with 'unknown'.

    Used for LIVE-built and UPLOADED data so a sloppy/partial source still validates and is
    safe to reason over (HARD RULE 2: an absent field is an explicit 'unknown', never invented).
    ``origin`` ('live' | 'upload' | 'sample') is stamped on `_origin` so the UI can label the
    data honestly (real data is NOT shown as 'placeholder'). Extra provenance keys (e.g.
    `_sources`) are added by the caller, not here.
    """
    d = d or {}
    la = d.get("layer_a") or {}
    lb = d.get("layer_b") or {}
    mom = lb.get("momentum") or {}
    ai = lb.get("digital_ai_signal") or {}
    conf = lb.get("conflicting_signals") or {}
    out = {
        "company": d.get("company") or UNKNOWN,
        "ticker": d.get("ticker") or UNKNOWN,
        "sector": d.get("sector") or UNKNOWN,
        "layer_a": {
            "esg_score_static": la.get("esg_score_static") or UNKNOWN,
            "as_of_date": la.get("as_of_date") or UNKNOWN,
            "note": la.get("note") or "",
        },
        "layer_b": {
            "momentum": {
                "E": _coerce_momentum(mom.get("E")),
                "S": _coerce_momentum(mom.get("S")),
                "G": _coerce_momentum(mom.get("G")),
            },
            "digital_ai_signal": {
                "ai_governance_hiring_velocity": ai.get("ai_governance_hiring_velocity") or UNKNOWN,
                "ai_disclosure_level": ai.get("ai_disclosure_level") or UNKNOWN,
                "gap_note": ai.get("gap_note") or "",
            },
            "conflicting_signals": {
                "news_sentiment": conf.get("news_sentiment") or UNKNOWN,
                "behaviour_trend": conf.get("behaviour_trend") or UNKNOWN,
                "conflict_note": conf.get("conflict_note") or "",
            },
            "near_term_catalyst": lb.get("near_term_catalyst") or UNKNOWN,
        },
        "_origin": origin,
    }
    hist = d.get("layer_a_history")
    if isinstance(hist, dict):
        series = [s for s in (hist.get("series") or []) if isinstance(s, dict)]
        out["layer_a_history"] = {
            "note": hist.get("note") or "",
            "series": [
                {"as_of": s.get("as_of") or UNKNOWN, "esg_score_static": s.get("esg_score_static") or UNKNOWN}
                for s in series
            ],
            "trend_note": hist.get("trend_note") or "",
        }
    return out


# --------------------------------------------------------------------------- #
#  VALIDATORS  (used by selftest; assert the on-disk batons match the contract)
# --------------------------------------------------------------------------- #
def validate_narrowed_question(d):
    _require(d, NARROWED_QUESTION_KEYS, "NarrowedQuestion (Contract A)")
    assert isinstance(d["trail"], list), "Contract A: trail must be a list"
    return True


def validate_stage2_answer(d):
    _require(d, STAGE2_ANSWER_KEYS, "Stage2Answer (Contract C)")
    assert isinstance(d["reasoning"], list), "Contract C: reasoning must be a list"
    assert isinstance(d["sources"], list), "Contract C: sources must be a list"
    return True


def validate_company_data(d):
    _require(d, COMPANY_DATA_KEYS, "CompanyData (Contract B)")
    _require(d["layer_b"], ("digital_ai_signal", "near_term_catalyst"), "CompanyData.layer_b")
    hist = d.get("layer_a_history")  # additive + optional: historical static-score series.
    if hist is not None:
        assert isinstance(hist, dict) and isinstance(hist.get("series"), list), \
            "CompanyData.layer_a_history must be {note, series:[...], trend_note}"
    return True


def _require(d, keys, name):
    assert isinstance(d, dict), f"{name} must be a dict, got {type(d).__name__}"
    missing = [k for k in keys if k not in d]
    assert not missing, f"{name} missing keys: {missing}"
