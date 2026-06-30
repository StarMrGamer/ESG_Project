# ESG Demo-Data Pipeline — Design Spec

**Date:** 2026-06-30
**Status:** Approved (design) — awaiting spec review
**Author:** session for ASEAN ESG Momentum Radar

---

## 1. Problem

The "browse and monitor" feature is non-functional in the default demo view, for two reasons:

1. **Fabricated metadata.** The 26 demo companies in `data/demo_universe.json` carry
   hand-picked risk-style `esg_score` values (~19–38, lower=better) with **no methodology** —
   indefensible to a hackathon judge.
2. **Monitor disabled in demo mode.** `app.py:1394` sets `disabled=bool(ss.get("demo_mode"))`,
   so in the default demo view you cannot pin or build a snapshot for any company.

**Goal:** replace the fabricated company scores with a principled, reproducible pipeline that
derives synthetic company ESG scores from **real OECD / World Bank country-level indicators**,
and make browse/monitor work end-to-end in the demo. This is explicitly **DEMO** data —
fictional company names, synthetic scores — grounded in real macro data because company-level
ESG (MSCI / Sustainalytics) is paywalled.

This honors CLAUDE.md HARD RULE 2 (never fabricate): demo data is permitted and clearly
**labelled illustrative / synthetic**; the *real* `asean_universe.json` evidence universe is
untouched and stays evidence-only.

---

## 2. Decisions (locked with user, 2026-06-30)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Data sourcing | **Fetch-with-fallback.** Live World Bank API on startup (5s timeout, try/except) → on any failure use bundled `data/fallback_oecd_wgi_asean.csv` → cache successful pulls back to that CSV. Silent fallback (no error/blank UI). Plus CSV-upload override. Console-only logging of live/fallback. |
| 2 | Score scale | **Switch demo to 0–100, higher=better** (harmonizes with evidence mode, which is already 0–100). |
| 3 | Roster | **Fresh roster from a new config file** (`data/demo_config.json`). |
| 4 | Monitor fix | **Enable ➕ Monitor in demo mode.** |
| 5 | Coverage | **6 countries** (SG, MY, ID, TH, PH, VN — the sourced set), **companies expanded** from 26 → ~36. |

---

## 3. Architecture — three-layer pipeline

```
World Bank API (live, best-effort, 5s)
        │  WGI governance (+ available E/S indicators) for 6 ASEAN countries
        ▼
esg_data.py ───────► data/fallback_oecd_wgi_asean.csv   (bundled real snapshot;
   │  normalize each indicator → 0–100                     refreshed on every successful
   │  graceful missing-value handling                      live pull; CSV-upload override)
   ▼
   clean per-country E/S/G indicator table
        │
        ├──◄ data/demo_config.json   (roster: {name, country, sector, real_world_basis, ticker, exchange})
        ▼
esg_scoring.py  (pure, deterministic, configurable constants)
   │  country baseline × SECTOR_MULTIPLIERS + seeded variance
   ▼  → {e_score, s_score, g_score, overall, breakdown, data_provenance}  (all 0–100)
        │
        ▼
build_demo_universe.py ───────► data/demo_universe.json
        (existing schema, now 0–100 higher=better, + esg_breakdown + data_provenance;
         momentum / live_signals / market / news stay illustrative as before)
```

Each layer has one job, a defined interface, and is independently testable. Web fetch is
isolated through `core.http_get()` (HARD RULE 6), exactly like `rag.py`.

---

## 4. Module specs

### 4.1 `esg_data.py` — country-indicator sourcing

Isolated I/O layer. Outbound HTTP only via `core.http_get()`.

**Indicators** (World Bank codes; estimate values):

| Pillar | Indicator | WB code | Direction | Source |
|--------|-----------|---------|-----------|--------|
| G | Rule of Law | `RL.EST` | higher=better | WGI (live) |
| G | Control of Corruption | `CC.EST` | higher=better | WGI (live) |
| G | Regulatory Quality | `RQ.EST` | higher=better | WGI (live) |
| E | CO₂ emissions per capita | `EN.GHG.CO2.PC.CE` (fallback `EN.ATM.CO2E.PC`) | **lower=better (inverted)** | WB (live) |
| E | Renewable energy share | `EG.FEC.RNEW.ZS` | higher=better | WB (live) |
| E | Environmental policy stringency | — (OECD EPS, sparse ASEAN coverage) | higher=better | bundled CSV, missing-handled |
| S | Labour-force participation | `SL.TLF.CACT.ZS` | higher=better | WB (live) |
| S | Female/male LFP ratio (gender proxy) | `SL.TLF.CACT.FM.ZS` | closer to 100=better | WB (live) |
| S | Workplace injury rate | — (ILO/SDG) | lower=better (inverted) | bundled CSV, missing-handled |

**Public API:**
- `fetch_worldbank(countries, indicators, *, timeout=5) -> dict|None` — live pull; returns
  raw per-country indicator values, or `None` on any failure (caught, never raised).
- `load_fallback(path=FALLBACK_CSV) -> table` — read the bundled CSV.
- `save_fallback(table, path=FALLBACK_CSV)` — cache a successful pull (best-effort).
- `parse_upload(file_or_text) -> table` — CSV-upload override.
- `normalize(raw_table) -> table` — each indicator → 0–100 (WGI −2.5..2.5 linear map; CO₂
  inverted against a documented cap; % indicators banded), with per-cell direction handling.
- `get_country_table(*, allow_live=True) -> table` — orchestrator: live → fallback → cache;
  `print(...)`-logs `live`/`fallback` to console; **never raises, never blank**.

**Missing-value handling:** a missing indicator is `None`; pillar normalization re-weights
over present indicators; a wholly-missing pillar falls back to the 6-country group mean and is
flagged in provenance.

### 4.2 `data/demo_config.json` — roster

List of `{ "name", "country", "sector", "real_world_basis", "ticker", "exchange" }`.
`real_world_basis` is **internal-only — never rendered in the UI or in any output JSON**.
~36 entries across 6 countries × 5 sectors (Financials–Banks, Comm–Telecom, Energy–Power &
Renewables, Real Estate, Consumer Staples), each country represented (incl. Vietnam).

### 4.3 `esg_scoring.py` — synthetic company scoring (pure, deterministic)

All knobs are **named module constants**, no magic numbers:

```python
INDICATOR_WEIGHTS = {            # within each pillar (re-normalized over present indicators);
  "E": {"co2_pc": 1/3, "renew_share": 1/3, "env_policy": 1/3},   # default equal-weight,
  "S": {"lfp": 1/3, "gender_lfp_ratio": 1/3, "injury_rate": 1/3},#   tunable per indicator
  "G": {"rule_of_law": 1/3, "control_corruption": 1/3, "reg_quality": 1/3},
}
PILLAR_WEIGHTS    = {"E": 0.34, "S": 0.33, "G": 0.33}     # → overall ESG
SECTOR_MULTIPLIERS = {                                     # materiality tilt per sector
  "Financials — Banks":              {"E": 0.95, "S": 1.00, "G": 1.10},
  "Energy — Power & Renewables":     {"E": 1.12, "S": 1.00, "G": 0.98},
  "Communication Services — Telecom":{"E": 0.98, "S": 1.05, "G": 1.02},
  "Real Estate":                     {"E": 1.08, "S": 1.00, "G": 1.00},
  "Consumer Staples":                {"E": 1.02, "S": 1.08, "G": 0.98},
}  # default {1,1,1} for unknown sectors
VARIANCE_PCT = 0.04              # ±4% deterministic per-company spread
```

- `score_company(country_row, sector, *, seed) -> dict` returns
  `{e_score, s_score, g_score, overall, breakdown:{...}, data_provenance}`, all clamped 0–100.
- **Variance is seeded off the company name** (stable hash) → reproducible across runs and
  testable (no `random` flakiness). Same name → same scores.
- `data_provenance` (per company): e.g. *"Derived from country-level OECD/World Bank proxies
  for {country} (WGI governance + WB environment/social indicators), sector-adjusted
  ({sector}). Synthetic demo company — not direct company disclosure."*

### 4.4 `build_demo_universe.py` — generator

Joins the country table + roster + scoring → writes `data/demo_universe.json` in the existing
top-level shape (`note`, `selection`, `benchmark`, `benchmark_stats`, `as_of`, `countries`,
`constituents`). Per constituent: `esg_score` (overall, 0–100 ↑better), new `esg_breakdown`
and `data_provenance`, plus the existing illustrative `momentum` / `live_signals` / `market` /
`news` / `analyst_coverage` / `price_change_90d` (carried/derived as today, still labelled
illustrative). **Asserts no `real_world_basis` leaks into the output.** Committed as the
offline-safe fixture; re-runnable against a fresh live pull.

---

## 5. Score-direction switch (0–100 higher=better) — blast radius

| Location | Change |
|---|---|
| `data/demo_universe.json` | regenerated by the pipeline (0–100 ↑better, + breakdown + provenance) |
| `metrics.py` | line-14 doc comment; `average_esg` label stays; `classify` text drops "lower=better"/"risk" wording (its momentum logic is unchanged); add `esg_breakdown` passthrough helper |
| `contracts.py` (FROZEN) | **untouched** — `esg_breakdown`/`data_provenance` ride as non-contract fields, like `market`/`news` already do |
| `datasource.py` | `company_from_numeric` rides the new fields; `layer_a` note flips "Risk score: LOWER=better" → "Performance score: HIGHER=better"; history note likewise |
| `app.py` | captions/legends mentioning "risk"/"lower is better"; deep-dive renders the E/S/G breakdown + the `data_provenance` line; **remove the demo-mode disable on ➕ Monitor (line 1394)** |
| `selftest.py` | update the assertions pinned to risk-style values; add the new pipeline tests |
| `asean_universe.json` / evidence mode | **untouched** (already 0–100 ↑better) |

`hidden_winners` ranks by **momentum**, not `esg_score`, so the direction flip needs **no
ranking-logic change** — it is data + labels + narrative only.

---

## 6. App integration & Monitor fix

- **Startup refresh:** `app.py` calls `esg_data.get_country_table()` once per session (cached
  via `st.cache_data`), best-effort + silent fallback. The dashboard reads the committed
  `demo_universe.json`; the build script regenerates it from a fresh pull when desired.
- **Monitor in demo:** delete the `disabled=bool(ss.get("demo_mode"))` gate at `app.py:1394`.
  `_build_and_pin_constituent` already constructs a CompanyData from a constituent dict; verify
  it runs on a demo row, pins to ⭐ Monitored, and persists to `watchlist.json`.
- **Deep-dive / methodology panel:** show the E/S/G/overall breakdown and the per-company
  `data_provenance` line.

---

## 7. Methodology README section (for judges)

Plain-language block: **what's real** (OECD / World Bank country indicators, live-fetched with
cached fallback) · **what's synthetic** (company names + scores, sector-adjusted from country
baselines with seeded variance) · **why** (company ESG from MSCI/Sustainalytics is paywalled;
a transparent country-proxy methodology is the defensible stand-in) · the weight-constants
table so scoring is transparent and tunable.

---

## 8. Testing (TDD, offline — selftest stays network-free)

- `esg_scoring`: deterministic math, sector-multiplier effect, variance reproducibility
  (same name → same score), 0–100 clamping, breakdown→overall consistency.
- `esg_data`: WB JSON parse, normalization (incl. inverted CO₂), **missing-value handling**,
  CSV round-trip (`save_fallback`→`load_fallback`), upload parse — all with **mocked
  `core.http_get`** so no network is touched.
- `build_demo_universe`: output validates against the schema; `data_provenance` present;
  **no `real_world_basis` leak**.
- Extend `selftest.py`; keep the existing 60 checks green (updating only the risk-style ones).

---

## 9. Out of scope

- No change to the real evidence universe (`asean_universe.json`) or `parse_evidence`.
- No buy/sell/hold or ranking semantics (HARD RULE 4) — scores describe, never advise.
- Momentum / market / news stay illustrative; this spec only regrounds the **ESG score**.
- No `contracts.py` / `core.py` changes (frozen).

---

## 10. New / changed files

**New:** `esg_data.py`, `esg_scoring.py`, `build_demo_universe.py`, `data/demo_config.json`,
`data/fallback_oecd_wgi_asean.csv` (real WGI snapshot, generated now from a live WB pull).
**Changed:** `data/demo_universe.json` (regenerated), `metrics.py`, `datasource.py`, `app.py`,
`selftest.py`, `README.md`.
**Untouched (frozen):** `core.py`, `contracts.py`. **Untouched:** `data/asean_universe.json`.
