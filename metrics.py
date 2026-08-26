"""
metrics.py — pure aggregation for the monitoring dashboard.
===========================================================
Turns a list of universe constituents (the base DB, optionally filtered to one industry /
country) into the numbers the command-center panels show: the **average ESG of the filtered
set**, the four **pillar-momentum** cards (E / S / G / Digital-AI), the **hidden-winners**
ranking vs the peer average, and a focused company's **classification** + signals.

No Streamlit, no network, no LLM — just arithmetic over the optional numeric fields each
constituent MAY carry, so it imports cleanly in tests and degrades to None/[] when the data
isn't there yet (the starter universe has no numbers until the real basket is dropped in).

PER-CONSTITUENT SCHEMA (all optional beyond identity; absent -> that panel shows "awaiting data"):
    esg_score: number            # the static Layer-A ESG score (0–100, higher = better)
    esg_as_of: "2023"            # vintage of that static score
    esg_cagr_2019_2023: "+5.2%"  # the foundation momentum metric (5-yr ESG-score CAGR)
    momentum: { environment, social, governance, digital_ai }   # live/90-day % per pillar
    live_signals: { ai_hiring_surge, green_patents, carbon_disclosure,
                    controversy_flags, board_ai_policy }          # the right-rail signals
    price_change_90d: "+9.4%"    # optional price panel (illustrative, demo only)
    market: { currency, price, prev_close, open, high, low, market_cap, pe_ratio,
              dividend_yield, week52_high, week52_low, as_of }   # optional financial snapshot
    news: [{ title, source, date }]                              # optional illustrative headlines
    analyst_coverage: { analysts, as_of }                        # optional sell-side breadth (count only)
                       # market / news / analyst_coverage are ILLUSTRATIVE, demo-only (HARD RULE 2):
                       # the real evidence universe never carries them -> panels show "awaiting data".
"""

import re
from urllib.parse import quote_plus

PILLARS = ("environment", "social", "governance", "digital_ai")
PILLAR_LABEL = {"environment": "Environment", "social": "Social",
                "governance": "Governance", "digital_ai": "Digital / AI"}


def _as_quarter(as_of):
    """Render a universe `as_of` as a quarter label: '2026-06-25' -> 'Q2 2026';
    an already-quarterly string ('Q1 2026') is returned unchanged; '' -> ''. [1.9]"""
    s = (as_of or "").strip()
    if not s:
        return ""
    if s[:1].lower() == "q":
        return s
    m = re.match(r"(\d{4})-(\d{1,2})", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        return f"Q{(month - 1) // 3 + 1} {year}"
    return s


def universe_banner(uni, top_n=5):
    """One-line universe banner, e.g. 'Q2 2026 · 52 companies · Top 5' — quarter + count derived
    dynamically from the active universe's as_of / constituents. [1.9]"""
    uni = uni or {}
    n = len(uni.get("constituents") or [])
    parts = [p for p in (_as_quarter(uni.get("as_of")),
                         f"{n} companies" if n else "", f"Top {top_n}") if p]
    return " · ".join(parts)

_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def num(v):
    """Coerce 12 / '12' / '+12%' / '−2%' -> float, else None. Tolerant of the unicode minus."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("−", "-").strip()
    m = _NUM_RE.search(s)
    return float(m.group(0)) if m else None


def _momentum(c, pillar):
    return num((c.get("momentum") or {}).get(pillar))


def has_numbers(constituents):
    """True if ANY constituent carries usable numeric ESG/momentum data (else 'awaiting data')."""
    for c in constituents or []:
        if num(c.get("esg_score")) is not None:
            return True
        if any(_momentum(c, p) is not None for p in PILLARS):
            return True
    return False


def esg_breakdown(company):
    """The E/S/G/overall 0-100 breakdown a demo constituent carries, or None (evidence names)."""
    bd = (company or {}).get("esg_breakdown")
    return bd if isinstance(bd, dict) and bd else None


def average_esg(constituents):
    """Mean static ESG score across the (filtered) set — the headline 'avg ESG of the industry'.
    Returns (avg, n) where n = how many constituents actually carried a score; (None, 0) if none."""
    vals = [num(c.get("esg_score")) for c in (constituents or [])]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, 0
    return round(sum(vals) / len(vals), 1), len(vals)


def trend_label(value):
    """Map a pillar momentum % onto the mockup's arrow + word (fast riser / accelerating / …)."""
    if value is None:
        return "·", "awaiting data"
    if value >= 25:
        return "↑", "fast riser"
    if value >= 8:
        return "↑", "accelerating"
    if value > -3:
        return "→", "stable"
    if value > -12:
        return "↓", "softening"
    return "↓", "declining"


def pillar_momentum(constituents):
    """Average momentum per pillar across the filtered set. Returns an ordered list of dicts:
    [{key,label,value,arrow,trend,fast}] (value None when no data). `fast` flags the top riser."""
    out = []
    best_key, best_val = None, None
    for p in PILLARS:
        vals = [_momentum(c, p) for c in (constituents or [])]
        vals = [v for v in vals if v is not None]
        avg = round(sum(vals) / len(vals), 1) if vals else None
        arrow, trend = trend_label(avg)
        out.append({"key": p, "label": PILLAR_LABEL[p], "value": avg, "arrow": arrow,
                    "trend": trend, "fast": False,
                    # `basis` names the SCALE, not the quality: "numeric" is a momentum percent
                    # from a constituent's own fields, "evidence" is a -1..+1 direction consensus
                    # from the engine (see `pillar_momentum_from_records`). The card renders a
                    # different unit for each, so it must never have to guess which it holds.
                    "basis": "numeric", "n": len(vals), "of": len(constituents or [])})
        if avg is not None and (best_val is None or avg > best_val):
            best_key, best_val = p, avg
    for row in out:                       # highlight the strongest riser (the orange card)
        if row["key"] == best_key and best_val is not None and best_val > 0:
            row["fast"] = True
    return out


#: Engine component key -> the board's pillar key. The engine scores on E/S/G/DIGITAL (the
#: Build-Spec component names); the board has always spoken environment/social/governance/
#: digital_ai. Nothing is renamed on either side — this is the join between them.
_COMPONENT_PILLAR = {"E": "environment", "S": "social", "G": "governance", "DIGITAL": "digital_ai"}


def consensus_trend(value, n=0):
    """Arrow + word for an EVIDENCE-derived pillar reading on the -1..+1 consensus scale.

    Deliberately NOT `trend_label`: that one reads a momentum PERCENT, where 8 means accelerating
    and 25 means a fast riser. A direction consensus tops out at 1.0, so passing it through the
    percent thresholds would report every real company as "stable" — a wrong word attached to a
    real number, which is worse than the blank it replaces."""
    if value is None or not n:
        return "·", "no evidence yet"
    if value >= 0.6:
        return "↑", "evidence agrees · improving"
    if value >= 0.2:
        return "↑", "leans improving"
    if value > -0.2:
        return "→", "evidence is mixed"
    if value > -0.6:
        return "↓", "leans deteriorating"
    return "↓", "evidence agrees · deteriorating"


def pillar_momentum_from_records(records):
    """Pillar cards derived from the ENGINE's per-component momentum, for universes whose
    constituents carry no numeric `momentum` block (i.e. the real ASEAN basket).

    Why this exists: the engine already computes a per-component direction consensus for every
    company it scores, and the board was reading a constituent field that only the FICTIONAL demo
    set carries. So four cards said "awaiting data" beside 44 companies' worth of environment
    evidence that had already been scored. Nothing here is new analysis and nothing is
    fabricated — it is the same rule-derived number the matrix and the quadrant labels use.

    Returns `pillar_momentum`'s shape plus:
      * `basis`  — "evidence" (this function) vs "numeric" (`pillar_momentum`), so the UI can
                   label the scale rather than silently showing -1..+1 where a percent used to be;
      * `n`      — how many companies in view actually carried evidence for that pillar. A mean
                   over 3 names and a mean over 44 are not the same claim, and the card says which.

    `value` is the mean direction consensus across the companies that HAVE evidence for the
    pillar — companies with none are left out rather than counted as zero, because "no evidence"
    and "evidence says flat" are different claims and averaging them together erases the first.
    """
    rows = list((records or {}).values()) if isinstance(records, dict) else list(records or [])
    out, best_key, best_val = [], None, None
    for pillar in PILLARS:
        vals = []
        for rec in rows:
            comps = (rec or {}).get("components") or {}
            for ckey, cval in comps.items():
                if _COMPONENT_PILLAR.get(str(ckey).upper()) != pillar:
                    continue
                v = num(cval.get("momentum") if isinstance(cval, dict) else cval)
                if v is not None:
                    vals.append(v)
        avg = round(sum(vals) / len(vals), 3) if vals else None
        arrow, trend = consensus_trend(avg, len(vals))
        out.append({"key": pillar, "label": PILLAR_LABEL[pillar], "value": avg,
                    "arrow": arrow, "trend": trend, "fast": False,
                    "basis": "evidence", "n": len(vals), "of": len(rows)})
        if avg is not None and (best_val is None or avg > best_val):
            best_key, best_val = pillar, avg
    for row in out:
        if row["key"] == best_key and best_val is not None and best_val > 0:
            row["fast"] = True
    return out


def pillar_momentum_for_record(record):
    """The four pillar readings for ONE company, off its own engine record.

    `pillar_momentum_from_records` averages across every company in view — which is the right
    number for the four cards when nothing is focused, and the WRONG one the moment a company's
    name is printed in the middle of them. The hub was drawing the 52-company average and
    labelling it with the focused company, so the readings never changed when you changed
    company. Same shape, same rule-derived numbers, one record.

    `n` here is how many dated signals sit behind THAT pillar for this company, and `of` is
    deliberately None: component counts do NOT partition the record total (RHB Bank is E 9, G 14
    against a total of 14, because one signal can carry more than one component), so printing
    "9 of 14" would state a share that does not exist. `scope` says which question the row
    answers, because "the average of 46 companies" and "this company" are different claims and
    the tooltip has to tell them apart. A pillar the company has no evidence for stays None —
    never zero, which would read as "measured, and flat".
    """
    r = record if isinstance(record, dict) else {}
    comps = r.get("components") or {}
    out, best_key, best_val = [], None, None
    for pillar in PILLARS:
        val, n = None, 0
        for ckey, cval in comps.items():
            if _COMPONENT_PILLAR.get(str(ckey).upper()) != pillar:
                continue
            if isinstance(cval, dict):
                val = num(cval.get("momentum"))
                n = int(num(cval.get("signal_count")) or 0)
            else:
                val = num(cval)
        arrow, trend = consensus_trend(val, n)
        out.append({"key": pillar, "label": PILLAR_LABEL[pillar],
                    "value": round(val, 3) if val is not None else None,
                    "arrow": arrow, "trend": trend, "fast": False,
                    "basis": "evidence", "scope": "company", "n": n, "of": None})
        if val is not None and (best_val is None or val > best_val):
            best_key, best_val = pillar, val
    for row in out:
        if row["key"] == best_key and best_val is not None and best_val > 0:
            row["fast"] = True
    return out


def signals_from_record(record, limit=8):
    """Right-rail rows for a company whose signals were scored by the ENGINE, in `live_signals`'
    `[{label, value, tone}]` shape.

    Why: `live_signals` reads a `live_signals` block that only the FICTIONAL demo constituents
    carry, so a real company with three scored, dated, sourced signals rendered as "0 signals" —
    an absence reported where evidence existed. The rail now falls back to the engine's own
    signals, which are the ones the momentum and the quadrant label were computed from.

    Newest first, because the decay model weights recent evidence most and a reader scanning the
    rail should meet the signals that actually moved the number.
    """
    rows = []
    for sig in sorted((record or {}).get("signals") or [],
                      key=lambda s: str(s.get("published_at") or ""), reverse=True)[:limit]:
        sub = str(sig.get("subcomponent") or sig.get("component") or "signal").replace("_", " ")
        direction = num(sig.get("direction")) or 0
        tone = "good" if direction > 0 else ("warn" if direction < 0 else "neutral")
        date = str(sig.get("published_at") or "")[:10] or "undated"
        # The source type is on the row because it is what caps the confidence: a company press
        # release is graded 0.5 by rule, and a reader who cannot see that has no way to tell a
        # regulator action from a self-published claim.
        stype = str(sig.get("source_type") or "unknown").replace("_", " ")
        rows.append({"label": f"{sub} · {stype}", "value": date, "tone": tone})
    return rows


#: Engine quadrant -> the card's tone. `hidden_winners` is the only one drawn as good news; the
#: two negative quadrants are drawn as warnings. `consensus` and `future_leaders` are neutral
#: because "the rating and the evidence agree" is not a verdict about the company at all.
_ENGINE_TONE = {
    "hidden_winners": "good",
    "future_leaders": "neutral",
    "consensus": "neutral",
    "overrated_leaders": "bad",
    "value_traps": "bad",
}


def classify_from_record(record):
    """The classification card read from a company's ENGINE record. {label, tone, line} or None.

    `classify` reads the `momentum` block that only the FICTIONAL demo set carries, so once the
    real basket landed EVERY real company fell through to "AWAITING DATA" — printed directly
    above a rationale panel already naming the engine's verdict for the same company, on the same
    screen. That is the pillar-card false negative again, one widget over.

    Nothing new is claimed here: the label is the engine's own `label_display` and every number is
    copied off the record. Returns None when the record cannot support a sentence, so the caller
    keeps saying "awaiting data" rather than inventing a verdict to fill the box.
    """
    r = record if isinstance(record, dict) else {}
    label = _clean(r.get("label_display"))
    if not label:
        return None
    n = int(num(r.get("signal_count")) or 0)
    mom, conf = num(r.get("composite_momentum")), num(r.get("composite_confidence"))
    dis = num(r.get("disagreement"))
    ours, theirs = num(r.get("momentum_percentile")), num(r.get("lseg_percentile"))
    def _ord(v):
        i = round(v * 100)
        suffix = "th" if 10 <= i % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
        return f"{i}{suffix}"

    parts = []
    if mom is not None and n:
        parts.append(f"Evidence momentum {mom:+.2f} on {n} dated signal{'' if n == 1 else 's'}"
                     + (f", confidence {conf:.2f}" if conf is not None else "") + ".")
    if dis is not None and ours is not None and theirs is not None:
        parts.append(f"Its published score ranks it {_ord(theirs)} of the basket; the "
                     f"evidence ranks it {_ord(ours)} \u2014 a signed gap of {dis:+.2f}.")
    if not parts:
        return None
    return {"label": label, "tone": _ENGINE_TONE.get(_clean(r.get("label")).lower(), "neutral"),
            "line": " ".join(parts)}


def fmt_pct(value):
    """A signed percent string for a card, e.g. 12 -> '+12%', -2 -> '-2%', None -> '—'."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    v = int(value) if float(value).is_integer() else value
    return f"{sign}{v}%"


def hidden_winners(constituents, *, signal="digital_ai", top_n=5, new_tickers=()):
    """Rank the filtered set by a live signal (default Digital/AI momentum) — the companies whose
    live trajectory diverges from the stale rating. Returns [{company,ticker,value,is_new}] sorted
    desc, plus the peer-average ESG for the panel subtitle. Skips names with no signal.

    ``new_tickers`` is the set of just-focused tickers the caller tracks in session state; a row is
    flagged ``is_new`` by membership — we never mutate (and leak) a `_new` flag onto cached dicts."""
    new = set(new_tickers or ())
    rows = []
    for c in constituents or []:
        v = _momentum(c, signal)
        if v is None:
            continue
        rows.append({"company": c.get("company", "—"), "ticker": c.get("ticker", ""),
                     "value": v, "is_new": c.get("ticker") in new})
    rows.sort(key=lambda r: r["value"], reverse=True)
    peer_avg, n = average_esg(constituents)
    return rows[:top_n], peer_avg, n


def hidden_winners_from_records(constituents, records, *, top_n=5, new_tickers=()):
    """The same panel, ranked by the ENGINE's signed disagreement instead of a Digital/AI number.

    `hidden_winners` ranks on `_momentum(c, "digital_ai")`, a field only the FICTIONAL demo set
    carries, so on the real basket the panel read "Nothing to rank in this filter yet" beside a
    matrix that had already placed four companies in the hidden-winner quadrant. Same false
    negative as the pillar cards and the classification strip, one panel over.

    The bar here is `disagreement` — our evidence percentile minus the rating's — which is the
    quantity the panel was always about: how far a company sits from where its rating puts it.
    Only companies the engine actually labelled `hidden_winners` are listed, so the panel's title
    stays true; ranking every name by disagreement would turn it into the ranking this project
    refuses to publish. Returns `hidden_winners`' shape.
    """
    new = set(new_tickers or ())
    # The board's engine block is a TRIMMED record — it carries `company_id` and the scores, not
    # the display name — so the name comes from the constituents we were handed. Falling back to
    # the ticker put "KLSE:RHBBANK" where a reader expects "RHB Bank Bhd".
    names = {c.get("ticker"): c.get("company") for c in (constituents or []) if c.get("ticker")}
    recs = list((records or {}).values()) if isinstance(records, dict) else list(records or [])
    rows = []
    for rec in recs:
        tk = (rec or {}).get("company_id")
        if tk not in names or (rec or {}).get("label") != "hidden_winners":
            continue
        v = num(rec.get("disagreement"))
        if v is None:
            continue
        rows.append({"company": rec.get("company") or names.get(tk) or tk, "ticker": tk,
                     "value": round(v, 3), "is_new": tk in new})
    rows.sort(key=lambda r: r["value"], reverse=True)
    peer_avg, n = average_esg(constituents)
    return rows[:top_n], peer_avg, n


def momentum_series(constituents, *, points=10):
    """An illustrative 90-day trajectory per pillar, interpolated from a shared baseline to each
    pillar's CURRENT average momentum (we don't hold a daily series). Returns {pillar: [floats]}
    for the line chart; empty when there's no momentum data. Clearly illustrative, not a backtest."""
    rows = pillar_momentum(constituents)
    series = {}
    for row in rows:
        if row["value"] is None:
            continue
        end = row["value"]
        # ease from a small opposite-leaning baseline to `end` so lines fan out like the mockup
        start = -end * 0.35
        divisor = max(points - 1, 1)  # guard points<=1 against ZeroDivisionError
        series[row["key"]] = [round(start + (end - start) * (i / divisor), 2)
                              for i in range(points)]
    return series


def compare_companies(companies):
    """Extract comparable numeric series from a list of Contract B dicts for the compare graphs.

    Pure (no network/LLM). Grounded ONLY in the data: a missing/unknown field is None — never
    fabricated (HARD RULE 2), so evidence-only names simply render 'awaiting data'. Returns
    {rows:[{company,ticker,esg_score:float|None,momentum:{E,S,G:float|None}}],
     pillars:['E','S','G'], has_momentum:bool, has_score:bool}."""
    rows = []
    for c in (companies or []):
        c = c if isinstance(c, dict) else {}
        la = c.get("layer_a") if isinstance(c.get("layer_a"), dict) else {}
        lb = c.get("layer_b") if isinstance(c.get("layer_b"), dict) else {}
        mom = lb.get("momentum") if isinstance(lb.get("momentum"), dict) else {}

        def _mag(k, mom=mom):
            cell = mom.get(k)
            return num(cell.get("magnitude")) if isinstance(cell, dict) else None

        rows.append({
            "company": c.get("company", "unknown"),
            "ticker": c.get("ticker", "unknown"),
            "esg_score": num(la.get("esg_score_static")),
            "momentum": {k: _mag(k) for k in ("E", "S", "G")},
        })
    has_momentum = any(v is not None for r in rows for v in r["momentum"].values())
    has_score = any(r["esg_score"] is not None for r in rows)
    return {"rows": rows, "pillars": ["E", "S", "G"],
            "has_momentum": has_momentum, "has_score": has_score}


def classify(company):
    """Classification verdict for ONE focused company (the center 'HIDDEN WINNER' panel).

    Reads its Digital/AI momentum + controversy flags. Returns {label, tone, line}. Never a
    buy/sell/hold — it flags the GAP between the stale rating and the live signal."""
    d = _momentum(company, "digital_ai")
    g = _momentum(company, "governance")
    flags = num((company.get("live_signals") or {}).get("controversy_flags")) or 0
    score = num(company.get("esg_score"))
    as_of = (company.get("esg_as_of") or "").strip()

    if d is not None and d >= 15 and flags < 1:
        label, tone = "HIDDEN WINNER", "good"
    elif (d is not None and d <= -5) or flags >= 1:
        label, tone = "WATCH — GAP RISK", "bad"
    elif d is not None:
        label, tone = "IN LINE", "neutral"
    else:
        return {"label": "AWAITING DATA", "tone": "neutral",
                "line": "No live momentum yet — add data or run a deep dive to compete."}

    bits = []
    if score is not None:
        bits.append(f"Rating stale ({score}{', ' + as_of if as_of else ''})")
    if d is not None:
        bits.append(f"live Digital/AI {fmt_pct(d)}")
    if g is not None:
        bits.append(f"Governance {fmt_pct(g)}")
    line = "; ".join(bits) + ". We flag the gap — never buy / sell / hold."
    return {"label": label, "tone": tone, "line": line}


# --------------------------------------------------------------------------- #
#  EVIDENCE MODE  (real universe has NO numbers yet — derive a GROUNDED leadership
#  score from the ratings each `esg_basis` actually CITES; never invents a figure)
# --------------------------------------------------------------------------- #
_MSCI_PTS = {"AAA": 30, "AA": 24, "A": 16, "BBB": 10, "BB": 6, "B": 3, "CCC": 1}
_MSCI_SCALE = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC")  # longest-first so the regex is greedy-correct
_MSCI_ALT = "|".join(_MSCI_SCALE)


def _extract_msci_rating(basis):
    """The CURRENT MSCI letter grade an `esg_basis` actually CITES, read case-sensitively — real
    ratings are written uppercase ('AA', 'A', 'BBB'); the English article 'a' is not, so it is
    ignored. A trajectory names the current rating LAST ('BBB->A', "from 'B' to 'BB'",
    'BBB -> A -> AA'), so we take the rating after the FINAL arrow/'to' transition. Returns the
    rating string, or None when the text names no letter grade (never fabricates one)."""
    text = basis or ""
    mi = re.search(r"(?i)\bmsci(?:\s+esg)?", text)
    if not mi:
        return None
    tail = text[mi.end():mi.end() + 90]  # wide enough to span a multi-hop 'X -> Y -> Z' chain
    # every arrow/'to' transition's target, in order; the LAST is the most recent (current) rating
    trans = re.findall(rf"(?:->|→|\bto\b)\s*['\"]?\s*\b({_MSCI_ALT})\b", tail)
    if trans:
        return trans[-1]
    first = re.search(rf"\b({_MSCI_ALT})\b", tail)  # single rating; the article 'a' never matches
    return first.group(1) if first else None


def parse_evidence(basis, confidence=""):
    """Extract the ESG credentials a constituent's `esg_basis` text actually NAMES (MSCI rating,
    DJSI/S&P Yearbook, CDP A-List, FTSE4Good, Sustainalytics risk, GRESB, national ESG indices) and
    sum them into a 0–100 leadership score. This is GROUNDED extraction from cited evidence — it
    emits a credential only when its keyword appears in the text — not a fabricated ESG figure.
    Returns {score, rating, credentials:[{label,value,tone}]}."""
    low = (basis or "").lower()
    creds, score, rating = [], 0, None

    rating = _extract_msci_rating(basis)
    if rating is None and "msci" in low and "leader" in low:
        rating = "AA"
    if rating:
        score += _MSCI_PTS.get(rating, 0)
        creds.append({"label": "MSCI ESG", "value": rating,
                      "tone": "good" if rating in ("AAA", "AA", "A") else "warn"})

    if "djsi world" in low or "sustainability index world" in low:
        score += 25; creds.append({"label": "DJSI", "value": "World", "tone": "good"})
    elif "djsi asia" in low or ("dow jones sustainability" in low and "asia" in low):
        score += 18; creds.append({"label": "DJSI", "value": "Asia Pacific", "tone": "good"})
    elif "djsi" in low or "dow jones sustainability" in low:
        score += 15; creds.append({"label": "DJSI", "value": "Member", "tone": "good"})
    if "yearbook" in low:
        score += 12; creds.append({"label": "S&P Yearbook", "value": "Member", "tone": "good"})
    if "gold class" in low:
        score += 14; creds.append({"label": "S&P Global", "value": "Gold Class", "tone": "good"})
    elif "silver class" in low:
        score += 10
    if "industry mover" in low:
        score += 10; creds.append({"label": "S&P Global", "value": "Industry Mover", "tone": "good"})

    if "cdp" in low and any(k in low for k in ("a list", "a-list", "double-a", "double a",
                                              "climate change a", "'a'", "cdp a")):
        score += 18; creds.append({"label": "CDP", "value": "A List", "tone": "good"})
    elif "cdp" in low:
        score += 6
    if "ftse4good" in low:
        asean = "asean" in low
        score += 14 if asean else 12
        creds.append({"label": "FTSE4Good", "value": "ASEAN 5" if asean else "Member", "tone": "good"})

    if "negligible risk" in low:
        score += 22; creds.append({"label": "Sustainalytics", "value": "Negligible Risk", "tone": "good"})
    elif "low risk" in low:
        score += 18; creds.append({"label": "Sustainalytics", "value": "Low Risk", "tone": "good"})
    elif "medium risk" in low:
        score += 8
    if "sustainalytics" in low and "top rated" in low:
        score += 10; creds.append({"label": "Sustainalytics", "value": "Top Rated", "tone": "good"})

    if "5-star" in low or "5 star" in low:
        score += 12; creds.append({"label": "GRESB", "value": "5-Star", "tone": "good"})
    elif "4-star" in low or "4 star" in low:
        score += 8; creds.append({"label": "GRESB", "value": "4-Star", "tone": "good"})

    if "sri-kehati" in low or "idx esg" in low:
        score += 12; creds.append({"label": "IDX ESG", "value": "Leader", "tone": "good"})
    sset = re.search(r"set esg[^.]{0,14}?\b(aaa|aa|a)\b", low)
    if sset or "set esg" in low:
        score += 10; creds.append({"label": "SET ESG", "value": sset.group(1).upper() if sset else "Rated",
                                   "tone": "good"})
    if any(k in low for k in ("asean cg", "asean corporate governance", "asean plc", "asean asset class")):
        score += 8; creds.append({"label": "ASEAN CG", "value": "Top", "tone": "good"})

    score += {"high": 8, "medium": 4}.get((confidence or "").lower(), 0)
    return {"score": min(100, score), "rating": rating, "credentials": creds}


def evidence_profile(c):
    """Grounded leadership profile for ONE constituent: {score, band, rating, credentials, has}."""
    basis = c.get("esg_basis") or ""
    p = parse_evidence(basis, c.get("confidence"))
    s = p["score"]
    band = "Leader" if s >= 70 else "Strong" if s >= 50 else "Established" if s >= 30 else "Emerging"
    return {**p, "band": band, "has": bool(basis)}


def evidence_average(constituents):
    """Mean derived ESG-leadership score across the filtered set — the evidence-mode 'avg ESG'."""
    scores = [evidence_profile(c)["score"] for c in (constituents or []) if (c.get("esg_basis"))]
    if not scores:
        return None, 0
    return round(sum(scores) / len(scores)), len(scores)


_COVERAGE_BUCKETS = (
    ("DJSI / Yearbook", lambda p: any(cr["label"] in ("DJSI", "S&P Yearbook", "S&P Global")
                                      for cr in p["credentials"])),
    ("MSCI AA+", lambda p: p["rating"] in ("AAA", "AA")),
    ("CDP A-List", lambda p: any(cr["label"] == "CDP" and cr["value"] == "A List" for cr in p["credentials"])),
    ("FTSE4Good", lambda p: any(cr["label"] == "FTSE4Good" for cr in p["credentials"])),
)


def credential_coverage(constituents):
    """For the four top cards in evidence mode: % of the filtered set holding each marquee
    credential (DJSI/Yearbook, MSCI AA+, CDP A-List, FTSE4Good). Grounded counts, not momentum."""
    profs = [evidence_profile(c) for c in (constituents or []) if c.get("esg_basis")]
    n = len(profs)
    out = []
    for label, test in _COVERAGE_BUCKETS:
        cnt = sum(1 for p in profs if test(p))
        out.append({"label": label, "count": cnt, "n": n,
                    "pct": round(cnt / n * 100) if n else None})
    return out


def evidence_leaders(constituents, *, top_n=5, new_tickers=()):
    """Rank the filtered set by derived leadership score — the evidence-mode 'hidden winners'.
    ``new_tickers`` flags freshly-focused names via membership (no cached-dict mutation)."""
    new = set(new_tickers or ())
    rows = [{"company": c.get("company", "—"), "ticker": c.get("ticker", ""),
             "value": evidence_profile(c)["score"], "is_new": c.get("ticker") in new}
            for c in (constituents or []) if c.get("esg_basis")]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n]


def classify_evidence(c):
    """Evidence-mode classification for the focused company (from its grounded credentials)."""
    if not (c or {}).get("esg_basis"):
        return {"label": "AWAITING DATA", "tone": "neutral",
                "line": "No evidence on file — add esg_basis or numeric data."}
    p = evidence_profile(c)
    label = ("ESG LEADER" if p["score"] >= 70 else "STRONG IMPROVER" if p["score"] >= 50
             else "ESTABLISHED" if p["score"] >= 30 else "EMERGING")
    tone = "good" if p["score"] >= 50 else "neutral"
    tags = ", ".join(f'{cr["label"]} {cr["value"]}' for cr in p["credentials"][:3]) or "documented ESG progress"
    line = (f"Evidence: {tags}. Leadership score {p['score']}/100 ({(c.get('confidence') or '—')} "
            "confidence). Live alt-data (AI/news/behaviour) not wired yet — we flag the gap, never buy/sell/hold.")
    return {"label": label, "tone": tone, "line": line}


def live_signals(company):
    """Normalise a focused company's right-rail signals into [{label,value,tone}] rows. Missing
    signals are dropped, so an empty list means 'no live signals yet'."""
    s = company.get("live_signals") or {}
    rows = []

    def add(label, value, tone="neutral"):
        if value is None or str(value).strip() in ("", "unknown"):
            return
        rows.append({"label": label, "value": str(value), "tone": tone})

    add("AI hiring surge", s.get("ai_hiring_surge"), "good")
    add("Green patents", s.get("green_patents"), "good")
    add("Carbon disclosure", s.get("carbon_disclosure"), "good")
    flags = s.get("controversy_flags")
    if flags is not None and num(flags) is not None:
        n = int(num(flags))
        if n > 0:
            rows.append({"label": "Controversy flag", "value": f"{n} new", "tone": "warn"})
        else:
            rows.append({"label": "Controversy flag", "value": "none", "tone": "neutral"})
    pol = s.get("board_ai_policy")
    if pol is not None:
        p = str(pol).strip().lower()
        if p in ("partial", "part", "in progress", "developing"):
            rows.append({"label": "Board AI policy", "value": "Partial", "tone": "warn"})
        elif p in ("true", "yes", "1"):
            rows.append({"label": "Board AI policy", "value": "Yes", "tone": "good"})
        else:
            rows.append({"label": "Board AI policy", "value": "No", "tone": "neutral"})
    return rows


# --------------------------------------------------------------------------- #
#  FEATURE-BACKLOG PURE HELPERS (2026-06-30) — all grounded only in provided
#  data; a missing fact is None/"awaiting", never fabricated (HARD RULE 2).
# --------------------------------------------------------------------------- #
def _clean(v):
    """A model/string field cleaned for display: ''/'unknown' (any case) -> ''."""
    s = str(v if v is not None else "").strip()
    return "" if s.lower() in ("", "unknown", "none") else s


def fmt_elapsed(now_ts, then_ts):
    """[1.11] Human 'updated X ago' from two epoch seconds (no clock read here, so it's pure).
    'just now' | 'N min ago' | 'N hr ago' | 'Nd ago'; '' when then_ts is None; clamps clock-skew."""
    if then_ts is None:
        return ""
    delta = max(0, int((now_ts or 0) - then_ts))
    if delta < 60:
        return "just now"
    mins = delta // 60
    if mins < 60:
        return f"{mins} min ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs} hr ago"
    return f"{hrs // 24}d ago"


def price_change_pct(constituent):
    """[#17] The 90-day price move as a float (e.g. '+9.4%' -> 9.4), or None when absent.
    Never fabricates a move for a name lacking the (illustrative, demo-only) field."""
    return num((constituent or {}).get("price_change_90d"))


def price_series(pct, *, points=10, base=100.0):
    """[#17] An ILLUSTRATIVE rebased 90-day path from `base` to base*(1+pct/100) over `points`
    samples (not a backtest). [] when pct is None. Mirrors momentum_series' ZeroDivision guard."""
    if pct is None:
        return []
    end = base * (1 + pct / 100.0)
    divisor = max(points - 1, 1)
    return [round(base + (end - base) * (i / divisor), 2) for i in range(points)]


def financial_snapshot(obj):
    """[#10/2.3] Read an illustrative financial snapshot off a constituent (obj['market']) or a
    Contract B (obj['_market']) + the top-level/ridden price_change_90d. {have:False} when absent —
    never invents a market figure for a name that lacks one (HARD RULE 2)."""
    o = obj if isinstance(obj, dict) else {}
    m = o.get("market") or o.get("_market")
    m = m if isinstance(m, dict) else {}
    pc = num(o.get("price_change_90d") or o.get("_price_change_90d"))
    pc_str = fmt_pct(pc) if pc is not None else None
    if not m:
        return {"have": False, "currency": "", "as_of": None, "price": None, "day_change": None,
                "price_change_90d": pc_str, "range_52w": None, "rows": [], "simple": []}
    cur = str(m.get("currency") or "").strip()

    def money(v):
        n = num(v)
        return f"{cur} {n:g}".strip() if n is not None else None

    price = money(m.get("price"))
    prev, cur_price = num(m.get("prev_close")), num(m.get("price"))
    day_change = (fmt_pct(round((cur_price / prev - 1) * 100, 1))
                  if (prev and cur_price is not None) else None)
    lo, hi = num(m.get("week52_low")), num(m.get("week52_high"))
    range_52w = f"{lo:.2f} – {hi:.2f}" if (lo is not None and hi is not None) else None
    pe = num(m.get("pe_ratio"))

    def _rows(pairs):
        out = []
        for label, value in pairs:
            if value is not None and str(value).strip() not in ("", "unknown"):
                out.append({"label": label, "value": str(value)})
        return out

    rows = _rows([
        ("Open", money(m.get("open"))), ("High", money(m.get("high"))),
        ("Low", money(m.get("low"))), ("Prev close", money(m.get("prev_close"))),
        ("Market cap", m.get("market_cap")),
        ("P / E", f"{pe:g}" if pe is not None else None),
        ("Dividend yield", m.get("dividend_yield")), ("52-week range", range_52w),
    ])
    simple = _rows([("Price", price), ("90-day change", pc_str),
                    ("Market cap", m.get("market_cap"))])
    return {"have": True, "currency": cur, "as_of": m.get("as_of"), "price": price,
            "day_change": day_change, "price_change_90d": pc_str, "range_52w": range_52w,
            "rows": rows, "simple": simple}


def youtube_search_url(name, terms="ESG sustainability"):
    """[#11] A deterministic YouTube SEARCH url for a company (not fabricated video content)."""
    q = f"{str(name or '').strip()} {terms}".strip()
    return "https://www.youtube.com/results?search_query=" + quote_plus(q)


def news_search_url(name, terms="ESG"):
    """[#11] A deterministic DuckDuckGo news SEARCH url (a query, not invented headlines)."""
    q = f"{str(name or '').strip()} {terms}".strip()
    return "https://duckduckgo.com/?iar=news&ia=news&q=" + quote_plus(q)


def news_card(company, stored=None):
    """[#11] Headlines + a YouTube/news search link for the focused company.

    Three states, and the card must never blur them. DEMO names carry illustrative seeded
    headlines (`company['news']`) and say so. A REAL name uses `stored` — the gathered record from
    `news.py`, whose titles and URLs are copied verbatim out of search results with no model in
    the path. With neither, the card stays 'awaiting' and offers a search link rather than
    inventing a headline (HARD RULE 2). Tolerant of None/junk input.
    """
    c = company if isinstance(company, dict) else {}
    name = str(c.get("company") or "").strip()
    raw = c.get("news")
    live_items = (stored or {}).get("items") if isinstance(stored, dict) else None
    if live_items:
        rows = [{"title": _clean(it.get("title")),
                 "source": _clean(it.get("source")) or "unknown source",
                 "date": _clean(it.get("published_at")),
                 "url": _clean(it.get("url"))}
                for it in live_items if _clean(it.get("title")) and _clean(it.get("url"))]
        if rows:
            return {"name": name or "this company", "illustrative": False, "status": "gathered",
                    "headlines": rows, "gathered_at": _clean((stored or {}).get("gathered_at")),
                    "dated": int((stored or {}).get("dated") or 0),
                    "youtube_url": youtube_search_url(name), "news_url": news_search_url(name)}
    headlines = []
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict) and _clean(it.get("title")):
                headlines.append({"title": _clean(it.get("title")),
                                  "source": _clean(it.get("source")) or "illustrative",
                                  "date": _clean(it.get("date"))})
    return {
        "name": name or "this company",
        "illustrative": bool(headlines),
        "status": "demo" if headlines else "awaiting",
        "headlines": headlines,
        "youtube_url": youtube_search_url(name),
        "news_url": news_search_url(name),
    }


def analyst_coverage(company):
    """[#18/3.17] Sell-side coverage BREADTH (a count only) — explicitly NOT a rating/consensus and
    never buy/sell/hold (HARD RULE 4). Reads only company['analyst_coverage']; illustrative, demo
    only. Absent/non-dict/uncountable -> 'awaiting data'. Distinct from the X/10 data-coverage meter."""
    c = company if isinstance(company, dict) else {}
    raw = c.get("analyst_coverage")
    if not isinstance(raw, dict):
        return {"covered": False, "analysts": None, "as_of": "", "label": "awaiting data",
                "illustrative": False}
    n = num(raw.get("analysts"))
    n = int(n) if n is not None else None
    as_of = _clean(raw.get("as_of"))
    if n is None or n <= 0:
        return {"covered": False, "analysts": n, "as_of": as_of, "label": "awaiting data",
                "illustrative": True}
    label = f"{n} analyst{'' if n == 1 else 's'} covering"
    return {"covered": True, "analysts": n, "as_of": as_of, "label": label, "illustrative": True}


def _outlook_band(mean):
    """(label, tone) for a mean pillar momentum — reuses trend_label's 8 / -3 boundaries."""
    if mean is None:
        return "AWAITING DATA", "neutral"
    if mean >= 8:
        return "Improving", "good"
    if mean > -3:
        return "Stable", "neutral"
    return "Softening", "bad"


def _outlook_word(value):
    """A per-pillar forward word (number-free): accelerating / holding / softening."""
    if value is None:
        return "awaiting"
    if value >= 8:
        return "accelerating"
    if value > -3:
        return "holding"
    return "softening"


_PLAIN_NUMERIC = {
    "HIDDEN WINNER": ("Quietly ahead of its rating",
                      "The live signals for {name} are improving faster than its older ESG score "
                      "reflects — worth a closer look."),
    "WATCH — GAP RISK": ("Watch for a widening gap",
                         "Some live signals for {name} are slipping or carry red flags, even if the "
                         "headline rating still looks calm."),
    "IN LINE": ("Broadly in line",
                "{name} is moving roughly in step with what its rating already implies — no big "
                "surprise either way yet."),
    "AWAITING DATA": ("Not enough live data yet",
                      "We do not have enough live signals on {name} to take a view — switch on demo "
                      "data or run a deep dive."),
}
_PLAIN_EVIDENCE = {
    "ESG LEADER": ("A documented ESG leader",
                   "{name} carries strong, independently-documented ESG credentials among its "
                   "ASEAN peers."),
    "STRONG IMPROVER": ("A strong improver",
                        "{name} shows clear, documented ESG progress, though it is not yet at the "
                        "very top of its peer group."),
    "ESTABLISHED": ("Established and steady",
                    "{name} has a solid, documented ESG track record without standing out as a "
                    "front-runner."),
    "EMERGING": ("Early on its ESG journey",
                 "{name} is early in its documented ESG story — some evidence on file, but limited "
                 "so far."),
    "AWAITING DATA": ("Not enough evidence yet",
                      "There is not enough evidence on file for {name} to take a view."),
}


def plain_summary(company, answer=None):
    """[2.1] A plain-language, score-free read of the focused company for Simplified mode. tone/label
    mirror classify (numeric) or classify_evidence (evidence); body is a controlled number-free
    template; verdict is the cleaned competes_summary (or '' when absent). No I/O."""
    c = company or {}
    name = _clean(c.get("company")) or "this company"
    cls, tmpl = {"label": "AWAITING DATA", "tone": "neutral"}, _PLAIN_NUMERIC
    if has_numbers([c]):
        cls, tmpl = classify(c), _PLAIN_NUMERIC
    # A CGSI basket row carries a static score AND evidence text but no pillar momentum, so the
    # numeric classifier cannot reach a verdict on it. Falling straight through to "awaiting
    # data" would throw away evidence we hold: try the evidence classifier before giving up.
    if cls["label"] == "AWAITING DATA" and c.get("esg_basis"):
        cls, tmpl = classify_evidence(c), _PLAIN_EVIDENCE
    label, tone = cls["label"], cls["tone"]
    headline, body = tmpl.get(label, tmpl["AWAITING DATA"])
    verdict = _clean((answer or {}).get("competes_summary"))
    return {"headline": headline, "body": body.format(name=name), "verdict": verdict,
            "tone": tone, "label": label}


def focused_answer_action(snapshots, ticker):
    """[#5] The cached deep-dive's one concrete action for the focused company. Reads the verified
    Stage 2 baton at snapshots[ticker]['answer'] — never generated here. Tolerant of None/junk."""
    snaps = snapshots if isinstance(snapshots, dict) else {}
    entry = snaps.get(ticker) if ticker else None
    ans = entry.get("answer") if isinstance(entry, dict) else None
    ans = ans if isinstance(ans, dict) else {}
    check = _clean(ans.get("check_before_monday"))
    verdict = _clean(ans.get("competes_summary"))
    return {"check": check, "verdict": verdict, "has": bool(check)}


# --- CHATBOT COPY (2.2) — In-Depth branch reproduces the current literals byte-for-byte ---------
def chat_relay_msg(company_name, mode, simplified, *, focused=False, live=False):
    verb = "interrogation" if mode == "interrogate" else "compete"
    if not simplified:
        if focused:
            return f"Running the 3-stage relay on the focused company ({verb} mode)…"
        if live:
            return f"Built {company_name} live (ASEAN) — running the 3-stage relay ({verb} mode)…"
        return f"Running the 3-stage ESG relay on {company_name} ({verb} mode)…"
    ask = ("I'll ask a few quick ESG questions first…" if mode == "interrogate"
           else "I'll show you the read straight away…")
    if focused:
        return f"Opening the focused company — {ask}"
    prefix = f"Found {company_name}. " if live else ""
    return f"{prefix}Opening {company_name} — {ask}"


def chat_focus_msg(company_name, sector_label, simplified, *, avg=None, digital_pct="—"):
    if not simplified:
        peer = (f" — scored against {sector_label} peers, Digital/AI {digital_pct} vs avg ESG {avg}."
                if avg is not None else ".")
        return f"Focused {company_name}{peer} Added to the grid."
    return f"Now showing {company_name} in the panels on the right."


def chat_filter_msg(bits, simplified):
    joined = " · ".join(bits)
    return (f"OK — showing {joined}." if simplified else f"Filtered to {joined}.")


def chat_relay_help(simplified):
    if simplified:
        return ("Tell me which company to look at — e.g. “look at DBS”, “check Maybank”, or an "
                "ASEAN name like “look at Grab”.")
    return ("Name a company to analyse — e.g. “analyze DBS”, “interrogate "
            "Maybank”, or a live ASEAN name like “analyze Grab”.")


def chat_fallback_msg(simplified):
    if simplified:
        return ("I can show a group (“banks”, “Singapore”, “all ASEAN”) or pull up one company "
                "(“DemoBank”, “add GreenChip Bank”).")
    return ("I can filter (“show banks”, “Singapore”, “all ASEAN”) or focus "
            "a company (“DemoBank”, “add GreenChip Bank”).")


def chat_cant_analyse_msg(name, simplified):
    if simplified:
        return f"Sorry — I couldn't open “{name}”."
    return f"Couldn't analyse “{name}”."


# --- SUGGESTED FOLLOW-UP CHIPS (14/3.7) ---------------------------------------------------------
def suggested_followups(*, focused_name=None, focused_sector=None, has_focus=False,
                        has_answer=False, simplified=True, sample_sector=None, sample_country=None):
    """Up to 3 {label, prompt} chips. `prompt` is a chat line the existing _chat_act parser
    understands (relay verb + name / sector word / country / 'all asean'). Labels are mode-aware;
    prompts are identical across modes. Never emits buy/sell/hold/score wording."""
    name = str(focused_name or "").strip()
    sec = str(focused_sector or "").strip()
    sec_missing = sec.lower() in ("", "all", "all industries", "unknown")
    chips = []
    if has_focus and name:
        chips.append({"label": ("Run a deep dive" if has_answer else "Get a quick read") if simplified
                      else ("Open the deep dive" if has_answer else f"Compete · {name}"),
                      "prompt": f"Analyze {name}"})
        chips.append({"label": "Ask sharper questions" if simplified else f"Interrogate · {name}",
                      "prompt": f"Interrogate {name}"})
        if not sec_missing:
            chips.append({"label": "See similar companies" if simplified else f"Peers · {sec}",
                          "prompt": f"Show {sec}"})
        else:
            chips.append({"label": "See all ASEAN" if simplified else "Show all ASEAN",
                          "prompt": "Show all ASEAN"})
    else:
        s = str(sample_sector or "Banks").strip() or "Banks"
        ctry = str(sample_country or "Singapore").strip() or "Singapore"
        chips.append({"label": f"Show {s}" if simplified else f"Sector · {s}", "prompt": f"Show {s}"})
        chips.append({"label": f"Look at {ctry}" if simplified else f"Market · {ctry}", "prompt": ctry})
        chips.append({"label": "See all ASEAN" if simplified else "Show all ASEAN",
                      "prompt": "Show all ASEAN"})
    return chips[:3]
