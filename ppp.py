"""PROFIT · PEOPLE · PLANET — one company's mix, and what the published record says about it.

Two things live here, and the second exists only because the first invites a question this
product must answer carefully.

1. `shares()` — where a company's movement actually IS, as three numbers that sum to 1: Planet,
   People, Profit. Drawn as a ternary plot (the PPP triangle), one dot per company.

2. `outlook()` — the honest answer to "so will it make money?", which is NOT a forecast. It is
   CGSI's own PUBLISHED base rate, attributed, alongside their own caveat that it does not
   transfer to a single stock.

WHAT THE TRIANGLE MEASURES, AND WHAT IT DOES NOT
------------------------------------------------
A ternary needs three non-negative shares of one whole, so every axis has to arrive
dimensionless. Two of the three already are:

  * **Planet** is the E pillar's contribution to composite momentum — |momentum| x evidence
    weight, which is exactly the product `engine.py` already forms when it aggregates.
  * **People** is the same for S and G. **Digital/AI folds in here**, stated on the panel rather
    than dropped: AI governance and AI disclosure are governance questions about how a company
    treats people, and silently discarding a pillar the engine weights at 0.15 would make the
    three shares a composition of something we never named.

  * **Profit** cannot come from evidence weight, because there is no profit PILLAR — the basket
    holds net income, not dated profit signals. It comes from the 12-1 price momentum, divided by
    `PROFIT_FULL_SCALE` and clamped. That constant is the SAME full scale the dual-momentum
    matrix already draws its x axis with, so the triangle and that plot cannot disagree about
    what "a big price move" means, and `basis()` prints the whole rule on screen. A normalising
    constant chosen in private is how a composition quietly becomes an opinion.

**IT IS A MAGNITUDE, NOT A VERDICT.** |momentum| is deliberate: the triangle answers *where is
this company's story*, not *is it good news*. A dot in the Planet corner can mean rapid
environmental progress OR an environmental collapse, and a reader who assumes the first would be
reading a chart that never said it. So the direction of each axis travels BESIDE the shares in
`directions`, and the panel prints it. This is the same discipline `RadarHub` already states for
its own radar — "how fast that pillar is moving, not how good it is" — made explicit because a
corner label is a stronger suggestion than a radius.

**AN ABSENT AXIS IS NOT A ZERO SHARE.** A company with no quotable listing has no Profit reading
at all, and normalising over the two we do have would silently redistribute the missing third
into Planet and People — inflating both and putting the dot somewhere no measurement supports.
`shares()` returns `known=False` with the missing axes named, and the panel declines to plot
rather than plotting a guess. Same rule the hollow dots and `align()` already follow: an absence
of evidence is a finding, not a reading.

NOTHING HERE REACHES A SCORE. `engine.py` and `signals.py` cannot import this module and
`selftest.py` pins it, exactly as it pins `financials`, `rationale`, `price_momentum` and
`quotes`. The shares are a rendering of numbers the engine already computed.
"""
import json
import os

#: Repo root — this module lives at the root, so `data/` is a sibling.
_ROOT = os.path.dirname(os.path.abspath(__file__))
CGSI_FIGURES = os.path.join(_ROOT, "data", "cgsi_note_figures.json")

#: The price move that counts as a FULL Profit reading, in percent. Deliberately the same
#: constant `EngineBoard`'s dual matrix draws its x axis with (+/-60%), so the triangle and the
#: plot cannot mean different things by "a big move".
PROFIT_FULL_SCALE = 60.0

#: Which engine pillar feeds which corner. Digital/AI joins People — see the module docstring.
CORNERS = {
    "planet": ("E",),
    "people": ("S", "G", "DIGITAL"),
}

BASIS = (
    "Planet = the E pillar's contribution to momentum (|direction| x evidence weight). "
    "People = the same for S, G and Digital/AI, which is a governance question and is folded in "
    "rather than dropped. Profit = |12-1 price momentum| / {scale:.0f}%, clamped at 1 — the same "
    "full scale the price axis is drawn with. The three are then divided by their total, so they "
    "sum to 100%. It is a MAGNITUDE: it says where this company is moving, never whether the "
    "movement is good news — the direction of each axis is printed beside it."
).format(scale=PROFIT_FULL_SCALE)

_FIGS = None


def _figures():
    """CGSI's transcribed note figures, loaded once. Missing -> empty, and `outlook` says so."""
    global _FIGS
    if _FIGS is None:
        try:
            with open(CGSI_FIGURES, encoding="utf-8") as fh:
                _FIGS = json.load(fh)
        except Exception:                                      # noqa: BLE001 - best-effort
            _FIGS = {}
    return _FIGS


# --------------------------------------------------------------------------- #
#  THE TRIANGLE
# --------------------------------------------------------------------------- #
def _weighted_shape(components):
    """True when `components` carries the per-pillar {momentum, weight} blocks this needs.

    `server._record_summary` flattens components to `{pillar: momentum}` for the board payload,
    dropping the weight. Handed that, the pulls would silently compute as zero and every company
    would render as "no movement" — a wrong answer that looks exactly like a real finding. So the
    shape is CHECKED and a mismatch is reported as such rather than absorbed.
    """
    for block in (components or {}).values():
        if not isinstance(block, dict):
            return False
    return True


def _pillar_pull(components, keys):
    """|momentum| x evidence weight, summed over the pillars feeding one corner.

    This is the engine's own aggregation term, taken in magnitude. A pillar the company has no
    evidence for contributes 0 — correctly, because it genuinely carries none of the story.
    """
    total = 0.0
    for key in keys:
        block = (components or {}).get(key)
        if not isinstance(block, dict):
            continue
        mom = block.get("momentum")
        weight = block.get("weight")
        if isinstance(mom, (int, float)) and isinstance(weight, (int, float)):
            total += abs(float(mom)) * float(weight)
    return total


def _pillar_direction(components, keys):
    """Which way the pillars feeding one corner point, weighted. -1, 0 or +1; None when silent."""
    num = den = 0.0
    for key in keys:
        block = (components or {}).get(key)
        if not isinstance(block, dict):
            continue
        mom = block.get("momentum")
        weight = block.get("weight")
        if isinstance(mom, (int, float)) and isinstance(weight, (int, float)):
            num += float(mom) * float(weight)
            den += float(weight)
    if not den:
        return None
    avg = num / den
    return 1 if avg > 0 else -1 if avg < 0 else 0


def shares(record, price_pct):
    """Where one company's movement sits across Profit / People / Planet. Pure.

    `record` is a FULL engine record (its `components` carry per-pillar weight, which the board's
    compact summary strips). `price_pct` is the 12-1 reading, or None.

    Returns a dict that ALWAYS carries `known`. When `known` is False the shares are None and
    `missing` names the axes we could not read — never a zero share, which would silently
    redistribute a missing axis into the other two and put the dot somewhere unmeasured.
    """
    components = (record or {}).get("components") or {}
    if not _weighted_shape(components):
        return {
            "known": False, "missing": ["components"],
            "planet": None, "people": None, "profit": None,
            "directions": {}, "lean": "", "basis": BASIS,
            "why": ("This needs the FULL engine record — the board's compact summary flattens "
                    "`components` to a momentum per pillar and drops the evidence weight the "
                    "shares are built from."),
        }
    missing = []

    planet = _pillar_pull(components, CORNERS["planet"])
    people = _pillar_pull(components, CORNERS["people"])
    if not (record or {}).get("signal_count"):
        missing.append("evidence")

    if price_pct is None:
        missing.append("price")
        profit = 0.0
    else:
        profit = min(1.0, abs(float(price_pct)) / PROFIT_FULL_SCALE)

    total = planet + people + profit
    if missing or total <= 0:
        return {
            "known": False,
            "missing": missing or ["movement"],
            "planet": None, "people": None, "profit": None,
            "directions": {}, "lean": "", "basis": BASIS,
            "why": _why_unknown(missing, total),
        }

    # Rounded shares must still sum to EXACTLY 1, or the barycentric placement is off and a
    # composition quietly stops being one. The residual is absorbed by the last share rather
    # than left to float: at 4dp that is a correction of at most 1e-4, and the invariant a
    # ternary plot depends on is worth more than the last digit of one share.
    p_planet = round(planet / total, 4)
    p_people = round(people / total, 4)
    out = {
        "known": True,
        "missing": [],
        "planet": p_planet,
        "people": p_people,
        "profit": round(1.0 - p_planet - p_people, 4),
        "directions": {
            "planet": _pillar_direction(components, CORNERS["planet"]),
            "people": _pillar_direction(components, CORNERS["people"]),
            # The price direction is the SIGNED reading, unlike the share above it.
            "profit": (1 if price_pct > 0 else -1 if price_pct < 0 else 0),
        },
        "basis": BASIS,
        "why": "",
    }
    out["lean"] = max(("planet", "people", "profit"), key=lambda k: out[k])
    return out


def _why_unknown(missing, total):
    if "price" in missing and "evidence" in missing:
        return ("Neither axis can be read for this company — no quotable listing and no scorable "
                "evidence — so there is no mix to place.")
    if "price" in missing:
        return ("No quotable listing, so the Profit axis is unmeasured. Sharing the other two "
                "over a missing third would inflate both and put the dot somewhere no "
                "measurement supports, so it is not plotted.")
    if "evidence" in missing:
        return ("No scorable evidence yet, so Planet and People are unmeasured. An absence of "
                "evidence is a finding, not a mix.")
    if total <= 0:
        return "Every reading for this company is flat, so there is no movement to apportion."
    return ""


def cohort(records, price_of):
    """`{company_id: shares(...)}` for a whole run. `price_of(cid)` returns the 12-1 pct or None."""
    return {cid: shares(rec, price_of(cid)) for cid, rec in (records or {}).items()}


# --------------------------------------------------------------------------- #
#  THE OUTLOOK — a published base rate, NOT a prediction
# --------------------------------------------------------------------------- #
#: Holding period -> which of CGSI's three measured horizons speaks to it.
HORIZON_FOR = {"under_2y": "1y", "2_5y": "3y", "5y_plus": "5y"}

#: What this panel is, said once and carried onto every payload it produces.
#:
#: The ask was a "financial momentum prediction". This product cannot make one and will not
#: pretend to: HARD RULE 4 forbids a buy/sell/hold or a score, and nothing in this repo could
#: back a forecast anyway — there is a dated price snapshot and dated documentary evidence, and
#: no forward-return series to fit a model on or validate one against. A number produced without
#: that is not a prediction, it is an invention with a percent sign, and a confident statistic
#: beside a real chart is precisely what a stale rating looks like from the outside.
#:
#: What CAN be said is what somebody has already measured and published. CGSI report how often an
#: ESG improver in this basket beat the index over each horizon. That is a HISTORICAL FREQUENCY
#: for a basket, it is attributed to them, and it comes with their own warning that it does not
#: transfer to a single stock — which is printed with it rather than beneath a fold.
NOT_A_FORECAST = (
    "A published base rate, not a prediction. This is how often an ESG improver in CGSI's basket "
    "beat the index over this horizon historically — it is not a probability for this company, "
    "and nothing here forecasts a price."
)


def outlook(holding, record=None, dual_row=None):
    """CGSI's published base rate for a holding period, plus this company's two directions.

    Returns `{available, horizon, rate, caveat, source, not_a_forecast, context}`. Never a
    probability we computed, never a target, never a recommendation.
    """
    figs = _figures()
    perf = (figs.get("performance") or {}).get("single_stock_caveat") or {}
    rates = perf.get("probability_an_improver_beats_the_index") or {}
    key = HORIZON_FOR.get(holding or "", "3y")
    rate = rates.get(key)
    src = figs.get("source") or {}

    context = []
    if dual_row and dual_row.get("alignment") not in (None, "", "unknown"):
        context.append(dual_row.get("display", ""))
    if record is not None and record.get("signal_count"):
        context.append(f"{record['signal_count']} dated signals behind the evidence read")

    return {
        "available": bool(rate),
        "horizon": key,
        "horizons": {k: rates.get(k) for k in ("1y", "3y", "5y")},
        "rate": rate,
        "caveat": perf.get("text", ""),
        "source": {
            "publisher": src.get("publisher", ""),
            "title": src.get("title", ""),
            "date": src.get("date", ""),
        },
        "not_a_forecast": NOT_A_FORECAST,
        "context": context,
    }


if __name__ == "__main__":  # pragma: no cover - developer convenience
    import engine
    import engine_config
    import harvest
    import price_momentum
    import universe
    import company_metadata

    cfg = engine_config.for_horizon("long")
    path = universe.active_file(False)
    cons = harvest.apply_overlay(universe.constituents(path))
    run = engine.run_engine(cons, metadata=company_metadata.load(demo=False), config=cfg)
    recs = {r["company_id"]: r for r in run["records"]}
    got = cohort(recs, lambda cid: (price_momentum.momentum(cid) or {}).get("pct"))
    known = [(c, s) for c, s in got.items() if s["known"]]
    print(f"{len(known)} of {len(got)} placeable\n")
    for cid, s in sorted(known, key=lambda kv: -kv[1]["profit"])[:12]:
        print(f"  {cid:14} planet {s['planet']:.2f}  people {s['people']:.2f}  "
              f"profit {s['profit']:.2f}  -> {s['lean']}")
    print()
    print(json.dumps(outlook("2_5y"), indent=1)[:700])
