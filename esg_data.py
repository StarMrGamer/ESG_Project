"""Country-indicator sourcing for the ESG demo pipeline (isolated I/O, like rag.py).

Live World Bank fetch -> normalize -> bundled CSV fallback. Best-effort by contract:
any failure degrades to data/fallback_oecd_wgi_asean.csv. Never raises to the UI.
"""
import csv, os
import json as _json
import core

WB_BASE = "https://api.worldbank.org/v2"

# Separate cache for live pulls — never overwrites the bundled reference CSV.
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
_LIVE_CACHE_CSV = os.path.join(_CACHE_DIR, "wb_live_cache.csv")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FALLBACK_CSV = os.path.join(DATA_DIR, "fallback_oecd_wgi_asean.csv")

COUNTRIES = {"SGP": "Singapore", "MYS": "Malaysia", "IDN": "Indonesia",
             "THA": "Thailand", "PHL": "Philippines", "VNM": "Vietnam"}

# key -> (World Bank code, source id, pillar, direction). direction: 'up' higher=better,
# 'down' lower=better (inverted on normalize), 'ratio' closer-to-100 (capped).
INDICATOR_META = {
    "rule_of_law":        ("GOV_WGI_RL.EST", 3, "G", "wgi"),
    "control_corruption": ("GOV_WGI_CC.EST", 3, "G", "wgi"),
    "reg_quality":        ("GOV_WGI_RQ.EST", 3, "G", "wgi"),
    "co2_pc":             ("EN.GHG.ALL.PC.CE.AR5", 75, "E", "down"),
    "renew_share":        ("EG.FEC.RNEW.ZS", 2, "E", "renew"),
    "env_policy":         (None, None, "E", "up"),      # OECD-only; bundled empty
    "lfp":                ("SL.TLF.CACT.ZS", 2, "S", "lfp"),
    "gender_lfp_ratio":   ("SL.TLF.CACT.FM.ZS", 2, "S", "ratio"),
    "injury_rate":        (None, None, "S", "down"),    # ILO-only; bundled empty
}
INDICATORS = list(INDICATOR_META)


def _to_float(s):
    s = (s or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_fallback(path=FALLBACK_CSV):
    """Read the bundled CSV into {country_name: {indicator: float|None}}. Missing/empty -> None."""
    table = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            country = row.get("country", "").strip()
            if not country:
                continue
            table[country] = {k: _to_float(row.get(k)) for k in INDICATORS}
    return table


def save_fallback(table, path=FALLBACK_CSV):
    """Persist a {country: {indicator: value}} table back to the CSV (cache the latest good pull).
    Best-effort: writes country rows in COUNTRIES order; None -> empty cell."""
    names = [n for n in COUNTRIES.values() if n in table] or list(table)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["country"] + INDICATORS)
        for name in names:
            row = table[name]
            w.writerow([name] + ["" if row.get(k) is None else row.get(k) for k in INDICATORS])


CO2_CAP, RENEW_CAP, LFP_LO, LFP_HI = 20.0, 50.0, 40.0, 80.0


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _norm_one(direction, v):
    if v is None:
        return None
    if direction == "wgi":
        out = (v + 2.5) / 5.0 * 100.0
    elif direction == "down":
        out = (1.0 - _clamp(v, 0.0, CO2_CAP) / CO2_CAP) * 100.0
    elif direction == "renew":
        out = _clamp(v, 0.0, RENEW_CAP) / RENEW_CAP * 100.0
    elif direction == "lfp":
        out = _clamp((v - LFP_LO) / (LFP_HI - LFP_LO), 0.0, 1.0) * 100.0
    else:  # 'ratio' or 'up'
        out = v
    return round(_clamp(out), 3)


def normalize(raw_table):
    """Raw indicator table -> 0..100 per-country table. None stays None (missing-handled later)."""
    out = {}
    for country, row in (raw_table or {}).items():
        out[country] = {k: _norm_one(INDICATOR_META[k][3], row.get(k)) for k in INDICATORS}
    return out


def _wb_indicator(code, source, *, timeout):
    """Fetch one indicator for all 6 countries -> {country_name: value}. None on any failure."""
    cc = ";".join(COUNTRIES)
    params = {"format": "json", "per_page": "3000", "date": "2010:2024"}
    if source:
        params["source"] = str(source)
    txt = core.http_get(f"{WB_BASE}/country/{cc}/indicator/{code}", params=params, timeout=timeout)
    data = _json.loads(txt)
    if not (isinstance(data, list) and len(data) > 1 and data[1]):
        return None
    latest = {}
    for r in data[1]:
        if r.get("value") is None:
            continue
        name = COUNTRIES.get(r.get("countryiso3code"))
        if not name:
            continue
        if name not in latest or r["date"] > latest[name][1]:
            latest[name] = (r["value"], r["date"])
    return {name: v for name, (v, _d) in latest.items()} or None


def fetch_worldbank(*, timeout=5):
    """Live pull of every World-Bank-backed indicator. Returns a raw table or None on failure.
    Best-effort: a single indicator failing is tolerated (left None); a hard error -> None."""
    table = {name: {k: None for k in INDICATORS} for name in COUNTRIES.values()}
    got_any = False
    for key, (code, source, _pillar, _dir) in INDICATOR_META.items():
        if not code:
            continue  # OECD/ILO-only -> stays None, supplied by fallback merge
        try:
            vals = _wb_indicator(code, source, timeout=timeout)
        except Exception:
            vals = None
        if vals:
            got_any = True
            for name, v in vals.items():
                table[name][key] = v
    return table if got_any else None


def get_country_table(*, allow_live=True, log=print):
    """Orchestrate live -> cache -> bundled fallback. Returns (normalized_table, origin).
    Never raises.

    On a successful live pull, merges in the bundled CSV's OECD/ILO-only columns (env_policy,
    injury_rate) so they are not lost, then caches the merged raw table to _LIVE_CACHE_CSV.
    On the fallback path, the most recent cached live pull is preferred over the bundled CSV,
    so the last good run becomes the next fallback automatically."""
    if allow_live:
        try:
            raw = fetch_worldbank()
        except Exception:
            raw = None
        if raw:
            try:
                bundled = load_fallback()
                for name, row in raw.items():
                    for k in ("env_policy", "injury_rate"):
                        if row.get(k) is None and bundled.get(name, {}).get(k) is not None:
                            row[k] = bundled[name][k]
                os.makedirs(os.path.dirname(_LIVE_CACHE_CSV) or ".", exist_ok=True)
                save_fallback(raw, _LIVE_CACHE_CSV)
            except Exception:
                pass
            log("[esg_data] country indicators: LIVE (World Bank)")
            return normalize(raw), "live"
    # Fallback: prefer the most recent successful live pull (cached) over the bundled CSV.
    # The whole read (cache + bundled + normalize) is guarded so a missing/unreadable
    # FALLBACK_CSV (clean clone, packaging slip, accidental delete) degrades to an
    # empty-but-valid result rather than raising to the UI ("never raises" contract).
    try:
        if os.path.exists(_LIVE_CACHE_CSV) and os.path.getsize(_LIVE_CACHE_CSV) > 0:
            cached = load_fallback(_LIVE_CACHE_CSV)
            if cached:
                log("[esg_data] country indicators: FALLBACK (cached live pull)")
                return normalize(cached), "fallback"
        log("[esg_data] country indicators: FALLBACK (bundled CSV)")
        return normalize(load_fallback()), "fallback"
    except Exception:
        log("[esg_data] country indicators: FALLBACK (no data available)")
        return {}, "fallback"
