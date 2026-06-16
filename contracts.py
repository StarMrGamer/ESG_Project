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
    { "company", "ticker", "sector", "layer_a": {...}, "layer_b": {...} }

Contract C — Stage2Answer (Stage 2 -> Stage 3)
    { "question_to_ask", "what_rating_sees", "what_we_see",
      "check_before_monday", "competes_summary" }

The coerce_* helpers keep stages robust to a sloppy LLM response: they retain only the
contract keys and fill anything missing with "unknown". This enforces HARD RULE 2 —
never invent; an absent field becomes an explicit "unknown", never a fabricated value.

DO NOT edit without sign-off (frozen).
"""

MANDATES = ("risk", "return", "compliance")
HORIZONS = ("near_term", "structural")
UNKNOWN = "unknown"

NARROWED_QUESTION_KEYS = ("narrowed_question", "mandate", "sector", "horizon", "trail")
STAGE2_ANSWER_KEYS = (
    "question_to_ask",
    "what_rating_sees",
    "what_we_see",
    "check_before_monday",
    "competes_summary",
)
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


def coerce_stage2_answer(d):
    """Return a Contract C dict, keeping only contract keys and filling gaps."""
    d = d or {}
    return {k: (d.get(k) or UNKNOWN) for k in STAGE2_ANSWER_KEYS}


# --------------------------------------------------------------------------- #
#  VALIDATORS  (used by selftest; assert the on-disk batons match the contract)
# --------------------------------------------------------------------------- #
def validate_narrowed_question(d):
    _require(d, NARROWED_QUESTION_KEYS, "NarrowedQuestion (Contract A)")
    assert isinstance(d["trail"], list), "Contract A: trail must be a list"
    return True


def validate_stage2_answer(d):
    _require(d, STAGE2_ANSWER_KEYS, "Stage2Answer (Contract C)")
    return True


def validate_company_data(d):
    _require(d, COMPANY_DATA_KEYS, "CompanyData (Contract B)")
    _require(d["layer_b"], ("digital_ai_signal", "near_term_catalyst"), "CompanyData.layer_b")
    return True


def _require(d, keys, name):
    assert isinstance(d, dict), f"{name} must be a dict, got {type(d).__name__}"
    missing = [k for k in keys if k not in d]
    assert not missing, f"{name} missing keys: {missing}"
