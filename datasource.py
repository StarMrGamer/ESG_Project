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
def build_live_company(user_text, *, use_rag=True, k=None):
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


def build_company_from_constituent(constituent, *, use_rag=True, k=None):
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


def company_from_numeric(constituent, *, origin="live"):
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
                "gap_note": f"Live Digital/AI momentum {_pct_str(d_ai)}{illus}.",
            },
            "conflicting_signals": {
                "news_sentiment": "unknown", "behaviour_trend": "unknown",
                "conflict_note": (f"{int(n(ls.get('controversy_flags')))} controversy flag(s)."
                                  if n(ls.get("controversy_flags")) else ""),
            },
            "near_term_catalyst": "unknown",
        },
    }, origin=origin)
    company["_country"] = c.get("country") or "unknown"
    company["_exchange"] = c.get("exchange") or "unknown"
    company["_constituent_ticker"] = c.get("ticker") or c.get("id") or "unknown"
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


def snapshot_from_company(company):
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
    mnum = _NUM_RE.search(rating) if _known(rating) else None
    # Derive Sustainalytics band from a plain numeric score when no text band was found.
    if not band and mnum:
        v = float(mnum.group(1))
        if v < 10:
            band = "Negligible Risk"
        elif v < 20:
            band = "Low Risk"
        elif v < 30:
            band = "Medium Risk"
        elif v < 40:
            band = "High Risk"
        else:
            band = "Severe Risk"

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
        if not isinstance(data, dict):
            raise ValueError("That .json file must be a single JSON object (a CompanyData record), "
                             f"not a {type(data).__name__}.")
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
