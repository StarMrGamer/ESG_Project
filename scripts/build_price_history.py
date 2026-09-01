"""Monthly close history for the basket -> data/price_history.json.

Why a second price file when `data/price_momentum.json` already exists: that one holds a single
12-1 READING per company, taken on one date. A forecast needs the opposite shape — the price at
many past dates, so a model can be trained on what was knowable at each cutoff and scored against
what actually happened next.

Ten years of monthly closes, from the same source and through the same `core.http_get` as every
other fetch in this repo (rule 1). Written once and committed, so training is reproducible from a
fresh clone with no network and the same file always yields the same model.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core                                                            # noqa: E402
import quotes                                                          # noqa: E402
import universe                                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "price_history.json")
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
         "?range=10y&interval=1mo")


def fetch(ticker):
    """`{"YYYY-MM": close}` for one ticker, or None. Never raises."""
    symbol = quotes.yahoo_symbol(ticker)
    if not symbol:
        return None
    try:
        raw = core.http_get(CHART.format(symbol=symbol), timeout=15)
        result = json.loads(raw)["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        stamps = result.get("timestamp") or []
    except Exception:                       # noqa: BLE001 - best-effort by contract (rule 1)
        return None
    out = {}
    for ts, close in zip(stamps, closes or []):
        if not isinstance(close, (int, float)):
            continue
        month = datetime.date.fromtimestamp(ts).strftime("%Y-%m")
        out[month] = round(float(close), 6)
    return out or None


def main():
    key = sys.argv[sys.argv.index("--universe") + 1] if "--universe" in sys.argv else ""
    cons = universe.constituents(universe.active_file(key=key))
    today = datetime.date.today().isoformat()
    # Merge, never replace: a price series is a fact about a listing, and snapshotting a second
    # universe must not drop the first one's history out from under the frozen model.
    try:
        with open(OUT, encoding="utf-8") as fh:
            series = json.load(fh).get("series") or {}
    except Exception:                                   # noqa: BLE001 - first run
        series = {}
    misses = []
    for c in cons:
        tk = c["ticker"]
        got = fetch(tk)
        if got:
            series[tk] = got
            print(f"  {tk:14} {len(got):>4} months  {min(got)} -> {max(got)}")
        else:
            misses.append(tk)
            print(f"  {tk:14}  ----   no history")
    payload = {
        "captured": today,
        "source": "Yahoo Finance",
        "interval": "1mo",
        "note": ("Monthly closes for TRAINING a forecast, not for display. The board's price "
                 "strip and the 12-1 factor read their own files. Committed so the model "
                 "retrains identically from a fresh clone."),
        "series": series,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\n{len(series)} of {len(cons)} resolved -> {OUT}")
    if misses:
        print(f"no history for: {', '.join(misses)}")


if __name__ == "__main__":
    main()
