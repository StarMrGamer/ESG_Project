"""
sg_day_rates.py — blended day rates for the pilot cost, from real Singapore job postings.
=========================================================================================

`ESG_Radar_Cost_and_Scale_Model.xlsx` marks four day-rate cells "NEEDS SOURCE: MyCareersFuture
or Michael Page SG salary guide 2026". This takes the first of those literally.

MyCareersFuture is run by Workforce Singapore. Its public API returns live postings with the
salary range the employer actually advertised — not a consultancy's survey, not a band somebody
remembers. Every rate this produces traces to a query anyone can re-run.

    https://api.mycareersfuture.gov.sg/v2/jobs?search=<role>&limit=<n>

HOW A MONTHLY SALARY BECOMES A DAY RATE
---------------------------------------
    cost per working day = monthly salary x 12 x (1 + employer CPF) / working days per year

and each of those three moves is a decision, so each is stated rather than buried:

* **The salary** is the MIDPOINT of the advertised range, and we report the median midpoint
  across postings rather than the mean — one director-level posting inside a search for
  "data engineer" otherwise drags the whole rate up.
* **Employer CPF** is 17%, the statutory rate for employees aged 55 and under earning above
  $750/month (CPF Board). It is a `--cpf` argument so a different assumption is visible.
* **Working days** default to 260 (52 x 5). Singapore has 11 gazetted public holidays, so the
  real figure is nearer 249 — dividing by the larger number makes every rate here a FLOOR by
  about 4%. Stated, not silently absorbed.

WHAT THIS IS NOT
----------------
It is not a contractor or agency day rate. This is the cost to employ someone permanently,
expressed per working day. An agency contract rate carries a margin on top, typically a large
one. If the pilot is staffed by contractors, these numbers are the wrong basis and the model
should say so on its face rather than quietly use them anyway.

Best-effort (rule 1): no network means no rates and an explicit reason, never a guessed number.

    python -m scripts.sg_day_rates                 # print the table
    python -m scripts.sg_day_rates --write         # write data/sg_day_rates.json
    python -m scripts.sg_day_rates --limit 60      # postings sampled per role
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(BASE_DIR, "data", "sg_day_rates.json")
API = "https://api.mycareersfuture.gov.sg/v2/jobs"

#: The four cells the workbook needs, and the search that fills each. Search terms are the
#: workbook's own role names, narrowed only where the plain term returns a different job
#: ("analyst" alone is dominated by finance roles).
ROLES = (
    ("data_ml_engineer", "Data / ML engineer", "data engineer", ""),
    ("fullstack_engineer", "Full-stack engineer", "full stack developer", ""),
    ("esg_analyst", "Domain / ESG analyst", "ESG",
     "WIDE SAMPLE, LOW MEDIAN. 'ESG' matches any posting mentioning it, including junior "
     "operations roles, which pulls the median down. Narrower terms return far higher rates on "
     "samples too small to trust: 'sustainability analyst' 2 postings at ~S$628/day, 'ESG "
     "analyst' 1 posting at ~S$594/day, 'sustainability manager' 8 at ~S$526/day. The true "
     "analyst rate is very likely ABOVE the figure shown here — treat it as a floor and check "
     "a salary guide before it reaches a slide."),
    ("project_manager", "Project manager", "project manager", ""),
)

#: CPF Board employer contribution rate, employees aged 55 and under earning > $750/month.
CPF_EMPLOYER = 0.17
CPF_SOURCE = "https://www.cpf.gov.sg/employer/employer-obligations/how-much-cpf-contributions-to-pay"
#: 52 weeks x 5 days. Singapore gazettes 11 public holidays, so the true figure is nearer 249 —
#: using the larger divisor makes every rate a floor. See the module docstring.
WORKING_DAYS = 260


def _median(values):
    vals = sorted(values)
    n = len(vals)
    if not n:
        return None
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def fetch_role(term, limit=50):
    """Advertised monthly salary midpoints for one search term. `[]` on any failure."""
    url = "%s?search=%s&limit=%d" % (API, core.urllib.parse.quote(term)
                                     if hasattr(core, "urllib") else term.replace(" ", "%20"),
                                     limit)
    try:
        payload = json.loads(core.http_get(url))
    except Exception:                                           # noqa: BLE001 — rule 1
        return [], 0
    total = payload.get("total", 0)
    out = []
    for job in payload.get("results") or []:
        sal = job.get("salary") or {}
        kind = ((sal.get("type") or {}).get("salaryType") or "").lower()
        lo, hi = sal.get("minimum"), sal.get("maximum")
        # Monthly only. A posting quoted hourly or annually is a different unit and mixing them
        # is how a median stops meaning anything.
        if kind != "monthly" or not lo or not hi:
            continue
        out.append((lo + hi) / 2.0)
    return out, total


def day_rate(monthly, cpf=CPF_EMPLOYER, working_days=WORKING_DAYS):
    return monthly * 12.0 * (1.0 + cpf) / working_days


def build(limit=50, cpf=CPF_EMPLOYER, working_days=WORKING_DAYS):
    rows = []
    for key, label, term, caveat in ROLES:
        mids, total = fetch_role(term, limit)
        med = _median(mids)
        rows.append({
            "key": key,
            "label": label,
            "search_term": term,
            "postings_sampled": len(mids),
            "postings_matching_search": total,
            "median_monthly_sgd": round(med) if med is not None else None,
            "day_rate_sgd": round(day_rate(med, cpf, working_days)) if med is not None else None,
            "source": "%s?search=%s&limit=%d" % (API, term.replace(" ", "%20"), limit),
            "caveat": caveat,
        })
    return {
        "_note": ("Blended day rates derived from LIVE MyCareersFuture postings (Workforce "
                  "Singapore). Median midpoint of the advertised monthly range, grossed up by "
                  "employer CPF, divided by working days. Every rate re-runs from the URL on "
                  "its own row."),
        "_formula": "monthly x 12 x (1 + employer_cpf) / working_days_per_year",
        "_basis": {
            "employer_cpf": cpf,
            "employer_cpf_source": CPF_SOURCE,
            "working_days_per_year": working_days,
            "working_days_note": ("52 x 5. Singapore gazettes 11 public holidays, so the real "
                                  "figure is nearer 249 and these rates are a FLOOR by ~4%."),
            "salary_basis": "midpoint of the advertised range; MEDIAN across postings, not mean",
            "monthly_only": "hourly and annual postings are excluded, not converted",
        },
        "_not": ("NOT a contractor or agency day rate. This is permanent-employment cost per "
                 "working day; an agency rate carries a margin on top."),
        "roles": rows,
    }


def main(argv):
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 50
    cpf = float(argv[argv.index("--cpf") + 1]) if "--cpf" in argv else CPF_EMPLOYER
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else WORKING_DAYS

    model = build(limit, cpf, days)
    print("SINGAPORE BLENDED DAY RATES — live MyCareersFuture postings")
    print("  %s\n" % model["_formula"])
    print("  %-24s %8s %12s %11s  %s"
          % ("role", "postings", "median/mo", "day rate", "search term"))
    missing = []
    for r in model["roles"]:
        if r["day_rate_sgd"] is None:
            missing.append(r["label"])
            print("  %-24s %8s %12s %11s  %s"
                  % (r["label"][:24], "-", "-", "NOT FOUND", r["search_term"]))
            continue
        print("  %-24s %8d %12s %11s  %s"
              % (r["label"][:24], r["postings_sampled"],
                 "%,d" % r["median_monthly_sgd"] if False else f"{r['median_monthly_sgd']:,}",
                 f"{r['day_rate_sgd']:,}", r["search_term"]))
    for r in model["roles"]:
        if r.get("caveat"):
            print("\n  ! %s — %s" % (r["label"], r["caveat"]))
    b = model["_basis"]
    print("\n  employer CPF %.0f%% (%s)" % (b["employer_cpf"] * 100, "CPF Board"))
    print("  working days %d/yr — %s" % (b["working_days_per_year"], b["working_days_note"]))
    print("  %s" % model["_not"])
    if missing:
        print("\n  NO RATE FOR: %s — network unavailable or no monthly postings matched."
              % ", ".join(missing))

    if "--write" in argv:
        with open(OUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(model, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print("\nwrote %s" % os.path.relpath(OUT_FILE, BASE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
