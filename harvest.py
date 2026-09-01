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
    python harvest.py --refilter              # re-apply the guards to what is already stored
    python harvest.py --cost                  # measured tokens per company (for the cost model)
"""

import json
import os
import time
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


#: SITE-SCOPED angles — the answer to "92% of what search returns is company-published".
#:
#: The confidence model caps a company's own publications at 0.50 by rule (the Adaro lesson), so
#: gathering MORE evidence raises signal counts and cannot raise confidence. Twelve companies
#: clear the disagreement bar and every one of them fails on confidence. The fix was never a
#: lower threshold — it is better SOURCES, and this is how they are reached.
#:
#: Measured on Public Bank, 2026-08-25: an unscoped query returned 2 of 3 results from
#: `publicbankgroup.com` (graded 0.50). The same query scoped to Bursa returned exchange filings
#: (0.95). Same engine, same cost, roughly double the source quality.
#:
#: Every domain here is one `signals.classify_source` ALREADY grades at 0.65 or better — a domain
#: it does not recognise falls through to `company_pr`, which would defeat the entire purpose.
#: Groups are kept to five or six domains because a long OR chain degrades result quality.
#: `docs/cse-high-quality-domains.txt` holds the same list in Google-CSE form.
QUALITY_ANGLES = (
    ("q_regulator", "ESG sustainability disclosure enforcement directive",
     "(site:mas.gov.sg OR site:sec.gov.ph OR site:bnm.gov.my OR site:europa.eu)"),
    ("q_exchange", "sustainability report filing announcement listing rule",
     "(site:sgx.com OR site:bursamalaysia.com OR site:idx.co.id OR site:set.or.th "
     "OR site:pse.com.ph)"),
    ("q_index", "ESG rating index inclusion score assessment",
     "(site:msci.com OR site:spglobal.com OR site:cdp.net OR site:ftserussell.com "
     "OR site:sustainalytics.com)"),
    # The watchdog group is not optional. Without an adverse-source angle a harvest quietly
    # becomes a press-release collector, which is precisely what Adaro looked like.
    ("q_watchdog", "controversy pollution deforestation labour violation campaign",
     "(site:banktrack.org OR site:marketforces.org.au OR site:mongabay.com "
     "OR site:greenpeace.org)"),
    ("q_news", "ESG green bond emissions governance",
     "(site:reuters.com OR site:bloomberg.com OR site:businesstimes.com.sg "
     "OR site:straitstimes.com OR site:channelnewsasia.com OR site:theedgemalaysia.com)"),
)


#: Years the DEEP sweep scopes each angle to, on top of the unscoped pass.
#:
#: Search ranks by recency, so an unscoped sweep returns a recency-shaped sample of a company's
#: history. Measured over the first full sweep: 2025 yielded 63 events, 2024 yielded 43, and 2023
#: only 20 — not because 2023 was a quiet year for ASEAN ESG, but because a 2023 filing is buried
#: under two years of newer pages. Naming the thin years in the query surfaces material the
#: ranking hides.
#:
#: Only the thin years are listed. Adding 2025 and 2026 would multiply cost to re-find pages the
#: unscoped pass already returns first.
DEEP_YEARS = ("2023", "2024")


def _query_for(constituent: Dict[str, Any], angle: str = "", year: str = "",
               sites: str = "") -> str:
    """A keyword query, not a sentence — news search does badly with questions.

    `year` scopes the angle to one year for the deep sweep. It is a keyword, not a date filter:
    search engines treat it as a term, which is exactly what is wanted — a page ABOUT 2023 is as
    useful as one published in 2023, and the date guards decide what survives either way."""
    return " ".join([
        constituent.get("company", ""),
        constituent.get("country", ""),
        angle or "ESG sustainability emissions target green financing governance controversy",
        year,
        sites,
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
        return [], 0, "retrieval failed (%s)" % type(exc).__name__, 0

    snippets = ctx.get("snippets") or []
    if not snippets:
        return [], 0, ctx.get("status") or "no snippets", 0

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
            return [], len(snippets), "extraction failed (%s)" % type(exc).__name__, 0
        if isinstance(parsed, dict) and "events" in parsed:
            break

    if not isinstance(parsed, dict) or "events" not in parsed:
        # A reply we could not parse is a FAILED harvest, not an empty one. Reporting "0 facts"
        # when the truth is "the answer did not come back as JSON" would under-report evidence
        # and read as a finding about the company.
        return [], len(snippets), "unparsed reply", len(_SYSTEM) + len(user)

    return (_clean_events(parsed.get("events"), allowed, cid, max_date),
            len(snippets), ctx.get("status", ""), len(_SYSTEM) + len(user))


def harvest_company(constituent: Dict[str, Any], *, use_cache: bool = True,
                    deep: bool = False, pace: float = 0.0,
                    quality: bool = False) -> Dict[str, Any]:
    """Live-retrieve across every angle, extract, dedupe, and return one record.

    NEVER raises (rule 1): a dead network, a missing key or a refusing model all come back as a
    record with no events and a status saying which."""
    cid = constituent.get("ticker", "unknown")
    record = {"company_id": cid, "company": constituent.get("company", cid),
              "events": [], "status": "", "snippet_count": 0, "angles": {}}
    # The latest date the VERIFIED data itself asserts. Nothing harvested may post-date it —
    # and this keeps the bound clock-free, like everything else the engine reads.
    max_date = str(constituent.get("as_of") or "").strip()[:10]

    # The unscoped pass, plus one year-scoped pass per thin year when running deep. Passes are
    # merged and deduped below, so a fact both passes find is still one fact.
    passes = [(name, angle, "", "") for name, angle in ANGLES]
    if quality:
        passes += [(name, angle, "", sites) for name, angle, sites in QUALITY_ANGLES]
    if deep:
        passes += [(f"{name}:{yr}", angle, yr, "") for name, angle in ANGLES for yr in DEEP_YEARS]
        if quality:
            passes += [(f"{name}:{yr}", angle, yr, sites)
                       for name, angle, sites in QUALITY_ANGLES for yr in DEEP_YEARS]

    merged, statuses = {}, []
    for pass_index, (name, angle, year, sites) in enumerate(passes):
        # Pacing exists because the search backend throttles a sustained sweep. The first full
        # 52-company run was cut off partway: 14 companies returned every angle `offline`. A
        # deep sweep fires three times as many queries, so it MUST be paced or it reproduces
        # that failure at three times the cost. Sleeping between passes is cheap; re-running a
        # 52-company sweep is not.
        if pace and pass_index:
            time.sleep(pace)
        events, n, status, chars = _extract_from(
            constituent, cid, _query_for(constituent, angle, year, sites), use_cache, max_date)
        record["snippet_count"] += n
        # Prompt size is recorded HERE, at the only moment it is known for free. Deriving it
        # later means replaying every retrieval, which needs a warm cache and stalls outright
        # when the search endpoint is rate-limited — a cost measurement should not depend on
        # the network being friendly.
        record["prompt_chars"] = record.get("prompt_chars", 0) + chars
        record["angles"][name] = {"snippets": n, "kept": len(events), "status": status,
                                  "prompt_chars": chars}
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


def save(record: Dict[str, Any], *, merge: bool = True, replace: bool = False) -> str:
    """Write one company's harvest, UNIONed with whatever is already stored (the default).

    Merge is the default because of a bug that cost real evidence. The first full 52-company
    sweep was rate-limited by the search backend partway through: 14 companies came back with
    every angle `offline` and 11 of them kept nothing. Because `save` overwrote, a FAILED FETCH
    replaced good stored evidence with an empty list — the harvest went backwards (2025 events
    fell 63 -> 48) and nothing on screen said so, because a company with no evidence looks exactly
    like a company we never swept.

    That is the same shape as every other trap here: an absence rendered as a finding. A network
    failure must never be able to destroy data it did not replace, so:

      * `merge=True` (default) unions new events with stored ones, deduped on (text prefix, url);
      * a record that kept NOTHING never overwrites a stored record that has something, even
        with `replace=True` — there is no legitimate reason for a failed sweep to empty a file;
      * `replace=True` is the deliberate opt-out, for a genuine re-harvest after a rule change.
    """
    os.makedirs(HARVEST_DIR, exist_ok=True)
    path = _path_for(record["company_id"])

    prior_events = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                prior_events = json.load(fh).get("events") or []
        except (OSError, ValueError):
            prior_events = []

    # The hard floor, independent of every flag: a sweep that kept nothing cannot empty a file.
    if prior_events and not (record.get("events") or []):
        record = dict(record)
        record["events"] = prior_events
        record["kept"] = len(prior_events)
        record["status"] = (record.get("status") or "") + " | kept prior evidence: this sweep " \
                           "returned nothing (search offline), so stored events were preserved"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        return path

    if merge and not replace and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                prior = json.load(fh)
        except (OSError, ValueError):
            prior = {}
        seen, out = set(), []
        for e in list(prior.get("events") or []) + list(record.get("events") or []):
            key = (str(e.get("text", ""))[:70].lower(), e.get("source_url"))
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        for i, e in enumerate(out):
            e["event_id"] = "%s-harvest-%d" % (record["company_id"], i)
        record = dict(record)
        record["events"] = out
        record["kept"] = len(out)
        record["merged_from_prior"] = len(prior.get("events") or [])
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


def refilter() -> Dict[str, int]:
    """Re-apply the guards to everything already on disk, without re-fetching.

    Exists because the guards get stronger over time and re-running a sweep costs real money
    and real calls to other people's servers. The events are already stored with their source
    and date, so a tightened rule can simply be re-applied to them. Currently this is what
    removes target-year dates (2050 "net zero" commitments read as publication dates) from
    harvests taken before that guard existed."""
    caps = {c["ticker"]: str(c.get("as_of") or "")[:10] for c in universe.constituents()}
    files = dropped = kept = 0
    try:
        names = sorted(os.listdir(HARVEST_DIR))
    except OSError:
        return {"files": 0, "dropped": 0, "kept": 0}
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(HARVEST_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        cid = rec.get("company_id", "")
        cap = caps.get(cid, "")
        before = rec.get("events") or []
        after = [e for e in before
                 if _DATE_ISO.fullmatch(str(e.get("published_at", "")))
                 and (not cap or str(e.get("published_at", "")) <= cap)]
        for i, e in enumerate(after):
            e["event_id"] = "%s-harvest-%d" % (cid, i)
        rec["events"], rec["kept"] = after, len(after)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        files += 1
        dropped += len(before) - len(after)
        kept += len(after)
    return {"files": files, "dropped": dropped, "kept": kept}


#: Characters per token. `core.py` is frozen and returns the assistant string rather than the
#: API's usage block, so token counts here are ESTIMATED the same way `llm_cost.py` estimates
#: them — and reported as estimates, never as metered figures.
CHARS_PER_TOKEN = 3.7


COST_FILE = os.path.join(BASE_DIR, "data", "harvest_cost.json")


def load_cost_profile() -> Dict[str, Any]:
    """The last measured cost profile, read from disk. `{}` if never measured.

    Measuring rebuilds every prompt, which means 4 retrieval calls per company — cheap when the
    cache is warm and very slow when it is not. The result is a property of a completed sweep,
    not something a caller should pay for repeatedly, so `--cost` persists it and everything
    downstream reads the file."""
    try:
        with open(COST_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def cost_profile(sample: Optional[int] = None, *, use_cache: bool = True) -> Dict[str, Any]:
    """Measured LLM cost of ONE harvest sweep, per company. Feeds the cost model's yellow cells.

    Rebuilds the exact prompts (retrieval is cached, so this costs nothing) and measures them.
    Output is measured from the events actually stored, which makes it a FLOOR: facts the guards
    dropped were still generated and still billed, and this cannot see them.

    This is the number the cost model was missing. Its skeleton assumes 40 signals/company/month
    at 1500 tokens/signal, which describes a system where an LLM does the scoring. Ours does not
    — scoring is rule-based and costs zero tokens. The LLM cost sits entirely in GATHERING, and
    it is per sweep, not per signal."""
    cons = universe.constituents()
    stored = {}
    try:
        names = sorted(os.listdir(HARVEST_DIR))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(HARVEST_DIR, name), "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        stored[rec.get("company_id", "")] = rec

    targets = [c for c in cons if c["ticker"] in stored]
    if sample:
        targets = targets[:sample]

    rows, replayed = [], 0
    for c in targets:
        rec = stored[c["ticker"]]
        prompt_chars = rec.get("prompt_chars", 0)
        for _name, angle in (() if prompt_chars else ANGLES):
            try:
                ctx = rag.gather_context(_query_for(c, angle), k=TOP_K, use_cache=use_cache)
            except Exception:                                   # noqa: BLE001
                continue
            snippets = ctx.get("snippets") or []
            block = "\n\n".join(
                "[%d] %s\n%s\nURL: %s" % (i + 1, s.get("title", ""),
                                          (s.get("snippet") or "")[:700], s.get("url", ""))
                for i, s in enumerate(snippets))
            user = (_USER.replace("{company}", c.get("company", ""))
                    .replace("{ticker}", c["ticker"])
                    .replace("{industry}", c.get("industry", c.get("sector", "")))
                    .replace("{country}", c.get("country", ""))
                    .replace("{snippets}", block))
            prompt_chars += len(_SYSTEM) + len(user)
        out_chars = len(json.dumps({"events": [
            {k: e[k] for k in ("text", "published_at", "source_url")}
            for e in rec.get("events", [])]}))
        if not rec.get("prompt_chars"):
            replayed += 1
        rows.append({
            "company_id": c["ticker"],
            "calls": len(ANGLES),
            "prompt_tokens": round(prompt_chars / CHARS_PER_TOKEN),
            "output_tokens": round(out_chars / CHARS_PER_TOKEN),
            "events_kept": len(rec.get("events", [])),
        })

    if not rows:
        return {"companies": 0, "note": "no harvests on disk to measure"}
    n = len(rows)
    prompt = sum(r["prompt_tokens"] for r in rows) / n
    output = sum(r["output_tokens"] for r in rows) / n
    # The system prompt is byte-identical on every call and every company, so it is the part a
    # prefix cache serves. That is the cacheable SHARE, not an observed hit rate.
    cacheable = len(_SYSTEM) / CHARS_PER_TOKEN * len(ANGLES)
    return {
        "companies": n,
        "calls_per_company_per_sweep": len(ANGLES),
        "avg_prompt_tokens_per_company": round(prompt),
        "avg_output_tokens_per_company": round(output),
        "avg_total_tokens_per_company": round(prompt + output),
        "cacheable_prompt_share": round(100.0 * cacheable / prompt, 1) if prompt else 0.0,
        "avg_events_kept": round(sum(r["events_kept"] for r in rows) / n, 1),
        "tokens_per_kept_event": round((prompt + output) /
                                       max(1, sum(r["events_kept"] for r in rows) / n)),
        "replayed_retrievals": replayed,
        "basis": ("Estimated at %.1f chars/token — core.py is frozen and does not return the "
                  "API usage block. Output is measured from STORED events, so it is a floor: "
                  "facts the guards dropped were generated and billed and cannot be seen here."
                  % CHARS_PER_TOKEN),
        "rows": rows,
    }


def main(argv: List[str]) -> int:
    if "--cost" in argv:
        out = load_cost_profile() if "--cached" in argv else cost_profile()
        if out.get("companies") and "--cached" not in argv:
            os.makedirs(os.path.dirname(COST_FILE), exist_ok=True)
            with open(COST_FILE, "w", encoding="utf-8") as fh:
                json.dump({k: v for k, v in out.items() if k != "rows"}, fh, indent=1)
                fh.write("\n")
            print("(measured and saved to %s)\n" % os.path.relpath(COST_FILE, BASE_DIR))
        if not out.get("companies"):
            print(out.get("note", "nothing to measure"))
            return 1
        print("HARVEST COST — measured over %d harvested companies\n" % out["companies"])
        print("  LLM calls per company per sweep      %6d   (%d search angles)"
              % (out["calls_per_company_per_sweep"], len(ANGLES)))
        print("  Prompt tokens per company            %6d" % out["avg_prompt_tokens_per_company"])
        print("  Output tokens per company            %6d" % out["avg_output_tokens_per_company"])
        print("  TOTAL tokens per company per sweep   %6d" % out["avg_total_tokens_per_company"])
        print("  Cacheable prompt share               %6.1f%%  (the byte-identical system prompt)"
              % out["cacheable_prompt_share"])
        print("  Dated facts kept per company         %6.1f" % out["avg_events_kept"])
        print("  Tokens per kept fact                 %6d" % out["tokens_per_kept_event"])
        print("\n  %s" % out["basis"])
        print("\n  NOTE FOR THE COST MODEL: the scoring path costs ZERO tokens — it is rule-based.")
        print("  All LLM cost is in GATHERING, and it is per SWEEP, not per signal. The model's")
        print("  skeleton assumes 40 signals/co/month at 1500 tokens/signal, which describes a")
        print("  system where the model does the scoring. Ours does not.")
        return 0

    if "--refilter" in argv:
        out = refilter()
        print("re-filtered %d file(s): dropped %d, kept %d"
              % (out["files"], out["dropped"], out["kept"]))
        return 0

    # WHICH universe to sweep. Evidence is stored per TICKER in `data/harvest/`, so a company
    # that sits in both baskets is harvested once and both read it — the overlay is shared on
    # purpose, because a ticker's dated evidence is a fact about the company, not about which
    # list happens to name it.
    key = argv[argv.index("--universe") + 1] if "--universe" in argv else ""
    cons = {c["ticker"]: c for c in universe.constituents(universe.active_file(key=key))}
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
    deep = "--deep" in argv
    pace = float(argv[argv.index("--pace") + 1]) if "--pace" in argv else 0.0
    quality = "--quality" in argv
    # Delisted names are excluded from investable output by rule, so gathering fresh evidence
    # for them spends calls on companies that no longer trade. Explicitly naming one still
    # harvests it — the facts are real and someone may want them — but a sweep skips them.
    def _live(ts):
        skipped = [t for t in ts if cons[t].get("delisted")]
        if skipped:
            print("skipping %d delisted: %s\n" % (len(skipped), ", ".join(skipped)))
        return [t for t in ts if not cons[t].get("delisted")]

    if "--empty" in argv:
        counts = _scored_counts()
        targets = _live([t for t in sorted(cons) if counts.get(t, 0) == 0])
    elif "--all" in argv:
        targets = _live(sorted(cons))
    else:
        targets = [a for a in argv if not a.startswith("--") and a in cons]
    targets = targets[:limit]

    if not targets:
        print("Nothing to do. Pass a ticker, --empty, or --all (see --list).")
        return 1

    passes = len(ANGLES) * (1 + len(DEEP_YEARS)) if deep else len(ANGLES)
    print("harvesting %d company(ies) — %d search pass(es) x %d snippets each%s\n"
          % (len(targets), passes, TOP_K,
             ("  [DEEP: angles also scoped to " + ", ".join(DEEP_YEARS)
              + "; merged into what is already stored]") if deep else ""))
    total_kept = 0
    for t in targets:
        if pace and t != targets[0]:
            time.sleep(pace * 2)          # a longer gap between companies than between passes
        rec = harvest_company(cons[t], deep=deep, pace=pace, quality=quality)
        save(rec, replace="--replace" in argv)
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
