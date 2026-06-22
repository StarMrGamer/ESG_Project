"""
rag.py — live retrieval (RAG) for the ASEAN ESG Momentum Radar.
===============================================================
Production grounding layer (sign-off 2026-06-23, CLAUDE.md rule 1 update). Given a query
built from the narrowed question + company, it:

  1. FETCHES real external documents — Google News RSS (recent ESG / regulatory news) and,
     optionally, a Wikipedia summary for background. No API key required.
  2. RANKS the text with a pure-Python TF-IDF + cosine retriever (no sklearn, no embeddings,
     fully offline once fetched) and returns the top-k snippets WITH their real source URLs.

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
from urllib.parse import quote
from xml.etree import ElementTree

import core

# --------------------------------------------------------------------------- #
#  CONFIG
# --------------------------------------------------------------------------- #
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
CACHE_TTL = float(os.environ.get("ESG_RAG_TTL", str(60 * 60 * 6)))  # 6 hours
DEFAULT_TOP_K = int(os.environ.get("ESG_RAG_TOP_K", "5"))
MAX_DOCS = int(os.environ.get("ESG_RAG_MAX_DOCS", "12"))
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
#  SOURCES  (real fetch via core.http_get — no API key needed)
# --------------------------------------------------------------------------- #
def _parse_rss(xml, limit):
    """Parse an RSS 2.0 feed into [{title,url,text}]. Raises FetchError if it isn't RSS."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        # Not XML — almost always a consent / redirect HTML page, not the feed.
        raise core.FetchError(
            "source returned a non-RSS page (likely a consent/redirect screen)"
        ) from e
    docs = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        src_el = item.find("source")
        src = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        text = " — ".join(x for x in (title, src, desc) if x)
        docs.append({"title": title, "url": link, "text": text})
        if len(docs) >= limit:
            break
    return docs


def _fetch_google_news(query, limit):
    """Google News RSS search (keyless). The CONSENT cookie skips the EU consent redirect."""
    xml = core.http_get(
        "https://news.google.com/rss/search",
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers={"Cookie": "CONSENT=YES+"},
    )
    return _parse_rss(xml, limit)


def _fetch_bing_news(query, limit):
    """Bing News RSS search (keyless) — fallback when Google is consent-walled or blocked."""
    xml = core.http_get("https://www.bing.com/news/search",
                        params={"q": query, "format": "rss"})
    return _parse_rss(xml, limit)


def _fetch_wikipedia(topic):
    """Background summary for a topic via the Wikipedia REST API (real, keyless). [] if none."""
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(topic.replace(" ", "_"))
    try:
        raw = core.http_get(url)
    except core.FetchError:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    extract = (data.get("extract") or "").strip()
    if not extract or data.get("type") == "disambiguation":
        return []
    page = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or url
    return [{"title": "Wikipedia — " + (data.get("title") or topic), "url": page, "text": extract}]


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
def fetch_documents(query, *, background_topic=None, max_docs=MAX_DOCS, use_cache=True):
    """Fetch real external documents for `query`. NEVER raises.

    Returns (docs, status, error): status is "cache" | "live" | "offline"; error is a short
    explanation string when nothing usable came back (else None). A blocked network / empty
    result yields ([], "offline", "<reason>") — the graceful rule-1 fallback.
    """
    cache_key = f"{query}||{background_topic or ''}||{max_docs}"
    if use_cache:
        cached = _cache_read(cache_key)
        if cached is not None:
            return cached, "cache", None

    docs, error = [], None
    for fetch in (_fetch_google_news, _fetch_bing_news):  # try sources in order
        try:
            got = fetch(query, max_docs)
        except core.FetchError as e:
            error = error or str(e)  # captured so the UI can show WHY, not just "offline".
            continue
        if got:
            docs.extend(got)
            error = None
            break
    if background_topic:
        try:
            docs.extend(_fetch_wikipedia(background_topic))
        except Exception:  # noqa: BLE001 — never let the optional source break the fetch.
            pass

    if not docs:
        return [], "offline", (error or "no usable items returned by the source(s)")
    if use_cache:
        _cache_write(cache_key, docs)
    return docs, "live", None


def gather_context(query, *, background_topic=None, k=DEFAULT_TOP_K, use_cache=True):
    """Fetch + retrieve in one call. NEVER raises.

    Returns {"snippets": [...], "status": "...", "doc_count": int, "query": query}.
    """
    docs, status, error = fetch_documents(
        query, background_topic=background_topic, use_cache=use_cache
    )
    return {
        "snippets": retrieve(query, docs, k=k),
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
    """A real, searchable background topic from the catalyst lead phrase (for Wikipedia)."""
    catalyst = (((company or {}).get("layer_b") or {}).get("near_term_catalyst") or "")
    lead = re.split(r"[—\-:]", catalyst)[0].strip()
    return lead or None
