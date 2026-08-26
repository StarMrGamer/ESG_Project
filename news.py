"""In the news — real, dated, sourced headlines per company.

Why this module has NO LLM in it
--------------------------------
`harvest.py` needs a model because a *fact* has to be pulled out of prose: a sentence about a
sustainability-linked loan has to become `{text, published_at, source_url}` before rules can score
it. A headline needs none of that. A search result already IS a title and a URL, so asking a model
to produce one would be asking it to retype what we already hold — and every retyping is a chance
to invent. So this module costs **zero tokens** and there is nothing here for a model to
hallucinate: every title and URL is copied verbatim out of the retrieved results.

It is also DISPLAY ONLY. Nothing here reaches `signals.py` or `engine.py`, no headline moves a
momentum, a confidence or a quadrant, and the stored file is not an input to `run_id`. That is
deliberate: news is the lowest-quality evidence class we touch, and the one place where a
company's own PR is hardest to tell from reporting.

The guards, which are the whole module
--------------------------------------
1. **The title must name the company.** A search for a mid-cap returns other companies, and a
   headline about the wrong one printed under this one's name is the `resolve_ric` failure again —
   the one that rendered I-Bhd's data under Malaysia Airports'. A distinctive word from the
   company's name has to appear in the title or the item is dropped.
2. **A date is the source's, or it is absent.** `signals.extract_date` returns the date the text
   states; anything it cannot find stays `None` and the card says "date not stated" rather than
   quietly showing today's.
3. **A date in the future is dropped.** The harvest learned this the expensive way: models and
   press releases both talk about target years, and "net zero by 2050" became a publication date
   that pushed an entire run's decay reference 24 years forward.
4. **Source type is decided by the domain, by us** (`signals.classify_source`), so a company's own
   newsroom can never present itself as reporting.
5. **Stored per company under `data/news/`**, so a bad sweep is deleted rather than unpicked, and
   the verified basket is never written to.

Run:  python news.py --company KLSE:RHBBANK     # one, printed
      python news.py --all                      # sweep the real universe -> data/news/
      python news.py --refilter                 # re-apply the guards to what is stored, no fetch
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import core
import rag
import signals
import universe

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "data", "news")

#: Two angles, not one. A single "<company> news" query returns the investor-relations page and
#: little else; pairing it with a sustainability angle is what surfaces reporting rather than
#: filings — the same reasoning as the harvest's four angles, at a smaller scale because this is
#: a display card and not evidence.
ANGLES = (
    '"{name}" news',
    '"{name}" sustainability OR ESG OR emissions news',
    # Green finance is the third angle because it is the one the product's own pipeline turns on:
    # N counts issuers, M counts bond-ready candidates, and an issuance announcement is the event
    # that moves a company between them. A general news sweep rarely surfaces it.
    '"{name}" green bond OR sustainability-linked OR sukuk OR transition finance',
)

MAX_PER_COMPANY = 8

#: Seconds between queries on a sweep. Not optional at 52 companies: the search backend serves a
#: challenge page under sustained load, and an unpaced run returns `offline` for most of the
#: basket — measured here, three of the first four companies came back with zero documents while
#: the cached one returned eight. `harvest.py` learned the same lesson ("the first full
#: 52-company run was cut off partway: 14 companies returned every angle offline") and this uses
#: its convention: a gap between passes, twice that between companies.
DEFAULT_PACE = 4.0

#: Search snippets carry no publication date — measured, not assumed: every result for RHB Bank
#: came back `dataset_as_of`, meaning nothing in the text stated one. An undated news card is a
#: weak card, so each kept headline is fetched once and the date is read out of the page's OWN
#: metadata. Best-effort by contract: a site that blocks us, or states no date, stays undated and
#: says so. Nothing is inferred from the URL, the crawl time or the position in the results.
_DATE_META = (
    re.compile(r'article:published_time"[^>]*content="([^"]+)"', re.I),
    re.compile(r'content="([^"]+)"[^>]*property="article:published_time"', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I),
    re.compile(r'name="pubdate"[^>]*content="([^"]+)"', re.I),
    re.compile(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})', re.I),
)

#: Result pages that are not articles. A quote page or an announcements index under an "In the
#: news" heading is filler that makes the card look answered when it is not.
_NOT_AN_ARTICLE = re.compile(
    r"stock price|share price|official announcements|company information|company profile"
    r"|\bquote\b|stock quote|financial statements|annual report \d{4}|investor relations",
    re.I)

#: Words that identify nobody. A title matching only these is not about this company.
_NOISE = {"bhd", "berhad", "plc", "pcl", "ltd", "limited", "tbk", "pt", "corp", "corporation",
          "inc", "co", "company", "public", "group", "holdings", "holding", "the", "and", "of",
          "international", "bank", "banking", "energy", "power", "capital"}


def _tokens(name: str):
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in _NOISE]


def names_the_company(title: str, company: str) -> bool:
    """Guard 1. Does this headline actually name this company?"""
    low = (title or "").lower()
    toks = _tokens(company)
    if not toks:
        return False
    # A single distinctive word is enough ("Sembcorp"), but it has to be a WORD — a bare
    # substring match is how "I-Bhd" once matched inside "malaysia airports".
    return any(re.search(rf"\b{re.escape(t)}", low) for t in toks if len(t) >= 3)


def _source_name(url: str) -> str:
    host = (urlparse(url or "").netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def page_date(url: str, today: str):
    """The publication date the ARTICLE states in its own metadata, or None. Never raises."""
    try:
        html_text = core.http_get(url, timeout=6)
    except Exception:                                          # noqa: BLE001 - best-effort
        return None
    for pattern in _DATE_META:
        m = pattern.search(html_text or "")
        if not m:
            continue
        iso = (m.group(1) or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) and iso <= today:
            return iso
    return None


def is_article(title: str, company: str) -> bool:
    """Is this a story, or a stock-quote page wearing the company's name?"""
    if _NOT_AN_ARTICLE.search(title or ""):
        return False
    # Strip the company's own words and the trailing " - Publisher" / " | Publisher" tail; what
    # is left has to be a sentence, not a label.
    body = re.split(r"\s[-|]\s", title or "")[0]
    for tok in _tokens(company):
        body = re.sub(rf"\b{re.escape(tok)}\b", " ", body, flags=re.I)
    # Legal-form words are not substance either. Without this, "DBS Group Holdings Ltd | Reuters"
    # keeps "Group Holdings Ltd" after the company's own name is removed, counts three words, and
    # a quote page passes as a story.
    words = [w for w in re.findall(r"[A-Za-z]{3,}", body) if w.lower() not in _NOISE]
    return len(words) >= 3


def _dated(text: str, today: str):
    """Guard 2 + 3. The date the source states, or None. Never today's, never the future."""
    iso, basis = signals.extract_date(text or "", fallback=None)
    if not iso or basis != "stated":
        return None
    return None if iso > today else iso


def gather(ticker: str, company: str, *, use_cache: bool = True, limit: int = MAX_PER_COMPANY,
           fetch_dates: bool = True, pace: float = 0.0):
    """Real headlines for one company. Returns the record; never raises (rule 1)."""
    today = datetime.date.today().isoformat()
    seen_urls, seen_titles, items, errors = set(), set(), [], []

    for angle_index, angle in enumerate(ANGLES):
        query = angle.format(name=company)
        if pace and angle_index:
            time.sleep(pace)
        try:
            docs, status, error = rag.fetch_documents(query, use_cache=use_cache)
            # A challenge page is a rate limit, not an empty topic. One patient retry recovers
            # most of them; without it a sweep records "no news" for a company that has plenty.
            if not docs and pace:
                time.sleep(pace * 3)
                docs, status, error = rag.fetch_documents(query, use_cache=False)
        except Exception as exc:                               # noqa: BLE001 - best-effort
            errors.append(f"{query}: {type(exc).__name__}")
            continue
        if error and not docs:
            errors.append(f"{query}: {error}")
        for doc in docs or []:
            title = (doc.get("title") or "").strip()
            url = (doc.get("url") or "").strip()
            if not title or not url.startswith("http"):
                continue
            key = re.sub(r"[^a-z0-9]+", "", title.lower())[:80]
            if url in seen_urls or key in seen_titles:
                continue
            if not names_the_company(title, company) or not is_article(title, company):
                continue
            seen_urls.add(url)
            seen_titles.add(key)
            items.append({
                "title": title,
                "url": url,
                "source": _source_name(url),
                # OUR call, from the domain — never the publisher's own description of itself.
                "source_type": signals.classify_source(url),
                "published_at": _dated(f"{title} {doc.get('text') or ''}", today),
            })

    # The snippet almost never states a date, so ask each article for its own. One fetch per kept
    # headline, best-effort, and only for the ones we are actually going to show.
    if fetch_dates:
        for item in items[:limit * 2]:
            if not item["published_at"]:
                item["published_at"] = page_date(item["url"], today)

    # Dated first, newest first; undated keep their place at the end rather than being dropped —
    # a real headline with no date on the page is still a real headline, and the card says so.
    items.sort(key=lambda it: (it["published_at"] is None, it["published_at"] or ""), reverse=False)
    items = sorted(items, key=lambda it: (it["published_at"] is None,
                                          "" if it["published_at"] is None
                                          else it["published_at"]), reverse=False)
    dated = [i for i in items if i["published_at"]]
    undated = [i for i in items if not i["published_at"]]
    dated.sort(key=lambda i: i["published_at"], reverse=True)
    ordered = (dated + undated)[:limit]

    # Did the SOURCE answer at all? "Blocked" and "this company has no news" are different
    # findings that both look like an empty list, and only one of them should ever be written.
    blocked = not ordered and len(errors) >= len(ANGLES)
    # Counted over what is KEPT, not over what was found. Counting before the trim printed
    # "8 items (11 dated)" — a count larger than the list it describes, which on the card would
    # have read as "11 of 8 carry a date".
    kept_dated = sum(1 for i in ordered if i["published_at"])
    return {"ticker": ticker, "company": company, "gathered_at": today,
            "items": ordered, "dated": kept_dated, "undated": len(ordered) - kept_dated,
            "found": {"dated": len(dated), "undated": len(undated)},
            "errors": errors, "blocked": blocked, "no_llm": True}


def save_unless_worse(record: dict):
    """Write the record UNLESS doing so would replace real headlines with nothing.

    `harvest.py` learned this and `selftest.py` pins it: a sweep that runs while the search
    backend is throttling returns empty for every company, and saving that erases a good earlier
    run. A rate limit is not evidence that a company stopped being in the news.
    """
    if record.get("blocked"):
        prior = load(record["ticker"])
        if prior and prior.get("items"):
            return None, "kept the earlier record — the source was blocked, not empty"
        return None, "not saved — the source was blocked and there was nothing stored"
    return save(record), None


def path_for(ticker: str) -> str:
    return os.path.join(STORE, ticker.replace(":", "_") + ".json")


def save(record: dict) -> str:
    os.makedirs(STORE, exist_ok=True)
    p = path_for(record["ticker"])
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    return p


def load(ticker: str):
    try:
        with open(path_for(ticker), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                          # noqa: BLE001 - best-effort
        return None


def _main():
    ap = argparse.ArgumentParser(description="Real headlines per company — no LLM, display only.")
    ap.add_argument("--company", help="one ticker, e.g. KLSE:RHBBANK")
    ap.add_argument("--all", action="store_true", help="sweep the whole real universe")
    ap.add_argument("--refilter", action="store_true",
                    help="re-apply the guards to stored records without re-fetching")
    ap.add_argument("--no-cache", action="store_true", help="ignore the retrieval cache")
    ap.add_argument("--no-dates", action="store_true",
                    help="skip the per-article date fetch (faster, and every item stays undated)")
    ap.add_argument("--pace", type=float, default=None,
                    help=f"seconds between queries (default {DEFAULT_PACE} on --all, 0 otherwise)")
    a = ap.parse_args()
    cons = universe.constituents()

    if a.refilter:
        today = datetime.date.today().isoformat()
        for c in cons:
            rec = load(c["ticker"])
            if not rec:
                continue
            before = len(rec.get("items") or [])
            kept = [i for i in rec["items"]
                    if names_the_company(i.get("title", ""), c["company"])
                    and not (i.get("published_at") and i["published_at"] > today)]
            rec["items"] = kept
            rec["dated"] = sum(1 for i in kept if i.get("published_at"))
            rec["undated"] = len(kept) - rec["dated"]
            save(rec)
            if before != len(kept):
                print(f"  {c['ticker']:<14} {before} -> {len(kept)}")
        print("refiltered stored records; nothing was fetched")
        return

    picks = ([c for c in cons if c["ticker"] == a.company] if a.company
             else cons if a.all else cons[:1])
    if not picks:
        print(f"no such ticker: {a.company}")
        return

    pace = a.pace if a.pace is not None else (DEFAULT_PACE if a.all else 0.0)
    total_items = total_dated = empty = 0
    for idx, c in enumerate(picks):
        if pace and idx:
            time.sleep(pace * 2)          # a longer gap between companies than between angles
        rec = gather(c["ticker"], c["company"], use_cache=not a.no_cache,
                     fetch_dates=not a.no_dates, pace=pace)
        if not rec["items"]:
            empty += 1
        total_items += len(rec["items"])
        total_dated += rec["dated"]
        if a.all:
            _, why = save_unless_worse(rec)
            note = f"  [{why}]" if why else ""
            print(f"  {c['ticker']:<14} {len(rec['items'])} items ({rec['dated']} dated){note}",
                  flush=True)
        else:
            print(f"\n{c['company']} ({c['ticker']}) — {len(rec['items'])} items, "
                  f"{rec['dated']} dated")
            for i in rec["items"]:
                print(f"  {i['published_at'] or 'undated  ':<10} {i['source']:<24} "
                      f"{i['source_type']:<16} {i['title'][:80]}")
            if rec["errors"]:
                print("  errors:", "; ".join(rec["errors"])[:200])
    if a.all:
        print(f"\n{len(picks)} companies · {total_items} headlines · {total_dated} dated · "
              f"{empty} with nothing · 0 tokens spent")


if __name__ == "__main__":
    sys.exit(_main())
