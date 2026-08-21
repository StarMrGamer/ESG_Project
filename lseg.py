"""
lseg.py — the REAL incumbent view: LSEG's public ESG Scores, fetched live.
==========================================================================
Everything else in this repo treats the incumbent rating as a **MOCK** stand-in (`engine.py`
percentile-ranks our stored static rating and stamps every record `baseline_origin:
"MOCK-LSEG"`). This module fetches the genuine article: LSEG's own published ESG score for a
company — the overall score, the three pillar scores, the twelve theme scores underneath them,
the fiscal year it was computed on, and the company's rank inside its TRBC industry.

That is exactly the "what the rating sees" side of the argument. It is Layer A, sourced.

WHERE THE DATA COMES FROM
-------------------------
LSEG's public **Company ESG scores finder** on

    https://www.lseg.com/en/data-analytics/sustainable-finance/sustainability-ratings-and-data

whose own copy reads "Freely access companies' top level ESG scores using the ESG scores
finder below". The widget is backed by two keyless JSON endpoints on the same host, which is
what we call. This is NOT the licensed LSEG Data Library / Workspace feed (`lseg-data`), which
needs a paid subscription — it is the free public lookup, and it carries the same numbers the
page renders.

THREE THINGS THAT WILL BITE ANYONE WHO REIMPLEMENTS THIS
--------------------------------------------------------
1. **A `Referer` header is mandatory.** Without one the endpoint returns a bare `{}` with a
   200. Not an error you would notice — just silently empty. `_REFERER` below is sent on
   every call.

2. **Their cache is keyed by PATH ONLY — the `?ricCode=` querystring is ignored.** The AEM
   dispatcher in front of the endpoint caches `esg_ratings_copy.details.json` as one file for
   an hour, so the *second* company you ask for comes back holding the *first* company's
   scores — under the first company's `TR.CommonName`, so nothing looks wrong. LSEG's own
   public widget has this bug today. Wiring it up naively would paint one issuer's ESG
   breakdown onto another issuer's card, which is precisely the fabrication HARD RULE 2
   forbids. The fix is `_details_url()`: we push the RIC into the URL **path** as an extra AEM
   selector, so every company gets its own cache entry. This is *gentler* on their origin than
   a random cache-buster would be — one origin hit per company per hour, cached at the edge
   after that. Verified against seven ASEAN issuers; each returns its own name and numbers.

3. **A missing company is `{}`, not a 404.** Coverage is ~12.5k issuers; ours is not the whole
   world. An unlisted name returns empty, which we surface as `None`, never as zeros.

TERMS OF USE (read this before shipping anything that hammers it)
-----------------------------------------------------------------
The page states, verbatim: "LSEG ESG Scores may be referenced and published for non-commercial
purposes with written approval. Any commercial use, redistribution, or systematic reproduction
of the data requires a licence." So this module is deliberately built for **attributed,
on-demand, one-company-at-a-time lookup with a long local cache** — the same access pattern a
human using their finder would produce. It does NOT bulk-harvest the universe into a committed
file. `ATTRIBUTION` travels with every payload so the UI can never render these numbers
unsourced, and `data/` never receives a scrape.

RULES
-----
* All outbound HTTP goes through `core.http_get()` (rule 1/6). No `requests` import here.
* Best-effort by contract: any failure degrades to `None` / `"unknown"` (rule 1). A blocked
  network must never crash the board.
* Nothing is derived that LSEG did not state. We do not average, rescale, or fill a missing
  theme — an absent score stays absent (rule 2).
* This is REAL third-party data, labelled `_origin: "lseg-public"` (rule 3). It is never
  merged into our own momentum numbers, and it is never advice (rule 4).
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache", "lseg")

_HOST = "https://www.lseg.com"
_COMPONENT = (
    "/content/lseg/en_us/data-analytics/sustainable-finance/sustainability-ratings-and-data"
    "/jcr:content/root/container/page_content_region/page-content-region"
    "/gated_component_copy/gated-content-region/esg_ratings_copy"
)
#: The human page the finder lives on — also the Referer the endpoint demands, and the URL we
#: attribute on screen so a judge can check any number by hand.
PUBLIC_URL = (
    "https://www.lseg.com/en/data-analytics/sustainable-finance/sustainability-ratings-and-data"
)
_REFERER = PUBLIC_URL

ATTRIBUTION = "LSEG ESG Scores (public company ESG scores finder), lseg.com"

# Suggestions is the full covered-issuer list (~12.5k rows, ~760KB) and changes rarely; the
# per-company details move at most quarterly. Cache both hard so a demo does not re-fetch.
_TTL_SUGGEST = core._env_float("ESG_LSEG_SUGGEST_TTL", 60 * 60 * 24 * 7)   # 7 days
_TTL_DETAILS = core._env_float("ESG_LSEG_TTL", 60 * 60 * 24)               # 24 hours

#: LSEG's own scale legend, lifted verbatim from the widget config. Their score is 0-5 and
#: HIGHER IS BETTER — the opposite direction to the Sustainalytics-style risk score in
#: `data/hero_company.json`, so the two must never be compared without saying so.
SCALE_MAX = 5
BANDS = {
    0: "Not engaging",
    1: "Limited",
    2: "Developing",
    3: "Established",
    4: "Advanced",
    5: "Leading",
}

#: The pillar -> theme taxonomy, keys exactly as the endpoint returns them. Five environmental
#: themes, three social, four governance = the twelve segments of LSEG's wheel. Labels are
#: LSEG's, with two of their typos corrected for display ("Labour Reations",
#: "Tax Transperancy"); the KEYS are untouched because they are the wire contract.
TAXONOMY: List[Dict[str, Any]] = [
    {
        "key": "TR.EnvironmentalPillarESGScore",
        "label": "Environmental",
        "short": "E",
        "tooltip": "The Environment pillar score is the weighted average score of a company "
                   "based on the reported environmental information and the resulting five "
                   "environmental theme scores.",
        "themes": [
            {"key": "TR.ClimateTransitionThemeScore", "label": "Climate Transition"},
            {"key": "TR.EnergyandResourceUseThemeScore", "label": "Energy & Resource Use"},
            {"key": "TR.BiodiversityThemeScore", "label": "Biodiversity"},
            {"key": "TR.WaterUseThemeScore", "label": "Water Use"},
            {"key": "TR.WasteandPollutionThemeScore", "label": "Waste & Pollution"},
        ],
    },
    {
        "key": "TR.SocialPillarESGScore",
        "label": "Social",
        "short": "S",
        "tooltip": "The Social pillar score is the weighted average score of a company based "
                   "on the reported social information and the resulting three social theme "
                   "scores.",
        "themes": [
            {"key": "TR.LabourRelationsThemeScore", "label": "Labour Relations"},
            {"key": "TR.HealthandSafetyThemeScore", "label": "Health & Safety"},
            {"key": "TR.HumanRightsandCommunityThemeScore", "label": "Human Rights & Community"},
        ],
    },
    {
        "key": "TR.GovernancePillarESGScore",
        "label": "Governance",
        "short": "G",
        "tooltip": "The Governance pillar score is the weighted average score of a company "
                   "based on the reported governance information and the resulting four "
                   "governance theme scores.",
        "themes": [
            {"key": "TR.BoardandManagementThemeScore", "label": "Board & Management"},
            {"key": "TR.ShareholdersRightsThemeScore", "label": "Shareholder Rights"},
            {"key": "TR.ConductandAntiCorruptionThemeScore", "label": "Conduct & Anti-Corruption"},
            {"key": "TR.TaxTransparencyandAccountingThemeScore",
             "label": "Tax Transparency & Accounting"},
        ],
    },
]

#: RIC suffix per ASEAN exchange, so a name only has to be matched inside its own market.
#: Both the ticker prefix we store (`SGX:D05`) and the human exchange name are accepted.
EXCHANGE_SUFFIX = {
    "SGX": "SI", "SI": "SI", "SINGAPORE EXCHANGE": "SI",
    "BURSA MALAYSIA": "KL", "KLSE": "KL", "MYX": "KL", "KL": "KL",
    "IDX": "JK", "JK": "JK", "INDONESIA STOCK EXCHANGE": "JK",
    "SET": "BK", "BK": "BK", "STOCK EXCHANGE OF THAILAND": "BK",
    "PSE": "PS", "PS": "PS", "PHILIPPINE STOCK EXCHANGE": "PS",
}

#: Names our fuzzy matcher gets wrong or cannot reach. Kept tiny and explicit on purpose: a
#: hand-checked RIC is evidence, a lucky fuzzy match is not. Verified against the finder.
RIC_OVERRIDES = {
    "aneka tambang (antam)": "ANTM.JK",
}


# --------------------------------------------------------------------------- #
#  cache  (same shape as rag.py's — a flat json blob with a stamped fetch time)
# --------------------------------------------------------------------------- #
def _cache_path(key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:80]
    return os.path.join(CACHE_DIR, safe + ".json")


def _cache_read(key: str, ttl: float) -> Optional[Any]:
    try:
        path = _cache_path(key)
        if time.time() - os.path.getmtime(path) > ttl:
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — a cold/corrupt cache is a miss, never an error.
        return None


def _cache_write(key: str, payload: Any) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:  # noqa: BLE001 — an unwritable cache must not fail the lookup.
        pass


# --------------------------------------------------------------------------- #
#  name -> RIC
# --------------------------------------------------------------------------- #
_STOPWORDS = re.compile(
    r"\b(pcl|tbk|pt|bhd|berhad|ltd|limited|inc|corp|corporation|group|holdings?|plc|co|"
    r"company|public|persero|the|and|of)\b"
)


def _norm(name: str) -> str:
    """Squash a company name to its comparable core.

    ASEAN listings carry a lot of legal-form noise that differs between our universe and
    LSEG's ('Malayan Banking (Maybank)' vs 'Malayan Banking Bhd'), so strip brackets, legal
    suffixes and punctuation before comparing anything."""
    n = re.sub(r"\(.*?\)", " ", (name or "").lower())
    n = _STOPWORDS.sub(" ", n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def fetch_covered_universe(*, use_cache: bool = True) -> List[Dict[str, str]]:
    """The finder's full covered-issuer list: ``[{"companyName", "ricCode"}, ...]``.

    ~12.5k rows. Returns ``[]`` on any failure — the caller then simply cannot resolve a RIC,
    which surfaces as "not covered", never as a crash."""
    if use_cache:
        cached = _cache_read("suggestions", _TTL_SUGGEST)
        if cached is not None:
            return cached
    try:
        raw = core.http_get(_HOST + _COMPONENT + ".suggestions.json",
                            headers={"Referer": _REFERER}, retries=1)
        rows = json.loads(raw)
    except Exception:  # noqa: BLE001 — rule 1: degrade, never crash.
        return []
    if not isinstance(rows, list):
        return []
    rows = [r for r in rows if isinstance(r, dict) and r.get("ricCode")]
    if use_cache:
        _cache_write("suggestions", rows)
    return rows


def resolve_ric(company: str, exchange: str = "", *, use_cache: bool = True) -> Optional[str]:
    """Best-effort company name -> RIC, restricted to the company's own exchange when known.

    Matching is exact-on-normalised first, then a containment match, then a difflib fallback
    at a deliberately high cutoff. Anything looser starts silently returning a *different*
    company's rating, which is worse than returning nothing at all."""
    if not company:
        return None
    override = RIC_OVERRIDES.get(company.strip().lower())
    if override:
        return override

    rows = fetch_covered_universe(use_cache=use_cache)
    if not rows:
        return None

    suffix = EXCHANGE_SUFFIX.get((exchange or "").strip().upper(), "")
    pool = rows
    if suffix:
        scoped = [r for r in rows if r["ricCode"].rsplit(".", 1)[-1] == suffix]
        pool = scoped or rows  # an unknown market is better searched wide than not at all

    target = _norm(company)
    if not target:
        return None

    by_norm: Dict[str, str] = {}
    for r in pool:
        by_norm.setdefault(_norm(r.get("companyName", "")), r["ricCode"])

    if target in by_norm:
        return by_norm[target]

    contained = [ric for n, ric in by_norm.items() if n and (n in target or target in n)]
    if len(contained) == 1:
        return contained[0]

    import difflib
    close = difflib.get_close_matches(target, [n for n in by_norm if n], n=1, cutoff=0.80)
    if close:
        return by_norm[close[0]]

    # Last tier: a CONTRACTION of the legal name. Baskets carry trading names ("OCBC",
    # "SingTel"); LSEG index legal ones ("Oversea-Chinese Banking Corporation Ltd", "Singapore
    # Telecommunications Ltd"). Those share no whole token and score far below the difflib
    # cutoff, so a real issuer was being reported as "not in LSEG's ~12.5k covered issuers" —
    # a confidently wrong answer, which is the worst kind.
    #
    # The rule: does the query read as this name's words clipped and run together, in order?
    # "oversea|chinese|banking|corporation" -> o+c+b+c, and "singapore|telecommunications" ->
    # sing+tel. Both are the same rule at different prefix lengths.
    #
    # Guarded hard, because a loose acronym match is exactly how you paint one bank's ESG
    # breakdown onto another's: at least four characters, and the match must be UNIQUE inside
    # the exchange. "OCBC" hits "Oversea-Chinese Banking Corporation" on SGX and must never
    # reach "Bank OCBC NISP Tbk PT" on IDX, which is a different company.
    if len(target) >= 4:
        hits = {r["ricCode"] for r in pool
                if _is_contraction(target, _contraction_words(r.get("companyName", "")))}
        if len(hits) == 1:
            return hits.pop()
    return None


#: Legal forms that trail a company name. Stripped from the END only — "Corporation" is the
#: fourth letter of OCBC and sits in the middle of "Oversea-Chinese Banking Corporation Ltd",
#: so a blanket stopword pass (which is what `_norm` does, correctly, for its own purpose)
#: deletes exactly the word the acronym needs.
#: Deliberately NARROW: only unambiguous entity forms. "Corporation", "Group" and "Holdings"
#: stay, because they carry letters an acronym uses — strip "Corporation" and OCBC's name is
#: three words and can no longer spell OCBC.
_LEGAL_TAIL = frozenset("""ltd limited plc pcl bhd berhad inc incorporated tbk pt
    sa nv ag gmbh pjsc""".split())


def _contraction_words(name: str) -> List[str]:
    """A company name as its significant words, trailing legal forms removed."""
    words = [w for w in re.split(r"[^a-z0-9]+", (name or "").lower()) if w]
    while words and words[-1] in _LEGAL_TAIL:
        words.pop()
    return words


def _is_contraction(query: str, words: List[str]) -> bool:
    """True when `query` is `words` clipped to prefixes and concatenated, in order.

    Every word must be consumed, so "sing" alone does not match ["singapore",
    "telecommunications"] — otherwise one prefix would match half the exchange."""
    if not words or len(words) > len(query):
        return False

    def walk(w_i: int, q_i: int) -> bool:
        if w_i == len(words):
            return q_i == len(query)
        word = words[w_i]
        # try the longest prefix first so "sing"+"tel" is preferred over "s"+"ingtel"
        for take in range(min(len(word), len(query) - q_i), 0, -1):
            if query[q_i:q_i + take] == word[:take] and walk(w_i + 1, q_i + take):
                return True
        return False

    return walk(0, 0)


# --------------------------------------------------------------------------- #
#  RIC -> scores
# --------------------------------------------------------------------------- #
def _details_url(ric: str) -> str:
    """Per-RIC URL. See point 2 in the module docstring — the RIC has to be in the PATH.

    AEM reads `.details.<slug>.json` as the `details` selector plus an ignored extra selector,
    so the servlet still answers off `?ricCode=`, but the dispatcher and CloudFront both see a
    distinct resource and cache it per company instead of serving the first one to everybody."""
    slug = re.sub(r"[^a-z0-9]+", "-", ric.lower()).strip("-")
    return "%s%s.details.%s.json?ricCode=%s" % (_HOST, _COMPONENT, slug, ric)


def _num(raw: Any) -> Optional[float]:
    """LSEG sends every score as a string ('3.8', '5'). Anything unparseable is absent."""
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _band(score: Optional[float]) -> str:
    """LSEG's own legend for a score. Their bands are integer steps across 0-5."""
    if score is None:
        return "unknown"
    return BANDS.get(max(0, min(SCALE_MAX, int(score))), "unknown")


def fetch_scores(ric: str, *, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """Fetch and shape one company's LSEG ESG scores. ``None`` if uncovered or unreachable."""
    if not ric:
        return None
    if use_cache:
        cached = _cache_read("details_" + ric, _TTL_DETAILS)
        if cached is not None:
            return cached
    try:
        raw = core.http_get(_details_url(ric), headers={"Referer": _REFERER}, retries=1)
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 — rule 1.
        return None
    if not isinstance(data, dict) or not data.get("TR.CommonName"):
        return None  # `{}` = not covered. Never zeros.

    payload = _shape(ric, data)
    if use_cache:
        _cache_write("details_" + ric, payload)
    return payload


def _shape(ric: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """Wire response -> the payload the API and the UI consume. Nothing is invented here."""
    pillars = []
    for pillar in TAXONOMY:
        p_score = _num(d.get(pillar["key"]))
        themes = []
        for theme in pillar["themes"]:
            t_score = _num(d.get(theme["key"]))
            themes.append({
                "key": theme["key"], "label": theme["label"],
                "score": t_score, "band": _band(t_score),
            })
        pillars.append({
            "key": pillar["key"], "label": pillar["label"], "short": pillar["short"],
            "tooltip": pillar["tooltip"], "score": p_score, "band": _band(p_score),
            "themes": themes,
        })

    esg = _num(d.get("TR.ESGScore"))
    rank, total = _num(d.get("esgLsegRank")), _num(d.get("esgLsegTotalIndustries"))
    # Their rank is 1 = best. Express it as a top-N% for the UI, but only when both halves
    # are present and sane — a derived percentile off a missing denominator is a made-up
    # number, and rule 2 does not bend for a nicer-looking card.
    top_pct = None
    if rank and total and total > 0 and rank >= 1:
        top_pct = round(100.0 * rank / total, 1)

    return {
        "company": d.get("TR.CommonName"),
        "ric": ric,
        "esg_score": esg,
        "band": _band(esg),
        "scale_max": SCALE_MAX,
        "scale_note": "LSEG ESG score, 0-5, HIGHER IS BETTER.",
        "fiscal_year": d.get("periodenddate") or "unknown",
        "basis": "Based on %s self-reported FY %s data." % (
            d.get("TR.CommonName"), d.get("periodenddate") or "unknown"),
        "industry": d.get("industryType") or "unknown",
        "rank": int(rank) if rank else None,
        "rank_total": int(total) if total else None,
        "rank_top_pct": top_pct,
        "pillars": pillars,
        "_origin": "lseg-public",
        "source_url": PUBLIC_URL,
        "attribution": ATTRIBUTION,
        "note": "LSEG's published rating — the incumbent view, on LSEG's own 0-5 scale. NOT "
                "our momentum read, and never merged with it.",
    }


def lookup(company: str, exchange: str = "", *, ric: str = "",
           use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """The one call the server needs: name (+ exchange) or an explicit RIC -> scores or None."""
    resolved = ric or resolve_ric(company, exchange, use_cache=use_cache)
    if not resolved:
        return None
    out = fetch_scores(resolved, use_cache=use_cache)
    if out and company:
        out["matched_from"] = company  # so the UI can show WHICH name we resolved
    return out


# --------------------------------------------------------------------------- #
#  CLI — `python lseg.py "DBS Group Holdings" SGX`
# --------------------------------------------------------------------------- #
def _print(payload: Optional[Dict[str, Any]], asked: str) -> None:
    if not payload:
        print("  %-38s  not covered / unreachable" % asked)
        return
    print("\n%s  (%s)" % (payload["company"], payload["ric"]))
    print("  ESG %s / %s  (%s)   FY%s   %s" % (
        payload["esg_score"], SCALE_MAX, payload["band"],
        payload["fiscal_year"], payload["industry"]))
    if payload["rank"]:
        print("  rank %s of %s in industry  (top %s%%)" % (
            payload["rank"], payload["rank_total"], payload["rank_top_pct"]))
    for p in payload["pillars"]:
        print("  %-14s %s  (%s)" % (p["label"], p["score"], p["band"]))
        for t in p["themes"]:
            print("      %-32s %s" % (t["label"], t["score"]))


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        _print(lookup(argv[1], argv[2] if len(argv) > 2 else ""), argv[1])
        return 0

    # No args: prove coverage against our own universe.
    import universe
    rows = universe.load_universe().get("constituents", [])
    print("LSEG public ESG scores vs the ASEAN universe (%d names)\n" % len(rows))
    print("%-42s %-12s %s" % ("COMPANY", "RIC", "LSEG ESG"))
    hit = 0
    for c in rows:
        ric = resolve_ric(c["company"], c.get("exchange", ""))
        if not ric:
            print("%-42s %-12s %s" % (c["company"][:42], "-", "unresolved"))
            continue
        s = fetch_scores(ric)
        hit += 1 if s else 0
        print("%-42s %-12s %s" % (
            c["company"][:42], ric,
            ("%s (%s) FY%s" % (s["esg_score"], s["band"], s["fiscal_year"])) if s
            else "not covered"))
    print("\n%d/%d resolved to a live LSEG score." % (hit, len(rows)))
    print("Source: %s" % PUBLIC_URL)
    print("Terms: reference/publication for non-commercial purposes needs written approval; "
          "commercial use, redistribution or systematic reproduction needs a licence.")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
