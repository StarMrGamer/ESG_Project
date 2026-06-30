"""Synthetic company ESG scoring from country baselines (pure, deterministic).

Country normalized E/S/G indicators -> per-pillar score -> sector materiality tilt ->
seeded per-company variance -> overall ESG (0..100, higher=better). No network, no LLM.
All knobs are named constants so weights are tunable, never magic numbers.
"""
import hashlib
import esg_data

# within each pillar; re-normalized over whichever indicators are present for a country
INDICATOR_WEIGHTS = {
    "E": {"co2_pc": 1 / 3, "renew_share": 1 / 3, "env_policy": 1 / 3},
    "S": {"lfp": 1 / 3, "gender_lfp_ratio": 1 / 3, "injury_rate": 1 / 3},
    "G": {"rule_of_law": 1 / 3, "control_corruption": 1 / 3, "reg_quality": 1 / 3},
}
PILLAR_WEIGHTS = {"E": 0.34, "S": 0.33, "G": 0.33}          # -> overall ESG
SECTOR_MULTIPLIERS = {                                       # materiality tilt per sector
    "Financials — Banks":               {"E": 0.95, "S": 1.00, "G": 1.10},
    "Energy — Power & Renewables":      {"E": 1.12, "S": 1.00, "G": 0.98},
    "Communication Services — Telecom": {"E": 0.98, "S": 1.05, "G": 1.02},
    "Real Estate":                      {"E": 1.08, "S": 1.00, "G": 1.00},
    "Consumer Staples":                 {"E": 1.02, "S": 1.08, "G": 0.98},
}
DEFAULT_MULT = {"E": 1.0, "S": 1.0, "G": 1.0}
VARIANCE_PCT = 0.04                                          # ±4% deterministic per-company spread

_PILLAR_KEYS = {p: [k for k, m in esg_data.INDICATOR_META.items() if m[2] == p]
                for p in ("E", "S", "G")}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def pillar_score(country_row, pillar):
    """Weighted mean of a pillar's present indicators (re-normalized weights). None if all missing."""
    weights = INDICATOR_WEIGHTS[pillar]
    num = den = 0.0
    for k in _PILLAR_KEYS[pillar]:
        v = country_row.get(k)
        if v is None:
            continue
        w = weights.get(k, 0.0)
        num += w * v
        den += w
    return (num / den) if den > 0 else None


def _variance(name, pillar):
    """Deterministic offset in [-VARIANCE_PCT, +VARIANCE_PCT] from a stable hash of name+pillar."""
    h = hashlib.md5(f"{name}|{pillar}".encode("utf-8")).hexdigest()
    frac = int(h[:8], 16) / 0xFFFFFFFF          # 0..1
    return (frac * 2 - 1) * VARIANCE_PCT         # -p..+p


def score_company(country_row, sector, *, name, country=""):
    """Country baseline -> sector tilt -> seeded variance -> E/S/G + overall (0..100)."""
    mult = SECTOR_MULTIPLIERS.get(sector, DEFAULT_MULT)
    pillars = {}
    for p in ("E", "S", "G"):
        base = pillar_score(country_row, p)
        if base is None:
            base = 50.0                          # neutral fallback when a whole pillar is missing
        tilted = base * mult[p]
        varied = tilted * (1 + _variance(name, p))
        pillars[p] = round(_clamp(varied), 1)
    overall = round(_clamp(sum(PILLAR_WEIGHTS[p] * pillars[p] for p in pillars)), 1)
    breakdown = {"e_score": pillars["E"], "s_score": pillars["S"],
                 "g_score": pillars["G"], "overall": overall}
    prov = (f"Derived from country-level OECD/World Bank proxies for {country or 'the country'} "
            f"(WGI governance + World Bank environment/social indicators), sector-adjusted "
            f"({sector}). Synthetic demo company — not direct company disclosure.")
    return {"e_score": pillars["E"], "s_score": pillars["S"], "g_score": pillars["G"],
            "overall": overall, "breakdown": breakdown, "data_provenance": prov}
