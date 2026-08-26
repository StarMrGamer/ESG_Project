"""brief.py — the pre-meeting brief a sell-side ESG analyst walks into a client call with.

WHAT THIS IS AND IS NOT. The brief prepares EVIDENCE; the analyst forms the view. It never says
buy, sell, hold, overweight or underweight, it never ranks the client's names against each other,
and it never suggests what to pitch — those would be HARD RULE 4, and the whole product argument
collapses the moment the tool starts picking. What it does instead is answer the four questions an
analyst is actually going to be asked in the room:

    1. What changed since we last spoke?          -> clients.delta(), against a stored snapshot
    2. Where do you disagree with the rating?     -> the engine record, unchanged
    3. Why might you be wrong?                    -> rationale.py's cons + sensitivity.py's margins
    4. What don't you know?                       -> the watch-outs, unrun screens, thin evidence

Question 3 is the one that makes this a sell-side tool rather than a marketing deck. A brief that
lists only reasons to agree gets the analyst ambushed by a portfolio manager who has done their
own work. So the case AGAINST every position is composed into the brief with the same weight as
the case for, and the objections section states the challenge in the client's voice.

NO LLM RUNS HERE. Every line is composed by rule from an engine record, so the brief replays
exactly with the run it names, and a client can be handed the same brief twice and get the same
document. That also means it costs nothing and cannot invent a fact, which is the property that
matters when the output is going in front of an institutional account.

Nothing in this module scores anything. It reads records, composes, and formats — `run_id` is
untouched, so the frozen N/M/K, the whitepaper figures and the anchored root all stay valid.
"""

from typing import Any, Dict, List, Optional

import clients
import rationale
import sensitivity

try:                                                        # optional — brief degrades without it
    import news as _news
except Exception:                                           # noqa: BLE001 - best-effort
    _news = None

try:
    import pipeline_counts as _pipeline
except Exception:                                           # noqa: BLE001 - best-effort
    _pipeline = None

DISCLAIMER = (
    "Evidence brief for an analyst's own use. It states where our dated evidence disagrees with "
    "the incumbent rating, what would overturn that, and what we do not know. It contains no "
    "recommendation, no target, no ranking and no view on price — those remain the analyst's, and "
    "this document is not investment advice.")

#: How the client is likely to phrase a challenge, by the kind of weakness the rules found. The
#: analyst is not being told what to think — they are being told what is coming.
_OBJECTION_VOICE = {
    "self_published": "Most of your evidence is the company's own PR. Why would I trust it?",
    "thin": "You are calling this on a handful of signals. That is not a position.",
    "coverage": "You have nothing on that pillar. How is that a complete ESG view?",
    "downward": "You are negative on a name the rating likes. Make that case to me.",
    "boundary": "You are a rounding error from the other side of your own line.",
    "stale": "Your newest evidence predates my holding period.",
    "provisional": "Your underlying data is marked provisional. Is it verified or not?",
    "mock": "Your baseline is a mock. What exactly are you disagreeing with?",
    "delisted": "This name is not listed any more. Why is it in your basket?",
    "financial": "The ESG story is fine. The earnings are not.",
    "generic": "Talk me through the case against your own verdict.",
}

#: Matched in order, most specific first. A con that trips nothing falls to `generic`, which is
#: deliberately the LAST resort rather than a catch-all — a brief full of identical challenges
#: teaches the analyst nothing, so `_objections` prefers a specific one wherever a position has it.
_OBJECTION_RULES = (
    ("delisted", ("delist", "went private", "membership stale")),
    ("mock", ("mock",)),
    ("provisional", ("provisional", "unrun", "not run", "screen_not_run")),
    ("stale", ("older than", "stale", "predates", "decay", "horizon")),
    ("self_published", ("self-published", "company-published", "company_pr", "press release",
                        "own publication")),
    ("downward", ("disagree downward", "more positive than the evidence", "not corroborated")),
    ("coverage", ("no evidence at all on", "silent there", "no evidence on")),
    ("thin", ("thin", "single signal", "few signals", "one signal", "only 1 ", "only 2 ",
              "only 3 ", "shrinkage")),
    ("boundary", ("boundary", "margin", "close to", "median")),
    ("financial", ("earnings", "net income", "revenue", "loss", "cash flow")),
)


def _objection_kind(text: str) -> str:
    t = (text or "").lower()
    for key, needles in _OBJECTION_RULES:
        if any(n in t for n in needles):
            return key
    return "generic"


def _nearest_line(position):
    """The boundary this verdict sits closest to, phrased as a measurement.

    `sensitivity._margins` returns `distance` (signed, value minus the line) and sorts nearest
    first. Reporting it matters more than it looks: "10 of 11 signals are load-bearing" reads as
    ten important findings when it actually means the company is balanced on a line, and the
    nearest margin is what tells those two apart.
    """
    margins = position.get("margins") or []
    if not margins:
        return ""
    m = margins[0]
    dist, val, line = m.get("distance"), m.get("value"), m.get("boundary")
    if not isinstance(dist, (int, float)):
        return ""
    # A COUNT is not a continuous measure — "signal count is 10.000" reads as a precision we do
    # not have. And a distance of exactly zero is not "above" or "below": a company sitting
    # precisely ON its own threshold is the single most useful thing this line can report, so it
    # is said outright rather than rounded into a direction.
    fmt = "%.0f" if m.get("key") == "signal_count" else "%.3f"
    where = ("exactly on it" if abs(dist) < 1e-9
             else "%+.3f, %s it" % (dist, m.get("side") or "from"))
    return ("Nearest line: %s is %s against the \u201c%s\u201d line at %s — %s."
            % (m.get("label") or m.get("key") or "value",
               fmt % (val if isinstance(val, (int, float)) else 0.0),
               m.get("boundary_name") or "boundary",
               fmt % (line if isinstance(line, (int, float)) else 0.0),
               where))


def _position(record: Dict[str, Any], row: Optional[Dict[str, Any]], run: Dict[str, Any],
              cfg: Optional[Dict[str, Any]], bucket_badge: Optional[Dict[str, Any]],
              with_flip: bool = True) -> Dict[str, Any]:
    """One covered name: the verdict, the case both ways, what would flip it, and its headlines."""
    case = rationale.build(record, row)
    cid = record.get("company_id", "")

    flip, flip_error = None, ""
    if with_flip:
        try:
            # The keyword is `config`, not `cfg`. Getting that wrong raised a TypeError that the
            # old blanket `except` turned into an empty margin list — which on screen reads as
            # "this verdict sits near no boundary", a confident and wrong claim rather than an
            # error. So a failure is RECORDED on the position instead of silently looking normal.
            flip = sensitivity.flip_analysis(run, cid, config=cfg)
        except Exception as exc:                            # noqa: BLE001 - brief must still build
            flip, flip_error = None, "sensitivity unavailable: %s" % exc

    headlines = []
    if _news is not None:
        stored = _news.load(cid) or {}
        for item in (stored.get("items") or [])[:3]:
            headlines.append({"title": item.get("title", ""), "url": item.get("source_url", ""),
                              "source": item.get("source", ""),
                              "published_at": item.get("published_at", "")})

    return {
        "company_id": cid,
        "company": record.get("company", ""),
        "country": record.get("country", ""),
        "industry": record.get("industry", ""),
        "label": record.get("label", ""),
        "label_display": record.get("label_display", ""),
        "disagreement": record.get("disagreement"),
        "momentum": record.get("composite_momentum"),
        "confidence": record.get("composite_confidence"),
        "signal_count": record.get("signal_count"),
        "momentum_percentile": record.get("momentum_percentile"),
        "rating_percentile": record.get("lseg_percentile"),
        "incumbent_notch": record.get("incumbent_notch"),
        "delisted": bool(record.get("delisted")),
        "summary": case.get("summary", ""),
        "case_for": (case.get("esg") or {}).get("pros") or [],
        "case_against": (case.get("esg") or {}).get("cons") or [],
        "financial": case.get("financial") or {},
        "watch_outs": case.get("watch_outs") or [],
        "pipeline": bucket_badge or {},
        "headlines": headlines,
        "margins": (flip or {}).get("margins") or [],
        "load_bearing": (flip or {}).get("load_bearing_count"),
        "flip_note": (flip or {}).get("verdict_note", "") or flip_error,
        "flip_error": flip_error,
    }


def _objections(positions: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    """What the client will push on, in their words, with the dated answer beside it.

    Sourced entirely from the cons and watch-outs the rules already produced — nothing here is
    generated. Where a position has several weaknesses the SPECIFIC one wins over the generic one,
    because "talk me through the case against" repeated six times tells an analyst nothing they
    could not have guessed. A position with no weakness found is omitted, and the section says so
    rather than implying there were none to find.
    """
    out = []
    for p in positions:
        weaknesses = list(p.get("case_against") or []) + list(p.get("watch_outs") or [])
        if not weaknesses:
            continue
        scored = [(w, _objection_kind(w)) for w in weaknesses]
        specific = next(((w, k) for w, k in scored if k != "generic"), None)
        answer, kind = specific or scored[0]
        out.append({
            "company_id": p["company_id"], "company": p["company"],
            "challenge": _OBJECTION_VOICE.get(kind, _OBJECTION_VOICE["generic"]),
            "kind": kind,
            "our_answer": answer,
            "what_would_move_it": _nearest_line(p),
            "evidence_n": p.get("signal_count"),
            "other_weaknesses": max(0, len(weaknesses) - 1),
        })
    # A specific challenge outranks a generic one; within that, the better-evidenced name first —
    # it is the position the client is most likely to have done their own work on.
    out.sort(key=lambda o: (o["kind"] == "generic", -(o.get("evidence_n") or 0)))
    return out[:limit]


def _unknowns(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What we cannot tell this client yet. Stated, not omitted.

    An analyst who opens with their own gaps is more credible than one who waits to be caught in
    them, and every item here is a rule-derived fact rather than a hedge.
    """
    out = []
    for p in positions:
        if not p.get("signal_count"):
            out.append({"company": p["company"], "company_id": p["company_id"],
                        "gap": "No dated evidence at all. We are not disagreeing with the rating "
                               "here — we have nothing to disagree with it about."})
        fin = p.get("financial") or {}
        if (fin.get("verdict") or "").lower() == "unknown":
            out.append({"company": p["company"], "company_id": p["company_id"],
                        "gap": "Financial read is unknown, which is not the same as weak — the "
                               "cells behind it are blank, not bad."})
        for w in p.get("watch_outs") or []:
            if "provisional" in w.lower() or "unrun" in w.lower() or "not run" in w.lower():
                out.append({"company": p["company"], "company_id": p["company_id"], "gap": w})
    return out[:10]


def build(client: Dict[str, Any], run: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None,
          cfg: Optional[Dict[str, Any]] = None, with_flip: bool = True) -> Dict[str, Any]:
    """The whole brief for one client against one run. Pure: same inputs, same document."""
    client = client or {}
    metadata = metadata or {}
    coverage = list(client.get("coverage") or [])
    by_id = {r.get("company_id"): r for r in (run or {}).get("records") or []}

    badges = {}
    counts = None
    if _pipeline is not None:
        try:
            subset = {"records": [by_id[c] for c in coverage if c in by_id],
                      "company_count": len(coverage)}
            counts = _pipeline.counts(subset, metadata, cfg)
            buckets = _pipeline.bucket_of(counts)
            badges = {c: _pipeline.bucket_badge(buckets.get(c, ""), counts) for c in coverage}
        except Exception:                                   # noqa: BLE001 - best-effort
            counts, badges = None, {}

    positions = []
    missing = []
    for cid in coverage:
        rec = by_id.get(cid)
        if not rec:
            missing.append(cid)
            continue
        positions.append(_position(rec, metadata.get(cid), run, cfg, badges.get(cid), with_flip))

    # Ordered by the size of the disagreement, because that is what the meeting is about — NOT by
    # attractiveness, and explicitly not a ranking of the names against each other.
    positions.sort(key=lambda p: -abs(p.get("disagreement") or 0))

    d = clients.delta(client, run)
    return {
        "client": clients.summary(client),
        "brief_note": client.get("brief_note", ""),
        "run_id": (run or {}).get("run_id", ""),
        "as_of": (run or {}).get("as_of", ""),
        "delta": d,
        "open_follow_ups": clients.open_follow_ups(client),
        "positions": positions,
        "objections": _objections(positions),
        "unknowns": _unknowns(positions),
        "origination": counts,
        "not_covered": missing,
        "disclaimer": DISCLAIMER,
        "no_llm": True,
    }


# --------------------------------------------------------------------------------------------- #
# export — analysts live in documents, not dashboards
# --------------------------------------------------------------------------------------------- #

def _plural(n, word):
    n = n or 0
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _f(v, spec="%+.3f"):
    return (spec % v) if isinstance(v, (int, float)) else "—"


def to_markdown(brief: Dict[str, Any]) -> str:
    """The brief as a document. Sections are numbered as they are EMITTED, not by a fixed plan —
    an empty section is dropped rather than printed as a heading with nothing under it, and the
    numbering must not skip when that happens."""
    c = brief.get("client") or {}
    L: List[str] = []
    n = [0]

    def head(title):
        n[0] += 1
        L.append("")
        L.append("## %d · %s" % (n[0], title))
        L.append("")

    L.append("# Client brief — %s" % (c.get("name") or "—"))
    L.append("")
    L.append("%s · %s · mandate: %s  " % (c.get("account_type") or "—", c.get("desk") or "—",
                                          c.get("mandate") or "—"))
    L.append("Run `%s` · evidence as of %s · %d of %d names covered  "
             % (brief.get("run_id", ""), brief.get("as_of", ""),
                len(brief.get("positions") or []), (c.get("coverage_n") or 0)))
    L.append("Last met %s" % (c.get("last_met") or "never — first meeting"))
    if brief.get("brief_note"):
        L.append("")
        L.append("> %s" % brief["brief_note"])

    d = brief.get("delta") or {}
    head("What changed since you last spoke")
    if not d.get("has_baseline"):
        L.append(d.get("note") or "No prior meeting on record.")
    elif not d.get("changes"):
        L.append("Nothing material moved across the %d covered names since %s."
                 % (d.get("covered") or 0, d.get("since") or "—"))
    else:
        L.append("Since %s (run `%s`):" % (d.get("since") or "—", d.get("since_run") or ""))
        L.append("")
        L.append("| Company | What moved | Evidence |")
        L.append("|---|---|---|")
        for ch in d["changes"]:
            L.append("| %s | %s | %s → %s |"
                     % (ch["company"], ch["note"], ch.get("signals_from"),
                        _plural(ch.get("signals_to"), "signal")))
        L.append("")
        L.append("%d of %d names unchanged." % (d.get("unchanged") or 0, d.get("covered") or 0))

    fu = brief.get("open_follow_ups") or []
    if fu:
        head("Still owed from last time")
        for f in fu:
            L.append("- %s  *(since %s)*" % (f.get("text", ""), f.get("since", "")))

    head("Where we are away from the rating")
    L.append("| Company | Our read | Rating pct | Disagreement | Confidence | Evidence |")
    L.append("|---|---|---|---|---|---|")
    for p in brief.get("positions") or []:
        L.append("| %s%s | %s | %s | %s | %s | %s |" % (
            p["company"], " *(delisted)*" if p.get("delisted") else "",
            p.get("label_display") or "—",
            _f((p.get("rating_percentile") or 0) * 100, "%.0f"),
            _f(p.get("disagreement")), _f(p.get("confidence"), "%.2f"),
            _plural(p.get("signal_count"), "signal")))
    L.append("")
    L.append("Ordered by the size of the disagreement. This is not a ranking of the names against "
             "each other and carries no view on any of them.")

    obj = brief.get("objections") or []
    head("Why we might be wrong")
    if not obj:
        L.append("The rules surfaced no specific challenge on these names. That is not the same "
                 "as there being none.")
    for o in obj:
        L.append("**%s** — *“%s”*  " % (o["company"], o["challenge"]))
        L.append("%s  " % o["our_answer"])
        if o.get("what_would_move_it"):
            L.append("%s" % o["what_would_move_it"])
        L.append("")

    unk = brief.get("unknowns") or []
    if unk:
        head("What we do not know")
        for u in unk:
            L.append("- **%s** — %s" % (u["company"], u["gap"]))

    orig = brief.get("origination")
    if orig:
        head("Origination across this book")
        L.append("N %s issuers · M %s bond-ready · K %s review list"
                 % (orig.get("N"), orig.get("M"), orig.get("K")))
        L.append("")
        L.append("Buckets are disjoint by rule: M excludes anything already issuing, K is the "
                 "explicit remainder we disagree about but cannot place.")

    if brief.get("not_covered"):
        head("Not in this run")
        L.append("No engine record for: %s." % ", ".join(brief["not_covered"]))

    L.append("")
    L.append("---")
    L.append("")
    L.append("*%s*" % brief.get("disclaimer", DISCLAIMER))
    L.append("")
    L.append("*Composed by rule from run `%s`. No language model was used, so this document "
             "replays identically from the same run.*" % brief.get("run_id", ""))
    return "\n".join(L)


if __name__ == "__main__":                                   # pragma: no cover - developer CLI
    import sys
    import company_metadata
    import engine
    import harvest
    import universe

    want = sys.argv[1] if len(sys.argv) > 1 else None
    meta = company_metadata.load(demo=False)
    run = engine.run_engine(harvest.apply_overlay(universe.constituents()), metadata=meta)
    book = clients.load_all()
    if want:
        book = [c for c in book if c.get("client_id") == want or c.get("name", "").lower().startswith(want.lower())]
    if not book:
        print("no such client")
        raise SystemExit(1)
    print(to_markdown(build(book[0], run, meta)))
