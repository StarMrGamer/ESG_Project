"""
build_metadata_mock.py — regenerate `data/company_metadata_mock.csv` (A3's provisional file).
=============================================================================================
Ships the mock metadata the badges/tiers/pipeline filter need BEFORE CGSI's verified data lands,
under the frozen header. Deterministic (md5 of the ticker — no RNG), so re-running never churns
the file and the golden set stays stable.

What it will and will not write, per HARD RULE 2:

* **Fictional demo companies** (`data/demo_universe.json`) get full values. They are invented
  names in a set already labelled illustrative, so a generated green-bond tier is a prop, not a
  claim — and the row says so in `notes`.
* **The real 52** (`data/asean_universe.json`) get `classification=unknown`,
  `profitability_flag=unknown` and NO invented ISIN, reviewer or URL. Nobody has verified their
  green-bond status yet, so the file says exactly that and the UI paints "Unverified".

Every row is `is_provisional = TRUE`. Phase B1 replaces this file with the verified one
(`data/company_metadata.csv`, which takes precedence) — no code change, which is the whole
reason the schema froze early.

    python -m scripts.build_metadata_mock
"""

import csv
import hashlib
import os

import company_metadata
import universe

OUT_FILE = company_metadata.MOCK_FILE
ACCESS_DATE = "2026-08-15"          # the date this generator was authored; not a clock read

_BOND_BUCKETS = (("cbi_certified", 15), ("labelled_reviewed", 30),
                 ("labelled_unreviewed", 25), ("none", 30))


def _roll(ticker, salt, modulo=100):
    """Stable 0..modulo-1 draw for a ticker — the same value on every machine, forever."""
    digest = hashlib.md5(f"{ticker}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


_LOSS_BUCKETS = (("labelled_unreviewed", 30), ("none", 70))


def _bond_status(ticker, loss_making=False):
    """Loss-makers draw from a different distribution: an unprofitable issuer rarely carries a
    reviewed or CBI-certified label, which is exactly why the Aggressive tier looks for
    `green_bond_status = none` + traction rather than a bond credential."""
    roll = _roll(ticker, "bond")
    running = 0
    for status, share in (_LOSS_BUCKETS if loss_making else _BOND_BUCKETS):
        running += share
        if roll < running:
            return status
    return "none"


def _demo_row(c):
    ticker = c["ticker"]
    loss_making = _roll(ticker, "pnl") < 25
    status = _bond_status(ticker, loss_making)
    # Traction is only meaningful for a loss-maker, and it should agree with the rest of the
    # fictional company's story rather than being an independent coin-flip: a loss-maker whose
    # stored pillar momentum is net positive is the one showing traction.
    momentum = c.get("momentum") if isinstance(c.get("momentum"), dict) else {}
    traction = loss_making and sum(v for v in momentum.values()
                                   if isinstance(v, (int, float))) > 0
    labelled = status != "none"
    reviewed = status in ("cbi_certified", "labelled_reviewed")
    return {
        "company_id": ticker,
        "company_name": c.get("company", ""),
        "exchange_ticker": ticker.split(":")[-1],
        "industry": c.get("sector", ""),
        "is_provisional": "TRUE",
        "green_bond_issuer": "Y" if labelled else "N",
        "classification": status,
        "bond_isin": "",                      # never invent an identifier, not even for a prop
        "issue_date": f"{2019 + _roll(ticker, 'year', 6)}-{1 + _roll(ticker, 'mon', 12):02d}-15"
                      if labelled else "",
        "amount_currency": f"USD {50 + _roll(ticker, 'amt', 10) * 25}m" if labelled else "",
        "label": "green" if labelled else "",
        "icma_structure": "standard_use_of_proceeds" if labelled else "",
        "standard_claimed": ("CBI Climate Bonds Standard" if status == "cbi_certified"
                             else "ICMA GBP" if labelled else ""),
        "external_reviewer": "MOCK reviewer (fictional company)" if reviewed else "",
        "review_type": "SPO" if reviewed else "",
        "framework_url": "",
        "allocation_report": "Y" if reviewed else ("N" if labelled else ""),
        "sgx_recognised": "Y" if ticker.startswith("SGX") and labelled else "N",
        "profitability_flag": "loss_making" if loss_making else "profitable",
        "fy_minus1_net_income": "MOCK", "fy_minus2_net_income": "MOCK",
        "operating_cf_trend": "improving" if _roll(ticker, "cf") < 60 else "flat",
        "traction_flag": "Y" if traction else ("N" if loss_making else "n/a"),
        "traction_evidence": "MOCK — revenue growth two consecutive halves" if traction else "n/a",
        "source_url_1": "", "source_url_2": "",
        "verified_by": "generated (build_metadata_mock.py)",
        "access_date": ACCESS_DATE,
        "notes": "MOCK ROW — fictional demo company; values generated deterministically from the "
                 "ticker. Illustrative only, not disclosure and not a claim about any real issuer.",
    }


def _real_row(c):
    ticker = c["ticker"]
    return {
        **{k: "" for k in company_metadata.HEADER},
        "company_id": ticker,
        "company_name": c.get("company", ""),
        "exchange_ticker": ticker.split(":")[-1],
        "industry": c.get("sector", ""),
        "is_provisional": "TRUE",
        "green_bond_issuer": "unknown",
        "classification": "unknown",
        "profitability_flag": "unknown",
        "traction_flag": "n/a",
        "traction_evidence": "n/a",
        "verified_by": "",
        "access_date": "",
        "notes": "AWAITING VERIFICATION — no green-bond or profitability field has been verified "
                 "from primary sources for this issuer. Placeholder row so the join succeeds; "
                 "replaced wholesale by the verified file at Phase B1.",
    }


def build():
    rows = [_demo_row(c) for c in universe.constituents(universe.DEMO_FILE)]
    rows += [_real_row(c) for c in universe.constituents(universe.UNIVERSE_FILE)]
    rows.sort(key=lambda r: r["company_id"])
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(company_metadata.HEADER))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    written = build()
    demo = sum(1 for r in written if r["classification"] != "unknown")
    print(f"wrote {len(written)} rows -> {os.path.relpath(OUT_FILE, company_metadata.BASE_DIR)}")
    print(f"  {demo} fictional demo rows with values · {len(written) - demo} real rows awaiting "
          "verification · all is_provisional=TRUE")
