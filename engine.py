"""
engine.py — `run_engine(company_list)`: the reproducible scoring engine (Gate 1).
=================================================================================
Signals in (from `signals.py`), **score records** out. One record per company, carrying every
number the UI, the harness and the Merkle anchor need — and nothing that can differ between two
runs of the same inputs.

Reproducibility is the whole point of Gate 1, so the engine is a pure function:

* **no clock** — time decay measures against an explicit `as_of` (defaulting to the newest date
  the data itself states), never `today`;
* **no RNG** — every tie-break and id is a hash of the inputs;
* **no network, no LLM** — signal extraction is rule-based (`signals.py`);
* **identity in the id** — `run_id = H(engine_version | config_hash | as_of | cutoff | company
  ids | signal ids)`. Same inputs → same run id → same records, and a changed weight cannot
  quietly produce "the same run".

The pipeline per company:

    signals -> (optional cutoff filter) -> weight each signal
            -> subcomponent momentum -> component momentum (E/S/G/DIGITAL)
            -> composite momentum + composite confidence
            -> percentile vs the run's cohort, against a MOCK baseline percentile
            -> disagreement -> CGSI quadrant label (A1)

`lseg_percentile` is a **mocked** incumbent baseline (Build Spec B4 calls it "the mocked LSEG
baseline"): the percentile of the company's stored static rating inside this run's cohort. Every
record says so in `baseline_basis` — it is never presented as a licensed LSEG figure.

Weighting, in one line: `w = materiality x confidence x 2^(-age_days / half_life)`, and a
component's momentum is `sum(direction x w) / sum(w)` over the signals routed to it, so every
momentum sits in [-1, +1] and is directly comparable across companies.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

import engine_config
import metrics
import signals as signal_lib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache", "engine")
#: The SHAPE of a record, versioned separately from `engine_version`.
#:
#: `run_id` hashes every INPUT — config, metadata, companies, signals — which is what makes a
#: cache hit safe and what `anchor.py` keys its Merkle roots on. But the record's shape is
#: decided by CODE, not by an input, so adding a display-only field leaves the id untouched and
#: a warm cache would serve the OLD shape under the SAME id. On screen that reads as "the field
#: is empty for this company", not "your cache is stale" — a false negative, which is the
#: failure mode this codebase keeps getting bitten by. Bump this when a record gains or loses a
#: field; `_read_cache` then discards the older shape instead of serving it. Deliberately NOT in
#: `run_id`: the scores, the evidence and the root are unchanged, so it is the same run.
RECORD_SCHEMA = "record-v3"
COMPONENTS = ("E", "S", "G", "DIGITAL")


class CutoffViolation(AssertionError):
    """A signal published on/after a backtest cutoff reached the score record — lookahead.

    Raised loudly and never swallowed: a backtest that silently sees the future is worse than
    no backtest at all (A8)."""


# --------------------------------------------------------------------------- #
#  small deterministic helpers
# --------------------------------------------------------------------------- #
def _days_between(later, earlier):
    """Whole days between two ISO dates, without importing a clock. Negative -> 0."""
    def _ord(iso):
        try:
            y, m, d = (int(x) for x in str(iso)[:10].split("-"))
        except (ValueError, AttributeError):
            return None
        # days-from-epoch via the civil-from-days inverse (Howard Hinnant's algorithm)
        y -= m <= 2
        era = (y if y >= 0 else y - 399) // 400
        yoe = y - era * 400
        doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
        doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
        return era * 146097 + doe - 719468
    a, b = _ord(later), _ord(earlier)
    if a is None or b is None:
        return 0
    return max(0, a - b)


def _decay(published_at, as_of, half_life_days):
    """2^(-age/half_life). Undated or future-dated signals decay by nothing — their weight is
    already cut through `confidence`, and double-penalising them would hide them entirely."""
    if not published_at or not as_of or half_life_days <= 0:
        return 1.0
    return 2.0 ** (-_days_between(as_of, published_at) / float(half_life_days))


def _percentiles(values):
    """Percentile rank in [0,1] for each value, ties sharing the average rank. Deterministic and
    independent of input order. A single-element cohort is 0.5 — it has no cohort to rank in."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    order = sorted(range(n), key=lambda i: (values[i], i))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 / (n - 1)
        for k in range(i, j + 1):
            ranks[order[k]] = round(shared, 6)
        i = j + 1
    return ranks


def _as_of_from(company_list, signals_by_id):
    """The reference date for decay: the newest date the DATA states. Deterministic by
    construction — two runs over the same files pick the same date forever."""
    dates = [s["published_at"] for sigs in signals_by_id.values() for s in sigs
             if s.get("published_at")]
    for c in company_list or []:
        for key in ("esg_as_of", "as_of"):
            v = str((c or {}).get(key) or "").strip()
            if v:
                dates.append(signal_lib._as_iso(v))
    return max(dates) if dates else ""


# --------------------------------------------------------------------------- #
#  aggregation
# --------------------------------------------------------------------------- #
def _aggregate(sigs, cfg, as_of):
    """Signals -> {subcomponents, components, composite_momentum, composite_confidence}.

    A signal reaches EVERY route it carries (A2: one cyber record scores in DIGITAL/digital_risk
    and in G/controversy) but is counted once for `signal_count` and once in the Merkle tree."""
    half_life = cfg["decay"]["half_life_days"]
    sub_acc = {}          # (component, subcomponent) -> [signed, total, count]
    for s in sigs:
        w = float(s["materiality"]) * float(s["confidence"]) * _decay(
            s.get("published_at"), as_of, half_life)
        if w <= 0:
            continue
        for route in s.get("routes") or [{"component": s.get("component"),
                                          "subcomponent": s.get("subcomponent")}]:
            key = (route["component"], route["subcomponent"])
            acc = sub_acc.setdefault(key, [0.0, 0.0, 0])
            acc[0] += float(s["direction"]) * w
            acc[1] += w
            acc[2] += 1

    subcomponents = {}
    for (comp, sub), (signed, total, count) in sorted(sub_acc.items()):
        subcomponents.setdefault(comp, {})[sub] = {
            "momentum": round(signed / total, 6) if total else 0.0,
            "weight": round(total, 6), "signal_count": count,
        }

    digital_w = {k: v for k, v in cfg["digital_subweights"].items() if not k.startswith("_")}
    components = {}
    for comp in COMPONENTS:
        subs = subcomponents.get(comp) or {}
        if not subs:
            continue
        if comp == "DIGITAL":
            # A2: the disclosed sub-weights drive DIGITAL, renormalised over the subcomponents
            # this company actually has evidence for (an absent one must not count as a zero).
            num = den = 0.0
            for sub, row in subs.items():
                sw = digital_w.get(sub, 0.0)
                num += sw * row["momentum"]
                den += sw
            momentum = num / den if den else 0.0
        else:
            num = sum(row["momentum"] * row["weight"] for row in subs.values())
            den = sum(row["weight"] for row in subs.values())
            momentum = num / den if den else 0.0
        components[comp] = {
            "momentum": round(momentum, 6),
            "weight": round(sum(r["weight"] for r in subs.values()), 6),
            "signal_count": sum(r["signal_count"] for r in subs.values()),
        }

    cw = {k: v for k, v in cfg["component_weights"].items() if not k.startswith("_")}
    num = sum(cw.get(c, 0.0) * components[c]["momentum"] for c in components)
    den = sum(cw.get(c, 0.0) for c in components)
    consensus = round(num / den, 6) if den else 0.0

    # Shrinkage. `consensus` says which way the evidence points; on its own it cannot tell one
    # weak signal from twelve corroborating ones, because both are unanimous. Scaling by
    # w/(w+k) makes an extreme score something a company has to EARN with evidence that is both
    # one-sided and substantial. Applied once, at the composite, so the per-component numbers
    # below stay readable as what they are: direction consensus.
    evidence_weight = sum(float(s["materiality"]) * float(s["confidence"])
                          * _decay(s.get("published_at"), as_of, half_life) for s in sigs)
    k = cfg["momentum_shrinkage"]["half_credit_weight"]
    shrinkage = evidence_weight / (evidence_weight + k) if (evidence_weight + k) > 0 else 0.0
    composite = round(consensus * shrinkage, 6)

    conf_cfg = cfg["confidence"]
    n = len(sigs)
    coverage = min(1.0, n / float(max(1, conf_cfg["saturation_count"])))
    mean_quality = (sum(float(s["confidence"]) for s in sigs) / n) if n else 0.0
    # breadth: how many INDEPENDENT lines of evidence agree. Eight signals about one thing are
    # weaker than four about four things, and corroboration is the only honest way to be more
    # confident than your best single source.
    breadth = len(sub_acc)
    saturation = max(2, conf_cfg["breadth_saturation"])
    corroboration = min(1.0, max(0, breadth - 1) / float(saturation - 1))
    quality = mean_quality + (1.0 - mean_quality) * conf_cfg["corroboration_weight"] * corroboration
    confidence = round(coverage * quality, 6) if n >= conf_cfg[
        "min_signals_for_any_confidence"] else 0.0

    return {"subcomponents": subcomponents, "components": components,
            "composite_momentum": composite, "composite_confidence": confidence,
            "direction_consensus": consensus, "evidence_weight": round(evidence_weight, 6),
            "shrinkage": round(shrinkage, 6),
            "coverage": round(coverage, 6), "mean_source_quality": round(mean_quality, 6),
            "breadth": breadth, "corroboration": round(corroboration, 6)}


def _baseline_score(company):
    """The incumbent static rating we are competing with, 0-100 (higher = better regarded).

    Numeric universes carry `esg_score`; the real ASEAN names carry no number, so we use the
    GROUNDED leadership score `metrics.parse_evidence` derives from the ratings their evidence
    text actually cites.

    THREE PROVENANCES, and the record carries which one it got (`baseline_origin`) because they
    are not interchangeable:

    * `SUPPLIED` — the company carries BOTH `esg_score` and an `esg_score_basis` saying where
      that number came from. The CGSI basket is this case: their real 2023 basket score, read
      from a DATED file on disk. Real, sourced, and still pure — the engine never fetches it.
    * `MOCK` — an `esg_score` with no stated basis. The fictional demo universe is this case,
      and it must keep saying so on every record.
    * `DERIVED-EVIDENCE` — no number at all, so the grounded leadership score above is used.
      That was every real name before the CGSI basket landed on 2026-08-21.

    Until then this was hard-coded `MOCK-LSEG` for all three, which was true then and would be
    a lie now. None of the three is LSEG's published score: `lseg.py` fetches the genuine
    article live, on its own 0-5 scale, and it is never mixed in here."""
    score = metrics.num(company.get("esg_score"))
    if score is not None:
        if str(company.get("esg_score_basis") or "").strip():
            return float(score), "stored_esg_score", "SUPPLIED"
        return float(score), "stored_esg_score", "MOCK"
    if company.get("esg_basis"):
        return (float(metrics.evidence_profile(company)["score"]),
                "evidence_leadership_score", "DERIVED-EVIDENCE")
    return None, "unavailable", "UNAVAILABLE"


def label_for(record, cfg):
    """CGSI quadrant label (A1), evaluated in config order so `hidden_winners` wins overlaps.
    Reads ONLY fields stored on the record — the label is always reproducible from it."""
    theta = cfg["theta"]
    d = record["disagreement"]
    conf = record["composite_confidence"]
    n = record["signal_count"]
    p = record["lseg_percentile"]
    m = record["composite_momentum"]
    hw = cfg["labels"]["hidden_winners"]
    for key in engine_config.label_order(cfg):
        if key == "hidden_winners":
            if (d >= engine_config.threshold(cfg, hw["min_disagreement"])
                    and conf >= hw["min_confidence"] and n >= hw["min_signal_count"]):
                return key
        elif key == "future_leaders" and p >= 0.5 and m > 0:
            return key
        elif key == "overrated_leaders" and p >= 0.5 and m < 0:
            return key
        elif key == "value_traps" and p < 0.5 and m < 0:
            return key
    return "consensus"
    # NOTE: `disagreement` is SIGNED (our percentile minus the rating's), so "disagreement >=
    # theta" reads exactly as the spec writes it — we are materially MORE positive than the
    # rating — and a deteriorating high-rated name (Top Glove) can never fall into Hidden
    # Winners on the strength of the gap alone.


# --------------------------------------------------------------------------- #
#  tiers (A5) — derived at RUNTIME from the record + the metadata CSV row
# --------------------------------------------------------------------------- #
def tier_match(record, meta, tier_key, cfg):
    """Does this company match one risk tier? `meta` is a metadata row (A3) or {}.

    Missing metadata is NOT a match — a tier that leans on green-bond status or profitability
    cannot be honestly evaluated without them, and guessing would be fabrication."""
    rules = cfg["risk_tiers"].get(tier_key) or {}
    meta = meta or {}
    status = (meta.get("green_bond_status") or "").strip().lower()
    profitability = (meta.get("profitability_flag") or "").strip().lower()

    if "green_bond_status_in" in rules and status not in rules["green_bond_status_in"]:
        return False
    if "profitability_in" in rules and profitability not in rules["profitability_in"]:
        return False
    if rules.get("require_traction") and str(meta.get("traction_flag", "")).strip().lower() \
            not in ("y", "yes", "true", "1"):
        return False
    if "min_confidence" in rules and record["composite_confidence"] < rules["min_confidence"]:
        return False
    if "min_disagreement" in rules and record["disagreement"] < engine_config.threshold(
            cfg, rules["min_disagreement"]):
        return False
    if "min_momentum_exclusive" in rules and record["composite_momentum"] <= rules[
            "min_momentum_exclusive"]:
        return False
    return True


def apply_tiers(record, meta, cfg=None):
    """Stamp `tiers: {conservative, balanced, aggressive}` onto a record (in place, returned)."""
    cfg = cfg or engine_config.load()
    record["tiers"] = {k: tier_match(record, meta, k, cfg)
                       for k in ("conservative", "balanced", "aggressive")}
    return record


# --------------------------------------------------------------------------- #
#  the run
# --------------------------------------------------------------------------- #
def _company_id(company: Dict[str, Any]) -> str:
    return company.get("ticker") or company.get("company_id") or company.get("company") or "unknown"


def _metadata_hash(metadata: Optional[Dict[str, Any]]) -> str:
    """Stable digest of the tier metadata — an INPUT to the run, so it belongs in the run_id.

    The Phase B1 swap is a file, not a code change: drop the verified CSV in and the tier flags
    move. If the id ignored that, the swapped run would collide with the provisional one and a
    warm cache would serve the OLD tiers under the same id — and `anchor.py` would hold one
    root for two different evidence sets. `None` (tiers not stamped at all) is deliberately
    distinct from `{}` (metadata supplied, no rows matched)."""
    if metadata is None:
        return "none"
    return hashlib.sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), default=str)
        .encode("utf-8")).hexdigest()[:16]


def _prepare_signals(companies, cfg, cutoff):
    """Extract signals and apply the historical cutoff before cohort scoring."""
    by_company, dropped = {}, 0
    for company in companies:
        cid = _company_id(company)
        signals = signal_lib.from_company(company, config=cfg)
        if cutoff:
            kept = [s for s in signals if not s.get("published_at") or s["published_at"] < cutoff]
            dropped += len(signals) - len(kept)
            signals = kept
        by_company[cid] = signals
    return by_company, dropped


def _build_records(companies, sigs_by_company, cfg, as_of, cutoff, metadata, run_id):
    """Build sorted records from frozen signals; kept separate to protect determinism."""
    aggregates, baselines, bases, origins = [], [], [], []
    for company in companies:
        cid = _company_id(company)
        aggregates.append(_aggregate(sigs_by_company[cid], cfg, as_of))
        score, basis, origin = _baseline_score(company)
        baselines.append(score)
        bases.append(basis)
        origins.append(origin)
    known = [score for score in baselines if score is not None]
    base_ranks = dict(zip([i for i, score in enumerate(baselines) if score is not None],
                          _percentiles(known)))
    mom_ranks = _percentiles([aggregate["composite_momentum"] for aggregate in aggregates])
    records = []
    for i, company in enumerate(companies):
        cid = _company_id(company)
        aggregate = aggregates[i]
        lseg_p, mom_p = round(base_ranks.get(i, 0.5), 6), mom_ranks[i]
        record = {
            "run_id": run_id, "company_id": cid, "company": company.get("company", cid),
            "sector": company.get("sector", "unknown"), "country": company.get("country", "unknown"),
            # Basket facts carried onto the record so every downstream screen reads ONE object.
            # `delisted` is CGSI's own note (MAHB, INTUCH): the row stays, but it is excluded
            # from investable output and badged, because a stale basket member is a finding.
            "industry": company.get("industry", company.get("sector", "unknown")),
            "delisted": bool(company.get("delisted")),
            "high_conviction": bool(company.get("high_conviction")),
            # The notch grade carried in the basket (BBB / BB / B). CGSI's own column, whose
            # header reads "ESG Rating" with NO agency named, so it travels unattributed and is
            # never called anyone's — see `scripts/build_cgsi_basket.py`. It is displayed, not
            # scored: `baseline_score` is the numeric ESG score, and letting a second incumbent
            # measure into the maths would be two rulers in one number.
            "incumbent_notch": str(company.get("incumbent_notch") or ""),
            "as_of": as_of, "cutoff": cutoff or "", "signal_count": len(sigs_by_company[cid]),
            "signal_ids": [s["signal_id"] for s in sigs_by_company[cid]],
            "composite_momentum": aggregate["composite_momentum"],
            "composite_confidence": aggregate["composite_confidence"],
            "direction_consensus": aggregate["direction_consensus"],
            "evidence_weight": aggregate["evidence_weight"], "shrinkage": aggregate["shrinkage"],
            "coverage": aggregate["coverage"], "mean_source_quality": aggregate["mean_source_quality"],
            "breadth": aggregate["breadth"], "corroboration": aggregate["corroboration"],
            "components": aggregate["components"], "subcomponents": aggregate["subcomponents"],
            "baseline_score": baselines[i], "baseline_basis": bases[i], "baseline_origin": origins[i],
            "lseg_percentile": lseg_p, "momentum_percentile": mom_p,
            "disagreement": round(mom_p - lseg_p, 6), "disagreement_abs": round(abs(mom_p - lseg_p), 6),
            "signals": sigs_by_company[cid],
        }
        record["label"] = label_for(record, cfg)
        record["label_display"] = engine_config.display(cfg, record["label"])
        if metadata is not None:
            apply_tiers(record, (metadata or {}).get(cid, {}), cfg)
        records.append(record)
    records.sort(key=lambda record: record["company_id"])
    return records


def run_engine(company_list: List[Dict[str, Any]], *, config: Optional[Dict[str, Any]] = None,
               as_of: Optional[str] = None, cutoff: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None, use_cache: bool = True,
               cache_dir: Optional[str] = None) -> Dict[str, Any]:
    """Score a list of company records. Returns a run dict:

        {run_id, engine_version, config_version, config_hash, as_of, cutoff,
         company_count, records: [...], labels: {key: display}}

    Same inputs -> byte-identical output, cached under `.cache/engine/<run_id>.json`.

    `cutoff` (ISO date) drops every signal published on or after it — the backtest lookback
    freeze. `metadata` is `{company_id: row}` from `company_metadata.py`; when present the tier
    flags are stamped in the run, otherwise `apply_tiers` can do it later at runtime."""
    cfg = config or engine_config.load()
    companies = [c for c in (company_list or []) if isinstance(c, dict)]

    sigs_by_company, dropped = _prepare_signals(companies, cfg, cutoff)

    as_of = as_of or _as_of_from(companies, sigs_by_company)
    if cutoff and (not as_of or as_of >= cutoff):
        as_of = cutoff          # never decay against a date the lookback isn't allowed to see

    metadata_hash = _metadata_hash(metadata)
    run_id = hashlib.sha256("|".join([
        cfg["engine_version"], cfg["config_hash"], as_of or "", cutoff or "", metadata_hash,
        *(f"{cid}:{','.join(s['signal_id'] for s in sigs)}"
          for cid, sigs in sorted(sigs_by_company.items())),
    ]).encode("utf-8")).hexdigest()[:16]

    cache_path = os.path.join(cache_dir or CACHE_DIR, f"{run_id}.json")
    if use_cache:
        cached = _read_cache(cache_path)
        if cached:
            return cached

    records = _build_records(companies, sigs_by_company, cfg, as_of, cutoff, metadata, run_id)
    run = {
        "run_id": run_id,
        "engine_version": cfg["engine_version"], "record_schema": RECORD_SCHEMA,
        "extractor_version": signal_lib.EXTRACTOR_VERSION,
        "config_version": cfg["config_version"],
        "config_hash": cfg["config_hash"],
        "metadata_hash": metadata_hash,   # which metadata file this run's tiers came from
        "as_of": as_of,
        "cutoff": cutoff or "",
        "signals_dropped_by_cutoff": dropped,
        "company_count": len(records),
        "signal_count": sum(r["signal_count"] for r in records),
        "labels": {k: engine_config.display(cfg, k) for k in engine_config.label_order(cfg)},
        "records": records,
    }
    if use_cache:
        _write_cache(cache_path, run)
    return run


def enforce_cutoff(run: Dict[str, Any], cutoff: Optional[str] = None) -> Dict[str, Any]:
    """Fail LOUDLY if any signal in a run was published on/after the cutoff (A8).

    Called by the harness after every backtest run; the filter inside `run_engine` should make
    this impossible, which is exactly why it is asserted rather than assumed."""
    cutoff = cutoff or run.get("cutoff")
    if not cutoff:
        return run
    bad = [(r["company_id"], s["signal_id"], s["published_at"], s["raw_text"][:70])
           for r in run["records"] for s in r["signals"]
           if s.get("published_at") and s["published_at"] >= cutoff]
    if bad:
        lines = "\n".join(f"    {cid} {sid} {when} — {text}" for cid, sid, when, text in bad[:10])
        raise CutoffViolation(
            f"LOOKAHEAD: {len(bad)} signal(s) at/after cutoff {cutoff} reached the run:\n{lines}")
    return run


def record_for(run: Dict[str, Any], company_id: str) -> Optional[Dict[str, Any]]:
    """One record by company id, or None."""
    for r in run.get("records", []):
        if r["company_id"] == company_id:
            return r
    return None


def label_counts(run: Dict[str, Any]) -> Dict[str, int]:
    """{label_key: n} across a run — the matrix legend's counts."""
    out = {}
    for r in run.get("records", []):
        out[r["label"]] = out.get(r["label"], 0) + 1
    return out


# --------------------------------------------------------------------------- #
#  cache (a run is immutable — its id hashes EVERY input, config and metadata included,
#  so a hit is always valid; add an input here and it must go into the id too)
# --------------------------------------------------------------------------- #
def _read_cache(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            run = json.load(fh)
    except (OSError, ValueError):
        return None
    # Same id, older record shape -> recompute. See RECORD_SCHEMA.
    if run.get("record_schema") != RECORD_SCHEMA:
        return None
    return run


def _write_cache(path, run):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(run, fh, sort_keys=True, separators=(",", ":"))
    except OSError:
        pass          # a read-only disk must never break a run (best-effort, like retrieval)


def digest(run: Dict[str, Any]) -> str:
    """A stable content digest of a run — the determinism test compares these."""
    return hashlib.sha256(
        json.dumps(run, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
