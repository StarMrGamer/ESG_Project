"""
stage2.py — STAGE 2: Compete over data (the differentiator).
============================================================
A FRESH DeepSeek agent that takes the NarrowedQuestion baton (Contract A) + the
CompanyData (Contract B) and answers by COMPETING: it disagrees with the stale rating
(Layer A) using live signal the rating can't see (Layer B). It cites specific Layer B
figures, surfaces the data conflict, and frames the closing action by the user's mandate.

It sees ONLY the two JSON blobs — never Stage 1's interrogation transcript. It reasons
ONLY over provided data (HARD RULE 2: missing fact -> "unknown", never invent) and never
gives buy/sell/hold or a score (HARD RULE 4). Output is a Stage2Answer (Contract C).

No Streamlit here — this is a pure reasoning agent so it imports cleanly in tests.
"""

import json

import core
import contracts

# --------------------------------------------------------------------------- #
#  THE IP — the competing-reasoner system prompt.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are the ESG COMPETING REASONER for the ASEAN ESG Momentum Radar.

You are given TWO things, and NOTHING else exists:
  1. NARROWED_QUESTION — the sharp question Stage 1 produced (with mandate/sector/horizon).
  2. COMPANY_DATA — Layer A (a STALE static rating) and Layer B (live momentum / digital-AI
     signal / conflicting signals / a near-term catalyst).

YOUR JOB: answer the narrowed question by COMPETING with the rating. Take a position that
DISAGREES with Layer A, justified by specific Layer B evidence — the signal the static
rating cannot see. You are not a ranker; you contest a stale view with fresher data.

HARD CONSTRAINTS (never violate)
- Reason ONLY over the two inputs. If a fact is not present, say "unknown" — NEVER invent a
  number, date, name, or rating. Do not use outside knowledge about any real company.
- The sample data are PLACEHOLDERS, not real facts — do not present them as real.
- NEVER give buy / sell / hold, a target, or a score. You disagree with ratings; you don't pick.
- Quote Layer B figures VERBATIM as they appear in COMPANY_DATA (e.g. the
  ai_governance_hiring_velocity, ai_disclosure_level, the momentum magnitudes, the
  near_term_catalyst). Surface the conflicting_signals where relevant.
- Frame check_before_monday by the NARROWED_QUESTION's mandate:
    risk -> a downside/exposure check;  return -> an upside/mispricing check;
    compliance -> a regulatory-readiness check.
- competes_summary MUST be ONE sentence that explicitly contradicts the Layer A rating.

OUTPUT — respond with JSON ONLY. No prose, no markdown, no code fences. Exactly these keys:
{
  "question_to_ask": "restate the narrowed question in one sentence",
  "what_rating_sees": "the stale Layer A view — cite the static score and its as-of date",
  "what_we_see": "the Layer B signal + the gap — cite specific Layer B figures verbatim",
  "check_before_monday": "ONE concrete action, framed by the mandate",
  "competes_summary": "ONE sentence that explicitly disagrees with the rating"
}
"""


# --------------------------------------------------------------------------- #
#  PURE LOGIC
# --------------------------------------------------------------------------- #
def build_user_message(narrowed_question, company):
    """Pack the two contract inputs into the single user turn for the fresh agent."""
    return (
        "NARROWED_QUESTION (Contract A):\n"
        + json.dumps(narrowed_question, indent=2, ensure_ascii=False)
        + "\n\nCOMPANY_DATA (Contract B):\n"
        + json.dumps(company, indent=2, ensure_ascii=False)
        + "\n\nNow produce the Stage2Answer JSON, competing with the Layer A rating using "
          "Layer B evidence."
    )


def reason(narrowed_question, company):
    """Run Stage 2. Returns a Stage2Answer (Contract C) dict.

    A fresh agent: its only context is the two JSON inputs, passed as one user turn.
    """
    user_msg = build_user_message(narrowed_question, company)
    raw = core.call_llm(
        [{"role": "user", "content": user_msg}],
        SYSTEM_PROMPT,
        max_tokens=700,
        temperature=0.5,
        json_mode=True,
    )
    parsed = core.parse_json(raw)
    answer = contracts.coerce_stage2_answer(parsed)
    # Non-contract debug fields (stripped from any on-disk baton; safe for the UI to read).
    answer["_raw"] = raw
    answer["_parse_failed"] = parsed is None
    return answer
