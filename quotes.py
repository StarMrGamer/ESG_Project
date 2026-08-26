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
import csv
import json
import os
import time

import core

#: Resolved exchange symbols, built ONCE by `scripts/resolve_market_symbols.py` and audited as a
#: file. See the note above `change_90d` for why this is a column and not a runtime name search.
SYMBOLS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                           "market_symbols.csv")
_SYMBOLS = None

#: A dated SNAPSHOT of the basket's prices, written by `python quotes.py --snapshot`.
#:
#: The demo runs off this, not off the network. A price strip is context, not evidence, and it is
#: not worth one flaky hop between a judge and a working screen — the same reasoning that keeps
#: the setup flow local. The snapshot is authoritative for names it holds; anything else (an
#: uploaded or live-built company) still tries the network and still degrades to "unavailable".
#:
#: It is never passed off as a live tick: every payload it serves carries `captured` and
#: `live: False`, and the card prints the date. A stored price shown as current would be a
#: rule-3 breach — label data by origin — for the sake of looking fresher than it is.
PRICES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                           "market_prices.json")
_PRICES = None

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
    "HOSE": "Vietnamese listings are not covered by this source",
}

#: The Philippine exchange, from a PSE-NATIVE source.
#:
#: The main source has no PSE line at all: searching Ayala there returns AYYLF and AYALY on OTC
#: Markets, and BDO returns BDOUY — US over-the-counter ADRs, a different security in a different
#: currency with different liquidity. Showing one under the local ticker would be a quiet
#: substitution, so for months these seven simply said "unavailable". That was the right call
#: given what we had; it was not the right end state.
#:
#: This is the PSE's own board in PHP. One request returns all 389 listed companies, so covering
#: our seven costs a single call, and the payload carries the company NAME — which is what makes
#: it safe to use: the name is read back and compared to ours before a price is shown, exactly as
#: `scripts/resolve_market_symbols.py` does for Singapore and Malaysia.
#:
#: It serves a last price and a day change, NOT a history. So PSE names get a quote and no 90-day
#: strip, and the card says so rather than drawing a line from one point.
PHISIX_ALL = "https://phisix-api2.appspot.com/stocks.json"
_PHISIX = None

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
#: The 90-day window the board's price strip is LABELLED with. Kept separate from CHART
#: on purpose: CHART's 5-day range yields a one-DAY change, and feeding that into a card
#: headed "90 days" would put a real number under a wrong label — the quietest kind of
#: wrong, because nothing on screen looks broken.
CHART_90D = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
             "?range=3mo&interval=1d")

TTL_SECONDS = 300
_CACHE = {}


def _symbols():
    """The resolved-symbol column, loaded once. Missing file -> empty, and every lookup falls
    back to the naive construction, so the module still works with no column at all."""
    global _SYMBOLS
    if _SYMBOLS is None:
        table = {}
        try:
            with open(SYMBOLS_CSV, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    sym = (row.get("symbol") or "").strip()
                    if sym:
                        table[(row.get("ticker") or "").strip()] = sym
        except Exception:                                      # noqa: BLE001 - best-effort
            table = {}
        _SYMBOLS = table
    return _SYMBOLS


def yahoo_symbol(ticker):
    """Our ticker -> the symbol its exchange is actually keyed by.

    The column comes first, because a mnemonic is not a stock code: Singapore keys DBS as
    ``D05`` and Malaysia keys RHB as ``1066``, so ``DBS.SI`` and ``RHBBANK.KL`` simply do not
    exist. Thailand and Indonesia happen to use the mnemonic, which is why 20 of 52 resolved
    before the column existed. A ticker not in the column falls back to the naive construction
    rather than returning nothing — an unknown name is still worth one attempt.
    """
    if not ticker or ":" not in ticker:
        return None
    mapped = _symbols().get(ticker)
    if mapped:
        return mapped
    exchange, _, code = ticker.partition(":")
    suffix = SUFFIX.get(exchange.upper())
    return f"{code}{suffix}" if suffix and code else None


def _norm_name(name):
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _same_company(ours, theirs):
    """Guard: the exchange's own name for this code has to be our company.

    A prefix comparison after stripping punctuation, which is what the real differences look
    like: "SM Investments Corp" against "SM Investments Corporation", "Ayala Land Inc" against
    "Ayala Land, Inc.". Anything that is not one company under two spellings fails.
    """
    a, b = _norm_name(ours), _norm_name(theirs)
    return bool(a and b and (a.startswith(b) or b.startswith(a)))


def _phisix():
    """The PSE board, fetched once per process. Failure is an empty dict, never an exception."""
    global _PHISIX
    if _PHISIX is None:
        try:
            payload = json.loads(core.http_get(PHISIX_ALL, timeout=10))
            _PHISIX = {s["symbol"]: s for s in payload.get("stocks", []) if s.get("symbol")}
        except Exception:                                      # noqa: BLE001 - best-effort
            _PHISIX = {}
    return _PHISIX


def _pse_quote(ticker, company=""):
    """A real PSE last price, or None. Never an ADR standing in for the local line."""
    code = ticker.partition(":")[2].upper()
    row = _phisix().get(code)
    if not row:
        return None
    price = (row.get("price") or {}).get("amount")
    if price is None:
        return None
    # The name check is the whole reason this source is usable. Without it we would be trusting
    # that a three-letter code means the same thing on their board as on ours.
    if company and not _same_company(company, row.get("name", "")):
        return None
    return {
        "ticker": ticker, "available": True, "symbol": code,
        "price": price, "currency": (row.get("price") or {}).get("currency") or "PHP",
        "change_pct": row.get("percentChange"),
        "exchange": "Philippine Stock Exchange",
        "as_of": None, "fifty_two_high": None, "fifty_two_low": None,
        "source": "PSE (phisix)",
        "resolved_name": row.get("name", ""),
        "note": "Last price for context only — not a signal, and no part of the ESG score. "
                "This source carries no history, so there is no 90-day series for PSE names.",
    }


def _prices():
    """The price snapshot, loaded once. Missing or unreadable -> empty, and every lookup falls
    through to the live path, so the module behaves exactly as it did before the file existed."""
    global _PRICES
    if _PRICES is None:
        try:
            with open(PRICES_JSON, encoding="utf-8") as fh:
                _PRICES = json.load(fh)
        except Exception:                                      # noqa: BLE001 - best-effort
            _PRICES = {}
    return _PRICES


def gap_reason(ticker):
    """The documented reason this exchange carries no quote, if it is a known gap."""
    exchange = (ticker or "").partition(":")[0].upper()
    return KNOWN_GAPS.get(exchange)


def _unavailable(ticker, reason):
    return {"ticker": ticker, "available": False, "reason": reason}


def quote(ticker, *, demo=False, ttl=TTL_SECONDS, company=""):
    """The latest quote for one ticker. Always returns a dict; never raises.

    `company` is our name for it, used to verify the PSE source is quoting the same company.
    """
    if demo:
        return _unavailable(ticker, "demo universe — these companies are fictional, so there is "
                                    "no market price and none is invented")
    stored = (_prices().get("quotes") or {}).get(ticker)
    if stored:
        return dict(stored)

    if (ticker or "").partition(":")[0].upper() == "PSE":
        got = _pse_quote(ticker, company)
        return got or _unavailable(
            ticker, "no Philippine Stock Exchange line for this code under a matching name")

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


#: MEASURED coverage on the real basket: 20 of 52 before the symbol column (2026-08-24),
#: 43 of 52 after it (2026-08-25). The 23 it recovered were Singapore and Malaysia, where the
#: exchange's own code is not the mnemonic our basket carries — DBS is D05, RHB is 1066, so
#: "DBS.SI" and "RHBBANK.KL" simply do not exist. Of the 9 still unresolved, 7 are Philippine
#: (see KNOWN_GAPS) and 2 are the DELISTED constituents, which correctly have no live price.
#:
#: The gap was NOT closed with a runtime name search. Resolving "CIMB Group Holdings Bhd"
#: through a search endpoint and taking the first hit is precisely how Malaysia Airports rendered
#: I-Bhd's data under Malaysia Airports' name — a failure that looked completely normal on
#: screen, which is what made it dangerous. It was closed with a real column,
#: `data/market_symbols.csv`, resolved once by `scripts/resolve_market_symbols.py` under three
#: conditions a runtime lookup could not enforce: every symbol must PRICE, in a currency, as an
#: instrumentType of EQUITY; the name the exchange files it under is read back and compared to
#: ours; and that name is written into the CSV so all 43 rows can be audited by eye. That equity
#: check is not paperwork — without it the resolver accepted the "Lion-OCBC Securities APAC
#: Financials Dividend Plus ETF" as OCBC, and a MUTUALFUND quoting 24,086,968,300 as Axiata.
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
    stored = (_prices().get("series") or {}).get(ticker)
    if stored:
        return dict(stored)
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


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import argparse
    import universe

    ap = argparse.ArgumentParser(description="Fetch live quotes for the real ASEAN universe.")
    ap.add_argument("tickers", nargs="*", help="e.g. SGX:D05 KLSE:1155 (default: a sample)")
    ap.add_argument("--snapshot", action="store_true",
                    help="fetch the whole basket ONCE and write data/market_prices.json, so the "
                         "app needs no network at all")
    a = ap.parse_args()

    if a.snapshot:
        import datetime
        # Bypass the stored file while building it, or a snapshot would only ever re-copy itself.
        _PRICES = {}
        cons = universe.load_universe(universe.UNIVERSE_FILE)["constituents"]
        today = datetime.date.today().isoformat()
        snap = {"as_of": today, "source": "Yahoo Finance",
                "note": "A DATED SNAPSHOT, not a live tick. Context only — never an input to any "
                        "score. Refresh with `python quotes.py --snapshot`.",
                "quotes": {}, "series": {}}
        for c in cons:
            tk = c["ticker"]
            _PRICES = {}
            q = quote(tk, company=c.get("company", ""))
            if q.get("available"):
                q["captured"], q["live"] = today, False
                snap["quotes"][tk] = q
            _PRICES = {}
            s90 = change_90d(tk)
            if s90:
                s90["captured"], s90["live"] = today, False
                snap["series"][tk] = s90
            print(f"  {tk:<14} {'quote ok' if q.get('available') else 'no quote':<9} "
                  f"{'90d ok' if s90 else 'no 90d'}")
        with open(PRICES_JSON, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=1, sort_keys=True)
        print(f"\nwrote {PRICES_JSON} — {len(snap['quotes'])} quotes, "
              f"{len(snap['series'])} 90-day series, as of {today}")
        raise SystemExit(0)

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
