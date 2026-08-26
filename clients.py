"""clients.py — the sell-side analyst's book, and what changed since they last spoke.

The audience is a SELL-SIDE ESG research analyst: they cover a universe, they have a roster of
institutional accounts, and they walk into a client call needing to defend a view that a
portfolio manager will push back on. This module holds the roster and the meeting log; `brief.py`
composes the actual pre-meeting brief on top of it.

Three design decisions worth stating, because each one saved a lot of code:

**A client profile IS a saved setup.** `Setup.tsx` already asks mandate, risk appetite, holding
period and green-finance focus, and those already derive the A5 tier and the decay horizon that
drive the board. A client's profile is the same four answers under an account name — so opening a
client just re-applies a setup, and nothing new had to be invented to describe what they care
about. `mandate` is Contract A's own `risk | return | compliance`, unchanged.

**The delta is computed from a STORED SNAPSHOT, not from run archaeology.** Every run is
deterministic and cached, so in principle you could re-run the engine at an old cutoff and diff.
In practice the honest and much cheaper answer is to record what we told the client AT THE TIME —
a handful of fields per covered name — and diff the current run against that. It also survives a
config change, which run archaeology would not: if the thresholds moved, "what changed since we
last spoke" must still mean "against what you were actually shown", not "against what the current
config would have said back then".

**Nothing here scores anything.** This is a pure overlay: it reads engine records, stores a copy
of a few fields, and subtracts. No signal is created, no weight is set, no label is decided, and
`run_id` is untouched — which matters, because the frozen N/M/K, the whitepaper figures and the
Sepolia anchor all key on it.

The shipped roster is FICTIONAL and says so on every record (`_origin: "fictional"`), the same
discipline `data/hero_company.json` carries. Real client names, holdings or contact details do not
belong in a demo repo, and a plausible-looking one is worse than an obviously invented one.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE_DIR, "data", "clients.json")

#: The per-company state a meeting records. Deliberately small: these are the fields a client was
#: actually shown and would notice moving. Storing the whole record would make every brief diff
#: noisy with internals (weights, shrinkage) that nobody was told about and nobody can act on.
SNAP_FIELDS = ("label", "label_display", "composite_momentum", "composite_confidence",
               "signal_count", "disagreement", "momentum_percentile", "lseg_percentile")

#: Below these, a move is noise rather than news. A client meeting has a finite number of minutes;
#: a brief that reports every third-decimal wobble trains the reader to skim past the one that
#: mattered. A LABEL change is always reported regardless of how small the move behind it was —
#: crossing a quadrant boundary changes what we are claiming, which is the definition of material.
EPS_CONFIDENCE = 0.05
EPS_MOMENTUM = 0.05

ACCOUNT_TYPES = ("long_only", "hedge_fund", "pension", "insurer", "sovereign", "private_bank")
MANDATES = ("risk", "return", "compliance")


# --------------------------------------------------------------------------------------------- #
# storage — best-effort, exactly like the watchlist: a broken file must never take the app down
# --------------------------------------------------------------------------------------------- #

def load_all() -> List[Dict[str, Any]]:
    """Every client on the book. A missing or corrupt store yields an empty roster, never raises."""
    try:
        with open(STORE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("clients") if isinstance(data, dict) else data
    return [c for c in (rows or []) if isinstance(c, dict) and c.get("client_id")]


def save_all(clients: List[Dict[str, Any]]) -> bool:
    try:
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as fh:
            json.dump({
                "_origin": "fictional",
                "_note": ("FICTIONAL institutional accounts for demonstration. No real client, "
                          "holding or contact detail appears in this file."),
                "clients": clients,
            }, fh, indent=1, sort_keys=True)
        return True
    except OSError:
        return False


def get(client_id: str) -> Optional[Dict[str, Any]]:
    return next((c for c in load_all() if c.get("client_id") == client_id), None)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s[:40] or "client"


def upsert(client: Dict[str, Any]) -> Dict[str, Any]:
    """Add or replace one client. Returns the stored record."""
    client = dict(client or {})
    client.setdefault("client_id", slug(client.get("name", "")))
    client.setdefault("_origin", "fictional")
    client.setdefault("coverage", [])
    client.setdefault("meetings", [])
    rows = load_all()
    for i, existing in enumerate(rows):
        if existing.get("client_id") == client["client_id"]:
            # Meetings are append-only history; an edit to the profile must never silently drop it.
            client["meetings"] = client.get("meetings") or existing.get("meetings") or []
            rows[i] = client
            break
    else:
        rows.append(client)
    save_all(rows)
    return client


def remove(client_id: str) -> bool:
    rows = load_all()
    kept = [c for c in rows if c.get("client_id") != client_id]
    if len(kept) == len(rows):
        return False
    save_all(kept)
    return True


# --------------------------------------------------------------------------------------------- #
# snapshots and the delta — both PURE (no clock, no store), so they are trivially testable
# --------------------------------------------------------------------------------------------- #

def snapshot_for(run: Dict[str, Any], tickers) -> Dict[str, Dict[str, Any]]:
    """The state of this client's names in this run — what they were shown, and nothing else."""
    want = set(tickers or [])
    out = {}
    for rec in (run or {}).get("records", []):
        cid = rec.get("company_id")
        if cid in want:
            out[cid] = {k: rec.get(k) for k in SNAP_FIELDS}
            out[cid]["company"] = rec.get("company", "")
    return out


def last_meeting(client: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    meetings = [m for m in (client or {}).get("meetings") or [] if m.get("date")]
    return sorted(meetings, key=lambda m: m["date"])[-1] if meetings else None


def _move(before, after):
    if before is None or after is None:
        return None
    return round(float(after) - float(before), 6)


def delta(client: Dict[str, Any], run: Dict[str, Any]) -> Dict[str, Any]:
    """What changed for this client's names since their last meeting.

    Returns `{has_baseline, since, since_run, current_run, changes, unchanged, new_names, dropped}`.
    `changes` is ordered by materiality: a crossed quadrant boundary first, then confidence, then
    new evidence, then momentum. A first meeting has NO baseline and says so — inventing one by
    diffing against zero would report every position as a dramatic move on the day you met them.
    """
    coverage = list((client or {}).get("coverage") or [])
    current = snapshot_for(run, coverage)
    prev = last_meeting(client)
    base = dict((prev or {}).get("snapshot") or {})

    out = {
        "has_baseline": bool(base),
        "since": (prev or {}).get("date", ""),
        "since_run": (prev or {}).get("run_id", ""),
        "current_run": (run or {}).get("run_id", ""),
        "as_of": (run or {}).get("as_of", ""),
        "changes": [],
        "unchanged": 0,
        "new_names": [c for c in current if c not in base] if base else [],
        "dropped": [c for c in base if c not in current],
        "covered": len(coverage),
    }
    if not base:
        out["note"] = ("First meeting on record — there is no prior snapshot to diff against, so "
                       "this brief is the opening view rather than a change report.")
        return out

    for cid, now in current.items():
        was = base.get(cid)
        if not was:
            continue
        name = now.get("company") or cid
        d_conf = _move(was.get("composite_confidence"), now.get("composite_confidence"))
        d_mom = _move(was.get("composite_momentum"), now.get("composite_momentum"))
        d_sig = _move(was.get("signal_count"), now.get("signal_count"))
        moved_label = was.get("label") != now.get("label")

        if not moved_label and (d_conf is None or abs(d_conf) < EPS_CONFIDENCE) \
                and (d_mom is None or abs(d_mom) < EPS_MOMENTUM) and not d_sig:
            out["unchanged"] += 1
            continue

        if moved_label:
            kind, rank = "label_move", 0
            note = "%s → %s" % (was.get("label_display") or was.get("label"),
                                now.get("label_display") or now.get("label"))
            if d_sig:
                note += " on %+d signal%s" % (d_sig, "" if abs(d_sig) == 1 else "s")
        elif d_conf is not None and abs(d_conf) >= EPS_CONFIDENCE:
            kind, rank = "confidence_move", 1
            note = "confidence %.2f → %.2f" % (was.get("composite_confidence") or 0.0,
                                               now.get("composite_confidence") or 0.0)
        elif d_sig:
            kind, rank = "evidence_added", 2
            note = "%+d dated signal%s" % (d_sig, "" if abs(d_sig) == 1 else "s")
        else:
            kind, rank = "momentum_move", 3
            note = "momentum %+.3f → %+.3f" % (was.get("composite_momentum") or 0.0,
                                               now.get("composite_momentum") or 0.0)

        out["changes"].append({
            "company_id": cid, "company": name, "kind": kind, "_rank": rank, "note": note,
            "label_from": was.get("label"), "label_to": now.get("label"),
            "label_from_display": was.get("label_display"), "label_to_display": now.get("label_display"),
            "confidence_from": was.get("composite_confidence"), "confidence_to": now.get("composite_confidence"),
            "confidence_delta": d_conf,
            "momentum_from": was.get("composite_momentum"), "momentum_to": now.get("composite_momentum"),
            "momentum_delta": d_mom,
            "signals_from": was.get("signal_count"), "signals_to": now.get("signal_count"),
            "signals_delta": d_sig,
        })

    out["changes"].sort(key=lambda c: (c["_rank"], -abs(c.get("confidence_delta") or 0)))
    for c in out["changes"]:
        c.pop("_rank", None)
    return out


def close_meeting(client_id: str, run: Dict[str, Any], date: str, note: str = "",
                  discussed=None, follow_ups=None) -> Optional[Dict[str, Any]]:
    """Record a meeting: the snapshot the client was shown, plus what we committed to follow up.

    `date` is supplied by the caller rather than read from a clock, so a replayed or back-dated
    meeting records the date it actually happened.
    """
    client = get(client_id)
    if not client:
        return None
    meeting = {
        "date": date,
        "run_id": (run or {}).get("run_id", ""),
        "as_of": (run or {}).get("as_of", ""),
        "note": note or "",
        "discussed": list(discussed or []),
        "follow_ups": [{"text": f, "done": False} if isinstance(f, str) else dict(f)
                       for f in (follow_ups or [])],
        "snapshot": snapshot_for(run, client.get("coverage") or []),
    }
    client["meetings"] = [m for m in (client.get("meetings") or []) if m.get("date") != date]
    client["meetings"].append(meeting)
    client["meetings"].sort(key=lambda m: m.get("date") or "")
    upsert(client)
    return meeting


def open_follow_ups(client: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Everything still owed to this client, newest meeting first — the other half of the delta."""
    out = []
    for m in sorted((client or {}).get("meetings") or [], key=lambda m: m.get("date") or "",
                    reverse=True):
        for f in m.get("follow_ups") or []:
            if not f.get("done"):
                out.append({"text": f.get("text", ""), "since": m.get("date", "")})
    return out


def summary(client: Dict[str, Any]) -> Dict[str, Any]:
    """The roster row — enough to choose a client without loading their whole history."""
    prev = last_meeting(client)
    return {
        "client_id": client.get("client_id", ""),
        "name": client.get("name", ""),
        "account_type": client.get("account_type", ""),
        "desk": client.get("desk", ""),
        "mandate": client.get("mandate", ""),
        "profile": client.get("profile") or {},
        "coverage": list(client.get("coverage") or []),
        "coverage_n": len(client.get("coverage") or []),
        "last_met": (prev or {}).get("date", ""),
        "meetings_n": len(client.get("meetings") or []),
        "open_follow_ups": len(open_follow_ups(client)),
        "_origin": client.get("_origin", "fictional"),
    }


if __name__ == "__main__":                                   # pragma: no cover - developer CLI
    import company_metadata
    import engine
    import harvest
    import universe

    cons = harvest.apply_overlay(universe.constituents())
    run = engine.run_engine(cons, metadata=company_metadata.load(demo=False))
    print("run %s · as_of %s\n" % (run["run_id"], run["as_of"]))
    for c in load_all():
        s = summary(c)
        print("  %-34s %-12s %2d names · last met %s · %d open" % (
            s["name"], s["account_type"], s["coverage_n"], s["last_met"] or "never",
            s["open_follow_ups"]))
        d = delta(c, run)
        if not d["has_baseline"]:
            print("       %s" % d.get("note", ""))
        for ch in d["changes"][:4]:
            print("       %-26s %s" % (ch["company"][:26], ch["note"]))
        print()
