"""Resolve each constituent to the symbol its exchange is actually keyed by, ONCE, offline.

Why this is a script and not a runtime lookup: our tickers carry mnemonics (``SGX:DBS``,
``KLSE:RHBBANK``) and the price source keys Singapore and Malaysia by the EXCHANGE's own code
(``D05.SI``, ``1066.KL``). ``quotes.py`` refuses to close that gap with a live name search, and
it is right to — resolving a name through a search endpoint and taking the first hit is exactly
how Malaysia Airports once rendered I-Bhd's data under Malaysia Airports' name.

So the search happens here, once, under three conditions the runtime path could not enforce:

  1. every candidate is CONFIRMED by fetching its own price series and reading back the name the
     exchange files it under — a symbol that does not price, or prices under a different company,
     is discarded rather than written;
  2. the name it resolved to is written into the CSV beside our name, so all 25 rows can be read
     by a human in one sitting. That is the audit;
  3. anything that fails stays BLANK, and the card keeps saying "unavailable". A wrong price is
     worse than no price.

Run:  python -m scripts.resolve_market_symbols            # dry run, prints the table
      python -m scripts.resolve_market_symbols --write    # writes data/market_symbols.csv
"""
import csv
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core
import quotes
import universe

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "market_symbols.csv")
SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0"
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=5d&interval=1d"

#: Legal-form words that carry no identity. Dropped from both sides before matching, so
#: "RHB Bank Bhd" and "RHB Bank Berhad" are the same company and "Bhd" alone is never a match.
NOISE = {"bhd", "berhad", "plc", "pcl", "ltd", "limited", "tbk", "pt", "corp", "corporation",
         "inc", "incorporated", "co", "company", "public", "group", "holdings", "holding",
         "the", "and", "of"}


#: The two the automated matcher cannot judge, decided by hand and still CONFIRMED by the source
#: like every other row — the symbol must price, in a currency, as an EQUITY, and the name the
#: exchange files it under is written into the CSV so the call can be checked in one glance.
#:   SGX:ST  is SingTel, a portmanteau of "Singapore Telecommunications" — no token or acronym
#:           rule reaches it, and the basket's own code (ST) is not the exchange's (Z74).
#:   KLSE:NESZ the search returns nothing for "Nestle (Malaysia)"; 4707 is the Bursa code.
#: Nothing else belongs here. A name the matcher rejects and a human cannot vouch for stays
#: unresolved and the card keeps saying "unavailable".
OVERRIDES = {
    "SGX:ST": ("Z74.SI", "SingTel is Singapore Telecommunications Limited"),
    "KLSE:NESZ": ("4707.KL", "Bursa code for Nestle (Malaysia) Berhad"),
}


def _tokens(name):
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in NOISE]


def _initials(name):
    """Initials over EVERY word, legal form included. OCBC files as "Oversea-Chinese Banking
    Corporation Limited": drop "Corporation" as noise first and the acronym reads "ocb", so the
    bank fails to match its own name."""
    return "".join(t[0] for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t)


def _aligned(a, b):
    """How many of `a`'s words find a partner in `b`, allowing a prefix to stand for a word.
    "Bangkok Dusit Med Service" and "Bangkok Dusit Medical Services" are the same company, and an
    exact-token count scores them at 50%."""
    used, hits = set(), 0
    for x in a:
        for j, y in enumerate(b):
            if j in used:
                continue
            if x == y or (len(x) >= 3 and y.startswith(x)) or (len(y) >= 3 and x.startswith(y)):
                used.add(j)
                hits += 1
                break
    return hits


def matches(ours, theirs):
    """Do these two names denote the same company? Returns (ok, why) — `why` goes in the CSV."""
    a, b = _tokens(ours), _tokens(theirs)
    if not a or not b:
        return False, "no comparable tokens"
    sa, sb = set(a), set(b)
    # A one-word name inside a long one is NOT a match: "OCBC" is a subset of "Lion-OCBC
    # Securities APAC Financials Dividend Plus ETF". Require the longer name to be a name and not
    # a description of a product that merely mentions the company.
    if (sa <= sb or sb <= sa) and abs(len(sa) - len(sb)) <= 2:
        return True, "every distinctive word matches"
    # An acronym is a real name here: OCBC files as "Oversea-Chinese Banking Corporation".
    if len(a) == 1 and len(a[0]) >= 3 and a[0] == _initials(theirs)[:len(a[0])]:
        return True, f"acronym of {theirs}"
    if len(b) == 1 and len(b[0]) >= 3 and b[0] == _initials(ours)[:len(b[0])]:
        return True, f"acronym of {ours}"
    # Scored against the LONGER name, not the shorter one. Against the shorter, "OCBC" scores
    # 100% on "Lion-OCBC Securities APAC Financials Dividend Plus ETF" — one word, one hit — and
    # the fund passes as the bank. Only the instrumentType guard caught that, and one guard
    # between us and a wrong price under a right name is not enough.
    overlap = _aligned(a, b) / max(len(a), len(b))
    if overlap >= 0.75:
        return True, f"{int(overlap * 100)}% of the distinctive words match"
    return False, f"only {int(overlap * 100)}% word overlap"


def confirm(symbol):
    """Fetch the symbol's own series. Returns (price, currency, name, exchange) or None.

    This is the guard the whole script rests on: a candidate is only accepted if the SOURCE
    itself returns a live price, in a currency, under a company name we can read back — and only
    if the instrument is an EQUITY.

    That last condition is not paperwork. Without it this script resolved OCBC to
    ``YLU.SI`` — the *Lion-OCBC Securities APAC Financials Dividend Plus ETF*, a fund with OCBC in
    its name — and Axiata to ``AXIATA.KL``, a MUTUALFUND quoting 24,086,968,300 with no currency
    at all. Both would have rendered a real number under the right company's name, which is the
    failure mode that looks completely normal on screen. The equities are ``O39.SI`` and
    ``6888.KL``.
    """
    try:
        d = json.loads(core.http_get(CHART.format(s=symbol)))
    except Exception:                                          # noqa: BLE001 - best-effort
        return None
    res = ((d.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    m = res.get("meta") or {}
    price, name = m.get("regularMarketPrice"), m.get("longName") or m.get("shortName")
    if price is None or not name:
        return None
    if (m.get("instrumentType") or "").upper() != "EQUITY" or not m.get("currency"):
        return None
    return price, m.get("currency"), name, m.get("fullExchangeName")


def candidates(company, suffix):
    """Search candidates on the right exchange. Queries go from most to least specific, because
    the source finds 'Hong Leong Bank' and not 'RHB Bank Bhd' — the legal suffix hurts."""
    seen, out = set(), []
    toks = _tokens(company)
    queries = [company, " ".join(toks), " ".join(toks[:2]), toks[0] if toks else ""]
    for q in [x for x in queries if x]:
        try:
            d = json.loads(core.http_get(SEARCH.format(q=urllib.parse.quote(q))))
        except Exception:                                      # noqa: BLE001
            continue
        for hit in d.get("quotes") or []:
            sym = hit.get("symbol") or ""
            if sym.endswith(suffix) and sym not in seen:
                seen.add(sym)
                out.append((sym, hit.get("longname") or hit.get("shortname") or ""))
        if out:
            break
    return out


def resolve(ticker, company):
    exchange = ticker.partition(":")[0].upper()
    suffix = quotes.SUFFIX.get(exchange)
    if not suffix:
        return {"ticker": ticker, "company": company, "symbol": "", "resolved_name": "",
                "basis": quotes.gap_reason(ticker) or f"{exchange} is not mapped"}
    # The naive construction first — it is already right for Thailand and Indonesia, and a
    # symbol we can confirm needs no search at all.
    manual = OVERRIDES.get(ticker)
    if manual:
        got = confirm(manual[0])
        if got:
            price, ccy, name, exch = got
            return {"ticker": ticker, "company": company, "symbol": manual[0],
                    "resolved_name": name, "basis": f"manual; {manual[1]}",
                    "price": price, "currency": ccy, "exchange": exch}
    naive = quotes.yahoo_symbol(ticker)
    tries = [(naive, "our own ticker code")] if naive else []
    tries += [(s, "exchange search") for s, _ in candidates(company, suffix)]
    for symbol, how in tries:
        got = confirm(symbol)
        if not got:
            continue
        price, ccy, name, exch = got
        ok, why = matches(company, name)
        if ok:
            return {"ticker": ticker, "company": company, "symbol": symbol,
                    "resolved_name": name, "basis": f"{how}; {why}",
                    "price": price, "currency": ccy, "exchange": exch}
    return {"ticker": ticker, "company": company, "symbol": "", "resolved_name": "",
            "basis": "no symbol on this exchange priced under a matching name"}


def main():
    write = "--write" in sys.argv
    rows = [resolve(c["ticker"], c["company"]) for c in universe.constituents()]
    ok = [r for r in rows if r["symbol"]]
    print(f"{'ticker':16s} {'symbol':11s} {'price':>11s}  resolved name / why not")
    for r in sorted(rows, key=lambda x: x["ticker"]):
        px = f"{r.get('price', ''):>11}" if r["symbol"] else " " * 11
        print(f"{r['ticker']:16s} {r['symbol'] or '—':11s} {px}  "
              f"{r['resolved_name'] or r['basis']}")
    print(f"\n{len(ok)} of {len(rows)} resolved and confirmed under a matching name.")
    if write:
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["ticker", "company", "symbol", "resolved_name",
                                               "currency", "exchange", "basis"])
            w.writeheader()
            for r in sorted(rows, key=lambda x: x["ticker"]):
                w.writerow({k: r.get(k, "") for k in w.fieldnames})
        print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
