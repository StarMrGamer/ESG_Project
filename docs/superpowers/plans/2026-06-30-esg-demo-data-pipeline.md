# ESG Demo-Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fabricated demo ESG scores with a reproducible pipeline that derives synthetic ASEAN company ESG scores (0–100, higher=better) from real OECD/World Bank country indicators, and make browse/monitor work in the demo.

**Architecture:** Three pure-ish layers — `esg_data.py` (live World Bank fetch → normalize → fallback CSV), `esg_scoring.py` (country baseline × sector multipliers + seeded variance → E/S/G/overall), and `build_demo_universe.py` (joins a fresh `data/demo_config.json` roster → emits `data/demo_universe.json`). Web I/O stays isolated in `core.http_get`; offline always degrades to the bundled CSV.

**Tech Stack:** Python 3.8+ stdlib (json, csv, hashlib, urllib via `core.http_get`), Streamlit (existing), `selftest.py` as the offline regression harness. No new dependencies.

## Global Constraints

- **No new pip dependencies** — stdlib only (`csv`, `json`, `hashlib`); reuse `core.http_get` / `core.parse_json`.
- **HARD RULE 1:** outbound HTTP ONLY via `core.http_get`; every fetch is best-effort and degrades to the bundled CSV — never crash, never blank UI.
- **HARD RULE 2:** demo data is synthetic but must be labelled illustrative; `real_world_basis` is internal-only and MUST NOT appear in any output JSON or the UI.
- **HARD RULE 4:** scores describe, never advise — no buy/sell/hold, no ranking semantics.
- **HARD RULE 5/6:** no secrets in code; LLM only via `core.call_llm`.
- **FROZEN:** do not edit `core.py` or `contracts.py`. New fields ride as non-contract keys (like `market`/`news`).
- **Score convention (NEW):** demo `esg_score` is 0–100, **higher = better** (harmonized with evidence mode). The real `data/asean_universe.json` is untouched.
- **selftest stays network-free:** all tests mock `core.http_get`; `python selftest.py` must end green.
- **selftest harness pattern (IMPORTANT):** `selftest.py` checks are plain `def test_*()` functions using bare `assert`, **manually registered** in the `checks = [...]` list inside `main()` as `("human label", lambda: test_fn())`. For every test this plan adds you MUST do BOTH: (1) define the `test_*` function at module level, and (2) append its `(label, lambda)` tuple to the `checks` list in `main()` (place new tuples just before the closing `]`). A function that is defined but not registered never runs. Tests take no args except where a monkeypatch fixture is threaded in (see `test_stage2_chain`); the new tests here take none.
- **6 countries:** Singapore (SGP), Malaysia (MYS), Indonesia (IDN), Thailand (THA), Philippines (PHL), Vietnam (VNM).
- **Run tests with the venv:** `PYTHONPATH=. ./venv/bin/python selftest.py` (deps live in `./venv`).

### Real indicator data (World Bank, pulled 2026-06-30) — verbatim, for the bundled CSV

| Country | RL.EST | CC.EST | RQ.EST | CO₂ t/cap | Renew % | LFP % | Gender LFP ratio |
|---------|-------:|-------:|-------:|----------:|--------:|------:|-----------------:|
| Singapore   | 1.431  | 1.968  | 2.132  | 12.605 | 1.1  | 69.673 | 84.340 |
| Malaysia    | 0.345  | 0.498  | 0.680  | 9.342  | 7.5  | 66.120 | 65.197 |
| Indonesia   | -0.207 | -0.545 | 0.125  | 4.670  | 20.2 | 67.965 | 65.291 |
| Thailand    | -0.216 | -0.527 | 0.106  | 5.894  | 19.0 | 66.678 | 78.637 |
| Philippines | -0.574 | -0.577 | 0.079  | 2.301  | 28.0 | 61.350 | 69.675 |
| Vietnam     | -0.314 | -0.252 | -0.267 | 5.785  | 24.2 | 72.778 | 88.650 |

World Bank indicator codes / sources: `GOV_WGI_RL.EST`, `GOV_WGI_CC.EST`, `GOV_WGI_RQ.EST` (source 3); `EN.GHG.ALL.PC.CE.AR5` (source 75, CO₂); `EG.FEC.RNEW.ZS`, `SL.TLF.CACT.ZS`, `SL.TLF.CACT.FM.ZS` (default WDI source 2). `env_policy` (OECD EPS) and `injury_rate` (ILO) have no ASEAN World-Bank coverage → bundled as empty → exercise missing-value handling.

---

## Task 1: `esg_data.py` skeleton + bundled fallback CSV + load/save round-trip

**Files:**
- Create: `esg_data.py`
- Create: `data/fallback_oecd_wgi_asean.csv`
- Modify: `selftest.py` (add a check block at the end, before the final summary)

**Interfaces:**
- Produces: `COUNTRIES` (dict ISO3→name), `INDICATORS` (ordered list of indicator keys), `INDICATOR_META` (key→{wb_code, source, pillar, direction}), `FALLBACK_CSV` (path), `load_fallback(path=FALLBACK_CSV) -> dict`, `save_fallback(table, path=FALLBACK_CSV) -> None`. The table shape is `{ "Singapore": {"rule_of_law": 1.431, ..., "env_policy": None, "injury_rate": None}, ... }` keyed by country **name**, raw (un-normalized) values, `None` for missing.

- [ ] **Step 1: Write `data/fallback_oecd_wgi_asean.csv`** with header `country,rule_of_law,control_corruption,reg_quality,co2_pc,renew_share,lfp,gender_lfp_ratio,env_policy,injury_rate` and the six data rows from the table above (empty cells for `env_policy`/`injury_rate`). Example first row:

```csv
country,rule_of_law,control_corruption,reg_quality,co2_pc,renew_share,lfp,gender_lfp_ratio,env_policy,injury_rate
Singapore,1.431,1.968,2.132,12.605,1.1,69.673,84.340,,
Malaysia,0.345,0.498,0.680,9.342,7.5,66.120,65.197,,
Indonesia,-0.207,-0.545,0.125,4.670,20.2,67.965,65.291,,
Thailand,-0.216,-0.527,0.106,5.894,19.0,66.678,78.637,,
Philippines,-0.574,-0.577,0.079,2.301,28.0,61.350,69.675,,
Vietnam,-0.314,-0.252,-0.267,5.785,24.2,72.778,88.650,,
```

- [ ] **Step 2: Write the failing test** — append to `selftest.py` (inside its check-runner style; use the same `check(name, cond)` helper the file already uses). If `selftest.py` uses bare asserts in functions, mirror that. Test content:

```python
def test_esg_data_fallback_roundtrip():
    import esg_data, tempfile, os
    t = esg_data.load_fallback()
    assert set(t.keys()) == set(esg_data.COUNTRIES.values()), "6 countries by name"
    assert abs(t["Singapore"]["rule_of_law"] - 1.431) < 1e-6
    assert t["Singapore"]["env_policy"] is None, "missing cell -> None"
    # round-trip: save then reload equals original
    fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
    esg_data.save_fallback(t, p)
    t2 = esg_data.load_fallback(p)
    assert t2["Vietnam"]["gender_lfp_ratio"] == t["Vietnam"]["gender_lfp_ratio"]
    assert t2["Philippines"]["injury_rate"] is None
    os.remove(p)
```

- [ ] **Step 3: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import esg_data"`
Expected: FAIL `ModuleNotFoundError: No module named 'esg_data'`

- [ ] **Step 4: Implement the skeleton + load/save** in `esg_data.py`:

```python
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
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python -c "import selftest" 2>&1 | tail -3` then `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | tail -3`
Expected: the new `test_esg_data_fallback_roundtrip` passes; existing checks still green.

- [ ] **Step 6: Commit**

```bash
git add esg_data.py data/fallback_oecd_wgi_asean.csv selftest.py
git commit -m "feat(esg_data): bundled WGI/OECD fallback CSV + load/save round-trip"
```

---

## Task 2: `normalize()` — raw indicators → 0–100 per-country table

**Files:**
- Modify: `esg_data.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `INDICATOR_META`, the raw table shape from Task 1.
- Produces: `normalize(raw_table) -> dict` of `{country: {indicator: float_0_100 | None}}`. Normalization per direction: `wgi` → `(v+2.5)/5*100`; `down` (CO₂) → `(1 - clamp(v,0,CO2_CAP)/CO2_CAP)*100` with `CO2_CAP=20.0`; `renew` → `clamp(v,0,RENEW_CAP)/RENEW_CAP*100` with `RENEW_CAP=50.0`; `lfp` → `clamp((v-LFP_LO)/(LFP_HI-LFP_LO),0,1)*100` with `LFP_LO=40, LFP_HI=80`; `ratio` → `clamp(v,0,100)`; `up` → `clamp(v,0,100)`. `None` stays `None`. All results clamped to [0,100].

- [ ] **Step 1: Write the failing test** (append to `selftest.py`):

```python
def test_esg_data_normalize():
    import esg_data
    raw = esg_data.load_fallback()
    norm = esg_data.normalize(raw)
    sg = norm["Singapore"]
    # WGI: (1.431+2.5)/5*100 = 78.62
    assert abs(sg["rule_of_law"] - 78.62) < 0.1
    # CO2 inverted, cap 20: (1-12.605/20)*100 = 36.975
    assert abs(sg["co2_pc"] - 36.975) < 0.05
    # renew cap 50: 1.1/50*100 = 2.2
    assert abs(sg["renew_share"] - 2.2) < 0.05
    # missing stays None
    assert sg["env_policy"] is None and sg["injury_rate"] is None
    # all present values within [0,100]
    for c in norm.values():
        for v in c.values():
            assert v is None or (0.0 <= v <= 100.0)
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import esg_data; print(hasattr(esg_data,'normalize'))"`
Expected: prints `False` (function missing) → test fails.

- [ ] **Step 3: Implement** in `esg_data.py`:

```python
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
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i normalize`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esg_data.py selftest.py
git commit -m "feat(esg_data): normalize indicators to 0-100 with direction handling"
```

---

## Task 3: `fetch_worldbank()` + `get_country_table()` orchestration (live → fallback → cache)

**Files:**
- Modify: `esg_data.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `core.http_get`, `core.parse_json` (or `json`), `COUNTRIES`, `INDICATOR_META`, `normalize`, `load_fallback`, `save_fallback`.
- Produces: `fetch_worldbank(*, timeout=5) -> dict|None` (raw table or None on any failure); `get_country_table(*, allow_live=True, log=print) -> (table_normalized, origin)` where `origin in {"live","fallback"}`. Never raises.

- [ ] **Step 1: Write the failing test** (append to `selftest.py`) — uses monkeypatched `core.http_get`, no network:

```python
def test_get_country_table_live_then_fallback(tmp_path=None):
    import esg_data, core, json
    # --- success path: mock returns a valid WB payload for any indicator ---
    def fake_ok(url, params=None, **kw):
        # derive indicator from url tail; return the same value for all 6 countries
        rows = [{"countryiso3code": iso, "date": "2024", "value": 1.0}
                for iso in esg_data.COUNTRIES]
        return json.dumps([{"page": 1}, rows])
    orig = core.http_get
    core.http_get = fake_ok
    try:
        table, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "live"
        assert set(table.keys()) == set(esg_data.COUNTRIES.values())
    finally:
        core.http_get = orig
    # --- failure path: mock raises -> fallback, never raises ---
    def fake_fail(url, params=None, **kw):
        raise RuntimeError("network down")
    core.http_get = fake_fail
    try:
        table, origin = esg_data.get_country_table(log=lambda *a: None)
        assert origin == "fallback"
        assert abs(table["Singapore"]["rule_of_law"] - 78.62) < 0.1  # normalized fallback
    finally:
        core.http_get = orig
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import esg_data; print(hasattr(esg_data,'get_country_table'))"`
Expected: `False`.

- [ ] **Step 3: Implement** in `esg_data.py`:

```python
import json as _json
import core

WB_BASE = "https://api.worldbank.org/v2"


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
    """Orchestrate live -> fallback -> cache. Returns (normalized_table, origin). Never raises.

    On a successful live pull, merges in the bundled CSV's OECD/ILO-only columns (env_policy,
    injury_rate) so they are not lost, then caches the merged raw table back to the CSV."""
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
                save_fallback(raw)
            except Exception:
                pass
            log("[esg_data] country indicators: LIVE (World Bank)")
            return normalize(raw), "live"
    log("[esg_data] country indicators: FALLBACK (bundled CSV)")
    return normalize(load_fallback()), "fallback"
```

> Note: `core.http_get` accepts `timeout=`; passing it through keeps the 5s budget. If a mock omits `timeout` in its signature, use `**kw` (as the test's fakes do).

- [ ] **Step 4: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i country_table`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esg_data.py selftest.py
git commit -m "feat(esg_data): live World Bank fetch with fallback + cache orchestration"
```

---

## Task 4: `parse_upload()` — CSV-upload override

**Files:**
- Modify: `esg_data.py`
- Modify: `selftest.py`

**Interfaces:**
- Produces: `parse_upload(text_or_file) -> dict` raw table (same shape as `load_fallback`), accepting a CSV string or a file-like object with `.read()`. Columns matched case-insensitively to `INDICATORS`; unknown columns ignored; missing `country` rows skipped.

- [ ] **Step 1: Write the failing test** (append to `selftest.py`):

```python
def test_esg_data_parse_upload():
    import esg_data
    csv_text = ("country,rule_of_law,co2_pc\n"
                "Singapore,2.0,10\n"
                "Vietnam,-0.5,6\n")
    t = esg_data.parse_upload(csv_text)
    assert abs(t["Singapore"]["rule_of_law"] - 2.0) < 1e-6
    assert abs(t["Vietnam"]["co2_pc"] - 6.0) < 1e-6
    assert t["Singapore"]["renew_share"] is None  # absent column -> None
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import esg_data; print(hasattr(esg_data,'parse_upload'))"`
Expected: `False`.

- [ ] **Step 3: Implement** in `esg_data.py`:

```python
import io


def parse_upload(text_or_file):
    """Parse an uploaded CSV (string or file-like) into a raw table. Unknown cols ignored;
    absent indicators -> None. Lets the user override the bundled data when re-tuning."""
    text = text_or_file.read() if hasattr(text_or_file, "read") else text_or_file
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(text))
    lower = {c.lower(): c for c in (reader.fieldnames or [])}
    table = {}
    for row in reader:
        country = (row.get(lower.get("country", "country"), "") or "").strip()
        if not country:
            continue
        table[country] = {k: _to_float(row.get(lower.get(k))) if lower.get(k) else None
                          for k in INDICATORS}
    return table
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i parse_upload`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esg_data.py selftest.py
git commit -m "feat(esg_data): CSV-upload override (parse_upload)"
```

---

## Task 5: `esg_scoring.py` — synthetic company scoring (pure, deterministic)

**Files:**
- Create: `esg_scoring.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: a normalized country row `{indicator: 0..100|None}` (from `esg_data.normalize`), `esg_data.INDICATOR_META` (for pillar grouping).
- Produces: `INDICATOR_WEIGHTS`, `PILLAR_WEIGHTS`, `SECTOR_MULTIPLIERS`, `VARIANCE_PCT`; `score_company(country_row, sector, *, name, country="") -> dict` returning `{"e_score","s_score","g_score","overall","breakdown":{...},"data_provenance"}` all 0–100 floats (1 dp). Deterministic: same `name` → same scores. `pillar_score(country_row, pillar) -> float|None` (re-weights over present indicators).

- [ ] **Step 1: Write the failing test** (append to `selftest.py`):

```python
def test_esg_scoring_deterministic_and_bounded():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Singapore"]
    a = esg_scoring.score_company(row, "Financials — Banks", name="DemoBank", country="Singapore")
    b = esg_scoring.score_company(row, "Financials — Banks", name="DemoBank", country="Singapore")
    assert a == b, "deterministic: same name -> identical scores"
    for k in ("e_score", "s_score", "g_score", "overall"):
        assert 0.0 <= a[k] <= 100.0
    # breakdown mirrors top-level
    assert a["breakdown"]["overall"] == a["overall"]
    # provenance present, no real_world_basis leak possible (name only)
    assert "country-level" in a["data_provenance"].lower()

def test_esg_scoring_sector_multiplier_effect():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Singapore"]
    bank = esg_scoring.score_company(row, "Financials — Banks", name="X Bank")
    power = esg_scoring.score_company(row, "Energy — Power & Renewables", name="X Bank")
    # banks tilt G up vs energy; energy tilts E up vs banks (same base row, same seed)
    assert bank["g_score"] > power["g_score"]
    assert power["e_score"] > bank["e_score"]

def test_esg_scoring_variance_differs_by_name():
    import esg_data, esg_scoring
    row = esg_data.normalize(esg_data.load_fallback())["Malaysia"]
    s1 = esg_scoring.score_company(row, "Real Estate", name="Alpha")
    s2 = esg_scoring.score_company(row, "Real Estate", name="Beta")
    assert s1["overall"] != s2["overall"], "seeded variance separates same-country peers"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import esg_scoring"`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `esg_scoring.py`:

```python
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
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i scoring`
Expected: all three scoring checks PASS.

- [ ] **Step 5: Commit**

```bash
git add esg_scoring.py selftest.py
git commit -m "feat(esg_scoring): deterministic country->company ESG scoring"
```

---

## Task 6: `data/demo_config.json` roster + `load_config()` validator

**Files:**
- Create: `data/demo_config.json`
- Create: `demo_roster.py` (small loader/validator — keeps `build_demo_universe.py` focused)
- Modify: `selftest.py`

**Interfaces:**
- Produces: `demo_roster.load_config(path=...) -> list[dict]`; each entry `{name, country, sector, real_world_basis, ticker, exchange}`. `load_config` validates required keys, unique tickers, country ∈ `esg_data.COUNTRIES.values()`, and raises `ValueError` on a malformed roster.

- [ ] **Step 1: Write `data/demo_config.json`** — 36 companies, 6 countries × 5 sectors (6 banks, and the other four sectors distributed so every country appears ≥4×). `real_world_basis` is internal. Skeleton (fill all 36; tickers unique, `EXCH:SYMBOL` form):

```json
{
  "note": "DEMO roster — fictional companies, synthetic scores grounded in real country data. real_world_basis is internal-only and never rendered.",
  "companies": [
    {"name": "DemoBank", "country": "Singapore", "sector": "Financials — Banks", "real_world_basis": "DBS", "ticker": "SGX:DBKO", "exchange": "SGX"},
    {"name": "Selat Bank", "country": "Malaysia", "sector": "Financials — Banks", "real_world_basis": "Maybank", "ticker": "KLSE:SLTB", "exchange": "KLSE"},
    {"name": "Garuda Mandiri Bank", "country": "Indonesia", "sector": "Financials — Banks", "real_world_basis": "Bank Mandiri", "ticker": "IDX:GRMB", "exchange": "IDX"},
    {"name": "Mekong Commercial Bank", "country": "Thailand", "sector": "Financials — Banks", "real_world_basis": "SCB", "ticker": "SET:MKCB", "exchange": "SET"},
    {"name": "Pearl Savings", "country": "Philippines", "sector": "Financials — Banks", "real_world_basis": "BDO", "ticker": "PSE:PRLS", "exchange": "PSE"},
    {"name": "Lac Viet Bank", "country": "Vietnam", "sector": "Financials — Banks", "real_world_basis": "Vietcombank", "ticker": "HOSE:LVTB", "exchange": "HOSE"},
    {"name": "NovaTel", "country": "Singapore", "sector": "Communication Services — Telecom", "real_world_basis": "Singtel", "ticker": "SGX:NVTL", "exchange": "SGX"},
    {"name": "Tiger Bay Telecom", "country": "Malaysia", "sector": "Communication Services — Telecom", "real_world_basis": "Maxis", "ticker": "KLSE:TBTL", "exchange": "KLSE"},
    {"name": "ASEAN Mobile", "country": "Indonesia", "sector": "Communication Services — Telecom", "real_world_basis": "Telkomsel", "ticker": "IDX:ASMB", "exchange": "IDX"},
    {"name": "SiamConnect", "country": "Thailand", "sector": "Communication Services — Telecom", "real_world_basis": "AIS", "ticker": "SET:SMCN", "exchange": "SET"},
    {"name": "LunaComm", "country": "Philippines", "sector": "Communication Services — Telecom", "real_world_basis": "Globe", "ticker": "PSE:LUNA", "exchange": "PSE"},
    {"name": "Mekong Mobile", "country": "Vietnam", "sector": "Communication Services — Telecom", "real_world_basis": "Viettel", "ticker": "HOSE:MKMB", "exchange": "HOSE"},
    {"name": "GreenGrid", "country": "Singapore", "sector": "Energy — Power & Renewables", "real_world_basis": "Sembcorp", "ticker": "SGX:GRGD", "exchange": "SGX"},
    {"name": "Suria Power", "country": "Malaysia", "sector": "Energy — Power & Renewables", "real_world_basis": "Tenaga", "ticker": "KLSE:SURP", "exchange": "KLSE"},
    {"name": "Borneo Energy", "country": "Indonesia", "sector": "Energy — Power & Renewables", "real_world_basis": "PLN", "ticker": "IDX:BRNE", "exchange": "IDX"},
    {"name": "ThaiSolar", "country": "Thailand", "sector": "Energy — Power & Renewables", "real_world_basis": "EGCO", "ticker": "SET:THSL", "exchange": "SET"},
    {"name": "Bayan Power", "country": "Philippines", "sector": "Energy — Power & Renewables", "real_world_basis": "AboitizPower", "ticker": "PSE:BYNP", "exchange": "PSE"},
    {"name": "Red River Renewables", "country": "Vietnam", "sector": "Energy — Power & Renewables", "real_world_basis": "PV Power", "ticker": "HOSE:RRRE", "exchange": "HOSE"},
    {"name": "Marina Estates", "country": "Singapore", "sector": "Real Estate", "real_world_basis": "CapitaLand", "ticker": "SGX:MRNA", "exchange": "SGX"},
    {"name": "KLCC Towers", "country": "Malaysia", "sector": "Real Estate", "real_world_basis": "KLCCP", "ticker": "KLSE:KLCT", "exchange": "KLSE"},
    {"name": "Jakarta Land", "country": "Indonesia", "sector": "Real Estate", "real_world_basis": "Bumi Serpong", "ticker": "IDX:JKLD", "exchange": "IDX"},
    {"name": "Bangkok Heights", "country": "Thailand", "sector": "Real Estate", "real_world_basis": "Central Pattana", "ticker": "SET:BKHT", "exchange": "SET"},
    {"name": "Bayan Realty", "country": "Philippines", "sector": "Real Estate", "real_world_basis": "Ayala Land", "ticker": "PSE:BYNR", "exchange": "PSE"},
    {"name": "Saigon Square Estates", "country": "Vietnam", "sector": "Real Estate", "real_world_basis": "Vinhomes", "ticker": "HOSE:SSQE", "exchange": "HOSE"},
    {"name": "Lion City Provisions", "country": "Singapore", "sector": "Consumer Staples", "real_world_basis": "Wilmar", "ticker": "SGX:LNCP", "exchange": "SGX"},
    {"name": "Tiger Bay Foods", "country": "Malaysia", "sector": "Consumer Staples", "real_world_basis": "Nestlé MY", "ticker": "KLSE:TBFD", "exchange": "KLSE"},
    {"name": "NusaFoods", "country": "Indonesia", "sector": "Consumer Staples", "real_world_basis": "Indofood", "ticker": "IDX:NUSA", "exchange": "IDX"},
    {"name": "FreshHarvest", "country": "Thailand", "sector": "Consumer Staples", "real_world_basis": "CP Foods", "ticker": "SET:FRHV", "exchange": "SET"},
    {"name": "Pearl Provisions", "country": "Philippines", "sector": "Consumer Staples", "real_world_basis": "Universal Robina", "ticker": "PSE:PRLP", "exchange": "PSE"},
    {"name": "Mekong Harvest", "country": "Vietnam", "sector": "Consumer Staples", "real_world_basis": "Masan", "ticker": "HOSE:MKHV", "exchange": "HOSE"},
    {"name": "Orchid Bank", "country": "Singapore", "sector": "Financials — Banks", "real_world_basis": "OCBC", "ticker": "SGX:ORCB", "exchange": "SGX"},
    {"name": "Sampan Bank", "country": "Thailand", "sector": "Financials — Banks", "real_world_basis": "Kasikorn", "ticker": "SET:SMPN", "exchange": "SET"},
    {"name": "SatBank", "country": "Indonesia", "sector": "Financials — Banks", "real_world_basis": "BCA", "ticker": "IDX:SATB", "exchange": "IDX"},
    {"name": "Hai Au Telecom", "country": "Vietnam", "sector": "Communication Services — Telecom", "real_world_basis": "FPT Telecom", "ticker": "HOSE:HATL", "exchange": "HOSE"},
    {"name": "Selat Power", "country": "Malaysia", "sector": "Energy — Power & Renewables", "real_world_basis": "YTL Power", "ticker": "KLSE:SLTP", "exchange": "KLSE"},
    {"name": "Manila Harvest", "country": "Philippines", "sector": "Consumer Staples", "real_world_basis": "San Miguel", "ticker": "PSE:MNHV", "exchange": "PSE"}
  ]
}
```

- [ ] **Step 2: Write the failing test** (append to `selftest.py`):

```python
def test_demo_roster_valid():
    import demo_roster, esg_data
    cfg = demo_roster.load_config()
    assert len(cfg) == 36
    tickers = [c["ticker"] for c in cfg]
    assert len(set(tickers)) == 36, "tickers unique"
    valid_countries = set(esg_data.COUNTRIES.values())
    for c in cfg:
        assert c["country"] in valid_countries
        for key in ("name", "country", "sector", "real_world_basis", "ticker", "exchange"):
            assert key in c
    # every country represented
    assert valid_countries <= {c["country"] for c in cfg}
```

- [ ] **Step 3: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import demo_roster"`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 4: Implement** `demo_roster.py`:

```python
"""Load + validate the demo company roster (data/demo_config.json)."""
import json, os
import esg_data

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo_config.json")
_REQUIRED = ("name", "country", "sector", "real_world_basis", "ticker", "exchange")


def load_config(path=CONFIG):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    companies = raw.get("companies") if isinstance(raw, dict) else raw
    if not isinstance(companies, list) or not companies:
        raise ValueError("demo_config: 'companies' must be a non-empty list")
    valid_countries = set(esg_data.COUNTRIES.values())
    seen = set()
    for c in companies:
        missing = [k for k in _REQUIRED if k not in c]
        if missing:
            raise ValueError(f"demo_config: {c.get('name','?')} missing {missing}")
        if c["country"] not in valid_countries:
            raise ValueError(f"demo_config: unknown country {c['country']}")
        if c["ticker"] in seen:
            raise ValueError(f"demo_config: duplicate ticker {c['ticker']}")
        seen.add(c["ticker"])
    return companies
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i roster`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data/demo_config.json demo_roster.py selftest.py
git commit -m "feat(demo): fresh 36-company roster config + validator"
```

---

## Task 7: Illustrative-field generators (momentum / live_signals / market / news)

**Files:**
- Create: `demo_enrich.py`
- Modify: `selftest.py`

**Interfaces:**
- Consumes: a roster entry dict + its scores dict (from Task 5).
- Produces (all deterministic from `name`, all clearly illustrative): `momentum(name, breakdown) -> {"environment","social","governance","digital_ai"}` (ints), `live_signals(name) -> {...}`, `market(name, exchange) -> {...}`, `news(name) -> [..]`, `analyst_coverage(name) -> {...}`, `price_change_90d(name) -> str`. These regenerate the existing demo schema's illustrative blocks for the fresh roster so cards stay populated. Helper `_rng(name, salt) -> float in [0,1)` (stable hash) and `_pick(name, salt, lo, hi)`.

- [ ] **Step 1: Write the failing test** (append to `selftest.py`):

```python
def test_demo_enrich_deterministic_and_labelled():
    import demo_enrich
    bd = {"e_score": 60.0, "s_score": 55.0, "g_score": 70.0, "overall": 61.0}
    m1 = demo_enrich.momentum("DemoBank", bd)
    m2 = demo_enrich.momentum("DemoBank", bd)
    assert m1 == m2 and set(m1) == {"environment", "social", "governance", "digital_ai"}
    news = demo_enrich.news("DemoBank")
    assert news and all("url" not in n for n in news), "no fabricated URLs (HARD RULE 2)"
    assert any("illustrative" in n["source"].lower() for n in news)
    mk = demo_enrich.market("DemoBank", "SGX")
    assert mk["currency"] == "SGD" and isinstance(mk["price"], float)
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import demo_enrich"`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `demo_enrich.py`:

```python
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
    return {"currency": ccy, "price": price,
            "open": round(price * (1 + _pick(name, "o", -0.01, 0.01)), 2),
            "high": round(price * (1 + _pick(name, "hi", 0.005, 0.03)), 2),
            "low": round(price * (1 - _pick(name, "lo", 0.005, 0.03)), 2),
            "prev_close": round(price * (1 + _pick(name, "pc", -0.02, 0.02)), 2),
            "market_cap": f"{ccy} {round(_pick(name,'mc',2,90),1)}B",
            "pe_ratio": round(_pick(name, "pe", 8, 22), 1),
            "dividend_yield": f"{round(_pick(name,'dy',1,6),1)}%",
            "week52_high": round(price * (1 + _pick(name, "wh", 0.05, 0.25)), 2),
            "week52_low": round(price * (1 - _pick(name, "wl", 0.05, 0.25)), 2),
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
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i enrich`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add demo_enrich.py selftest.py
git commit -m "feat(demo): deterministic illustrative enrichment for fresh roster"
```

---

## Task 8: `build_demo_universe.py` — generate `data/demo_universe.json`

**Files:**
- Create: `build_demo_universe.py`
- Modify: `data/demo_universe.json` (regenerated by running the script)
- Modify: `selftest.py`

**Interfaces:**
- Consumes: `esg_data.get_country_table`, `demo_roster.load_config`, `esg_scoring.score_company`, `demo_enrich.*`.
- Produces: `build(allow_live=False) -> dict` (the full universe dict) and a `main()` that writes `data/demo_universe.json`. Each constituent carries: `company, ticker, exchange, country, sector, esg_score` (=overall, 0–100 ↑better), `esg_as_of`, `esg_breakdown`, `data_provenance`, plus illustrative `momentum, live_signals, market, news, analyst_coverage, price_change_90d`. **No `real_world_basis` key in any constituent.**

- [ ] **Step 1: Write the failing test** (append to `selftest.py`):

```python
def test_build_demo_universe_schema_and_no_leak():
    import build_demo_universe
    uni = build_demo_universe.build(allow_live=False)   # offline -> bundled CSV
    cons = uni["constituents"]
    assert len(cons) == 36
    for c in cons:
        assert "real_world_basis" not in c, "internal field must never leak"
        assert 0.0 <= c["esg_score"] <= 100.0, "0-100 higher=better"
        assert set(c["esg_breakdown"]) == {"e_score", "s_score", "g_score", "overall"}
        assert "data_provenance" in c and c["data_provenance"]
        for k in ("momentum", "market", "news", "live_signals"):
            assert k in c
    # serialized JSON also has no leak
    import json
    assert "real_world_basis" not in json.dumps(uni)
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python -c "import build_demo_universe"`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `build_demo_universe.py`:

```python
"""Generate data/demo_universe.json from real country data + the demo roster.

Pipeline: get_country_table (live->fallback) -> score each roster company -> attach
illustrative enrichment -> write the universe. real_world_basis is dropped (internal-only)."""
import json, os
import esg_data, esg_scoring, demo_enrich, demo_roster

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo_universe.json")


def build(allow_live=False):
    table, origin = esg_data.get_country_table(allow_live=allow_live, log=lambda *a: None)
    roster = demo_roster.load_config()
    constituents = []
    for c in roster:
        row = table.get(c["country"]) or {}
        sc = esg_scoring.score_company(row, c["sector"], name=c["name"], country=c["country"])
        bd = sc["breakdown"]
        constituents.append({
            "company": c["name"], "ticker": c["ticker"], "exchange": c["exchange"],
            "country": c["country"], "sector": c["sector"],
            "esg_score": sc["overall"], "esg_as_of": "2024",
            "esg_breakdown": bd, "data_provenance": sc["data_provenance"],
            "momentum": demo_enrich.momentum(c["name"], bd),
            "live_signals": demo_enrich.live_signals(c["name"]),
            "market": demo_enrich.market(c["name"], c["exchange"]),
            "news": demo_enrich.news(c["name"]),
            "analyst_coverage": demo_enrich.analyst_coverage(c["name"]),
            "price_change_90d": demo_enrich.price_change_90d(c["name"]),
        })
    return {
        "note": ("DEMO universe — fictional companies, scores DERIVED from real country-level "
                 "OECD/World Bank indicators (sector-adjusted). Illustrative, not company disclosure."),
        "selection": "ASEAN ESG demo basket (6 countries × 5 sectors)",
        "benchmark": "MSCI ASEAN ESG (illustrative benchmark)",
        "benchmark_stats": {"basket_return": "55.1%", "benchmark_return": "6.4%", "window": "2019–2023"},
        "as_of": "2026-06-30", "data_origin": origin,
        "countries": sorted({c["country"] for c in roster}),
        "constituents": constituents,
    }


def main():
    uni = build(allow_live=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(uni, f, indent=2, ensure_ascii=False)
    print(f"[build_demo_universe] wrote {len(uni['constituents'])} constituents "
          f"(country data: {uni['data_origin']}) -> {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test, then regenerate the file**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i build_demo`
Expected: PASS.
Then regenerate the committed artifact (best-effort live, falls back offline):
Run: `PYTHONPATH=. ./venv/bin/python build_demo_universe.py`
Expected: prints `wrote 36 constituents ...`.

- [ ] **Step 5: Verify `universe.py` still loads it** (the app's loader must accept the regenerated file):

Run: `PYTHONPATH=. ./venv/bin/python -c "import universe; u=universe.load_universe(demo=True) if hasattr(universe,'load_universe') else None; print('loaded')"`
Expected: prints `loaded` (adjust to the real loader name found in `universe.py`; if `_coerce_constituent` drops unknown keys, confirm `esg_breakdown`/`data_provenance` survive — see Task 9).

- [ ] **Step 6: Commit**

```bash
git add build_demo_universe.py data/demo_universe.json selftest.py
git commit -m "feat(demo): generate demo_universe.json from real country data (0-100 higher=better)"
```

---

## Task 9: 0–100 switch in `universe.py` / `datasource.py` / `metrics.py`

**Files:**
- Modify: `universe.py` (`_coerce_constituent` — pass through `esg_breakdown`, `data_provenance`)
- Modify: `datasource.py` (`company_from_numeric` — ride new fields; flip layer_a note text)
- Modify: `metrics.py` (line-14 comment; `classify` wording; add `esg_breakdown(company)` passthrough helper)
- Modify: `selftest.py`

**Interfaces:**
- Consumes: regenerated constituents with `esg_score` (0–100 ↑better), `esg_breakdown`, `data_provenance`.
- Produces: `metrics.esg_breakdown(company) -> dict|None`; `datasource.company_from_numeric` Contract B with `layer_a.note` = "Performance score: HIGHER = better." and `_esg_breakdown`/`_data_provenance` non-contract ride-alongs.

- [ ] **Step 1: Read the exact current code** to edit precisely:

Run: `PYTHONPATH=. ./venv/bin/python - <<'PY'
import re
for f in ("universe.py","datasource.py"):
    s=open(f).read()
    for pat in ("_coerce_constituent","company_from_numeric","LOWER = better","Risk score","esg_score"):
        for m in re.finditer(re.escape(pat), s):
            ln=s.count("\n",0,m.start())+1; print(f"{f}:{ln}: {pat}")
PY`
Expected: line numbers for each anchor. Use them for the edits below.

- [ ] **Step 2: Write the failing test** (append to `selftest.py`):

```python
def test_company_from_numeric_rides_breakdown_and_note():
    import datasource
    c = {"company": "DemoBank", "ticker": "SGX:DBKO", "sector": "Financials — Banks",
         "esg_score": 64.0, "esg_as_of": "2024",
         "esg_breakdown": {"e_score": 19.0, "s_score": 79.0, "g_score": 95.0, "overall": 64.0},
         "data_provenance": "Derived from country-level proxies.",
         "momentum": {"environment": 5, "social": 3, "governance": 8, "digital_ai": 20}}
    cd = datasource.company_from_numeric(c)
    assert "HIGHER" in cd["layer_a"]["note"], "note flipped to higher=better"
    assert cd.get("_esg_breakdown", {}).get("g_score") == 95.0
    assert "country-level" in cd.get("_data_provenance", "").lower()

def test_metrics_esg_breakdown_passthrough():
    import metrics
    comp = {"esg_breakdown": {"e_score": 1, "s_score": 2, "g_score": 3, "overall": 4}}
    assert metrics.esg_breakdown(comp)["g_score"] == 3
    assert metrics.esg_breakdown({}) is None
```

- [ ] **Step 3: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -iE "breakdown|note" | head`
Expected: failures (functions/behaviour missing).

- [ ] **Step 4: Implement the edits**

In `universe.py` `_coerce_constituent`, add to the passthrough of non-contract keys (alongside `market`/`news`/etc.) — keep existing lines, add:
```python
        if "esg_breakdown" in raw:
            out["esg_breakdown"] = raw["esg_breakdown"]
        if "data_provenance" in raw:
            out["data_provenance"] = raw["data_provenance"]
```
In `datasource.py` `company_from_numeric`: locate where `layer_a` is built and the note string is set (the "Risk score: LOWER = better" text). Replace that note with:
```python
        "note": "Performance score: HIGHER = better. Country-proxy baseline.",
```
and where it rides non-contract keys (e.g. `_market`, `_price_change_90d`), add:
```python
    cd["_esg_breakdown"] = c.get("esg_breakdown")
    cd["_data_provenance"] = c.get("data_provenance")
```
(Use the exact variable name the function returns — `cd`/`out`/`company` — from Step 1.)
In `metrics.py`: update the line-14 comment from `(lower = better for risk)` to `(0–100, higher = better)`. Remove/replace any "risk"/"lower=better" wording in `classify`'s output string (the logic uses momentum, unchanged). Add the helper near `average_esg`:
```python
def esg_breakdown(company):
    """The E/S/G/overall 0-100 breakdown a demo constituent carries, or None (evidence names)."""
    bd = (company or {}).get("esg_breakdown")
    return bd if isinstance(bd, dict) and bd else None
```

- [ ] **Step 5: Run the tests, verify they pass**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | tail -5`
Expected: the two new tests PASS. Fix any now-failing legacy assertions that pinned risk-style values (Task 11 covers the sweep).

- [ ] **Step 6: Commit**

```bash
git add universe.py datasource.py metrics.py selftest.py
git commit -m "feat: switch demo ESG score to 0-100 higher=better; ride breakdown+provenance"
```

---

## Task 10: `app.py` — enable Monitor in demo, render breakdown/provenance, startup refresh

**Files:**
- Modify: `app.py` (`_universe_cards` ~line 1393; deep-dive render; session init)
- Modify: `selftest.py` (AppTest smoke already exists in the offline harness; extend if present)

**Interfaces:**
- Consumes: `esg_data.get_country_table`, `metrics.esg_breakdown`, constituents' `data_provenance`.

- [ ] **Step 1: Write the failing check** — a headless AppTest asserting Monitor is enabled in demo mode. Append to `selftest.py` (guard with a `try: from streamlit.testing.v1 import AppTest` so the offline harness skips cleanly if Streamlit is absent):

```python
def test_monitor_enabled_in_demo_mode():
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        return  # streamlit not available in this env -> skip
    at = AppTest.from_file("app.py", default_timeout=60); at.run()
    # find the universe '➕ Monitor' buttons; in demo mode they must NOT all be disabled
    mon = [b for b in at.button if "Monitor" in (b.label or "")]
    assert mon, "expected Monitor buttons in the browse grid"
    assert any(not b.disabled for b in mon), "Monitor must be enabled in demo mode"
    assert not at.exception
```

- [ ] **Step 2: Run it, verify it fails**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i monitor_enabled`
Expected: FAIL (buttons disabled in demo).

- [ ] **Step 3: Implement the edits in `app.py`**

At `app.py:1393-1396`, remove the demo-mode disable:
```python
                    elif b2.button("➕ Monitor", key=f"umon_{tk}", use_container_width=True):
                        _build_and_pin_constituent(ss, c)
                        st.rerun()
```
Update the caption at `app.py:1368` to drop "(real mode only)":
```python
    st.caption("Filtered by the panel on the left. 🎯 Focus features a company in the right-rail "
               "panels; ➕ Monitor builds an ESG snapshot and pins it to your watchlist.")
```
In the deep-dive renderer (find where `data_provenance` / breakdown should show — near the Layer-B evidence block), add a methodology line using `metrics.esg_breakdown(company)` and the `_data_provenance` ride-along:
```python
    bd = metrics.esg_breakdown(comp) or (comp.get("_esg_breakdown") if isinstance(comp, dict) else None)
    if bd:
        st.caption(f"ESG breakdown — E {bd['e_score']:.0f} · S {bd['s_score']:.0f} · "
                   f"G {bd['g_score']:.0f} · overall {bd['overall']:.0f} (0–100, higher=better)")
    prov = comp.get("_data_provenance") or comp.get("data_provenance")
    if prov:
        st.caption(f"📑 {prov}")
```
At session init (where `_DEFAULTS` / startup runs), call the country-table refresh once, cached, best-effort:
```python
@st.cache_data(show_spinner=False)
def _country_data_origin():
    try:
        import esg_data
        _table, origin = esg_data.get_country_table()
        return origin
    except Exception:
        return "fallback"
```
and invoke `_country_data_origin()` once early in the main render so the live pull + cache happens on first load (origin is available for an optional caption; failure is silent).

- [ ] **Step 4: Run the smoke check + full AppTest, verify pass**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -i monitor_enabled`
Expected: PASS.
Run the broader render smoke (reuse the scratch smoke from session start or AppTest across modes):
Run: `PYTHONPATH=. ./venv/bin/python -c "import sys; sys.path.insert(0,'.'); from streamlit.testing.v1 import AppTest; at=AppTest.from_file('app.py',default_timeout=90); at.run(); print('exc:', list(at.exception))"`
Expected: `exc: []`.

- [ ] **Step 5: Commit**

```bash
git add app.py selftest.py
git commit -m "feat(app): enable Monitor in demo mode + render ESG breakdown/provenance + startup data refresh"
```

---

## Task 11: Sweep legacy risk-style assertions; full green selftest

**Files:**
- Modify: `selftest.py` (and any test fixtures pinned to old risk-style values / old demo company names)

**Interfaces:** none new — this task makes `python selftest.py` fully green after the 0–100 switch and roster change.

- [ ] **Step 1: Run the full suite, list every failure**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | grep -iE "FAIL|Error|Traceback" | head -40`
Expected: a list of legacy checks that assumed risk-style scores (e.g. `esg=22.4`), the old 26-name roster, or "lower=better" copy.

- [ ] **Step 2: Fix each failing assertion** to the new convention. For each: if it pinned a specific old `esg_score`, re-derive the expected via the pipeline or assert the property (0–100, ordering) instead of a magic number; if it referenced a removed demo company name, switch to a name in the new roster (e.g. `DemoBank`, `NovaTel`, `GreenGrid`); if it asserted "lower=better"/"risk" copy, update to "higher=better". Show the change inline per assertion (no blanket edits).

- [ ] **Step 3: Re-run until green**

Run: `PYTHONPATH=. ./venv/bin/python selftest.py 2>&1 | tail -3`
Expected: `OK — all checks passed`.

- [ ] **Step 4: Run the live end-to-end smoke** (best-effort; needs network + key, non-blocking):

Run: `PYTHONPATH=. ./venv/bin/python -c "import build_demo_universe as b; u=b.build(allow_live=True); print('origin:', u['data_origin'], '| n:', len(u['constituents']))"`
Expected: `origin: live | n: 36` (or `fallback` offline — both acceptable).

- [ ] **Step 5: Commit**

```bash
git add selftest.py
git commit -m "test: update selftest to 0-100 convention + fresh roster (all green)"
```

---

## Task 12: README methodology section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Demo-data methodology" section** to `README.md` (place after the existing data-modes description):

```markdown
## Demo-data methodology (for judges)

The demo basket's company ESG scores are **synthetic but principled** — derived from
**real country-level indicators**, because company-level ESG (MSCI/Sustainalytics) is paywalled.

- **What's real:** OECD / World Bank country indicators, live-fetched on startup with a cached
  CSV fallback (`data/fallback_oecd_wgi_asean.csv`): WGI governance (Rule of Law, Control of
  Corruption, Regulatory Quality), CO₂ per capita and renewable-energy share (E), labour-force
  participation and the female/male participation ratio (S).
- **What's synthetic:** the company **names** and their **scores**. Each demo company takes its
  country's normalized E/S/G baseline, applies a **sector materiality tilt** (banks weight
  governance higher, power/utilities weight environment higher, …) and a small **seeded variance**
  so same-country peers differ. Defined in `data/demo_config.json`; generated by
  `build_demo_universe.py`.
- **Why:** it lets us demonstrate a transparent, tunable ESG methodology grounded in real macro
  data without claiming paywalled company disclosures. Every demo score carries a
  `data_provenance` line saying so. Weights live as named constants in `esg_scoring.py`
  (`INDICATOR_WEIGHTS`, `PILLAR_WEIGHTS`, `SECTOR_MULTIPLIERS`, `VARIANCE_PCT`) — tune and re-run.
- **Scores are 0–100, higher = better**, and describe only — never buy/sell/hold.

Regenerate after tuning: `PYTHONPATH=. ./venv/bin/python build_demo_universe.py`.
Override the country data with your own OECD/WGI CSV via the app's upload, or by replacing
`data/fallback_oecd_wgi_asean.csv`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: demo-data methodology section for judges"
```

---

## Self-Review notes (verification of this plan against the spec)

- **Spec §4.1 esg_data** → Tasks 1–4 (CSV+load/save, normalize, fetch+orchestrate, upload). ✅
- **Spec §4.2 demo_config** → Task 6. ✅
- **Spec §4.3 esg_scoring** → Task 5 (constants, sector mult, seeded variance, provenance). ✅
- **Spec §4.4 build_demo_universe** → Task 8 (+ illustrative enrichment Task 7). ✅
- **Spec §5 score switch** → Task 9 (+ legacy sweep Task 11). ✅
- **Spec §6 app integration + Monitor fix** → Task 10. ✅
- **Spec §7 README** → Task 12. ✅
- **Spec §8 testing (offline, mocked http_get)** → every task is TDD; live calls mocked in tests; Task 11 keeps the suite green. ✅
- **No `real_world_basis` leak** → asserted in Tasks 6 (config has it) and 8 (output must not). ✅
- **Frozen files** → `core.py`/`contracts.py` never edited; new fields ride as non-contract keys. ✅
- **Type consistency** → `get_country_table` returns `(table, origin)` (consumed in Tasks 8/10); `score_company(...).breakdown` keys `e_score/s_score/g_score/overall` (consumed in Tasks 8/9/10); `esg_breakdown(company)` helper name consistent (Tasks 9/10). ✅
