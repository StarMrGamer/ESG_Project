"""Build data/oecd_industry_benchmark.csv — real OECD greenhouse-gas intensity by industry.

Developer tool, not a runtime path. The app reads the CSV this writes; it never fetches OECD
during a request, because the unfiltered emissions extract is tens of megabytes and a demo
cannot wait on it. Re-run this when you want a fresher snapshot; the CSV records the exact
query URLs and the retrieval date so every number on screen can be traced back.

Two real series, both from the OECD's public SDMX endpoint, both for the ``OECD`` aggregate:

  emissions   OECD.SDD.NAD.SEEA,DSD_AEA@DF_AEA        Air Emissions Accounts, GHG, tonnes CO2e
  value added OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1_OUTPUT  B1G gross value added, USD

Intensity is tonnes CO2e per million USD of gross value added — the ratio is what makes the
industries comparable. A raw emissions total would just rank industries by size, which says
nothing about whether one is good or bad at what it does.

The two datasets do not share an activity breakdown: emissions are reported per ISIC section
(A, B, C, D, …) and value added only for aggregates (BTE = B+C+D+E, GTI = G+H+I, …). So the
emissions side is summed UP into the value-added side's groups. That aggregation is the only
arithmetic here; nothing is estimated, interpolated or filled in. An industry missing either
half is dropped, not guessed.

Usage:
    python -m scripts.build_oecd_benchmark            # latest year with both series
    python -m scripts.build_oecd_benchmark --year 2021
"""
import argparse
import csv
import io
import os
import sys
import datetime as _dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402

SDMX = "https://sdmx.oecd.org/public/rest/data"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "oecd_industry_benchmark.csv")

# The value-added activity groups, and which ISIC sections of the emissions account roll into
# each. `BTE` and `C` overlap by construction — OECD publishes manufacturing both inside
# "industry except construction" and on its own, and both are useful, so both are kept.
GROUPS = {
    "A":   ("Agriculture, forestry and fishing", ["A"]),
    "BTE": ("Industry (except construction)", ["B", "C", "D", "E"]),
    "C":   ("Manufacturing", ["C"]),
    "F":   ("Construction", ["F"]),
    "GTI": ("Wholesale, retail, transport, accommodation and food", ["G", "H", "I"]),
    "J":   ("Information and communication", ["J"]),
    "K":   ("Financial and insurance activities", ["K"]),
    "L":   ("Real estate activities", ["L"]),
    "M_N": ("Professional, scientific, technical and support services", ["M", "N"]),
    "OTQ": ("Public administration, defence, education, health", ["O", "P", "Q"]),
    "RTU": ("Arts, entertainment, other services", ["R", "S", "T", "U"]),
}

def _key(width, **at):
    """An SDMX key built by 1-based dimension position.

    Hand-written dot strings are how you end up asking for a transaction in the counterpart-sector
    slot and getting a 404 that looks like "no such data" rather than "wrong question".
    """
    parts = [""] * width
    for pos, value in at.items():
        parts[int(pos) - 1] = value
    return ".".join(parts)


# DSD_AEA dimensions, in order:
#   1 REF_AREA · 2 FREQ · 3 MEASURE · 4 UNIT_MEASURE · 5 ADJUSTMENT · 6 ACTIVITY
#   7 POLLUTANT · 8 ACTIVITY_SCOPE · 9 METHODOLOGY · 10 SOURCE
EMISSIONS_URL = (SDMX + "/OECD.SDD.NAD.SEEA,DSD_AEA@DF_AEA,1.0/"
                 + _key(10, **{"2": "A", "3": "EMISSIONS", "4": "T_CO2E", "7": "GHG"})
                 + "?startPeriod=2018&format=csvfilewithlabels")

# DSD_NAMAIN10 dimensions, in order:
#   1 FREQ · 2 REF_AREA · 3 SECTOR · 4 COUNTERPART_SECTOR · 5 TRANSACTION · 6 INSTR_ASSET
#   7 ACTIVITY · 8 EXPENDITURE · 9 UNIT_MEASURE · 10 PRICE_BASE · 11 TRANSFORMATION
#   12 TABLE_IDENTIFIER
GVA_URL = (SDMX + "/OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1_OUTPUT,2.0/"
           + _key(12, **{"1": "A", "5": "B1G", "9": "USD_EXC", "10": "V"})
           + "?startPeriod=2018&format=csvfilewithlabels")

# Aggregate codes that are not a country and must never be summed with the members.
NOT_A_COUNTRY = {"OECD", "EU27_2020", "EU28", "EA19", "EA20", "G7", "G20", "WLD", "_T"}


def _rows(url, label):
    print(f"  fetching {label} …", flush=True)
    text = core.http_get(url)
    if not text:
        raise SystemExit(f"no data returned for {label}")
    rows = list(csv.DictReader(io.StringIO(text)))
    print(f"    {len(text):,} chars · {len(rows):,} rows")
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _scaled(row):
    """OBS_VALUE in base units.

    SDMX reports UNIT_MULT separately from the value: emissions come through with no multiplier
    (plain tonnes) while value added arrives with UNIT_MULT=6, i.e. millions. Reading the column
    instead of assuming is the difference between an intensity and an intensity times a million —
    and the wrong one still ranks the industries correctly, so it would not have looked wrong.
    """
    val = _num(row.get("OBS_VALUE"))
    if val is None:
        return None
    mult = _num(row.get("UNIT_MULT")) or 0
    return val * (10 ** int(mult))


def collect(year=None):
    """Return (year, countries, emissions_by_group, value_added_by_group).

    The OECD aggregate carries emissions per industry but value added only as one economy-wide
    total, so a ratio cannot be formed from it. The per-country series carries both at the
    industry level, so the aggregate is rebuilt here from the members — and only from members
    that report BOTH series for BOTH the year and every industry in question. A country that is
    missing one half would otherwise deflate that industry's numerator or denominator and quietly
    bias the intensity.
    """
    em = _rows(EMISSIONS_URL, "emissions by country (AEA, GHG)")
    gv = _rows(GVA_URL, "gross value added by country (NAMAIN10 B1G)")

    def index(rows, want):
        """{year: {country: {activity: value}}}"""
        out = {}
        for r in rows:
            area, act = r.get("REF_AREA"), r.get("ACTIVITY")
            per, val = r.get("TIME_PERIOD"), _scaled(r)
            if area in NOT_A_COUNTRY or act not in want or not per or val is None:
                continue
            out.setdefault(per, {}).setdefault(area, {})[act] = val
        return out

    sections = {sec for _, secs in GROUPS.values() for sec in secs}
    em_y = index(em, sections)
    gv_y = index(gv, set(GROUPS))

    def usable(y):
        """Countries reporting every emissions section and every value-added group in year y."""
        e, g = em_y.get(y, {}), gv_y.get(y, {})
        return sorted(c for c in set(e) & set(g)
                      if sections <= set(e[c]) and set(GROUPS) <= set(g[c]))

    years = [str(year)] if year else sorted(set(em_y) & set(gv_y), reverse=True)
    for y in years:
        countries = usable(y)
        if len(countries) >= 8:
            print(f"  year {y} · {len(countries)} countries with both series in full")
            e_tot = {sec: sum(em_y[y][c][sec] for c in countries) for sec in sections}
            g_tot = {grp: sum(gv_y[y][c][grp] for c in countries) for grp in GROUPS}
            return y, countries, e_tot, g_tot
        print(f"  year {y} · only {len(countries)} complete countries — skipping")
    raise SystemExit("no year has enough countries reporting both series in full")


def build(year=None):
    y, countries, em, gv = collect(year)
    recs = []
    for code, (label, sections) in GROUPS.items():
        if code not in gv or not all(s in em for s in sections):
            missing = [s for s in sections if s not in em] or ["value added"]
            print(f"  skip {code:<4} — no {', '.join(missing)}")
            continue
        ghg = sum(em[s] for s in sections)
        gva = gv[code]
        if gva <= 0:
            print(f"  skip {code:<4} — non-positive value added")
            continue
        recs.append({
            "isic_code": code, "isic_label": label,
            "isic_sections": "+".join(sections),
            "year": y,
            "ghg_t_co2e": round(ghg, 3),
            "gva_usd": round(gva, 3),
            # tonnes CO2e per million USD of gross value added
            "intensity_t_per_musd": round(ghg / (gva / 1e6), 4),
        })

    recs.sort(key=lambda r: r["intensity_t_per_musd"])
    n = len(recs)
    for i, r in enumerate(recs):
        r["rank_cleanest"] = i + 1
        # Percentile of CLEANLINESS: 1.0 = the least emissions-intense industry in the set.
        r["cleanliness_percentile"] = round(1 - (i / (n - 1)) if n > 1 else 0.5, 4)

    retrieved = _dt.date.today().isoformat()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        f.write(f"# OECD greenhouse-gas intensity by industry, {y}.\n")
        f.write(f"# basis: {len(countries)} OECD members reporting both series in full — "
                f"{','.join(countries)}\n")
        f.write("# intensity_t_per_musd = tonnes CO2e per million USD of gross value added.\n")
        f.write("# cleanliness_percentile: 1.0 = least intense industry in this set, 0.0 = most.\n")
        f.write(f"# emissions:   {EMISSIONS_URL}\n")
        f.write(f"# value added: {GVA_URL}\n")
        f.write(f"# retrieved:   {retrieved}\n")
        w = csv.DictWriter(f, fieldnames=[
            "isic_code", "isic_label", "isic_sections", "year", "ghg_t_co2e", "gva_usd",
            "intensity_t_per_musd", "rank_cleanest", "cleanliness_percentile"])
        w.writeheader()
        w.writerows(recs)

    print(f"\nwrote {OUT} — {n} industries, year {y}, {len(countries)} countries")
    for r in recs:
        print(f"  {r['rank_cleanest']:>2}. {r['isic_label'][:52]:<54}"
              f"{r['intensity_t_per_musd']:>12,.1f} t/USDm")
    return recs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, help="pin a year instead of taking the latest usable one")
    build(ap.parse_args().year)
