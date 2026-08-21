"""
refresh_eurostat_benchmark.py — the industry bar, live from Eurostat, keyless.
==============================================================================

`data/oecd_sector_benchmark.csv` says where each basket industry's transition bar sits:
greenhouse-gas intensity in **grams CO2e per euro of gross value added**. This script proves
that file against the source, and can rewrite it.

WHY THIS EXISTS
---------------
The benchmark layer dies on one question — *"which dataset, exactly?"* — and a CSV somebody
mailed you is not an answer. Jayden found the answer: Eurostat's dissemination API serves the
exact series, free and without a key, so a judge can reproduce any number on our slide from
their own laptop in one HTTP GET. That is a far stronger claim than a citation.

    https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_ac_aeint_r2
        ?format=JSON&geo=EU27_2020&airpol=GHG&nace_r2=K&na_item=B1G&unit=G_EUR_CP&time=2023

Dataset `env_ac_aeint_r2` — "Air emissions intensities by NACE Rev. 2 activity". Pin all four
of `airpol=GHG`, `na_item=B1G` (value added, gross), `unit=G_EUR_CP` (grams per euro, current
prices) and `time`, or the response carries several series at once and the caller picks the
wrong one by accident. Verified 2026-08-21: banks (K), EU-27, 2023 = **7.89 g/EUR**, which is
what the CSV already said.

WHAT IT IS NOT
--------------
Not the OECD. The file is named `oecd_sector_benchmark.csv` because CGSI's pack named it that,
but the numbers are **Eurostat, EU-27**, and every surface that shows one says "OECD-Europe
(EU-27) benchmark" and cites the dataset. Nine rows fall back to Germany because EU-27 is not
published at that NACE level; those carry `fallback_flag` and must stay flagged on screen.

Not a company measurement either. This is the INDUSTRY's bar. We do not hold per-company GHG
intensity for the basket, so nothing here is ever differenced against a company's own number —
it sizes the transition gap the sector faces, and that is all it is allowed to say.

    python -m scripts.refresh_eurostat_benchmark             # verify the CSV against the API
    python -m scripts.refresh_eurostat_benchmark --write     # refresh values in place
    python -m scripts.refresh_eurostat_benchmark --year 2024 # a different reference year

Best-effort by contract (rule 1): no network means "could not verify", never a crash, and the
committed CSV keeps serving the app.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402  (path set above so this runs from scripts/)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "oecd_sector_benchmark.csv")
ENDPOINT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
            "env_ac_aeint_r2")
DATASET = "env_ac_aeint_r2"
#: Eurostat's own geo codes. The CSV writes them in human form.
GEO = {"EU-27": "EU27_2020", "DE (Germany)": "DE"}
#: Anything under this absolute difference is the same number to the two decimals we publish.
TOLERANCE = 0.005


def fetch(nace, geo_code, year):
    """One (industry, geography, year) -> intensity in g CO2e per EUR of gross value added.

    Returns `(value, note)`; `value` is None when the series is absent or unreachable, and the
    note says which, because "Eurostat does not publish this" and "your wifi is down" must
    never look the same to the caller."""
    url = ("%s?format=JSON&airpol=GHG&na_item=B1G&unit=G_EUR_CP&geo=%s&nace_r2=%s&time=%s"
           % (ENDPOINT, geo_code, nace, year))
    try:
        raw = core.http_get(url)
    except Exception as exc:                                   # noqa: BLE001 — best-effort
        return None, "unreachable (%s)" % type(exc).__name__
    if not raw:
        return None, "unreachable (empty response)"
    try:
        payload = json.loads(raw if isinstance(raw, str) else raw)
    except (ValueError, TypeError):
        return None, "unparseable response"

    values = payload.get("value") or {}
    if not values:
        return None, "not published for this NACE level"
    # Every dimension above is pinned to a single category, so a well-formed response holds
    # exactly one cell. More than one means the query lost a filter — refuse to guess which.
    if len(values) != 1:
        return None, "ambiguous response (%d cells — a filter was dropped)" % len(values)
    return float(next(iter(values.values()))), ""


def read_csv():
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or ())


def main(argv):
    write = "--write" in argv
    year = "2023"
    if "--year" in argv:
        year = argv[argv.index("--year") + 1]

    rows, fieldnames = read_csv()
    print("%s · %s · GHG per EUR gross value added · reference year %s"
          % (DATASET, "Eurostat dissemination API", year))
    print("%-30s %-6s %-12s %10s %10s   %s"
          % ("basket industry", "NACE", "geo", "in file", "live", "verdict"))

    checked = matched = 0
    for row in rows:
        nace = (row.get("nace_rev2_code") or "").strip()
        geo_label = (row.get("reference_geo") or "").strip()
        geo_code = GEO.get(geo_label)
        stated = (row.get("ghg_intensity_g_co2e_per_eur_gva") or "").strip()
        if not nace or not geo_code:
            print("%-30s %-6s %-12s %10s %10s   skipped (no NACE/geo)"
                  % (row.get("basket_industry", "")[:30], nace, geo_label, stated, "-"))
            continue

        live, note = fetch(nace, geo_code, year)
        checked += 1
        if live is None:
            verdict = "COULD NOT VERIFY — %s" % note
        else:
            same = stated and abs(float(stated) - live) < TOLERANCE
            matched += bool(same)
            verdict = "match" if same else "DIFFERS"
            if write and not same:
                row["ghg_intensity_g_co2e_per_eur_gva"] = "%.2f" % live
                row["reference_year"] = year
        print("%-30s %-6s %-12s %10s %10s   %s"
              % (row.get("basket_industry", "")[:30], nace, geo_label, stated,
                 "%.2f" % live if live is not None else "-", verdict))

    print("\n%d/%d rows reproduce from the live API." % (matched, checked))
    if write:
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print("wrote %s" % os.path.relpath(CSV_PATH, BASE_DIR))
    elif matched < checked:
        print("Run with --write to refresh the differing rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
