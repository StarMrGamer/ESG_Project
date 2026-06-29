"""
rag.py — live retrieval (RAG) for the ASEAN ESG Momentum Radar.
===============================================================
Production grounding layer (sign-off 2026-06-23, CLAUDE.md rule 1 update). Given a query
built from the narrowed question + company, it:

  1. FETCHES real external documents from DuckDuckGo — its keyless HTML/Lite search results
     (real titles, snippets, source URLs) PLUS the DuckDuckGo Instant-Answer "AI" abstract,
     a synthesized summary the reasoner INTERPRETS. No API key required.
  2. RANKS the search text with a pure-Python TF-IDF + cosine retriever (no sklearn, no
     embeddings, fully offline once fetched) and returns the top-k snippets WITH real URLs.

Design rules it honours:
  - All outbound HTTP goes through core.http_get() (isolation; tests monkeypatch that one fn).
  - Best-effort: any fetch failure degrades to [] so Stage 2 still reasons on the dataset.
  - Never fabricates: snippets are verbatim slices of fetched text; URLs are the real links.
  - Results are cached on disk (.cache/) with a TTL so repeat runs are fast and resilient.

This module is import-safe and side-effect-free (no network at import time).
"""

import hashlib
import html
import json
import math
import os
import re
import time
from urllib.parse import unquote

import core

# --------------------------------------------------------------------------- #
#  CONFIG
# --------------------------------------------------------------------------- #
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
# guarded env parsing (core._env_*): a non-numeric tunable must not crash `import rag`.
CACHE_TTL = core._env_float("ESG_RAG_TTL", 60 * 60 * 6)  # 6 hours
DEFAULT_TOP_K = core._env_int("ESG_RAG_TOP_K", 5)
MAX_DOCS = core._env_int("ESG_RAG_MAX_DOCS", 12)
CHUNK_CHARS = 480
CHUNK_OVERLAP = 80

# A small stop-word list keeps TF-IDF focused on content terms (ESG/finance/regulatory).
_STOPWORDS = frozenset(
    """a an the of to in on for and or is are was were be been being this that these those
    with without from by as at it its their our your my his her they we you i he she them us
    about into over under more most less than then so such can will would should could may
    might must do does did has have had not no if but also which who whom whose what when
    where why how said say says new will year years""".split()
)

# Framing / domain-generic words that dilute a NEWS query (they match too much). Stripped from
# the retrieval query so the distinctive topic words (e.g. "water", "drought") drive the search.
_QUERY_GENERIC = frozenset(
    """company companies firm stock stocks shares sector industry market markets business
    chip chips chipmaker semiconductor semiconductors manufacturing manufacture supply chain
    near term long short downside upside return returns risk risks concern concerns issue
    issues exposure due affecting impact potential investment invest investing investor esg
    rating ratings score scores""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
#  TEXT UTILITIES
# --------------------------------------------------------------------------- #
def _tokenize(text):
    return [t for t in _TOKEN_RE.findall((text or "").lower())
            if len(t) > 1 and t not in _STOPWORDS]


def _strip_html(text):
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _chunks(text, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Split text into overlapping windows so a long article ranks at passage granularity."""
    text = _WS_RE.sub(" ", text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out, start = [], 0
    step = max(size - overlap, 1)
    while start < len(text):
        out.append(text[start:start + size])
        start += step
    return out


# --------------------------------------------------------------------------- #
#  TF-IDF RETRIEVAL  (pure Python — cosine over tf-idf vectors)
# --------------------------------------------------------------------------- #
def _tfidf_rank(query, chunk_texts):
    """Return [(index, score), ...] sorted by descending cosine similarity to the query."""
    docs_tokens = [_tokenize(t) for t in chunk_texts]
    n = len(docs_tokens)
    if n == 0:
        return []
    df = {}
    for toks in docs_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1

    def idf(term):
        return math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0

    def vec(tokens):
        if not tokens:
            return {}
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        inv = 1.0 / len(tokens)
        return {t: (c * inv) * idf(t) for t, c in tf.items()}

    qv = vec(_tokenize(query))
    if not qv:
        return []
    qnorm = math.sqrt(sum(w * w for w in qv.values())) or 1.0

    scored = []
    for i, toks in enumerate(docs_tokens):
        dv = vec(toks)
        if not dv:
            continue
        dot = sum(qv.get(t, 0.0) * w for t, w in dv.items())
        if dot <= 0.0:
            continue
        dnorm = math.sqrt(sum(w * w for w in dv.values())) or 1.0
        scored.append((i, dot / (qnorm * dnorm)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def retrieve(query, documents, k=DEFAULT_TOP_K):
    """Rank chunks of `documents` against `query`; return top-k snippets with provenance.

    Args:
        query:     the retrieval query string.
        documents: list of {"title", "url", "text"} dicts (from fetch_documents).
        k:         how many snippets to return.
    Returns:
        list of {"title", "url", "snippet", "score"} ordered by relevance (dedup'd).
    """
    chunks = []  # (text, title, url)
    for d in documents or []:
        for ch in _chunks(d.get("text", "")):
            chunks.append((ch, d.get("title", ""), d.get("url", "")))
    if not chunks:
        return []
    out, seen, seen_titles = [], set(), set()
    for idx, score in _tfidf_rank(query, [c[0] for c in chunks]):
        text, title, url = chunks[idx]
        tkey = (title or "").strip().lower()[:80]  # collapse the same story from two sources
        if (url, text[:60]) in seen or (tkey and tkey in seen_titles):
            continue
        seen.add((url, text[:60]))
        if tkey:
            seen_titles.add(tkey)
        out.append({"title": title, "url": url, "snippet": text, "score": round(score, 4)})
        if len(out) >= k:
            break
    return out


# --------------------------------------------------------------------------- #
#  SOURCES  (real fetch via core.http_get — DuckDuckGo, no API key needed)
# --------------------------------------------------------------------------- #
# A browser-like UA: DuckDuckGo's HTML/Lite endpoints serve a challenge page to obvious bots.
_DDG_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

_DDG_RESULT_RE = re.compile(r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_DDG_SNIPPET_RE = re.compile(r'result__snippet[^>]*>(.*?)</a>', re.S | re.I)
_LITE_LINK_RE = re.compile(r'result-link[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_LITE_SNIPPET_RE = re.compile(r'result-snippet[^>]*>(.*?)</td>', re.S | re.I)


def _ddg_unwrap(href):
    """Turn a DuckDuckGo redirect ('//duckduckgo.com/l/?uddg=...') into the real target URL."""
    href = html.unescape((href or "").strip())
    if href.startswith("//"):
        href = "https:" + href
    m = re.search(r"[?&]uddg=([^&]+)", href)
    return unquote(m.group(1)) if m else href


def _zip_results(titles, snippets, limit):
    """Pair parsed (href, title) tuples with snippets positionally into [{title,url,text}]."""
    docs = []
    for i, (href, raw_title) in enumerate(titles):
        title = _strip_html(raw_title)
        if not title:
            continue
        snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
        text = " — ".join(x for x in (title, snippet) if x)
        docs.append({"title": title, "url": _ddg_unwrap(href), "text": text})
        if len(docs) >= limit:
            break
    return docs


def _fetch_ddg_html(query, limit):
    """DuckDuckGo HTML results (keyless GET). Real titles, snippets, and source URLs."""
    page = core.http_get("https://html.duckduckgo.com/html/",
                         params={"q": query, "kl": "us-en"}, headers=_DDG_HEADERS)
    docs = _zip_results(_DDG_RESULT_RE.findall(page), _DDG_SNIPPET_RE.findall(page), limit)
    if not docs:
        raise core.FetchError("DuckDuckGo HTML returned no parseable results (challenge page?)")
    return docs


def _fetch_ddg_lite(query, limit):
    """DuckDuckGo Lite results (keyless GET) — simpler markup; fallback when HTML is walled."""
    page = core.http_get("https://lite.duckduckgo.com/lite/",
                         params={"q": query, "kl": "us-en"}, headers=_DDG_HEADERS)
    docs = _zip_results(_LITE_LINK_RE.findall(page), _LITE_SNIPPET_RE.findall(page), limit)
    if not docs:
        raise core.FetchError("DuckDuckGo Lite returned no parseable results")
    return docs


def _fetch_ddg_instant(query):
    """DuckDuckGo Instant-Answer API (keyless GET) — the synthesized 'AI' abstract + related
    topics. Returns {"summary","url","source","related":[...]} or None. NEVER raises.

    The abstract is real, sourced text (it carries an AbstractURL) — the reasoner INTERPRETS
    it; it is never presented as a fabricated company fact (HARD RULE 2)."""
    try:
        raw = core.http_get("https://api.duckduckgo.com/", params={
            "q": query, "format": "json", "no_html": "1", "skip_disambig": "1",
        }, headers=_DDG_HEADERS)
    except core.FetchError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):  # valid JSON but a list/number/null -> degrade, never .get-crash
        return None
    summary = _strip_html(data.get("AbstractText") or "")
    related = []
    for topic in (data.get("RelatedTopics") or []):
        items = topic.get("Topics") if isinstance(topic, dict) and topic.get("Topics") else [topic]
        for it in items:
            if not isinstance(it, dict):
                continue
            text = _strip_html(it.get("Text") or "")
            furl = (it.get("FirstURL") or "").strip()
            if text and furl:
                related.append({"title": text[:90], "url": furl, "text": text})
    if not summary and not related:
        return None
    return {
        "summary": summary,
        "url": (data.get("AbstractURL") or "").strip(),
        "source": (data.get("AbstractSource") or "DuckDuckGo").strip(),
        "related": related,
    }


# --------------------------------------------------------------------------- #
#  ON-DISK CACHE  (TTL'd — fast repeats, resilient to a flaky network)
# --------------------------------------------------------------------------- #
def _cache_path(key):
    return os.path.join(CACHE_DIR, hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] + ".json")


def _cache_read(key):
    try:
        with open(_cache_path(key), encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict):  # a hand-edited/non-object cache file must not .get-crash
        return None
    if time.time() - blob.get("ts", 0) > CACHE_TTL:
        return None
    return blob.get("docs")


def _cache_write(key, docs):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "docs": docs}, f)
    except OSError:
        pass  # cache is an optimisation, never load-bearing.


# --------------------------------------------------------------------------- #
#  PUBLIC API
# --------------------------------------------------------------------------- #
def fetch_documents(query, *, max_docs=MAX_DOCS, use_cache=True):
    """Fetch real DuckDuckGo search documents for `query`. NEVER raises.

    Returns (docs, status, error): status is "cache" | "live" | "offline"; error is a short
    reason when nothing usable came back (else None). A blocked network / empty result yields
    ([], "offline", "<reason>") — the graceful rule-1 fallback. Each doc = {title,url,text}.
    """
    cache_key = f"ddg::{query}::{max_docs}"
    if use_cache:
        cached = _cache_read(cache_key)
        if cached is not None:
            return cached, "cache", None

    docs, error = [], None
    for fetch in (_fetch_ddg_html, _fetch_ddg_lite):  # HTML first, Lite as the fallback
        try:
            got = fetch(query, max_docs)
        except core.FetchError as e:
            error = error or str(e)  # captured so the UI can show WHY, not just "offline".
            continue
        if got:
            docs.extend(got)
            error = None
            break

    if not docs:
        return [], "offline", (error or "no usable DuckDuckGo results returned")
    if use_cache:
        _cache_write(cache_key, docs)
    return docs, "live", None


def fetch_ai_summary(query, *, use_cache=True):
    """DuckDuckGo's synthesized 'AI' summary for `query` (cached). NEVER raises; None if absent.

    Returns {"summary","url","source","related":[...]} — the Instant-Answer abstract the
    reasoner INTERPRETS, plus any related topics (real URLs) folded into the cited snippets."""
    cache_key = f"ddg-ai::{query}"
    if use_cache:
        cached = _cache_read(cache_key)
        if cached is not None:
            return cached or None
    ai = _fetch_ddg_instant(query)
    if use_cache and ai is not None:
        _cache_write(cache_key, ai)
    return ai


def gather_context(query, *, background_topic=None, k=DEFAULT_TOP_K, use_cache=True):
    """Fetch (DuckDuckGo search + the DuckDuckGo AI summary) + rank, in one call. NEVER raises.

    Returns {"snippets", "ai_summary", "status", "doc_count", "query", "error"}. ``ai_summary``
    is DuckDuckGo's synthesized abstract ({"summary","url","source"}) for the agent to
    INTERPRET; ``snippets`` are the ranked search results (real URLs) it cites as [n].
    ``background_topic`` (the catalyst lead / entity) is the cleaner query for the abstract.
    """
    docs, status, error = fetch_documents(query, use_cache=use_cache)
    ai = fetch_ai_summary(background_topic or query, use_cache=use_cache)
    if ai and ai.get("related"):
        docs = docs + ai["related"]          # related topics are citable (real URLs)
    if status == "offline" and ai:           # the AI summary answered even though search didn't
        status, error = "live", None
    return {
        "snippets": retrieve(query, docs, k=k),
        "ai_summary": ({"summary": ai["summary"], "url": ai["url"], "source": ai["source"]}
                       if ai and (ai.get("summary") or "").strip() else None),
        "status": status,
        "doc_count": len(docs),
        "query": query,
        "error": error,
    }


def build_query(narrowed_question, company):
    """Build a focused KEYWORD query for news search — company name + the salient content
    words of the narrowed question + sector + catalyst. A full question SENTENCE returns poor
    news results, so we extract keywords (stop-words dropped) instead of passing it raw."""
    nq = narrowed_question or {}
    comp = company or {}

    def clean(v):
        v = (v or "").strip()
        return "" if v.lower() == "unknown" else v

    name = clean(comp.get("company"))
    sector = clean(nq.get("sector") or comp.get("sector"))
    catalyst = clean((comp.get("layer_b") or {}).get("near_term_catalyst"))

    # Distinctive topic words: drop stop-words, domain-generic fillers, and the company's own
    # name tokens (already in `name`). Fall back to the full token set if that empties it.
    name_toks = set(_tokenize(name))
    toks = _tokenize(nq.get("narrowed_question") or "")
    topic = [t for t in toks if t not in _QUERY_GENERIC and t not in name_toks] or toks

    kws, seen = [], set()
    for t in topic:
        if t not in seen:
            seen.add(t)
            kws.append(t)
    parts = [name, sector, " ".join(kws[:8]), catalyst]
    q = _WS_RE.sub(" ", " ".join(p for p in parts if p)).strip()
    return q[:200]


def background_topic(company):
    """A real, searchable entity from the catalyst lead phrase (cleaner query for the AI summary)."""
    catalyst = (((company or {}).get("layer_b") or {}).get("near_term_catalyst") or "")
    lead = re.split(r"[—\-:]", catalyst)[0].strip()
    return lead or None
