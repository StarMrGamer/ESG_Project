"""Build the FICTIONAL sell-side client book — `data/clients.json`.

Deterministic and re-runnable. Nothing here is a real client: the five accounts are invented, and
the file says so on every record.

The one part that is NOT invented is the meeting history. A prior meeting stores the snapshot the
client was shown at the time, and rather than authoring plausible-looking earlier numbers this
script takes them from a REAL earlier state of the engine: the run over the VERIFIED BASKET ONLY,
with no harvest overlay applied. That is genuinely what the tool said before we gathered live
evidence, it is reproducible from this repo by anyone, and it makes the delta a true account of
what the harvest changed rather than a mocked-up demo of movement.

So the brief's headline — "RHB Bank crossed from Consensus to Hidden Winners on +9 signals since
you last met" — is a real transition this engine actually made, dated, against a real earlier
run_id. Inventing that number would have been easier and would have been a rule-2 breach.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import clients                                                          # noqa: E402
import company_metadata                                                 # noqa: E402
import engine                                                           # noqa: E402
import harvest                                                          # noqa: E402
import universe                                                         # noqa: E402

# The book. Account names are invented; the coverage lists are real tickers from the basket, chosen
# so each account has a reason to exist — a different mandate, a different corner of the universe,
# and between them at least one of every quadrant the matrix can produce.
BOOK = [
    {
        "client_id": "meridian_straits",
        "name": "Meridian Straits Asset Management",
        "account_type": "long_only",
        "desk": "ASEAN Equities",
        "mandate": "return",
        "profile": {"risk": "balanced", "horizon": "long", "green_focus": False},
        "brief_note": ("Core ASEAN financials book. Asks the same question every quarter: where "
                       "are we away from consensus, and what is the evidence."),
        "coverage": ["KLSE:RHBBANK", "SGX:OCBC", "SGX:UOB", "SGX:DBS", "KLSE:MAY", "KLSE:CIMB",
                     "IDX:BBCA", "SET:KTB"],
        "met": "2026-08-12",
        "meeting_note": "Quarterly review. Pushed back hard on the bank overweight.",
        "follow_ups": [
            "Send the source list behind the RHB governance signals.",
            "Confirm whether the incumbent notch on the basket is MSCI-sourced — CGSI's column "
            "header is unattributed.",
        ],
    },
    {
        "client_id": "kestrel_delta",
        "name": "Kestrel Delta Capital",
        "account_type": "hedge_fund",
        "desk": "Event / Special Situations",
        "mandate": "return",
        "profile": {"risk": "aggressive", "horizon": "short", "green_focus": False},
        "brief_note": ("Short-horizon book. Only interested in names where the rating and the "
                       "evidence point in opposite directions, and in what would flip them back."),
        "coverage": ["SET:PTTGC", "SET:PTT", "SET:TOP", "SET:PTTEP", "KLSE:PCHEM", "KLSE:PMAH",
                     "SET:SCC"],
        "met": "2026-08-18",
        "meeting_note": "Wanted the negative quadrants, not the positive ones.",
        "follow_ups": [
            "PTT Global Chemical reads 0.000 on the 45-day horizon — show them the long-horizon "
            "read beside it and explain the decay, not just the number.",
            "Traction screen is still unrun for both loss-makers. Do not present them as "
            "disqualified.",
        ],
    },
    {
        "client_id": "northwind_pension",
        "name": "Northwind Pension Trust",
        "account_type": "pension",
        "desk": "Sustainable Fixed Income",
        "mandate": "compliance",
        "profile": {"risk": "conservative", "horizon": "long", "green_focus": True},
        "brief_note": ("Green-labelled issuance mandate. The origination pipeline (N/M/K) is the "
                       "part of the brief they actually read."),
        "coverage": ["SET:PTT", "KLSE:MAY", "SGX:DBS", "SGX:OCBC", "KLSE:PCHEM", "SET:CPALL",
                     "KLSE:MISC", "SET:BEM"],
        "met": "2026-07-30",
        "meeting_note": "Mandate review. Asked for the verification process behind the labels.",
        "follow_ups": [
            "Green-bond rows are team-verified per the ICMA-based process, NOT CGSI-confirmed — "
            "say so explicitly, they will ask who signed off.",
            "PCHEM entered the bond-ready bucket once the traction cells landed. Show the "
            "before/after.",
        ],
    },
    {
        "client_id": "selat_sovereign",
        "name": "Selat Sovereign Investment Office",
        "account_type": "sovereign",
        "desk": "Strategic Holdings",
        "mandate": "risk",
        "profile": {"risk": "conservative", "horizon": "long", "green_focus": False},
        "brief_note": ("Long-dated strategic book. Cares more about stale data and stranded "
                       "positions than about alpha."),
        "coverage": ["KLSE:MAHB", "SET:INTUCH", "PSE:AC", "PSE:SM", "SGX:KEP", "KLSE:SIME",
                     "SET:BEM", "KLSE:AXIATA"],
        "met": "2026-08-05",
        "meeting_note": "Governance review of the strategic holdings.",
        "follow_ups": [
            "Malaysia Airports and Intouch both went private in 2025 and are still sitting in the "
            "basket. Lead with that — a static list going stale is the argument.",
        ],
    },
    {
        # No meeting history at all, deliberately: the brief has to handle a first meeting honestly
        # rather than diffing against zero and reporting every position as a dramatic move.
        "client_id": "ironbark_insurance",
        "name": "Ironbark Insurance Asset Management",
        "account_type": "insurer",
        "desk": "General Account",
        "mandate": "risk",
        "profile": {"risk": "conservative", "horizon": "long", "green_focus": True},
        "brief_note": "New account. First meeting — opening view, no change report.",
        "coverage": ["PSE:BDO", "PSE:BPI", "PSE:SMPH", "PSE:ALI", "PSE:TEL", "SGX:SGX",
                     "SET:CPN"],
        "met": "",
        "meeting_note": "",
        "follow_ups": [],
    },
]


def main():
    cons_verified = universe.constituents()
    meta = company_metadata.load(demo=False)

    # The EARLIER real state: verified basket only, no harvested evidence. This is what the tool
    # said before the sweeps, and it is what the prior meetings record.
    before = engine.run_engine(cons_verified, metadata=meta)
    # The CURRENT state, harvest overlay applied — what the board shows today.
    after = engine.run_engine(harvest.apply_overlay(cons_verified), metadata=meta)

    print("prior run (verified only)  %s · as_of %s · %d signals"
          % (before["run_id"], before["as_of"], before["signal_count"]))
    print("current run (+ harvest)    %s · as_of %s · %d signals\n"
          % (after["run_id"], after["as_of"], after["signal_count"]))

    book = []
    for spec in BOOK:
        client = {
            "client_id": spec["client_id"],
            "name": spec["name"],
            "account_type": spec["account_type"],
            "desk": spec["desk"],
            "mandate": spec["mandate"],
            "profile": spec["profile"],
            "brief_note": spec["brief_note"],
            "coverage": spec["coverage"],
            "meetings": [],
            "_origin": "fictional",
        }
        if spec["met"]:
            client["meetings"].append({
                "date": spec["met"],
                "run_id": before["run_id"],
                "as_of": before["as_of"],
                "note": spec["meeting_note"],
                "discussed": spec["coverage"],
                "follow_ups": [{"text": t, "done": False} for t in spec["follow_ups"]],
                "snapshot": clients.snapshot_for(before, spec["coverage"]),
                "_basis": ("Real engine state: the run over the verified basket with no harvested "
                           "evidence merged. Reproduce with engine.run_engine("
                           "universe.constituents())."),
            })
        book.append(client)

    clients.save_all(book)
    print("wrote %s\n" % clients.STORE)

    for c in book:
        d = clients.delta(c, after)
        s = clients.summary(c)
        print("  %-36s %2d names · last met %-10s · %d open"
              % (s["name"], s["coverage_n"], s["last_met"] or "never", s["open_follow_ups"]))
        if not d["has_baseline"]:
            print("      (first meeting — no baseline, and the brief says so)")
        for ch in d["changes"][:3]:
            print("      %-24s %s" % (ch["company"][:24], ch["note"]))
        if d["has_baseline"]:
            print("      %d unchanged" % d["unchanged"])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
