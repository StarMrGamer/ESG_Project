"""
company_metadata.py — A3: the green-bond / profitability metadata loader.
=========================================================================
Reads the verification CSV whose **header is a frozen contract**
(`D/green_bond_verification_template.csv`) and joins it onto the universe by `company_id`.
Everything the A4 badges, the A5 risk tiers and the A6 pipeline filter need about a company
that is NOT derivable from signals comes from here.

Three rules this module exists to enforce:

1. **Missing file or missing row must never break rendering** (A3). Both return an empty row;
   badges then render the PROVISIONAL / "awaiting verification" treatment instead of a value.
2. **The header is the contract.** A file whose columns drift is reported through
   `load_report()` — the loader still returns what it can, but the drift is visible rather
   than silently mis-joined. This is why Phase B1 ("swap the real CSV") needs no code change.
3. **`unknown` is not `none`.** `green_bond_status = "none"` is a verified finding (no labelled
   issue); `"unknown"` means nobody has checked yet. No risk tier ever matches `unknown` — the
   engine will not guess a company into a tier (HARD RULE 2).

`is_provisional = TRUE` marks a row as not-yet-verified; it mirrors the MOCK pattern used
elsewhere in the app, and the badge says so on screen.
"""

import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MOCK_FILE = os.path.join(DATA_DIR, "company_metadata_mock.csv")
REAL_FILE = os.path.join(DATA_DIR, "company_metadata.csv")      # Phase B1 drops this in
TEMPLATE_FILE = os.path.join(BASE_DIR, "D", "green_bond_verification_template.csv")

# The frozen schema (template header row, in order). Do not reorder without sign-off.
HEADER = (
    "company_id", "company_name", "exchange_ticker", "industry", "is_provisional",
    "green_bond_issuer", "classification", "bond_isin", "issue_date", "amount_currency",
    "label", "icma_structure", "standard_claimed", "external_reviewer", "review_type",
    "framework_url", "allocation_report", "sgx_recognised", "profitability_flag",
    "fy_minus1_net_income", "fy_minus2_net_income", "operating_cf_trend", "traction_flag",
    "traction_evidence", "source_url_1", "source_url_2", "verified_by", "access_date", "notes",
)

GREEN_BOND_STATUSES = ("cbi_certified", "labelled_reviewed", "labelled_unreviewed", "none")
PROFITABILITY_STATES = ("profitable", "loss_making", "unknown")

_TRUEY = ("true", "t", "yes", "y", "1")
_CACHE = {}          # path -> {"mtime", "rows", "report"}


def active_file(path=None):
    """The real verified CSV once Phase B1 lands, else the provisional mock, else the template.

    An EXPLICIT path is used or it is not — never silently replaced by a fallback. Falling back
    would mean a typo in the Phase B1 filename quietly serves mock rows while everyone believes
    they are looking at verified data, which is the one failure this whole module exists to
    prevent."""
    if path:
        return path if os.path.exists(path) else ""
    for candidate in (REAL_FILE, MOCK_FILE, TEMPLATE_FILE):
        if os.path.exists(candidate):
            return candidate
    return ""


def _truthy(value):
    return str(value or "").strip().lower() in _TRUEY


def _norm(row):
    """One CSV row -> the shape the rest of the app consumes. Unrecognised values become
    'unknown' rather than being coerced into a real status."""
    status = (row.get("classification") or "").strip().lower().replace(" ", "_")
    if status not in GREEN_BOND_STATUSES:
        status = "unknown"
    profitability = (row.get("profitability_flag") or "").strip().lower().replace(" ", "_")
    if profitability not in PROFITABILITY_STATES:
        profitability = "unknown"
    evidence_url = next((row.get(k) or "" for k in ("framework_url", "source_url_1", "source_url_2")
                         if (row.get(k) or "").strip().startswith("http")), "")
    return {
        **{k: (row.get(k) or "").strip() for k in HEADER if k in row},
        "green_bond_status": status,
        "profitability_flag": profitability,
        "is_provisional": _truthy(row.get("is_provisional")),
        "traction_flag": (row.get("traction_flag") or "").strip(),
        "has_traction": _truthy(row.get("traction_flag")),
        "evidence_url": evidence_url,
    }


def load(path=None):
    """`{company_id: normalised_row}`. Missing/unreadable file -> `{}` (never raises)."""
    return _load(path)[0]


def load_report(path=None):
    """`{path, rows, provisional, missing_columns, extra_columns, ok, note}` — what the loader
    actually found. The UI shows this as the data-provenance line under the badges."""
    return _load(path)[1]


def _load(path=None):
    target = active_file(path)
    if not target:
        return {}, {"path": "", "rows": 0, "provisional": 0, "missing_columns": list(HEADER),
                    "extra_columns": [], "ok": False,
                    "note": (f"Metadata CSV not found at {path} — no rows loaded (badges render "
                             "as unverified)." if path else "No metadata CSV found.")}
    try:
        mtime = os.path.getmtime(target)
    except OSError:
        mtime = 0.0
    hit = _CACHE.get(target)
    if hit and hit["mtime"] == mtime:
        return hit["rows"], hit["report"]

    rows, report = {}, {"path": os.path.relpath(target, BASE_DIR), "rows": 0, "provisional": 0,
                        "missing_columns": [], "extra_columns": [], "ok": True, "note": ""}
    try:
        with open(target, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            found = tuple(reader.fieldnames or ())
            report["missing_columns"] = [c for c in HEADER if c not in found]
            report["extra_columns"] = [c for c in found if c not in HEADER]
            for raw in reader:
                cid = (raw.get("company_id") or "").strip()
                if not cid or cid.upper().startswith("EXAMPLE"):
                    continue
                row = _norm(raw)
                if str(row.get("company_name", "")).upper().startswith("EXAMPLE"):
                    continue          # the template's self-documenting sample row
                rows[cid] = row
                if row["is_provisional"]:
                    report["provisional"] += 1
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        report.update(ok=False, note=f"Could not read metadata CSV: {exc}")
        rows = {}

    report["rows"] = len(rows)
    if report["missing_columns"]:
        report["ok"] = False
        report["note"] = ("Header drift — the frozen schema is missing "
                          f"{len(report['missing_columns'])} column(s); rows still loaded.")
    elif not report["note"]:
        report["note"] = (f"{report['rows']} rows, {report['provisional']} provisional "
                          "(awaiting verification).")
    _CACHE[target] = {"mtime": mtime, "rows": rows, "report": report}
    return rows, report


def row_for(company_id, rows=None):
    """One company's row, or `{}` — the shape every consumer must already tolerate."""
    return (rows if rows is not None else load()).get(company_id, {})


# --------------------------------------------------------------------------- #
#  A4 — the two badges. Pure presentation payloads; the UI just paints them.
# --------------------------------------------------------------------------- #
def green_bond_badge(row, cfg=None):
    """`{status, display, tone, rank, provisional, url, note}` for the green-bond badge.

    Four tiers (config `green_bond_tiers`), plus the PROVISIONAL treatment layered on top and
    an explicit 'unverified' state when we hold no row at all."""
    import engine_config
    cfg = cfg or engine_config.load()
    tiers = {k: v for k, v in cfg["green_bond_tiers"].items() if not k.startswith("_")}
    status = (row or {}).get("green_bond_status", "unknown")
    tier = tiers.get(status)
    if not tier:
        return {"status": "unknown", "display": "Unverified", "tone": "muted", "rank": 0,
                "provisional": True, "url": (row or {}).get("evidence_url", ""),
                "note": "No verified green-bond record yet — awaiting Phase B data."}
    provisional = bool((row or {}).get("is_provisional"))
    return {
        "status": status,
        "display": tier["display"] + (" · PROVISIONAL" if provisional else ""),
        "tone": "warn" if provisional else tier["tone"],
        "rank": tier["rank"],
        "provisional": provisional,
        "url": (row or {}).get("evidence_url", ""),
        "note": ("Provisional row — not yet verified against primary sources."
                 if provisional else (row or {}).get("review_type", "") or "Verified row."),
    }


def profitability_badge(row):
    """`{state, display, tone, traction, url, note}` — three states plus the traction pip that
    only ever appears on a loss-maker (A4)."""
    state = (row or {}).get("profitability_flag", "unknown")
    traction = bool((row or {}).get("has_traction")) and state == "loss_making"
    display = {"profitable": "Profitable", "loss_making": "Loss-making",
               "unknown": "Profitability unverified"}[state]
    tone = {"profitable": "good", "loss_making": "warn", "unknown": "muted"}[state]
    return {
        "state": state, "display": display, "tone": tone, "traction": traction,
        "url": (row or {}).get("source_url_2") or (row or {}).get("evidence_url", ""),
        "note": (row or {}).get("traction_evidence", "") if traction else
                (row or {}).get("operating_cf_trend", ""),
    }
