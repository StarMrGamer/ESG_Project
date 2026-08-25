"""Financial viability — the second axis, kept deliberately OUTSIDE the ESG score.

Why this module exists
----------------------
The ESG engine answers one question: *which way is the evidence pointing, and does the incumbent
rating agree?* A reasonable objection is that a company can be improving on ESG and still be a
bad business — so "is it also going to make money?" deserves an answer.

This module answers it as a **gate**, never as a term in the momentum maths.

That distinction is the whole design. `disagreement` currently means one specific, defensible
thing: our evidence-based momentum percentile minus the incumbent rating's percentile. Fold an
earnings-growth term into it and nobody — including us — can say what a disagreement of +0.6 is
claiming any more, and the output stops being "we disagree with this rating" and becomes a
composite pick. Nothing in `engine.py` or `signals.py` imports this file, and nothing should.

Where the numbers come from
---------------------------
`data/company_metadata.csv` carries two fiscal years of net income for **all 52** companies,
verified by us with sources on the row. That is real, dated, local financial data and it needs no
fetch — which matters, because the free keyless financial endpoints do not exist any more
(Yahoo's `quoteSummary` now requires a crumb; MSCI/S&P/Sustainalytics are licensed products).

So the growth read below is computed from data we already hold and can point at. The live half of
the picture — the 90-day price move — stays in `quotes.py`, stays best-effort, and stays context.

The comparison that is NOT allowed
----------------------------------
Net income is carried in each company's own reporting currency (Rp trillions, THB billions, S$
millions). A magnitude is therefore meaningful **only against the same company's other year**.
`growth_pct` is a within-company ratio, so the currency cancels; an absolute figure is never
compared across companies and `parse_amount` is deliberately not exported for ranking. Comparing
Rp57.5T against S$10.3b would be two different measures subtracted — the exact error
`benchmarks.py` refuses to make with GHG intensity, arriving through a different door.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

import company_metadata

#: Fiscal-year labels, stripped BEFORE any number is read. "FY2025 -THB14.6b" otherwise yields
#: 2025 -- the year, not the amount -- and two consecutive years then read as a widening loss when
#: the loss is in fact halving. This bug was real; see traction.py's note on PTTGC.
_FY = re.compile(r"\bFY\s*\d{2,4}\b|\b(?:19|20)\d{2}\b", re.I)
_NUM = re.compile(r"-?[\d,]+(?:\.\d+)?")

#: PART-YEAR markers: "9M2024", "1H2025", "Q3FY24". These do NOT get stripped as fiscal-year
#: labels, because "2024" inside "9M2024" has no word boundary before it -- so the plain reader
#: took the leading "9" as the amount and reported Malaysia Airports as -98.3%. Worse than the
#: mis-parse: a nine-month figure is not comparable to a full year at all, so when one appears
#: the growth percent is SUPPRESSED rather than computed off two different period lengths.
_PART_YEAR = re.compile(r"\b(\d{1,2}[MH]|Q[1-4])\s*(?:FY)?\s*\d{2,4}\b", re.I)

#: A RANGE, e.g. "~RM3.3-3.4b". The unit belongs to the LAST number, and taking the first number
#: alone yields RM3.3 MILLION against a RM3.1 BILLION prior year -- which is how RHB Bank came
#: out at -99.9%. The midpoint is taken and the read is marked approximate.
_RANGE = re.compile(r"(-?[\d,]+(?:\.\d+)?)\s*[-\u2013\u2014]\s*(-?[\d,]+(?:\.\d+)?)")

#: Scale suffix read from the characters IMMEDIATELY AFTER the matched number -- never from
#: anywhere in the cell. Several rows carry a parenthetical second figure on a different scale
#: ("FY2025 S$789m (S$1.1b cont. ops)"), and a loose search finds that "b", multiplies the 789
#: MILLION by a thousand and reports +83,836% growth. Which is what it did.
_UNIT_SUFFIX = re.compile(r"^\s*(tn|trillion|t|bn|billion|b|mn|million|m)\b", re.I)
_UNIT_SCALE = {"t": 1_000_000.0, "tn": 1_000_000.0, "trillion": 1_000_000.0,
               "b": 1_000.0, "bn": 1_000.0, "billion": 1_000.0,
               "m": 1.0, "mn": 1.0, "million": 1.0}

#: A company is only called a grower if the change clears this. Two years of net income is a
#: noisy read -- FX, one-off provisions, a disposal -- so a 2% move is not a trend, and saying it
#: is would be the same over-reading of thin evidence that `shrinkage` exists to prevent.
FLAT_BAND_PCT = 5.0

#: What counts as strong growth. OURS, and never confirmed by anyone: say so on every surface,
#: exactly as the traction screen does with its own thresholds.
STRONG_GROWTH_PCT = 10.0

LABEL = ("Financial read — team-designed measure, thresholds are ours and were NOT confirmed by "
         "the CGSI panel. Computed from the two net-income cells the basket carries. It is a "
         "CONTEXT GATE, never part of the ESG score: no financial figure enters momentum, "
         "disagreement, confidence or a quadrant label.")


def parse_amount(text: str) -> Optional[float]:
    """A net-income cell -> a magnitude in millions of its OWN currency, sign preserved.

    Returns None when no number survives. Only ever meaningful against the same company's other
    year -- see the module docstring on why this is not a cross-company quantity.
    """
    if not text:
        return None
    body = _PART_YEAR.sub(" ", str(text).replace(",", ""))
    body = _FY.sub(" ", body)

    rng = _RANGE.search(body)
    if rng:
        # Midpoint of the stated range, with the unit read from after the SECOND number.
        low, high = float(rng.group(1)), float(rng.group(2))
        value = (low + high) / 2.0
        suffix = _UNIT_SUFFIX.match(body[rng.end():])
    else:
        hit = _NUM.search(body)
        if not hit:
            return None
        value = float(hit.group())
        suffix = _UNIT_SUFFIX.match(body[hit.end():])
    if suffix:
        value *= _UNIT_SCALE[suffix.group(1).lower()]
    # "LOSS" is written as a word on some rows and as a minus on others; a row that says both
    # must not double-negate back to a profit.
    if "loss" in body.lower() and value > 0:
        value = -value
    return value


def earnings_read(row: Dict[str, Any]) -> Dict[str, Any]:
    """The two net-income cells, read as a direction. Pure -- no I/O, no clock.

    `growth_pct` is `(latest - prior) / |prior|`, so the currency cancels and a company that
    swung from a loss to a profit is not reported as a percentage of a negative base (that number
    is arithmetically fine and rhetorically meaningless, so it is suppressed and the swing is
    named instead).
    """
    latest_raw = (row or {}).get("fy_minus1_net_income", "")
    prior_raw = (row or {}).get("fy_minus2_net_income", "")
    latest, prior = parse_amount(latest_raw), parse_amount(prior_raw)

    out = {"latest_text": latest_raw, "prior_text": prior_raw, "growth_pct": None,
           "direction": "unknown", "basis": "two FY net-income cells carried in the basket",
           "note": ""}

    # A part-year figure against a full year is not a growth rate, it is a period-length
    # artefact. Refusing to compute it is the same rule as `unknown != not_met`: we do not
    # manufacture a number to fill a cell we cannot honestly fill.
    part_latest = bool(_PART_YEAR.search(str(latest_raw or "")))
    part_prior = bool(_PART_YEAR.search(str(prior_raw or "")))
    if part_latest != part_prior:
        out["direction"] = "not comparable"
        out["note"] = ("One cell covers a PART year and the other a full year — different period "
                       "lengths, so no growth rate is computed. Not a failure; a data shape.")
        return out
    if latest is None or prior is None or prior == 0:
        out["note"] = "Net income not readable for both years — unknown, which is not a failure."
        return out

    if prior < 0 <= latest:
        out["direction"] = "swung to profit"
        out["note"] = ("Growth percent is suppressed: a percentage of a negative base is "
                       "arithmetically valid and tells a reader nothing.")
        return out
    if latest < 0 <= prior:
        out["direction"] = "swung to loss"
        out["note"] = "Growth percent is suppressed: the base changed sign."
        return out
    if latest < 0 and prior < 0:
        out["direction"] = "narrowing loss" if latest > prior else (
            "widening loss" if latest < prior else "flat loss")
        out["growth_pct"] = round((latest - prior) / abs(prior) * 100, 1)
        return out

    growth = round((latest - prior) / abs(prior) * 100, 1)
    out["growth_pct"] = growth
    if growth >= STRONG_GROWTH_PCT:
        out["direction"] = "growing"
    elif growth > FLAT_BAND_PCT:
        out["direction"] = "growing modestly"
    elif growth >= -FLAT_BAND_PCT:
        out["direction"] = "flat"
    elif growth > -STRONG_GROWTH_PCT:
        out["direction"] = "softening"
    else:
        out["direction"] = "declining"
    return out


#: The gate's four states. `unknown` is deliberately distinct from `weak` -- the same discipline
#: `traction.py` keeps. A company whose cells we cannot read has not failed anything; scoring our
#: own missing data as its failure is how a data gap becomes a false verdict.
VERDICTS = ("strong", "adequate", "weak", "unknown")


def viability(row: Dict[str, Any]) -> Dict[str, Any]:
    """The financial GATE for one company. Pure.

    Combines the profitability flag the basket carries with the earnings direction read above.
    It answers "can this company pay for itself while it improves?" -- it does NOT answer "is
    this a good investment", it produces no score, and it ranks nothing.
    """
    earnings = earnings_read(row)
    flag = str((row or {}).get("profitability_flag") or "").strip().lower()
    direction = earnings["direction"]
    reasons = []

    if flag == "profitable":
        reasons.append("profitable in the latest FY")
    elif flag == "loss_making":
        reasons.append("loss-making in the latest FY")
    else:
        reasons.append("profitability not stated in the basket")

    if direction in ("growing", "swung to profit"):
        reasons.append(f"earnings {direction}")
    elif direction != "unknown":
        reasons.append(f"earnings {direction}")

    if flag == "profitable" and direction in ("growing", "swung to profit"):
        verdict = "strong"
    elif flag == "profitable" and direction in ("growing modestly", "flat"):
        verdict = "adequate"
    elif flag == "profitable" and direction == "unknown":
        verdict = "adequate"
        reasons.append("earnings trend unreadable — profitability alone carries this")
    elif flag == "profitable":
        verdict = "weak"
    elif flag == "loss_making":
        # A loss-maker is NOT auto-failed. `traction.py` runs the four-test screen for exactly
        # this case, and until it has been run the honest answer is `unknown`.
        verdict = "unknown"
        reasons.append("loss-making — the four-test traction screen decides this one, "
                       "and an unrun screen is not a failure")
    else:
        verdict = "unknown"

    return {"verdict": verdict, "reasons": reasons, "earnings": earnings,
            "profitability_flag": flag or "unknown", "label": LABEL}


def profiles(demo: bool = False) -> Dict[str, Dict[str, Any]]:
    """`{company_id: viability(...)}` for a whole universe. Metadata follows its universe --
    passing `demo` is not optional, because the mock rows key on the fictional tickers and the
    verified CSV on the real 52 (see company_metadata.active_file)."""
    rows = company_metadata.load(demo=demo)
    return {cid: viability(row) for cid, row in sorted(rows.items())}


if __name__ == "__main__":                                   # pragma: no cover - developer CLI
    import collections
    import sys
    demo = "--demo" in sys.argv
    out = profiles(demo=demo)
    tally = collections.Counter(v["verdict"] for v in out.values())
    for cid, v in out.items():
        e = v["earnings"]
        growth = f"{e['growth_pct']:+.1f}%" if e["growth_pct"] is not None else "—"
        print(f"  {cid:16} {v['verdict']:9} {growth:>8}  {e['direction']:<18} {e['latest_text']}")
    print("\n", dict(tally), f"over {len(out)} companies")
    print(" ", LABEL)
