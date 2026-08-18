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
