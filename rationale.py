"""Why this company carries this verdict — pros, cons, and what to look out for.

The board could always show WHAT a company was labelled. It could not say WHY, in a form a
person could argue with. A quadrant label and a momentum number are a conclusion; a reader — and
a judge — is entitled to the reasoning, including the parts that cut against the verdict.

So every case is built from BOTH sides and BOTH axes:

    ESG        pros / cons   from the engine record (momentum, confidence, source mix, breadth)
    FINANCIAL  pros / cons   from `financials.py` (profitability, earnings direction)
    WATCH-OUTS               the things that would change the answer, or that the answer hides

Three disciplines this module keeps:

1.  **Cons are never suppressed.** A Hidden Winner with 92% company-published sources gets that
    said on its own card. A case that only lists reasons to agree is marketing, and the whole
    premise of this project is that inconvenient evidence has to surface — we do not get to make
    an exception for our own verdicts.

2.  **Nothing here is a recommendation.** It explains a disagreement with a rating. It does not
    say buy, sell, hold, or rank, and the financial half is a CONTEXT GATE that never enters the
    ESG score — see `financials.py`.

3.  **No LLM.** Every line is derived by rule from the stored record, so the reasoning is
    reproducible from the same run and cannot drift between two readings of the same company.
    Same discipline as `signals.py`: the model reads, the rules decide.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import financials

#: Source types the confidence model grades at or below the company-PR cap. A case built mostly
#: on these is weak however many signals it has -- the Adaro lesson, stated on the card.
_SELF_PUBLISHED = {"company_pr", "unknown"}

#: Coverage saturates at 12 signals in `engine.confidence`; below a third of that, a direction is
#: an anecdote rather than a read.
_THIN_SIGNALS = 4

#: Below this, the engine is explicitly not confident. Same number the Hidden Winner gate uses.
_LOW_CONFIDENCE = 0.5

_PILLAR_NAME = {"E": "environment", "S": "social", "G": "governance", "DIGITAL": "digital/AI"}


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _source_mix(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How much of the case rests on the company's own publications."""
    total = len(signals or [])
    if not total:
        return {"total": 0, "self_published": 0, "share": None, "kinds": {}}
    kinds: Dict[str, int] = {}
    self_pub = 0
    for sig in signals:
        stype = str(sig.get("source_type") or "unknown")
        kinds[stype] = kinds.get(stype, 0) + 1
        if stype in _SELF_PUBLISHED:
            self_pub += 1
    return {"total": total, "self_published": self_pub,
            "share": round(self_pub / total, 2), "kinds": kinds}


def _esg_case(record: Dict[str, Any]) -> Dict[str, List[str]]:
    """The ESG half — read entirely off the engine record."""
    pros: List[str] = []
    cons: List[str] = []

    momentum = record.get("composite_momentum") or 0.0
    confidence = record.get("composite_confidence") or 0.0
    count = record.get("signal_count") or 0
    disagreement = record.get("disagreement") or 0.0
    signals = record.get("signals") or []
    mix = _source_mix(signals)

    # --- the disagreement itself: our half of the argument ---------------------------------- #
    if disagreement > 0 and momentum > 0:
        pros.append(
            f"The evidence points up ({momentum:+.3f}) while the incumbent rating puts this "
            f"company at the {_pct(record.get('lseg_percentile'))} percentile — a signed "
            f"disagreement of {disagreement:+.2f}. That gap IS the thesis.")
    elif disagreement < 0:
        cons.append(
            f"We disagree DOWNWARD: the rating is more positive than the evidence "
            f"({disagreement:+.2f}). A high rating here is not corroborated by what we can see.")

    if momentum > 0:
        pros.append(f"Composite momentum {momentum:+.3f} — the dated evidence agrees on "
                    f"direction more than it disagrees.")
    elif momentum < 0:
        cons.append(f"Composite momentum {momentum:+.3f} — the evidence points down.")
    elif count:
        cons.append("Momentum is exactly 0.000 despite evidence on file: the signals have "
                    "decayed past this horizon's half-life, or they cancel out.")

    # --- how much evidence, and of what quality --------------------------------------------- #
    if count >= 10:
        pros.append(f"{count} scored signals — past the coverage bar the Hidden Winner gate asks "
                    f"for.")
    elif count >= _THIN_SIGNALS:
        pros.append(f"{count} scored signals, each dated and sourced.")
    elif count:
        cons.append(f"Only {count} scored signal{'s' if count != 1 else ''}. Shrinkage holds the "
                    f"momentum down deliberately — one thin signal must never score like twelve.")
    else:
        cons.append("NO scorable evidence at all. This is an absence of evidence, not evidence "
                    "of no movement — the company sits on the zero line for a different reason "
                    "than the ones around it.")

    if mix["share"] is not None:
        share = mix["share"]
        if share >= 0.75:
            cons.append(
                f"{share * 100:.0f}% of the evidence is company-published. `source_quality` caps "
                f"that at 0.5 by rule, so confidence cannot climb however much more we gather. "
                f"This is the constraint, not the signal count.")
        elif share <= 0.4:
            pros.append(f"Only {share * 100:.0f}% of the evidence is company-published — the "
                        f"rest is external ({', '.join(k for k in mix['kinds'] if k not in _SELF_PUBLISHED) or 'n/a'}).")

    if confidence >= _LOW_CONFIDENCE:
        pros.append(f"Confidence {confidence:.2f} — clears the bar the Hidden Winner label needs.")
    elif count:
        cons.append(f"Confidence {confidence:.2f}, below the {_LOW_CONFIDENCE} bar. Coverage "
                    f"{record.get('coverage', 0):.2f} x corroboration "
                    f"{record.get('corroboration', 0):.2f} is what holds it there.")

    breadth = record.get("breadth") or 0
    if breadth >= 3:
        pros.append(f"Evidence spans {breadth} distinct subcomponents — corroboration, not one "
                    f"story told repeatedly.")
    elif breadth == 1 and count > 1:
        cons.append("Every signal routes to a single subcomponent: repetition rather than "
                    "corroboration.")

    # --- which pillars are actually covered -------------------------------------------------- #
    comps = record.get("components") or {}
    covered = [_PILLAR_NAME.get(k, k) for k in comps]
    missing = [name for key, name in _PILLAR_NAME.items() if key not in comps]
    if covered:
        pros.append(f"Pillars with evidence: {', '.join(covered)}.")
    if missing:
        cons.append(f"No evidence at all on {', '.join(missing)} — the verdict is silent there, "
                    f"which is not the same as clean.")

    if record.get("delisted"):
        cons.append("DELISTED — this name went private while sitting in a basket meant to be "
                    "current. It is excluded from investable output by rule.")

    notch = record.get("incumbent_notch")
    if notch:
        pros.append(f"An industry-standard notch grade is on file ({notch}) — carried "
                    f"unattributed and never scored, but it is a second view of the same company.")
    return {"pros": pros, "cons": cons}


def _financial_case(row: Dict[str, Any]) -> Dict[str, Any]:
    """The financial half — the CONTEXT GATE, never part of the ESG score."""
    via = financials.viability(row or {})
    earn = via["earnings"]
    pros: List[str] = []
    cons: List[str] = []

    if via["profitability_flag"] == "profitable":
        pros.append("Profitable in the latest reported FY.")
    elif via["profitability_flag"] == "loss_making":
        cons.append("Loss-making in the latest reported FY. The four-test traction screen "
                    "decides this case; an unrun screen is NOT a failure.")
    else:
        cons.append("Profitability is not stated in the basket — unknown, not negative.")

    growth, direction = earn["growth_pct"], earn["direction"]
    if direction in ("growing", "swung to profit"):
        pros.append(f"Earnings {direction}"
                    + (f" ({growth:+.1f}% on the two FY cells)." if growth is not None else "."))
    elif direction == "growing modestly":
        pros.append(f"Earnings up modestly ({growth:+.1f}%) — inside the noise band for a "
                    f"two-year read, so treat it as stable rather than rising.")
    elif direction in ("declining", "softening", "widening loss", "swung to loss"):
        cons.append(f"Earnings {direction}"
                    + (f" ({growth:+.1f}%)." if growth is not None else "."))
    elif direction == "narrowing loss":
        pros.append(f"Loss is narrowing ({growth:+.1f}%) — a direction, not a return to profit.")
    elif direction == "flat":
        cons.append(f"Earnings flat ({growth:+.1f}%) — no financial tailwind behind the ESG story.")
    else:
        cons.append("Earnings trend could not be read from the two cells on file.")

    # A figure inflated by one-offs is the classic way a growth number flatters a company, and
    # several rows say so IN the cell. Surfacing it is the difference between reading the data
    # and reading the number.
    blob = f"{earn['latest_text']} {earn['prior_text']}".lower()
    if "one-off" in blob or "one off" in blob or "incl" in blob:
        cons.append("The reported figure carries one-offs — the row says so. The underlying "
                    "number is materially different; read the cell, not the percentage.")
    if "cont. ops" in blob or "continuing" in blob:
        cons.append("Continuing versus total operations differ on this row — the growth read "
                    "depends on which basis you take.")

    if str(row.get("traction_flag") or "").strip():
        pros.append(f"Traction screen recorded: {row.get('traction_flag')}.")
    elif via["profitability_flag"] == "loss_making":
        cons.append("Traction screen not yet run for this loss-maker — `screen_not_run`, which "
                    "is neither cleared nor disqualified.")

    return {"pros": pros, "cons": cons, "verdict": via["verdict"], "earnings": earn,
            "label": financials.LABEL}


def _watch_outs(record: Dict[str, Any], row: Dict[str, Any]) -> List[str]:
    """What would change this answer, and what the answer is quietly resting on."""
    out: List[str] = []
    count = record.get("signal_count") or 0
    disagreement = record.get("disagreement") or 0.0

    if 0 < count <= _THIN_SIGNALS:
        out.append(f"Thin base: removing any one of {count} signals could move the label. "
                   f"Run the sensitivity view before quoting this verdict.")
    if abs(disagreement) < 0.35:
        out.append(f"Close to the disagreement boundary ({disagreement:+.2f}) — a small amount of "
                   f"new evidence flips which side of the argument this company is on.")
    if str(row.get("is_provisional") or "").strip().upper() in ("TRUE", "1", "YES"):
        out.append("The green-bond metadata for this company is still PROVISIONAL — not yet "
                   "human-verified, so any tier that depends on it is provisional too.")
    if record.get("baseline_origin") == "MOCK":
        out.append("The incumbent baseline here is a MOCK score with no stated basis. The "
                   "disagreement is therefore against a placeholder, not a published rating.")
    dates = sorted([str(s.get("published_at") or "")[:10]
                    for s in (record.get("signals") or []) if s.get("published_at")], reverse=True)
    if dates and dates[0] < "2024":
        out.append(f"Newest evidence is from {dates[0]} — this reads as a long-horizon verdict "
                   f"and will decay to nothing on the short horizon.")
    if not out:
        out.append("No boundary or provenance flags on this one — the usual caveat still holds "
                   "that this is a disagreement with a rating, not a recommendation.")
    return out


def build(record: Dict[str, Any], row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The full case for one company: `{label, summary, esg, financial, watch_outs}`.

    `record` is a FULL engine record (signals included — `_record_summary` strips them).
    `row` is the company's metadata row, or None if it has none.
    """
    record = record or {}
    row = row or {}
    esg = _esg_case(record)
    fin = _financial_case(row)
    label = record.get("label_display") or record.get("label") or "unclassified"

    # The summary states BOTH axes, in that order, and never merges them into one judgement.
    momentum = record.get("composite_momentum") or 0.0
    confidence = record.get("composite_confidence") or 0.0
    summary = (
        f"{label}: momentum {momentum:+.3f} at confidence {confidence:.2f} on "
        f"{record.get('signal_count', 0)} dated signals, against an incumbent rating at the "
        f"{_pct(record.get('lseg_percentile'))} percentile. Financially {fin['verdict']}. "
        f"The two are reported side by side and are NOT combined — the financial read gates "
        f"whether an ESG disagreement is worth acting on, it never changes the ESG verdict.")

    return {
        "company_id": record.get("company_id", ""),
        "company": record.get("company", ""),
        "label": record.get("label", ""),
        "label_display": label,
        "summary": summary,
        "esg": esg,
        "financial": fin,
        "watch_outs": _watch_outs(record, row),
        "counts": {"esg_pros": len(esg["pros"]), "esg_cons": len(esg["cons"]),
                   "fin_pros": len(fin["pros"]), "fin_cons": len(fin["cons"])},
    }


if __name__ == "__main__":                                   # pragma: no cover - developer CLI
    import sys
    import company_metadata
    import engine
    import harvest
    import universe

    want = sys.argv[1] if len(sys.argv) > 1 else None
    cons = harvest.apply_overlay(universe.constituents())
    run = engine.run_engine(cons, metadata=company_metadata.load(demo=False))
    rows = company_metadata.load(demo=False)
    recs = [r for r in run["records"] if not want or r["company_id"] == want]
    if want and not recs:
        print(f"no such company: {want}")
        raise SystemExit(1)
    if not want:
        recs = sorted(recs, key=lambda r: -(r.get("disagreement") or 0))[:3]
    for rec in recs:
        case = build(rec, rows.get(rec["company_id"]))
        print(f"\n=== {case['company']} ({case['company_id']}) — {case['label_display']} ===")
        print(f"  {case['summary']}\n")
        for side in ("esg", "financial"):
            print(f"  {side.upper()}")
            for p in case[side]["pros"]:
                print(f"    + {p}")
            for c in case[side]["cons"]:
                print(f"    - {c}")
        print("  WATCH OUT FOR")
        for w in case["watch_outs"]:
            print(f"    ! {w}")
