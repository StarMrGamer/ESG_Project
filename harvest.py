"""
harvest.py — turn live public sources into DATED, SOURCED evidence the engine can score.
=========================================================================================

THE PROBLEM THIS SOLVES
-----------------------
The verified CGSI basket is a green-bond verification sheet, not an evidence base. Scored
deterministically it yields at most 5 signals a company and 28 of the 52 yield none at all, so
`hidden_winners` — which needs 10 corroborating signals — is unreachable on real data. The
answer is NOT to lower the threshold until the screen returns what we want; that is precisely
the failure the Adaro case exists to warn about. The answer is more evidence.

WHERE THE AI SITS
-----------------
Exactly where it sits everywhere else in this system: **the model reads, the rules score.**

    live search (rag.py)  ->  LLM extracts dated facts from the snippets ONLY
                          ->  signals.py routes them by rule
                          ->  engine.py scores them deterministically

The model never assigns a direction weight, never sets a confidence, never decides a label. It
does one job — turn prose into `{text, published_at, source_url}` — and every one of those three
fields is checked against the retrieved snippets before it is allowed through. That is what makes
the output safe to feed a pure engine: the scoring stays reproducible even though the gathering
is not.

THE FOUR GUARDS (rule 2 is the whole point of this file)
--------------------------------------------------------
1. **A URL the model did not retrieve is dropped.** Every event's `source_url` must appear in
   the snippet set for that company. The model cannot cite anything it was not shown.
2. **A date the snippet does not state is dropped.** No event is back-filled to "today" — an
   undated claim is not evidence of *when*, and time decay is meaningless without it.
3. **`source_type` is decided by us, not the model**, from the URL's own domain. Otherwise a
   company press release can be labelled "regulator" and score at double weight.
4. **The verified basket is never overwritten.** Harvested events land in `data/harvest/` and
   are merged as an OVERLAY at load time, so CGSI's rows stay exactly as CGSI supplied them and
   any harvest can be thrown away without losing the source of truth.

Best-effort by contract (rule 1): no key, no network, or a refusing model all degrade to "no
harvested evidence", never to a crash and never to an invented fact.

    python harvest.py --list                  # what has been harvested, and what has not
    python harvest.py SGX:DBS                 # one company
    python harvest.py --empty                 # every company the engine currently scores at 0
    python harvest.py --all --limit 10        # the whole basket, capped
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import core
import engine_config
import rag
import signals as signal_lib
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HARVEST_DIR = os.path.join(BASE_DIR, "data", "harvest")

#: How many ranked snippets to hand the model per company.
TOP_K = int(os.environ.get("ESG_HARVEST_TOP_K", "8"))

#: URL domain -> `source_quality` key in `data/engine_config.json`. Decided HERE, never by the
#: model (guard 3). Order matters: the first matching fragment wins, so the specific regulator
#: and exchange hosts are checked before the generic news bucket.
_DOMAIN_RULES = (
    (("mas.gov.sg", "sc.com.my", "sec.or.th", "ojk.go.id", "sec.gov.ph", "bnm.gov.my",
      ".gov", "europa.eu", "unfccc.int"), "regulator"),
    (("sgx.com", "bursamalaysia.com", "set.or.th", "idx.co.id", "pse.com.ph", "links.sgx.com"),
     "exchange_filing"),
    (("msci.com", "spglobal.com", "ftserussell.com", "climatebonds.net", "cdp.net",
      "sustainalytics.com", "iss-corporate.com", "moodys.com", "lseg.com"), "index_provider"),
    (("globalforestwatch.org", "wwf.", "greenpeace.", "amnesty.", "hrw.org",
      "transparency.org"), "ngo"),
    (("reuters.com", "bloomberg.com", "channelnewsasia.com", "straitstimes.com",
      "thestar.com.my", "bangkokpost.com", "nikkei.com", "ft.com", "scmp.com",
      "theedgemalaysia.com", "businesstimes.com.sg", "inquirer.net", "jakartapost.com"),
     "news"),
)

_DATE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")

_SYSTEM = """You extract ESG evidence from search results. You are given SNIPPETS about one \
company. Return ONLY facts that the snippets themselves state.

RULES — a violation makes the whole answer useless:
- Use ONLY the snippets below. Do not use anything you know about this company.
- `published_at` is when the source was PUBLISHED, or when the event HAPPENED. It is never a
  target year. "aims for net zero by 2050" is a fact published in some past year about 2050 —
  if the snippet does not say WHEN it was published, DROP the fact. Never write a future date.
- Format YYYY-MM-DD. If the snippet gives only a month, use the first of that month. If it
  states no date at all, DROP the fact.
- Every fact needs `source_url` copied EXACTLY from the snippet it came from.
- One specific, checkable fact per item, in one sentence, quoting the snippet's own numbers.
- Prefer: emissions and targets, renewable or transition capex, green/sustainability financing, \
regulatory action, fines, controversies, labour and safety, board and governance changes, \
disclosure and assurance, AI/digital investment, patents, data breaches.
- Skip share prices, analyst ratings, and generic corporate description.
- If the snippets contain no datable ESG fact, return {"events": []}.

Do not explain your working. Do not think out loud. Your entire reply must start with { and
end with } and contain nothing else, in this exact shape:
{"events": [{"text": "...", "published_at": "YYYY-MM-DD", "source_url": "..."}]}"""

_USER = """COMPANY: {company} ({ticker}), {industry}, listed in {country}.

SNIPPETS:
{snippets}"""


def _source_type_for(url: str) -> str:
    """Guard 3 — the weight a source earns is decided by its domain, not by the model."""
    low = (url or "").lower()
    for fragments, kind in _DOMAIN_RULES:
        if any(f in low for f in fragments):
            return kind
    return "company_pr" if low else "unknown"


#: FOUR SEARCH ANGLES, not one. A single blended query ("ESG sustainability emissions
#: governance controversy") returns one page of results and yields about one usable fact; the
#: same company searched four ways returns four disjoint result sets, because each angle
#: surfaces a different corner of the public record. Measured on Siam Cement: one blended query
#: kept 1 event, these four kept 5, and the engine went from 0 signals to 4.
#:
#: They are also deliberately not all flattering. `controversy` is there so the harvest cannot
#: quietly become a press-release collector — the same reason company PR is capped at 0.5
#: confidence everywhere else.
ANGLES = (
    ("emissions", "emissions reduction target scope 1 2 3 net zero carbon renewable energy"),
    ("governance", "board governance disclosure assurance sustainability report audit committee"),
    ("financing", "green bond sustainable financing framework capex renewable investment"),
    ("controversy", "fine lawsuit penalty pollution controversy labour safety incident breach"),
)


def _query_for(constituent: Dict[str, Any], angle: str = "") -> str:
    """A keyword query, not a sentence — news search does badly with questions."""
    return " ".join([
        constituent.get("company", ""),
        constituent.get("country", ""),
        angle or "ESG sustainability emissions target green financing governance controversy",
    ]).strip()


def _clean_events(raw: Any, allowed_urls: set, cid: str,
                  max_date: str = "") -> List[Dict[str, Any]]:
    """Guards 1 and 2: drop anything the model cited or dated beyond what it was shown.

    `max_date` is the real teeth on the date guard. Models reliably read a TARGET year as a
    publication date — "aims for net zero by 2050" came back as `published_at: 2050-12-31`. That
    is not a small error: `engine._as_of_from` takes the newest date in the data as the decay
    reference, so one 2050 event moved `as_of` 24 years into the future, decayed every genuine
    signal in the basket to zero weight, and took composite momentum for the WHOLE universe to
    0.000 — M went 4 -> 0 while every affected company still showed its original signal count.
    A future publication date is impossible; anything past `max_date` is dropped."""
    out, seen = [], set()
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        url = str(item.get("source_url") or "").strip()
        date = str(item.get("published_at") or "").strip()[:10]
        if not text or len(text) < 25:
            continue
        if url not in allowed_urls:               # guard 1 — a URL it was not given
            continue
        if not _DATE_ISO.fullmatch(date):         # guard 2 — undated, or a made-up shape
            continue
        if max_date and date > max_date:          # guard 2b — a target year, not a publication
            continue
        key = (text[:90].lower(), url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "event_id": "%s-harvest-%d" % (cid, len(out)),
            "text": text,
            "published_at": date,
            "source_url": url,
            "source_type": _source_type_for(url),
            "_origin": "harvest",
        })
    return out


def _extract_from(constituent, cid, query, use_cache, max_date=""):
    """One search angle -> (events, snippet_count, status). Never raises."""
    try:
        ctx = rag.gather_context(query, k=TOP_K, use_cache=use_cache)
    except Exception as exc:                                    # noqa: BLE001
        return [], 0, "retrieval failed (%s)" % type(exc).__name__

    snippets = ctx.get("snippets") or []
    if not snippets:
        return [], 0, ctx.get("status") or "no snippets"

    allowed = {str(s.get("url") or "").strip() for s in snippets}
    allowed.discard("")
    block = "\n\n".join(
        # `rag.retrieve` names the body `snippet`, not `text`. Reading the wrong key sent the
        # model titles with no bodies, and it correctly extracted nothing from them.
        "[%d] %s\n%s\nURL: %s" % (i + 1, s.get("title", ""), (s.get("snippet") or "")[:700],
                                  s.get("url", ""))
        for i, s in enumerate(snippets))

    user = (_USER
            .replace("{company}", constituent.get("company", ""))
            .replace("{ticker}", cid)
            .replace("{industry}", constituent.get("industry", constituent.get("sector", "")))
            .replace("{country}", constituent.get("country", ""))
            .replace("{snippets}", block))

    # Two attempts. The model sometimes reasons at length before answering and runs out of
    # budget mid-thought, which arrives as an unparseable reply rather than an error — the
    # generous token ceiling is for that preamble, not for the answer, which is short.
    parsed = {}
    for attempt in range(2):
        try:
            reply = core.call_llm([{"role": "user", "content": user}], _SYSTEM,
                                  max_tokens=2600, temperature=0.0 if attempt else 0.2,
                                  json_mode=True)
            parsed = core.parse_json(reply) or {}
        except Exception as exc:                                # noqa: BLE001
            return [], len(snippets), "extraction failed (%s)" % type(exc).__name__
        if isinstance(parsed, dict) and "events" in parsed:
            break

    if not isinstance(parsed, dict) or "events" not in parsed:
        # A reply we could not parse is a FAILED harvest, not an empty one. Reporting "0 facts"
        # when the truth is "the answer did not come back as JSON" would under-report evidence
        # and read as a finding about the company.
        return [], len(snippets), "unparsed reply"

    return (_clean_events(parsed.get("events"), allowed, cid, max_date),
            len(snippets), ctx.get("status", ""))


def harvest_company(constituent: Dict[str, Any], *, use_cache: bool = True) -> Dict[str, Any]:
    """Live-retrieve across every angle, extract, dedupe, and return one record.

    NEVER raises (rule 1): a dead network, a missing key or a refusing model all come back as a
    record with no events and a status saying which."""
    cid = constituent.get("ticker", "unknown")
    record = {"company_id": cid, "company": constituent.get("company", cid),
              "events": [], "status": "", "snippet_count": 0, "angles": {}}
    # The latest date the VERIFIED data itself asserts. Nothing harvested may post-date it —
    # and this keeps the bound clock-free, like everything else the engine reads.
    max_date = str(constituent.get("as_of") or "").strip()[:10]

    merged, statuses = {}, []
    for name, angle in ANGLES:
        events, n, status = _extract_from(constituent, cid, _query_for(constituent, angle),
                                          use_cache, max_date)
        record["snippet_count"] += n
        record["angles"][name] = {"snippets": n, "kept": len(events), "status": status}
        if status and status not in ("live", "cache"):
            statuses.append("%s: %s" % (name, status))
        for e in events:
            # Dedupe across angles — the same filing surfaces in more than one search, and one
            # fact counted four times would be corroboration the evidence does not have.
            merged.setdefault((e["text"][:70].lower(), e["source_url"]), e)

    events = list(merged.values())
    for i, e in enumerate(events):
        e["event_id"] = "%s-harvest-%d" % (cid, i)
    record["events"] = events
    record["kept"] = len(events)
    record["status"] = "; ".join(statuses) if statuses else "ok"
    return record


# --------------------------------------------------------------------------- #
#  storage + overlay
# --------------------------------------------------------------------------- #
def _path_for(cid: str) -> str:
    return os.path.join(HARVEST_DIR, cid.replace(":", "_") + ".json")


def save(record: Dict[str, Any]) -> str:
    os.makedirs(HARVEST_DIR, exist_ok=True)
    path = _path_for(record["company_id"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return path


def load_overlay() -> Dict[str, List[Dict[str, Any]]]:
    """`{company_id: [events]}` for everything harvested so far. `{}` when nothing has been."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        names = sorted(os.listdir(HARVEST_DIR))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(HARVEST_DIR, name), "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        events = rec.get("events") or []
        if events:
            out[rec.get("company_id", "")] = events
    out.pop("", None)
    return out


def apply_overlay(constituents: List[Dict[str, Any]],
                  overlay: Optional[Dict[str, List[Dict[str, Any]]]] = None
                  ) -> List[Dict[str, Any]]:
    """Return constituents with harvested events APPENDED to their own.

    A copy — the verified basket on disk is never touched (guard 4). Harvested events sort after
    the basket's own, and `signals.from_company` dedupes by `signal_id`, so re-running a harvest
    cannot inflate a company's signal count with the same fact twice."""
    overlay = load_overlay() if overlay is None else overlay
    if not overlay:
        return constituents
    out = []
    for c in constituents:
        extra = overlay.get(c.get("ticker", ""))
        if not extra:
            out.append(c)
            continue
        merged = dict(c)
        merged["events"] = list(c.get("events") or []) + list(extra)
        out.append(merged)
    return out


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _scored_counts() -> Dict[str, int]:
    cfg = engine_config.load()
    return {c["ticker"]: len(signal_lib.from_company(c, config=cfg))
            for c in universe.constituents()}


def main(argv: List[str]) -> int:
    cons = {c["ticker"]: c for c in universe.constituents()}
    overlay = load_overlay()

    if "--list" in argv:
        counts = _scored_counts()
        done = sum(1 for t in cons if t in overlay)
        print("harvested %d / %d companies · %d events on disk"
              % (done, len(cons), sum(len(v) for v in overlay.values())))
        for t, c in sorted(cons.items()):
            got = len(overlay.get(t, []))
            print("  %-14s %-32s base %2d  harvested %2d%s"
                  % (t, c["company"][:32], counts.get(t, 0), got,
                     "" if got or counts.get(t, 0) else "   <- no evidence at all"))
        return 0

    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 10**9
    if "--empty" in argv:
        counts = _scored_counts()
        targets = [t for t in sorted(cons) if counts.get(t, 0) == 0]
    elif "--all" in argv:
        targets = sorted(cons)
    else:
        targets = [a for a in argv if not a.startswith("--") and a in cons]
    targets = targets[:limit]

    if not targets:
        print("Nothing to do. Pass a ticker, --empty, or --all (see --list).")
        return 1

    print("harvesting %d company(ies) — %d search angles x %d snippets each\n"
          % (len(targets), len(ANGLES), TOP_K))
    total_kept = 0
    for t in targets:
        rec = harvest_company(cons[t])
        save(rec)
        total_kept += rec.get("kept", 0)
        note = rec["status"] if rec["status"] != "ok" else ""
        print("  %-14s %-30s snippets %3d  kept %2d  %s"
              % (t, cons[t]["company"][:30], rec["snippet_count"], rec.get("kept", 0), note))
    print("\nkept %d dated, sourced events -> %s"
          % (total_kept, os.path.relpath(HARVEST_DIR, BASE_DIR)))
    print("The engine picks these up through `harvest.apply_overlay`; the verified basket on "
          "disk is untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
