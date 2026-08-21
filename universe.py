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

import copy
import os
from typing import Any, Dict, List, Optional
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(BASE_DIR, "data", "asean_universe.json")
DEMO_FILE = os.path.join(BASE_DIR, "data", "demo_universe.json")  # fictional, fully-numeric demo set

# The five markets MSCI ASEAN spans. Used to order/group the universe grid.
ASEAN_COUNTRIES = ("Singapore", "Malaysia", "Indonesia", "Thailand", "Philippines")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CACHE = {}  # path -> {"mtime", "data"} : per-file mtime cache so Streamlit reruns don't re-read disk


def active_file(demo: bool = False) -> str:
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
    # market / news / analyst_coverage are ILLUSTRATIVE demo-only fields (HARD RULE 2: the real
    # evidence universe never carries them, so the market-data panels show "awaiting data").
    for k in ("esg_score", "esg_as_of", "momentum", "live_signals", "price_change_90d",
              "market", "news", "analyst_coverage"):
        if c.get(k) is not None:
            out[k] = c[k]
    if "esg_breakdown" in c:
        out["esg_breakdown"] = c["esg_breakdown"]
    if "data_provenance" in c:
        out["data_provenance"] = c["data_provenance"]
    # Optional DOCUMENTATION fields — the evidence for why a name is an ESG improver.
    for k in ("esg_basis", "source_url", "source_url_2", "confidence", "esg_score_basis",
              "as_of"):
        if c.get(k):
            out[k] = str(c[k]).strip()
    # `events` is the DATED evidence block `signals.from_company` scores: each item carries its
    # own text, source URL, publication date and source type. The CGSI basket ships it (built
    # by `scripts/build_cgsi_basket.py` from their verified rows); dropping it here would leave
    # the engine scoring nothing but `esg_basis` prose and silently starve every real name.
    if isinstance(c.get("events"), list):
        out["events"] = c["events"]
    # CGSI basket fields. `industry` is their own label and is what the OECD benchmark joins
    # on, so it must survive alongside the descriptive `sector`.
    if isinstance(c.get("aliases"), list):
        out["aliases"] = [str(a) for a in c["aliases"] if a]
    for k in ("bbg_code", "ric", "industry", "incumbent_notch", "green_bond_classification",
              "profitability_flag"):
        if c.get(k):
            out[k] = str(c[k]).strip()
    for k in ("high_conviction", "delisted"):
        if c.get(k) is not None:
            out[k] = bool(c[k])
    return out


def load_universe(path: Optional[str] = None) -> Dict[str, Any]:
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
    rd = raw if isinstance(raw, dict) else {}
    # derive items from rd (not raw) so a valid-but-scalar/null/bool top level degrades to []
    # instead of raising AttributeError on raw.get — honouring the no-raise contract (HARD RULE 1).
    items = raw if isinstance(raw, list) else (rd.get("constituents") or [])
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


def constituents(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Just the list of constituent dicts."""
    return load_universe(path).get("constituents", [])


def countries(path: Optional[str] = None) -> List[str]:
    """Distinct countries present, ordered by ASEAN_COUNTRIES then any extras alphabetically."""
    present = {c["country"] for c in constituents(path) if c["country"] != "unknown"}
    ordered = [c for c in ASEAN_COUNTRIES if c in present]
    return ordered + sorted(present - set(ordered))


def sectors(path: Optional[str] = None) -> List[str]:
    """Distinct sectors present (alphabetical) — for the dashboard filter."""
    return sorted({c["sector"] for c in constituents(path) if c["sector"] != "unknown"})


def filter_constituents(country: Optional[str] = None, sector: Optional[str] = None,
                        query: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, Any]]:
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


def get(ticker: str, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Exact constituent lookup by ticker id. Returns a COPY so a caller mutating the result
    (e.g. stamping a transient flag) can never poison the module-level mtime cache."""
    for c in constituents(path):
        if c["ticker"] == ticker or c["id"] == ticker:
            return copy.deepcopy(c)
    return None


def resolve(text: str, path: Optional[str] = None, *, min_score: int = 2) -> Optional[Dict[str, Any]]:
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
        # Parenthetical alias, e.g. "(BCA)" / "(OCBC)" — a common way users name these — plus
        # any alias the basket carries. CGSI write terse names ("Bank Central Asia"), so without
        # the alias list "add BCA" and "show Maybank" stop resolving.
        alias_pool = list(re.findall(r"\(([^)]+)\)", c["company"]))
        alias_pool += [a for a in (c.get("aliases") or []) if isinstance(a, str)]
        for alias in alias_pool:
            alias = alias.lower().strip()
            if not alias:
                continue
            if alias in qtoks or (len(alias) > 3 and alias in low):
                score += 4
            else:
                alias_toks = set(_tokens(alias)) - _GENERIC_TOKENS
                if alias_toks and alias_toks <= qtoks:
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
    # COPY the winner so a caller mutating it can't leak into the shared cache (see get()).
    return copy.deepcopy(best) if best_score >= min_score else None


def to_seed_company(constituent: Dict[str, Any]) -> Dict[str, Any]:
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


def scope_terms(constituent: Dict[str, Any]) -> List[str]:
    """Disambiguation suffix for a retrieval query — the company's market + exchange + 'ASEAN'.
    Folded into datasource/rag queries so 'fetch' finds the right ASEAN-listed entity."""
    c = constituent or {}
    parts = [p for p in (c.get("country"), c.get("exchange")) if p and p != "unknown"]
    return " ".join(parts + ["ASEAN"]).strip()
