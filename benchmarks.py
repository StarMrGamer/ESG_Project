"""Industry benchmarks — what "good" looks like for the industry a company sits in.

Two benchmarks, deliberately kept apart because they answer different questions and are not in
the same unit:

  ASEAN peer average   the mean ESG score of this industry inside our own universe. Same unit as
                       the company, so the comparison is direct: is this name ahead of or behind
                       its ASEAN peers?
  OECD industry        greenhouse-gas intensity for the industry across OECD members, in tonnes
                       CO2e per million USD of gross value added. A different unit and a
                       different question: is this industry structurally clean or dirty, and so
                       how much should a given score impress you?

Averaging the two into one "benchmark score" would be inventing a number, so nothing here does.
Both are reported side by side with their own units, counts and provenance.

The OECD figures are read from ``data/oecd_industry_benchmark.csv``, which is REAL data pulled
from the OECD's public SDMX endpoint by ``scripts/build_oecd_benchmark.py``. This module never
fetches: the extract behind that CSV is ~10 MB and a request path cannot wait on it. The CSV
carries the year, the contributing countries, the two query URLs and the retrieval date, and
everything below passes that provenance through to the caller.

The sector crosswalk is a STATED MAPPING, not data. Our universe labels companies with
``GICS sector — sub-industry`` strings; the OECD reports ISIC groups. Each rule below is an
explicit editorial choice and is reported as such via ``via``. A sector that matches no rule
comes back unmatched — never guessed into the nearest bucket.
"""
import csv
import os

import metrics
import universe

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OECD_FILE = os.path.join(DATA_DIR, "oecd_industry_benchmark.csv")

# --------------------------------------------------------------------------- #
#  The crosswalk
# --------------------------------------------------------------------------- #
# Checked in order against the WHOLE sector string, lower-cased. These exist because the GICS
# sector prefix is sometimes the wrong signal: an oil-palm plantation filed under Consumer
# Staples is agriculture, and an airport filed under Industrials is transport.
# Order is load-bearing, and the real-estate rules come first on purpose: "Real Estate — Retail
# Malls" and "Real Estate — Industrial & Logistics REIT" both contain a trade/transport word, and
# a landlord letting shop space is a real-estate business, not a retailer.
SUBINDUSTRY_RULES = [
    ("reit", "L"), ("data centre", "L"), ("developer", "L"), ("malls", "L"),
    ("commercial property", "L"),
    ("palm oil", "A"), ("plantation", "A"), ("agribusiness", "A"),
    ("metals & mining", "BTE"), ("nickel", "BTE"), ("aluminium", "BTE"),
    ("airport", "GTI"), ("land transport", "GTI"), ("marine shipping", "GTI"),
    ("logistics", "GTI"), ("retail", "GTI"), ("restaurant", "GTI"),
    ("construction materials", "C"),
    ("property & construction", "F"),
    ("telecom towers", "J"),
]

# The fallback: GICS sector prefix -> ISIC group.
SECTOR_RULES = {
    "energy": "BTE",
    "materials": "C",
    "industrials": "C",
    "consumer discretionary": "GTI",
    "consumer staples": "C",
    "health care": "C",
    "financials": "K",
    "information technology": "C",
    "technology": "C",
    "communication services": "J",
    "utilities": "BTE",
    "real estate": "L",
}


def _rows_and_meta(path=OECD_FILE):
    """Parse the benchmark CSV into (rows, meta). The leading ``#`` lines carry the provenance."""
    meta, lines = {}, []
    with open(path, newline="", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                body = line[1:].strip()
                key, _, val = body.partition(":")
                if val.strip():
                    meta[key.strip().lower().replace(" ", "_")] = val.strip()
                else:
                    meta.setdefault("note", body)
            else:
                lines.append(line)
    rows = []
    for r in csv.DictReader(lines):
        for k in ("ghg_t_co2e", "gva_usd", "intensity_t_per_musd", "cleanliness_percentile"):
            r[k] = metrics.num(r.get(k))
        r["rank_cleanest"] = int(r["rank_cleanest"]) if r.get("rank_cleanest") else None
        rows.append(r)
    return rows, meta


_CACHE = {}


def load_oecd(path=OECD_FILE):
    """{'rows': [...], 'meta': {...}} — cached, since the file never changes during a run."""
    if path not in _CACHE:
        if not os.path.exists(path):
            _CACHE[path] = {"rows": [], "meta": {}, "available": False}
        else:
            rows, meta = _rows_and_meta(path)
            _CACHE[path] = {"rows": rows, "meta": meta, "available": bool(rows)}
    return _CACHE[path]


def isic_for_sector(sector):
    """Map one of our sector strings onto an ISIC group, reporting HOW it matched.

    Returns ``{"code", "via", "matched_on"}`` or ``None`` when no rule applies. `via` is carried
    all the way to the UI so a reader can see whether the industry was matched on its specific
    sub-industry or merely on its GICS sector.
    """
    if not sector or sector.lower() in ("", "unknown", "all"):
        return None
    low = sector.lower()
    for needle, code in SUBINDUSTRY_RULES:
        if needle in low:
            return {"code": code, "via": "sub-industry", "matched_on": needle}
    head = low.split("—")[0].strip()
    if head in SECTOR_RULES:
        return {"code": SECTOR_RULES[head], "via": "GICS sector", "matched_on": head}
    return None


def oecd_for_sector(sector, path=OECD_FILE):
    """The OECD industry benchmark for one sector, or an explicit 'unmatched'/'unavailable'."""
    book = load_oecd(path)
    if not book["available"]:
        return {"available": False, "reason": "no OECD benchmark file — run "
                                              "scripts/build_oecd_benchmark.py"}
    hit = isic_for_sector(sector)
    if not hit:
        return {"available": False, "reason": f"no ISIC crosswalk rule for “{sector}”",
                "sector": sector}
    row = next((r for r in book["rows"] if r["isic_code"] == hit["code"]), None)
    if not row:
        return {"available": False, "reason": f"ISIC {hit['code']} not in the benchmark file"}
    rows = book["rows"]
    meta = book["meta"]
    return {
        "available": True,
        "sector": sector,
        "isic_code": row["isic_code"],
        "isic_label": row["isic_label"],
        "isic_sections": row["isic_sections"],
        "via": hit["via"],
        "matched_on": hit["matched_on"],
        "intensity": row["intensity_t_per_musd"],
        "unit": "t CO2e per US$m of gross value added",
        "rank": row["rank_cleanest"],
        "of": len(rows),
        "percentile": row["cleanliness_percentile"],
        "cleanest": rows[0]["isic_label"] if rows else None,
        "dirtiest": rows[-1]["isic_label"] if rows else None,
        "median": _median([r["intensity_t_per_musd"] for r in rows]),
        "year": row["year"],
        "basis": meta.get("basis", ""),
        "retrieved": meta.get("retrieved", ""),
        "sources": [v for k, v in meta.items() if k in ("emissions", "value_added")],
    }


def _median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else round((vals[mid - 1] + vals[mid]) / 2, 4)


def asean_for_sector(sector, path=None, demo=False):
    """The ASEAN peer average for one sector, in whichever unit that universe actually supports."""
    path = path or universe.active_file(demo)
    peers = universe.filter_constituents(sector=sector or "All", path=path)
    if not peers:
        return {"available": False, "reason": "no ASEAN peers in this industry", "n": 0}
    if metrics.has_numbers(peers):
        avg, n = metrics.average_esg(peers)
        metric, unit, kind = "mean static ESG score", "0–100", "static"
    else:
        avg, n = metrics.evidence_average(peers)
        metric, unit, kind = ("mean ESG-leadership (derived from cited ratings)", "0–100",
                              "evidence")
    if avg is None:
        return {"available": False, "reason": "peers carry no scorable data yet", "n": len(peers)}
    return {"available": True, "sector": sector, "average": avg, "n": n,
            "metric": metric, "metric_kind": kind, "unit": unit,
            "universe": os.path.basename(path)}


def industry_table(path=None, demo=False):
    """Every industry in the active universe, with both benchmarks side by side.

    This is the "average for each industry, so you can see which is good and bad" view: the ASEAN
    column ranks our own names, the OECD column says what the industry's structural footprint is.
    """
    path = path or universe.active_file(demo)
    out = []
    for sector in universe.sectors(path):
        peers = universe.filter_constituents(sector=sector, path=path)
        asean = asean_for_sector(sector, path=path)
        oecd = oecd_for_sector(sector)
        out.append({
            "sector": sector,
            "n": len(peers),
            "asean_avg": asean.get("average"),
            "asean_metric": asean.get("metric"),
            "oecd_isic": oecd.get("isic_label"),
            "oecd_intensity": oecd.get("intensity"),
            "oecd_rank": oecd.get("rank"),
            "oecd_of": oecd.get("of"),
            "oecd_percentile": oecd.get("percentile"),
            "oecd_via": oecd.get("via"),
            "matched": bool(oecd.get("available")),
        })
    out.sort(key=lambda r: (r["asean_avg"] is None, -(r["asean_avg"] or 0)))
    return out


def _own_score(company, path, higher_better=None):
    """(value, source) for the company's own score, or (None, reason).

    Four places can hold it, tried in order: the constituent field, the computed 0-100 breakdown
    a live-built profile carries, a lookup of the constituent this profile was built from, and —
    for an UPLOAD, where ``coerce_company_data`` keeps only contract fields and the number
    survives nowhere else — ``layer_a.esg_score_static``.

    That last one is read only when the caller can confirm the scale runs the same way. A static
    rating holds whatever the incumbent published, and a Sustainalytics-style risk score runs the
    other way: lower is better. Subtracting a peer average from it would produce a confident,
    plausible, backwards answer. The app already works the direction out when it builds the
    snapshot (``score_higher_better``), so that verdict is passed in rather than guessed here;
    without it, the company reports unknown.
    """
    if not company:
        return None, "no company payload"
    direct = metrics.num(company.get("esg_score"))
    if direct is not None:
        return direct, "0–100 ESG score"
    for key in ("esg_breakdown", "_esg_breakdown"):
        bd = company.get(key)
        if isinstance(bd, dict) and metrics.num(bd.get("overall")) is not None:
            return metrics.num(bd["overall"]), "computed 0–100 ESG breakdown"
    ticker = company.get("_constituent_ticker") or company.get("ticker")
    if ticker:
        c = universe.get(ticker, path)
        if c and metrics.num(c.get("esg_score")) is not None:
            return metrics.num(c["esg_score"]), "0–100 ESG score from the universe record"
    static = metrics.num((company.get("layer_a") or {}).get("esg_score_static"))
    if static is not None:
        if higher_better:
            return static, "uploaded static score"
        return None, ("the only figure on this company is an incumbent static rating whose "
                      "direction is not known to run the same way as the peer average, so it is "
                      "not compared")
    return None, "no score on the peer scale for this company"


def compare_company(company, path=None, demo=False, higher_better=None):
    """One company against both benchmarks.

    `company` is a universe constituent or a Contract B payload — anything carrying `sector`, and
    optionally `esg_score`. This is what an uploaded file lands in: the upload has a sector, so it
    gets the same two benchmarks as a name we already track.
    """
    sector = (company or {}).get("sector") or ""
    path = path or universe.active_file(demo)
    asean = asean_for_sector(sector, path=path)
    oecd = oecd_for_sector(sector)

    own, own_source = _own_score(company, path, higher_better)

    gap = None
    verdict = ""
    note = ""
    if own is None:
        note = own_source
    elif not asean.get("available"):
        note = asean.get("reason", "")
    elif asean.get("metric_kind") != "static":
        # Both sides are 0-100 and higher-is-better, which is exactly why this needs saying: they
        # are still not the same measurement. The real ASEAN set carries no static scores, so its
        # average is an ESG-LEADERSHIP index derived from the ratings each name's evidence cites.
        # Subtracting a company's own static score from that would look like a peer gap and mean
        # nothing. Both numbers are shown; the difference is not.
        note = (f"Not differenced: this company's figure is a {own_source}, while the peer "
                f"average for this industry is a {asean['metric']}. Both run 0–100 with "
                f"higher being better, but they measure different things, so the difference "
                f"between them would not mean anything.")
    else:
        gap = round(own - asean["average"], 1)
        # Deliberately a comparison, not a recommendation — we never grade a company outright.
        if gap > 2:
            verdict = f"Ahead of its ASEAN peers by {gap:+.1f} points."
        elif gap < -2:
            verdict = f"Behind its ASEAN peers by {gap:+.1f} points."
        else:
            verdict = f"In line with its ASEAN peers ({gap:+.1f})."

    return {
        "company": (company or {}).get("company"),
        "sector": sector,
        "own_score": own,
        "own_score_source": own_source if own is not None else "",
        "own_score_note": note,
        "asean": asean,
        "oecd": oecd,
        "gap_vs_asean": gap,
        "verdict": verdict,
        "disclaimer": "A peer comparison and an industry footprint — not a rating, and never "
                      "investment advice.",
    }


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Print the industry benchmark table.")
    ap.add_argument("--demo", action="store_true", help="use the fictional demo universe")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sector", help="show one sector in full instead of the table")
    a = ap.parse_args()

    if a.sector:
        payload = {"oecd": oecd_for_sector(a.sector),
                   "asean": asean_for_sector(a.sector, demo=a.demo)}
        print(_json.dumps(payload, indent=2))
    else:
        table = industry_table(demo=a.demo)
        if a.json:
            print(_json.dumps(table, indent=2))
        else:
            book = load_oecd()
            print(f"OECD benchmark: {book['meta'].get('note', '')}")
            print(f"  {book['meta'].get('basis', '')[:100]}\n")
            print(f"{'industry':<52}{'n':>4}{'ASEAN avg':>11}{'OECD t/US$m':>13}  ISIC")
            for r in table:
                av = f"{r['asean_avg']:.1f}" if r["asean_avg"] is not None else "—"
                oi = f"{r['oecd_intensity']:,.1f}" if r["oecd_intensity"] is not None else "—"
                print(f"{r['sector'][:50]:<52}{r['n']:>4}{av:>11}{oi:>13}  "
                      f"{r['oecd_isic'] or 'unmatched'}")
