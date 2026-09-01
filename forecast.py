"""A FORECAST of forward price return, trained on the PPP system — and its measured skill.

READ THIS BEFORE QUOTING ANY NUMBER IT PRODUCES.
------------------------------------------------
This module does something the rest of the repo deliberately refuses to do: it predicts. Every
other surface reports what is already known and dated, and `CLAUDE.md` HARD RULE 4 says the
product never picks. This was added on an explicit instruction to build a real predictive model
and label its output as a prediction.

The instruction is honoured literally, which means two things, and the second is the one that
matters:

  * it is a REAL model — ridge regression fitted on a real panel of (what was knowable at a past
    cutoff) against (what the share price actually did next). Nothing is invented, no coefficient
    is hand-set, and the panel is rebuilt from committed files so a fresh clone reproduces it;

  * it REPORTS ITS OWN SKILL, always. `predict()` cannot return an estimate without the
    out-of-sample metrics attached, because a forecast without its error is the exact object this
    whole product exists to argue against — a confident number whose reliability the reader
    cannot check. If the model has no skill, the honest result is a prediction carrying "no
    measured skill", and that is what ships.

HOW THE PANEL IS BUILT
----------------------
The engine is PURE and replays at any cutoff, which is the only reason this is possible at all.
For each quarterly cutoff the engine is re-run with `cutoff=as_of=date`, so it sees only evidence
published before that date — no lookahead. The PPP shares are taken from that run. The features
are then paired with the return the stock ACTUALLY delivered over the following `HORIZON_MONTHS`,
read from `data/price_history.json`.

FIVE THINGS THAT WOULD MAKE THIS DISHONEST, AND WHAT IS DONE ABOUT EACH
----------------------------------------------------------------------
1. **Lookahead through evidence.** Solved by the engine's own cutoff: a signal published after
   the cutoff cannot enter the run. `enforce_cutoff` is called to assert it, not assumed.
2. **Lookahead through scaling.** Feature standardisation is fitted on the TRAINING rows only and
   then applied to the test rows. Standardising over the whole panel first leaks the test
   period's distribution into training and flatters every metric.
3. **Lookahead through the split.** The split is by TIME, never random. Random k-fold on a panel
   like this trains on 2026 to predict 2024 and produces a number that means nothing.
4. **Grading against nothing.** R^2 is reported against a real baseline — predicting the training
   mean — so "better than guessing" is measured rather than asserted. Directional hit rate is
   reported beside it, because a model can have negative R^2 and still call the sign.
5. **Overlapping returns.** Quarterly cutoffs with a 6-month horizon means consecutive rows share
   months, so observations are NOT independent and the effective sample is far smaller than the
   row count. This cannot be engineered away with the data available; it is stated in the frozen
   model file and printed on screen.

WHAT THE DATA CANNOT SUPPORT, WHATEVER THE OUTPUT LOOKS LIKE
------------------------------------------------------------
Evidence in this basket concentrates in 2023-2026, so the panel covers ONE market regime across
~3 years and ~43 companies. That is a small, heavily autocorrelated sample. A good-looking metric
here is weak evidence of genuine predictive power and should never be presented as validated
alpha. `SAMPLE_CAVEAT` travels with every payload for that reason.

Pure-Python by design: the ridge solve is a few dozen lines of Gaussian elimination, so the app
gains no numeric dependency (`requirements.txt` stays as it is). Nothing in `engine.py` or
`signals.py` can import this, and `selftest.py` pins that.
"""
import datetime
import json
import os

import company_metadata
import engine
import engine_config
import harvest
import ppp
import universe

_ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY_JSON = os.path.join(_ROOT, "data", "price_history.json")
MODEL_JSON = os.path.join(_ROOT, "data", "forecast_model.json")

#: How far ahead the model predicts, in months.
HORIZON_MONTHS = 6
#: Months between cutoffs. Quarterly — see the overlapping-returns note above.
CUTOFF_STEP_MONTHS = 3
#: Evidence before this is too thin to score a cohort against (2002-2022 is 60 of 344 signals).
PANEL_START = "2023-06"
#: Ridge penalty. Small and fixed; a penalty tuned on the test period is a leak.
RIDGE_LAMBDA = 1.0
#: Fraction of the CUTOFFS (in time order) used for training. The rest is out-of-sample.
TRAIN_FRACTION = 0.6

#: The features, in a fixed order. All of them are knowable at the cutoff.
FEATURES = ("planet", "people", "profit", "momentum", "evidence",
            "price_mom", "beta", "vol", "prof")

FEATURE_LABEL = {
    "planet": "PPP · Planet share of movement",
    "people": "PPP · People share of movement",
    "profit": "PPP · Profit share of movement",
    "momentum": "ESG evidence momentum (direction consensus)",
    "evidence": "Evidence depth (log signal count)",
    "price_mom": "WML · 12-1 momentum factor",
    "beta": "MKT · beta to the equal-weighted cohort",
    "vol": "VOL · realised volatility, trailing 12m",
    "prof": "RMW-proxy · profitability from two audited years",
}

SAMPLE_CAVEAT = (
    "Trained on ~3 years and ~43 ASEAN companies — one market regime, with overlapping 6-month "
    "returns that make consecutive rows non-independent. The effective sample is far smaller "
    "than the row count. Treat any skill figure here as weak evidence, never as validated alpha."
)

NOT_ADVICE = (
    "A model estimate of 6-month price return, not investment advice and not a recommendation. "
    "It is shown with the out-of-sample skill it actually achieved; read that first."
)

_HISTORY = None
_MODEL = None


# --------------------------------------------------------------------------- #
#  price history
# --------------------------------------------------------------------------- #
def _history():
    global _HISTORY
    if _HISTORY is None:
        try:
            with open(HISTORY_JSON, encoding="utf-8") as fh:
                _HISTORY = json.load(fh).get("series") or {}
        except Exception:                                      # noqa: BLE001 - best-effort
            _HISTORY = {}
    return _HISTORY


def _shift(month, months):
    """'YYYY-MM' shifted by a whole number of months."""
    y, m = int(month[:4]), int(month[5:7])
    total = y * 12 + (m - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _close(ticker, month):
    return (_history().get(ticker) or {}).get(month)


def _price_momentum_at(ticker, month):
    """The 12-1 factor as it stood at `month`: return from t-13 to t-1. None if unavailable.

    Same convention as `price_momentum.compute` — the most recent month is skipped, so this is
    knowable at the cutoff and carries no lookahead.
    """
    start, end = _close(ticker, _shift(month, -13)), _close(ticker, _shift(month, -1))
    if not start or not end:
        return None
    return (end - start) / start * 100.0


def _forward_return(ticker, month, horizon=HORIZON_MONTHS):
    """What the stock ACTUALLY did over the next `horizon` months, in percent. None if unknown."""
    now, later = _close(ticker, month), _close(ticker, _shift(month, horizon))
    if not now or not later:
        return None
    return (later - now) / now * 100.0


# --------------------------------------------------------------------------- #
#  FACTORS — Fama-French STYLE, with the two we cannot source named
# --------------------------------------------------------------------------- #
#: WHICH FAMA-FRENCH FACTORS THIS ACTUALLY HAS, AND WHICH IT DOES NOT.
#:
#: The ask was a Fama-French multi-factor model. What is built here is a cross-sectional factor
#: regression in that STYLE, and it is labelled that way rather than as the real thing, because
#: two of the canonical factors cannot be sourced from anything this repo holds or can legally
#: fetch:
#:
#:   * **SMB (size)** needs market capitalisation — shares outstanding times price. No shares
#:     count exists in `data/company_metadata.csv`, the Yahoo chart endpoint does not return one,
#:     and `quoteSummary`, which would, is crumb-gated (see the note in `financials.py`).
#:   * **HML (value)** needs book-to-market. No book value anywhere, same reasons.
#:
#: Substituting a proxy for either — price level for size, say — would be inventing a factor, so
#: neither is faked and both are named on screen. What IS constructed is real:
#:
#:   * **MKT** — beta to the equal-weighted cohort over the trailing year. A market factor built
#:     from the 43 names we actually hold, not a borrowed index.
#:   * **WML / UMD** — the Carhart momentum factor, which is the 12-1 reading already on file.
#:   * **VOL** — realised volatility of trailing monthly returns. Not a Fama-French factor; it is
#:     included because low-volatility is a documented cross-sectional effect and it costs nothing
#:     to compute from data already here.
#:   * **RMW-proxy** — profitability, from the two audited fiscal years the basket carries. A
#:     proxy and called one: RMW is built from operating profitability over book equity, and we
#:     have neither denominator.
#:
#: And then the factors this product exists for, which no factor model carries: the ESG evidence
#: direction, and the Profit/People/Planet shares.
FACTOR_NOTE = (
    "Fama-French STYLE, not the real thing: MKT (beta to the equal-weighted cohort), WML (the "
    "12-1 Carhart momentum factor), realised volatility and a profitability proxy from two "
    "audited fiscal years — plus our own ESG evidence direction and PPP shares. SMB and HML are "
    "ABSENT and not proxied: size needs market capitalisation and value needs book-to-market, "
    "and neither is in this repo or fetchable from a keyless endpoint."
)

FACTORS_PRESENT = ("MKT", "WML", "VOL", "RMW-proxy", "ESG", "PPP")
FACTORS_MISSING = {
    "SMB": "needs market capitalisation — no shares-outstanding figure on file, and quoteSummary is crumb-gated",
    "HML": "needs book-to-market — no book value on file, same reason",
}

#: Trailing window for beta and volatility, in months.
FACTOR_WINDOW = 12


def _monthly_returns(ticker, month, window=FACTOR_WINDOW):
    """The trailing monthly returns ending at `month`, oldest first. [] when incomplete."""
    out = []
    for i in range(window, 0, -1):
        prev, cur = _close(ticker, _shift(month, -i)), _close(ticker, _shift(month, -i + 1))
        if not prev or not cur:
            return []
        out.append((cur - prev) / prev)
    return out


def cohort_returns(month, tickers, window=FACTOR_WINDOW):
    """The equal-weighted cohort return per month — our MKT factor. Built from the names we hold.

    Only companies with a complete window contribute, so the factor is not a different basket
    each month by accident.
    """
    series = [_monthly_returns(t, month, window) for t in tickers]
    series = [s for s in series if len(s) == window]
    if not series:
        return []
    return [sum(s[i] for s in series) / len(series) for i in range(window)]


def _beta(rets, mkt):
    """OLS beta of a return series on the market series. None when it cannot be formed."""
    n = len(rets)
    if n < 6 or len(mkt) != n:
        return None
    mbar = sum(mkt) / n
    rbar = sum(rets) / n
    var = sum((m - mbar) ** 2 for m in mkt)
    if var < 1e-12:
        return None
    cov = sum((mkt[i] - mbar) * (rets[i] - rbar) for i in range(n))
    return cov / var


def _vol(rets):
    """Realised volatility (sd of monthly returns). None when the window is too short."""
    n = len(rets)
    if n < 6:
        return None
    mean = sum(rets) / n
    return (sum((r - mean) ** 2 for r in rets) / (n - 1)) ** 0.5


def profitability(row):
    """RMW PROXY in [-1, 1] from the two audited fiscal years the basket carries.

    Called a proxy everywhere because it is one: real RMW is operating profitability scaled by
    book equity, and we hold neither denominator. This is direction and level only.
    """
    import financials
    via = financials.viability(row or {})
    flag = via.get("profitability_flag")
    direction = (via.get("earnings") or {}).get("direction", "unknown")
    if flag == "profitable":
        base = 0.5
    elif flag == "loss_making":
        base = -0.5
    else:
        return 0.0
    if direction in ("growing", "swung to profit"):
        return base + 0.5
    if direction in ("shrinking", "widening loss"):
        return base - 0.5
    return base


# --------------------------------------------------------------------------- #
#  the panel
# --------------------------------------------------------------------------- #
def cutoffs(history=None, horizon=HORIZON_MONTHS, start=PANEL_START, step=CUTOFF_STEP_MONTHS):
    """Every cutoff month we can both score and grade, oldest first.

    A cutoff is usable only if the price history reaches `horizon` months PAST it — otherwise the
    row has no answer to be graded against, and including it would mean training on rows whose
    target we quietly filled in.
    """
    months = set()
    for series in (history if history is not None else _history()).values():
        months.update(series)
    if not months:
        return []
    last = max(months)
    out, cur = [], start
    while _shift(cur, horizon) <= last:
        out.append(cur)
        cur = _shift(cur, step)
    return out


def build_panel(demo=False, horizon=HORIZON_MONTHS, verbose=False):
    """One row per (company, cutoff) with features knowable then and the return that followed.

    The engine is re-run per cutoff with `cutoff=as_of=<date>`, so it sees only evidence
    published before it. `engine.enforce_cutoff` ASSERTS that rather than trusting it.
    """
    cfg = engine_config.for_horizon("long")
    uni = universe.load_universe(universe.active_file(demo))
    cons = uni["constituents"]
    if not demo:
        # Guard 2b per universe — the harvest store is shared and the baskets have
        # different horizons. See the note on `harvest.apply_overlay`.
        cons = harvest.apply_overlay(cons, as_of=uni.get("as_of") or "")
    meta = company_metadata.load(demo=demo)
    tickers = [c["ticker"] for c in cons]

    rows = []
    for month in cutoffs(horizon=horizon):
        # The MKT factor for this cutoff: the equal-weighted cohort return over the trailing
        # year. Rebuilt per cutoff, from the names that have a complete window at that date.
        mkt = cohort_returns(month, tickers)
        # Cutoff at the FIRST day of the month after: everything published within `month` counts.
        date = _shift(month, 1) + "-01"
        run = engine.run_engine(cons, metadata=meta, config=cfg, as_of=date, cutoff=date,
                                use_cache=False)
        engine.enforce_cutoff(run, cutoff=date)
        for rec in run["records"]:
            cid = rec["company_id"]
            fwd = _forward_return(cid, month, horizon)
            if fwd is None:
                continue
            px = _price_momentum_at(cid, month)
            share = ppp.shares(rec, px)
            if not share["known"]:
                continue
            rets = _monthly_returns(cid, month)
            beta = _beta(rets, mkt)
            vol = _vol(rets)
            if beta is None or vol is None:
                continue
            rows.append({
                "company_id": cid,
                "cutoff": month,
                "planet": share["planet"],
                "people": share["people"],
                "profit": share["profit"],
                "momentum": rec["composite_momentum"],
                "evidence": _log1p(rec["signal_count"]),
                "price_mom": px / 100.0,
                "beta": round(beta, 6),
                "vol": round(vol, 6),
                "prof": profitability(meta.get(cid)),
                "target": fwd,
                # The classification target: did it go UP over the horizon?
                "up": 1 if fwd >= 0 else 0,
            })
        if verbose:
            n = sum(1 for r in rows if r["cutoff"] == month)
            print(f"  cutoff {month}  rows {n}")
    return rows


def _log1p(n):
    import math
    return round(math.log1p(max(0, int(n or 0))), 6)


# --------------------------------------------------------------------------- #
#  ridge regression, in pure Python
# --------------------------------------------------------------------------- #
def _solve(a, b):
    """Gaussian elimination with partial pivoting. Returns None for a singular system."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        pv = m[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col] / pv
            if factor:
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def _standardise(rows, keys, stats=None):
    """Centre and scale features. `stats` is fitted on TRAIN ONLY and passed in for test rows."""
    if stats is None:
        stats = {}
        for k in keys:
            vals = [r[k] for r in rows]
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
            sd = var ** 0.5
            stats[k] = {"mean": mean, "sd": sd if sd > 1e-9 else 1.0}
    x = [[(r[k] - stats[k]["mean"]) / stats[k]["sd"] for k in keys] for r in rows]
    return x, stats


def fit_ridge(x, y, lam=RIDGE_LAMBDA):
    """Ridge with an UNPENALISED intercept. Returns (intercept, coefficients) or None."""
    n, k = len(x), len(x[0])
    ybar = sum(y) / n
    # Features are already centred by `_standardise`, so the intercept is just the mean of y.
    xtx = [[sum(x[i][a] * x[i][b] for i in range(n)) + (lam if a == b else 0.0)
            for b in range(k)] for a in range(k)]
    xty = [sum(x[i][a] * (y[i] - ybar) for i in range(n)) for a in range(k)]
    coef = _solve(xtx, xty)
    if coef is None:
        return None
    return ybar, coef


def _apply(intercept, coef, row):
    return intercept + sum(c * v for c, v in zip(coef, row))


# --------------------------------------------------------------------------- #
#  logistic regression, also pure Python — for DIRECTION
# --------------------------------------------------------------------------- #
#: Fixed iterations and a fixed step: no RNG anywhere, so the same panel always yields the same
#: coefficients. Determinism is the property the whole repo is built on and a forecast is not
#: allowed to be the one thing that breaks it.
LOGIT_ITERS = 400
LOGIT_STEP = 0.35
LOGIT_L2 = 1.0


def _sigmoid(z):
    import math
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fit_logistic(x, y, l2=LOGIT_L2, iters=LOGIT_ITERS, step=LOGIT_STEP):
    """Batch gradient descent on the log-loss, with an UNPENALISED intercept.

    Returns (intercept, coefficients). Features must already be standardised, which is what makes
    one global step size reasonable across them.
    """
    n, k = len(x), len(x[0])
    b0, b = 0.0, [0.0] * k
    for _ in range(iters):
        g0, g = 0.0, [0.0] * k
        for i in range(n):
            p = _sigmoid(b0 + sum(b[j] * x[i][j] for j in range(k)))
            err = p - y[i]
            g0 += err
            for j in range(k):
                g[j] += err * x[i][j]
        b0 -= step * g0 / n
        for j in range(k):
            b[j] -= step * (g[j] / n + l2 * b[j] / n)
    return b0, b


def train_direction(rows, train_fraction=TRAIN_FRACTION):
    """Predict the SIGN of the forward return, graded against the majority class.

    Direction is the question that was actually asked ("the likely direction of the stock") and it
    is a fairer test than the return magnitude: a model can be hopeless at how far and still be
    useful about which way. It is graded against the MAJORITY CLASS, never 50% — in a rising
    market "always up" is a strong baseline and beating a coin is not evidence of anything.
    """
    months = sorted({r["cutoff"] for r in rows})
    if len(months) < 4:
        return {"trained": False, "why": f"only {len(months)} usable cutoffs — too few to split"}
    edge = max(1, int(len(months) * train_fraction))
    tr = [r for r in rows if r["cutoff"] in set(months[:edge])]
    te = [r for r in rows if r["cutoff"] in set(months[edge:])]
    if not tr or not te:
        return {"trained": False, "why": "the time split left one side empty"}

    xtr, stats = _standardise(tr, FEATURES)
    ytr = [r["up"] for r in tr]
    if len(set(ytr)) < 2:
        return {"trained": False, "why": "the training period went one way only — nothing to learn"}
    b0, b = fit_logistic(xtr, ytr)

    xte, _ = _standardise(te, FEATURES, stats)
    yte = [r["up"] for r in te]
    probs = [_sigmoid(b0 + sum(b[j] * row[j] for j in range(len(b)))) for row in xte]
    pred = [1 if p >= 0.5 else 0 for p in probs]

    hits = sum(1 for a, p in zip(yte, pred) if a == p)
    ups = sum(yte)
    majority = max(ups, len(yte) - ups) / len(yte)
    acc = hits / len(yte)
    # Brier score: mean squared error of the PROBABILITY, against the same majority baseline.
    # Accuracy alone hides a model that is right but wildly overconfident.
    brier = sum((p - a) ** 2 for p, a in zip(probs, yte)) / len(yte)
    base_rate = sum(ytr) / len(ytr)
    brier_base = sum((base_rate - a) ** 2 for a in yte) / len(yte)

    return {
        "trained": True,
        "kind": "logistic",
        "features": list(FEATURES),
        "intercept": round(b0, 6),
        "coefficients": {k: round(c, 6) for k, c in zip(FEATURES, b)},
        "standardisation": {k: {"mean": round(v["mean"], 6), "sd": round(v["sd"], 6)}
                            for k, v in stats.items()},
        "train": {"cutoffs": months[:edge], "rows": len(tr)},
        "test": {"cutoffs": months[edge:], "rows": len(te)},
        "skill": {
            "accuracy": round(acc, 4),
            "majority_class": round(majority, 4),
            "beats_majority": bool(acc > majority),
            "brier": round(brier, 4),
            "brier_baseline": round(brier_base, 4),
            "beats_brier": bool(brier < brier_base),
        },
        "factors_present": list(FACTORS_PRESENT),
        "factors_missing": FACTORS_MISSING,
        "factor_note": FACTOR_NOTE,
    }


def direction_verdict(skill):
    """Same harsh rule as `verdict`: beating ONE baseline is what an unskilled model does."""
    if not skill:
        return {"word": "untrained", "line": "No direction model has been fitted."}
    if skill.get("beats_majority") and skill.get("beats_brier"):
        return {"word": "some skill",
                "line": "Calls the direction more often than always predicting the common one, "
                        "and its probabilities are better calibrated than the base rate. Weak "
                        "evidence of skill on this sample, not proof."}
    if skill.get("beats_majority") or skill.get("beats_brier"):
        return {"word": "marginal",
                "line": "Beats one baseline and not the other, which is what an unskilled model "
                        "does about half the time. Do not act on it."}
    return {"word": "no measured skill",
            "line": "It calls the direction no better than always predicting the commoner one. "
                    "The factors available here — with size and value missing — do not separate "
                    "the winners from the losers in this basket."}


# --------------------------------------------------------------------------- #
#  training, with an out-of-sample split BY TIME
# --------------------------------------------------------------------------- #
def train(rows, lam=RIDGE_LAMBDA, train_fraction=TRAIN_FRACTION):
    """Fit on the earlier cutoffs, grade on the later ones. Returns the frozen-model dict.

    The split is by cutoff, not by row: splitting rows would put the same date on both sides and
    let the model see its own test period.
    """
    months = sorted({r["cutoff"] for r in rows})
    if len(months) < 4:
        return {"trained": False, "why": f"only {len(months)} usable cutoffs — too few to split"}
    edge = max(1, int(len(months) * train_fraction))
    train_months, test_months = set(months[:edge]), set(months[edge:])
    tr = [r for r in rows if r["cutoff"] in train_months]
    te = [r for r in rows if r["cutoff"] in test_months]
    if not tr or not te:
        return {"trained": False, "why": "the time split left one side empty"}

    xtr, stats = _standardise(tr, FEATURES)
    ytr = [r["target"] for r in tr]
    fitted = fit_ridge(xtr, ytr, lam)
    if fitted is None:
        return {"trained": False, "why": "the normal equations were singular"}
    intercept, coef = fitted

    xte, _ = _standardise(te, FEATURES, stats)
    yte = [r["target"] for r in te]
    pred = [_apply(intercept, coef, row) for row in xte]

    # The BASELINE is the training mean — "what you would have said knowing nothing about the
    # company". R^2 against it is the only version of "better than guessing" worth reporting.
    base = sum(ytr) / len(ytr)
    ss_res = sum((a - b) ** 2 for a, b in zip(yte, pred))
    ss_base = sum((a - base) ** 2 for a in yte)
    r2 = 1.0 - ss_res / ss_base if ss_base > 0 else 0.0
    mae = sum(abs(a - b) for a, b in zip(yte, pred)) / len(yte)
    base_mae = sum(abs(a - base) for a in yte) / len(yte)
    hits = sum(1 for a, b in zip(yte, pred) if (a >= 0) == (b >= 0))
    # The honest comparison for a hit rate is the majority class, not 50%: in a rising market
    # "always up" is a strong baseline and a model must beat IT to have called anything.
    ups = sum(1 for a in yte if a >= 0)
    majority = max(ups, len(yte) - ups) / len(yte)

    return {
        "trained": True,
        "horizon_months": HORIZON_MONTHS,
        "features": list(FEATURES),
        "intercept": round(intercept, 6),
        "coefficients": {k: round(c, 6) for k, c in zip(FEATURES, coef)},
        "standardisation": {k: {"mean": round(v["mean"], 6), "sd": round(v["sd"], 6)}
                            for k, v in stats.items()},
        "lambda": lam,
        "train": {"cutoffs": sorted(train_months), "rows": len(tr)},
        "test": {"cutoffs": sorted(test_months), "rows": len(te)},
        "skill": {
            "r2_oos": round(r2, 4),
            "mae_oos": round(mae, 3),
            "baseline_mae": round(base_mae, 3),
            "beats_baseline": bool(mae < base_mae),
            "hit_rate": round(hits / len(yte), 4),
            "majority_class": round(majority, 4),
            "beats_majority": bool(hits / len(yte) > majority),
        },
        "sample_caveat": SAMPLE_CAVEAT,
        "not_advice": NOT_ADVICE,
    }


def verdict(skill):
    """How much weight this model has earned, in one word plus the reason. Rule-based.

    Deliberately harsh: a model is 'useful' only if it beats BOTH baselines — the mean (on error)
    and the majority class (on direction). Beating one is what an unskilled model does by chance.
    """
    if not skill:
        return {"word": "untrained", "line": "No model has been fitted."}
    r2, beats_mae = skill.get("r2_oos", -1), skill.get("beats_baseline")
    beats_dir = skill.get("beats_majority")
    if r2 > 0 and beats_mae and beats_dir:
        return {"word": "some skill",
                "line": "Beats both baselines out of sample — on error and on direction. Given "
                        "the sample, this is weak evidence of skill, not proof of it."}
    if beats_mae or beats_dir:
        return {"word": "marginal",
                "line": "Beats one baseline out of sample and not the other, which is what an "
                        "unskilled model does about half the time. Do not act on it."}
    return {"word": "no measured skill",
            "line": "It does not beat guessing the average out of sample. The model is shown "
                    "because it was asked for and because its failure is the finding: this "
                    "panel does not support forecasting a price from these features."}


# --------------------------------------------------------------------------- #
#  serving
# --------------------------------------------------------------------------- #
def model():
    """The frozen model, loaded once. Missing -> None, and `predict` says so."""
    global _MODEL
    if _MODEL is None:
        try:
            with open(MODEL_JSON, encoding="utf-8") as fh:
                _MODEL = json.load(fh)
        except Exception:                                      # noqa: BLE001 - best-effort
            _MODEL = {}
    return _MODEL or None


def latest_month():
    """The newest month the price history covers, or ''. The serve-time reference date."""
    months = set()
    for series in _history().values():
        months.update(series)
    return max(months) if months else ""


def factors_now(ticker, cohort_tickers, meta_row=None, month=None):
    """The three market factors for one company TODAY, or Nones. Never raises.

    Computed from the committed price history, at the newest month it covers, using exactly the
    same functions the training panel used — so a factor cannot mean one thing in training and
    another at serve time. A factor that cannot be formed comes back None and `predict` then
    substitutes the training mean (which standardises to zero and contributes nothing) rather
    than a made-up value.
    """
    month = month or latest_month()
    if not month:
        return {"beta": None, "vol": None, "prof": None}
    rets = _monthly_returns(ticker, month)
    mkt = cohort_returns(month, list(cohort_tickers or []))
    return {
        "beta": _beta(rets, mkt) if rets and mkt else None,
        "vol": _vol(rets) if rets else None,
        "prof": profitability(meta_row) if meta_row is not None else None,
    }


def _direction_for(row):
    """The direction model's read on an already-standardised feature row, or None.

    It re-standardises from the DIRECTION model's own stats rather than reusing the return
    model's: the two are fitted on the same panel but nothing guarantees they always will be, and
    silently sharing one model's scaling with another is the kind of coupling that breaks quietly.
    """
    mdl = model()
    dm = (mdl or {}).get("direction") or {}
    if not dm.get("trained"):
        return None
    p = _sigmoid(dm["intercept"] + sum(dm["coefficients"][k] * v
                                       for k, v in zip(dm["features"], row)))
    skill = dm.get("skill") or {}
    return {
        "up_probability": round(p, 4),
        "call": "up" if p >= 0.5 else "down",
        # How far from a coin flip. Printed rather than the raw probability alone, because 0.52
        # and 0.94 are both "up" and mean entirely different things.
        "confidence": round(abs(p - 0.5) * 2, 4),
        "skill": skill,
        "verdict": direction_verdict(skill),
        "factors_present": dm.get("factors_present", list(FACTORS_PRESENT)),
        "factors_missing": dm.get("factors_missing", FACTORS_MISSING),
        "factor_note": dm.get("factor_note", FACTOR_NOTE),
    }


def predict(record, price_pct, shares=None, factors=None):
    """A 6-month return estimate for one company, WITH the model's measured skill. Pure.

    Returns `available: False` when the model is missing or the company's features cannot be
    read — never a zero, which would read as "the model expects no move".
    """
    mdl = model()
    if not mdl or not mdl.get("trained"):
        return {"available": False,
                "why": (mdl or {}).get("why", "no model has been trained"),
                "not_advice": NOT_ADVICE}
    share = shares if shares is not None else ppp.shares(record, price_pct)
    if not share.get("known") or price_pct is None:
        return {"available": False,
                "why": share.get("why") or "this company's features cannot be read",
                "not_advice": NOT_ADVICE}

    raw = {
        "planet": share["planet"], "people": share["people"], "profit": share["profit"],
        "momentum": (record or {}).get("composite_momentum") or 0.0,
        "evidence": _log1p((record or {}).get("signal_count")),
        "price_mom": price_pct / 100.0,
        # The three market factors. Absent at serve time (they need the price history and the
        # cohort), they fall back to the TRAINING MEAN — which standardises to 0 and therefore
        # contributes nothing, rather than to a fabricated value. `factors_live` reports whether
        # they were real, so the panel never implies a factor read it did not have.
        "beta": (factors or {}).get("beta"),
        "vol": (factors or {}).get("vol"),
        "prof": (factors or {}).get("prof"),
    }
    st = mdl["standardisation"]

    def _z(key):
        v = raw.get(key)
        if v is None:
            return 0.0                      # the training mean, standardised
        return (v - st[key]["mean"]) / st[key]["sd"]

    row = [_z(k) for k in mdl["features"]]
    est = mdl["intercept"] + sum(mdl["coefficients"][k] * v for k, v in zip(mdl["features"], row))

    direction = _direction_for(row)
    skill = mdl.get("skill") or {}
    return {
        "direction": direction,
        "factors_live": [k for k in ("beta", "vol", "prof") if raw.get(k) is not None],
        "factors_missing": FACTORS_MISSING,
        "factor_note": FACTOR_NOTE,
        "available": True,
        "estimate_pct": round(est, 2),
        "horizon_months": mdl.get("horizon_months", HORIZON_MONTHS),
        "skill": skill,
        "verdict": verdict(skill),
        # The typical size of this model's error out of sample. Printed WITH the estimate,
        # because an estimate of +8% from a model that is routinely 20 points out is not a
        # forecast of +8% and must never be read as one.
        "typical_error_pct": skill.get("mae_oos"),
        "sample_caveat": mdl.get("sample_caveat", SAMPLE_CAVEAT),
        "not_advice": mdl.get("not_advice", NOT_ADVICE),
        "trained_on": mdl.get("train", {}).get("cutoffs", [])[:1],
        "tested_on": mdl.get("test", {}).get("cutoffs", []),
    }


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import argparse

    ap = argparse.ArgumentParser(description="Train the PPP -> forward-return forecast.")
    ap.add_argument("--train", action="store_true", help="rebuild the panel, fit, and freeze")
    ap.add_argument("--horizon", type=int, default=HORIZON_MONTHS, help="months ahead")
    a = ap.parse_args()

    if a.train:
        print(f"building the panel (horizon {a.horizon}m)…")
        rows = build_panel(horizon=a.horizon, verbose=True)
        print(f"\n{len(rows)} rows over {len({r['cutoff'] for r in rows})} cutoffs, "
              f"{len({r['company_id'] for r in rows})} companies\n")
        out = train(rows)
        out["direction"] = train_direction(rows)
        out["built_at"] = datetime.date.today().isoformat()
        out["rows"] = len(rows)
        out["companies"] = len({r["company_id"] for r in rows})
        # ONE fit can be unlucky; nine cannot all be. The sweep is recorded in the frozen file so
        # the headline verdict is quotable as a robustness result rather than a single split —
        # and so that a future session cannot re-roll the split until it likes the answer.
        print("\n  robustness sweep (horizon x train split):")
        sweep = []
        for h in (3, 6, 12):
            srows = rows if h == a.horizon else build_panel(horizon=h)
            for frac in (0.5, 0.6, 0.7):
                got = train(srows, train_fraction=frac)
                if not got.get("trained"):
                    continue
                sk = got["skill"]
                sweep.append({"horizon_months": h, "train_fraction": frac, "rows": len(srows),
                              "r2_oos": sk["r2_oos"], "mae_oos": sk["mae_oos"],
                              "baseline_mae": sk["baseline_mae"], "hit_rate": sk["hit_rate"],
                              "majority_class": sk["majority_class"],
                              "verdict": verdict(sk)["word"]})
                print(f"    h={h:2}m frac={frac}  R2={sk['r2_oos']:+.3f}  "
                      f"MAE={sk['mae_oos']:5.2f} vs {sk['baseline_mae']:5.2f}  "
                      f"dir={sk['hit_rate']:.1%} vs maj {sk['majority_class']:.1%}")
        out["sweep"] = sweep
        out["sweep_summary"] = {
            "configurations": len(sweep),
            "with_skill": sum(1 for r in sweep if r["verdict"] == "some skill"),
            "negative_r2": sum(1 for r in sweep if r["r2_oos"] < 0),
            "below_majority": sum(1 for r in sweep if r["hit_rate"] <= r["majority_class"]),
        }
        with open(MODEL_JSON, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
            fh.write("\n")
        if out.get("trained"):
            s = out["skill"]
            print(f"  train {out['train']['rows']} rows / {len(out['train']['cutoffs'])} cutoffs")
            print(f"  test  {out['test']['rows']} rows / {len(out['test']['cutoffs'])} cutoffs")
            print(f"\n  OOS R^2        {s['r2_oos']:+.4f}")
            print(f"  OOS MAE        {s['mae_oos']:.2f}%   (baseline {s['baseline_mae']:.2f}%)")
            print(f"  direction      {s['hit_rate']:.1%}   (majority class {s['majority_class']:.1%})")
            v = verdict(s)
            print(f"\n  VERDICT: {v['word'].upper()} — {v['line']}")
            d = out.get("direction") or {}
            if d.get("trained"):
                ds = d["skill"]
                print(f"\n  DIRECTION (logistic, Fama-French style factors)")
                print(f"    accuracy       {ds['accuracy']:.1%}   (majority class {ds['majority_class']:.1%})")
                print(f"    brier          {ds['brier']:.4f}   (baseline {ds['brier_baseline']:.4f})")
                dv = direction_verdict(ds)
                print(f"    VERDICT: {dv['word'].upper()} — {dv['line']}")
            else:
                print(f"\n  DIRECTION not trained — {d.get('why')}")
            print("\n  coefficients (standardised):")
            for k, c in out["coefficients"].items():
                print(f"    {FEATURE_LABEL[k]:<44} {c:+.3f}")
        else:
            print(f"  NOT TRAINED — {out.get('why')}")
        print(f"\n-> {MODEL_JSON}")
    else:
        print(json.dumps(predict(None, None), indent=1))
