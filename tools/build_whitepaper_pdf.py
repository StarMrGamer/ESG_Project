import json as _json
import os as _os

# THE COUNTS ARE READ, NOT TYPED. This document shipped once quoting N/M/K 13 / 11 / 3 — real,
# but frozen on 2026-08-24, one run before the deep+quality sweep re-froze them at 13 / 10 / 1.
# The figures had been written out in prose, so re-freezing the run could not update them, and
# the same page also quoted "391 events" and "four Hidden Winners" from the NEWER run. Nothing
# about a mixed-run document looks wrong until someone asks to see the eleven pipeline names.
#
# So the table below is generated from `data/nmk_frozen.json`, and the run id it came from is
# stamped in the footer. A stale figure is now either impossible or visible.
def _frozen():
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "data",
                         "nmk_frozen.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = _json.load(fh)
        c = d.get("counts") or {}
        return {"N": c.get("N"), "M": c.get("M"), "K": c.get("K"),
                "run_id": d.get("run_id", ""), "as_of": d.get("frozen_at") or d.get("date") or ""}
    except (OSError, ValueError):
        return {"N": None, "M": None, "K": None, "run_id": "", "as_of": ""}


NMK = _frozen()


def _nmk(key, fallback):
    """The frozen count, or a stated fallback if the file cannot be read — never a silent blank."""
    v = NMK.get(key)
    return str(v) if v is not None else fallback


from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether)
from reportlab.lib.enums import TA_JUSTIFY

INK   = colors.HexColor("#14211C")
GREEN = colors.HexColor("#1B5E3F")
MID   = colors.HexColor("#4A5852")
SOFT  = colors.HexColor("#6E7C76")
RULE  = colors.HexColor("#C9D4CD")
TINT  = colors.HexColor("#EEF3EF")

W, H = A4
LM = RM = 14*mm; TM = 13*mm; BM = 9*mm

def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=7.85, leading=9.5, textColor=INK,
                spaceBefore=0, spaceAfter=0)
    base.update(kw); return ParagraphStyle(name, **base)

S = {
 "title":   style("title", fontName="Helvetica-Bold", fontSize=17, leading=18.5, textColor=INK, spaceAfter=2),
 "tagline": style("tagline", fontName="Helvetica-Oblique", fontSize=9.6, leading=11.5, textColor=GREEN, spaceAfter=3),
 "stand":   style("stand", fontSize=8.3, leading=10.4, textColor=MID, spaceAfter=5),
 "h2":      style("h2", fontName="Helvetica-Bold", fontSize=8.3, leading=9.6, textColor=GREEN, spaceBefore=4.5, spaceAfter=2.2),
 "body":    style("body", alignment=TA_JUSTIFY, spaceAfter=3.0),
 "bodyc":   style("bodyc", alignment=TA_JUSTIFY, spaceAfter=0),
 "small":   style("small", fontSize=7.2, leading=8.7, textColor=SOFT),
 "cell":    style("cell", fontSize=7.3, leading=8.9),
 "cellb":   style("cellb", fontName="Helvetica-Bold", fontSize=7.3, leading=8.9),
 "cellh":   style("cellh", fontName="Helvetica-Bold", fontSize=6.6, leading=8.0, textColor=SOFT),
 "kicker":  style("kicker", fontName="Helvetica-Bold", fontSize=6.8, leading=8.2, textColor=SOFT),
 "close":   style("close", fontName="Helvetica-Bold", fontSize=8.4, leading=10.0, textColor=INK),
}

def P(t, s="body"): return Paragraph(t, S[s])

def rule_row():
    t = Table([[""]], colWidths=[W-LM-RM], rowHeights=[0.4])
    t.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,-1),0.5,RULE),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return t

def datatable(rows, widths, header=True):
    data = []
    for i, r in enumerate(rows):
        data.append([Paragraph(c, S["cellh"] if (header and i==0) else S["cell"]) for c in r])
    t = Table(data, colWidths=widths)
    st = [("VALIGN",(0,0),(-1,-1),"TOP"),
          ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),5),
          ("TOPPADDING",(0,0),(-1,-1),2.0),("BOTTOMPADDING",(0,0),(-1,-1),2.0),
          ("LINEBELOW",(0,0),(-1,-2),0.35,RULE)]
    if header: st.append(("LINEBELOW",(0,0),(-1,0),0.7,colors.HexColor("#9FB0A7")))
    t.setStyle(TableStyle(st)); return t

def tintbox(paras, pad=5):
    inner = []
    for p in paras: inner.append(p)
    t = Table([[inner]], colWidths=[W-LM-RM])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),TINT),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),pad),("BOTTOMPADDING",(0,0),(-1,-1),pad),
        ("LINEBEFORE",(0,0),(0,-1),1.6,GREEN)]))
    return t


def quadcell(title, sub, tone):
    return [Paragraph(title, S["cellb"]), Paragraph(sub, S["small"])]

def quadrants():
    hdr = [Paragraph("", S["cellh"]),
           Paragraph("LOW ESG SCORE TODAY", S["cellh"]),
           Paragraph("HIGH ESG SCORE TODAY", S["cellh"])]
    r1 = [Paragraph("MOMENTUM<br/>IMPROVING", S["cellh"]),
          quadcell("HIDDEN WINNERS", "Low score, improving fast. <b>The opportunity lives here.</b>", 0),
          quadcell("FUTURE LEADERS", "High score, still improving. A genuine ESG moat.", 0)]
    r2 = [Paragraph("MOMENTUM<br/>DECLINING", S["cellh"]),
          quadcell("VALUE TRAPS", "Low score and declining. Structural risk. Avoid.", 0),
          quadcell("OVERRATED LEADERS", "High score, deteriorating. Still priced at a premium.", 0)]
    cw = [21*mm, (W-LM-RM-21*mm)/2, (W-LM-RM-21*mm)/2]
    t = Table([hdr, r1, r2], colWidths=cw)
    t.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LEFTPADDING",(1,1),(-1,-1),5),
        ("BACKGROUND",(1,1),(1,1),TINT),
        ("LINEBELOW",(0,0),(-1,0),0.7,colors.HexColor("#9FB0A7")),
        ("LINEBELOW",(0,1),(-1,1),0.35,RULE),
        ("LINEAFTER",(1,0),(1,-1),0.35,RULE),
    ]))
    return t

def header_footer(canv, doc):
    canv.saveState()
    lead = "TEAM: QUILL & CANDLE"
    canv.setFont("Helvetica-Bold", 6.9); canv.setFillColor(INK)
    canv.drawString(LM, H-TM+3, lead)
    off = canv.stringWidth(lead, "Helvetica-Bold", 6.9) + 7
    canv.setFont("Helvetica", 6.9); canv.setFillColor(SOFT)
    canv.drawString(LM+off, H-TM+3, "·   CATEGORY: ESG")
    canv.drawRightString(W-RM, H-TM+3,
        "ASEAN ESG Momentum Radar   ·   PolyFinTech100 API Hackathon 2026 (CGSI)   ·   page %d of 2" % doc.page)
    canv.setStrokeColor(INK); canv.setLineWidth(0.9)
    canv.line(LM, H-TM, W-RM, H-TM)
    # The run every figure on this page came from. Without it, a number copied out of a superseded
    # run reads exactly like a current one.
    if NMK.get("run_id"):
        canv.setFont("Helvetica", 5.9); canv.setFillColor(SOFT)
        canv.drawString(LM, BM - 1,
                        "Figures from engine run %s%s · anchored on Sepolia · reproducible from the repository"
                        % (NMK["run_id"], (" frozen " + NMK["as_of"]) if NMK.get("as_of") else ""))
    canv.restoreState()

doc = BaseDocTemplate("ESG_QuillAndCandle.pdf", pagesize=A4,
                      leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
                      title="ASEAN ESG Momentum Radar - Quill & Candle - ESG",
                      author="Team Quill & Candle")
frame = Frame(LM, BM, W-LM-RM, H-TM-BM-4, id="f", leftPadding=0, rightPadding=0,
              topPadding=4, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="pt", frames=[frame], onPage=header_footer)])

F = []
F += [Spacer(1,2), P("ASEAN ESG Momentum Radar","title"),
      P("LSEG tells you where a company is. We tell you where it’s heading.","tagline"),
      P("A momentum layer on the LSEG ESG baseline. It reads continuous, dated evidence, scores the <b>direction</b> a "
        "company is moving rather than the level it has reached, and reports where that evidence disagrees with the rating "
        "the market is already using. Built for the green-finance investor: used by the analyst, bought by the CIO.","stand")]

F += [P("1 · THE PROBLEM WE ARE SOLVING","h2")]
F += [P("Capital wants into ASEAN’s green transition; the evidence arrives late and skewed. ESG ratings partly measure "
        "<b>how long a company has been required to disclose</b>, not only how well it performs — Europe mandated "
        "non-financial disclosure in 2014; Singapore’s Scope 1 and 2 requirement begins FY2025. That decade is a paperwork "
        "gap scored as a performance gap, pricing ASEAN issuers as laggards by construction. The consequences are "
        "measurable: the emerging-market greenium was statistically insignificant in 2024 (~0 bp against 1.3 bp in "
        "developed markets), and roughly 75% of EM sustainable bonds carried no international rating. CGSI’s own analysis "
        "shows ESG improvers outperform — 28.9% at one year rising to 61.5% at five — <i>but only if you find them "
        "early</i>. A rating cannot do that: it reports a level, annually, and can go stale with nobody noticing.")]
F += [P("<b>Problem-statement areas addressed:</b> sustainable-investing research · trustworthy and comparable ESG data · "
        "deciding which ASEAN names deserve a closer look, and which green-financing claims stand up.","small")]

F += [P("2 · WHAT WE BUILT","h2")]
F += [P("We do not replace the institutional baseline; we challenge it with evidence anyone can check. Three inputs are "
        "read together. <b>LSEG</b> — the only major rater with a <b>free, keyless, per-company endpoint</b>, used on "
        "demand, one company at a time, attributed, never redistributed. An <b>industry GHG-intensity benchmark from "
        "Eurostat’s public dissemination API</b> (<font face='Courier' size='7'>env_ac_aeint_r2</font>, NACE Rev. 2, EU-27, 2023): one HTTP GET "
        "returns <b>7.89 g CO<sub>2</sub>e per euro of gross value added</b> for banks, and all 22 rows re-download in about ten "
        "seconds, so <b>a judge can rebuild our yardstick on their own laptop</b>. And <b>CGSI’s own 52-company ASEAN "
        "dataset</b>, 2019–2023.")]
F += [P("The benchmark is <b>not an ESG rating and never stands in for one</b> — it sizes how carbon-heavy an industry "
        "structurally is, so a bank and a cement producer are not judged on the same bar. Our code refuses to subtract it "
        "from a company’s ESG score: they are different measures, and differencing them would be exactly the sloppiness "
        "this project exists to catch in others.","small")]
F += [datatable([
    ["THE FOUR PARTS","WHAT IT DOES"],
    ["<b>Continuous signals</b>","Up to 27 live searches per company along four angles — emissions, governance, financing, controversies — over news, filings, patents and hiring. Event-driven, not annual; each signal scored for direction, velocity and confidence, with source URL and hash on every record."],
    ["<b>Four pillars</b>","E · S · G <b>+ Digital &amp; AI</b> — the execution capacity behind ESG promises: patents, AI talent, digital capex, and the intangibles named in the brief — data moats, platform dominance, digital risk."],
    ["<b>A decision, not a score</b>","Set to your mandate by seven questions — risk appetite, holding period, whether green financing matters — each moving a number, never just a line of summary. Momentum vs the LSEG percentile then places each name in CGSI’s quadrants: <b>Hidden Winners</b>, <b>Future Leaders</b>, <b>Value Traps</b>, <b>Overrated Leaders</b>."],
    ["<b>Every verdict explains itself</b>","ESG pros and cons, financial pros and cons, and what to look out for — proximity to a boundary, provisional metadata, evidence too old for the chosen horizon. All derived by rule from the stored run; <b>no language model writes any of it</b>, so it reproduces exactly. Cons render at the same size, in the same column, as pros."],
], [30*mm, W-LM-RM-30*mm])]

F += [P("3 · THE BRIDGE: WHERE ESG MEETS THE MONEY","h2")]
F += [P("An improving ESG story attached to a failing business is not an investment case, so every name carries a second, "
        "separate read built from two fiscal years of net income: <b>17 strong · 22 adequate · 11 weak · 2 unknown</b>. The two "
        "unknowns are loss-making and route to a four-test traction screen — until it has run, <i>“we don’t know”</i> is "
        "the honest answer; scoring an unrun test as a failure would disqualify a company for our missing data rather than "
        "its own numbers.")]
F += [tintbox([
    P("<b>The two axes are shown side by side and never merged.</b> The moment the output is one combined number, nobody — "
      "including us — can say which half is driving it, and we stop being a tool that disagrees with ratings and become a "
      "tool that picks stocks. The financial read is a <b>gate</b>: it decides whether an ESG disagreement is worth acting "
      "on. It never moves the ESG verdict. Our test suite enforces this — the scoring engine is checked to make sure it "
      "cannot even import the financial module.","bodyc")])]
F += [Spacer(1,3.5)]
F += [datatable([
    ["THE OUTPUT","","WHAT IT MEANS"],
    ["<b>N · issuers</b>","<b>%s</b>" % _nmk("N", "13"),"Already a labelled, reviewed or CBI-certified green-bond issuer. Credibility established — and priced in."],
    ["<b>M · pipeline</b>","<b>%s</b>" % _nmk("M", "10"),"<b>The bridge.</b> Below its industry’s ASEAN peer ESG average, positive evidenced momentum, passes the financial gate, not already an issuer, not delisted."],
    ["<b>K · review list</b>","<b>%s</b>" % _nmk("K", "1"),"We disagree, but something still blocks it — confidence, profitability, sector position or unverified metadata. A human looks at these."],
], [24*mm, 10*mm, W-LM-RM-34*mm])]
F += [Spacer(1,3)]
F += [P("<b>Hidden Winners now holds four names — and the bar never moved to let them in.</b> The threshold was published "
        "in advance. For weeks the quadrant was empty, because 80% of what live search returns is company-published "
        "material, which our source-quality rule caps at 0.50 confidence. The quadrant filled when a deeper sweep took the "
        "evidence base from 167 to <b>391 dated events</b> — better sources, not a lower bar. A screen that returns "
        "zero when the evidence does not support a claim is more credible than one that always finds something.")]

F += [P("4 · WHAT WE FOUND IN CGSI’S OWN DATA","h2")]
F += [P("CGSI’s three-filter model returns 17 high-conviction names, selected on above-average ESG CAGR, coverage-universe "
        "inclusion and an <i>Add</i> recommendation — only the first of which is an ESG signal. Set that list against "
        "green-bond issuance verified per company from frameworks, second-party opinions and allocation reports:")]
F += [tintbox([
    P("<b>Eleven of the 17 have never issued a labelled green bond</b>, and <b>seven of the 13 verified issuers are not "
      "among the 17.</b> This is not a claim that either list is wrong — it is that momentum and green-financing "
      "credibility measure different things, and an investor who needs both has to see both, unblended.","bodyc")])]
F += [Spacer(1,3.5)]
F += [P("Nine further names carry only sustainability-linked instruments or a social bond: they clear a loose “sustainable "
        "finance” screen but hold no use-of-proceeds green bond — under ICMA and the ASEAN GBS, a different instrument with "
        "a different credibility profile. Two of the 52 are <b>no longer listed</b> (Malaysia Airports, 25 Feb 2025; "
        "Intouch, 3 Apr 2025), so the investable universe is 50, and nothing in the published rating moved to say so. Two "
        "more hold a full framework with a second-party opinion and have never issued under it — a near-term pipeline no "
        "ESG score can capture, because nothing has happened yet for it to score.")]
F += [P("<b>We also found two errors in the data we were given, and reported both back.</b> The <font face='Courier' size='7'>lseg_rating</font> "
        "column carries BB / BBB / B — the MSCI notch scale, not LSEG’s own A+ to D−; we verified this against the live "
        "LSEG endpoint. And PTTGC’s FY2025 loss reconciles to THB 15,572m audited against THB 14.6b in the supplied row. "
        "Auditing the inputs is not a courtesy here; it is the same discipline we apply to every other source.")]

F += [P("5 · WHY THE NUMBER HOLDS","h2")]
F += [P("<b>The AI never computes the score.</b> It only extracts — direction, materiality, confidence — under a fixed "
        "schema, versions pinned. The score is deterministic arithmetic in a version-controlled config and no language model is "
        "reachable from it. Five structural defences stop a company gaming the signal: PR capped at 0.50 source quality; "
        "corroboration log-capped so repetition cannot inflate; “we reduced” outscoring “we will”; a 180-day decay half-life; and no "
        "evidence meaning score 0 at confidence ≤ 0.2. A press release cannot structurally produce a high-confidence signal.")]
F += [P("<b>Backtested on five named ASEAN cases with the lookback frozen before every outcome</b>, share prices from "
        "Yahoo Finance — Sembcorp, ACEN, Top "
        "Glove, Adaro, REE. Top Glove’s forced-labour warnings were public 19 months before the US import ban while it stayed "
        "on the Dow Jones Sustainability Index throughout. One of the five is a case we got wrong and we left it in: a "
        "backtest you can only pass is not a backtest. Building the financial layer surfaced three parsing bugs, each "
        "producing a confidently wrong number under a real company’s name — one read RHB Bank as having almost stopped "
        "earning when it had grown 8.1%. All three are now locked into the test suite. The audit chain is voluntarily "
        "mapped, clause by clause, to the MAS Code of Conduct for ESG Rating and Data Product Providers.")]

F += [P("6 · THREE LAYERS — AND WHERE THE CHAIN ACTUALLY SITS","h2")]
F += [datatable([
    ["LAYER","WHAT IT IS HERE"],
    ["<b>1 · Sensors</b>","Four-angle live search, the live LSEG rating, the industry benchmark, the verified basket."],
    ["<b>2 · Verification</b>","Five harvest guards, source type decided by domain, company PR capped at 0.50, forward-looking claims halved, rule-based scoring, provisional-until-reviewed, maker-checker. <b>All of it off-chain, by rules any reviewer can read.</b>"],
    ["<b>3 · Ledger</b>","One Merkle root per run — run id, 32-byte hash, timestamp: <b>72 bytes</b>, no names, no scores, no URLs. A run id can be written <b>once, ever</b>; a second write is rejected by the contract."],
], [24*mm, W-LM-RM-24*mm])]
F += [Spacer(1,3)]
F += [P("<b>A chain cannot verify an off-chain fact</b> — it is closed, and immutability applied to a false claim only makes the "
        "false claim permanent. So the chain is the ledger layer, not the verification layer: it records a commitment to "
        "what the rules saw — checkable in about 15 seconds. It earns its place in 2028, when an investor who acted on an "
        "August 2026 verdict asks whether it was really built on this evidence or backfilled later. A hash anchored at the "
        "time answers that, and nobody has to trust us to check it.")]

F += [P("7 · WHAT SEPARATES US","h2")]
F += [P("Real-time ESG intelligence exists — Truvalue Labs (FactSet), RepRisk, Clarity AI, ESG Book — as do supply-chain "
        "chain-of-custody platforms. They validate the category; none does all five of: scoring the <b>divergence</b> "
        "against the baseline an investment committee actually screens on · calibrating to ASEAN disclosure conditions "
        "rather than a global distribution · treating <b>Digital &amp; AI</b> as a distinct scored pillar · producing "
        "evidence a third party can verify <b>without trusting us</b> · using green-bond credibility as the gauge with risk "
        "appetite as the filter. The chain-of-custody platforms are issuer-side, writing a company’s own data to evidence "
        "its own claims. We are investor-side and adversarial to the issuer: a company’s own publication is the "
        "<i>least</i>-trusted source we hold.")]

F += [P("8 · INVESTMENT AND TIME TO MARKET","h2")]
F += [P("<b>The ask is S$25,000 and one design partner</b> — a six-week pilot on the 52-name basket, success criteria "
        "agreed in advance. That assumes founder-subsidised labour, and we say the gap before you find it: fully loaded at "
        "sourced 2026 day rates it is <b>S$86,378</b>, with no unsourced cells. Pricing is per-firm SaaS tiered by AUM, "
        "averaging <b>S$68k in Year 1</b>, anchored to Bloomberg and LSEG Workspace comparables, break-even ~S$57k at 20 firms.")]
F += [P("<b>Measured, not estimated:</b> evidence gathering costs <b>S$0.079 per company per year</b> — S$4.12 to cover all "
        "52, S$39.65 at 500, S$158.60 at 2,000 — and scoring, bridging and case generation cost <b>zero marginal tokens</b>, "
        "because deterministic code does that work. Sweeps are batch jobs, so running off-peak is an exact 50% saving. "
        "Metadata verification is the one cost that is people rather than tokens, at a measured Singapore ESG-analyst rate "
        "of about S$36 per hour; we have not yet timed it per company, and say so rather than filling the gap.")]
F += [tintbox([
    P("<b>We do not draw a falling cost-per-company curve, because we cannot yet justify one.</b> Inference is linear in "
      "companies, so on every cost we have actually measured the line is <b>flat</b>. It falls only when the fixed data "
      "licence is spread across clients — and no licence quote exists yet. Drawing that curve before the number arrives "
      "would be drawing the conclusion first, which is precisely what this tool exists to catch other people doing.","bodyc")])]
F += [Spacer(1,3.5)]
F += [P("<b>The timeline is gated, not dated.</b> Each phase starts when its entry condition is met, not on a date we cannot "
        "control: one real source wired end-to-end gates the pilot; a completed design-partner pilot against its pre-agreed "
        "criteria gates regional coverage; outside capital enters only once revenue covers data costs.")]

F += [P("9 · WHAT WE ARE HONEST ABOUT","h2")]
F += [datatable([
    ["CONSTRAINT","THE FIX, OR THE REASON"],
    ["<b>MSCI, Sustainalytics and S&amp;P cannot be displayed</b> — licensed products; showing their scores without a contract is a licence breach, not a style choice.","LSEG is the free, attributed substitute, already live. Where a company’s own evidence cites those houses we read it, and it feeds the evidence score."],
    ["<b>Financial data is mixed</b> — real where sourced, labelled mock elsewhere, with <font face='Courier' size='7'>is_mock</font> on every record. Sponsor-confirmed acceptable for the pilot.","Per-source migration, costed. SGX filings wired end-to-end first."],
    ["<b>The engine only scores its own cohort.</b> A percentile is a rank; hand it a name from outside the basket and the missing baseline defaults to zero, ranking it last and printing a convincing +0.673.","We never run an off-basket name through the engine board — that is an absence rendered as a finding. The assistant handles those companies instead, in sentences."],
    ["<b>The benchmark is a European industry series</b>, and it gives industry averages, not company data.","Shipped as a hash-anchored file so the yardstick cannot be quietly edited; refreshed annually from the same Eurostat call, with OECD’s SDMX explorer as the route beyond Europe."],
    ["<b>Digital &amp; AI is a hypothesis</b>, not a proven leading indicator. Vietnam coverage is our weakest — a language problem, not a data problem.","Being tested in the harness; we will report the correlation either way. Vietnamese-language extraction is a costed roadmap item."],
], [0.50*(W-LM-RM), 0.50*(W-LM-RM)])]
F += [Spacer(1,3)]
F += [P("<b>And about our own foundation:</b> CGSI’s improver basket returned 55.1% against the index’s 6.4% over the study "
        "period — and <b>lagged that same index by 4.6% year-to-date</b>, on a roughly 45% banking weight. Both numbers "
        "always travel together. ESG improvement alone does not predict single-stock performance. <b>The line we do not "
        "cross:</b> no buy, sell or hold language · no price targets · evidence always shown · human in the loop. Momentum "
        "informs issuer selection and monitoring; it is never a green-bond <i>eligibility</i> rating, which attaches to use "
        "of proceeds, framework and external review under ICMA and the ASEAN Green Bond Standards.","small")]

F += [Spacer(1,3), rule_row(), Spacer(1,3)]
F += [P("ESG was built to grade companies. We built something to govern capital. A rating tells you where a company is; "
        "this tells you where it is heading — and exactly which piece of evidence is holding that up. <b>The ask: S$25,000 "
        "and one design partner. We’d like it to be you.</b>","close")]
F += [Spacer(1,3)]
F += [P("Sources: CGSI, ESG Momentum 2.0 (2026), indicative · IFC &amp; Amundi, EM Green Bonds 2024 (Jun 2025) · ADB Asia Bond "
        "Monitor (Nov 2025) · ACRA &amp; SGX RegCo (Aug 2025) · Eurostat <font face='Courier' size='7'>env_ac_aeint_r2</font>, EU-27 2023, fallback "
        "flagged in-product · MAS Code of Conduct for ESG Rating &amp; Data Product Providers (Dec 2023) · green-bond status "
        "verified from frameworks, SPOs and allocation reports, ≥2 primary sources each · verified against the running "
        "system, 24–25 Aug 2026.","small")]

doc.build(F)
print("built")
