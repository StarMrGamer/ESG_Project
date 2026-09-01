"""The BIG ASEAN index members -> data/asean_indexes.json — a SECOND universe, beside CGSI's 52.

WHY THIS IS A SEPARATE FILE AND NOT MORE ROWS IN THE FIRST ONE
---------------------------------------------------------------
`data/asean_universe.json` is CGSI's verified 52, and those names mean something specific: index
constituents that stayed in throughout AND posted a positive 2019-2023 ESG-score CAGR. The whole
"55.1% vs 6.4%" claim describes THAT selection. Index members are simply the biggest listings —
selected for size and liquidity, with no ESG screen at all.

Merging the two would have silently changed what the universe IS while every surface went on
describing it as "52 ASEAN companies with consistent ESG improvement", and would have re-frozen
`run_id`, N/M/K, the golden digest and the Sepolia anchor along the way. So this is its own file,
scored as its own run, switchable in the header — and CGSI's basket is untouched.

WHAT THESE COMPANIES DO NOT HAVE, AND WHY THAT IS SAID RATHER THAN PATCHED
--------------------------------------------------------------------------
**No incumbent ESG rating.** CGSI supplied a 2023 score for their 52; nobody has supplied one for
these. `engine._baseline_score` therefore returns `UNAVAILABLE`, and `engine.label_for` gives
them the `unrated` label rather than a quadrant.

That label was added FOR this universe and it matters. Without it, a company with no baseline
falls back to a percentile of 0.5 — the median — and `disagreement` becomes
`momentum_percentile - 0.5`. A high-momentum name would then clear theta and be labelled a
**Hidden Winner**: "our evidence is materially more positive than the incumbent rating", against
a rating that does not exist. A low-momentum one would be labelled Consensus, asserting agreement
with nobody. Both are claims about a number we never had.

The obvious fix — fetch LSEG's real published score for each — is **deliberately not taken**.
`lseg.py` can do it, but LSEG's terms allow attributed, on-demand, one-company-at-a-time lookups
and forbid systematic reproduction, which is why `data/` never receives an LSEG scrape. A licence
is not a technical obstacle to route around.

**No ESG evidence, at first.** Every name starts at zero signals and plots hollow on the zero
line, counted and stated. `harvest.py` gathers evidence for them exactly as it did for the
basket's thin names — same four search angles, same five guards, same deterministic scoring.

SOURCING
--------
Constituent lists come from Wikipedia's index pages, fetched through `core.http_get` like every
other request here (rule 1). Wikipedia is a weaker source than a filing and is named as one on
every row (`membership_source`): an index's membership is a matter of public record and is the
kind of fact it is reliable for, but nothing here treats it as evidence ABOUT a company. The
ESG side of every one of these rows still has to be earned by the harvest.

Tickers are normalised to this repo's `EXCHANGE:CODE` shape. A name that duplicates one already
in CGSI's basket keeps CGSI's ticker so the two universes stay joinable.
"""
import datetime
import html as _html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core                                                            # noqa: E402
import universe                                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "asean_indexes.json")

#: One entry per index. `pick` chooses the constituent table by its header, because these pages
#: also carry year-by-year performance tables with more rows than the constituent list.
INDEXES = [
    {"key": "STI", "name": "Straits Times Index", "country": "Singapore", "exchange": "SGX",
     "url": "https://en.wikipedia.org/wiki/Straits_Times_Index",
     "header": ("stock symbol", "company"), "ticker_col": 0, "name_col": 1, "sector_col": None},
    {"key": "KLCI", "name": "FTSE Bursa Malaysia KLCI", "country": "Malaysia", "exchange": "KLSE",
     "url": "https://en.wikipedia.org/wiki/FTSE_Bursa_Malaysia_KLCI",
     "header": ("constituent name", "stock code"), "ticker_col": 1, "name_col": 0, "sector_col": 2},
    {"key": "SET50", "name": "SET50", "country": "Thailand", "exchange": "SET",
     "url": "https://en.wikipedia.org/wiki/SET50_Index_and_SET100_Index",
     "header": ("symbol", "securities name"), "ticker_col": 0, "name_col": 1, "sector_col": 2},
    {"key": "LQ45", "name": "LQ45", "country": "Indonesia", "exchange": "IDX",
     "url": "https://en.wikipedia.org/wiki/LQ45",
     "header": ("ticker", "company"), "ticker_col": 0, "name_col": 1, "sector_col": None},
    {"key": "PSEi", "name": "PSE Composite Index", "country": "Philippines", "exchange": "PSE",
     "url": "https://en.wikipedia.org/wiki/PSE_Composite_Index",
     "header": ("company", "ticker symbol"), "ticker_col": 1, "name_col": 0, "sector_col": None},
]

#: Trailing corporate boilerplate stripped from a display name. The legal form is not the company.
_SUFFIX_RE = re.compile(
    r"\s*(tbk\.?|berhad|bhd\.?|public company limited|pcl|plc|ltd\.?|limited|"
    r"corporation|corp\.?|incorporated|inc\.?|company|co\.?)\s*$", re.I)


def _cells(row):
    out = []
    for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S):
        txt = _html.unescape(re.sub(r"<[^>]+>", " ", c))
        # Wikipedia footnote markers ("[ 11 ]") ride along with the text and are not part of it.
        txt = re.sub(r"\[\s*\d+\s*\]", " ", txt)
        out.append(" ".join(txt.split()))
    return out


def _tables(raw):
    return re.findall(r"<table[^>]*wikitable.*?</table>", raw, re.S)


def _pick_table(raw, header):
    """The table whose header row contains every word in `header`. None when no table matches.

    Matching on the header rather than on position or row count is what stops a page edit
    silently handing us the year-by-year performance table instead of the constituents.
    """
    for table in _tables(raw):
        rows = re.findall(r"<tr.*?</tr>", table, re.S)
        if len(rows) < 10:
            continue
        head = " ".join(_cells(rows[0])).lower()
        if all(word in head for word in header):
            return rows[1:]
    return None


def clean_name(text):
    name = " ".join((text or "").split())
    prev = None
    while prev != name:                      # "... Tbk." then "... Corporation"
        prev = name
        name = _SUFFIX_RE.sub("", name).strip(" .,")
    return name or text


def clean_ticker(text, exchange):
    """`SGX : A17U`, `5326` or `ADVANC` -> `SGX:A17U`. '' when there is no usable code."""
    txt = " ".join((text or "").split())
    if ":" in txt:
        code = txt.split(":", 1)[1]
    else:
        code = txt
    code = re.sub(r"[^A-Za-z0-9.\-]", "", code).upper()
    return f"{exchange}:{code}" if code else ""


def fetch_index(spec):
    """`[{company, ticker, country, exchange, sector, index}]` for one index. [] on any failure."""
    try:
        raw = core.http_get(spec["url"], timeout=20)
    except Exception as e:                  # noqa: BLE001 - best-effort by contract (rule 1)
        print(f"  {spec['key']:6} FETCH FAILED — {type(e).__name__}: {e}")
        return []
    rows = _pick_table(raw, spec["header"])
    if not rows:
        print(f"  {spec['key']:6} no table matched header {spec['header']}")
        return []

    out, seen = [], set()
    for row in rows:
        cells = _cells(row)
        need = max(c for c in (spec["ticker_col"], spec["name_col"],
                               spec["sector_col"] or 0) if c is not None)
        if len(cells) <= need:
            continue
        ticker = clean_ticker(cells[spec["ticker_col"]], spec["exchange"])
        name = clean_name(cells[spec["name_col"]])
        if not ticker or not name or ticker in seen:
            continue
        seen.add(ticker)
        sector = (cells[spec["sector_col"]].strip()
                  if spec["sector_col"] is not None and len(cells) > spec["sector_col"] else "")
        out.append({
            "company": name,
            "ticker": ticker,
            "exchange": spec["exchange"],
            "country": spec["country"],
            # An unstated sector is "unknown", never guessed from the name. The industry
            # benchmark joins on this label and a wrong join is worse than an absent one.
            "sector": sector or "unknown",
            "industry": sector or "unknown",
            "index": spec["key"],
        })
    print(f"  {spec['key']:6} {len(out):>3} constituents  ({spec['name']})")
    return out


def build():
    today = datetime.date.today().isoformat()
    # CGSI's tickers win on a collision, so a company in both universes keeps ONE identity.
    cgsi = {c["ticker"]: c for c in universe.constituents(universe.UNIVERSE_FILE)}
    by_name = {c["company"].lower(): c["ticker"] for c in cgsi.values()}

    rows, overlap = [], 0
    for spec in INDEXES:
        for row in fetch_index(spec):
            hit = cgsi.get(row["ticker"]) or cgsi.get(by_name.get(row["company"].lower(), ""))
            if hit:
                overlap += 1
                row["ticker"] = hit["ticker"]
                row["also_in_cgsi"] = True
            else:
                row["also_in_cgsi"] = False
            row.update({
                "as_of": today,
                # NO ESG score and NO evidence basis. Stated by omission AND in words: the engine
                # reads this as an UNAVAILABLE baseline and labels the company `unrated`.
                "baseline_note": ("No incumbent ESG rating on file for this company. It is an "
                                  "index member, selected for size and liquidity, not an ESG "
                                  "screen — so there is nothing here to disagree with."),
                "membership_source": "Wikipedia index constituent list",
                "membership_source_url": next(s["url"] for s in INDEXES
                                              if s["key"] == row["index"]),
                "confidence": "low",
            })
            rows.append(row)

    # Same ticker in two indexes (rare, but a dual listing would do it) collapses to one row.
    unique = {}
    for r in rows:
        unique.setdefault(r["ticker"], r)
    rows = sorted(unique.values(), key=lambda r: (r["country"], r["company"]))

    payload = {
        "note": ("THE BIG ASEAN INDEX MEMBERS — a SECOND universe, beside CGSI's verified 52 and "
                 "deliberately not merged with it. These are the largest listings in five ASEAN "
                 "markets, selected for size and liquidity with NO ESG screen. None carries an "
                 "incumbent ESG rating, so every one is labelled `unrated` until one is supplied "
                 "— the engine will not manufacture a disagreement with a rating that does not "
                 "exist. Evidence is gathered by `harvest.py`, exactly as for the basket."),
        "selection": ("Constituents of " + ", ".join(s["name"] for s in INDEXES)
                      + ". Membership from Wikipedia's index pages, cited per row."),
        "benchmark": "none — this is a size-and-liquidity universe, not a strategy",
        "benchmark_stats": {},
        "source_file": "scripts/build_index_universe.py",
        "as_of": today,
        "is_provisional": True,
        "countries": sorted({r["country"] for r in rows}),
        "indexes": {s["key"]: {"name": s["name"], "country": s["country"], "url": s["url"]}
                    for s in INDEXES},
        "overlap_with_cgsi": overlap,
        "constituents": rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    print(f"\n{len(rows)} constituents across {len(INDEXES)} indexes "
          f"({overlap} already in CGSI's 52) -> {OUT}")
    return payload


if __name__ == "__main__":
    build()
