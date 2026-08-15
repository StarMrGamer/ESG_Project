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

import json
import os
import queue
import re
import threading
import time

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import anchor
import company_metadata
import contracts
import core
import datasource
import engine
import engine_config
import metrics
import pipeline_counts
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


def _entry_json(ticker):
    """Full deep-dive payload for one monitored company (Contract B + snap + cached batons)."""
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


def _engine_run(demo):
    """The scored run for a universe, with metadata joined and tiers stamped."""
    cfg = engine_config.load()
    path = universe.active_file(demo)
    key = (path, cfg["config_hash"], os.path.getmtime(path) if os.path.exists(path) else 0,
           company_metadata.load_report().get("rows", 0))
    hit = _ENGINE_MEMO.get(key)
    if hit:
        return hit
    meta = company_metadata.load()
    run = engine.run_engine(universe.constituents(path), metadata=meta, config=cfg)
    if len(_ENGINE_MEMO) > 4:                  # keys carry mtime+config, so stale ones pile up
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


def _badges(ticker, meta, cfg):
    row = meta.get(ticker, {})
    return {"green_bond": company_metadata.green_bond_badge(row, cfg),
            "profitability": company_metadata.profitability_badge(row)}


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


def _engine_block(demo, filtered):
    """Everything the Build-Spec front-end needs for one filtered view."""
    run, meta, cfg = _engine_run(demo)
    tickers = [c["ticker"] for c in filtered]
    by_id = {r["company_id"]: r for r in run["records"]}
    subset = {"records": [by_id[t] for t in tickers if t in by_id],
              "company_count": len(tickers)}
    labels = {k: engine_config.display(cfg, k) for k in engine_config.label_order(cfg)}
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
        "nmk": pipeline_counts.counts(subset, meta, cfg),
        "metadata": company_metadata.load_report(),
        "anchor": _anchor_summary(run),
        "records": {t: _record_summary(by_id[t]) for t in tickers if t in by_id},
        "badges": {t: _badges(t, meta, cfg) for t in tickers},
    }


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


def _cc_focused(focus_ticker, filtered, path):
    if focus_ticker:
        c = universe.get(focus_ticker, path)
        if c:
            return c
        e = _ENTRIES.get(focus_ticker)
        if e:
            return e["company"]
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
          focus: str = "", simplified: bool = Query(True)):
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
    focused = _cc_focused(focus or None, filtered, path)
    nt = {focus} if focus else set()

    avg_payload = _board_average(filtered, mode, sector)

    hw_rows, peer_avg, peer_n = metrics.hidden_winners(filtered, top_n=5, new_tickers=nt)
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
        fc = metrics.forecast_outlook(focused)
        pct = metrics.price_change_pct(focused) if demo else None
        focused_payload = {
            "constituent": focused,
            "from_snapshot": bool(entry),
            "classification": cls,
            "credentials": ep.get("credentials", []),
            "leadership": {"score": ep.get("score"), "band": ep.get("band"),
                           "has": bool(ep)} if ep else None,
            "signals": signals,
            "signals_kind": signals_kind,
            "why_wrong": _why_wrong(focused),
            "plain_summary": metrics.plain_summary(focused, answer),
            "forecast": fc,
            "news": metrics.news_card(focused),
            "analyst": metrics.analyst_coverage(focused),
            "check_action": metrics.focused_answer_action(
                {ft: entry} if entry else {}, ft),
            "price": {"pct": pct, "series": metrics.price_series(pct) if pct is not None else []},
            "foundation": ({"basis": focused.get("esg_basis"),
                            "source_url": focused.get("source_url"),
                            "confidence": focused.get("confidence")}
                           if focused.get("esg_basis") else None),
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
        "pillars": metrics.pillar_momentum(filtered),
        "momentum_series": metrics.momentum_series(filtered),
        "hidden_winners": {"rows": hw_rows, "peer_avg": peer_avg, "n": peer_n},
        "evidence": {"coverage": metrics.credential_coverage(filtered), "leaders": leaders},
        "constituents": filtered,
        "engine": _engine_block(demo, filtered),
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


@app.post("/api/monitor")
def monitor(body: MonitorIn):
    if body.ticker:
        if body.ticker in _ENTRIES:
            return {"ok": True, "ticker": body.ticker, "entry": _entry_json(body.ticker)}
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
        return {"ok": True, "ticker": tk, "entry": _entry_json(tk)}
    if body.text:
        tk, err = _add_live_company(body.text)
        if not tk:
            raise HTTPException(502, err or f"Couldn't build “{body.text}”.")
        return {"ok": True, "ticker": tk, "entry": _entry_json(tk), "live_added": True}
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
        e = _entry_json(tk)
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
def entry(ticker: str):
    e = _entry_json(ticker)
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
def engine_company(ticker: str, demo: bool = Query(True)):
    """One company's full score record + its evidence trail.

    Every trail row carries the stored `rationale` — the one-line justification for why that
    signal was routed and scored the way it was (INSTRUCTIONS step 5) — plus its real source
    URL, so the three-click rule holds: card -> evidence -> source."""
    run, meta, cfg = _engine_run(demo)
    record = engine.record_for(run, ticker)
    if not record:
        raise HTTPException(404, f"{ticker} is not in the scored universe.")
    constituent = universe.get(ticker, universe.active_file(demo)) or {}
    trail = [{
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
        "badges": _badges(ticker, meta, cfg),
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
    tamper: bool = False              # rehearsal-only: corrupt one excerpt and watch it fail
    tamper_leaf_id: str = ""


@app.post("/api/verify")
def verify(body: VerifyIn):
    """C4: recompute this company's evidence leaves, walk the Merkle paths, compare with the
    anchored root. Works fully offline against the stored run record; when an RPC is configured
    it ALSO reads the root back off Sepolia and reports both verdicts.

    `tamper=true` edits one character of one excerpt before hashing — the five-second demo that
    a changed source breaks verification. It never touches the stored record."""
    run, _meta, _cfg = _engine_run(body.demo)
    record = anchor.load_record(run["run_id"])
    if not record:
        anchor.anchor_run(run, company_metadata.load(), push=False)
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


@app.get("/api/anchors")
def anchors():
    """Every anchored run on disk — the comply-or-explain run list (C2: anchor every run)."""
    return {"records": anchor.list_records(), "chain": anchor.chain_config()}


# --------------------------------------------------------------------------- #
#  STATIC (production: serve the built React app from web/dist)
# --------------------------------------------------------------------------- #
if os.path.isdir(WEB_DIST):
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    # HOST defaults to all interfaces for local dev. Behind a reverse proxy set HOST=127.0.0.1 so
    # the app port is not independently reachable — otherwise anyone can bypass the proxy (and
    # whatever auth it enforces) by hitting the port directly. See docs/DEPLOY.md.
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", 8000)))
