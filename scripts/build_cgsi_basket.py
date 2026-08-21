"""
build_cgsi_basket.py — turn CGSI's verified 52 into the two files the app actually reads.
==========================================================================================

CGSI delivered `CGSI_52_verified.csv` on 2026-08-20: the REAL foundation basket, every row
carrying a green-bond classification reached through the ICMA-first process, a profitability
flag, two sources, and the 17 high-conviction picks flagged. It replaces the provisional
basket. This script is the swap.

WHAT THE HANDOVER NOTE GOT WRONG (and why this file exists)
-----------------------------------------------------------
`Prototype_Build_Notes.md` §1 says "Same schema, zero code changes." It is not the same
schema. The frozen contract in `company_metadata.py` (which IS the header of
`D/green_bond_verification_template.csv`) has **29** columns; CGSI's file has **23**:

    renamed   company_id -> bbg_code · company_name -> company · external_reviewer -> reviewer
              fy_minus1_net_income -> fy_latest_net_income · access_date -> as_of
    dropped   bond_isin · issue_date · amount_currency · label · icma_structure
              standard_claimed · review_type · sgx_recognised · operating_cf_trend
              traction_flag · traction_evidence · verified_by
    added     lseg_rating · esg_score_2023 · esg_cagr_5y · high_conviction_17
              instruments_note · confidence · market

So the swap needs an adapter, not a copy. Writing one here — rather than loosening the
frozen header — is the whole point of freezing it: the contract holds, and the shape of
someone else's spreadsheet is this script's problem instead of the engine's.

WHAT IT WRITES
--------------
    data/company_metadata.csv      the 29-column frozen shape. `company_metadata.py` already
                                   prefers this path over the mock, so nothing else changes.
    data/asean_universe.json       the basket itself — CGSI's 52 names, replacing our own
                                   public-evidence reconstruction (kept alongside as
                                   `asean_universe_reconstructed.json`, which says in its own
                                   note that it would not reproduce this list).

DETERMINISTIC. No clock, no network, no LLM, no RNG — `as_of` comes from the CSV. Same input
file always produces byte-identical output, which is what lets Gate 1 and the anchor hold.

NOTHING IS INVENTED (rule 2). Every field is either copied from CGSI's row, or derived from
it by a rule stated here:
  * `esg_score` is CGSI's `esg_score_2023`, carried with `esg_as_of: 2023-12-31` — a DATED
    baseline on disk, which is what lets the engine stay pure while using a real number.
  * `events` are dated, sourced facts. Their TEXT is CGSI's own prose (`instruments_note`,
    `notes`) passed through verbatim, plus two statements derived strictly from boolean
    columns. They are not written to match the signal taxonomy — whatever matches, matches,
    and a company with nothing to say scores no signals.
  * `esg_cagr_5y` is carried for DISPLAY ONLY and is deliberately NOT emitted as a signal.
    It is derived from the rating's own history, so scoring it as our momentum would make us
    agree with the incumbent by construction and quietly destroy the disagreement thesis.

    python -m scripts.build_cgsi_basket            # write both files
    python -m scripts.build_cgsi_basket --check    # verify on-disk output is current
"""

import csv
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SOURCE_CSV = os.path.join(BASE_DIR, "D", "ESG_Radar_Final_Pack", "01_DATA",
                          "CGSI_52_verified.csv")
OUT_METADATA = os.path.join(DATA_DIR, "company_metadata.csv")
OUT_UNIVERSE = os.path.join(DATA_DIR, "asean_universe.json")
PRIOR_UNIVERSE = os.path.join(DATA_DIR, "asean_universe_reconstructed.json")

#: The frozen 29-column contract, mirrored from `company_metadata.HEADER`. Imported rather
#: than retyped would be tidier, but this script must run standalone from `scripts/`.
HEADER = (
    "company_id", "company_name", "exchange_ticker", "industry", "is_provisional",
    "green_bond_issuer", "classification", "bond_isin", "issue_date", "amount_currency",
    "label", "icma_structure", "standard_claimed", "external_reviewer", "review_type",
    "framework_url", "allocation_report", "sgx_recognised", "profitability_flag",
    "fy_minus1_net_income", "fy_minus2_net_income", "operating_cf_trend", "traction_flag",
    "traction_evidence", "source_url_1", "source_url_2", "verified_by", "access_date", "notes",
)

#: Bloomberg market suffix -> the exchange prefix this repo has always used for company ids.
#: CGSI ships Bloomberg codes ("OCBC SP"); every id below is derived from one, so any ticker
#: on screen can be traced straight back to a row in their file.
MARKETS = {
    "SP": ("SGX", "Singapore"),
    "MK": ("KLSE", "Malaysia"),
    "TB": ("SET", "Thailand"),
    "IJ": ("IDX", "Indonesia"),
    "PM": ("PSE", "Philippines"),
}

#: A `reviewer` cell that means "no external review", in CGSI's own words. Anything else is
#: treated as a named second-party opinion provider. Compared against the text BEFORE any
#: parenthetical, because Keppel's cell reads "none (SL framework reviewed; not green)" — a
#: naive membership test reads that as a reviewer literally named "none" and then states, on
#: screen, that the framework "carries a second-party opinion from none."
_NO_REVIEWER = ("", "none", "n/a", "na", "-", "not applicable", "no external review")


def _reviewer_name(raw):
    """The named second-party opinion provider, or "" when the cell means "nobody"."""
    head = (raw or "").split("(")[0].strip()
    return "" if head.lower() in _NO_REVIEWER else head

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_MON_RE = "|".join(m[:3] for m in _MONTHS)
#: "25 Feb 2025" / "Feb 2025" / "Jun 2023". Month-only dates resolve to the first of the
#: month, which is the earliest reading consistent with what the text states.
_DATE_FULL = re.compile(r"\b(\d{1,2})\s+(%s)\w*\s+(20\d{2})\b" % _MON_RE, re.I)
_DATE_MON = re.compile(r"\b(%s)\w*\s+(20\d{2})\b" % _MON_RE, re.I)


def _iso(day, month_abbr, year):
    month = next(i for i, m in enumerate(_MONTHS, 1) if m.startswith(month_abbr.lower()))
    return "%04d-%02d-%02d" % (int(year), month, int(day))


def date_in(text, fallback):
    """The earliest date the TEXT itself states, else `fallback` (CGSI's verification date).

    Never guesses a more precise date than the words support: a bare "Jun 2023" becomes
    2023-06-01, and text with no date at all keeps the date we know is true — the day the row
    was verified."""
    full = _DATE_FULL.search(text or "")
    if full:
        return _iso(full.group(1), full.group(2), full.group(3))
    mon = _DATE_MON.search(text or "")
    if mon:
        return _iso(1, mon.group(1), mon.group(2))
    return fallback


def company_id(bbg_code):
    """`"OCBC SP"` -> `("SGX:OCBC", "SGX", "Singapore")`."""
    root, _, suffix = (bbg_code or "").strip().rpartition(" ")
    exchange, country = MARKETS.get(suffix.upper(), ("XXX", "unknown"))
    return "%s:%s" % (exchange, root.replace(" ", "")), exchange, country


def is_delisted(row):
    """True when CGSI's own `notes` records a delisting. The word is theirs, not ours —
    MAHB (25 Feb 2025) and INTUCH (3 Apr 2025) are the two, and finding them in a basket
    that is meant to be current is a result, not an error."""
    return "delisted" in (row.get("notes") or "").lower()


def _events(row, cid, as_of):
    """Dated, sourced facts for one company — the evidence the engine scores.

    Four possible rows, in descending source quality. Text is CGSI's verbatim where CGSI
    wrote prose; the two derived statements restate a boolean column and nothing more."""
    out = []
    url_1 = (row.get("source_url_1") or "").strip()
    url_2 = (row.get("source_url_2") or "").strip()
    framework = (row.get("framework_url") or "").strip()
    reviewer = (row.get("reviewer") or "").strip()
    instruments = (row.get("instruments_note") or "").strip()
    notes = (row.get("notes") or "").strip()

    reviewer_name = _reviewer_name(reviewer)
    if reviewer_name:
        text = ("Sustainable-finance framework carries a second-party opinion from %s."
                % reviewer_name)
        out.append({"text": text, "source_url": framework or url_2 or url_1,
                    "published_at": date_in(instruments, as_of),
                    "source_type": "external_reviewer"})

    if (row.get("allocation_report") or "").strip().upper() == "Y":
        out.append({"text": "Publishes an allocation report against issued proceeds.",
                    "source_url": url_1 or framework,
                    "published_at": date_in(notes, as_of),
                    "source_type": "company_pr"})

    if instruments:
        out.append({"text": instruments, "source_url": framework or url_1,
                    "published_at": date_in(instruments, as_of),
                    "source_type": "company_pr"})

    if notes:
        out.append({"text": notes, "source_url": url_2 or url_1,
                    "published_at": date_in(notes, as_of),
                    "source_type": "dataset"})

    for i, event in enumerate(out):
        event["event_id"] = "%s-cgsi-%d" % (cid, i)
    return out


def _alias_book():
    """`{normalised CGSI name: [alternative names]}` — real alternative names for the same
    company, taken from the public-evidence universe we built while waiting for this list.

    CGSI writes terse legal-ish names ("Bank Central Asia", "OCBC"); our earlier DB wrote the
    forms people actually type, with the common short name in parentheses ("Bank Central Asia
    (BCA)"). Those are genuine alternative names with a source behind them, so carrying them
    across keeps "add BCA" and "show Maybank" working. NOTHING is invented here: a CGSI name
    with no counterpart in the old file simply gets no alias."""
    try:
        with open(PRIOR_UNIVERSE, "r", encoding="utf-8") as fh:
            prior = json.load(fh)
    except (OSError, ValueError):
        return {}
    rows = prior.get("constituents", prior) if isinstance(prior, dict) else prior
    return {_match_key(r.get("company", "")): r.get("company", "") for r in rows
            if r.get("company")}


_GENERIC = {"bhd", "berhad", "plc", "pcl", "ltd", "limited", "inc", "corp", "corporation",
            "group", "holdings", "company", "co", "the", "pt", "tbk", "public"}


def _match_key(name):
    """A comparable key for one company name: significant words only, sorted."""
    body = re.sub(r"\(([^)]*)\)", r" \1 ", (name or "").lower())
    words = [w for w in re.split(r"[^a-z0-9]+", body) if w and w not in _GENERIC]
    return " ".join(sorted(words))


def aliases_for(name, book):
    """Alternative names for one CGSI company: the old DB's name for it (when the two names
    share at least two significant words), plus any parenthetical inside either."""
    out = []
    key = _match_key(name)
    mine = set(key.split())
    for other_key, other_name in book.items():
        theirs = set(other_key.split())
        if other_key == key or len(mine & theirs) >= 2:
            if other_name.lower() != (name or "").lower():
                out.append(other_name)
            out.extend(re.findall(r"\(([^)]+)\)", other_name))
    return sorted({a.strip() for a in out if a.strip()})


def metadata_row(row):
    """CGSI's 23 columns -> the frozen 29. Absent columns are left EMPTY, never guessed:
    `traction_flag` in particular stays blank because CGSI did not run a traction screen,
    and inventing a flag there would drive a tier the data cannot support."""
    cid, _, _ = company_id(row["bbg_code"])
    return {
        "company_id": cid,
        "company_name": row["company"],
        "exchange_ticker": row["bbg_code"],
        "industry": row["industry"],
        "is_provisional": row.get("is_provisional", "FALSE"),
        "green_bond_issuer": row.get("green_bond_issuer", ""),
        "classification": row.get("classification", ""),
        "bond_isin": "",
        "issue_date": "",
        "amount_currency": "",
        "label": "",
        "icma_structure": "",
        "standard_claimed": "",
        "external_reviewer": row.get("reviewer", ""),
        "review_type": "second_party_opinion" if _reviewer_name(row.get("reviewer")) else "",
        "framework_url": row.get("framework_url", ""),
        "allocation_report": row.get("allocation_report", ""),
        "sgx_recognised": "",
        "profitability_flag": row.get("profitability_flag", ""),
        "fy_minus1_net_income": row.get("fy_latest_net_income", ""),
        "fy_minus2_net_income": row.get("fy_prior_net_income", ""),
        "operating_cf_trend": "",
        "traction_flag": "",
        "traction_evidence": "",
        "source_url_1": row.get("source_url_1", ""),
        "source_url_2": row.get("source_url_2", ""),
        "verified_by": "Quill & Candle (ICMA-based process, >=2 sources per row)",
        "access_date": row.get("as_of", ""),
        "notes": row.get("notes", ""),
    }


def constituent(row, alias_book=None):
    """One CGSI row -> one universe constituent."""
    cid, exchange, country = company_id(row["bbg_code"])
    bbg_root = (row["bbg_code"] or "").rsplit(" ", 1)[0].strip()
    as_of = (row.get("as_of") or "").strip()
    score = (row.get("esg_score_2023") or "").strip()
    return {
        "company": row["company"],
        "ticker": cid,
        "bbg_code": row["bbg_code"],
        "exchange": exchange,
        "country": country,
        "sector": row["industry"],
        "industry": row["industry"],
        "esg_score": float(score) if score else None,
        "esg_as_of": "2023-12-31",
        "esg_score_basis": ("CGSI ESG Momentum 2.0 basket score, 2023 vintage (0-100, higher "
                            "is better). Supplied by CGSI, not recomputed here."),
        "esg_cagr_2019_2023": (row.get("esg_cagr_5y") or "").strip(),
        "incumbent_notch": (row.get("lseg_rating") or "").strip(),
        "high_conviction": (row.get("high_conviction_17") or "").strip().upper() == "Y",
        "delisted": is_delisted(row),
        "green_bond_classification": row.get("classification", ""),
        "profitability_flag": row.get("profitability_flag", ""),
        "confidence": (row.get("confidence") or "").strip() or "unknown",
        # Search synonyms, not facts: the Bloomberg root CGSI themselves use, plus the name our
        # earlier public-evidence DB gave the same company. Lets "add BCA" / "show Maybank"
        # keep working against CGSI's terser names.
        "aliases": sorted({a for a in ([bbg_root] + aliases_for(row["company"],
                                                                alias_book or {}))
                           if a and a.lower() != row["company"].lower()}),
        "as_of": as_of,
        "esg_basis": " ".join(p for p in ((row.get("instruments_note") or "").strip(),
                                          (row.get("notes") or "").strip()) if p),
        "source_url": (row.get("source_url_1") or "").strip(),
        "source_url_2": (row.get("source_url_2") or "").strip(),
        "events": _events(row, cid, as_of),
    }


NOTE = (
    "THE REAL BASKET. CGSI's own 52-name ESG Momentum 2.0 foundation basket, delivered "
    "2026-08-20 as `CGSI_52_verified.csv` and adapted here by `scripts/build_cgsi_basket.py`. "
    "Every constituent carries CGSI's 2023 ESG score (0-100, higher is better) as a DATED "
    "on-disk baseline, their 5-year ESG CAGR, their green-bond classification reached through "
    "the ICMA-first process with >=2 sources per row, a profitability flag, and the "
    "high_conviction_17 flag behind the blind agreement test. This REPLACES the public-evidence "
    "reconstruction we built while waiting for the real list, which is kept beside it as "
    "`asean_universe_reconstructed.json` and whose own note says it would not reproduce this "
    "basket -- it does not, and only 22 of these 52 names appear in it. "
    "TWO WARNINGS THAT TRAVEL WITH THIS FILE. (1) `incumbent_notch` is CGSI's `lseg_rating` "
    "column carried through under a neutral name: its values are BB / BBB / B, which is the "
    "MSCI notch scale, NOT LSEG's (A+ to D-), and the scores do not reconcile to LSEG's live "
    "published figures (SGX 62 vs 52, Siam Cement 70 vs 78, PTT 73 vs 78 on a 0-100 basis). "
    "It is displayed as an unattributed incumbent notch and never as LSEG's. `lseg.py` fetches "
    "the genuine LSEG score live and separately. (2) `esg_cagr_2019_2023` is DISPLAY ONLY and "
    "is deliberately not scored: it is derived from the rating's own history, so treating it "
    "as our momentum would make us agree with the incumbent by construction."
)


class SourceMissing(RuntimeError):
    """CGSI's file is not on this machine. `D/` is the team hand-off pack and is deliberately
    git-ignored, so a fresh clone has the BUILT outputs but not the input. That is fine for
    running the app and wrong for rebuilding it, and the difference should be one clear
    sentence rather than a traceback."""


def build():
    if not os.path.exists(SOURCE_CSV):
        raise SourceMissing(
            "Cannot find %s.\n"
            "`D/` is the team hand-off pack and is git-ignored on purpose, so a clone has the\n"
            "built outputs (data/asean_universe.json, data/company_metadata.csv) but not the\n"
            "input they were built from. Copy CGSI_52_verified.csv back into place to rebuild;\n"
            "the app itself needs no rebuild." % os.path.relpath(SOURCE_CSV, BASE_DIR))
    with open(SOURCE_CSV, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: company_id(r["bbg_code"])[0])

    alias_book = _alias_book()
    constituents = [constituent(r, alias_book) for r in rows]
    universe = {
        "note": NOTE,
        "selection": ("CGSI ESG Momentum 2.0 foundation basket -- 52 ASEAN-listed companies "
                      "with consistent ESG improvement 2019-2023 (positive 5-year ESG-score "
                      "CAGR). Supplied by CGSI, verified row-by-row by Quill & Candle."),
        "benchmark": "MSCI ASEAN",
        "benchmark_stats": {
            "basket_return": "55.1%", "benchmark_return": "6.4%",
            "basket_sharpe": "0.57", "benchmark_sharpe": "-0.22",
            "high_conviction_picks": sum(1 for c in constituents if c["high_conviction"]),
            "source": ("CGSI, \"ESG Momentum 2.0\" (2026), indicative -- CGSI's own backtest "
                       "of this exact basket, display only, not recomputed here"),
        },
        "source_file": "D/ESG_Radar_Final_Pack/01_DATA/CGSI_52_verified.csv",
        "as_of": rows[0].get("as_of", ""),
        "is_provisional": False,
        "countries": sorted({c["country"] for c in constituents}),
        "constituents": constituents,
    }

    return universe, [metadata_row(r) for r in rows]


def _write_metadata(metadata):
    with open(OUT_METADATA, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(metadata)


def _write_universe(universe):
    with open(OUT_UNIVERSE, "w", encoding="utf-8") as fh:
        json.dump(universe, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")


def main(argv):
    check = "--check" in argv
    try:
        universe, metadata = build()
    except SourceMissing as exc:
        print(exc)
        return 0 if check else 1

    if check:
        problems = []
        if not os.path.exists(OUT_UNIVERSE) or not os.path.exists(OUT_METADATA):
            problems.append("output missing -- run `python -m scripts.build_cgsi_basket`")
        else:
            with open(OUT_UNIVERSE, "r", encoding="utf-8") as fh:
                if json.load(fh) != universe:
                    problems.append("%s is stale" % os.path.relpath(OUT_UNIVERSE, BASE_DIR))
            with open(OUT_METADATA, "r", encoding="utf-8-sig", newline="") as fh:
                if list(csv.DictReader(fh)) != [
                        {k: str(v) for k, v in row.items()} for row in metadata]:
                    problems.append("%s is stale" % os.path.relpath(OUT_METADATA, BASE_DIR))
        for problem in problems:
            print("STALE: %s" % problem)
        print("OK — both files current." if not problems else "Rebuild required.")
        return 1 if problems else 0

    # Keep the reconstruction we shipped while waiting for the real list. It is the honest
    # record of what we did without the data, and the backtest series still references it.
    if os.path.exists(OUT_UNIVERSE) and not os.path.exists(PRIOR_UNIVERSE):
        with open(OUT_UNIVERSE, "r", encoding="utf-8") as fh:
            prior = fh.read()
        with open(PRIOR_UNIVERSE, "w", encoding="utf-8") as fh:
            fh.write(prior)
        print("kept prior universe -> %s" % os.path.relpath(PRIOR_UNIVERSE, BASE_DIR))

    _write_universe(universe)
    _write_metadata(metadata)

    constituents = universe["constituents"]
    signals = sum(len(c["events"]) for c in constituents)
    print("wrote %s  (%d constituents, %d dated events, %d high-conviction, %d delisted)"
          % (os.path.relpath(OUT_UNIVERSE, BASE_DIR), len(constituents), signals,
             sum(1 for c in constituents if c["high_conviction"]),
             sum(1 for c in constituents if c["delisted"])))
    print("wrote %s  (%d rows, frozen %d-column shape)"
          % (os.path.relpath(OUT_METADATA, BASE_DIR), len(metadata), len(HEADER)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
