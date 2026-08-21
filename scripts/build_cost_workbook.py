"""
build_cost_workbook.py — write the cost model as a real, calculating Excel workbook.
====================================================================================

The pack's `ESG_Radar_Cost_and_Scale_Model.xlsx` is a skeleton: labels, a colour convention, and
prose descriptions of formulas. It contains no formulas and no values, so nothing calculates and
nothing can be sensitivity-tested. This writes the version that does.

Every number lands in one of three states, and the workbook shows which by colour — the same
convention the original README sets out, now actually applied:

    BLUE   an input. Changeable. Carries a Source on its own row.
    BLACK  a formula. Excel computes it; overwrite it and the model stops meaning anything.
    AMBER  still needed. The cell is EMPTY, not filled with a placeholder, because a plausible
           number in a cost model is worse than a blank one — a blank gets asked about.

Inputs come from files, never from this script's imagination:
    data/sg_day_rates.json    live MyCareersFuture postings   (scripts/sg_day_rates.py)
    data/harvest_cost.json    measured tokens per company     (harvest.py --cost)
    engine + basket           company counts

Prices are arguments, as everywhere else in this repo — see `cost_model.py` for why.

    python -m scripts.build_cost_workbook --price-hit 0.007 --price-miss 0.22 --price-out 0.66
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, "data", "ESG_Radar_Cost_Model_filled.xlsx")

BLUE = "0000CC"      # an input
BLACK = "000000"     # a formula
AMBER = "B06F06"     # still needed
AMBER_FILL = "FFF3D6"


def _load(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        raise SystemExit("Missing %s — %s" % (os.path.relpath(path, BASE_DIR), what))


def build(price_hit, price_miss, price_out, fx, sweeps, cache_hit):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    rates = _load(os.path.join(BASE_DIR, "data", "sg_day_rates.json"),
                  "run `python -m scripts.sg_day_rates --write`")
    tokens = _load(os.path.join(BASE_DIR, "data", "harvest_cost.json"),
                   "run `python harvest.py --cost`")
    by_key = {r["key"]: r for r in rates["roles"]}

    wb = Workbook()
    head = Font(bold=True, size=12)
    sub = Font(italic=True, size=9, color="666666")
    inp = Font(color=BLUE)
    fml = Font(color=BLACK, bold=False)
    need = Font(color=AMBER, bold=True)
    fill = PatternFill("solid", fgColor=AMBER_FILL)
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(title, widths):
        ws = wb.create_sheet(title)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + i)].width = w
        return ws

    # ---------------- README ----------------
    ws = wb.active
    ws.title = "README"
    ws.column_dimensions["A"].width = 110
    lines = [
        ("ESG Momentum Radar — Cost & Scale Model (CALCULATING VERSION)", head),
        ("Built by scripts/build_cost_workbook.py. Re-run it to refresh; do not hand-edit, "
         "the inputs live in files.", sub),
        ("", None),
        ("COLOUR CONVENTION", head),
        ("BLUE   = an input you can change. Every input row carries its Source.", None),
        ("BLACK  = a formula. Excel computes it. Overwriting one breaks the model.", None),
        ("AMBER + shaded = still needed. Left EMPTY on purpose — a plausible number in a cost "
         "model is worse than a blank one, because a blank gets asked about.", None),
        ("", None),
        ("WHAT CHANGED FROM THE SKELETON", head),
        ("The skeleton assumed 40 signals/company/month at 1,500 tokens/signal. That describes a "
         "system where a model does the scoring. This one does not: scoring is rule-based and "
         "costs ZERO tokens. All LLM cost is in GATHERING evidence, charged per SWEEP of a "
         "company, not per signal. The Unit Economics tab is built on the measured figure.", None),
        ("", None),
        ("THE TWO MONEY STORIES — never mix them", head),
        ("PILOT ASK (commercial): what the pilot costs at real market rates. Pilot Cost tab.", None),
        ("HACKATHON ACTUALS: what the team is really spending this semester. Separate tab.", None),
        ("", None),
        ("SOURCES BEHIND THE FILLED CELLS", head),
        ("Day rates: live MyCareersFuture postings (Workforce Singapore), median advertised "
         "monthly midpoint, grossed up by 17% employer CPF, over 260 working days. "
         "NOT a contractor/agency rate — an agency rate carries a margin on top.", None),
        ("Tokens: measured over a full %d-company harvest sweep (harvest.py --cost)."
         % tokens["companies"], None),
        ("LLM prices: supplied at build time from the provider's published card. This model "
         "never guesses a price.", None),
    ]
    for i, (text, font) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=text)
        if font:
            c.font = font
        c.alignment = wrap

    # ---------------- Assumptions ----------------
    ws = sheet("Assumptions", [42, 14, 12, 78])
    ws["A1"], ws["A1"].font = "ASSUMPTIONS — the only tab you edit", head
    ws["A2"], ws["A2"].font = ("Blue = input. Amber + shaded = still needed, deliberately left "
                               "empty.", sub)
    r = 4
    for hdr, col in zip(("Assumption", "Value", "Unit", "Source / note"), "ABCD"):
        ws["%s%d" % (col, r)] = hdr
        ws["%s%d" % (col, r)].font = head
    r += 1

    def row(label, value, unit, source, state="input"):
        nonlocal r
        ws.cell(row=r, column=1, value=label).alignment = wrap
        c = ws.cell(row=r, column=2, value=value)
        ws.cell(row=r, column=3, value=unit)
        s = ws.cell(row=r, column=4, value=source)
        s.alignment = wrap
        if state == "need":
            c.font, c.fill, s.font = need, fill, need
        elif state == "formula":
            c.font = fml
        else:
            c.font = inp
        r += 1
        return r - 1

    ws.cell(row=r, column=1, value="PEOPLE — pilot team").font = head
    r += 1
    rate_rows = {}
    for key, label in (("data_ml_engineer", "Data / ML engineer — day rate"),
                       ("fullstack_engineer", "Full-stack engineer — day rate"),
                       ("esg_analyst", "Domain / ESG analyst — day rate"),
                       ("project_manager", "Project manager — day rate")):
        rr = by_key[key]
        note = "MyCareersFuture: median of %d postings (%d matched), %s/mo x 12 x 1.17 / 260" % (
            rr["postings_sampled"], rr["postings_matching_search"],
            f"S${rr['median_monthly_sgd']:,}")
        if rr.get("caveat"):
            note += "  !! " + rr["caveat"][:180]
        rate_rows[key] = row(label, rr["day_rate_sgd"], "SGD/day", note)
    dur = row("Pilot duration", 6, "weeks", "Buyer journey — pilot stage is 6 weeks")
    dpw = row("Working days per week", 5, "days", "Standard")
    fte = {}
    for key, label, v in (("data_ml_engineer", "Data/ML engineer — FTE", 1),
                          ("fullstack_engineer", "Full-stack — FTE", 1),
                          ("esg_analyst", "Domain analyst — FTE", 0.5),
                          ("project_manager", "PM — FTE", 0.5)):
        fte[key] = row(label, v, "FTE", "Team plan")

    ws.cell(row=r, column=1, value="DATA & LICENSING").font = head
    r += 1
    lseg_row = row("LSEG / baseline ESG feed — pilot", None, "SGD total",
                   "NEEDS QUOTE — enquiry to LSEG/CGSI, no reply. If none, model from "
                   "comparables and SAY SO on the slide.", "need")
    jobs_row = row("Licensed job-posting feed", None, "SGD total",
                   "NEEDS QUOTE — licensed feeds only, no scraping.", "need")
    row("Exchange filings (SGX/Bursa/IDX/SET/PSE)", 0, "SGD total", "Free — public portals")
    row("Patent data (EPO OPS free tier)", 0, "SGD total", "Free tier")
    row("Industry benchmark (Eurostat)", 0, "SGD total",
        "Free, keyless — env_ac_aeint_r2. All 22 rows reproduce live.")

    ws.cell(row=r, column=1, value="INFRASTRUCTURE & INFERENCE").font = head
    r += 1
    cloud = row("Cloud hosting & storage — pilot", 2000, "SGD total",
                "Slide 16 figure. Cross-check vs the ~S$52/semester Alibaba actual.")
    tok_p = row("Prompt tokens per company per SWEEP",
                tokens["avg_prompt_tokens_per_company"], "tokens",
                "MEASURED over %d companies (harvest.py --cost)" % tokens["companies"])
    tok_o = row("Output tokens per company per SWEEP",
                tokens["avg_output_tokens_per_company"], "tokens",
                "MEASURED — never discounted by the cache")
    cache_share = row("Cacheable prompt share", tokens["cacheable_prompt_share"] / 100.0, "share",
                      "MEASURED — the byte-identical system prompt, %s%% of the prompt"
                      % tokens["cacheable_prompt_share"])
    hit = row("Cache hit rate on the cacheable share", cache_hit, "share",
              "Assumption. Applies ONLY to the cacheable share, never to output.")
    sweeps_row = row("Sweeps per company per month", sweeps, "sweeps",
                     "Cadence decision — 4 = weekly")
    row("Tokens per signal (SCORING path)", 0, "tokens",
        "MEASURED — structurally zero. signals.py routes by rule, engine.py scores "
        "deterministically; no LLM is reachable from either.")
    p_hit = row("Price — 1M input, cache HIT", price_hit, "USD",
                "Provider published card. SUPPLIED at build time; never guessed.")
    p_miss = row("Price — 1M input, cache MISS", price_miss, "USD", "Provider published card")
    p_out = row("Price — 1M output", price_out, "USD", "Provider published card")
    fx_row = row("USD:SGD", fx, "rate", "Set to the rate used on the slide")

    ws.cell(row=r, column=1, value="COVERAGE").font = head
    r += 1
    n_pilot = row("Companies covered — pilot", 52, "companies", "The CGSI verified basket")
    n_y1 = row("Companies covered — Year 1", 500, "companies", "Scenario lever")
    n_y3 = row("Companies covered — Year 3", 2000, "companies", "Scenario lever")

    A = lambda rw: "Assumptions!$B$%d" % rw          # noqa: E731 — a local alias, read once

    # ---------------- Pilot Cost ----------------
    ws = sheet("Pilot Cost", [40, 16, 74])
    ws["A1"], ws["A1"].font = "PILOT COST — bottom-up, commercial rates", head
    ws["A2"], ws["A2"].font = ("Calculates from Assumptions. Amber rows are blank until a quote "
                               "arrives.", sub)
    pr = 4
    for hdr, col in zip(("Line", "SGD", "Basis"), "ABC"):
        ws["%s%d" % (col, pr)] = hdr
        ws["%s%d" % (col, pr)].font = head
    pr += 1
    ws.cell(row=pr, column=1, value="PEOPLE").font = head
    pr += 1
    people_first = pr
    for key, label in (("data_ml_engineer", "Data / ML engineer"),
                       ("fullstack_engineer", "Full-stack engineer"),
                       ("esg_analyst", "Domain / ESG analyst"),
                       ("project_manager", "Project manager")):
        ws.cell(row=pr, column=1, value=label)
        ws.cell(row=pr, column=2,
                value="=%s*%s*%s*%s" % (A(rate_rows[key]), A(dur), A(dpw), A(fte[key]))).font = fml
        ws.cell(row=pr, column=3, value="day rate x weeks x days/week x FTE").alignment = wrap
        pr += 1
    people_sub = pr
    ws.cell(row=pr, column=1, value="People subtotal").font = head
    ws.cell(row=pr, column=2, value="=SUM(B%d:B%d)" % (people_first, pr - 1)).font = fml
    pr += 2

    ws.cell(row=pr, column=1, value="DATA & LICENSING").font = head
    pr += 1
    data_first = pr
    for label, ref in (("LSEG / baseline ESG feed", lseg_row), ("Licensed job-posting feed", jobs_row)):
        ws.cell(row=pr, column=1, value=label)
        c = ws.cell(row=pr, column=2, value="=%s" % A(ref))
        c.font, c.fill = need, fill
        ws.cell(row=pr, column=3, value="from Assumptions — BLANK until a quote arrives").alignment = wrap
        pr += 1
    ws.cell(row=pr, column=1, value="Free sources (filings, patents, Eurostat)")
    ws.cell(row=pr, column=2, value=0).font = fml
    ws.cell(row=pr, column=3, value="free by design")
    pr += 1
    data_sub = pr
    ws.cell(row=pr, column=1, value="Data subtotal").font = head
    ws.cell(row=pr, column=2, value="=SUM(B%d:B%d)" % (data_first, pr - 1)).font = fml
    pr += 2

    ws.cell(row=pr, column=1, value="INFRASTRUCTURE & INFERENCE").font = head
    pr += 1
    infra_first = pr
    ws.cell(row=pr, column=1, value="Cloud hosting & storage")
    ws.cell(row=pr, column=2, value="=%s" % A(cloud)).font = fml
    ws.cell(row=pr, column=3, value="from Assumptions")
    pr += 1
    ws.cell(row=pr, column=1, value="LLM inference — pilot window")
    ws.cell(row=pr, column=2,
            value=("=%s*'Unit Economics'!$B$9*%s*1.5" % (A(n_pilot), A(sweeps_row)))).font = fml
    ws.cell(row=pr, column=3,
            value="companies x SGD per company per sweep x sweeps/month x 1.5 months "
                  "(the 6-week pilot)").alignment = wrap
    pr += 1
    infra_sub = pr
    ws.cell(row=pr, column=1, value="Infrastructure subtotal").font = head
    ws.cell(row=pr, column=2, value="=SUM(B%d:B%d)" % (infra_first, pr - 1)).font = fml
    pr += 2

    ws.cell(row=pr, column=1, value="COMPLIANCE & OTHER").font = head
    pr += 1
    comp_first = pr
    for label in ("Legal review", "Professional indemnity insurance"):
        ws.cell(row=pr, column=1, value=label)
        c = ws.cell(row=pr, column=2)
        c.font, c.fill = need, fill
        ws.cell(row=pr, column=3, value="NEEDS A QUOTE").font = need
        pr += 1
    comp_sub = pr
    ws.cell(row=pr, column=1, value="Compliance subtotal").font = head
    ws.cell(row=pr, column=2, value="=SUM(B%d:B%d)" % (comp_first, pr - 1)).font = fml
    pr += 2
    ws.cell(row=pr, column=1, value="TOTAL — fully loaded pilot").font = head
    ws.cell(row=pr, column=2,
            value="=B%d+B%d+B%d+B%d" % (people_sub, data_sub, infra_sub, comp_sub)).font = fml
    ws.cell(row=pr, column=3,
            value="INCOMPLETE while the amber rows are blank. Say so on the slide rather than "
                  "presenting this as the fully-loaded number.").alignment = wrap
    ws.cell(row=pr, column=3).font = need

    # ---------------- Unit Economics ----------------
    ws = sheet("Unit Economics", [46, 18, 76])
    ws["A1"], ws["A1"].font = "UNIT ECONOMICS — cost to cover one company", head
    ws["A2"], ws["A2"].font = ("Inference only. Excludes the fixed data licence — that is the "
                               "cost which falls per company as clients are added.", sub)
    ur = 4
    for hdr, col in zip(("Metric", "Value", "Basis"), "ABC"):
        ws["%s%d" % (col, ur)] = hdr
        ws["%s%d" % (col, ur)].font = head
    rows_ue = [
        ("Prompt tokens billed at HIT price",
         "=%s*%s*%s" % (A(tok_p), A(cache_share), A(hit)),
         "prompt x cacheable share x hit rate"),
        ("Prompt tokens billed at MISS price",
         "=%s-B5" % A(tok_p),
         "everything in the prompt the cache did not serve"),
        ("Output tokens per sweep", "=%s" % A(tok_o),
         "MEASURED — never discounted by the cache"),
        ("USD per company per sweep",
         "=(B5/1000000*%s)+(B6/1000000*%s)+(B7/1000000*%s)" % (A(p_hit), A(p_miss), A(p_out)),
         "a cache HIT is a cheaper RATE, not free — priced separately, never written off"),
        ("SGD per company per sweep", "=B8*%s" % A(fx_row), "USD x FX"),
        ("SGD per company per MONTH", "=B9*%s" % A(sweeps_row), "x sweeps per month"),
        ("SGD per company per YEAR", "=B10*12", "x 12"),
    ]
    ur = 5
    for label, val, basis in rows_ue:
        ws.cell(row=ur, column=1, value=label)
        ws.cell(row=ur, column=2, value=val).font = fml if isinstance(val, str) else inp
        ws.cell(row=ur, column=3, value=basis).alignment = wrap
        ur += 1
    ur += 1
    for note in (
        "The data licence is a FIXED cost shared across all clients. Inference is the only truly "
        "variable cost, and it is linear in companies.",
        "So the marginal-cost-per-company line is FLAT on inference alone. It falls only once the "
        "fixed licence is spread across clients — which cannot be charted until a quote exists. "
        "Drawing a falling line before then is drawing the conclusion first.",
    ):
        c = ws.cell(row=ur, column=1, value=note)
        c.alignment, c.font = wrap, sub
        ur += 1

    # ---------------- Scale Scenarios ----------------
    ws = sheet("Scale Scenarios", [42, 16, 16, 16, 62])
    ws["A1"], ws["A1"].font = "SCALE SCENARIOS — annual run-rate", head
    ws["A2"], ws["A2"].font = ("Annual run-rate, including the Pilot column. The Pilot Cost tab "
                               "is a 6-week spend — a different basis. Do not compare totals.", sub)
    sr = 4
    for hdr, col in zip(("Metric", "Pilot", "Year 1", "Year 3", "Basis"), "ABCDE"):
        ws["%s%d" % (col, sr)] = hdr
        ws["%s%d" % (col, sr)].font = head
    sr = 5
    ws.cell(row=sr, column=1, value="Companies covered")
    for col, ref in zip("BCD", (n_pilot, n_y1, n_y3)):
        ws["%s%d" % (col, sr)] = "=%s" % A(ref)
        ws["%s%d" % (col, sr)].font = fml
    ws.cell(row=sr, column=5, value="from Assumptions")
    sr += 1
    ws.cell(row=sr, column=1, value="Inference (SGD/yr)")
    for col in "BCD":
        ws["%s%d" % (col, sr)] = "=%s5*'Unit Economics'!$B$11" % col
        ws["%s%d" % (col, sr)].font = fml
    ws.cell(row=sr, column=5, value="companies x SGD per company per year").alignment = wrap
    sr += 1
    for label in ("People (SGD/yr)", "Data & licensing (SGD/yr)", "Cloud & infra (SGD/yr)"):
        ws.cell(row=sr, column=1, value=label)
        for col in "BCD":
            c = ws["%s%d" % (col, sr)]
            c.font, c.fill = need, fill
        ws.cell(row=sr, column=5,
                value="NEEDS headcount plan + licence quote").font = need
        sr += 1
    total_row = sr
    ws.cell(row=sr, column=1, value="Total cost (SGD/yr)").font = head
    for col in "BCD":
        ws["%s%d" % (col, sr)] = "=SUM(%s6:%s9)" % (col, col)
        ws["%s%d" % (col, sr)].font = fml
    sr += 2
    ws.cell(row=sr, column=1, value="Marginal cost per company — INFERENCE ONLY").font = head
    for col in "BCD":
        ws["%s%d" % (col, sr)] = "='Unit Economics'!$B$11"
        ws["%s%d" % (col, sr)].font = fml
    c = ws.cell(row=sr, column=5,
                value="FLAT by construction — inference is linear in companies. This is NOT the "
                      "falling chart; that needs the fixed licence spread across clients.")
    c.alignment, c.font = wrap, need
    sr += 1
    ws.cell(row=sr, column=1, value="Total cost per company (SGD/yr)").font = head
    for col in "BCD":
        ws["%s%d" % (col, sr)] = "=%s%d/%s5" % (col, total_row, col)
        ws["%s%d" % (col, sr)].font = fml
    ws.cell(row=sr, column=5,
            value="THIS is the line that falls — once People and Data are filled.").alignment = wrap

    # ---------------- Hackathon Actuals ----------------
    ws = sheet("Hackathon Actuals", [50, 14, 62])
    ws["A1"], ws["A1"].font = "HACKATHON ACTUALS — what the team is really spending", head
    ws["A2"], ws["A2"].font = ("Never mix with the commercial pilot ask. Label both wherever "
                               "they appear.", sub)
    hr = 4
    for hdr, col in zip(("Line", "SGD", "Source"), "ABC"):
        ws["%s%d" % (col, hr)] = hdr
        ws["%s%d" % (col, hr)].font = head
    hr = 5
    for label, val, src in (
            ("Alibaba Cloud hosting (2 vCPU / 2GB), semester", 52, "Methodology Appendix A"),
            ("Bandwidth / storage buffer", 13, "Methodology Appendix A"),
            ("DeepSeek credits — dev + demo", 19, "Methodology Appendix A"),
            ("Public demo domain + SSL (one-time)", 19, "Methodology Appendix A"),
            ("Testnet anchoring gas", 0, "Testnet — effectively zero")):
        ws.cell(row=hr, column=1, value=label)
        ws.cell(row=hr, column=2, value=val).font = inp
        ws.cell(row=hr, column=3, value=src).alignment = wrap
        hr += 1
    ws.cell(row=hr, column=1, value="Subtotal").font = head
    ws.cell(row=hr, column=2, value="=SUM(B5:B%d)" % (hr - 1)).font = fml
    hr += 1
    ws.cell(row=hr, column=1, value="Contingency @ 15%")
    ws.cell(row=hr, column=2, value="=B%d*0.15" % (hr - 1)).font = fml
    hr += 1
    ws.cell(row=hr, column=1, value="TOTAL — hackathon actuals").font = head
    ws.cell(row=hr, column=2, value="=B%d+B%d" % (hr - 2, hr - 1)).font = fml

    # ---------------- Pricing & Ask ----------------
    ws = sheet("Pricing & Ask", [44, 18, 18, 62])
    ws["A1"], ws["A1"].font = "PRICING & THE FUNDING ASK", head
    ws["A2"], ws["A2"].font = ("Two cells here are business DECISIONS, not lookups. They stay "
                               "blank until somebody decides.", sub)
    qr = 4
    for hdr, col in zip(("Metric", "Year 1", "Year 3", "Note"), "ABCD"):
        ws["%s%d" % (col, qr)] = hdr
        ws["%s%d" % (col, qr)].font = head
    qr = 5
    ws.cell(row=qr, column=1, value="Annual price per firm (SGD)")
    for col in "BC":
        c = ws["%s%d" % (col, qr)]
        c.font, c.fill = need, fill
    ws.cell(row=qr, column=4,
            value="NEEDS A NUMBER — anchor to a public ESG subscription comparable and cite "
                  "it.").font = need
    qr += 1
    ws.cell(row=qr, column=1, value="Customers")
    for col in "BC":
        c = ws["%s%d" % (col, qr)]
        c.font, c.fill = need, fill
    ws.cell(row=qr, column=4, value="NEEDS A PLAN").font = need
    qr += 1
    ws.cell(row=qr, column=1, value="Revenue")
    for col in "BC":
        ws["%s%d" % (col, qr)] = "=%s5*%s6" % (col, col)
        ws["%s%d" % (col, qr)].font = fml
    qr += 1
    ws.cell(row=qr, column=1, value="Total cost")
    ws["B%d" % qr] = "='Scale Scenarios'!C10"
    ws["C%d" % qr] = "='Scale Scenarios'!D10"
    for col in "BC":
        ws["%s%d" % (col, qr)].font = fml
    qr += 1
    ws.cell(row=qr, column=1, value="Margin").font = head
    for col in "BC":
        ws["%s%d" % (col, qr)] = "=%s7-%s8" % (col, col)
        ws["%s%d" % (col, qr)].font = fml
    qr += 2
    ws.cell(row=qr, column=1, value="THE ASK").font = head
    qr += 1
    for label, val, note in (
            ("Amount requested (SGD)", "='Pilot Cost'!B%d" % pr,
             "Defaults to the fully-loaded pilot — which is INCOMPLETE until the amber rows fill"),
            ("Months it funds", 6, "Pilot duration"),
            ("Milestone it buys", None,
             "NEEDS A SPECIFIC, CHECKABLE MILESTONE — not 'build the product'")):
        ws.cell(row=qr, column=1, value=label)
        c = ws.cell(row=qr, column=2, value=val)
        if val is None:
            c.font, c.fill = need, fill
            ws.cell(row=qr, column=4, value=note).font = need
        else:
            c.font = fml if isinstance(val, str) else inp
            ws.cell(row=qr, column=4, value=note).alignment = wrap
        qr += 1

    wb.save(OUT)
    return OUT


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-hit", type=float, required=True)
    ap.add_argument("--price-miss", type=float, required=True)
    ap.add_argument("--price-out", type=float, required=True)
    ap.add_argument("--fx", type=float, default=1.35)
    ap.add_argument("--sweeps", type=float, default=4.0)
    ap.add_argument("--cache-hit", type=float, default=0.9)
    a = ap.parse_args(argv)
    path = build(a.price_hit, a.price_miss, a.price_out, a.fx, a.sweeps, a.cache_hit)
    print("wrote %s" % os.path.relpath(path, BASE_DIR))
    print("Formulas calculate on open. Amber cells are EMPTY on purpose — they are the ones to "
          "chase.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
