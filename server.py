"""
server.py — FastAPI backend for the React rebuild of the ASEAN ESG Momentum Radar.
====================================================================================
The Python "brain" stays exactly as it was: core / contracts / metrics / universe / rag /
datasource / stage1 / stage2 are imported unchanged (frozen modules untouched). This file is
the NEW presentation boundary: it exposes the brain over REST (+ one SSE stream for Stage 2)
so the React app in web/ can render it. Stage 3's job (rendering the answer) now lives in
React — this server only ever returns verified contract batons, never re-words them.

What it ports from the old Streamlit shell (app.py), as pure request/response logic:
  - the dashboard board state (filters -> metrics aggregation),
  - the chat intent parser (_chat_act) as structured actions,
  - the watchlist / snapshot registry (in-memory + data/watchlist.json persistence),
  - the deep-dive relay plumbing (default NarrowedQuestion, Stage-2 progress phases).

HARD RULES honoured: LLM only via core.call_llm, fetch only via core.http_get (both inside
the imported modules), retrieval best-effort, never fabricate, key from env only.

Run:
    venv/bin/python server.py                 # http://localhost:8000
    (dev UI: cd web && npm run dev  ->  http://localhost:5173, proxies /api to :8000)
"""

import datetime as _dt
import json
import os
import queue
import re
import threading
import time

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import anchor
import benchmarks
import brief as brief_mod
import clients as clients_mod
import company_metadata
import contracts
import core
import datasource
import engine
import engine_config
import harvest
import lseg
import metrics
import pipeline_counts
import news
import quotes
import rationale
import sensitivity
import stage1
import stage2
import universe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")
SAMPLE_FILE = os.path.join(DATA_DIR, "hero_company.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
WEB_DIST = os.path.join(BASE_DIR, "web", "dist")

# Uploads are read into memory, so they are capped. See /api/upload.
MAX_UPLOAD_BYTES = int(float(os.environ.get("ESG_MAX_UPLOAD_MB", "5")) * 1024 * 1024)

# Stage-2 progress phases (same narration as the Streamlit shell): as each Contract-C key
# appears in the streamed JSON, advance the status label against REAL progress.
_S2_PHASES = [
    ("what_rating_sees", "Reading the stale rating + its history…"),
    ("what_we_see", "Checking the live signal the rating can't see…"),
    ("check_before_monday", "Framing the check for your mandate…"),
    ("competes_summary", "Forming the disagreement…"),
    ("reasoning", "Writing out its chain of thought…"),
]

_ORIGIN_BADGE = {"live": "Live (fetched)", "upload": "Uploaded", "sample": "Sample",
                 "dataset": "Dataset"}
_ORIGIN_DISCLAIMER = {
    "live": "Built live from public sources — fields not found are shown as “unknown”, never "
            "invented. Not investment advice.",
    "upload": "Built from your uploaded data. Not investment advice.",
    "sample": "Illustrative sample — placeholder data, not real facts about any real company.",
    "dataset": "Built from pre-scored local dataset values (not a live fetch). Not investment "
               "advice.",
}

app = FastAPI(title="ASEAN ESG Momentum Radar API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
#  SNAPSHOT REGISTRY  (what Streamlit kept in st.session_state.snapshots)
# --------------------------------------------------------------------------- #
_ENTRIES = {}          # ticker -> {"company", "snap", "answer", "narrowed_q", "built_at"}
_ENTRIES_LOCK = threading.Lock()
_BUILT_AT = [time.time()]


def _load_watchlist():
    try:
        with open(WATCHLIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [t for t in (data.get("tickers") or []) if isinstance(t, str)]
    except (OSError, ValueError):
        return []


def _save_watchlist(tickers):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"tickers": list(dict.fromkeys(tickers))}, f, indent=2)
    except OSError:
        pass


_WATCHLIST = _load_watchlist()


def _pin(company):
    """Compute a snapshot for a built CompanyData and add it to the monitored board."""
    snap = datasource.snapshot_from_company(company)
    tk = company.get("ticker") or company.get("_constituent_ticker") or snap.get("ticker") or ""
    if not _known(tk):
        name = company.get("company") or ""
        slug = re.sub(r"[^A-Za-z0-9]+", "", name)[:12]
        tk = f"{slug or 'live'}-{time.time_ns()}"
    entry = {"company": company, "snap": snap, "answer": None, "narrowed_q": None,
             "built_at": time.time()}
    with _ENTRIES_LOCK:
        _ENTRIES[tk] = entry
        _BUILT_AT[0] = entry["built_at"]
        if tk not in _WATCHLIST:
            _WATCHLIST.append(tk)
        _save_watchlist(_WATCHLIST)
    return tk


def _unpin(ticker):
    with _ENTRIES_LOCK:
        if ticker in _WATCHLIST:
            _WATCHLIST.remove(ticker)
        _ENTRIES.pop(ticker, None)
        _save_watchlist(_WATCHLIST)


def _entry_json(ticker, demo=False):
    """Full deep-dive payload for one monitored company (Contract B + snap + cached batons).

    Also carries the two industry benchmarks and, for a real listing, a live quote. An UPLOADED
    company arrives here like any other, so an upload gets benchmarked against its ASEAN peers
    and its OECD industry with no extra plumbing — which is the whole point of hanging this off
    the entry rather than off the universe.
    """
    entry = _ENTRIES.get(ticker)
    if not entry:
        return None
    company = entry["company"]
    bd = metrics.esg_breakdown(company)
    if bd is None and isinstance(company, dict) and isinstance(company.get("_esg_breakdown"), dict):
        bd = company.get("_esg_breakdown")
    return {
        "ticker": ticker,
        "company": company,
        "snap": entry["snap"],
        "answer": entry["answer"],
        "narrowed_q": entry["narrowed_q"],
        "default_nq": _default_nq(company),
        "built_at": entry["built_at"],
        "financial": metrics.financial_snapshot(company),
        "breakdown": bd,
        "origin_badge": _ORIGIN_BADGE.get(company.get("_origin", "sample"), ""),
        "origin_disclaimer": _ORIGIN_DISCLAIMER.get(company.get("_origin", "sample"), ""),
        # score_higher_better is the snapshot's own reading of which way this company's static
        # rating runs; the benchmark needs it before it dares subtract anything from it.
        "benchmark": benchmarks.compare_company(
            company, demo=demo, higher_better=entry["snap"].get("score_higher_better")),
        # The name travels with the ticker: the PSE source is trusted only because the
        # company it names is read back and compared to ours before a price is shown.
        "quote": quotes.quote(ticker, demo=demo, company=company.get("company", "")),
    }


def _default_nq(company):
    """A sensible default NarrowedQuestion so a deep dive can 'compete' without interrogation
    (ported from app.py — grounded clause only for foundation-basket constituents)."""
    name = company.get("company", "this company")
    grounded = _known(company.get("_constituent_ticker"))
    if grounded:
        q = (f"Is {name}'s ESG profile as solid as its static rating and 2019–2023 improvement "
             "imply, once you weigh the live AI / news / behaviour signals the rating can't see?")
    else:
        q = (f"Is {name}'s ESG profile as solid as its static rating implies, once you weigh the "
             "live AI / news / behaviour signals the rating can't see?")
    return contracts.coerce_narrowed_question({
        "narrowed_question": q, "mandate": "risk",
        "sector": company.get("sector", "unknown"), "horizon": "near_term", "trail": [],
    })


def _known(v):
    return bool(v) and str(v).strip().lower() not in ("", "unknown")


def _short_sector(s):
    s = s or "All"
    return "All industries" if s == "All" else s.split("—")[-1].strip()


def _band_emoji(snap):
    tone = (snap.get("band_tone") or "").strip().lower()
    if tone:
        return {"good": "🟢", "caution": "🟡", "warn": "🟠", "bad": "🔴"}.get(tone, "⚪")
    b = (snap.get("band") or "").strip().lower()
    if not b:
        return "⚪"
    if "negli" in b or "low" in b or b in ("aaa", "aa"):
        return "🟢"
    if "med" in b or b in ("a", "bbb"):
        return "🟡"
    if "high" in b or b in ("bb", "b"):
        return "🟠"
    if "sever" in b or b == "ccc":
        return "🔴"
    return "⚪"


# --------------------------------------------------------------------------- #
#  BUILD PATHS  (ported _ensure_snapshot / _add_live_company)
# --------------------------------------------------------------------------- #
def _ensure_snapshot(constituent, demo):
    """Return the ticker of a constituent's snapshot, building it first if needed. Numeric
    constituents build locally (no network); evidence-only names go through the live builder."""
    tk = constituent.get("ticker") or constituent.get("id")
    if tk in _ENTRIES:
        return tk, None
    if metrics.has_numbers([constituent]):
        company = datasource.company_from_numeric(constituent,
                                                  origin="sample" if demo else "dataset")
        return _pin(company), None
    try:
        company, _meta = datasource.build_company_from_constituent(constituent, use_rag=True)
    except core.LLMConfigError as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001 — a live flop must not break the board.
        return None, f"Couldn't build that snapshot ({type(e).__name__}: {e})."
    return _pin(company), None


def _add_live_company(text):
    """Build a LIVE company by name (not in the universe) and pin it — ASEAN-only gate."""
    try:
        company, _meta = datasource.build_live_company(text, use_rag=True)
    except core.LLMConfigError as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001
        return None, f"Couldn't build “{text}” live ({type(e).__name__})."
    country = (company.get("_country") or "").strip()
    asean = [c.lower() for c in universe.ASEAN_COUNTRIES]
    if country and country.lower() != "unknown" and country.lower() not in asean:
        return None, (f"{company.get('company', text)} looks {country}-listed — this radar is "
                      "ASEAN-only (Singapore, Malaysia, Indonesia, Thailand, Philippines).")
    return _pin(company), None


# --------------------------------------------------------------------------- #
#  HEALTH
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm_configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "model": core.MODEL,
        "entries": len(_ENTRIES),
        "watchlist": len(_WATCHLIST),
    }


# --------------------------------------------------------------------------- #
#  BOARD  (the whole dashboard state for a filter set — pure metrics, no LLM)
# --------------------------------------------------------------------------- #
def _uni_mode(cons):
    if metrics.has_numbers(cons):
        return "numeric"
    if any(c.get("esg_basis") for c in cons):
        return "evidence"
    return "empty"


# --------------------------------------------------------------------------- #
#  ENGINE  (Build Spec v2 — score records, CGSI quadrants, tiers, N/M/K, anchors)
#  The engine is a pure function of the data files, so one run per (universe,
#  config) is memoised in-process; run_engine's own disk cache backs that up.
# --------------------------------------------------------------------------- #
_ENGINE_MEMO = {}


def precompute_engine():
    """Warm every (universe, horizon) pair so the first toggle flip is a memo hit.

    A5 says the matrix must re-segment in under a second and to precompute if it does not. The
    tiers are already instant because they are flags on a finished record; the horizon is a
    re-score, so this is where that promise is actually kept. Best-effort by design — a failure
    here must never stop the server booting, it just means the first flip pays for itself."""
    warmed = []
    for demo in (True, False):
        for name in sorted(engine_config.horizons()) or [engine_config.DEFAULT_HORIZON]:
            try:
                run, _meta, _cfg = _engine_run(demo, name)
                warmed.append(f"{'demo' if demo else 'real'}/{name}:{run['run_id']}")
            except Exception as exc:                                        # noqa: BLE001
                warmed.append(f"{'demo' if demo else 'real'}/{name}:FAILED {type(exc).__name__}")
    return warmed


def _engine_run(demo, horizon=engine_config.DEFAULT_HORIZON):
    """The scored run for a universe at a named decay horizon, metadata joined, tiers stamped.

    The horizon is NOT a filter. The risk tiers are — they read flags already stamped on a
    finished record, so the front-end can re-segment without asking us anything. Changing the
    decay half-life changes the weight of every signal, so momentum, confidence, percentiles,
    quadrants and N/M/K are all different numbers: it is a re-score, and it gets its own
    `run_id`. Hence the memo below and the startup precompute — the spec's "<1 second" is met
    by having both answers ready, not by making the flip cheap."""
    cfg = engine_config.for_horizon(horizon)
    path = universe.active_file(demo)
    # The metadata file follows the UNIVERSE, not the preference order: the fictional demo set
    # is keyed on invented tickers and joins nothing against the verified 52.
    key = (path, cfg["config_hash"], os.path.getmtime(path) if os.path.exists(path) else 0,
           company_metadata.load_report(demo=demo).get("rows", 0), demo,
           0 if demo else sum(len(v) for v in harvest.load_overlay().values()))
    hit = _ENGINE_MEMO.get(key)
    if hit:
        return hit
    meta = company_metadata.load(demo=demo)
    cons = universe.constituents(path)
    if not demo:
        # Harvested evidence merges in for the REAL basket only — searching live news about a
        # fictional company would be nonsense, and the demo set already carries rich momentum.
        # This changes the run's INPUTS, so it changes the run_id, which is correct: a run over
        # more evidence is a different run. The engine itself stays pure, and the harvest files
        # are committed, so a fresh clone reproduces the same id.
        cons = harvest.apply_overlay(cons)
    run = engine.run_engine(cons, metadata=meta, config=cfg)
    if len(_ENGINE_MEMO) > 8:      # keys carry mtime+config; 2 universes x 2 horizons live here
        _ENGINE_MEMO.clear()
    _ENGINE_MEMO[key] = (run, meta, cfg)
    return _ENGINE_MEMO[key]


def _record_summary(record):
    """The compact per-company record the dashboard paints (signals stay server-side)."""
    return {
        "company_id": record["company_id"],
        "label": record["label"],
        "label_display": record["label_display"],
        "composite_momentum": record["composite_momentum"],
        "composite_confidence": record["composite_confidence"],
        "direction_consensus": record["direction_consensus"],
        "evidence_weight": record["evidence_weight"],
        "shrinkage": record["shrinkage"],
        "disagreement": record["disagreement"],
        "lseg_percentile": record["lseg_percentile"],
        "momentum_percentile": record["momentum_percentile"],
        "signal_count": record["signal_count"],
        "baseline_origin": record["baseline_origin"],
        "baseline_basis": record["baseline_basis"],
        "components": {k: v["momentum"] for k, v in record["components"].items()},
        "tiers": record.get("tiers", {}),
    }


def _badges(ticker, meta, cfg, record=None, nmk=None, buckets=None):
    """The per-company badges. `delisted` is CGSI's own note carried onto the record, and it is
    surfaced deliberately: two of their 52 (MAHB, INTUCH) went private in 2025 while sitting in
    a basket meant to be current. A static list going stale IS the product's argument, so the
    row stays and wears a badge rather than disappearing (Prototype_Build_Notes.md §3)."""
    row = meta.get(ticker, {})
    out = {"green_bond": company_metadata.green_bond_badge(row, cfg),
           "profitability": company_metadata.profitability_badge(row)}
    # Which origination bucket this company is in. The counts strip has always shown the totals;
    # this puts the label on the company, which is where a reader asking "is THIS one a lead?"
    # actually looks. Display only — a join over the same run, no new scoring.
    if buckets is not None:
        out["pipeline"] = pipeline_counts.bucket_badge(buckets.get(ticker, ""), nmk)
    if record and record.get("delisted"):
        out["delisted"] = {
            "label": "delisted",
            "value": "delisted — basket membership stale",
            "note": (record.get("company", ticker) + " is no longer listed. Kept in the basket "
                     "and excluded from investable output."),
            "tone": "warn",
        }
    # The industry's transition bar, joined on CGSI's own industry label. Context for the
    # evidence trail, never differenced against the company (see benchmarks.sector_benchmark).
    bar = benchmarks.sector_benchmark((record or {}).get("industry", ""))
    if bar.get("available"):
        out["sector_benchmark"] = {
            "label": "industry bar",
            "value": "%s g CO2e/EUR GVA" % bar["intensity"],
            "industry": bar["industry"],
            "nace": bar["nace_code"],
            "rank": bar["rank_cleanest"], "of": bar["of"],
            "above_median": bar["above_median"],
            "attribution": bar["attribution"],
            "caveat": bar["caveat"],
            "note": ("Sector bar only — we hold no per-company emissions intensity for this "
                     "basket, so this is never subtracted from the company."),
        }
    return out


def _anchor_summary(run):
    """Anchor status for a run — never computes a chain call on the board path."""
    record = anchor.load_record(run["run_id"])
    if not record:
        return {"status": "not_built", "run_id": run["run_id"], "root": "", "leaf_count": 0,
                "tx_hash": "", "explorer_url": "", "chain": anchor.CHAIN_NAME,
                "note": "Run not anchored yet — `python anchor.py --run` builds and anchors it."}
    cfg = anchor.chain_config()
    explorer = (f"{cfg['explorer']}/tx/{record['tx_hash']}" if record.get("tx_hash")
                else f"{cfg['explorer']}/address/{record['contract']}" if record.get("contract")
                else "")
    return {"status": record.get("status", "anchor_pending"), "run_id": record["run_id"],
            "root": record["root"], "leaf_count": record["leaf_count"],
            "tx_hash": record.get("tx_hash", ""), "block_number": record.get("block_number"),
            "signer": record.get("signer", ""), "contract": record.get("contract", ""),
            "chain": record.get("chain", anchor.CHAIN_NAME), "explorer_url": explorer,
            "note": record.get("anchor_note", "")}


def _harvest_summary(demo):
    """How much live-gathered evidence is in this run, and how much of the basket it touched."""
    if demo:
        return {"companies": 0, "events": 0, "note": ""}
    overlay = harvest.load_overlay()
    events = sum(len(v) for v in overlay.values())
    return {
        "companies": len(overlay),
        "events": events,
        "note": ("%d dated, sourced facts gathered live for %d companies and merged into this "
                 "run. The model only read them — every direction, weight and label below is "
                 "still assigned by rule." % (events, len(overlay))) if events else "",
    }


def _engine_block(demo, filtered, horizon=engine_config.DEFAULT_HORIZON):
    """Everything the Build-Spec front-end needs for one filtered view."""
    run, meta, cfg = _engine_run(demo, horizon)
    tickers = [c["ticker"] for c in filtered]
    by_id = {r["company_id"]: r for r in run["records"]}
    subset = {"records": [by_id[t] for t in tickers if t in by_id],
              "company_count": len(tickers)}
    labels = {k: engine_config.display(cfg, k) for k in engine_config.label_order(cfg)}
    # Computed once and used twice: the counts strip beside the matrix, and the per-company
    # bucket badge. Two calls could drift apart on the same screen.
    nmk = pipeline_counts.counts(subset, meta, cfg)
    buckets = pipeline_counts.bucket_of(nmk)
    return {
        "run_id": run["run_id"],
        "as_of": run["as_of"],
        "engine_version": run["engine_version"],
        "config_version": run["config_version"],
        "config_hash": run["config_hash"],
        "theta": cfg["theta"],
        "labels": labels,
        "label_tooltips": {k: (cfg["labels"].get(k) or {}).get("tooltip", "")
                           for k in engine_config.label_order(cfg)},
        "label_rules": {k: (cfg["labels"].get(k) or {}).get("rule", "")
                        for k in engine_config.label_order(cfg)},
        "label_counts": engine.label_counts(subset),
        "tiers": {k: cfg["risk_tiers"][k]["display"]
                  for k in ("conservative", "balanced", "aggressive")},
        "tier_rules": {k: cfg["risk_tiers"][k].get("rule", "") for k in
                       ("conservative", "balanced", "aggressive")},
        "default_tier": cfg["risk_tiers"]["default"],
        # The horizon names and their half-lives come from config, never from a literal here —
        # the UI renders whatever `decay.horizons` holds, so adding a third is a file edit.
        "horizon": engine_config.horizon_of(cfg) or engine_config.DEFAULT_HORIZON,
        "horizons": engine_config.horizons(cfg),
        "default_horizon": engine_config.DEFAULT_HORIZON,
        "half_life_days": cfg["decay"]["half_life_days"],
        "nmk": nmk,
        "metadata": company_metadata.load_report(demo=demo),
        # Say how much of this run's evidence was harvested rather than supplied. A board that
        # silently mixes the two invites exactly the question we would have no answer to.
        "harvest": _harvest_summary(demo),
        "anchor": _anchor_summary(run),
        "records": {t: _record_summary(by_id[t]) for t in tickers if t in by_id},
        "badges": {t: _badges(t, meta, cfg, by_id.get(t), nmk, buckets) for t in tickers},
    }


def _focused_engine_record(demo, horizon, ticker):
    """The FULL engine record (signals included) for one ticker, or None. `_record_summary`
    deliberately strips signals for the board payload, so the rail asks the run directly."""
    if not ticker:
        return None
    try:
        run, _meta, _cfg = _engine_run(demo, horizon)
    except Exception:                                   # noqa: BLE001 - never break the board
        return None
    for rec in run.get("records") or []:
        if rec.get("company_id") == ticker:
            return rec
    return None


def _live_price_90d(focused):
    """The real 90-day price move for a REAL listing, via `quotes.change_90d`. Returns None on
    any failure, an unmapped exchange (PSE and HOSE are documented gaps) or a fictional name —
    the strip then says it is unavailable rather than drawing a flat line, which a reader would
    take to mean the price did not move. A quote is context and never an input to a score."""
    ticker = (focused or {}).get("ticker")
    if not ticker:
        return None
    try:
        return quotes.change_90d(ticker)
    except Exception:                                   # noqa: BLE001 - best-effort by design
        return None


def _decay_note(record, half_life_days):
    """Why a company with evidence can still read zero momentum.

    The short horizon halves the weight of evidence every 45 days, so a name whose newest signal
    is a year old scores 0.000 and lands in `consensus` — correct, and completely opaque on
    screen, because the card just empties. Saying it turns a blank into the finding it actually
    is: the evidence exists, it is simply too old to answer THIS question."""
    if not record:
        return ""
    count = record.get("signal_count") or 0
    if not count or metrics.num(record.get("composite_momentum")):
        return ""
    dates = [str(s.get("published_at") or "")[:10] for s in (record.get("signals") or [])]
    dates = sorted([d for d in dates if d], reverse=True)
    newest = dates[0] if dates else ""
    return (f"{count} scored signal{'s' if count != 1 else ''} on file"
            + (f", newest {newest}" if newest else "")
            + f" — all decayed to zero weight at a {half_life_days}-day half-life. "
              "The evidence exists; it is too old to move this horizon. Switch to the longer "
              "horizon to see what it says.")


#: Seconds the cutoff-replay chart may spend before giving up (see below).
SERIES_BUDGET_SECONDS = 6.0

_SERIES_CACHE = {}


def _real_momentum_series(demo, horizon, run, points=8):
    """A REAL per-pillar momentum series: the engine re-run at successive historical cutoffs.

    The existing `metrics.momentum_series` interpolates — it eases from an invented baseline to
    each pillar's current value so the lines fan out like the mockup, and it says so. That is
    honest for the FICTIONAL demo set, which holds no dated evidence to build a series from.

    The real basket does hold dated evidence, and `run_engine` already takes a `cutoff`, so every
    point here is a genuine engine run at its own date — what the Radar WOULD have said then, on
    only the evidence that existed then. Same construction as the five backtest cases, and the
    reason it can be drawn at all is Gate-1 purity: no clock, no RNG, so a replay of 2024-06-30
    is the same computation today as it was then.

    Returns `{pillar: [floats]}` plus the cutoff labels, or `({}, [])` when there is nothing
    dated to plot — never an interpolated stand-in for a real universe.
    """
    as_of = str(run.get("as_of") or "")[:10]
    if demo or not as_of:
        return {}, []
    key = (demo, horizon, run.get("run_id"), points)
    if key in _SERIES_CACHE:
        return _SERIES_CACHE[key]

    year, month = int(as_of[:4]), int(as_of[5:7])
    cutoffs = []
    for step in range(points - 1, -1, -1):
        m = month - step * 3
        y = year
        while m <= 0:
            m += 12
            y -= 1
        # Quarter ends, so a cutoff never lands mid-month and shift the window unevenly.
        cutoffs.append(f"{y:04d}-{m:02d}-28")

    cfg = engine_config.for_horizon(horizon)
    metadata = company_metadata.load(demo=demo)
    cons = universe.constituents(universe.active_file(demo))
    if not demo:
        cons = harvest.apply_overlay(cons)
    series = {p: [] for p in metrics.PILLARS}
    # A HARD BUDGET, because this is eight full engine runs. They are cheap once the disk cache
    # is warm, but every cutoff is its own `run_id` and a harvest running in the background
    # changes the inputs continuously — so during a sweep every request is a cold miss and the
    # board would block on a CHART. A chart is never worth a hanging page: past the budget this
    # gives up and the panel shows its honest empty state until the inputs settle.
    deadline = time.monotonic() + SERIES_BUDGET_SECONDS
    for cutoff in cutoffs:
        if time.monotonic() > deadline:
            return {}, []
        try:
            past = engine.run_engine(cons, metadata=metadata, config=cfg, cutoff=cutoff)
        except Exception:                              # noqa: BLE001 - a chart must not 500
            return {}, []
        rows = metrics.pillar_momentum_from_records(past["records"])
        for row in rows:
            # `None` where NO company had evidence for that pillar at that cutoff. Substituting
            # 0.0 here would be the bug this whole codebase keeps catching: "no evidence" and
            # "evidence says flat" both land on zero, and only one of them is a measurement.
            series[row["key"]].append(row["value"] if row["n"] else None)

    # A line can only be drawn where every point is a real reading. Social and digital evidence
    # exists for 3 of 52 companies, so those pillars have genuine gaps — and a chart that bridges
    # a gap with a zero is asserting a measurement nobody made. Rather than draw a broken line or
    # a false one, a pillar that is missing ANY point is dropped and the count is reported
    # alongside, which is the same treatment the matrix gives its hollow dots.
    dropped = {k: sum(1 for x in v if x is None) for k, v in series.items()
               if any(x is None for x in v)}
    series = {k: v for k, v in series.items()
              if v and all(x is not None for x in v) and any(abs(x) > 1e-9 for x in v)}
    out = (series, cutoffs if series else [])
    if dropped:
        out[0].setdefault("_dropped", None)
        del out[0]["_dropped"]        # keep the shape clean; the note travels in the log
        print(f"[series] pillars with evidence gaps, not plotted: {dropped}")
    _SERIES_CACHE[key] = out
    return out


def _why_wrong(focused):
    if not focused:
        return "Add or focus a company to see where its live signal diverges from the stale rating."
    s = focused.get("live_signals") or {}
    d = metrics.num((focused.get("momentum") or {}).get("digital_ai"))
    name = focused.get("company", "This company")
    score, as_of = focused.get("esg_score"), (focused.get("esg_as_of") or "")
    if d is None and focused.get("esg_basis"):
        p = metrics.evidence_profile(focused)
        tags = ", ".join(f'{cr["label"]} {cr["value"]}' for cr in p["credentials"][:2]) or \
               "documented ESG progress"
        return (f"{name} is a documented ESG improver ({tags}; leadership {p['score']}/100). A "
                "stale rating may already price that leadership — the radar's edge is the LIVE "
                "alt-data (AI hiring, patents, news/behaviour) that isn't wired yet. That's where "
                "a 2023 score gets caught out.")
    cls = metrics.classify(focused)
    if cls["label"] == "HIDDEN WINNER":
        return (f"{name} is hiring hard for AI governance ({s.get('ai_hiring_surge') or 'fast'}) "
                f"while the static {as_of} score ({score if score is not None else '—'}) sits "
                f"still — the rating can't see the live Digital/AI {metrics.fmt_pct(d)} trajectory.")
    if cls["label"].startswith("WATCH"):
        return (f"{name} carries {int(metrics.num(s.get('controversy_flags')) or 0)} controversy "
                f"flag(s) with softening signals (Digital/AI {metrics.fmt_pct(d)}); the stale "
                "score lags the behaviour.")
    if d is None:
        return (f"No live momentum for {name} yet — add numeric data (or run a deep dive) so the "
                "radar can compete with its rating.")
    return (f"{name}'s live signal (Digital/AI {metrics.fmt_pct(d)}) is roughly in line with its "
            "rating — watch for divergence.")


#: A company has to carry at least this much scored evidence to be the one the board OPENS on.
#: Not a display filter — every company is still reachable, ranked and plotted. It only stops the
#: unconfigured first screen landing on a name we have almost nothing to say about.
_DEFAULT_FOCUS_MIN_SIGNALS = 5


def _default_focus_from_records(filtered, records):
    """The company the board opens on when the user has not chosen one.

    THE OLD CHAIN OPENED ON THE WRONG COMPANY, and for the same reason three widgets did before
    it: `metrics.hidden_winners` ranks on a Digital/AI field only the FICTIONAL demo set carries,
    so on the real basket it returns nothing and the pick fell through to `evidence_leaders` —
    which counts the rating agencies named in a company's `esg_basis` PROSE, not evidence this
    engine ever scored. That opened the board on Bank Negara Indonesia: eight agency mentions in
    its blurb, no social evidence, no digital/AI evidence, no headlines, and a Consensus label.
    The first thing anyone saw was the one company we had nothing to say about.

    So the pick reads the engine, like everything else now does. Ranked by
    `|disagreement| x confidence`: a big disagreement we are confident in is precisely what this
    product exists to show, and multiplying is what stops a wild claim on one thin signal
    outranking a solid one. Deterministic, ties broken by ticker, so the board opens on the same
    company every time.
    """
    by_id = {r.get("company_id"): r for r in (records or [])}
    best, best_key = None, None
    for c in filtered:
        r = by_id.get(c.get("ticker"))
        if not r or r.get("delisted"):
            continue
        signals = r.get("signal_count") or 0
        if signals < _DEFAULT_FOCUS_MIN_SIGNALS:
            continue
        conf = r.get("composite_confidence") or 0.0
        strength = abs(r.get("disagreement") or 0.0) * conf
        key = (strength, signals, c.get("ticker") or "")
        if best_key is None or key > best_key:
            best, best_key = c, key
    return best


def _cc_focused(focus_ticker, filtered, path, records=None):
    if focus_ticker:
        c = universe.get(focus_ticker, path)
        if c:
            return c
        e = _ENTRIES.get(focus_ticker)
        if e:
            return e["company"]
    picked = _default_focus_from_records(filtered, records)
    if picked:
        return picked
    hw, _, _ = metrics.hidden_winners(filtered, top_n=1)
    if hw:
        return universe.get(hw[0]["ticker"], path) or (filtered[0] if filtered else None)
    lead = metrics.evidence_leaders(filtered, top_n=1)
    if lead:
        return universe.get(lead[0]["ticker"], path) or (filtered[0] if filtered else None)
    return filtered[0] if filtered else None


def _board_average(filtered, mode, sector):
    """Build the filtered-set average card without coupling it to the endpoint response."""
    if mode == "evidence":
        avg, count = metrics.evidence_average(filtered)
        return {"kind": "evidence", "value": avg, "n": count,
                "title": f"Avg ESG-leadership · {_short_sector(sector)}",
                "sub": f"evidence index 0–100 · {count} names" if avg is not None
                       else "awaiting data"}
    avg, count = metrics.average_esg(filtered)
    return {"kind": "numeric", "value": avg, "n": count,
            "title": f"Avg ESG · {_short_sector(sector)}",
            "sub": f"mean static score · {count} names" if avg is not None else "awaiting data"}


def _board_watchlist(path):
    """Serialize monitored entries and preserve unbuilt universe tickers."""
    rows = []
    for ticker in _WATCHLIST:
        entry = _ENTRIES.get(ticker)
        constituent = universe.get(ticker, path)
        if entry:
            rows.append({"ticker": ticker, "name": entry["snap"]["company"], "built": True,
                         "band": entry["snap"].get("band") or "",
                         "band_emoji": _band_emoji(entry["snap"]),
                         "has_answer": entry.get("answer") is not None,
                         "in_universe": constituent is not None})
        else:
            rows.append({"ticker": ticker, "name": (constituent or {}).get("company") or ticker,
                         "built": False, "band": "", "band_emoji": "", "has_answer": False,
                         "in_universe": constituent is not None})
    return rows


@app.get("/api/board")
def board(demo: bool = Query(True), country: str = "All", sector: str = "All",
          focus: str = "", simplified: bool = Query(True),
          horizon: str = Query(engine_config.DEFAULT_HORIZON)):
    path = universe.active_file(demo)
    uni = universe.load_universe(path)
    cons = uni["constituents"]
    sectors = ["All"] + universe.sectors(path)
    countries = ["All"] + universe.countries(path)
    if sector not in sectors:
        sector = "All"
    if country not in countries:
        country = "All"
    filtered = universe.filter_constituents(country=country, sector=sector, path=path)
    mode = _uni_mode(cons)
    # The engine run is memoised, so consulting it here costs nothing — the board
    # builds it a few lines below anyway.
    focused = _cc_focused(focus or None, filtered, path,
                          _engine_run(demo, horizon)[0].get("records"))
    nt = {focus} if focus else set()

    avg_payload = _board_average(filtered, mode, sector)

    hw_rows, peer_avg, peer_n = metrics.hidden_winners(filtered, top_n=5, new_tickers=nt)
    # Same false negative again: `hidden_winners` ranks on a Digital/AI field only the demo set
    # carries, so the real basket showed "nothing to rank" beside a matrix already holding four
    # names in that quadrant. Fall back to the engine's own signed disagreement.
    hw_basis = "digital_ai"
    if not hw_rows:
        hw_rows, peer_avg, peer_n = metrics.hidden_winners_from_records(
            filtered, _engine_block(demo, filtered, horizon)["records"],
            top_n=5, new_tickers=nt)
        hw_basis = "disagreement" if hw_rows else hw_basis
    leaders = metrics.evidence_leaders(filtered, top_n=5, new_tickers=nt)

    # --- focused company panels ------------------------------------------------ #
    focused_payload = None
    if focused:
        ft = focused.get("ticker")
        entry = _ENTRIES.get(ft)
        answer = entry.get("answer") if entry else None
        ep = metrics.evidence_profile(focused) if focused.get("esg_basis") else {}
        if mode == "evidence":
            cls = metrics.classify_evidence(focused)
            signals = [{"label": cr["label"], "value": cr["value"], "tone": cr["tone"]}
                       for cr in ep.get("credentials", [])]
            signals_kind = "credentials"
        else:
            cls = metrics.classify(focused)
            signals = metrics.live_signals(focused)
            signals_kind = "signals"
        # The engine holds dated, sourced, SCORED signals for the real basket; `live_signals`
        # only ever finds the demo set's own block. Falling back means a real company with three
        # scored signals stops reporting "0 signals" beside the momentum those signals produced.
        erec = _focused_engine_record(demo, horizon, focused.get("ticker"))
        if not signals and erec:
            signals = metrics.signals_from_record(erec)
            if signals:
                signals_kind = "scored signals"
        # The SAME false negative, one widget over. `metrics.classify` reads the demo-only
        # `momentum` block, so once the real basket landed every real company read "AWAITING
        # DATA" in the classification strip and in the RadarHub chip — printed directly above a
        # rationale panel naming the engine's verdict for that same company. Two adjacent widgets
        # disagreeing about whether we have data is worse than either answer on its own. The
        # engine record is the authority whenever there is one; when there is not, the honest
        # "awaiting data" stands.
        if isinstance(cls, dict) and cls.get("label") == "AWAITING DATA" and erec:
            cls = metrics.classify_from_record(erec) or cls
        # The four pillar readings for THIS company. `board["pillars"]` is the average across
        # everything in view, which is the right number when nothing is focused and the wrong one
        # the moment a company's name is printed in the middle of it: the hub drew the 52-company
        # average and labelled it with the focused company, so the readings never moved when you
        # changed company. Same precedence as the board cards — the constituent's own numeric
        # block first (the fictional demo set), the engine record otherwise. None when neither
        # can answer, and the hub then falls back to the set average and says so.
        own_pillars = metrics.pillar_momentum([focused])
        if not any(row["value"] is not None for row in own_pillars):
            own_pillars = metrics.pillar_momentum_for_record(erec) if erec else []
        focus_pillars = own_pillars if any(
            row["value"] is not None for row in (own_pillars or [])) else None
        # A real last price for a real listing (best-effort, never a signal — see quotes.py).
        # The demo universe is FICTIONAL and deliberately gets no quote.
        live_px = None if demo else _live_price_90d(focused)
        # The last traded price, separately from the 90-day series. The Philippine board gives a
        # real PSE price but no history, so without this a reader would see "no price" for a
        # company we can in fact quote.
        last_px = None if demo else quotes.quote(
            focused.get("ticker") or "", company=focused.get("company", ""))
        pct = metrics.price_change_pct(focused) if demo else (live_px or {}).get("pct")
        focused_payload = {
            "constituent": focused,
            "from_snapshot": bool(entry),
            "classification": cls,
            "pillars": focus_pillars,
            "credentials": ep.get("credentials", []),
            "leadership": {"score": ep.get("score"), "band": ep.get("band"),
                           "has": bool(ep)} if ep else None,
            "signals": signals,
            "signals_kind": signals_kind,
            # Why a company WITH evidence can still read zero momentum on this horizon. Empty
            # string when it does not apply, so the UI shows nothing rather than a caveat that
            # does not fit the company in front of the reader.
            "decay_note": _decay_note(erec, _engine_run(demo, horizon)[2]["decay"]["half_life_days"]),
            # WHY this verdict — pros and cons on BOTH axes, derived by rule from the same run.
            # A label without its reasoning is a conclusion the reader cannot argue with, and the
            # cons are not optional: a case that only lists reasons to agree is marketing.
            "case": (rationale.build(erec, company_metadata.load(demo=demo).get(focused.get("ticker")))
                     if erec else None),
            "why_wrong": _why_wrong(focused),
            "plain_summary": metrics.plain_summary(focused, answer),
            # Real gathered headlines for a real company; the demo set keeps its own seeded,
            # clearly-labelled ones. Display only — nothing here reaches the engine.
            "news": metrics.news_card(
                focused, None if demo else news.load(focused.get("ticker") or "")),
            "analyst": metrics.analyst_coverage(focused),
            "check_action": metrics.focused_answer_action(
                {ft: entry} if entry else {}, ft),
            # Demo draws a synthetic curve from its own illustrative percent; a real listing
            # draws its ACTUAL closes, rebased to 100. `source` says which, so the strip can
            # stop calling a live Yahoo series "illustrative".
            "price": {"pct": pct,
                      "series": ((live_px or {}).get("series")
                                 if live_px else
                                 (metrics.price_series(pct) if pct is not None else [])),
                      "source": (live_px or {}).get("source") if live_px else None,
                      "points": (live_px or {}).get("points") if live_px else None,
                      # The date the series was CAPTURED. The basket runs off a dated snapshot so
                      # the demo needs no network; a stored price printed without its date would
                      # read as a live tick, which is a rule-3 breach for the sake of looking
                      # fresher than it is.
                      "captured": (live_px or {}).get("captured") if live_px else None,
                      "last": ({"price": last_px.get("price"),
                                "currency": last_px.get("currency"),
                                "change_pct": last_px.get("change_pct"),
                                "exchange": last_px.get("exchange"),
                                "source": last_px.get("source"),
                                "captured": last_px.get("captured")}
                               if last_px and last_px.get("available") else None)},
            "foundation": ({"basis": focused.get("esg_basis"),
                            "source_url": focused.get("source_url"),
                            "confidence": focused.get("confidence")}
                           if focused.get("esg_basis") else None),
            # Peer average and industry footprint for the focused name. Local and cheap — the
            # OECD half is a parsed CSV, the ASEAN half is an average over the filtered set.
            "benchmark": benchmarks.compare_company(focused, path=path),
        }

    # --- watchlist ---------------------------------------------------------------- #
    wl = _board_watchlist(path)

    followups = metrics.suggested_followups(
        focused_name=(focused or {}).get("company"),
        focused_sector=_short_sector((focused or {}).get("sector")),
        has_focus=bool(focus) or bool(focused),
        has_answer=bool(focused and (_ENTRIES.get(focused.get("ticker")) or {}).get("answer")),
        simplified=simplified,
        sample_sector=_short_sector(universe.sectors(path)[0]) if universe.sectors(path) else None,
        sample_country=(universe.countries(path) or [None])[0])

    # Built once and used TWICE below — the pillar cards fall back to the engine's own
    # per-component momentum when the constituents carry no numeric block, so the board must not
    # score the same filtered view twice (it is cached, but the two copies could still drift).
    engine_block = _engine_block(demo, filtered, horizon)

    # The pillar cards: a constituent's own `momentum` block when it has one (the fictional demo
    # set), otherwise the ENGINE's per-component direction consensus. Before this the cards read
    # only the first source, so the real basket showed four "awaiting data" tiles next to 44
    # companies' worth of environment evidence the engine had already scored. Two different
    # scales, so each row carries `basis` and the UI labels the unit rather than guessing.
    pillars = metrics.pillar_momentum(filtered)
    if not any(row["value"] is not None for row in pillars):
        pillars = metrics.pillar_momentum_from_records(engine_block["records"])

    # The momentum chart. For the real basket this is not a drawing — it is the engine re-run at
    # each quarter end, which is only possible because the engine is pure.
    real_series, series_labels = _real_momentum_series(demo, horizon, _engine_run(demo, horizon)[0])

    return {
        "universe": {"note": uni.get("note"), "selection": uni.get("selection"),
                     "benchmark": uni.get("benchmark"),
                     "benchmark_stats": uni.get("benchmark_stats"),
                     "as_of": uni.get("as_of"),
                     "banner": metrics.universe_banner(uni),
                     "quarter": metrics._as_quarter(uni.get("as_of", ""))},
        "mode": mode,
        "demo": demo,
        "sectors": sectors,
        "countries": countries,
        "filter": {"country": country, "sector": sector},
        "counts": {"total": len(cons), "showing": len(filtered)},
        "industries": len({c["sector"] for c in cons if c["sector"] != "unknown"}),
        "avg": avg_payload,
        "pillars": pillars,
        # Real basket: genuine engine replays at quarterly cutoffs. Demo: the illustrative
        # interpolation, which is all a fictional set can honestly support.
        "momentum_series": real_series or metrics.momentum_series(filtered),
        "momentum_series_basis": (
            "engine replayed at each quarter cutoff — every point is a real run"
            if real_series else "illustrative interpolation"),
        "momentum_series_labels": series_labels,
        "hidden_winners": {"rows": hw_rows, "peer_avg": peer_avg, "n": peer_n,
                           "basis": hw_basis},
        "evidence": {"coverage": metrics.credential_coverage(filtered), "leaders": leaders},
        "constituents": filtered,
        "engine": engine_block,
        "focused": focused_payload,
        "watchlist": wl,
        "followups": followups,
        "built_at": _BUILT_AT[0],
        "fresh": metrics.fmt_elapsed(time.time(), _BUILT_AT[0]),
    }


# --------------------------------------------------------------------------- #
#  CHAT  (the intent parser — ported from app.py _chat_act, returns actions)
# --------------------------------------------------------------------------- #
_RELAY_TRIGGERS = ("analyse", "analyze", "deep dive", "deep-dive", "deepdive", "run esg",
                   "esg analysis", "esg on", "3 stage", "three stage", "relay", "compete",
                   "interrogate", "ask about", "challenge", "assess", "evaluate", "question")
_INTERROGATE_TRIGGERS = ("interrogate", "ask about", "challenge", "question")
_RELAY_STRIP = ("run an esg analysis on", "run esg analysis on", "esg analysis on", "run esg on",
                "run the 3 stages on", "3 stage relay on", "deep dive on", "deep-dive on",
                "compete against", "compete with", "compete on", "ask about", "analyse", "analyze",
                "deep dive", "deep-dive", "deepdive", "run esg", "esg analysis", "esg on",
                "interrogate", "challenge", "evaluate", "assess", "relay", "compete", "question",
                "please", "run ")


def _match_sector(low, path):
    qtoks = set(re.findall(r"[a-z]+", low))
    syn = {"banks": ("bank",), "telecom": ("telco", "telcos", "mobile"),
           "estate": ("property", "realty"), "energy": ("power", "renewables", "renewable", "solar"),
           "consumer": ("staples", "food", "retail"), "technology": ("tech", "chip", "semiconductor")}
    for s in universe.sectors(path):
        words = [w for w in re.findall(r"[a-z]+", s.lower())
                 if len(w) > 3 and w not in ("services", "communication")]
        for w in words:
            if w in qtoks or any(syk in qtoks for syk in syn.get(w, ())):
                return s
    return None


def _relay_request(low):
    if not any(v in low for v in _RELAY_TRIGGERS):
        return None
    return "interrogate" if any(v in low for v in _INTERROGATE_TRIGGERS) else "compete"


def _strip_relay_verbs(text):
    out = text
    for v in _RELAY_STRIP:
        out = re.sub(re.escape(v), " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip(" ?.")


class ChatIn(BaseModel):
    text: str
    demo: bool = True
    simplified: bool = True
    focus_ticker: str = ""


@app.post("/api/chat")
def chat(body: ChatIn):
    path = universe.active_file(body.demo)
    t = (body.text or "").strip()
    if not t:
        return {"reply": metrics.chat_fallback_msg(body.simplified),
                "action": {"kind": "none"}}
    low = t.lower()
    simple = body.simplified

    # 1) run the 3-stage relay (two modes)
    rmode = _relay_request(low)
    if rmode:
        stripped = _strip_relay_verbs(t)
        if stripped.lower() in ("this", "it", "focused", "the company", "") and body.focus_ticker:
            ft = body.focus_ticker
            built = ft in _ENTRIES
            uc = universe.get(ft, path)
            if built or uc:
                return {"reply": metrics.chat_relay_msg(None, rmode, simple, focused=True),
                        "action": {"kind": "relay", "ticker": ft, "mode": rmode,
                                   "needs_build": not built,
                                   "company": (uc or {}).get("company") or ft}}
        c = universe.resolve(stripped or t, path)
        if c:
            built = c["ticker"] in _ENTRIES
            return {"reply": metrics.chat_relay_msg(c["company"], rmode, simple),
                    "action": {"kind": "relay", "ticker": c["ticker"], "mode": rmode,
                               "needs_build": not built and not metrics.has_numbers([c]) and not body.demo,
                               "company": c["company"], "demo_numeric": metrics.has_numbers([c])}}
        if stripped and len(stripped) >= 2 and not _match_sector(stripped.lower(), path) \
                and stripped.lower() not in ("all", "asean", "everything", "this", "it", "company"):
            return {"reply": f"Building “{stripped}” live (ASEAN check)…",
                    "action": {"kind": "relay_live", "text": stripped, "mode": rmode}}
        return {"reply": metrics.chat_relay_help(simple), "action": {"kind": "none"}}

    # 2) filters + focus
    bits, country_out, sector_out = [], None, None
    if any(k in low for k in ("all asean", "all countries", "whole asean", "everywhere", "any country")):
        country_out, bits = "All", bits + ["all ASEAN markets"]
    else:
        for cn in universe.countries(path):
            if cn.lower() in low:
                country_out = cn
                bits.append(cn)
                break
    if any(k in low for k in ("all industries", "all sectors", "every industry", "any industry")):
        sector_out, bits = "All", bits + ["all industries"]
    else:
        sec = _match_sector(low, path)
        if sec:
            sector_out = sec
            bits.append(_short_sector(sec))

    comp = universe.resolve(t, path)
    explicit = low.startswith(("add ", "monitor ", "track ", "watch ", "focus ", "show me "))
    if comp and (explicit or not bits):
        peers = [c for c in universe.constituents(path) if c["sector"] == comp["sector"]]
        avg, _ = metrics.average_esg(peers)
        d = metrics.num((comp.get("momentum") or {}).get("digital_ai"))
        needs_build = (not body.demo and comp["ticker"] not in _ENTRIES
                       and not metrics.has_numbers([comp]))
        return {"reply": metrics.chat_focus_msg(comp["company"], _short_sector(comp["sector"]),
                                                 simple, avg=avg,
                                                 digital_pct=metrics.fmt_pct(d)),
                "action": {"kind": "focus", "ticker": comp["ticker"],
                           "needs_build": needs_build, "company": comp["company"]}}
    if bits:
        return {"reply": metrics.chat_filter_msg(bits, simple),
                "action": {"kind": "filter", "country": country_out, "sector": sector_out}}
    return {"reply": metrics.chat_fallback_msg(simple), "action": {"kind": "none"}}


# --------------------------------------------------------------------------- #
#  MONITOR / WATCHLIST  (build + pin snapshots)
# --------------------------------------------------------------------------- #
class MonitorIn(BaseModel):
    ticker: str = ""
    text: str = ""
    demo: bool = True


# --------------------------------------------------------------------------------------------- #
# The analyst's book — clients, and the brief they walk into a meeting with.
#
# A pure overlay on the engine: these endpoints read a scored run and compose. Nothing here
# creates a signal, sets a weight or decides a label, so `run_id` is untouched and the frozen
# N/M/K, the whitepaper figures and the anchored Merkle root all stay valid.
#
# The brief carries NO recommendation by construction (see brief.DISCLAIMER) — it prepares the
# evidence and the objections, and the analyst forms the view. That is HARD RULE 4 holding at the
# one place in the product where it would be most tempting to break it.
# --------------------------------------------------------------------------------------------- #

def _client_run(horizon=engine_config.DEFAULT_HORIZON):
    """Clients are always scored against the REAL universe — a book of institutional accounts
    over a fictional demo basket would be a category error, and the demo toggle does not reach
    here."""
    return _engine_run(False, horizon)


@app.get("/api/clients")
def clients_list():
    return {"clients": [clients_mod.summary(c) for c in clients_mod.load_all()],
            "origin": "fictional",
            "note": ("Fictional institutional accounts. No real client, holding or contact "
                     "detail appears in this build.")}


@app.get("/api/clients/{client_id}")
def client_get(client_id: str):
    c = clients_mod.get(client_id)
    if not c:
        raise HTTPException(status_code=404, detail="no such client")
    run, _meta, _cfg = _client_run()
    return {"client": c, "summary": clients_mod.summary(c),
            "delta": clients_mod.delta(c, run),
            "open_follow_ups": clients_mod.open_follow_ups(c)}


@app.get("/api/clients/{client_id}/brief")
def client_brief(client_id: str, horizon: str = engine_config.DEFAULT_HORIZON,
                 flip: bool = Query(True)):
    c = clients_mod.get(client_id)
    if not c:
        raise HTTPException(status_code=404, detail="no such client")
    run, meta, cfg = _client_run(horizon)
    return brief_mod.build(c, run, meta, cfg, with_flip=flip)


@app.get("/api/clients/{client_id}/brief.md")
def client_brief_md(client_id: str, horizon: str = engine_config.DEFAULT_HORIZON):
    c = clients_mod.get(client_id)
    if not c:
        raise HTTPException(status_code=404, detail="no such client")
    run, meta, cfg = _client_run(horizon)
    md = brief_mod.to_markdown(brief_mod.build(c, run, meta, cfg))
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


@app.post("/api/clients/{client_id}/meetings")
def client_close_meeting(client_id: str, payload: dict = Body(default={})):
    """Close a meeting: store the snapshot the client was actually shown, so the NEXT brief can
    say what changed. The date is supplied by the caller rather than read from a clock, so a
    back-dated or replayed meeting records when it really happened."""
    c = clients_mod.get(client_id)
    if not c:
        raise HTTPException(status_code=404, detail="no such client")
    run, _meta, _cfg = _client_run()
    date = (payload.get("date") or "").strip() or _dt.date.today().isoformat()
    meeting = clients_mod.close_meeting(
        client_id, run, date,
        note=payload.get("note") or "",
        discussed=payload.get("discussed") or c.get("coverage") or [],
        follow_ups=payload.get("follow_ups") or [])
    return {"ok": bool(meeting), "meeting": meeting,
            "summary": clients_mod.summary(clients_mod.get(client_id) or {})}


@app.post("/api/clients")
def client_upsert(payload: dict = Body(default={})):
    if not (payload.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="a client needs a name")
    return {"client": clients_mod.upsert(payload)}


@app.delete("/api/clients/{client_id}")
def client_delete(client_id: str):
    return {"ok": clients_mod.remove(client_id)}


@app.post("/api/monitor")
def monitor(body: MonitorIn):
    if body.ticker:
        if body.ticker in _ENTRIES:
            return {"ok": True, "ticker": body.ticker,
                    "entry": _entry_json(body.ticker, body.demo)}
        path = universe.active_file(body.demo)
        c = universe.get(body.ticker, path)
        if not c:
            c = universe.get(body.ticker, universe.active_file(not body.demo))
        if not c:
            # a previously live-added / uploaded ticker may simply not be in this universe
            raise HTTPException(404, f"{body.ticker} is not in the active universe.")
        tk, err = _ensure_snapshot(c, body.demo)
        if not tk:
            raise HTTPException(502, err or "Couldn't build that snapshot.")
        return {"ok": True, "ticker": tk, "entry": _entry_json(tk, body.demo)}
    if body.text:
        tk, err = _add_live_company(body.text)
        if not tk:
            raise HTTPException(502, err or f"Couldn't build “{body.text}”.")
        return {"ok": True, "ticker": tk, "entry": _entry_json(tk), "live_added": True}  # live => real
    raise HTTPException(400, "Provide a ticker or free text.")


@app.delete("/api/monitor/{ticker}")
def monitor_delete(ticker: str):
    _unpin(ticker)
    return {"ok": True, "watchlist": _WATCHLIST}


@app.get("/api/watchlist")
def watchlist():
    out = []
    stale = []
    for tk in _WATCHLIST:
        e = _entry_json(tk, demo=True)  # summary rows: skip the per-name quote fetch
        if e:
            out.append(e)
        elif (universe.get(tk, universe.active_file(True)) or
              universe.get(tk, universe.active_file(False))):
            out.append({"ticker": tk, "built": False})
        else:
            stale.append(tk)
    if stale:
        with _ENTRIES_LOCK:
            for tk in stale:
                if tk in _WATCHLIST:
                    _WATCHLIST.remove(tk)
            _save_watchlist(_WATCHLIST)
    return {"tickers": _WATCHLIST, "entries": out}


@app.get("/api/entry/{ticker}")
def entry(ticker: str, demo: bool = Query(False)):
    e = _entry_json(ticker, demo)
    if not e:
        raise HTTPException(404, "No built snapshot for that ticker — POST /api/monitor first.")
    return e


@app.post("/api/sample")
def sample():
    if not os.path.exists(SAMPLE_FILE):
        raise HTTPException(404, "Sample file missing.")
    company = core.load_company_data(SAMPLE_FILE)
    company["_origin"] = "sample"
    tk = _pin(company)
    entry = _ENTRIES[tk]
    try:
        with open(os.path.join(FIXTURES_DIR, "narrowed_question.json"), encoding="utf-8") as f:
            entry["narrowed_q"] = contracts.coerce_narrowed_question(json.load(f))
        with open(os.path.join(FIXTURES_DIR, "stage2_answer.json"), encoding="utf-8") as f:
            entry["answer"] = contracts.coerce_stage2_answer(json.load(f))
    except (OSError, ValueError):
        pass
    return {"ok": True, "ticker": tk, "entry": _entry_json(tk)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    # Read in bounded chunks and stop the moment the cap is exceeded. `await file.read()` with no
    # limit pulls the whole upload into memory, so on a publicly reachable instance one large POST
    # is enough to take the process down. Tunable via ESG_MAX_UPLOAD_MB (default 5 MB) — a
    # Contract-B JSON/CSV is kilobytes, so this is generous.
    limit = MAX_UPLOAD_BYTES
    chunks, total = [], 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                413, f"File is larger than the {limit // (1024 * 1024)} MB upload limit.")
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(400, "That file is empty.")
    try:
        company, meta = datasource.load_upload(file.filename or "upload", content)
    except core.LLMConfigError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Couldn't read that file ({type(e).__name__}).")
    tk = _pin(company)
    return {"ok": True, "ticker": tk, "meta": meta, "entry": _entry_json(tk)}


# --------------------------------------------------------------------------- #
#  STAGE 1 — interrogation (stateless: the client owns the conversation)
# --------------------------------------------------------------------------- #
class Stage1AskIn(BaseModel):
    messages: list
    turns: int = 0
    ticker: str = ""
    force: bool = False


@app.post("/api/stage1/ask")
def stage1_ask(body: Stage1AskIn):
    company = (_ENTRIES.get(body.ticker) or {}).get("company")
    turns = core.MAX_QUESTIONS if body.force else body.turns
    try:
        env, raw = stage1.ask_next(body.messages, turns, company)
    except core.LLMConfigError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Couldn't reach the model ({type(e).__name__}: {e}).")
    return {"envelope": env, "raw": raw}


class Stage1NarrowIn(BaseModel):
    trail: list
    final_env: dict


@app.post("/api/stage1/narrow")
def stage1_narrow(body: Stage1NarrowIn):
    return {"narrowed_q": stage1.build_narrowed_question(body.trail, body.final_env)}


# --------------------------------------------------------------------------- #
#  STAGE 2 — compete (SSE: rag status -> phase labels -> token deltas -> answer)
# --------------------------------------------------------------------------- #
class Stage2In(BaseModel):
    ticker: str
    nq: dict
    use_rag: bool = True
    top_k: int = 5


@app.post("/api/stage2/run")
def stage2_run(body: Stage2In):
    entry = _ENTRIES.get(body.ticker)
    if not entry:
        raise HTTPException(404, "No built snapshot for that ticker.")
    company = entry["company"]
    nq = contracts.coerce_narrowed_question(body.nq)

    q = queue.Queue()

    def work():
        try:
            ctx = stage2.retrieve_context(nq, company, use_rag=body.use_rag, k=body.top_k)
            q.put(("rag", {"status": ctx.get("status"), "doc_count": ctx.get("doc_count", 0),
                           "query": ctx.get("query", ""), "error": ctx.get("error"),
                           "snippets": len(ctx.get("snippets") or [])}))
            seen = set()

            def on_delta(delta, accumulated):
                for key, label in _S2_PHASES:
                    if key not in seen and f'"{key}"' in accumulated:
                        seen.add(key)
                        q.put(("phase", {"label": label}))
                q.put(("delta", {"text": delta}))

            answer = stage2.reason(nq, company, on_delta=on_delta, context=ctx)
            with _ENTRIES_LOCK:
                entry["answer"] = answer
                entry["narrowed_q"] = nq
                _BUILT_AT[0] = time.time()
            q.put(("answer", {"answer": answer, "narrowed_q": nq}))
        except core.LLMConfigError as e:
            q.put(("error", {"kind": "config", "message": str(e)}))
        except Exception as e:  # noqa: BLE001
            q.put(("error", {"kind": "model",
                             "message": f"Something went wrong reaching the model ({type(e).__name__}: {e})."}))
        finally:
            q.put(("done", {}))

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            try:
                kind, payload = q.get(timeout=120)
            except queue.Empty:
                yield "event: error\ndata: {}\n\n".replace(
                    "{}", json.dumps({"kind": "timeout", "message": "Stage 2 timed out."}))
                break
            yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if kind in ("answer", "error", "done"):
                if kind != "done":
                    # drain the trailing done marker so the client sees a clean close
                    try:
                        q.get(timeout=1)
                    except queue.Empty:
                        pass
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Stage2QuickIn(BaseModel):
    ticker: str
    use_rag: bool = True
    top_k: int = 5


@app.post("/api/stage2/quick")
def stage2_quick(body: Stage2QuickIn):
    """Non-streaming variant (simpler clients / tests): blocks until the answer is ready."""
    entry = _ENTRIES.get(body.ticker)
    if not entry:
        raise HTTPException(404, "No built snapshot for that ticker.")
    company = entry["company"]
    nq = entry.get("narrowed_q") or _default_nq(company)
    try:
        answer = stage2.reason(nq, company, context=None if body.use_rag else
                               {"snippets": [], "status": "disabled", "doc_count": 0,
                                "query": "", "error": None})
    except core.LLMConfigError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Stage 2 failed ({type(e).__name__}: {e}).")
    entry["answer"] = answer
    entry["narrowed_q"] = nq
    return {"answer": answer, "narrowed_q": nq}


# --------------------------------------------------------------------------- #
#  COMPARE
# --------------------------------------------------------------------------- #
class CompareIn(BaseModel):
    tickers: list


@app.post("/api/compare")
def compare(body: CompareIn):
    tickers = [tk for tk in body.tickers if tk in _ENTRIES]
    if len(tickers) < 2:
        raise HTTPException(400, "Need at least 2 built snapshots to compare.")
    companies = [_ENTRIES[tk]["company"] for tk in tickers]
    data = metrics.compare_companies(companies)
    cards = []
    for tk in tickers:
        e = _ENTRIES[tk]
        snap = e["snap"]
        ans = e.get("answer") or {}
        cards.append({"ticker": tk, "snap": snap, "band_emoji": _band_emoji(snap),
                      "verdict": ans.get("competes_summary") or ""})
    return {"data": data, "cards": cards,
            "higher_better_all": bool(tickers) and all(
                _ENTRIES[tk]["snap"].get("score_higher_better") for tk in tickers)}


# --------------------------------------------------------------------------- #
#  EVIDENCE TRAIL + ON-CHAIN VERIFICATION  (Build Spec A4/A5 detail · C4)
# --------------------------------------------------------------------------- #
@app.get("/api/engine/company/{ticker:path}")
def engine_company(ticker: str, demo: bool = Query(True),
                   horizon: str = Query(engine_config.DEFAULT_HORIZON)):
    """One company's full score record + its evidence trail.

    Every trail row carries the stored `rationale` — the one-line justification for why that
    signal was routed and scored the way it was (INSTRUCTIONS step 5) — plus its real source
    URL, so the three-click rule holds: card -> evidence -> source.

    `horizon` must match whatever the matrix is showing. Serving the Long record behind a Short
    matrix would put one set of numbers on the card and a different set one click away, which is
    exactly the kind of quiet inconsistency the evidence trail exists to rule out."""
    run, meta, cfg = _engine_run(demo, horizon)
    record = engine.record_for(run, ticker)
    # The bucket is a property of the WHOLE run — you cannot tell whether a company is bond-ready
    # without the cohort it is ranked against — so it is derived from the full run here, not from
    # whatever subset a filter happens to be showing.
    nmk_one = pipeline_counts.counts(run, meta, cfg)
    buckets_one = pipeline_counts.bucket_of(nmk_one)
    if not record:
        raise HTTPException(404, f"{ticker} is not in the scored universe.")
    constituent = universe.get(ticker, universe.active_file(demo)) or {}
    # Which of these facts we gathered ourselves, rather than receiving in the verified basket.
    # Matched on (url, date) because that pair is what the harvest actually stored; a reader
    # looking at a mixed trail is entitled to know which rows came from where.
    harvested = {(e.get("source_url", ""), e.get("published_at", ""))
                 for e in harvest.load_overlay().get(ticker, [])}
    trail = [{
        "origin": ("harvested" if (s["source_url"], s["published_at"]) in harvested
                   else "supplied"),
        "signal_id": s["signal_id"], "routes": s["routes"], "component": s["component"],
        "subcomponent": s["subcomponent"], "direction": s["direction"],
        "materiality": s["materiality"], "confidence": s["confidence"],
        "published_at": s["published_at"], "date_basis": s["date_basis"],
        "source_url": s["source_url"], "source_type": s["source_type"],
        "raw_text": s["raw_text"], "rationale": s["rationale"],
        "model_version": s["model_version"], "prompt_version": s["prompt_version"],
    } for s in sorted(record["signals"], key=lambda s: (s["published_at"], s["signal_id"]),
                      reverse=True)]
    return {
        "ticker": ticker,
        "company": record["company"],
        "record": _record_summary(record),
        "subcomponents": record["subcomponents"],
        "coverage": record["coverage"],
        "breadth": record["breadth"],
        "corroboration": record["corroboration"],
        "mean_source_quality": record["mean_source_quality"],
        "trail": trail,
        "badges": _badges(ticker, meta, cfg, record, nmk_one, buckets_one),
        "metadata_row": {k: v for k, v in (meta.get(ticker) or {}).items()
                         if k not in ("notes",)} or {},
        "metadata_note": (meta.get(ticker) or {}).get("notes", ""),
        "foundation": {"basis": constituent.get("esg_basis", ""),
                       "source_url": constituent.get("source_url", ""),
                       "confidence": constituent.get("confidence", "")},
        "anchor": _anchor_summary(run),
        "run_id": run["run_id"],
        "as_of": run["as_of"],
    }


class VerifyIn(BaseModel):
    ticker: str
    demo: bool = True
    horizon: str = engine_config.DEFAULT_HORIZON   # verify the run the judge is LOOKING at
    tamper: bool = False              # rehearsal-only: corrupt one excerpt and watch it fail
    tamper_leaf_id: str = ""


@app.post("/api/verify")
def verify(body: VerifyIn):
    """C4: recompute this company's evidence leaves, walk the Merkle paths, compare with the
    anchored root. Works fully offline against the stored run record; when an RPC is configured
    it ALSO reads the root back off Sepolia and reports both verdicts.

    `tamper=true` edits one character of one excerpt before hashing — the five-second demo that
    a changed source breaks verification. It never touches the stored record."""
    run, _meta, _cfg = _engine_run(body.demo, body.horizon)
    record = anchor.load_record(run["run_id"])
    if not record:
        anchor.anchor_run(run, company_metadata.load(demo=body.demo), push=False)
    evidence = None
    if body.tamper:
        stored = anchor.load_record(run["run_id"]) or {}
        mine = [leaf for leaf in stored.get("leaves", [])
                if leaf.get("company_id") == body.ticker]
        target = next((leaf for leaf in mine if leaf["leaf_id"] == body.tamper_leaf_id), None) \
            or (mine[0] if mine else None)
        if target:
            evidence = [{"leaf_id": target["leaf_id"],
                         "preimage": target["preimage"] + "X"}]
    payload = anchor.verify_company(run["run_id"], body.ticker, evidence=evidence,
                                    check_chain=True)
    payload["tampered"] = bool(evidence)
    payload["chain_config"] = {k: v for k, v in anchor.chain_config().items() if k != "has_key"}
    return payload


@app.get("/api/benchmarks")
def benchmarks_api(demo: bool = Query(True), sector: str = ""):
    """Industry benchmarks: the ASEAN peer average and the OECD industry footprint.

    Served on its own rather than inlined into /api/board because it is a level-2 panel — the
    board should not pay for a table nobody has opened.
    """
    book = benchmarks.load_oecd()
    payload = {
        "available": book["available"],
        "meta": book["meta"],
        "industries": book["rows"],
        "table": benchmarks.industry_table(demo=demo),
    }
    if sector:
        payload["sector"] = {"asean": benchmarks.asean_for_sector(sector, demo=demo),
                             "oecd": benchmarks.oecd_for_sector(sector)}
    return payload


@app.get("/api/quote/{ticker:path}")
def quote_api(ticker: str, demo: bool = Query(False)):
    """One live quote. Best-effort: an unavailable quote is a 200 with a reason, not an error."""
    row = next((c for c in universe.constituents(universe.active_file(demo)) if c["ticker"] == ticker), None)
    return quotes.quote(ticker, demo=demo, company=(row or {}).get("company", ""))


@app.get("/api/lseg/{ticker:path}")
def lseg_api(ticker: str, demo: bool = Query(False), company: str = "", exchange: str = ""):
    """LSEG's own published ESG score for one company — the REAL incumbent view.

    This is the only number on the board that the rating agency itself published, so it is the
    honest left-hand side of "what the rating sees vs what we see". Everywhere else the
    incumbent baseline is a SUPPLIED or MOCK figure; here it is sourced, dated by fiscal
    year, and attributed on its face.

    Deliberately NOT part of /api/board. It is one outbound call per company and the board
    paints 52 of them — a screen must never fan out into a rating provider. The deep dive asks
    for the focused name only.

    Best-effort like every other live panel (rule 1): an uncovered issuer, a blocked network or
    a slow endpoint all return `available: false` with a reason, at 200. Nothing on the board
    is allowed to hard-fail because a third party is down.

    `demo=true` is refused rather than answered: the demo universe is FICTIONAL, and asking a
    real rating provider about an invented company can only produce a wrong-name match.
    """
    row = universe.get(ticker, universe.active_file(demo)) or {}
    name = company or row.get("company", "")
    market = exchange or row.get("exchange", "")
    base = {"ticker": ticker, "company": name, "source_url": lseg.PUBLIC_URL,
            "attribution": lseg.ATTRIBUTION}

    if demo or (row and row.get("_demo")):
        return {**base, "available": False,
                "reason": "Demo universe names are illustrative, so there is no real rating to "
                          "fetch. Switch off Demo data to look this up."}
    if not name:
        return {**base, "available": False, "reason": f"{ticker} is not in the loaded universe."}

    # CGSI publish the Reuters code for every one of the 52 in Figure 5 of their note, and the
    # basket carries it. Using it means an EXACT lookup — no name matching, so no chance of
    # serving one issuer's ESG breakdown under another's name. Name matching stays as the
    # fallback for anything reached outside the basket (an upload, a free-text company).
    ric = (row.get("ric") or "").strip()
    candidates = [name] + [a for a in (row.get("aliases") or []) if len(a) > 3 and a != name]
    scores = None
    try:
        if ric:
            scores = lseg.lookup("", market, ric=ric)
        for candidate in candidates:
            if scores:
                break
            scores = lseg.lookup(candidate, market)
    except Exception as exc:  # noqa: BLE001 — rule 1: a third party never breaks the board.
        return {**base, "available": False, "reason": f"LSEG lookup failed: {type(exc).__name__}"}

    if not scores:
        return {**base, "available": False,
                "reason": f"{name} is not in LSEG's ~12.5k covered issuers, or the finder is "
                          f"unreachable right now."}
    return {**base, "available": True, "scores": scores}


@app.get("/api/rationale/{ticker:path}")
def company_rationale(ticker: str, demo: bool = False,
                      horizon: str = engine_config.DEFAULT_HORIZON):
    """The full pro/con case for one company — ESG and financial, side by side and never merged.

    Rule-derived from the stored run (no LLM), so it replays identically for the run it
    describes. 404 when the company is not in the scored universe: a case built for a company the
    engine never ranked would be a verdict with no cohort behind it."""
    rec = _focused_engine_record(demo, horizon, ticker)
    if not rec:
        raise HTTPException(status_code=404, detail=f"{ticker} is not in the scored universe")
    return rationale.build(rec, company_metadata.load(demo=demo).get(ticker))


@app.get("/api/anchors")
def anchors():
    """Every anchored run on disk — the comply-or-explain run list (C2: anchor every run)."""
    return {"records": anchor.list_records(), "chain": anchor.chain_config()}


# --------------------------------------------------------------------------- #
#  "BUT WHAT ABOUT THE FUTURE?" — the two honest answers
#
#  Neither endpoint predicts anything, because the engine cannot and will not. Between them
#  they answer the question a static rating never has to face: the evidence WILL change, so
#  what is this verdict actually standing on, and has it moved before?
#
#    /api/sensitivity  — forwards. Which signals carry the label right now, and how close is
#                        it to a boundary. Measured by re-scoring, not estimated.
#    /api/backtest     — backwards. Five real cases where each point is a real engine run at
#                        its own cutoff: what the Radar would have said on that date, against
#                        a rating that did not move.
# --------------------------------------------------------------------------- #
@app.get("/api/sensitivity/{ticker:path}")
def sensitivity_for(ticker: str, demo: bool = Query(True),
                    horizon: str = Query(engine_config.DEFAULT_HORIZON)):
    """What would change this verdict — leave-one-out over the evidence, plus the margins.

    `horizon` must match the matrix on screen for the same reason `/api/engine/company` insists
    on it: a sensitivity report computed against a different re-score would name signals that
    are not the ones behind the number the reader is looking at."""
    run, _meta, cfg = _engine_run(demo, horizon)
    out = sensitivity.flip_analysis(run, ticker, cfg)
    if out is None:
        raise HTTPException(404, f"{ticker} is not in the scored universe.")
    out["horizon"] = horizon
    return out


@app.get("/api/backtest")
def backtest(case: str = Query("")):
    """The per-case validation timelines: our reading moving while the rating stayed flat.

    Read straight off `docs/backtest/series.json`, which `backtest_timeline.py` regenerates and
    `harness.py` checks is current — so this endpoint can never quietly serve a stale chart that
    disagrees with the one in the docs. Best-effort: a missing file is an empty case list and a
    reason, never a 500 that takes the board down with it."""
    path = os.path.join(BASE_DIR, "docs", "backtest", "series.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, ValueError) as exc:                                    # noqa: BLE001
        return {"available": False, "cases": [],
                "reason": f"No backtest series on disk ({type(exc).__name__}). "
                          "Run `python backtest_timeline.py`."}
    cases = blob.get("cases") or []
    if case:
        cases = [c for c in cases if c.get("case_id") == case]
        if not cases:
            raise HTTPException(404, f"No backtest case {case!r}.")
    return {
        "available": True,
        "note": blob.get("_note", ""),
        "lookback_months": blob.get("lookback_months"),
        "generated_from": blob.get("generated_from", ""),
        "cases": cases,
        "disclaimer": ("Each point is a real engine run with its own cutoff — what the Radar "
                       "would have said on that date. The baseline is a MOCK stand-in for the "
                       "incumbent view, not a licensed rating series. Past behaviour of the "
                       "signal is not a prediction and never investment advice."),
    }


@app.get("/api/claim-evidence")
def claim_evidence(ticker: str = Query("")):
    """Claim vs Evidence — what a company SAYS against what an independent source can see.

    ILLUSTRATIVE by construction (Prototype_Build_Notes.md §6) and the payload says so in its
    own header: no satellite query is run here. Each row carries `checked` on BOTH sides and on
    the verdict, so the one genuine determination in the set — a bank's financed emissions,
    where no independent dataset exists at all — is visibly a result rather than a mock-up.

    Best-effort: a missing file is `available: False` and a reason, never a 500."""
    path = os.path.join(BASE_DIR, "data", "claim_vs_evidence.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, ValueError) as exc:                                    # noqa: BLE001
        return {"available": False, "rows": [],
                "reason": f"No claim/evidence file on disk ({type(exc).__name__})."}
    rows = blob.get("rows") or []
    if ticker:
        rows = [r for r in rows if r.get("company_id") == ticker]
    return {
        "available": True,
        "header": blob.get("header", ""),
        "deck_line": blob.get("deck_line", ""),
        "verdicts": blob.get("verdicts", {}),
        "rows": rows,
        "illustrative": True,
    }


# --------------------------------------------------------------------------- #
#  STATIC (production: serve the built React app from web/dist)
# --------------------------------------------------------------------------- #
if os.path.isdir(WEB_DIST):
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    for line in precompute_engine():
        print(f"  precomputed  {line}")
    # HOST defaults to all interfaces for local dev. Behind a reverse proxy set HOST=127.0.0.1 so
    # the app port is not independently reachable — otherwise anyone can bypass the proxy (and
    # whatever auth it enforces) by hitting the port directly. See docs/DEPLOY.md.
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", 8000)))
