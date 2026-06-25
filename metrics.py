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
    esg_score: number            # the static Layer-A ESG/risk score (lower = better for risk)
    esg_as_of: "2023"            # vintage of that static score
    esg_cagr_2019_2023: "+5.2%"  # the foundation momentum metric (5-yr ESG-score CAGR)
    momentum: { environment, social, governance, digital_ai }   # live/90-day % per pillar
    live_signals: { ai_hiring_surge, green_patents, carbon_disclosure,
                    controversy_flags, board_ai_policy }          # the right-rail signals
    price_change_90d: "+9.4%"    # optional price panel
"""

import re

PILLARS = ("environment", "social", "governance", "digital_ai")
PILLAR_LABEL = {"environment": "Environment", "social": "Social",
                "governance": "Governance", "digital_ai": "Digital / AI"}

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
                    "trend": trend, "fast": False})
        if avg is not None and (best_val is None or avg > best_val):
            best_key, best_val = p, avg
    for row in out:                       # highlight the strongest riser (the orange card)
        if row["key"] == best_key and best_val is not None and best_val > 0:
            row["fast"] = True
    return out


def fmt_pct(value):
    """A signed percent string for a card, e.g. 12 -> '+12%', -2 -> '-2%', None -> '—'."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    v = int(value) if float(value).is_integer() else value
    return f"{sign}{v}%"


def hidden_winners(constituents, *, signal="digital_ai", top_n=5):
    """Rank the filtered set by a live signal (default Digital/AI momentum) — the companies whose
    live trajectory diverges from the stale rating. Returns [{company,ticker,value,is_new}] sorted
    desc, plus the peer-average ESG for the panel subtitle. Skips names with no signal."""
    rows = []
    for c in constituents or []:
        v = _momentum(c, signal)
        if v is None:
            continue
        rows.append({"company": c.get("company", "—"), "ticker": c.get("ticker", ""),
                     "value": v, "is_new": bool(c.get("_new"))})
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
        series[row["key"]] = [round(start + (end - start) * (i / (points - 1)), 2)
                              for i in range(points)]
    return series


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


def parse_evidence(basis, confidence=""):
    """Extract the ESG credentials a constituent's `esg_basis` text actually NAMES (MSCI rating,
    DJSI/S&P Yearbook, CDP A-List, FTSE4Good, Sustainalytics risk, GRESB, national ESG indices) and
    sum them into a 0–100 leadership score. This is GROUNDED extraction from cited evidence — it
    emits a credential only when its keyword appears in the text — not a fabricated ESG figure.
    Returns {score, rating, credentials:[{label,value,tone}]}."""
    low = (basis or "").lower()
    creds, score, rating = [], 0, None

    m = re.search(r"msci(?:\s+esg)?[^.]{0,24}?\b(aaa|aa|a|bbb|bb|b|ccc)\b", low)
    if m:
        rating = m.group(1).upper()
    elif "msci" in low and "leader" in low:
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


def evidence_leaders(constituents, *, top_n=5):
    """Rank the filtered set by derived leadership score — the evidence-mode 'hidden winners'."""
    rows = [{"company": c.get("company", "—"), "ticker": c.get("ticker", ""),
             "value": evidence_profile(c)["score"], "is_new": bool(c.get("_new"))}
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
        rows.append({"label": "Board AI policy", "value": "Yes" if pol else "No",
                     "tone": "good" if pol else "warn"})
    return rows
