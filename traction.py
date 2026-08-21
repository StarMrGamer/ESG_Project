"""
traction.py — the screen a loss-making company is routed through instead of the profit flag.
=============================================================================================

Playbook step 4, Methodology Additions §B.4. Where a company is not currently profitable,
profitability alone is too blunt a disqualifier — a company can be investing ahead of revenue.
So four demand tests replace it, with thresholds set once, disclosed, and frozen for the pilot:

    1. revenue_growth   revenue growth of at least 10% compound over the last two FYs
    2. cash_flow        operating cash flow positive, OR negative but improving across the two
    3. order_book       a contracted order book or backlog disclosed in the annual report
    4. green_pipeline   signed PPAs, or a committed green capital-expenditure pipeline

    >= 2 met  -> positive traction flag
    0 met     -> disqualified from the pilot universe on debt-service capacity grounds
    otherwise -> the screen has run and the company sits between the two

THE THRESHOLDS ARE OURS. The disqualifier list in §B.3 is ACMF / ICMA / MAS / SGX — the market's
bar, not ours. This screen is not: the CGSI panel never confirmed these four, so every surface
that shows a traction verdict labels it a **team-designed measure**.

WHAT THIS MODULE WILL AND WILL NOT DO
-------------------------------------
It will compute a verdict from evidence. It will NOT invent the evidence.

The verified basket carries net income and nothing else — no revenue, no operating cash flow, no
order book — so tests 1 and 2 come back `unknown` for both loss-makers until somebody supplies
the figures. `unknown` is NOT `fail`: an unrun test is a gap in what we know, and scoring it as
a failure would disqualify a company for our missing data rather than for its own numbers.

What it does do is **assemble the sheet**: it retrieves real, dated, sourced candidate evidence
for each test through the same harvest pipeline the engine uses, attaches it with URLs, and
leaves the verdict for a human. That is the maker-checker split the panel asked for, applied to
the one screen a person still has to sign: AI gathers, a named reviewer decides.

    python traction.py                 # the screen as it stands, for every loss-maker
    python traction.py --gather        # + retrieve candidate evidence per test (live, billable)
    python traction.py --sheet         # write data/traction_sheet.json for Sean/Cayden to fill
    python traction.py --apply         # fold a filled sheet back into the metadata CSV
"""

import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import company_metadata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(BASE_DIR, "data", "traction_sheet.json")

#: §B.4, frozen for the pilot. `needs` says what a human has to look at to settle each test —
#: written as an instruction because a blank cell with no instruction is how a screen quietly
#: never gets run.
TESTS = (
    ("revenue_growth",
     "Revenue growth >= 10% compound over the last two financial years",
     "Revenue for the last two FYs, from the annual report or results announcement."),
    ("cash_flow",
     "Operating cash flow positive, or negative but improving across the two years",
     "Net cash from operating activities for the last two FYs, from the cash-flow statement."),
    ("order_book",
     "A contracted order book or backlog disclosed in the annual report",
     "Any disclosed backlog, contracted revenue or order book figure, with the page or note."),
    ("green_pipeline",
     "Signed power purchase agreements, or a committed green capex pipeline",
     "Signed PPAs, or a board-approved green/transition capex commitment with an amount."),
)

#: The three states a test can be in. `unknown` is deliberately distinct from `fail`.
STATES = ("met", "not_met", "unknown")

MIN_MET = 2

LABEL = ("Traction screen — team-designed measure. Thresholds are ours and were NOT confirmed "
         "by the CGSI panel. A context flag, not credit analysis: green-bond eligibility "
         "attaches to use-of-proceeds and external review, never to issuer profitability.")

#: Search angles for the candidate evidence behind each test. Used only with `--gather`.
_ANGLES = {
    "revenue_growth": "annual revenue results FY growth year on year",
    "cash_flow": "net cash from operating activities cash flow statement annual report",
    "order_book": "order book backlog contracted revenue disclosed annual report",
    "green_pipeline": "power purchase agreement PPA signed green capex commitment "
                      "renewable investment",
}

_NUM = re.compile(r"-?[\d,]+(?:\.\d+)?")
#: "FY2025", "FY25", or a bare 4-digit year — a label, never an amount.
_FY = re.compile(r"\bFY\s*\d{2,4}\b|\b(?:19|20)\d{2}\b", re.I)


def loss_makers(rows: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Every company the profitability screen routed here. Keyed by company_id."""
    rows = company_metadata.load() if rows is None else rows
    return {cid: row for cid, row in sorted(rows.items())
            if row.get("profitability_flag") == "loss_making"}


def _net_income_trend(row: Dict[str, Any]) -> Dict[str, Any]:
    """A READING of the two net-income cells, reported separately from the four tests.

    It is not one of them. §B.4 asks about operating cash flow, and net income is not that —
    treating a narrowing loss as if it satisfied the cash-flow test would be answering an easier
    question than the one the methodology asks. It is surfaced because it is the only financial
    trajectory the basket actually carries, and a reviewer should see it."""
    latest, prior = row.get("fy_minus1_net_income", ""), row.get("fy_minus2_net_income", "")

    def _mag(text):
        # Strip the fiscal-year label FIRST. "FY2025 -THB14.6b LOSS" otherwise yields 2025 —
        # the year, not the amount — and two consecutive years then read as a widening loss
        # when the loss is in fact halving.
        body = _FY.sub(" ", (text or "").replace(",", ""))
        hit = _NUM.search(body)
        if not hit:
            return None
        value = abs(float(hit.group()))
        if re.search(r"\d\s*(?:b\b|bn\b|billion)", body.lower()):
            value *= 1000.0
        return value

    a, b = _mag(latest), _mag(prior)
    both_loss = "loss" in (latest or "").lower() and "loss" in (prior or "").lower()
    direction = "unknown"
    if a is not None and b is not None and both_loss:
        direction = "narrowing" if a < b else ("widening" if a > b else "flat")
    elif "loss" in (latest or "").lower() and "loss" not in (prior or "").lower():
        direction = "swung to loss"
    return {"latest": latest, "prior": prior, "direction": direction,
            "note": ("Net income, not operating cash flow — reported for context, and NOT "
                     "counted toward the four tests.")}


def screen(row: Dict[str, Any], answers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run the four tests over whatever answers exist. Pure — no I/O, no clock."""
    answers = answers or {}
    results = []
    for key, rule, needs in TESTS:
        state = answers.get(key, "unknown")
        if state not in STATES:
            state = "unknown"
        results.append({"test": key, "rule": rule, "needs": needs, "state": state,
                        "evidence": (answers.get(key + "_evidence") or "").strip(),
                        "source_url": (answers.get(key + "_source") or "").strip()})

    met = sum(1 for r in results if r["state"] == "met")
    not_met = sum(1 for r in results if r["state"] == "not_met")
    unknown = sum(1 for r in results if r["state"] == "unknown")

    if met >= MIN_MET:
        verdict, flag = "traction", True
    elif not_met == len(TESTS):
        verdict, flag = "disqualified", False
    elif unknown:
        verdict, flag = "screen_not_run", False
    else:
        verdict, flag = "insufficient_traction", False

    return {
        "tests": results, "met": met, "not_met": not_met, "unknown": unknown,
        "verdict": verdict,
        "traction_flag": flag,
        "reason": {
            "traction": "Meets %d of 4 — at or above the two required." % met,
            "disqualified": "Meets none of the four. Disqualified on debt-service capacity.",
            "screen_not_run": ("%d of 4 tests have no answer yet, so the screen has not run. "
                               "Unknown is not a failure — the company is neither cleared nor "
                               "disqualified until somebody fills them." % unknown),
            "insufficient_traction": "Meets %d of 4, below the two required." % met,
        }[verdict],
        "label": LABEL,
        "net_income": _net_income_trend(row),
    }


def gather(row: Dict[str, Any], *, use_cache: bool = True) -> Dict[str, List[Dict[str, str]]]:
    """Candidate evidence per test — real, dated, sourced. NEVER sets a state (rule 2 + §5).

    Imported lazily so the screen itself stays import-safe and network-free."""
    import harvest, rag                                        # noqa: PLC0415

    name = row.get("company_name", "")
    out: Dict[str, List[Dict[str, str]]] = {}
    for key, angle in _ANGLES.items():
        try:
            ctx = rag.gather_context("%s %s" % (name, angle), k=6, use_cache=use_cache)
        except Exception:                                       # noqa: BLE001 — rule 1
            out[key] = []
            continue
        out[key] = [{"title": s.get("title", ""), "url": s.get("url", ""),
                     "snippet": (s.get("snippet") or "")[:320],
                     "source_type": harvest._source_type_for(s.get("url", ""))}
                    for s in (ctx.get("snippets") or [])]
    return out


# --------------------------------------------------------------------------- #
#  the sheet
# --------------------------------------------------------------------------- #
def build_sheet(*, with_evidence: bool = False) -> Dict[str, Any]:
    rows = loss_makers()
    companies = {}
    for cid, row in rows.items():
        entry = {
            "company": row.get("company_name", cid),
            "industry": row.get("industry", ""),
            "note_from_cgsi": row.get("notes", ""),
            "net_income": _net_income_trend(row),
            "answers": {k: "unknown" for k, _, _ in TESTS},
        }
        for key, _, _ in TESTS:
            entry["answers"][key + "_evidence"] = ""
            entry["answers"][key + "_source"] = ""
        if with_evidence:
            entry["candidate_evidence"] = gather(row)
        companies[cid] = entry
    return {
        "_note": ("Traction screen sheet — playbook step 4, Methodology Additions §B.4. Set each "
                  "answer to met / not_met / unknown and paste the figure plus its source. "
                  "`unknown` is not a failure: it means nobody has looked yet, and a company is "
                  "neither cleared nor disqualified while any test is unanswered."),
        "_owner": "Sean & Cayden",
        "_label": LABEL,
        "_states": list(STATES),
        "_rule": "met >= 2 -> traction flag; met == 0 and all four answered -> disqualified",
        "_candidate_evidence": ("Retrieved, not decided. Every item is a real search result with "
                                "its URL — it is there to save the lookup, and it never sets a "
                                "state. A human sets the state." if with_evidence else
                                "not gathered — run `python traction.py --sheet --gather`"),
        "companies": companies,
    }


def load_sheet(path: str = SHEET) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _report(cid: str, row: Dict[str, Any], answers: Optional[Dict[str, str]]) -> None:
    result = screen(row, answers)
    ni = result["net_income"]
    print("%s  %s" % (cid, row.get("company_name", "")))
    print("   CGSI note      %s" % (row.get("notes", "") or "—"))
    print("   net income     %s  ->  %s   (%s)" % (ni["prior"], ni["latest"], ni["direction"]))
    for t in result["tests"]:
        mark = {"met": "[x]", "not_met": "[ ]", "unknown": "[?]"}[t["state"]]
        print("   %s %-15s %s" % (mark, t["test"], t["rule"]))
        if t["state"] == "unknown":
            print("       needs: %s" % t["needs"])
        elif t["evidence"]:
            print("       %s  %s" % (t["evidence"], t["source_url"]))
    print("   VERDICT        %s — %s" % (result["verdict"].upper(), result["reason"]))
    print()


def apply_sheet(path: str = SHEET) -> Dict[str, Any]:
    """Fold a FILLED sheet back into `data/company_metadata.csv`.

    Writes only `traction_flag` and `traction_evidence`, only for loss-makers, and only where
    the screen has actually run — a company with any `unknown` left is skipped rather than
    written as a blank flag, because a blank cell and "we looked and found nothing" are
    different states and the tier logic reads them the same way."""
    sheet = load_sheet(path).get("companies", {})
    if not sheet:
        return {"written": 0, "skipped": [], "note": "no sheet on disk — run --sheet first"}

    target = company_metadata.active_file()
    with open(target, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header, rows = list(reader.fieldnames or []), list(reader)

    rowsets = loss_makers()
    written, skipped = 0, []
    for row in rows:
        cid = (row.get("company_id") or "").strip()
        if cid not in rowsets or cid not in sheet:
            continue
        result = screen(rowsets[cid], sheet[cid].get("answers"))
        if result["verdict"] == "screen_not_run":
            skipped.append(cid)
            continue
        row["traction_flag"] = "Y" if result["traction_flag"] else "N"
        row["traction_evidence"] = "; ".join(
            "%s: %s" % (t["test"], t["evidence"] or t["state"])
            for t in result["tests"] if t["state"] != "unknown")
        written += 1

    if written:
        with open(target, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return {"written": written, "skipped": skipped,
            "note": "%s updated" % os.path.relpath(target, BASE_DIR) if written
                    else "nothing to write — every screen is still unrun"}


def main(argv: List[str]) -> int:
    rows = loss_makers()
    if not rows:
        print("No loss-making companies in the active metadata. Nothing to screen.")
        return 0

    if "--apply" in argv:
        out = apply_sheet()
        print(out["note"])
        if out["skipped"]:
            print("skipped (screen still unrun): %s" % ", ".join(out["skipped"]))
        return 0

    if "--sheet" in argv:
        sheet = build_sheet(with_evidence="--gather" in argv)
        with open(SHEET, "w", encoding="utf-8") as fh:
            json.dump(sheet, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print("wrote %s — %d company(ies) for %s"
              % (os.path.relpath(SHEET, BASE_DIR), len(sheet["companies"]), sheet["_owner"]))
        if "--gather" not in argv:
            print("Add --gather to attach real candidate evidence per test (live, billable).")
        return 0

    sheet = load_sheet().get("companies", {})
    print("TRACTION SCREEN — %d loss-making company(ies)" % len(rows))
    print("%s\n" % LABEL)
    for cid, row in rows.items():
        _report(cid, row, (sheet.get(cid) or {}).get("answers"))

    # Keyed on the VERDICT, not on leftover unknowns: once two tests are met the rule is
    # satisfied and the remaining ones cannot unsatisfy it, so a company that has reached
    # `traction` is done even with a blank cell left on the sheet.
    unfilled = [cid for cid in rows
                if screen(rows[cid], (sheet.get(cid) or {}).get("answers"))["verdict"]
                == "screen_not_run"]
    if unfilled:
        print("The screen has NOT run for: %s" % ", ".join(unfilled))
        print("Neither cleared nor disqualified — `python traction.py --sheet --gather` builds "
              "the sheet with the sources already looked up.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
