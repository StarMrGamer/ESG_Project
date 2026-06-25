"""
universe.py — the ASEAN base database (the ESG-improver universe).
==================================================================
Loads `data/asean_universe.json` — the universe of companies the radar monitors — and exposes
filtering + name/ticker resolution so the dashboard can browse it and the chatbot can map a
free-text request ("add DBS", "BCA", "PTT") onto a real constituent.

WHAT THE UNIVERSE IS (per the ESG Momentum 2.0 foundation): "52 ASEAN companies with consistent
ESG improvement 2019-2023" (ESG-score 5-year CAGR as the momentum signal). MSCI ASEAN is the
performance BENCHMARK that basket beat — NOT the source of the names. The shipped list is a
labelled STARTER proxy; replace `constituents` with the authoritative 52 and everything updates.

Design rules it honours:
  - Import-safe & network-free: this is a local JSON read, NOT the company *dataset* (Layer A/B
    are still built live per company by datasource.py). The universe is just the watchlist menu.
  - Frozen contracts untouched: `country` / `exchange` ride as non-contract fields (`_country`,
    `_exchange`) on the seed company, so contracts.py needs no sign-off.

The radar is ASEAN-focused: every constituent carries its country + home exchange, which the
live builder folds into retrieval queries so "fetch" finds the RIGHT ASEAN company (e.g. it
disambiguates Singapore's UOB from a same-named foreign entity).
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(BASE_DIR, "data", "asean_universe.json")
DEMO_FILE = os.path.join(BASE_DIR, "data", "demo_universe.json")  # fictional, fully-numeric demo set

# The five markets MSCI ASEAN spans. Used to order/group the universe grid.
ASEAN_COUNTRIES = ("Singapore", "Malaysia", "Indonesia", "Thailand", "Philippines")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CACHE = {}  # path -> {"mtime", "data"} : per-file mtime cache so Streamlit reruns don't re-read disk


def active_file(demo=False):
    """Which universe JSON to load — the fictional demo set, or the real ASEAN base DB."""
    return DEMO_FILE if demo else UNIVERSE_FILE

# Generic corporate-suffix / filler tokens — they match too many names, so they don't count
# toward a resolve() overlap (otherwise "random corp" spuriously hits "...Banking Corp").
_GENERIC_TOKENS = frozenset(
    """corp corporation co company ltd limited group holdings holding berhad bhd pcl plc inc
    incorporated the and of for international intl national bank banking finance financial
    industries industry development ventures pacific energy add monitor track watch want""".split()
)


def _tokens(text):
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1]


def _coerce_constituent(c):
    """Keep only the universe keys, filling any gap with 'unknown'. `id` = ticker (stable key)."""
    c = c or {}
    company = str(c.get("company") or "unknown").strip() or "unknown"
    ticker = str(c.get("ticker") or "unknown").strip() or "unknown"
    out = {
        "id": ticker,                                    # stable key for the watchlist / session
        "company": company,
        "ticker": ticker,
        "exchange": str(c.get("exchange") or "unknown").strip() or "unknown",
        "country": str(c.get("country") or "unknown").strip() or "unknown",
        "sector": str(c.get("sector") or "unknown").strip() or "unknown",
        # Optional foundation field — the basket's selection metric (blank until provided).
        "esg_cagr_2019_2023": str(c.get("esg_cagr_2019_2023") or "").strip(),
    }
    # Optional NUMERIC dashboard fields — passed through verbatim for metrics.py (absent is fine).
    for k in ("esg_score", "esg_as_of", "momentum", "live_signals", "price_change_90d"):
        if c.get(k) is not None:
            out[k] = c[k]
    # Optional DOCUMENTATION fields — the evidence for why a name is an ESG improver.
    for k in ("esg_basis", "source_url", "confidence"):
        if c.get(k):
            out[k] = str(c[k]).strip()
    return out


def load_universe(path=None):
    """Load the base DB. Returns {"note","benchmark","as_of","countries","constituents":[...]}.

    Cached on file mtime so repeated Streamlit reruns don't re-read disk; drop in a new
    msci_asean.json and the cache invalidates on the next call. Never raises on a missing/locked
    file — returns an empty universe so the app degrades gracefully instead of crashing.
    """
    import json
    path = path or UNIVERSE_FILE
    empty = {"note": "", "selection": "", "benchmark": "MSCI ASEAN", "benchmark_stats": {},
             "as_of": "", "countries": list(ASEAN_COUNTRIES), "constituents": []}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return empty
    hit = _CACHE.get(path)
    if hit and hit["mtime"] == mtime:
        return hit["data"]
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return empty
    items = raw if isinstance(raw, list) else (raw.get("constituents") or [])
    rd = raw if isinstance(raw, dict) else {}
    data = {
        "note": rd.get("note") or "",
        "selection": rd.get("selection") or "",
        "benchmark": rd.get("benchmark") or "MSCI ASEAN",
        "benchmark_stats": rd.get("benchmark_stats") or {},
        "as_of": rd.get("as_of") or "",
        "countries": rd.get("countries") or list(ASEAN_COUNTRIES),
        "constituents": [_coerce_constituent(c) for c in items if isinstance(c, dict)],
    }
    _CACHE[path] = {"mtime": mtime, "data": data}
    return data


def constituents(path=None):
    """Just the list of constituent dicts."""
    return load_universe(path).get("constituents", [])


def countries(path=None):
    """Distinct countries present, ordered by ASEAN_COUNTRIES then any extras alphabetically."""
    present = {c["country"] for c in constituents(path) if c["country"] != "unknown"}
    ordered = [c for c in ASEAN_COUNTRIES if c in present]
    return ordered + sorted(present - set(ordered))


def sectors(path=None):
    """Distinct sectors present (alphabetical) — for the dashboard filter."""
    return sorted({c["sector"] for c in constituents(path) if c["sector"] != "unknown"})


def filter_constituents(country=None, sector=None, query=None, path=None):
    """Filter the universe by country and/or sector and/or a free-text substring."""
    q = (query or "").strip().lower()
    out = []
    for c in constituents(path):
        if country and country != "All" and c["country"] != country:
            continue
        if sector and sector != "All" and c["sector"] != sector:
            continue
        if q and q not in (c["company"] + " " + c["ticker"] + " " + c["sector"]).lower():
            continue
        out.append(c)
    return out


def get(ticker, path=None):
    """Exact constituent lookup by ticker id."""
    for c in constituents(path):
        if c["ticker"] == ticker or c["id"] == ticker:
            return c
    return None


def resolve(text, path=None, *, min_score=2):
    """Map a free-text request ("add DBS", "BCA bank", "SET:PTT") onto ONE constituent.

    Scores each constituent by token overlap + substring hits against its name/ticker/country.
    Returns the best match (dict) or None if nothing clears `min_score`. This is how the chatbot
    decides which ASEAN name to pin — it keeps the watchlist inside the MSCI ASEAN universe.
    """
    text = (text or "").strip()
    if not text:
        return None
    low = text.lower()
    qtoks = set(_tokens(text))
    best, best_score = None, 0.0
    for c in constituents(path):
        name, tick = c["company"].lower(), c["ticker"].lower()
        score = 0.0
        # Strong signals: ticker mention, or the full company name as a substring of the query.
        code = tick.split(":")[-1]
        if tick in low or (code and code in qtoks):
            score += 5
        # Parenthetical alias, e.g. "(BCA)" / "(OCBC)" — a common way users name these.
        for alias in re.findall(r"\(([^)]+)\)", c["company"]):
            if alias.lower() in low or alias.lower() in qtoks:
                score += 4
        ntoks = set(_tokens(c["company"])) - _GENERIC_TOKENS
        overlap = (qtoks - _GENERIC_TOKENS) & ntoks
        score += 2 * len(overlap)
        # Substring of a multi-word name (e.g. "ayala land" inside the query).
        if len(name) > 3 and name in low:
            score += 3
        if c["country"].lower() in low:
            score += 0.5
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= min_score else None


def to_seed_company(constituent):
    """A minimal identity seed (NOT a full Contract B) the live builder anchors on, so retrieval
    is ASEAN-scoped and the company is disambiguated by its real country + home exchange."""
    c = constituent or {}
    return {
        "company": c.get("company") or "unknown",
        "ticker": c.get("ticker") or "unknown",
        "sector": c.get("sector") or "unknown",
        "_country": c.get("country") or "unknown",
        "_exchange": c.get("exchange") or "unknown",
    }


def scope_terms(constituent):
    """Disambiguation suffix for a retrieval query — the company's market + exchange + 'ASEAN'.
    Folded into datasource/rag queries so 'fetch' finds the right ASEAN-listed entity."""
    c = constituent or {}
    parts = [p for p in (c.get("country"), c.get("exchange")) if p and p != "unknown"]
    return " ".join(parts + ["ASEAN"]).strip()
