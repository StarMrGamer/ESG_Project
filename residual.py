"""THE 10% TEST — does our ESG evidence explain what a factor model cannot?

READ THE SPECIFICATION BEFORE THE RESULT. IT WAS WRITTEN FIRST, DELIBERATELY.
----------------------------------------------------------------------------
The pitch-shaped claim behind this module is that a Fama-French style factor model explains most
of the cross-section of returns and leaves a residual — "the 10%" — and that dated ESG evidence,
which no factor model carries, is one of the things living in there.

`forecast.py` could never answer that. It puts the market factors and our ESG features into ONE
pooled regression, so the incremental contribution of the ESG block is never isolated: a model
with no skill overall tells you nothing about whether one of its blocks earned its place. This
module asks the question in the only form that can answer it — TWO STAGES:

    stage 1   target  ~  factor block            ->  fitted, then residuals
    stage 2   residual ~ ESG block               ->  incremental skill, out of sample

and reports what stage 1 itself explained, so the "90/10" split is MEASURED on this panel rather
than assumed from the literature.

WHAT THE FACTOR BLOCK IS, AND WHY THE ANSWER IS BIASED IN OUR FAVOUR
--------------------------------------------------------------------
Stage 1 can only use the factors this repo can legally source (see `forecast.FACTORS_MISSING`):
MKT (beta to the equal-weighted cohort), WML (12-1), VOL and an RMW-proxy. **SMB and HML are
absent.** A weaker stage-1 model leaves a BIGGER residual, and a bigger residual is EASIER for
stage 2 to explain. So this test is tilted toward the answer we would like, and any negative
result is therefore stronger than it looks, and any positive one weaker. That asymmetry is the
first thing to say out loud about any number below.

WHAT THE ESG BLOCK IS, AND THE TWO THINGS DELIBERATELY LEFT OUT OF IT
---------------------------------------------------------------------
`momentum` (ESG evidence direction consensus), `evidence` (log signal count), and the PPP
`planet` and `people` shares. Two exclusions, both for reasons that have nothing to do with the
result:

  * **PPP `profit` is not in the ESG block** — it is |12-1 price momentum| over a fixed scale
    (`ppp.BASIS`), i.e. a transform of the WML factor stage 1 has just removed. Letting it back in
    at stage 2 would let the ESG block re-explain a factor we are supposed to be controlling for,
    and would produce exactly the false positive this whole module exists to avoid.
  * **The three PPP shares sum to 1**, so with an intercept they are perfectly collinear and the
    normal equations are rank-deficient. Ridge hides that numerically rather than fixing it.
    Dropping one as the reference category is the standard treatment of compositional data, and
    the one to drop is the one that is also a leak.

THE PRIMARY SPECIFICATION, FIXED BEFORE THE FIRST RUN
------------------------------------------------------
`SPEC_PRIMARY` below: cross-sectionally demeaned, 6-month horizon, 0.6 train fraction. The
horizon and split match `forecast.py`'s frozen model so the two are comparable. The demeaning is
the substantive choice and the argument for it is a priori:

    A factor model prices the CROSS-SECTION — which names beat which. The common return of the
    whole cohort in a given period is a market move, is not predictable from any of these
    features by construction, and on raw returns it dominates the variance. Testing on raw
    returns therefore grades a cross-sectional question with a market-timing scorecard. Demeaning
    per cutoff removes the period effect and leaves the question actually being asked.

Every other cell of the grid is reported too — 3 specs x 3 horizons x 3 splits — for the same
reason `forecast.py` freezes its sweep: so that no future session can run the grid, pick the cell
it likes and ship that one. A result is only quotable with its spec attached.

WHY THE HEADLINE STATISTIC IS THE IC AND NOT R^2
-------------------------------------------------
Pooled R^2 on fat-tailed 6-month returns is decided by a handful of outliers, and a single
blow-up can flip it. The information coefficient — the rank correlation between the stage-2
prediction and the actual residual, computed WITHIN each test cutoff and then averaged across
cutoffs — is the standard factor-research statistic and is what a cross-sectional claim should be
graded on. Its t-statistic is reported beside it and is WEAK BY CONSTRUCTION here: there are five
test cutoffs, and 6-month returns sampled quarterly overlap, so the effective count is smaller
still. A t-stat on five overlapping observations is a direction of travel, not an inference.

Pure Python, no new dependency, no RNG, no clock. Nothing in `engine.py` or `signals.py` can
import this and `selftest.py` pins that, exactly as it does for `forecast.py`.
"""
import json
import os

import forecast

_ROOT = os.path.dirname(os.path.abspath(__file__))
RESULT_JSON = os.path.join(_ROOT, "data", "residual_test.json")

#: Stage 1 — the factors, such as we can source them. SMB and HML are absent; see the header.
FACTOR_BLOCK = ("beta", "price_mom", "vol", "prof")

#: Stage 2 — what a factor model does not carry. PPP `profit` is excluded; see the header.
ESG_BLOCK = ("momentum", "evidence", "planet", "people")

BLOCK_LABEL = {
    "beta": "MKT · beta to the equal-weighted cohort",
    "price_mom": "WML · 12-1 momentum factor",
    "vol": "VOL · realised volatility, trailing 12m",
    "prof": "RMW-proxy · profitability from two audited years",
    "momentum": "ESG evidence momentum (direction consensus)",
    "evidence": "Evidence depth (log signal count)",
    "planet": "PPP · Planet share of movement",
    "people": "PPP · People share of movement",
}

#: The specifications swept. `xs` is primary — the argument is in the header, and it was written
#: before the first run.
SPECS = ("raw", "xs", "xs_winsor")
SPEC_NOTE = {
    "raw": "Raw forward returns, pooled. Includes the common market move, which no feature here "
           "can predict — reported for completeness, not as the test.",
    "xs": "Cross-sectionally demeaned per cutoff: the period's cohort mean is removed from the "
          "target and from every feature, so what is graded is relative ranking.",
    "xs_winsor": "As `xs`, with the target winsorised at the 5th/95th percentile WITHIN each "
                 "cutoff before demeaning, so a single blow-up cannot decide R^2.",
}
SPEC_PRIMARY = "xs"
HORIZONS_PRIMARY = 6
TRAIN_FRACTION_PRIMARY = 0.6

HORIZONS = (3, 6, 12)
TRAIN_FRACTIONS = (0.5, 0.6, 0.7)

BIAS_NOTE = (
    "Stage 1 is missing SMB and HML, so it under-explains and leaves a larger residual than a "
    "full Fama-French model would. That makes stage 2's job EASIER: a negative result here is "
    "stronger than it looks, and a positive one is weaker."
)

SAMPLE_CAVEAT = forecast.SAMPLE_CAVEAT

NOT_ADVICE = (
    "A measurement of whether one block of features explains the part of returns another block "
    "does not. It is not a forecast, not a recommendation, and not a claim that any company "
    "will do anything."
)


# --------------------------------------------------------------------------- #
#  small statistics, in pure Python
# --------------------------------------------------------------------------- #
def _mean(v):
    return sum(v) / len(v) if v else 0.0


def _ranks(v):
    """Average ranks, ties shared — Spearman needs the tie correction or a flat feature scores."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def spearman(a, b):
    """Rank correlation. None when either side is constant — undefined, never 0."""
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = _mean(ra), _mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    if da < 1e-12 or db < 1e-12:
        return None
    return num / (da * db)


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = (len(sorted_vals) - 1) * q
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _r2(actual, pred, base):
    """R^2 against a stated baseline prediction, not against zero. Returns None if degenerate."""
    ss_base = sum((a - base) ** 2 for a in actual)
    if ss_base <= 0:
        return None
    ss_res = sum((a - p) ** 2 for a, p in zip(actual, pred))
    return 1.0 - ss_res / ss_base


# --------------------------------------------------------------------------- #
#  the specification transforms
# --------------------------------------------------------------------------- #
def apply_spec(rows, spec):
    """Return a NEW row list transformed per `spec`. The panel itself is never mutated.

    Winsorising and demeaning both happen WITHIN a cutoff. Doing either across the whole panel
    would mix periods together and leak one cutoff's distribution into another's.
    """
    if spec == "raw":
        return [dict(r) for r in rows]

    by_cut = {}
    for r in rows:
        by_cut.setdefault(r["cutoff"], []).append(r)

    out = []
    for cut in sorted(by_cut):
        group = [dict(r) for r in by_cut[cut]]
        if spec == "xs_winsor" and len(group) >= 5:
            vals = sorted(r["target"] for r in group)
            lo, hi = _percentile(vals, 0.05), _percentile(vals, 0.95)
            for r in group:
                r["target"] = min(hi, max(lo, r["target"]))
        keys = ("target",) + FACTOR_BLOCK + ESG_BLOCK
        for k in keys:
            m = _mean([r[k] for r in group])
            for r in group:
                r[k] = r[k] - m
        out.extend(group)
    return out


def split(rows, train_fraction):
    """Split by CUTOFF, never by row — the same discipline as `forecast.train`."""
    months = sorted({r["cutoff"] for r in rows})
    if len(months) < 4:
        return None, None, months
    edge = max(1, int(len(months) * train_fraction))
    train_months, test_months = set(months[:edge]), set(months[edge:])
    tr = [r for r in rows if r["cutoff"] in train_months]
    te = [r for r in rows if r["cutoff"] in test_months]
    return tr, te, months


# --------------------------------------------------------------------------- #
#  one block, fitted on train and applied out of sample
# --------------------------------------------------------------------------- #
def _fit_block(tr, te, keys, target_tr, target_te, lam=forecast.RIDGE_LAMBDA):
    """Fit ridge on the train rows for `keys` against `target_tr`; predict both sides.

    Standardisation stats come from TRAIN ONLY, per `forecast._standardise` — the same leak this
    repo already guards against one module over.
    """
    xtr, stats = forecast._standardise(tr, keys)
    fitted = forecast.fit_ridge(xtr, target_tr, lam)
    if fitted is None:
        return None
    intercept, coef = fitted
    xte, _ = forecast._standardise(te, keys, stats)
    return {
        "intercept": intercept,
        "coef": dict(zip(keys, coef)),
        "pred_train": [forecast._apply(intercept, coef, row) for row in xtr],
        "pred_test": [forecast._apply(intercept, coef, row) for row in xte],
    }


def _ic_by_cutoff(rows, actual, pred):
    """Rank IC computed WITHIN each cutoff, then the series across cutoffs.

    Pooling every test row into one correlation would let cross-period level differences stand in
    for cross-sectional skill, which is the same mistake as not demeaning.
    """
    by_cut = {}
    for r, a, p in zip(rows, actual, pred):
        by_cut.setdefault(r["cutoff"], []).append((a, p))
    series = []
    for cut in sorted(by_cut):
        pairs = by_cut[cut]
        ic = spearman([p for _, p in pairs], [a for a, _ in pairs])
        if ic is not None:
            series.append({"cutoff": cut, "ic": round(ic, 4), "n": len(pairs)})
    if not series:
        return {"series": [], "mean": None, "sd": None, "t_stat": None, "cutoffs": 0}
    vals = [s["ic"] for s in series]
    m = _mean(vals)
    if len(vals) > 1:
        var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
        sd = var ** 0.5
        t = m / (sd / len(vals) ** 0.5) if sd > 1e-12 else None
    else:
        sd, t = None, None
    return {
        "series": series,
        "mean": round(m, 4),
        "sd": round(sd, 4) if sd is not None else None,
        "t_stat": round(t, 3) if t is not None else None,
        "cutoffs": len(vals),
    }


# --------------------------------------------------------------------------- #
#  THE TEST
# --------------------------------------------------------------------------- #
def run_test(rows, spec=SPEC_PRIMARY, train_fraction=TRAIN_FRACTION_PRIMARY,
             lam=forecast.RIDGE_LAMBDA):
    """Two stages, graded out of sample. Returns the full result dict or a `ran: False` reason."""
    data = apply_spec(rows, spec)
    tr, te, months = split(data, train_fraction)
    if not tr or not te:
        return {"ran": False, "why": f"only {len(months)} usable cutoffs — too few to split"}

    ytr = [r["target"] for r in tr]
    yte = [r["target"] for r in te]

    # -- stage 1: the factor model, i.e. "the 90%" ---------------------------- #
    s1 = _fit_block(tr, te, FACTOR_BLOCK, ytr, yte, lam)
    if s1 is None:
        return {"ran": False, "why": "stage 1 normal equations were singular"}
    base_tr = _mean(ytr)
    stage1_r2 = _r2(yte, s1["pred_test"], base_tr)

    # Residuals. Train residuals are in-sample by construction — that is what stage 2 must be
    # fitted on, since the whole point is to model what stage 1 left over on data stage 1 saw.
    res_tr = [a - p for a, p in zip(ytr, s1["pred_train"])]
    res_te = [a - p for a, p in zip(yte, s1["pred_test"])]

    # -- stage 2: the ESG block on the residual, i.e. "the 10%" --------------- #
    s2 = _fit_block(tr, te, ESG_BLOCK, res_tr, res_te, lam)
    if s2 is None:
        return {"ran": False, "why": "stage 2 normal equations were singular"}
    res_base = _mean(res_tr)
    incremental_r2 = _r2(res_te, s2["pred_test"], res_base)
    ic = _ic_by_cutoff(te, res_te, s2["pred_test"])

    # -- the ablation, as a cross-check on the two-stage result --------------- #
    # Same question asked a second way: fit ONE model on both blocks and one on the factors
    # alone, and compare out-of-sample error. If the ESG block carries anything, the joint model
    # beats the factor-only model here as well as clearing the two-stage test.
    joint = _fit_block(tr, te, FACTOR_BLOCK + ESG_BLOCK, ytr, yte, lam)
    ablation = None
    if joint is not None:
        r2_joint = _r2(yte, joint["pred_test"], base_tr)
        mae_f = _mean([abs(a - p) for a, p in zip(yte, s1["pred_test"])])
        mae_j = _mean([abs(a - p) for a, p in zip(yte, joint["pred_test"])])
        ablation = {
            "r2_factors_only": round(stage1_r2, 4) if stage1_r2 is not None else None,
            "r2_with_esg": round(r2_joint, 4) if r2_joint is not None else None,
            "delta_r2": (round(r2_joint - stage1_r2, 4)
                         if (r2_joint is not None and stage1_r2 is not None) else None),
            "mae_factors_only": round(mae_f, 3),
            "mae_with_esg": round(mae_j, 3),
            "esg_helps_mae": bool(mae_j < mae_f),
        }

    return {
        "ran": True,
        "spec": spec,
        "spec_note": SPEC_NOTE[spec],
        "train_fraction": train_fraction,
        "train": {"cutoffs": sorted({r["cutoff"] for r in tr}), "rows": len(tr)},
        "test": {"cutoffs": sorted({r["cutoff"] for r in te}), "rows": len(te)},
        "stage1": {
            "block": list(FACTOR_BLOCK),
            "r2_oos": round(stage1_r2, 4) if stage1_r2 is not None else None,
            "coefficients": {k: round(v, 6) for k, v in s1["coef"].items()},
            "residual_share": (round(max(0.0, 1.0 - stage1_r2), 4)
                               if stage1_r2 is not None else None),
        },
        "stage2": {
            "block": list(ESG_BLOCK),
            "incremental_r2_oos": round(incremental_r2, 4) if incremental_r2 is not None else None,
            "coefficients": {k: round(v, 6) for k, v in s2["coef"].items()},
            "ic": ic,
        },
        "ablation": ablation,
    }


def verdict(result):
    """Did the ESG block explain any of the residual? One word plus the reason. Rule-based.

    The bar is fixed here rather than at the call site so it cannot be softened per-caller: BOTH
    a positive out-of-sample incremental R^2 AND a positive mean IC carrying |t| >= 2. One of the
    two alone is what noise produces about half the time, which is the same standard
    `forecast.verdict` already applies to its two baselines.
    """
    if not result or not result.get("ran"):
        return {"word": "not run", "line": (result or {}).get("why", "The test has not been run.")}
    inc = result["stage2"]["incremental_r2_oos"]
    ic = result["stage2"]["ic"]
    mean_ic, t = ic.get("mean"), ic.get("t_stat")
    r2_ok = inc is not None and inc > 0
    ic_ok = mean_ic is not None and mean_ic > 0 and t is not None and abs(t) >= 2.0
    ic_lean = mean_ic is not None and mean_ic > 0 and t is not None and abs(t) >= 1.5

    if r2_ok and ic_ok:
        return {"word": "explains part of the residual",
                "line": "The ESG block improves on the factor model's leftovers out of sample, "
                        "on both error and rank. On this sample that is weak evidence, not "
                        "validated alpha — and stage 1 is missing SMB and HML, which flatters it."}
    if r2_ok or ic_lean:
        return {"word": "marginal",
                "line": "One of the two tests is positive and the other is not, which is what an "
                        "unskilled block does roughly half the time. It is not evidence that the "
                        "residual has been explained."}
    return {"word": "no measurable contribution",
            "line": "The ESG block does not explain the part of returns the factor model leaves "
                    "over — on this panel, out of sample. The evidence layer is still measuring "
                    "something the rating cannot see; what it is NOT doing is predicting the "
                    "residual return, and that distinction is the finding."}


def sweep(verbose=False):
    """Every spec x horizon x split, all reported. No cell is privileged except the declared one.

    The panel is rebuilt once per horizon (the cutoff list and the forward return both depend on
    it) and reused across specs and splits.
    """
    grid = []
    for horizon in HORIZONS:
        rows = forecast.build_panel(horizon=horizon)
        if verbose:
            print(f"  horizon {horizon}m — {len(rows)} rows, "
                  f"{len({r['cutoff'] for r in rows})} cutoffs")
        for spec in SPECS:
            for frac in TRAIN_FRACTIONS:
                r = run_test(rows, spec=spec, train_fraction=frac)
                if not r.get("ran"):
                    continue
                grid.append({
                    "spec": spec,
                    "horizon_months": horizon,
                    "train_fraction": frac,
                    "rows": len(rows),
                    "stage1_r2_oos": r["stage1"]["r2_oos"],
                    "incremental_r2_oos": r["stage2"]["incremental_r2_oos"],
                    "mean_ic": r["stage2"]["ic"]["mean"],
                    "ic_t_stat": r["stage2"]["ic"]["t_stat"],
                    "delta_r2": (r["ablation"] or {}).get("delta_r2"),
                    "verdict": verdict(r)["word"],
                })
    return grid


def summarise_by_horizon(grid):
    """Collapse the grid to one row per horizon: how many specs survived, and how strongly.

    A flat "6 of 27 configurations" hides the only thing that distinguishes a robust effect from
    a lucky cell — WHERE the hits are. Six hits spread across three horizons is noise; six hits
    that are every single cell at one horizon is a horizon-specific effect, which is a real
    finding AND a real caveat.
    """
    rows = {}
    for g in grid:
        h = g["horizon_months"]
        b = rows.setdefault(h, {"horizon_months": h, "cells": 0, "positive_verdict": 0,
                                "mean_ic_positive": 0, "ic_t_at_least_2": 0, "ics": []})
        b["cells"] += 1
        if g["verdict"] == "explains part of the residual":
            b["positive_verdict"] += 1
        if (g["mean_ic"] or 0) > 0:
            b["mean_ic_positive"] += 1
        if abs(g["ic_t_stat"] or 0) >= 2.0 and (g["mean_ic"] or 0) > 0:
            b["ic_t_at_least_2"] += 1
        if g["mean_ic"] is not None:
            b["ics"].append(g["mean_ic"])
    out = []
    for h in sorted(rows):
        b = rows[h]
        ics = b.pop("ics")
        b["mean_ic_across_specs"] = round(_mean(ics), 4) if ics else None
        out.append(b)
    return out


def _horizon_note(by_horizon):
    """State in one sentence what shape the grid actually has. Rule-derived, not editorial."""
    # "Concentrated" means ONE horizon where every specification clears, and a MINORITY of
    # specifications clearing at each of the others. Stated as a shape rule rather than a
    # threshold picked off this grid: requiring the other horizons to be exactly zero would call
    # 9-of-9 against 2-of-9 "scattered", which is not what scattered means.
    clean = [b for b in by_horizon if b["cells"] and b["ic_t_at_least_2"] == b["cells"]]
    weak = [b for b in by_horizon if b["cells"] and b["ic_t_at_least_2"] * 2 < b["cells"]]
    if len(clean) == 1 and len(weak) == len(by_horizon) - 1:
        h = clean[0]["horizon_months"]
        return (f"Every specification at the {h}-month horizon clears the IC test, and at every "
                f"other horizon a minority do. That is robust to the specification and confined "
                f"to one "
                f"horizon — which is a real finding and a real limitation in the same sentence. "
                f"An effect present at one horizon only is not yet distinguishable from a "
                f"horizon-shaped artefact of a 3-year panel, and it should be quoted with the "
                f"horizon attached, never as 'the model works'.")
    if not any(b["ic_t_at_least_2"] for b in by_horizon):
        return ("No horizon clears the IC test under any specification.")
    return ("The hits are spread across horizons rather than concentrated in one. Scattered hits "
            "at this sample size are what noise looks like; treat them as such.")


def build(verbose=False):
    """Run the primary specification and the full grid, and return the frozen-file payload."""
    rows = forecast.build_panel(horizon=HORIZONS_PRIMARY, verbose=verbose)
    primary = run_test(rows, spec=SPEC_PRIMARY, train_fraction=TRAIN_FRACTION_PRIMARY)
    grid = sweep(verbose=verbose)
    positive = [g for g in grid if g["verdict"] == "explains part of the residual"]
    by_horizon = summarise_by_horizon(grid)
    return {
        "built_at": "",  # stamped by the CLI, which is the only thing here allowed a clock
        "question": "Does the ESG evidence block explain the part of forward returns that the "
                    "factor block does not?",
        "primary_spec": SPEC_PRIMARY,
        "spec_declared_before_run": True,
        "factor_block": {k: BLOCK_LABEL[k] for k in FACTOR_BLOCK},
        "esg_block": {k: BLOCK_LABEL[k] for k in ESG_BLOCK},
        "factors_missing": forecast.FACTORS_MISSING,
        "excluded_from_esg_block": {
            "profit": "PPP Profit share is |12-1 price momentum| rescaled — a transform of the "
                      "WML factor stage 1 removes. Re-entering it at stage 2 would let the ESG "
                      "block re-explain a controlled factor.",
        },
        "bias_note": BIAS_NOTE,
        "companies": len({r["company_id"] for r in rows}),
        "rows": len(rows),
        "result": primary,
        "verdict": verdict(primary),
        "sweep": grid,
        "sweep_summary": {
            "configurations": len(grid),
            "with_contribution": len(positive),
            "by_horizon": by_horizon,
            "note": "Every configuration is recorded so that a later session cannot run the grid, "
                    "pick the cell it prefers and quote that one. A figure is only quotable with "
                    "its spec, horizon and split attached.",
            "structure_note": "Read the grid BY HORIZON, not as a flat count. A result that "
                              "survives every specification at one horizon and appears at no "
                              "other is a different animal from the same number of scattered "
                              "hits: the first is robust-but-horizon-specific, the second is "
                              "noise. Which of those this is, is stated in `horizon_note`.",
            "horizon_note": _horizon_note(by_horizon),
        },
        "sample_caveat": SAMPLE_CAVEAT,
        "not_advice": NOT_ADVICE,
    }


def frozen():
    """The frozen result, or None. Readers should prefer this over re-running the panel."""
    try:
        with open(RESULT_JSON, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
#  SOLVING FOR THE RESIDUAL — an actual predictor, developed against a sealed holdout
# --------------------------------------------------------------------------- #
#: WHY THIS SECTION EXISTS AND WHY IT IS SHAPED LIKE THIS.
#:
#: The section above MEASURES whether the ESG block explains the factor model's leftovers. This
#: one tries to PREDICT them — asked for directly, with partial credit explicitly acceptable:
#: eliminating a twentieth of the residual would be a real result.
#:
#: That ask changes the danger. Measuring once is safe; TRYING THINGS UNTIL ONE WORKS is how a
#: 5% appears out of noise, and by the time this ran the grid above had already been seen — so
#: every choice here is being made with knowledge of the data, which is exactly the condition
#: under which honest people fool themselves. Two defences, both structural rather than
#: intentional:
#:
#:   1. **A THREE-WAY SPLIT BY TIME.** Cutoffs divide into TRAIN, VALIDATION and HOLDOUT. Every
#:      model is fitted on TRAIN. Every hyperparameter — the feature transform, the ridge
#:      penalty, the shrinkage — is chosen on VALIDATION. The HOLDOUT is scored ONCE, at the end,
#:      by the single configuration validation picked. A number quoted off validation is a number
#:      chosen for being the best of many; only the holdout figure is reportable.
#:
#:   2. **THE SEARCH IS COUNTED AND PUBLISHED.** `configs_tried` rides in the frozen file beside
#:      the result. Twelve configurations searched for one positive answer is a different claim
#:      from one configuration that worked, and the reader is entitled to tell them apart.
#:
#: WHAT IS ACTUALLY NEW HERE, and each is arguable WITHOUT reference to the answer it gives:
#:
#:   * **BREADTH.** The panel is widened from the CGSI 52 to CGSI plus the ASEAN index universe.
#:     A cross-sectional factor model draws its power from the number of names compared at each
#:     date, and 41 is very few; 97 is still few, but it is not the same order of few. This is
#:     the change most likely to matter and it has nothing to do with which way the answer falls.
#:   * **RANK-TRANSFORMED FEATURES.** Within each cutoff, features are replaced by their
#:     cross-sectional ranks before standardising. Returns and evidence counts are fat-tailed and
#:     live on unrelated scales; ranks are the standard robust treatment in cross-sectional
#:     factor work, and a single outlier can otherwise set a coefficient by itself.
#:   * **A TUNED PENALTY AND AN EXPLICIT SHRINKAGE.** A low-signal regression fitted by lightly
#:     penalised least squares produces predictions that are correct in ORDER and far too large
#:     in SCALE, which is precisely how a model can hold a positive rank IC and still score a
#:     negative R². Shrinking the prediction toward the mean converts rank skill into explained
#:     variance. Both the penalty and the shrinkage are chosen on validation, never on holdout.
#:
#: WHAT THE ARITHMETIC ALLOWS, stated before the run so the result cannot be oversold. For a
#: calibrated linear prediction, explained variance is about the square of the correlation. At
#: the IC this panel showed — around 0.135 — the ceiling is roughly 1.8% of the residual. Five
#: per cent needs a correlation near 0.22. So a mid-single-digit result would be a strong outcome
#: and a one-to-two per cent result is the expected one. Neither is alpha; both are a measurement
#: on ~3 years of one regime with overlapping returns.

#: Which names the wide panel scores. Both are REAL universes; the fictional demo set is never
#: admitted, since a residual test over invented prices is not a weaker finding but not a finding.
WIDE_UNIVERSES = ("data/asean_universe.json", "data/asean_indexes.json")

#: The wide panel's factor block. RMW-proxy is DROPPED, not imputed: `forecast.profitability`
#: returns 0.0 for a company with no metadata row, and 155 of these names have none — so keeping
#: it would encode "we hold no accounts for this company" as "average profitability" for most of
#: the cohort. That is the `unknown` vs `not_met` confusion `traction.py` exists to refuse, and a
#: constant column would in any case carry no information while implying it did.
WIDE_FACTOR_BLOCK = ("beta", "price_mom", "vol")

TRAIN_FRAC, VAL_FRAC = 0.5, 0.25

#: The search space. Small and fixed — a grid enumerated in the source is a search whose size the
#: reader can count, which is the whole point of publishing `configs_tried`.
TRANSFORMS = ("z", "rank")
LAMBDAS = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
SHRINKS = (0.25, 0.5, 0.75, 1.0)


def wide_constituents():
    """CGSI's basket plus the index universe, de-duplicated, first file winning on a clash."""
    import universe as _u
    seen, out, as_of = set(), [], ""
    for path in WIDE_UNIVERSES:
        uni = _u.load_universe(os.path.join(_ROOT, path))
        as_of = as_of or (uni.get("as_of") or "")
        for c in uni["constituents"]:
            if c["ticker"] not in seen:
                seen.add(c["ticker"])
                out.append(c)
    return out, as_of


def build_wide_panel(horizon=HORIZONS_PRIMARY, verbose=False):
    cons, as_of = wide_constituents()
    return forecast.build_panel(horizon=horizon, constituents=cons, as_of=as_of, verbose=verbose)


def rank_features(rows, keys):
    """Replace each feature by its cross-sectional rank within its cutoff, scaled to [-0.5, 0.5].

    Per cutoff, never pooled: a rank taken across dates would encode which period a row came
    from, which is the same leak demeaning exists to remove.
    """
    by_cut = {}
    for r in rows:
        by_cut.setdefault(r["cutoff"], []).append(r)
    out = []
    for cut in sorted(by_cut):
        group = [dict(r) for r in by_cut[cut]]
        n = len(group)
        for k in keys:
            rk = _ranks([r[k] for r in group])
            for r, v in zip(group, rk):
                r[k] = (v - (n + 1) / 2.0) / n if n > 1 else 0.0
        out.extend(group)
    return out


def three_way(rows, train_frac=TRAIN_FRAC, val_frac=VAL_FRAC):
    """Split the CUTOFFS into train / validation / holdout, in time order. Never by row."""
    months = sorted({r["cutoff"] for r in rows})
    n = len(months)
    if n < 6:
        return None
    a = max(1, int(round(n * train_frac)))
    b = max(a + 1, int(round(n * (train_frac + val_frac))))
    if b >= n:
        return None
    return months[:a], months[a:b], months[b:]


def _stage_pair(tr, ev, factor_block, esg_block, lam, shrink):
    """Fit stage 1 and stage 2 on `tr`, and return predictions + actual residual for `ev`.

    Both stages are fitted on TRAIN only. `ev` is whichever set is being scored — validation
    while searching, holdout exactly once at the end — and nothing about it touches the fit.
    """
    ytr = [r["target"] for r in tr]
    yev = [r["target"] for r in ev]
    s1 = _fit_block(tr, ev, factor_block, ytr, yev, lam=forecast.RIDGE_LAMBDA)
    if s1 is None:
        return None
    res_tr = [a - p for a, p in zip(ytr, s1["pred_train"])]
    res_ev = [a - p for a, p in zip(yev, s1["pred_test"])]
    s2 = _fit_block(tr, ev, esg_block, res_tr, res_ev, lam=lam)
    if s2 is None:
        return None
    base = _mean(res_tr)
    # Shrink TOWARD the training-residual mean, which is the baseline R^2 is measured against.
    pred = [base + shrink * (p - base) for p in s2["pred_test"]]
    return {"residual": res_ev, "pred": pred, "base": base,
            "stage1_r2": _r2(yev, s1["pred_test"], _mean(ytr)),
            "coef": s2["coef"]}


def _score(out, rows):
    r2 = _r2(out["residual"], out["pred"], out["base"])
    ic = _ic_by_cutoff(rows, out["residual"], out["pred"])
    return {"residual_r2": round(r2, 5) if r2 is not None else None,
            "share_of_residual_pct": round(r2 * 100, 3) if r2 is not None else None,
            "mean_ic": ic.get("mean"), "ic_t_stat": ic.get("t_stat"),
            "ic_cutoffs": ic.get("cutoffs"), "ic_series": ic.get("series")}


def solve(rows, factor_block, esg_block, verbose=False):
    """Search on validation, then score the holdout ONCE with what validation chose."""
    split = three_way(rows)
    if split is None:
        return {"ran": False, "why": "too few cutoffs for a three-way split"}
    tr_m, va_m, ho_m = split
    base_rows = apply_spec(rows, "xs")          # the declared primary target treatment

    searched, best = [], None
    for transform in TRANSFORMS:
        keys = tuple(factor_block) + tuple(esg_block)
        data = rank_features(base_rows, keys) if transform == "rank" else base_rows
        tr = [r for r in data if r["cutoff"] in set(tr_m)]
        va = [r for r in data if r["cutoff"] in set(va_m)]
        for lam in LAMBDAS:
            for shrink in SHRINKS:
                out = _stage_pair(tr, va, factor_block, esg_block, lam, shrink)
                if out is None:
                    continue
                sc = _score(out, va)
                searched.append({"transform": transform, "lambda": lam, "shrink": shrink,
                                 "val_residual_r2": sc["residual_r2"],
                                 "val_mean_ic": sc["mean_ic"]})
                if sc["residual_r2"] is not None and (
                        best is None or sc["residual_r2"] > best["val"]["residual_r2"]):
                    best = {"transform": transform, "lambda": lam, "shrink": shrink, "val": sc}

    if best is None:
        return {"ran": False, "why": "no configuration fitted"}

    # ── the holdout, touched once ────────────────────────────────────────────
    keys = tuple(factor_block) + tuple(esg_block)
    data = rank_features(base_rows, keys) if best["transform"] == "rank" else base_rows
    tr = [r for r in data if r["cutoff"] in set(tr_m)]
    ho = [r for r in data if r["cutoff"] in set(ho_m)]
    final = _stage_pair(tr, ho, factor_block, esg_block, best["lambda"], best["shrink"])
    if final is None:
        return {"ran": False, "why": "the chosen configuration did not fit the holdout split"}
    hold = _score(final, ho)

    return {
        "ran": True,
        "companies": len({r["company_id"] for r in rows}),
        "rows": len(rows),
        "factor_block": [BLOCK_LABEL.get(k, k) for k in factor_block],
        "esg_block": [BLOCK_LABEL.get(k, k) for k in esg_block],
        "split": {"train": tr_m, "validation": va_m, "holdout": ho_m},
        "chosen": {"transform": best["transform"], "lambda": best["lambda"],
                   "shrink": best["shrink"]},
        "configs_tried": len(searched),
        "validation": best["val"],
        "holdout": hold,
        "stage1_r2_holdout": round(final["stage1_r2"], 5) if final["stage1_r2"] is not None else None,
        "coefficients": {k: round(v, 6) for k, v in final["coef"].items()},
        "search": searched,
    }


def solve_verdict(res):
    """What the HOLDOUT earned, in one word. Validation is never allowed to set this.

    The bands are stated in advance and in the reader's own terms: the ask was to eliminate part
    of the residual, with a twentieth named as a good outcome.
    """
    if not res or not res.get("ran"):
        return {"word": "not run", "line": (res or {}).get("why", "")}
    pct = (res["holdout"] or {}).get("share_of_residual_pct")
    ic = (res["holdout"] or {}).get("mean_ic")
    if pct is None:
        return {"word": "not scored", "line": "The holdout could not be scored."}
    if pct >= 5.0:
        return {"word": "predicts part of the residual",
                "line": f"{pct:.1f}% of the factor model's leftovers explained out of sample, on "
                        f"a holdout scored once. That clears the bar that was set in advance — "
                        f"and it is still ~3 years of one regime with overlapping returns, so it "
                        f"is a measurement, not validated alpha."}
    if pct > 0:
        return {"word": "partial",
                "line": f"{pct:.2f}% of the residual explained on the sealed holdout — real, "
                        f"positive, and below the 5% that was called a good outcome. At this "
                        f"panel's information coefficient that is close to what the arithmetic "
                        f"allows; more comes from better sources and more names, not from "
                        f"further tuning."}
    return {"word": "no",
            "line": f"The chosen configuration explains none of the residual on the holdout "
                    f"({pct:.2f}%). Validation preferred it out of {res['configs_tried']} "
                    f"candidates and the holdout did not agree, which is what that split is for."}


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _print(payload):
    r = payload["result"]
    v = payload["verdict"]
    print("\nTHE 10% TEST — does ESG evidence explain what the factor model cannot?")
    print("=" * 78)
    print(f"  panel            {payload['rows']} rows · {payload['companies']} companies")
    print(f"  primary spec     {payload['primary_spec']} · horizon "
          f"{HORIZONS_PRIMARY}m · train {TRAIN_FRACTION_PRIMARY}")
    print(f"                   {SPEC_NOTE[payload['primary_spec']]}")
    if not r.get("ran"):
        print(f"\n  NOT RUN — {r.get('why')}")
        return
    print(f"\n  STAGE 1 · the factor block ({' · '.join(FACTOR_BLOCK)})")
    print(f"    out-of-sample R^2        {r['stage1']['r2_oos']:+.4f}")
    print(f"    residual left over       {r['stage1']['residual_share']:.1%} of the variance")
    print(f"\n  STAGE 2 · the ESG block on that residual ({' · '.join(ESG_BLOCK)})")
    print(f"    incremental R^2 (oos)    {r['stage2']['incremental_r2_oos']:+.4f}")
    ic = r["stage2"]["ic"]
    t = f"{ic['t_stat']:+.2f}" if ic["t_stat"] is not None else "n/a"
    print(f"    mean rank IC             {ic['mean']:+.4f}   (t {t} over {ic['cutoffs']} cutoffs)")
    for s in ic["series"]:
        print(f"      {s['cutoff']}  IC {s['ic']:+.3f}  n={s['n']}")
    ab = r.get("ablation") or {}
    if ab:
        print(f"\n  ABLATION · one model, with and without the ESG block")
        print(f"    R^2 factors only         {ab['r2_factors_only']:+.4f}")
        print(f"    R^2 with ESG             {ab['r2_with_esg']:+.4f}   "
              f"(delta {ab['delta_r2']:+.4f})")
        print(f"    MAE                      {ab['mae_factors_only']:.3f} -> "
              f"{ab['mae_with_esg']:.3f}")
    print(f"\n  VERDICT: {v['word'].upper()}")
    print(f"    {v['line']}")
    print(f"\n  {payload['bias_note']}")
    print(f"\n  GRID — every configuration, none privileged")
    print(f"    {'spec':<11}{'hor':>4}{'train':>7}{'stage1 R2':>11}{'incr R2':>10}"
          f"{'mean IC':>9}{'t':>7}  verdict")
    for g in payload["sweep"]:
        s1 = f"{g['stage1_r2_oos']:+.4f}" if g["stage1_r2_oos"] is not None else "   n/a"
        i2 = f"{g['incremental_r2_oos']:+.4f}" if g["incremental_r2_oos"] is not None else "   n/a"
        mi = f"{g['mean_ic']:+.4f}" if g["mean_ic"] is not None else "   n/a"
        tt = f"{g['ic_t_stat']:+.2f}" if g["ic_t_stat"] is not None else "  n/a"
        star = " *" if (g["spec"] == SPEC_PRIMARY
                        and g["horizon_months"] == HORIZONS_PRIMARY
                        and g["train_fraction"] == TRAIN_FRACTION_PRIMARY) else ""
        print(f"    {g['spec']:<11}{g['horizon_months']:>4}{g['train_fraction']:>7}"
              f"{s1:>11}{i2:>10}{mi:>9}{tt:>7}  {g['verdict']}{star}")
    ss = payload["sweep_summary"]
    print(f"\n    {ss['with_contribution']} of {ss['configurations']} configurations show a "
          f"contribution — but read them BY HORIZON:")
    for b in ss.get("by_horizon", []):
        mi = (f"{b['mean_ic_across_specs']:+.4f}"
              if b["mean_ic_across_specs"] is not None else "n/a")
        print(f"      {b['horizon_months']:>2}m   {b['ic_t_at_least_2']} of {b['cells']} specs "
              f"clear IC t>=2   ·   mean IC across specs {mi}")
    print(f"\n    {ss.get('horizon_note', '')}")
    print(f"    {ss['note']}")
    print(f"\n  {payload['sample_caveat']}")


def sample_caveat(companies, rows):
    """The caveat with THIS panel's own numbers in it.

    `forecast.SAMPLE_CAVEAT` names ~43 companies because that is the basket it was written for.
    Printing it under a 97-company panel states a false fact about the run on screen, which is a
    small error of exactly the kind this repo keeps finding: a figure carried forward from the
    context it was true in.
    """
    return (f"Trained on ~3 years and {companies} ASEAN companies ({rows} rows) — one market "
            f"regime, with overlapping 6-month returns that make consecutive rows "
            f"non-independent. The effective sample is far smaller than the row count. Treat any "
            f"skill figure here as weak evidence, never as validated alpha.")


#: The single most important thing this section produced, kept as text so it travels with the
#: data rather than living only in a chat message.
HOLDOUT_LESSON = (
    "On the CGSI panel validation selected a configuration worth +7.6% of the residual and the "
    "sealed holdout returned -1.8%. The configuration it chose was the least-regularised corner "
    "of the grid. Without the three-way split that +7.6% is what would have been reported, and "
    "it would have cleared the target that was set. This is what searching 48 configurations "
    "against one evaluation set does, and it is why the holdout is scored once."
)


# --------------------------------------------------------------------------- #
#  DOES ADDING ESG PICK FEWER LOSERS?  — the question in the reader's own terms
# --------------------------------------------------------------------------- #
#: THIS IS A DIFFERENT QUESTION FROM EVERYTHING ABOVE, AND A BETTER ONE TO ASK.
#:
#: The sections above ask how much of the return VARIANCE our evidence explains. That is the
#: academic form of the question and it is what "Fama-French explains ~90%" actually refers to —
#: how much of the up-and-down movement a few common factors account for. It is NOT a claim that
#: 90% of investments make money and 10% fail; the model says nothing about a success rate.
#:
#: The practical question — "if I use this, do I pick fewer losers?" — is separate, answerable,
#: and the one a fund actually cares about. So: rank the cohort by the factor model alone, then
#: by the factor model PLUS our ESG block, take the top slice of each, and count how many of
#: those picks lost money. If the ESG block is worth anything, the second number is lower.
#:
#: THREE THINGS THAT KEEP THIS HONEST.
#:
#:   * **NO HYPERPARAMETER SEARCH.** The section above searched 48 configurations, validation
#:     picked one worth +7.6%, and the sealed holdout returned -1.8%. Having learned that here,
#:     this test does no searching at all: one declared penalty, and the full grid of slice sizes
#:     and loss thresholds reported together so there is no best cell to quote.
#:   * **SHRINKAGE IS ABSENT BECAUSE IT CANNOT MATTER.** Shrinking every prediction toward a
#:     constant is monotonic, so it cannot change an ORDER, and this test only reads order. One
#:     fewer knob, for a reason rather than by preference.
#:   * **THE TARGET IS THE RAW RETURN, NOT THE DEMEANED ONE.** "Did this lose money" is an
#:     absolute question. The demeaned target was right for asking who beat whom; using it here
#:     would count a company that fell 3% in a market that fell 10% as a WINNER, which is not
#:     what anybody means by a loser.
#:
#: The ranking model itself is still fitted on demeaned returns — picking who will do best
#: relative to the cohort is the thing a cross-sectional model can do — and only the SCORING of
#: the picks uses raw returns.

#: Declared in advance: one penalty, ranks, no search.
DOWNSIDE_LAMBDA = 10.0
#: Top slice sizes and loss thresholds. The whole grid is reported; none is the headline.
TOP_FRACTIONS = (0.10, 0.25, 0.50)
LOSS_THRESHOLDS = (0.0, -5.0, -10.0)


def _pick_rate(rows, scores, top_frac, threshold):
    """Take the top `top_frac` by score WITHIN each cutoff; return the loser rate among them.

    Per cutoff, because a pooled top-quartile would simply select the best PERIOD — every name
    from the strongest quarter and none from the weakest — which measures market timing rather
    than selection.
    """
    by_cut = {}
    for r, sc in zip(rows, scores):
        by_cut.setdefault(r["cutoff"], []).append((sc, r["target"]))
    picked = 0
    lost = 0
    for cut, pairs in by_cut.items():
        pairs.sort(key=lambda x: -x[0])
        k = max(1, int(round(len(pairs) * top_frac)))
        for _, tgt in pairs[:k]:
            picked += 1
            if tgt < threshold:
                lost += 1
    return {"picked": picked, "lost": lost,
            "rate": round(lost / picked, 4) if picked else None}


def downside(rows, factor_block, esg_block):
    """Do the ESG features reduce the share of picks that lose money? Scored on the holdout."""
    split = three_way(rows)
    if split is None:
        return {"ran": False, "why": "too few cutoffs for a three-way split"}
    tr_m, va_m, ho_m = split
    # Validation is not used to choose anything here — no search — so it is folded into TRAIN.
    # Saying that plainly matters: silently enlarging the training set is how a comparison
    # against an earlier result stops being like-for-like.
    fit_m = set(tr_m) | set(va_m)

    keys = tuple(factor_block) + tuple(esg_block)
    data = rank_features(apply_spec(rows, "xs"), keys)
    raw = {(r["company_id"], r["cutoff"]): r["target"] for r in rows}   # RAW returns, for scoring

    tr = [r for r in data if r["cutoff"] in fit_m]
    ho = [r for r in data if r["cutoff"] in set(ho_m)]
    if not tr or not ho:
        return {"ran": False, "why": "the split left one side empty"}

    ytr = [r["target"] for r in tr]
    yho = [r["target"] for r in ho]
    s1 = _fit_block(tr, ho, factor_block, ytr, yho, lam=DOWNSIDE_LAMBDA)
    if s1 is None:
        return {"ran": False, "why": "the factor model did not fit"}
    res_tr = [a - p for a, p in zip(ytr, s1["pred_train"])]
    s2 = _fit_block(tr, ho, esg_block, res_tr, [0.0] * len(ho), lam=DOWNSIDE_LAMBDA)
    if s2 is None:
        return {"ran": False, "why": "the ESG block did not fit"}

    factor_only = s1["pred_test"]
    combined = [a + b for a, b in zip(s1["pred_test"], s2["pred_test"])]

    # Score against the RAW return, not the demeaned one the model was fitted on.
    ho_raw = [{"cutoff": r["cutoff"], "target": raw[(r["company_id"], r["cutoff"])]} for r in ho]

    grid = []
    for thr in LOSS_THRESHOLDS:
        base_lost = sum(1 for r in ho_raw if r["target"] < thr)
        base_rate = base_lost / len(ho_raw)
        for tf in TOP_FRACTIONS:
            f = _pick_rate(ho_raw, factor_only, tf, thr)
            c = _pick_rate(ho_raw, combined, tf, thr)
            grid.append({
                "loss_threshold_pct": thr,
                "top_fraction": tf,
                "cohort_rate": round(base_rate, 4),
                "factor_only_rate": f["rate"],
                "with_esg_rate": c["rate"],
                "picked": c["picked"],
                "change_vs_factor_pp": (round((c["rate"] - f["rate"]) * 100, 2)
                                        if (c["rate"] is not None and f["rate"] is not None)
                                        else None),
            })
    better = sum(1 for g in grid if (g["change_vs_factor_pp"] or 0) < 0)
    return {
        "ran": True,
        "companies": len({r["company_id"] for r in rows}),
        "rows": len(rows),
        "fit_cutoffs": sorted(fit_m),
        "holdout_cutoffs": ho_m,
        "lambda": DOWNSIDE_LAMBDA,
        "searched": 0,
        "grid": grid,
        "cells_improved": better,
        "cells": len(grid),
    }


def downside_verdict(res):
    """Rule-based, and it requires a MAJORITY of cells, not a best one."""
    if not res or not res.get("ran"):
        return {"word": "not run", "line": (res or {}).get("why", "")}
    n, k = res["cells"], res["cells_improved"]
    avg = _mean([g["change_vs_factor_pp"] for g in res["grid"]
                 if g["change_vs_factor_pp"] is not None])
    if k > n * 0.6 and avg < -1.0:
        return {"word": "picks fewer losers",
                "line": f"Adding the ESG block lowers the loss rate in {k} of {n} slice/threshold "
                        f"combinations, by {abs(avg):.1f} percentage points on average, on the "
                        f"holdout. Small sample, one regime — a signal, not a guarantee."}
    if k >= n * 0.4:
        return {"word": "no clear difference",
                "line": f"The ESG block changes the loss rate in {k} of {n} combinations one way "
                        f"and the rest the other, averaging {avg:+.1f} points. That is what no "
                        f"effect looks like."}
    return {"word": "picks more losers",
            "line": f"Adding the ESG block RAISES the loss rate in {n - k} of {n} combinations, "
                    f"averaging {avg:+.1f} points. On this panel it makes selection worse."}


def _print_downside(r):
    print("\nDOES ADDING ESG PICK FEWER LOSERS?")
    print("=" * 78)
    if not r.get("ran"):
        print(f"  NOT RUN — {r.get('why')}")
        return
    print(f"  panel      {r['rows']} rows · {r['companies']} companies")
    print(f"  fitted on  {r['fit_cutoffs'][0]} .. {r['fit_cutoffs'][-1]}")
    print(f"  scored on  {r['holdout_cutoffs'][0]} .. {r['holdout_cutoffs'][-1]}  (holdout)")
    print(f"  search     {r['searched']} configurations — nothing was tuned")
    print(f"\n  {'loses more than':>16} {'you pick':>9} {'everyone':>10} {'factors':>10} "
          f"{'+ our ESG':>11} {'change':>9}")
    for g in r["grid"]:
        print(f"  {abs(g['loss_threshold_pct']):>13.0f}%   {g['top_fraction']:>8.0%} "
              f"{g['cohort_rate']:>10.1%} {g['factor_only_rate']:>10.1%} "
              f"{g['with_esg_rate']:>11.1%} {g['change_vs_factor_pp']:>+8.1f}pp")
    v = downside_verdict(r)
    print(f"\n  VERDICT: {v['word'].upper()}")
    print(f"    {v['line']}")


def _print_solve(r):
    print("\nSOLVING FOR THE RESIDUAL — can we predict what the factor model leaves over?")
    print("=" * 78)
    if not r.get("ran"):
        print(f"  NOT RUN — {r.get('why')}")
        return
    print(f"  panel            {r['panel']} — {r['rows']} rows · {r['companies']} companies")
    print(f"  stage 1 block    {' · '.join(r['factor_block'])}")
    print(f"  stage 2 block    {' · '.join(r['esg_block'])}")
    sp = r["split"]
    print(f"\n  SPLIT BY TIME")
    print(f"    train        {len(sp['train']):>2} cutoffs   {sp['train'][0]} .. {sp['train'][-1]}")
    print(f"    validation   {len(sp['validation']):>2} cutoffs   "
          f"{sp['validation'][0]} .. {sp['validation'][-1]}   (chooses the configuration)")
    print(f"    HOLDOUT      {len(sp['holdout']):>2} cutoffs   "
          f"{sp['holdout'][0]} .. {sp['holdout'][-1]}   (scored ONCE)")
    c = r["chosen"]
    print(f"\n  SEARCH           {r['configs_tried']} configurations scored on validation")
    print(f"    chosen         transform={c['transform']} · lambda={c['lambda']} · "
          f"shrink={c['shrink']}")
    v = r["validation"]
    print(f"    validation     residual R^2 {v['residual_r2']:+.5f}  "
          f"({v['share_of_residual_pct']:+.3f}% of the residual)   — CHOSEN ON, not reportable")
    h = r["holdout"]
    print(f"\n  HOLDOUT — the only reportable number")
    print(f"    stage 1 R^2              {r['stage1_r2_holdout']:+.5f}")
    print(f"    residual explained       {h['share_of_residual_pct']:+.3f}%   "
          f"(R^2 {h['residual_r2']:+.5f})")
    t = f"{h['ic_t_stat']:+.2f}" if h["ic_t_stat"] is not None else "n/a"
    print(f"    mean rank IC             {h['mean_ic']:+.4f}   (t {t} over {h['ic_cutoffs']})")
    for sx in h["ic_series"]:
        print(f"      {sx['cutoff']}  IC {sx['ic']:+.3f}  n={sx['n']}")
    vd = r["verdict"]
    print(f"\n  VERDICT: {vd['word'].upper()}")
    print(f"    {vd['line']}")
    print(f"\n  {r['sample_caveat']}")


def main(argv=None):
    import argparse
    import datetime
    ap = argparse.ArgumentParser(description="The 10% test — two-stage residual analysis.")
    ap.add_argument("--run", action="store_true",
                    help="rebuild the panel and re-run (default: read the frozen result)")
    ap.add_argument("--freeze", action="store_true",
                    help="run and write data/residual_test.json")
    ap.add_argument("--solve", action="store_true",
                    help="develop a predictor of the residual against a sealed holdout")
    ap.add_argument("--downside", action="store_true",
                    help="does adding ESG reduce the share of picks that lose money?")
    ap.add_argument("--narrow", action="store_true",
                    help="with --solve: the CGSI 52 only, instead of the wide two-universe panel")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the report")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.downside:
        wide = not args.narrow
        rows = (build_wide_panel(verbose=args.verbose) if wide
                else forecast.build_panel(horizon=HORIZONS_PRIMARY, verbose=args.verbose))
        fb = WIDE_FACTOR_BLOCK if wide else FACTOR_BLOCK
        res = downside(rows, fb, ESG_BLOCK)
        res["panel"] = "wide · CGSI 52 + ASEAN indexes" if wide else "narrow · CGSI 52"
        res["verdict"] = downside_verdict(res)
        if args.freeze:
            path = os.path.join(_ROOT, "data", "residual_downside.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1, sort_keys=True)
                fh.write("\\n")
            print(f"wrote {path}")
        if args.json:
            print(json.dumps(res, indent=1, sort_keys=True))
        else:
            _print_downside(res)
        return 0

    if args.solve:
        wide = not args.narrow
        rows = (build_wide_panel(verbose=args.verbose) if wide
                else forecast.build_panel(horizon=HORIZONS_PRIMARY, verbose=args.verbose))
        fb = WIDE_FACTOR_BLOCK if wide else FACTOR_BLOCK
        res = solve(rows, fb, ESG_BLOCK, verbose=args.verbose)
        res["panel"] = "wide · CGSI 52 + ASEAN indexes" if wide else "narrow · CGSI 52"
        res["verdict"] = solve_verdict(res)
        res["sample_caveat"] = sample_caveat(res.get("companies"), res.get("rows"))
        res["not_advice"] = NOT_ADVICE
        res["holdout_lesson"] = HOLDOUT_LESSON
        payload = res
        if args.freeze:
            path = os.path.join(_ROOT, "data", "residual_solve.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1, sort_keys=True)
                fh.write("\n")
            print(f"wrote {path}")
        if args.json:
            print(json.dumps(payload, indent=1, sort_keys=True))
        else:
            _print_solve(payload)
        return 0

    if args.run or args.freeze:
        payload = build(verbose=args.verbose)
        payload["built_at"] = datetime.date.today().isoformat()
        if args.freeze:
            with open(RESULT_JSON, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1, sort_keys=True)
                fh.write("\n")
            print(f"wrote {RESULT_JSON}")
    else:
        payload = frozen()
        if payload is None:
            print("No frozen result. Run: python residual.py --freeze")
            return 1
    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
    else:
        _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
