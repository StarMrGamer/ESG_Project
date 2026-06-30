"""Deterministic ILLUSTRATIVE enrichment for demo constituents (HARD RULE 2: labelled, no
fabricated URLs/real facts). Seeded off the company name so the demo is stable across runs."""
import hashlib

_CCY = {"SGX": "SGD", "KLSE": "MYR", "IDX": "IDR", "SET": "THB", "PSE": "PHP", "HOSE": "VND"}


def _rng(name, salt):
    h = hashlib.md5(f"{name}|{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0x100000000          # 0..1


def _pick(name, salt, lo, hi):
    return lo + (hi - lo) * _rng(name, salt)


def momentum(name, breakdown):
    """Illustrative pillar momentum (%), loosely keyed to the pillar scores + seeded jitter."""
    def mom(score, salt):
        return int(round((score - 50) * 0.5 + _pick(name, salt, -6, 10)))
    return {"environment": mom(breakdown["e_score"], "E"),
            "social": mom(breakdown["s_score"], "S"),
            "governance": mom(breakdown["g_score"], "G"),
            "digital_ai": int(round(_pick(name, "AI", 4, 34)))}


def live_signals(name):
    return {"ai_hiring_surge": f"+{int(_pick(name,'h',60,360))}%",
            "board_ai_policy": _rng(name, "p") > 0.5,
            "carbon_disclosure": f"+{int(_pick(name,'c',4,22))}%",
            "green_patents": f"+{int(_pick(name,'gp',20,95))}%",
            "controversy_flags": 0 if _rng(name, "f") > 0.25 else 1}


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


def news(name):
    heads = [f"{name} lifts sustainable-finance disclosure",
             f"{name} expands renewable-energy sourcing plan",
             f"{name} names sustainability & AI-governance lead"]
    dates = ["2026-06-12", "2026-05-28", "2026-05-09"]
    src = ["DemoWire (illustrative)", "Mock Business Daily (illustrative)", "ASEAN ESG Demo (illustrative)"]
    return [{"title": heads[i], "source": src[i], "date": dates[i]} for i in range(3)]


def analyst_coverage(name):
    return {"analysts": int(_pick(name, "an", 6, 28)), "as_of": "Q1 2026"}


def price_change_90d(name):
    v = round(_pick(name, "p90", -8, 14), 1)
    return f"{'+' if v >= 0 else ''}{v}%"
