"""Deterministic ILLUSTRATIVE enrichment for demo constituents (HARD RULE 2: labelled, no
fabricated URLs/real facts). Seeded off the company name so the demo is stable across runs."""
import hashlib

_CCY = {"SGX": "SGD", "KLSE": "MYR", "IDX": "IDR", "SET": "THB", "PSE": "PHP", "HOSE": "VND"}


def _rng(name, salt):
    h = hashlib.md5(f"{name}|{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0x100000000          # 0..1


def _pick(name, salt, lo, hi):
    return lo + (hi - lo) * _rng(name, salt)


def trajectory(name):
    """improving | mixed | deteriorating — one deterministic story per demo company.

    Every enrichment block below reads this, so a company's momentum, live signals and headlines
    tell the SAME story. Without it the demo set was uniformly positive (three identical upbeat
    headlines and four always-positive live signals for all 36 names), which left the matrix's
    Value Traps and Overrated Leaders quadrants permanently empty and gave the engine nothing to
    disagree with. Roughly 60/25/15 — an ESG-improver basket that still contains names going the
    wrong way, because catching those is the entire product claim."""
    r = _rng(name, "traj")
    return "deteriorating" if r < 0.15 else "mixed" if r < 0.40 else "improving"


def momentum(name, breakdown, traj=None):
    """Illustrative pillar momentum (%), keyed to the pillar scores, the company's trajectory
    and seeded jitter. Deteriorating names tilt AGAINST their pillar score, so a well-rated
    company can be sliding — which is exactly the Overrated Leaders quadrant."""
    traj = traj or trajectory(name)
    tilt, lo, hi = {"improving": (0.5, -4, 12), "mixed": (0.2, -10, 10),
                    "deteriorating": (-0.15, -20, 2)}[traj]

    def mom(score, salt):
        return int(round((score - 50) * tilt + _pick(name, salt, lo, hi)))

    ai = {"improving": (6, 34), "mixed": (-6, 16), "deteriorating": (-26, -2)}[traj]
    return {"environment": mom(breakdown["e_score"], "E"),
            "social": mom(breakdown["s_score"], "S"),
            "governance": mom(breakdown["g_score"], "G"),
            "digital_ai": int(round(_pick(name, "AI", *ai)))}


def live_signals(name, traj=None):
    """Live-signal block matching the company's trajectory. Values may be NEGATIVE — a falling
    carbon-disclosure or AI-hiring number is a real signal, and the engine reads its sign."""
    traj = traj or trajectory(name)
    if traj == "improving":
        return {"ai_hiring_surge": f"+{int(_pick(name,'h',60,360))}%",
                "board_ai_policy": _rng(name, "p") > 0.35,
                "carbon_disclosure": f"+{int(_pick(name,'c',4,22))}%",
                "green_patents": f"+{int(_pick(name,'gp',20,95))}%",
                "controversy_flags": 0 if _rng(name, "f") > 0.15 else 1}
    if traj == "mixed":
        return {"ai_hiring_surge": f"+{int(_pick(name,'h',10,90))}%",
                "board_ai_policy": _rng(name, "p") > 0.6,
                "carbon_disclosure": f"{int(_pick(name,'c',-6,9)):+d}%",
                "green_patents": f"{int(_pick(name,'gp',-10,30)):+d}%",
                "controversy_flags": 0 if _rng(name, "f") > 0.45 else 1}
    return {"ai_hiring_surge": f"{int(_pick(name,'h',-45,-4)):+d}%",
            "board_ai_policy": False,
            "carbon_disclosure": f"{int(_pick(name,'c',-24,-3)):+d}%",
            "green_patents": f"{int(_pick(name,'gp',-30,4)):+d}%",
            "controversy_flags": 1 if _rng(name, "f") > 0.4 else 2}


def market(name, exchange):
    ccy = _CCY.get(exchange, "USD")
    price = round(_pick(name, "px", 4, 40), 2)
    prev_close = round(price * (1 + _pick(name, "pc", -0.02, 0.02)), 2)
    open_ = round(price * (1 + _pick(name, "o", -0.01, 0.01)), 2)
    hi = round(max(price, open_, prev_close) * (1 + _pick(name, "hi", 0.002, 0.02)), 2)
    lo = round(min(price, open_, prev_close) * (1 - _pick(name, "lo", 0.002, 0.02)), 2)
    return {"currency": ccy, "price": price,
            "open": open_, "high": hi, "low": lo, "prev_close": prev_close,
            "market_cap": f"{ccy} {round(_pick(name,'mc',2,90),1)}B",
            "pe_ratio": round(_pick(name, "pe", 8, 22), 1),
            "dividend_yield": f"{round(_pick(name,'dy',1,6),1)}%",
            "week52_high": round(hi * (1 + _pick(name, "wh", 0.05, 0.25)), 2),
            "week52_low": round(lo * (1 - _pick(name, "wl", 0.05, 0.25)), 2),
            "as_of": "2026-01-15"}


_HEADLINES = {
    "improving": [
        "{n} lifts sustainable-finance disclosure",
        "{n} expands renewable-energy sourcing plan",
        "{n} names sustainability & AI-governance lead",
    ],
    "mixed": [
        "{n} reports flat emissions intensity for a second year",
        "{n} delays its renewable-energy sourcing milestone",
        "{n} names sustainability & AI-governance lead",
    ],
    "deteriorating": [
        "{n} faces a regulatory investigation over effluent discharge",
        "{n} misses its emissions reduction target as disclosure slips",
        "{n} loses its head of sustainability amid restructuring",
    ],
}


def news(name, traj=None):
    """Three dated illustrative headlines that MATCH the company's trajectory.

    No URLs are ever emitted and every source is labelled illustrative (HARD RULE 2): these are
    props for a fictional company, and the engine reads their wording, so an all-positive set
    would have made every demo name look like an improver regardless of its numbers."""
    traj = traj or trajectory(name)
    dates = ["2026-06-12", "2026-05-28", "2026-05-09"]
    src = ["DemoWire (illustrative)", "Mock Business Daily (illustrative)",
           "ASEAN ESG Demo (illustrative)"]
    return [{"title": _HEADLINES[traj][i].format(n=name), "source": src[i], "date": dates[i]}
            for i in range(3)]


def analyst_coverage(name):
    return {"analysts": int(_pick(name, "an", 6, 28)), "as_of": "Q1 2026"}


def price_change_90d(name):
    v = round(_pick(name, "p90", -8, 14), 1)
    return f"{'+' if v >= 0 else ''}{v}%"
