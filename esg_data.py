"""Country-indicator sourcing for the ESG demo pipeline (isolated I/O, like rag.py).

Live World Bank fetch -> normalize -> bundled CSV fallback. Best-effort by contract:
any failure degrades to data/fallback_oecd_wgi_asean.csv. Never raises to the UI.
"""
import csv, os

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
