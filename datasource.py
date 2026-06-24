"""
datasource.py — build a CompanyData (Contract B) for a LIVE company, or load an UPLOAD.
=======================================================================================
Two production data paths feed Stage 2, both producing a Contract B dict:

  * build_live_company(user_text) — identify the company from what the user asked + fetch
    real documents (rag.py), then have the LLM extract a Contract B GROUNDED ONLY in those
    sources. Anything a source does not support is "unknown" — never invented (HARD RULE 2).

  * load_upload(filename, content) — accept the user's own ESG data:
      - .json  → used AS-IS (authoritative; coerced to the shape, no LLM guessing).
      - .csv/.txt → the LLM extracts a Contract B grounded ONLY in the uploaded file.

Both stamp `_origin` ("live" | "upload") and attach `_sources` provenance so the UI can label
the data honestly (real data is NOT presented as placeholder). LLM access stays in
core.call_llm(); fetch stays in rag.py / core.http_get(). Import-safe (no I/O at import time).
"""

import csv
import io
import json
import re

import contracts
import core
import rag

# Filler words stripped when no capitalised entity is found in the user's request.
_FILLER_RE = re.compile(
    r"\b(i|we|want|to|invest|in|is|a|an|the|should|worry|about|buy|sell|hold|sustainable|"
    r"stock|shares|company|esg|please|tell|me|analyse|analyze|look|at|how|does|do|on|of|for)\b",
    re.I,
)


_LEAD_DROP = {"is", "are", "was", "were", "be", "do", "does", "did", "should", "could", "would",
              "can", "will", "what", "why", "how", "who", "which", "the", "a", "an", "i", "we",
              "you", "my", "our", "tell", "me", "about"}


def _entity_hint(text):
    """Best-effort company name from the user's request — drives the targeted ESG-rating and
    AI-summary queries (which need a clean entity, not a whole sentence). Heuristic, never
    authoritative: the LLM extractor still resolves the real identity."""
    caps = [c.strip() for c in re.findall(r"\b[A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+)*\b", text or "")
            if len(c.strip()) > 1]
    if caps:
        words = max(caps, key=len).split()  # longest capitalised run, e.g. "DBS Bank" / "Nvidia"
        while len(words) > 1 and words[0].lower() in _LEAD_DROP:  # strip "Is Tesla" -> "Tesla"
            words.pop(0)
        return " ".join(words)
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^\w\s&.\-]", " ", _FILLER_RE.sub(" ", text or ""))).strip()
    return cleaned or (text or "").strip()

# --------------------------------------------------------------------------- #
#  THE GROUNDED EXTRACTOR  (build Contract B from sources only — never invent)
# --------------------------------------------------------------------------- #
EXTRACTOR_SYSTEM_PROMPT = """\
You are the ESG DATA EXTRACTOR for the ASEAN ESG Momentum Radar.

You are given SOURCES (a USER REQUEST naming/implying a company, plus real fetched snippets
or an uploaded document). Build a CompanyData JSON object describing ONE company.

ABSOLUTE RULES (never violate)
- IDENTITY (`company`, `ticker`, `sector`): determine these CONFIDENTLY from the USER REQUEST,
  the SOURCES, and the company's own name — this is identification, not ESG measurement (a bank
  → "Financials — Banks"; a chipmaker → "Technology — Semiconductors"; an oil major →
  "Energy"). Use "unknown" only when the name is genuinely ambiguous or unrecognisable.
- LAYER A (the static rating): when an ESG-RATING SOURCE states a rating, set `esg_score_static`
  to that REAL value. PREFER a numeric Sustainalytics/Morningstar ESG Risk Rating and format it
  NUMBER-FIRST as "N.N (Band Risk)" — e.g. "13.4 (Low Risk)", "22.4 (Medium Risk)", "32.8 (High
  Risk)". Mention any OTHER agency (e.g. "MSCI: AAA") in `note`, NOT in esg_score_static. Only if
  no numeric score exists, put a letter rating (e.g. "MSCI: AAA") in esg_score_static. Set
  `as_of_date` to the date the source gives (ISO yyyy-mm-dd when shown, e.g. "Jun 13, 2026" →
  "2026-06-13"). Use "unknown" only if NO source states a rating. Never invent a score or date.
- For EVERY other field, fill it ONLY with a fact explicitly supported by the SOURCES. If the
  sources do not support a value, output the string "unknown". NEVER invent or estimate a
  number, percentage, date, score, magnitude, or rating. Do not use outside knowledge.
- The free-text `note` / `gap_note` / `conflict_note` / `trend_note` fields may briefly
  PARAPHRASE what the sources say (qualitative is fine), or be "" if nothing applies. They
  must not contain invented figures.
- QUALITATIVE CLASSIFICATION is allowed and ENCOURAGED when the SOURCES (including the
  DUCKDUCKGO_AI_SUMMARY) clearly support it — this is grounded reading, not invention. When the
  sources convey it, DO set: each `momentum` DIRECTION ("improving"/"flat"/"declining"),
  `ai_disclosure_level` (e.g. "none"/"limited"/"partial"/"full"), `news_sentiment`
  ("positive"/"negative"/"mixed"), and `behaviour_trend` ("positive"/"negative"). These power
  the dashboard's charts. Leave a numeric `magnitude` / `ai_governance_hiring_velocity` as
  "unknown" unless a real figure appears in the sources — classify the DIRECTION even when the
  exact number is absent. Only use "unknown" for a classification the sources are silent on.
- `momentum` directions must be one of "improving" | "flat" | "declining" | "unknown".
- Prefer "unknown" over a guess for NUMBERS; for the qualitative classifications above, prefer a
  grounded reading of what the sources actually say over a reflexive "unknown".

OUTPUT — respond with JSON ONLY. No prose, no markdown, no code fences. Exactly this shape:
{
  "company": "string|unknown", "ticker": "string|unknown", "sector": "string|unknown",
  "layer_a": { "esg_score_static": "string|unknown", "as_of_date": "string|unknown",
               "note": "short paraphrase of the current rating context, or ''" },
  "layer_b": {
    "momentum": { "E": {"direction":"...","magnitude":"string|unknown"},
                  "S": {"direction":"...","magnitude":"string|unknown"},
                  "G": {"direction":"...","magnitude":"string|unknown"} },
    "digital_ai_signal": { "ai_governance_hiring_velocity": "string|unknown",
                           "ai_disclosure_level": "string|unknown",
                           "gap_note": "qualitative AI-governance gap from sources, or ''" },
    "conflicting_signals": { "news_sentiment": "positive|negative|mixed|unknown",
                             "behaviour_trend": "positive|negative|unknown",
                             "conflict_note": "where sources disagree, or ''" },
    "near_term_catalyst": "a real upcoming regulation/event from sources, or unknown"
  }
}
"""


def _extract(sources_block, *, max_tokens=1500):
    """Run the grounded extractor over a SOURCES text block. Returns a raw dict (or None)."""
    raw = core.call_llm(
        [{"role": "user", "content": sources_block}],
        EXTRACTOR_SYSTEM_PROMPT,
        max_tokens=max_tokens,
        temperature=0.2,  # low — we want faithful extraction, not creativity.
        json_mode=True,
    )
    parsed = core.parse_json(raw)
    if parsed is None:  # one silent retry before giving up
        raw = core.call_llm(
            [{"role": "user", "content": sources_block}],
            EXTRACTOR_SYSTEM_PROMPT,
            max_tokens=max_tokens,
            temperature=0.2,
            json_mode=True,
        )
        parsed = core.parse_json(raw)
    return parsed, raw


def _sources_provenance(snippets):
    """De-duped [{title,url}] from retrieved snippets, for the company's `_sources`."""
    out, seen = [], set()
    for s in snippets or []:
        url = (s.get("url") or "").strip()
        title = (s.get("title") or url or "source").strip()
        key = url or title
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": url})
    return out


# --------------------------------------------------------------------------- #
#  LIVE COMPANY  (fetch real docs, then extract grounded Contract B)
# --------------------------------------------------------------------------- #
def build_live_company(user_text, *, use_rag=True, k=None):
    """Identify the company from `user_text` + fetch real docs, then extract a grounded
    Contract B. Returns (company_dict, meta). meta = {"status", "doc_count"}.

    status: "live"   — built with fetched sources,
            "thin"   — built, but no/low external context (mostly 'unknown'),
            "offline"— retrieval failed; identity from the user text only.
    ``k`` overrides how many ranked snippets to ground the build (defaults to DEFAULT_TOP_K).
    Raises core.LLMConfigError if the API key is missing (caller surfaces it).
    """
    snippets, ai_summary, esg_docs = [], None, []
    doc_count, status, err = 0, "thin", None
    ent = _entity_hint(user_text)  # clean entity for the targeted ESG / AI-summary queries
    if use_rag:
        try:
            # General context + the AI summary queried by the ENTITY (not the whole sentence).
            ctx = rag.gather_context(user_text, background_topic=ent, k=k or rag.DEFAULT_TOP_K)
            snippets = ctx.get("snippets", [])
            ai_summary = ctx.get("ai_summary")
            doc_count = ctx.get("doc_count", 0)
            err = ctx.get("error")
        except Exception as e:  # noqa: BLE001 — retrieval must never break the build.
            snippets, err = [], f"{type(e).__name__}: {e}"
        try:
            # Dedicated ESG-rating retrieval so LAYER A (the static rating) can be grounded.
            ed, _st, _er = rag.fetch_documents(
                f"{ent} ESG risk rating score Sustainalytics Morningstar MSCI")
            esg_docs = ed[:6]
        except Exception:  # noqa: BLE001 — best-effort; absence just leaves Layer A "unknown".
            esg_docs = []
        has_ctx = bool(snippets or esg_docs or (ai_summary or {}).get("summary"))
        status = "live" if has_ctx else ("offline" if err else "thin")

    lines = [f"USER REQUEST:\n{user_text}\n"]
    if snippets:
        lines.append("SOURCES (real fetched snippets — the ONLY basis for facts):")
        for i, s in enumerate(snippets, 1):
            lines.append(f"[{i}] {s.get('title','')}\n    {s.get('snippet','')}")
    else:
        lines.append("SOURCES: (none fetched — set every fact you cannot support to 'unknown')")
    if esg_docs:
        lines.append("\nESG-RATING SOURCES (for LAYER A — set esg_score_static / as_of_date ONLY "
                     "from a rating, risk band, or date a snippet here actually states):")
        for i, s in enumerate(esg_docs, 1):
            lines.append(f"[E{i}] {s.get('title','')}\n    {(s.get('text') or '')[:480]}")
    if (ai_summary or {}).get("summary"):
        lines.append("\nDUCKDUCKGO_AI_SUMMARY (synthesized background — grounding context; "
                     "classify qualitative fields from it, but never invent figures):\n"
                     + ai_summary["summary"])
    parsed, raw = _extract("\n".join(lines))

    company = contracts.coerce_company_data(parsed, origin="live")
    company["_sources"] = _sources_provenance(snippets + esg_docs)
    company["_build_status"] = status
    company["_build_error"] = err
    company["_raw"] = raw
    return company, {"status": status, "doc_count": doc_count + len(esg_docs), "error": err}


# --------------------------------------------------------------------------- #
#  UPLOADS  (.json used as-is; .csv/.txt extracted grounded in the file only)
# --------------------------------------------------------------------------- #
def _decode(content):
    return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)


def _csv_to_text(text):
    """Flatten a CSV into a readable 'col: val' block for the extractor (best-effort)."""
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return text
    if not rows:
        return text
    header = rows[0]
    out = []
    for r in rows[1:]:
        pairs = [f"{(header[i] if i < len(header) else f'col{i}')}: {v}" for i, v in enumerate(r)]
        out.append(" | ".join(pairs))
    # include the header line too, in case it's a key,value file
    return "HEADER: " + ", ".join(header) + "\n" + "\n".join(out) if out else text


def load_upload(filename, content):
    """Load uploaded ESG data into a Contract B dict. Returns (company_dict, meta).

    .json → coerced as-is (authoritative). .csv/.txt → LLM extraction grounded ONLY in the
    file. meta = {"mode": "json"|"extracted", "filename": ...}. Raises ValueError on an
    unsupported type or unparseable JSON; core.LLMConfigError if extraction needs a key.
    """
    name = (filename or "").lower()
    text = _decode(content)

    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"That .json file isn't valid JSON: {e}") from e
        company = contracts.coerce_company_data(data, origin="upload")
        company["_sources"] = [{"title": f"Uploaded file: {filename}", "url": ""}]
        company["_build_status"] = "upload"
        return company, {"mode": "json", "filename": filename}

    if name.endswith(".csv") or name.endswith(".txt"):
        body = _csv_to_text(text) if name.endswith(".csv") else text
        block = (
            f"USER REQUEST:\nESG data uploaded by the user in {filename}. Identify the company "
            "and extract a CompanyData from THIS FILE ONLY.\n\n"
            "SOURCES (the uploaded file — the ONLY basis for facts):\n" + body[:8000]
        )
        parsed, raw = _extract(block)
        company = contracts.coerce_company_data(parsed, origin="upload")
        company["_sources"] = [{"title": f"Uploaded file: {filename}", "url": ""}]
        company["_build_status"] = "extracted"
        company["_raw"] = raw
        return company, {"mode": "extracted", "filename": filename}

    raise ValueError("Unsupported file type. Upload a .json, .csv, or .txt file.")
