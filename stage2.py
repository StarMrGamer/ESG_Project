"""
stage2.py — STAGE 2: Compete over data (the differentiator).
============================================================
A FRESH DeepSeek agent that takes the NarrowedQuestion baton (Contract A) + the
CompanyData (Contract B) + LIVE RETRIEVED CONTEXT (RAG) and answers by COMPETING: it
disagrees with the stale rating (Layer A) using signal the rating can't see (Layer B), the
historical static-score TREND (layer_a_history), and real external context the radar fetched.

It cites specific Layer B figures, surfaces the data conflict, frames the closing action by
the user's mandate, and shows its CHAIN OF THOUGHT (the `reasoning` list). It sees ONLY the
narrowed-question baton + the data + the retrieved snippets — never Stage 1's chat. It reasons
ONLY over provided inputs (HARD RULE 2: missing fact -> "unknown", never invent) and never
gives buy/sell/hold or a score (HARD RULE 4). Output is a Stage2Answer (Contract C), now with
`reasoning` (visible CoT) and `sources` (the real RAG citations — attached from retrieval, so
the model can never fabricate a URL).

No Streamlit here — this is a pure reasoning agent so it imports cleanly in tests. Retrieval is
isolated in rag.py / core.http_get and is best-effort: a dead network just means no snippets.
"""

import json

import core
import contracts
import rag

# --------------------------------------------------------------------------- #
#  THE IP — the competing-reasoner system prompt.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are the ESG COMPETING REASONER for the ASEAN ESG Momentum Radar.

You are given these inputs, and NOTHING else exists:
  1. NARROWED_QUESTION — the sharp question Stage 1 produced (with mandate/sector/horizon).
  2. COMPANY_DATA — Layer A (a STALE static rating), LAYER_A_HISTORY (the static score's
     trend over time), and Layer B (live momentum / digital-AI signal / conflicting signals /
     a near-term catalyst).
  3. RETRIEVED_CONTEXT — real external snippets the radar fetched live from DuckDuckGo (search
     results), each tagged [n] with a source URL. This may be EMPTY (offline) — that's fine.
  4. DUCKDUCKGO_AI_SUMMARY — DuckDuckGo's own synthesized answer about the topic, when one
     exists. INTERPRET it: treat it as a lead, cross-check it against the [n] snippets and the
     COMPANY_DATA, and lean on it for context — but never copy it verbatim as a verified fact,
     and never let it override a figure that COMPANY_DATA or a cited snippet actually states.

YOUR JOB: answer the narrowed question by COMPETING with the rating — take a position that
DISAGREES with the Layer A rating, justified by EVIDENCE the static rating cannot see. Use your
evidence in this order:
  (a) Layer B signals + the LAYER_A_HISTORY trend, WHEN PRESENT (quote figures verbatim); and
  (b) the RETRIEVED_CONTEXT — real, current news/regulatory reality (cite inline as [n]).
For a LIVE company the structured Layer B is often "unknown"; in that case build your answer
from the RETRIEVED_CONTEXT. Do NOT collapse to "no Layer B signal, therefore no risk" — weigh
what the sources actually say about the question. You are not a ranker; you contest a stale
view with fresher, cited evidence.

HARD CONSTRAINTS (never violate)
- NEVER invent a company-specific number, date, score, or rating that isn't in COMPANY_DATA or
  a cited source. If a precise FIGURE is unavailable, make the point qualitatively — never
  fabricate one. Synthesising what CITED sources say about the question is exactly your job.
- Never present an "unknown" as a fact. (A curated sample's values are illustrative; live /
  uploaded values are real — treat whatever IS present as the data of record.)
- When you rely on a retrieved source, cite it inline as [n] in `what_we_see` / `reasoning`.
- NEVER give buy / sell / hold, a target, or a score. You disagree with ratings; you don't pick.
- If Layer B figures ARE present, quote them verbatim and surface conflicting_signals + the
  LAYER_A_HISTORY trend; if they're "unknown", lean on RETRIEVED_CONTEXT instead.
- If BOTH Layer B and RETRIEVED_CONTEXT are empty, say plainly there isn't enough evidence yet
  and what to watch — do not manufacture a verdict.
ANSWER THE QUESTION THIS READER ACTUALLY ASKED. Stage 1 ran up to five adaptive questions to
build the NARROWED_QUESTION; every field of it is a thing the reader told us, so use them:
- `trail` is the transcript of the interrogation. Items with `"type": "answer"` are THE READER'S
  OWN WORDS; items with `"type": "question"` are what we asked them. Read the answers: they say
  what this reader is actually worried about. Address that concern head-on in `what_we_see`, and
  where they named a suspicion about the rating, say plainly whether the evidence supports it or
  contradicts it. If the trail carries no answers, fall back to mandate and horizon alone.
- `horizon` decides which evidence carries weight. `near_term` -> lead with the most recent dated
  signals and anything catalytic; `structural` -> lead with the multi-year trajectory and the
  LAYER_A_HISTORY trend, and treat a single recent item as weak on its own.
- `mandate` shapes what `what_we_see` FOREGROUNDS, not only the closing action:
    risk -> exposure, controversies, the downside the rating has not priced;
    return -> mispricing, improvement the rating has not caught up with;
    compliance -> disclosure quality, regulatory readiness, verification status.
- Frame check_before_monday by the same mandate:
    risk -> a downside/exposure check;  return -> an upside/mispricing check;
    compliance -> a regulatory-readiness check.

PERSONALISE THE EMPHASIS, NEVER THE VERDICT. The mandate, horizon and trail decide which true
things you lead with and how you frame them. They NEVER decide what is true, never change which
evidence exists, and never soften a finding. If the evidence contradicts what the reader hoped
or suspected, SAY SO FIRST and plainly — that is the single most useful thing this tool can do,
and a reader who is only told what they wanted to hear has been given nothing. An answer shaped
to please is a worse failure here than an answer that is merely generic.
- competes_summary MUST be ONE sentence that challenges the Layer A rating — or, when the
  rating is "unknown", challenges the market's complacent view — using your strongest evidence.

TIGHTEN THE ANSWER. The five text fields are for a busy decision-maker:
- Each is ONE tight sentence. competes_summary ≤ 30 words. No hedging, no preamble.
- Put the long chain-of-thought ONLY in `reasoning` (3–6 short steps), not in the text fields.
- In `reasoning`, you MAY cite retrieved context as [n]; keep each step to one line.

OUTPUT — respond with JSON ONLY. No prose, no markdown, no code fences. Exactly these keys:
{
  "question_to_ask": "restate the narrowed question in one sentence",
  "what_rating_sees": "the Layer A view — static score + as-of date + history trend IF known; if unknown, say so and note the market's prevailing view",
  "what_we_see": "the signal the rating can't see — Layer B figures verbatim if present, else the real-world evidence from RETRIEVED_CONTEXT cited as [n]",
  "check_before_monday": "ONE concrete action, framed by the mandate",
  "competes_summary": "ONE sentence (<=30 words) that explicitly disagrees with the rating",
  "reasoning": ["step 1 — short", "step 2 — short", "..."]
}
Do NOT output a "sources" key — the radar attaches the real citations itself.
"""


# --------------------------------------------------------------------------- #
#  PURE LOGIC
# --------------------------------------------------------------------------- #
def _format_context(snippets):
    """Render retrieved snippets as a numbered, source-tagged block for the prompt."""
    if not snippets:
        return "RETRIEVED_CONTEXT: (none — offline or retrieval disabled; reason on the data)"
    lines = ["RETRIEVED_CONTEXT (real DuckDuckGo snippets, ranked; cite as [n] in reasoning):"]
    for i, s in enumerate(snippets, 1):
        title = (s.get("title") or s.get("url") or "source").strip()
        snippet = (s.get("snippet") or "").strip()
        lines.append(f"[{i}] {title}\n    {snippet}")
    return "\n".join(lines)


def _format_ai_summary(ai_summary):
    """Render DuckDuckGo's synthesized 'AI' summary as a block for the agent to INTERPRET."""
    summary = ((ai_summary or {}).get("summary") or "").strip()
    if not summary:
        return ("DUCKDUCKGO_AI_SUMMARY: (none returned — interpret the snippets / data instead)")
    source = (ai_summary.get("source") or "DuckDuckGo").strip()
    return ("DUCKDUCKGO_AI_SUMMARY (DuckDuckGo's synthesized answer — INTERPRET it, cross-check "
            f"against the snippets and the data; do not copy as fact; source: {source}):\n"
            + summary)


def build_user_message(narrowed_question, company, snippets=None, ai_summary=None):
    """Pack the inputs into the single user turn for the fresh agent."""
    return (
        "NARROWED_QUESTION (Contract A):\n"
        + json.dumps(narrowed_question, indent=2, ensure_ascii=False)
        + "\n\nCOMPANY_DATA (Contract B — includes layer_a_history):\n"
        + json.dumps(company, indent=2, ensure_ascii=False)
        + "\n\n"
        + _format_context(snippets or [])
        + "\n\n"
        + _format_ai_summary(ai_summary)
        + "\n\nNow produce the Stage2Answer JSON: compete with the Layer A rating using Layer B "
          "evidence + the historical trend, interpret the DuckDuckGo AI summary, show your "
          "reasoning steps, keep the text fields tight."
    )


def retrieve_context(narrowed_question, company, use_rag=True, k=None):
    """Live-fetch + rank external ESG context for this question. NEVER raises.

    Returns the rag.gather_context dict: {"snippets", "status", "doc_count", "query"}.
    Exposed separately so the UI can show retrieval progress before the (longer) LLM call.
    ``k`` overrides how many ranked snippets to keep (defaults to rag.DEFAULT_TOP_K).
    """
    if not use_rag:
        return {"snippets": [], "status": "disabled", "doc_count": 0, "query": "", "error": None}
    try:
        return rag.gather_context(
            rag.build_query(narrowed_question, company),
            background_topic=rag.background_topic(company),
            k=k or rag.DEFAULT_TOP_K,
        )
    except Exception as e:  # noqa: BLE001 — retrieval must never break the relay.
        return {"snippets": [], "status": "offline", "doc_count": 0, "query": "",
                "error": f"{type(e).__name__}: {e}"}


def reason(narrowed_question, company, on_delta=None, context=None):
    """Run Stage 2. Returns a Stage2Answer (Contract C) dict (+ debug/RAG metadata).

    A fresh agent: its context is the narrowed question + company data + retrieved snippets,
    passed as one user turn. ``context`` is a rag.gather_context dict; if None it is fetched
    here (so reason() works standalone). Pass ``on_delta`` to stream (the UI narrates progress);
    the parsed Contract C is identical either way. On a JSON parse-fail we retry ONCE, silently.

    ``sources`` is set from the REAL retrieved snippets — never from the model — so a citation
    can never be fabricated (HARD RULE 2).
    """
    if context is None:
        context = retrieve_context(narrowed_question, company, use_rag=True)
    snippets = (context or {}).get("snippets", [])
    ai_summary = (context or {}).get("ai_summary")

    user_msg = build_user_message(narrowed_question, company, snippets, ai_summary)
    # Generous budget: this is the largest prompt, and a reasoning model spends tokens
    # thinking BEFORE the JSON — too small a cap returns empty content.
    #
    # 2000 was too small and failed silently, which is the worst way for it to fail. On
    # deepseek-v4-flash the reasoning alone ran past the cap, so `content` came back empty,
    # core.call_llm fell back to `reasoning_content`, and what reached parse_json was 8kB of
    # "We need respond JSON only. Need craft answer. Need think." — unparseable twice over, so
    # every one of Contract C's five text fields coerced to "unknown" while the sources list
    # still filled in from real retrieval. An answer that looks retrieved but says nothing.
    # Measured: 4000 completes in ~14s and returns all six keys. Raise this, do not lower it.
    raw = core.call_llm(
        [{"role": "user", "content": user_msg}],
        SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.5,
        json_mode=True,
        stream=bool(on_delta),
        on_delta=on_delta,
    )
    parsed = core.parse_json(raw)
    if parsed is None:  # one non-streaming retry with a fresh budget before giving up
        retry_raw = core.call_llm(
            [{"role": "user", "content": user_msg}],
            SYSTEM_PROMPT,
            max_tokens=4000,
            temperature=0.4,
            json_mode=True,
        )
        retry_parsed = core.parse_json(retry_raw)
        if retry_parsed is not None:
            raw, parsed = retry_raw, retry_parsed
        elif retry_raw and not raw:
            raw = retry_raw  # surface SOMETHING for the debug view, even if unparseable

    answer = contracts.coerce_stage2_answer(parsed)
    # Attach the REAL retrieved sources (title + url) — provenance the model can't fabricate.
    answer["sources"] = [
        {"title": s.get("title", ""), "url": s.get("url", "")}
        for s in snippets if s.get("url")
    ]
    # The DuckDuckGo AI summary carries its own real source URL — add it as provenance too.
    if ai_summary and ai_summary.get("url") and \
            all(s["url"] != ai_summary["url"] for s in answer["sources"]):
        answer["sources"].append({
            "title": f"DuckDuckGo AI summary — {ai_summary.get('source') or 'DuckDuckGo'}",
            "url": ai_summary["url"],
        })
    # Non-contract debug fields (stripped from any on-disk baton; safe for the UI to read).
    answer["_raw"] = raw
    answer["_parse_failed"] = parsed is None
    answer["_rag_status"] = (context or {}).get("status", "disabled")
    answer["_rag_query"] = (context or {}).get("query", "")
    answer["_ai_summary"] = ai_summary  # for Stage 3 to display what it interpreted
    return answer
