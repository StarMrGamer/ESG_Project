"""Financial price momentum — the SECOND axis, drawn BESIDE the ESG read and never inside it.

Why this exists: the product's whole claim is that a stale rating misses live evidence. The fair
question back is "and what has the market already done about it?" — a company whose price has run
hard may have priced in exactly the improvement we are pointing at, and a company whose price is
running while our evidence deteriorates is a different and more interesting shape. Neither of
those is answerable from the ESG side alone.

WHAT IT IS: the classical cross-sectional momentum factor (Jegadeesh & Titman 1993; the `UMD`
/ `MOM` factor Fama & French carry alongside the three-factor model) — the cumulative return over
the twelve months ending ONE MONTH AGO. The skipped month is not a rounding convenience: the
one-month reversal is a documented, opposite-signed effect, and a 12-month window that includes it
measures two things at once. Written `12-1` throughout, which is what the literature calls it.

WHAT IT IS NOT, and this is the load-bearing part:

  * **It is not an input to any score.** `engine.py` and `signals.py` cannot reach this module and
    `selftest.py` pins that they never will. `composite_momentum` stays a consensus over dated
    documentary evidence and `disagreement` stays our percentile minus the rating's. Folding a
    price term into either would end the project exactly as folding an earnings term would (see
    the note above `financials.py`): nobody, including us, could say what +0.6 was claiming.
  * **It is not a recommendation.** A positive reading is not a reason to buy and a negative one
    is not a reason to sell. It is one of two directions, reported next to each other.
  * **It is not fetched at render time.** The serving path reads a dated SNAPSHOT
    (`data/price_momentum.json`, written by `python price_momentum.py --snapshot`), so the board
    needs no network and the same file always produces the same reading. Every payload carries
    `captured` and the card prints it — a stored price shown as current would be a rule-3 breach
    for the sake of looking fresher than it is.
  * **The FICTIONAL demo universe gets nothing.** Inventing a price history for a company that
    does not exist is precisely the fabrication rule 2 forbids, and a plausible 12-month return
    beside a made-up name is the most dangerous kind.

Symbols come from `quotes.py`'s audited `data/market_symbols.csv` — resolved once, name-checked
against ours, equity-checked. They are NOT re-resolved here by name search: doing that is how
Malaysia Airports rendered I-Bhd's data under Malaysia Airports' name.
"""
import json
import os

import core
import quotes

#: Repo root — this module lives at the root, so `data/` is a sibling.
_ROOT = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_JSON = os.path.join(_ROOT, "data", "price_momentum.json")

#: The factor's name, printed wherever the number is, so nobody has to guess the convention.
WINDOW = "12-1"
WINDOW_LABEL = "12-month price return, skipping the most recent month (12-1 momentum factor)"

#: Two years of monthly bars. We need 13 COMPLETE closes to span t-12 -> t-1, and asking for
#: exactly 13 leaves no room for the partial current month or a missing bar.
CHART_2Y = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            "?range=2y&interval=1mo")

#: Monthly closes needed for one reading: c[-12] and c[-1] after the in-progress month is dropped.
MIN_MONTHS = 13

_SNAP = None


# --------------------------------------------------------------------------- #
#  ALIGNMENT — the two directions read together
# --------------------------------------------------------------------------- #
#: The four combinations of two signed directions, plus the two honest non-answers.
#:
#: `unknown` is NOT `flat` and neither is a quadrant. A company with no scorable evidence sits at
#: exactly composite_momentum 0.000 — 28 of the verified 52 did before the harvest — and calling
#: that "divergence" would manufacture a finding out of an absence. Same discipline as
#: `traction.py`: an unrun test is not a failed one.
ALIGNMENT = {
    "aligned": {
        "display": "Aligned",
        "short": "Aligned",
        "tone": "good",
        "rule": "price momentum > 0 AND ESG evidence momentum > 0",
        "tooltip": ("The market and our evidence are pointing the same way: the price has risen "
                    "over the 12-1 window and the dated evidence is improving. Agreement, not a "
                    "recommendation — and it says nothing about what is already priced in."),
    },
    "downside_trap": {
        "display": "Divergence — downside risk",
        "short": "Divergence",
        "tone": "bad",
        "rule": "price momentum > 0 AND ESG evidence momentum < 0",
        "tooltip": ("The price has risen while our dated evidence deteriorates. This is the shape "
                    "a static rating cannot see and the one the product exists to surface — the "
                    "People/Planet side is going backwards while the market is not marking it."),
    },
    "evidence_ahead": {
        "display": "Divergence — evidence ahead",
        "short": "Evidence ahead",
        "tone": "warn",
        "rule": "price momentum < 0 AND ESG evidence momentum > 0",
        "tooltip": ("Our evidence is improving while the price has fallen over the window. The "
                    "mirror of the trap, and the reason this is not a ranking: it is a "
                    "disagreement with the market, exactly as the matrix is a disagreement with "
                    "the rating."),
    },
    "both_falling": {
        "display": "Both deteriorating",
        "short": "Both down",
        "tone": "bad",
        "rule": "price momentum < 0 AND ESG evidence momentum < 0",
        "tooltip": "Price and evidence are both negative over their respective windows.",
    },
    "flat": {
        "display": "No divergence to read",
        "short": "Flat",
        "tone": "muted",
        "rule": "either reading is exactly zero",
        "tooltip": "One of the two readings is flat, so there is no direction to compare.",
    },
    "unknown": {
        "display": "Not comparable",
        "short": "Unknown",
        "tone": "muted",
        "rule": "no quotable listing, or no scorable ESG evidence for this company",
        "tooltip": ("One of the two directions is missing — either the listing is not quotable "
                    "from our audited symbol column, or the company has no scorable evidence "
                    "yet. An absence of evidence is a finding, not a divergence."),
    },
}


def align(price_pct, esg_momentum, signal_count=None):
    """Read the two directions together. Returns one key of `ALIGNMENT`. Pure.

    `signal_count` is consulted because a company with NO evidence scores composite_momentum
    0.000 — which is the same number as "the evidence says flat" and a completely different
    claim. Zero signals is `unknown`, never a divergence.
    """
    if price_pct is None or esg_momentum is None:
        return "unknown"
    if signal_count is not None and signal_count <= 0:
        return "unknown"
    if price_pct == 0 or esg_momentum == 0:
        return "flat"
    if price_pct > 0:
        return "aligned" if esg_momentum > 0 else "downside_trap"
    return "evidence_ahead" if esg_momentum > 0 else "both_falling"


# --------------------------------------------------------------------------- #
#  THE SNAPSHOT
# --------------------------------------------------------------------------- #
def _snapshot():
    """The dated snapshot, loaded once. Missing or unreadable -> empty, and every lookup returns
    None, so the board renders "not quotable" rather than failing."""
    global _SNAP
    if _SNAP is None:
        try:
            with open(SNAPSHOT_JSON, encoding="utf-8") as fh:
                _SNAP = json.load(fh)
        except Exception:                                      # noqa: BLE001 - best-effort
            _SNAP = {}
    return _SNAP


def captured():
    """The date the snapshot was taken, or '' — printed wherever a reading is shown."""
    return (_snapshot() or {}).get("captured", "")


def momentum(ticker, *, demo=False):
    """The 12-1 price momentum for one ticker, or None.

    None — never a zero — when the window cannot be sourced, so the card says "not quotable"
    rather than drawing a flat reading that reads as "the price did not move".
    """
    if demo:
        return None
    row = ((_snapshot() or {}).get("momentum") or {}).get(ticker)
    return dict(row) if row else None


def compute(closes, timestamps=None):
    """12-1 momentum from monthly closes, or None. Pure — no clock, no network.

    `closes` is oldest-first monthly closes. The FINAL bar is dropped unconditionally: a request
    made mid-month returns an in-progress bar, and a partial month is not a month. That also IS
    the factor's skipped month, so what remains spans t-12 to t-1.
    """
    clean, stamps = [], []
    for i, c in enumerate(closes or []):
        if isinstance(c, (int, float)):
            clean.append(float(c))
            stamps.append((timestamps or [])[i] if timestamps and i < len(timestamps) else None)
    if len(clean) < MIN_MONTHS + 1:
        return None
    # Drop the in-progress month. What is left ends at t-1, which is where the factor ends.
    clean, stamps = clean[:-1], stamps[:-1]
    start, end = clean[-MIN_MONTHS], clean[-1]
    if not start:
        return None
    return {
        "pct": round((end - start) / start * 100, 2),
        "window": WINDOW,
        "months": MIN_MONTHS - 1,
        "source": "Yahoo Finance",
        "start_ts": stamps[-MIN_MONTHS],
        "end_ts": stamps[-1],
    }


def fetch(ticker):     # pragma: no cover - network path, exercised by --snapshot only
    """Fetch and compute one reading LIVE. Only the snapshot builder calls this."""
    symbol = quotes.yahoo_symbol(ticker)
    if not symbol:
        return None
    try:
        raw = core.http_get(CHART_2Y.format(symbol=symbol), timeout=10)
        result = json.loads(raw)["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        stamps = result.get("timestamp")
    except Exception:                       # noqa: BLE001 - best-effort by contract (rule 1)
        return None
    out = compute(closes, stamps)
    if out:
        out["symbol"] = symbol
    return out


# --------------------------------------------------------------------------- #
#  THE BOARD READ
# --------------------------------------------------------------------------- #
#: WHY a row is `unknown`, in the reader's terms rather than ours.
#:
#: Three different absences land on the same key, and giving the wrong one is worse than giving
#: none: on the FICTIONAL demo universe the honest answer is "this company does not exist", and
#: blaming our symbol column instead quietly implies the company is real and we merely failed to
#: look it up.
DEMO_REASON = ("These companies are fictional, so there is no market price and none is invented "
               "(HARD RULE 2). Switch Demo off for the real basket, where 43 of 52 resolve.")
NO_QUOTE_REASON = ("No quotable listing for this company in our audited symbol column, so there "
                   "is no second direction to compare. Seven Philippine names and the two "
                   "delisted constituents sit here.")
NO_EVIDENCE_REASON = ("No scorable evidence for this company yet, so there is no ESG direction "
                      "to compare. An absence of evidence is a finding, not a divergence.")


def why_unknown(price_pct, signal_count, *, demo=False):
    """The reason this pair cannot be read, or '' when it can. Pure."""
    if demo:
        return DEMO_REASON
    if price_pct is None:
        return NO_QUOTE_REASON
    if not signal_count:
        return NO_EVIDENCE_REASON
    return ""


def read(records, *, demo=False):
    """The dual-momentum read for a whole run.

    `records` is `{company_id: engine record}`. Returns `{"rows": {...}, "counts": {...}}` where
    every row carries BOTH directions, the alignment key and — when the pair cannot be read — the
    reason WHY, which differs by universe. The counts are exactly what the banner states:
    measured off this run and this dated snapshot, never a remembered statistic.
    """
    rows, counts = {}, {k: 0 for k in ALIGNMENT}
    quotable = 0
    for cid, rec in (records or {}).items():
        px = momentum(cid, demo=demo)
        esg = rec.get("composite_momentum")
        pct = (px or {}).get("pct")
        signals = rec.get("signal_count", 0)
        key = align(pct, esg, signals)
        if px:
            quotable += 1
        counts[key] += 1
        rows[cid] = {
            "price_pct": pct,
            "price_window": WINDOW,
            "esg_momentum": esg,
            "signal_count": signals,
            "alignment": key,
            "display": ALIGNMENT[key]["display"],
            "tone": ALIGNMENT[key]["tone"],
            "why": why_unknown(pct, signals, demo=demo) if key == "unknown" else "",
        }
    return {
        "rows": rows,
        "counts": counts,
        "quotable": quotable,
        "total": len(records or {}),
        "captured": captured(),
        "demo": bool(demo),
        "window": WINDOW,
        "window_label": WINDOW_LABEL,
        "alignment": ALIGNMENT,
        "note": ("Price momentum is context beside the ESG read, never inside it — no part of "
                 "this reaches composite_momentum, disagreement or any quadrant label."),
        # The banner needs one line for the case where NOTHING is readable, or it reports a row
        # of zeros with no explanation — which reads as a broken panel rather than a demo.
        "unavailable": DEMO_REASON if demo else "",
    }


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import argparse
    import datetime

    import universe

    ap = argparse.ArgumentParser(description="12-1 price momentum for the real ASEAN basket.")
    ap.add_argument("--snapshot", action="store_true",
                    help="fetch the whole basket ONCE and write data/price_momentum.json")
    a = ap.parse_args()

    cons = universe.load_universe(universe.UNIVERSE_FILE)["constituents"]
    if a.snapshot:
        today = datetime.date.today().isoformat()
        out, misses = {}, []
        for c in cons:
            tk = c["ticker"]
            got = fetch(tk)
            if got:
                got["captured"] = today
                got["live"] = False
                out[tk] = got
                print(f"  {tk:14} {got['pct']:>8.2f}%  {got['symbol']}")
            else:
                misses.append(tk)
                print(f"  {tk:14}    ----   no {WINDOW} window")
        payload = {
            "captured": today,
            "window": WINDOW,
            "window_label": WINDOW_LABEL,
            "source": "Yahoo Finance",
            "note": ("A DATED SNAPSHOT, not a live tick. Context beside the ESG read and never "
                     "an input to it — see the module docstring."),
            "momentum": out,
        }
        with open(SNAPSHOT_JSON, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"\n{len(out)} of {len(cons)} resolved -> {SNAPSHOT_JSON}")
        if misses:
            print(f"no window for: {', '.join(misses)}")
    else:
        for c in cons[:8]:
            got = momentum(c["ticker"])
            print(f"  {c['ticker']:14} {got['pct'] if got else '----'}")
