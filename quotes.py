"""Live market quotes — a thin, best-effort strip beside the ESG read.

Why this exists: the radar competes with a stale ESG rating, and the obvious next question from
anyone watching is "so what is the stock doing?". Until now the only price on screen was the
illustrative demo series, which cannot answer that. This fetches a real last price.

What it is NOT: a price feed, a chart, a signal, or an input to any score. Nothing in the engine
reads this module — a quote never moves momentum, a quadrant or a tier. It is context for the
reader, kept deliberately at arm's length from the analysis so that a market move can never be
mistaken for ESG evidence.

Rules it obeys:
  * all outbound HTTP goes through ``core.http_get`` (rule 1, I/O isolation);
  * failure degrades to "unavailable" with a reason — never an exception, never a blocked demo;
  * the FICTIONAL demo universe gets no quotes at all. Inventing a price for a company that does
    not exist is exactly the fabrication rule 2 forbids, and a plausible-looking number next to a
    made-up name is the most dangerous kind.
"""
import json
import time

import core

# Our tickers are ``EXCHANGE:CODE``; Yahoo wants ``CODE.SUFFIX``. Only these five map — every
# ASEAN listing in the real universe is on one of them, and an unknown prefix returns no quote
# rather than a guessed suffix.
SUFFIX = {
    "SGX": ".SI",    # Singapore Exchange
    "KLSE": ".KL",   # Bursa Malaysia
    "IDX": ".JK",    # Indonesia Stock Exchange
    "SET": ".BK",    # Stock Exchange of Thailand
}

# Exchanges we deliberately do not quote, and why. The Philippine case is the instructive one:
# the ``.PS`` symbols resolve but carry no price, and the only Yahoo instruments for these
# issuers are US over-the-counter ADRs (AYYLF, AYALY). An ADR is a different security in a
# different currency with different liquidity, so showing one under the local ticker would be a
# quiet substitution — the reader would think they were looking at the PSE line. Better to say
# there is no quote.
KNOWN_GAPS = {
    "PSE": "no Philippine Stock Exchange price from this source — the only instruments available "
           "are US OTC ADRs, which are a different security and are not shown in their place",
    "HOSE": "Vietnamese listings are not covered by this source",
}

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
#: The 90-day window the board's price strip is LABELLED with. Kept separate from CHART
#: on purpose: CHART's 5-day range yields a one-DAY change, and feeding that into a card
#: headed "90 days" would put a real number under a wrong label — the quietest kind of
#: wrong, because nothing on screen looks broken.
CHART_90D = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
             "?range=3mo&interval=1d")

TTL_SECONDS = 300
_CACHE = {}


def yahoo_symbol(ticker):
    """``SGX:D05`` -> ``D05.SI``. None when the exchange is not one we can map."""
    if not ticker or ":" not in ticker:
        return None
    exchange, _, code = ticker.partition(":")
    suffix = SUFFIX.get(exchange.upper())
    return f"{code}{suffix}" if suffix and code else None


def gap_reason(ticker):
    """The documented reason this exchange carries no quote, if it is a known gap."""
    exchange = (ticker or "").partition(":")[0].upper()
    return KNOWN_GAPS.get(exchange)


def _unavailable(ticker, reason):
    return {"ticker": ticker, "available": False, "reason": reason}


def quote(ticker, *, demo=False, ttl=TTL_SECONDS):
    """The latest quote for one ticker. Always returns a dict; never raises."""
    if demo:
        return _unavailable(ticker, "demo universe — these companies are fictional, so there is "
                                    "no market price and none is invented")
    symbol = yahoo_symbol(ticker)
    if not symbol:
        return _unavailable(ticker, gap_reason(ticker) or "no exchange mapping for this ticker")

    hit = _CACHE.get(symbol)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]

    try:
        raw = core.http_get(CHART.format(symbol=symbol), timeout=6)
        payload = json.loads(raw)
        meta = payload["chart"]["result"][0]["meta"]
    except Exception as e:  # noqa: BLE001 — best-effort by contract (rule 1)
        # "FetchError" tells a reader nothing. The common case by far is a symbol that does not
        # exist — an uploaded or live-built company that is not listed under the ticker we
        # derived — and that deserves to be said plainly rather than dressed as an outage.
        text = str(e)
        if "404" in text or "Not Found" in text:
            reason = f"no listing found for {symbol} on this source"
        elif isinstance(e, (KeyError, IndexError, TypeError, ValueError)):
            reason = f"no usable quote data returned for {symbol}"
        else:
            reason = f"quote lookup failed for {symbol} — the source was unreachable"
        return _unavailable(ticker, reason)

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return _unavailable(ticker, "no price in the response")

    change_pct = None
    if prev:
        try:
            change_pct = round((price - prev) / prev * 100, 2)
        except ZeroDivisionError:
            change_pct = None

    out = {
        "ticker": ticker, "available": True, "symbol": symbol,
        "price": price, "currency": meta.get("currency") or "",
        "change_pct": change_pct,
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        "as_of": meta.get("regularMarketTime"),
        "fifty_two_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_low": meta.get("fiftyTwoWeekLow"),
        "source": "Yahoo Finance",
        "note": "Last price for context only — not a signal, and no part of the ESG score.",
    }
    _CACHE[symbol] = (time.time(), out)
    return out


def quotes(tickers, *, demo=False):
    """Batch helper. Sequential on purpose: a handful of names, and politeness beats speed."""
    return {t: quote(t, demo=demo) for t in tickers}


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import argparse
    import universe

    ap = argparse.ArgumentParser(description="Fetch live quotes for the real ASEAN universe.")
    ap.add_argument("tickers", nargs="*", help="e.g. SGX:D05 KLSE:1155 (default: a sample)")
    a = ap.parse_args()

    picks = a.tickers
    if not picks:
        cons = universe.load_universe(universe.UNIVERSE_FILE)["constituents"]
        seen, picks = set(), []
        for c in cons:  # one per exchange, so every suffix mapping gets exercised
            ex = c["ticker"].split(":")[0]
            if ex not in seen:
                seen.add(ex)
                picks.append(c["ticker"])

    for t in picks:
        q = quote(t)
        if q["available"]:
            chg = f"{q['change_pct']:+.2f}%" if q["change_pct"] is not None else "—"
            print(f"{t:<12} {q['symbol']:<12} {q['price']:>10,.2f} {q['currency']:<4} "
                  f"{chg:>8}  {q['exchange']}")
        else:
            print(f"{t:<12} {'—':<12} {'unavailable':>10}  {q['reason']}")


#: MEASURED coverage on the real basket (2026-08-24): 20 of 52 resolve, 25 are mapped but not
#: found, 7 are on an exchange we do not map at all. The 25 are almost all Bursa: Yahoo keys
#: Malaysian listings by their NUMERIC stock code ("1023.KL" for CIMB) and the basket carries only
#: "CIMB MK" and the RIC "CIMB.KL", neither of which resolves.
#:
#: Do NOT close that gap with a name search. Resolving "CIMB Group Holdings Bhd" through a search
#: endpoint and taking the first hit is precisely how Malaysia Airports rendered I-Bhd's data
#: under Malaysia Airports' name — a failure that looked completely normal on screen, which is
#: what made it dangerous. A price for the wrong company is worse than no price. Close it with a
#: real numeric-code column in the basket, or leave the card saying "unavailable".
def change_90d(ticker, *, demo=False, ttl=TTL_SECONDS):
    """Percent change over ~90 days plus a rebased series for the strip, or None.

    Returns `{"pct": float, "series": [float, ...], "points": int, "source": str}` where the
    series is rebased to 100 at the start of the window, matching what the demo strip draws.
    Returns None — never a partial or a zero — when the window cannot be sourced, so the card
    says "unavailable" rather than drawing a flat line that reads as "the price did not move".

    Same contract as `quote`: context only. Nothing in the engine reads this, a price never
    enters a score, and the FICTIONAL demo universe gets no quote at all.
    """
    if demo:
        return None
    symbol = yahoo_symbol(ticker)
    if not symbol:
        return None
    key = f"90d:{symbol}"
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    try:
        raw = core.http_get(CHART_90D.format(symbol=symbol), timeout=8)
        result = json.loads(raw)["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:                       # noqa: BLE001 - best-effort by contract (rule 1)
        return None
    # Yahoo returns null for non-trading days inside the range; dropping them is right, but a
    # window that is mostly holes is not a 90-day read and should not claim to be one.
    closes = [c for c in (closes or []) if isinstance(c, (int, float))]
    if len(closes) < 20 or not closes[0]:
        return None
    first, last = closes[0], closes[-1]
    out = {
        "pct": round((last - first) / first * 100, 2),
        "series": [round(c / first * 100, 2) for c in closes],
        "points": len(closes),
        "source": "Yahoo Finance",
    }
    _CACHE[key] = (time.time(), out)
    return out
