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
from typing import Any, Dict, Optional, Tuple

import contracts
import core
import rag
import signals as _signals

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
- IDENTITY (`company`, `ticker`, `sector`, `country`): determine these CONFIDENTLY from the USER
  REQUEST, the SOURCES, and the company's own name — this is identification, not ESG measurement (a
  bank → "Financials — Banks"; a chipmaker → "Technology — Semiconductors"; an oil major →
  "Energy"). `country` is the company's HOME country — where it is HEADQUARTERED / primarily
  operates, NOT the stock-exchange venue (e.g. Grab → "Singapore" and GoTo → "Indonesia" even
  though they may list abroad; Nvidia → "United States"). Use "unknown" only when genuinely
  ambiguous or unrecognisable.
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
  "company": "string|unknown", "ticker": "string|unknown", "sector": "string|unknown", "country": "string|unknown",
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


# Words that mark a retrieved item as a genuine ESG red flag (not a generic ratings page).
_CONTROVERSY_KWS = ("controvers", "scandal", "lawsuit", "sued", "fine", "fined", "penalt",
                    "probe", "investigat", "breach", "fraud", "misconduct", "violation",
                    "recall", "spill", "pollut", "emission", "strike", "boycott", "sanction",
                    "settlement", "allegation", "greenwash", "data leak", "antitrust", "bribery")


def _select_controversies(docs, limit=5):
    """Keep only retrieved docs whose text actually flags a controversy — real news leads with
    real URLs (never a verdict, just items to check). De-duped, capped at `limit`."""
    out, seen = [], set()
    for d in docs or []:
        blob = ((d.get("text") or "") + " " + (d.get("title") or "")).lower()
        if not any(kw in blob for kw in _CONTROVERSY_KWS):
            continue
        key = (d.get("url") or d.get("title") or "").strip()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"title": d.get("title") or d.get("url") or "source",
                    "url": d.get("url") or "", "snippet": (d.get("text") or "")[:220]})
        if len(out) >= limit:
            break
    return out


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
def build_live_company(user_text: str, *, use_rag: bool = True,
                       k: Optional[int] = None) -> Dict[str, Any]:
    """Identify the company from `user_text` + fetch real docs, then extract a grounded
    Contract B. Returns (company_dict, meta). meta = {"status", "doc_count"}.

    status: "live"   — built with fetched sources,
            "thin"   — built, but no/low external context (mostly 'unknown'),
            "offline"— retrieval failed; identity from the user text only.
    ``k`` overrides how many ranked snippets to ground the build (defaults to DEFAULT_TOP_K).
    Raises core.LLMConfigError if the API key is missing (caller surfaces it).
    """
    snippets, ai_summary, esg_docs, controversies = [], None, [], []
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
        try:
            # Red-flag retrieval — recent ESG controversies (the 'behaviour' side of the conflict).
            cd, _cst, _cer = rag.fetch_documents(
                f"{ent} ESG controversy scandal fine lawsuit investigation")
            controversies = _select_controversies(cd)
        except Exception:  # noqa: BLE001 — best-effort; no flags is a perfectly valid result.
            controversies = []
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
    company["_country"] = (parsed or {}).get("country") or "unknown"  # for the ASEAN-only gate
    company["_sources"] = _sources_provenance(snippets + esg_docs)
    company["_controversies"] = controversies
    company["_build_status"] = status
    company["_build_error"] = err
    company["_raw"] = raw
    return company, {"status": status, "doc_count": doc_count + len(esg_docs), "error": err}


# --------------------------------------------------------------------------- #
#  CONSTITUENT-ANCHORED BUILD  (the dashboard path — identity from the base DB)
# --------------------------------------------------------------------------- #
def _search_entity(name):
    """Flatten a constituent name into a clean search entity: drop the parenthetical alias's
    brackets so both the long name and the short alias are searchable ('Bank Central Asia (BCA)'
    -> 'Bank Central Asia BCA')."""
    return re.sub(r"\s+", " ", (name or "").replace("(", " ").replace(")", " ")).strip()


def build_company_from_constituent(constituent: Dict[str, Any], *, use_rag: bool = True,
                                   k: Optional[int] = None) -> Dict[str, Any]:
    """Build a grounded Contract B for a KNOWN MSCI ASEAN constituent (dashboard / monitoring).

    Unlike build_live_company (which must first GUESS the identity from free text), identity here
    is authoritative — it comes from the base DB — so the extractor locks company/ticker/sector
    and spends its effort on Layer A/B. Retrieval is ASEAN-SCOPED: every query carries the
    company's country + home exchange, so 'fetch' finds the right ASEAN-listed entity (this is the
    "new search"). Returns (company_dict, meta); never raises on a retrieval failure.
    """
    c = constituent or {}
    name = (c.get("company") or "unknown").strip()
    country = (c.get("country") or "").strip()
    exchange = (c.get("exchange") or "").strip()
    ent = _search_entity(name)
    scope = " ".join(p for p in (country, "ASEAN") if p and p.lower() != "unknown")

    snippets, ai_summary, esg_docs, controversies = [], None, [], []
    doc_count, status, err = 0, "thin", None
    if use_rag:
        try:
            ctx = rag.gather_context(f"{ent} {scope} ESG sustainability governance",
                                     background_topic=ent, k=k or rag.DEFAULT_TOP_K)
            snippets = ctx.get("snippets", [])
            ai_summary = ctx.get("ai_summary")
            doc_count = ctx.get("doc_count", 0)
            err = ctx.get("error")
        except Exception as e:  # noqa: BLE001 — retrieval must never break the build.
            snippets, err = [], f"{type(e).__name__}: {e}"
        try:
            ed, _st, _er = rag.fetch_documents(
                f"{ent} {country} ESG risk rating score Sustainalytics Morningstar MSCI")
            esg_docs = ed[:6]
        except Exception:  # noqa: BLE001
            esg_docs = []
        try:
            cd, _cst, _cer = rag.fetch_documents(
                f"{ent} {country} ESG controversy scandal fine lawsuit investigation")
            controversies = _select_controversies(cd)
        except Exception:  # noqa: BLE001
            controversies = []
        has_ctx = bool(snippets or esg_docs or (ai_summary or {}).get("summary"))
        status = "live" if has_ctx else ("offline" if err else "thin")

    cagr = (c.get("esg_cagr_2019_2023") or "").strip()
    lines = [
        "KNOWN IDENTITY (authoritative — use these VERBATIM for company/ticker/sector and do NOT "
        "override them; this is a confirmed ASEAN ESG-momentum constituent):",
        f"  company: {name}",
        f"  ticker:  {c.get('ticker') or 'unknown'}",
        f"  sector:  {c.get('sector') or 'unknown'}",
        f"  market:  {country or 'unknown'} ({exchange or 'unknown'})",
    ]
    if cagr:
        lines.append(
            f"  esg_cagr_2019_2023: {cagr} — FOUNDATION FACT: this name was selected for CONSISTENT "
            "ESG-score improvement 2019-2023 (positive 5-year CAGR). On THIS grounded basis you MAY "
            "classify the static/historical ESG trend as improving; still ground Layer B specifics "
            "(AI, news, behaviour) only in the snippets below.")
    lines += [
        "",
        f"USER REQUEST:\nBuild the ESG profile (Layer A static rating + Layer B momentum/signals) "
        f"for {name}, listed in {country or 'ASEAN'}. Ground EVERY fact in the sources below.\n",
    ]
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
    # Identity is authoritative — overwrite whatever the extractor returned with the base-DB facts.
    company["company"] = name or company.get("company")
    company["ticker"] = c.get("ticker") or company.get("ticker")
    if (c.get("sector") or "").lower() not in ("", "unknown"):
        company["sector"] = c["sector"]
    company["_country"] = country or "unknown"
    company["_exchange"] = exchange or "unknown"
    company["_constituent_ticker"] = c.get("ticker") or c.get("id") or "unknown"
    company["_sources"] = _sources_provenance(snippets + esg_docs)
    company["_controversies"] = controversies
    company["_build_status"] = status
    company["_build_error"] = err
    company["_raw"] = raw
    return company, {"status": status, "doc_count": doc_count + len(esg_docs), "error": err}


# --------------------------------------------------------------------------- #
#  SNAPSHOT  (compact at-a-glance card data for the dashboard / monitoring board)
# --------------------------------------------------------------------------- #
_BAND_RE = re.compile(r"\(([^)]*risk[^)]*)\)", re.I)          # "(Medium Risk)" -> Medium Risk
_NUM_RE = re.compile(r"(\d{1,2}(?:\.\d)?)")                   # a 0-60ish risk number
_LETTER_RE = re.compile(r"\b(AAA|AA|A|BBB|BB|B|CCC)\b")        # MSCI-style letter
_ARROWS = {"improving": "▲", "declining": "▼", "flat": "—", "unknown": "·"}

# 10 signals the monitoring card reports coverage against (mirrors the deep-dive coverage meter).
_SNAP_SIGNALS = (
    ("layer_a", "esg_score_static"), ("layer_a", "as_of_date"),
    ("momentum", "E"), ("momentum", "S"), ("momentum", "G"),
    ("ai", "ai_disclosure_level"), ("conf", "news_sentiment"),
    ("conf", "behaviour_trend"), ("catalyst", None), ("controversies", None),
)


def _known(v):
    return bool(v) and str(v).strip().lower() not in ("", "unknown")


def _dir_from(v):
    """A momentum % -> a Layer-B direction word."""
    if v is None:
        return "unknown"
    return "improving" if v > 1 else "declining" if v < -1 else "flat"


def _pct_str(v):
    if v is None:
        return "unknown"
    sign = "+" if v > 0 else ""
    return f"{sign}{int(v) if float(v).is_integer() else v}%"



# --------------------------------------------------------------------------------------------- #
# Layer B from the evidence we already hold.
#
# The live builder asks the model to set anything it cannot support to "unknown", which is right —
# but it means a company whose live search comes back thin gets an EMPTY Layer B while the repo is
# sitting on dated, sourced, already-scored evidence for that exact company. That is not a missing
# fact, it is a fact we did not look up.
#
# So: no network, no LLM, and nothing invented. `signals.from_company` routes the stored evidence
# by rule and every field below is a count or a direction read off those signals.
# --------------------------------------------------------------------------------------------- #

#: Above this the evidence is calling a direction; below it, the signals disagree enough that
#: "flat" is the honest word. Deliberately not zero: two signals pointing opposite ways average to
#: ~0 and that is a CONFLICT, not a company standing still.
_CONSENSUS_BAND = 0.15

_COMPONENT_PILLAR = {"E": "E", "S": "S", "G": "G"}


def _consensus_word(value):
    if value is None:
        return "unknown"
    if value > _CONSENSUS_BAND:
        return "improving"
    if value < -_CONSENSUS_BAND:
        return "declining"
    return "flat"


def _strength_word(value):
    """Adverb, for prose: "strongly improving"."""
    a = abs(value or 0.0)
    return "strongly" if a >= 0.75 else "clearly" if a >= 0.4 else "weakly"


def _strength_adj(value):
    """Adjective, for the `magnitude` FIELD, which is rendered beside the direction as
    "strong · improving". No digits, ever — see momentum_cell."""
    a = abs(value or 0.0)
    return "strong" if a >= 0.75 else "clear" if a >= 0.4 else "weak"



#: A framework with no issuance under it is the one genuinely FORWARD-looking fact this repo
#: holds. Everything else here is dated evidence about what has already happened; an unused
#: framework is a stated intention with a document behind it, which is exactly what a "near-term
#: catalyst" is meant to name — and it is invisible to an ESG score, because nothing has happened
#: yet for a score to move on.
#:
#: The SLB distinction is load-bearing. A sustainability-LINKED framework is a different
#: instrument from a green use-of-proceeds bond under ICMA and the ASEAN GBS, with a different
#: credibility profile, so it is reported as what it is rather than counted as a green pipeline.
def _catalyst_from_metadata(row):
    row = row or {}
    framework = (row.get("framework_url") or "").strip()
    if not framework:
        return ""
    issued = (row.get("green_bond_status") or "none").strip().lower()
    if issued not in ("none", ""):
        return ""                       # already issuing — priced in, not a catalyst
    reviewer = (row.get("external_reviewer") or "").strip()
    spo = (row.get("review_type") or "").strip().lower() in ("second_party_opinion", "spo")
    linked = "sl" in reviewer.lower().replace("sustainability-linked", "slb")

    if spo and not linked:
        return ("Holds a green-bond framework with a second-party opinion%s and has not issued "
                "under it. An issuance is a near-term event no ESG score can price, because "
                "nothing has happened yet for one to move on."
                % (" from %s" % reviewer.split("(")[0].strip() if reviewer else ""))
    if spo and linked:
        return ("Holds a reviewed SUSTAINABILITY-LINKED framework and has not issued under it. "
                "Under ICMA and the ASEAN GBS that is a different instrument from a green "
                "use-of-proceeds bond, so it is a pipeline for a different thing — worth "
                "watching, not counted as green issuance.")
    return ("Has published a financing framework with no second-party opinion on file and has "
            "not issued under it. Weaker than a reviewed framework, and still a stated intention "
            "the rating cannot see.")


def layer_b_from_evidence(constituent: Dict[str, Any], *, config=None, meta_row=None):
    """A Contract-B Layer B built from stored signals. `(layer_b, meta)`, or `(None, meta)`.

    THE MAGNITUDE STAYS "unknown" ON PURPOSE. The engine's number is a DIRECTION CONSENSUS on a
    -1..+1 scale, and Contract B's `magnitude` is percent-shaped by convention ("+8%") — worse,
    `metrics.num` happily reads 0.78 out of any string containing it, so a consensus parked in
    that field would be plotted on an axis labelled "%" and a strong agreement would render as a
    rounding error. Direction is the part that survives the unit change intact, so direction is
    what gets filled; the consensus itself is stated in the notes, where nothing parses it.
    """
    # THE HARVEST IS PART OF "THE DATABASE WE HAVE". The server hands this function a RAW
    # constituent, so without the overlay the fallback sees only the verified basket — 76 signals
    # across the universe instead of 391 — and a company like RHB reads unknown on environment
    # while eleven dated environmental events sit in `data/harvest/`. Applying it here rather than
    # at the call site means every caller gets the same evidence the ENGINE scores, which is the
    # only defensible answer when the two are shown on the same screen.
    #
    # Safe to apply to an already-overlaid constituent: `apply_overlay` appends and
    # `signals.from_company` dedupes by `signal_id`, so the same fact cannot be counted twice.
    try:
        import harvest as _harvest
        constituent = _harvest.apply_overlay([constituent or {}])[0]
    except Exception:                                       # noqa: BLE001 - overlay is optional
        constituent = constituent or {}

    try:
        sigs = _signals.from_company(constituent, config=config)
    except Exception:                                       # noqa: BLE001 - never break a build
        return None, {"available": False, "reason": "signal extraction failed"}
    if not sigs:
        return None, {"available": False, "reason": "no stored evidence for this company"}

    buckets: Dict[str, list] = {}
    for sg in sigs:
        buckets.setdefault(sg.get("component") or "?", []).append(sg)

    def read(component):
        rows = buckets.get(component) or []
        if not rows:
            return None
        dirs = [float(sg.get("direction") or 0) for sg in rows]
        consensus = sum(dirs) / len(dirs)
        return {
            "n": len(rows),
            "up": sum(1 for d in dirs if d > 0),
            "down": sum(1 for d in dirs if d < 0),
            "consensus": round(consensus, 3),
            "newest": max((sg.get("published_at") or "") for sg in rows),
            "sources": sorted({sg.get("source_type") or "unknown" for sg in rows}),
        }

    pillars = {k: read(k) for k in _COMPONENT_PILLAR}
    digital = read("DIGITAL")

    def momentum_cell(key):
        r = pillars.get(key)
        if not r:
            return {"direction": "unknown", "magnitude": "unknown"}
        # A WORD, and specifically a word with NO DIGITS IN IT. The strength is real information
        # and leaving it "unknown" made the panel read "↑ unknown · improving" — but the moment a
        # number appears in this string, `metrics.num` will read it back out ("strong · 9 signals"
        # yields 9.0) and something will plot it on an axis labelled "%". A bare adjective carries
        # the magnitude a reader wants and cannot be mistaken for a measurement.
        return {"direction": _consensus_word(r["consensus"]),
                "magnitude": _strength_adj(r["consensus"])}

    # A pillar whose signals point BOTH ways is the most interesting thing on this panel, and it
    # is a real reading rather than a hedge — so it is reported with its counts.
    split = [(k, r) for k, r in pillars.items() if r and r["up"] and r["down"]]
    if split:
        key, r = max(split, key=lambda kv: kv[1]["n"])
        conflict_note = ("%d %s signals disagree: %d point up, %d down (consensus %+.2f). "
                         "The direction is contested, not absent."
                         % (r["n"], {"E": "environmental", "S": "social",
                                     "G": "governance"}[key], r["up"], r["down"], r["consensus"]))
    else:
        conflict_note = ""

    # Sentiment we do NOT hold. What we hold is which KIND of source said what, which is a
    # different and more defensible claim, so that is what is reported.
    news_sigs = [sg for sg in sigs if (sg.get("source_type") or "") == "news"]
    news_dir = (sum(float(sg.get("direction") or 0) for sg in news_sigs) / len(news_sigs)
                if news_sigs else None)
    overall = sum(float(sg.get("direction") or 0) for sg in sigs) / len(sigs)

    if digital:
        gap_note = ("%d dated Digital/AI signal%s on file, %s %s (consensus %+.2f). Newest %s."
                    % (digital["n"], "" if digital["n"] == 1 else "s",
                       _strength_word(digital["consensus"]),
                       _consensus_word(digital["consensus"]), digital["consensus"],
                       digital["newest"] or "undated"))
    else:
        gap_note = ("No Digital/AI evidence on file for this company. That is an absence of "
                    "evidence, not evidence that nothing is happening.")

    layer_b = {
        "momentum": {k: momentum_cell(k) for k in ("E", "S", "G")},
        "digital_ai_signal": {
            "ai_governance_hiring_velocity": "unknown",
            "ai_disclosure_level": "disclosed" if digital else "unknown",
            "gap_note": gap_note,
        },
        "conflicting_signals": {
            "news_sentiment": _consensus_word(news_dir) if news_sigs else "unknown",
            "behaviour_trend": _consensus_word(overall),
            "conflict_note": conflict_note,
        },
        # We hold no forward CALENDAR — no regulation dates, no results dates — so the only
        # honest catalyst is one with a document behind it: a published framework nobody has
        # issued under yet. Absent that, this stays unknown rather than being filled with a hedge.
        "near_term_catalyst": _catalyst_from_metadata(meta_row) or "unknown",
    }
    meta = {
        "available": True,
        "signal_count": len(sigs),
        "pillars": {k: v for k, v in pillars.items() if v},
        "digital": digital,
        "newest": max((sg.get("published_at") or "") for sg in sigs),
        "note": ("Layer B read from %d dated, sourced signals already on file — no live retrieval "
                 "and no model. Directions are the evidence consensus; magnitudes are a "
                 "WORD rather than a number, because that consensus is not a percentage."
                 % len(sigs)),
    }
    return layer_b, meta



def _is_unknown(value):
    return not value or str(value).strip().lower() in ("", "unknown", "none")


def _fill_layer_b_from_evidence(company: Dict[str, Any], constituent: Dict[str, Any]) -> bool:
    """Fill only the Layer B fields still reading "unknown", from stored evidence.

    Returns True if anything was filled. Stamps `_layer_b_origin` either way, because a reader is
    entitled to know which half of the panel came from a live build and which from the file on
    disk (HARD RULE 3) — and because "derived from stored evidence" is a materially different
    claim from "fetched just now".
    """
    lb = company.get("layer_b")
    if not isinstance(lb, dict):
        return False

    # The metadata row carries the green-bond framework state, which is where the only
    # forward-looking fact we hold lives. Loaded lazily so a demo constituent costs nothing.
    meta_row = None
    try:
        import company_metadata as _cm
        ticker = constituent.get("ticker") or constituent.get("id") or ""
        meta_row = (_cm.load(demo=False) or {}).get(ticker)
    except Exception:                                       # noqa: BLE001 - optional enrichment
        meta_row = None
    evidence, meta = layer_b_from_evidence(constituent, meta_row=meta_row)
    if not evidence:
        # Stamp the same keys on every path. A caller that has to check whether a field EXISTS
        # before reading it will eventually forget, and the forgetting looks like "nothing was
        # filled" rather than like an error.
        company["_layer_b_origin"] = "constituent"
        company["_layer_b_filled"] = []
        company["_layer_b_evidence"] = meta or {}
        company["_layer_b_note"] = (meta or {}).get("reason", "")
        return False

    filled = []
    mom = lb.get("momentum") if isinstance(lb.get("momentum"), dict) else {}
    for key, cell in (evidence.get("momentum") or {}).items():
        target = mom.get(key)
        if isinstance(target, dict) and _is_unknown(target.get("direction")) \
                and not _is_unknown(cell.get("direction")):
            target["direction"] = cell["direction"]
            if _is_unknown(target.get("magnitude")) and not _is_unknown(cell.get("magnitude")):
                target["magnitude"] = cell["magnitude"]
            filled.append("momentum.%s" % key)

    # `near_term_catalyst` is a bare string at the top of layer_b, not inside either block, so
    # the loop below never reached it and a computed catalyst went nowhere.
    if _is_unknown(lb.get("near_term_catalyst")) \
            and not _is_unknown(evidence.get("near_term_catalyst")):
        lb["near_term_catalyst"] = evidence["near_term_catalyst"]
        filled.append("near_term_catalyst")

    for block in ("digital_ai_signal", "conflicting_signals"):
        src = evidence.get(block) or {}
        dst = lb.get(block)
        if not isinstance(dst, dict):
            continue
        for field, value in src.items():
            if _is_unknown(dst.get(field)) and not _is_unknown(value):
                dst[field] = value
                filled.append("%s.%s" % (block, field))

    company["_layer_b_origin"] = "stored-evidence" if filled else "constituent"
    company["_layer_b_filled"] = filled
    company["_layer_b_evidence"] = meta
    company["_layer_b_note"] = meta.get("note", "") if filled else ""
    return bool(filled)


def company_from_numeric(constituent: Dict[str, Any], *, origin: str = "live") -> Dict[str, Any]:
    """Build a Contract B from a constituent's NUMERIC dashboard fields (esg_score / momentum /
    live_signals) with NO network or LLM — so the chatbot can run the 3-stage relay on demo or
    pre-scored data coherently and offline. Identity + numbers come straight from the row."""
    c = constituent or {}
    mom = c.get("momentum") or {}
    ls = c.get("live_signals") or {}

    def n(x):
        try:
            return float(str(x).replace("−", "-").strip().rstrip("%"))
        except (TypeError, ValueError):
            return None

    score = c.get("esg_score")
    illus = " (illustrative)" if origin == "sample" else ""

    def pillar(key):
        v = n(mom.get(key))
        return {"direction": _dir_from(v), "magnitude": _pct_str(v)}

    d_ai = n(mom.get("digital_ai"))
    company = contracts.coerce_company_data({
        "company": c.get("company"), "ticker": c.get("ticker"), "sector": c.get("sector"),
        "layer_a": {
            "esg_score_static": (f"{score}" if score is not None else "unknown"),
            "as_of_date": str(c.get("esg_as_of") or "unknown"),
            "note": f"Performance score: HIGHER = better. Country-proxy baseline{illus}.",
        },
        "layer_b": {
            "momentum": {"E": pillar("environment"), "S": pillar("social"), "G": pillar("governance")},
            "digital_ai_signal": {
                "ai_governance_hiring_velocity": str(ls.get("ai_hiring_surge") or "unknown"),
                "ai_disclosure_level": ("disclosed" if ls.get("board_ai_policy") else "unknown"),
                # An empty note when there is no number, NOT the sentence "Live Digital/AI
                # momentum unknown." — `_is_unknown` tests for the bare token, so a sentence
                # containing the word counts as KNOWN and blocks the evidence fallback from
                # filling it. CelcomDigi has five digital signals and still read "unknown".
                "gap_note": (f"Live Digital/AI momentum {_pct_str(d_ai)}{illus}."
                             if d_ai is not None else ""),
            },
            "conflicting_signals": {
                "news_sentiment": "unknown", "behaviour_trend": "unknown",
                "conflict_note": (f"{int(n(ls.get('controversy_flags')))} controversy flag(s)."
                                  if n(ls.get("controversy_flags")) else ""),
            },
            "near_term_catalyst": "unknown",
        },
    }, origin=origin)
    # THE REAL BASKET REACHES HERE. `metrics.has_numbers` is True for it — CGSI's rows carry an
    # `esg_score` — but `momentum` and `live_signals` are FICTIONAL demo-only blocks, so every
    # Layer B field above resolves to "unknown" for all 52 real companies while the repo holds
    # hundreds of dated, sourced, already-scored signals for them. That is not a missing fact, it
    # is a fact nobody looked up.
    #
    # So anything still unknown is filled from the stored evidence. Gap-filling, never overwriting:
    # a constituent that really does carry numbers keeps them, and only the holes are filled.
    _fill_layer_b_from_evidence(company, c)

    company["_country"] = c.get("country") or "unknown"
    company["_exchange"] = c.get("exchange") or "unknown"
    company["_constituent_ticker"] = c.get("ticker") or c.get("id") or "unknown"
    company["_score_higher_better"] = True
    flags_n = int(n(ls.get("controversy_flags")) or 0)
    if flags_n > 0:
        company["_controversies"] = [{"title": f"Controversy flag {i + 1}{illus}"}
                                     for i in range(flags_n)]
    # Ride the ILLUSTRATIVE market-data fields as non-contract keys (contracts.py stays frozen),
    # numeric/demo path only — so the deep dive can show the financial snapshot / analyst pill.
    # Attach only when present (no None leak); evidence-only real names never reach here.
    if isinstance(c.get("market"), dict):
        company["_market"] = c["market"]
    if c.get("price_change_90d") is not None:
        company["_price_change_90d"] = c["price_change_90d"]
    if isinstance(c.get("analyst_coverage"), dict):
        company["analyst_coverage"] = c["analyst_coverage"]
    if c.get("esg_breakdown") is not None:
        company["_esg_breakdown"] = c["esg_breakdown"]
    if c.get("data_provenance") is not None:
        company["_data_provenance"] = c["data_provenance"]
    return company


def snapshot_from_company(company: Dict[str, Any]) -> Dict[str, Any]:
    """Compact monitoring summary for a dashboard card. Pure read over a Contract B dict — no
    network, no LLM. Returns rating/band/score, E-S-G momentum arrows, red-flag count, and a
    coverage fraction (how many of the 10 monitored signals are actually grounded)."""
    c = company or {}
    la = c.get("layer_a") or {}
    lb = c.get("layer_b") or {}
    mom = lb.get("momentum") or {}
    ai = lb.get("digital_ai_signal") or {}
    conf = lb.get("conflicting_signals") or {}

    # str() so a numeric esg_score_static (valid uploaded JSON, e.g. 22.4) doesn't crash the
    # regex searches below with "expected string or bytes-like object, got 'float'".
    rating = str(la.get("esg_score_static") or "unknown")
    band = ""
    if _known(rating):
        mb = _BAND_RE.search(rating)
        if mb:
            band = mb.group(1).strip().title()
        else:
            ml = _LETTER_RE.search(rating)
            band = (ml.group(1) if ml else "")
    higher_better = bool(c.get("_score_higher_better"))
    band_tone = ""
    # tone an already-found TEXT band (e.g. "13.4 (Low Risk)", "AA") by risk keywords
    if band:
        bl = band.lower()
        if "negli" in bl or "low" in bl or bl in ("aaa", "aa"):
            band_tone = "good"
        elif "med" in bl or bl in ("a", "bbb"):
            band_tone = "caution"
        elif "high" in bl or bl in ("bb", "b"):
            band_tone = "warn"
        elif "sever" in bl or bl == "ccc":
            band_tone = "bad"
    mnum = _NUM_RE.search(rating) if _known(rating) else None
    if not band and mnum:
        v = float(mnum.group(1))
        if higher_better:                       # 0–100 ESG performance score, HIGHER = better
            if v >= 70:   band, band_tone = "Leader", "good"
            elif v >= 55: band, band_tone = "Strong", "good"
            elif v >= 40: band, band_tone = "Moderate", "caution"
            elif v >= 25: band, band_tone = "Developing", "warn"
            else:         band, band_tone = "Lagging", "bad"
        else:                                   # Sustainalytics-style risk score, LOWER = better
            if v < 10:    band, band_tone = "Negligible Risk", "good"
            elif v < 20:  band, band_tone = "Low Risk", "good"
            elif v < 30:  band, band_tone = "Medium Risk", "caution"
            elif v < 40:  band, band_tone = "High Risk", "warn"
            else:         band, band_tone = "Severe Risk", "bad"

    def _dir(x):
        return (x or {}).get("direction", "unknown") or "unknown"

    momentum = {k: _dir(mom.get(k)) for k in ("E", "S", "G")}
    arrows = {k: _ARROWS.get(v, "·") for k, v in momentum.items()}

    # coverage — count grounded signals out of 10
    vals = {
        ("layer_a", "esg_score_static"): rating,
        ("layer_a", "as_of_date"): la.get("as_of_date"),
        ("momentum", "E"): None if momentum["E"] == "unknown" else momentum["E"],
        ("momentum", "S"): None if momentum["S"] == "unknown" else momentum["S"],
        ("momentum", "G"): None if momentum["G"] == "unknown" else momentum["G"],
        ("ai", "ai_disclosure_level"): ai.get("ai_disclosure_level"),
        ("conf", "news_sentiment"): conf.get("news_sentiment"),
        ("conf", "behaviour_trend"): conf.get("behaviour_trend"),
        ("catalyst", None): lb.get("near_term_catalyst"),
        ("controversies", None): "yes" if (c.get("_controversies") or []) else None,
    }
    covered = sum(1 for sig in _SNAP_SIGNALS if _known(vals.get(sig)))

    return {
        "company": c.get("company", "unknown"),
        "ticker": c.get("ticker", "unknown"),
        "country": c.get("_country", c.get("country", "unknown")),
        "sector": c.get("sector", "unknown"),
        "rating": rating,
        "rating_num": (mnum.group(1) if mnum else ""),
        "band": band,
        "band_tone": band_tone,
        "score_higher_better": higher_better,
        "as_of": la.get("as_of_date") or "unknown",
        "momentum": momentum,
        "arrows": arrows,
        "red_flags": len(c.get("_controversies") or []),
        "coverage": covered,
        "coverage_total": len(_SNAP_SIGNALS),
        "status": c.get("_build_status", "unknown"),
        "origin": c.get("_origin", "unknown"),
    }


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


def _carry_peer_score(company: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Ride an uploaded ``esg_score`` through as a non-contract field, if it is one.

    ``coerce_company_data`` keeps only contract keys, so an uploaded 0-100 score was dropped and
    the industry benchmark had nothing to compare — the only figure left was
    ``layer_a.esg_score_static``, which holds whatever the incumbent published and may run either
    way (a risk score is better when it is lower). Rather than guess a direction off a bare
    number, the benchmark uses this field, which is the SAME field name and the same convention
    our own universe files use: 0-100, higher is better.

    So an upload that follows the documented shape gets a peer comparison, and one that only
    carries a foreign static rating is reported as not comparable instead of being differenced
    against a scale it may not share. Same non-contract-field pattern as ``_market`` and
    ``_esg_breakdown`` above, so contracts.py stays frozen.
    """
    raw = data.get("esg_score")
    if isinstance(raw, bool) or raw is None:
        return
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return
    if 0.0 <= val <= 100.0:
        company["esg_score"] = val
        company["_score_higher_better"] = True


def load_upload(filename: str, content: bytes) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
        if not isinstance(data, dict):
            raise ValueError("That .json file must be a single JSON object (a CompanyData record), "
                             f"not a {type(data).__name__}.")
        company = contracts.coerce_company_data(data, origin="upload")
        company["_sources"] = [{"title": f"Uploaded file: {filename}", "url": ""}]
        company["_build_status"] = "upload"
        _carry_peer_score(company, data)
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
