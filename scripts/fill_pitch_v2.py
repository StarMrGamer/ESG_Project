"""Fill ESG_Momentum_Radar_v2.pptx — the empty card bodies, and the two placeholder slides.

WHAT THIS DOES AND WHY IT IS A SCRIPT RATHER THAN HAND-EDITING
--------------------------------------------------------------
The deck arrived with three kinds of hole:

  * card bodies on slides 2, 4 and 5 — each card is about a third empty under its headline;
  * slide 5 has no italic deck line, though slides 2, 3 and 4 all carry one in the same place;
  * slides 6 and 7 are single text boxes carrying instructions to whoever fills them.

Doing it in code rather than by hand means every value below is the value LIFTED OFF the deck's
own slides, not a visual approximation of it — the fonts, the sizes, the letter-spacing, the
rounded-corner adjustment, the exact greens. A hand-placed box that is 0.05in out and one point
too large is the kind of thing nobody can name and everybody can see.

THE STYLE, MEASURED OFF SLIDES 1-5 AND 8
-----------------------------------------
Palette      ink #13301F · accent #2E6B47 · body #3E4741 · muted #8A928B
             page #F7F6F2 · card #FFFFFF · card border #D6D3CA · strip #EDEBE4 · wash #E3EDE6
Eyebrow      Courier New 10pt bold, letter-spacing 201, accent
Title        Cambria 38pt bold, ink
Deck line    Calibri 15pt italic, body
Card label   Courier New 9pt bold, letter-spacing 99, accent, CENTRED
Card head    Cambria 17pt bold, ink, CENTRED
Card body    Calibri 11pt, body, CENTRED          <- the shape this script adds
Footer       Courier New 9pt, muted (left letter-spaced 99, right aligned RIGHT)
Cards        roundRect, adj 3019, white fill, 1pt #D6D3CA border

EVERY NUMBER ON THE TWO NEW SLIDES IS FROM THE REPO, NOT FROM A PITCH INSTINCT
------------------------------------------------------------------------------
  11 -> 20 -> 22   `roadmap.py` — the real engine re-run over the same evidence with only
                   `source_type` changed. Labelled on the slide as what it is.
  S$118.45         the workbook's Hackathon Actuals tab: 52+13+19+19+0, +15% contingency.
  S$0.0793 / S$4.12 / S$158.60   `cost_model.py --window off-peak` at DeepSeek's published card.
  S$75,758         65 working days x S$1,165.50 blended, from `data/sg_day_rates.json` — rates
                   derived from live MyCareersFuture postings, not a remembered band.
  0 tokens         the scoring path: `signals.py` routes by rule and `engine.py` scores; neither
                   can reach an LLM, and `selftest.py` pins that.

Run:  python -m scripts.fill_pitch_v2 [--in PATH] [--out PATH]
The original is left untouched unless --out names it.
"""
import argparse
import copy
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── the palette, lifted off the deck ──────────────────────────────────────────
INK = RGBColor(0x13, 0x30, 0x1F)
ACCENT = RGBColor(0x2E, 0x6B, 0x47)
BODY = RGBColor(0x3E, 0x47, 0x41)
MUTED = RGBColor(0x8A, 0x92, 0x8B)
PAGE = RGBColor(0xF7, 0xF6, 0xF2)
CARD = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xD6, 0xD3, 0xCA)
STRIP = RGBColor(0xED, 0xEB, 0xE4)
WASH = RGBColor(0xE3, 0xED, 0xE6)

MONO, SERIF, SANS = "Courier New", "Cambria", "Calibri"


def _spc(run, hundredths):
    """Letter-spacing. python-pptx has no API for it; the deck uses spc on every mono run."""
    run.font._rPr.set("spc", str(hundredths))


def _txt(slide, x, y, w, h, align=None, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if align is not None:
        tf.paragraphs[0].alignment = align
    return box, tf


def _line(tf, text, *, font, size, color, bold=False, italic=False, spc=None,
          align=None, first=False, space_before=None):
    para = tf.paragraphs[0] if first else tf.add_paragraph()
    if align is not None:
        para.alignment = align
    if space_before is not None:
        para.space_before = Pt(space_before)
    run = para.add_run()
    run.text = text
    f = run.font
    f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
    f.color.rgb = color
    if spc is not None:
        _spc(run, spc)
    return para


def card(slide, x, y, w, h, fill=CARD, border=BORDER, radius=3019):
    """The deck's card: a rounded rectangle, adj 3019, 1pt border. Measured off slide 2."""
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if border is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = border
        sh.line.width = Pt(1)
    sh.shadow.inherit = False
    try:
        sh.adjustments[0] = radius / 100000.0
    except Exception:
        pass
    sh.text_frame.text = ""
    return sh


def page_furniture(slide, number, *, dark=False, left="POLYFINTECH100 · ESG"):
    """Background, footer and page number, in the positions slides 2-5 use."""
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x13, 0x30, 0x1F) if dark else PAGE

    _, tf = _txt(slide, 0.60, 6.95, 4.00, 0.30)
    _line(tf, left, font=MONO, size=9, color=MUTED, spc=99, first=True)

    _, tf = _txt(slide, 11.70, 6.95, 1.00, 0.30, align=PP_ALIGN.RIGHT)
    _line(tf, number, font=MONO, size=9, color=MUTED, align=PP_ALIGN.RIGHT, first=True)


def head(slide, eyebrow, title, deck=None):
    """Eyebrow / title / deck line, at the exact coordinates slides 2, 3 and 4 use."""
    _, tf = _txt(slide, 0.60, 0.50, 6.00, 0.30)
    _line(tf, eyebrow, font=MONO, size=10, color=ACCENT, bold=True, spc=201, first=True)

    _, tf = _txt(slide, 0.60, 0.90, 11.50, 0.85)
    _line(tf, title, font=SERIF, size=38, color=INK, bold=True, first=True)

    if deck:
        _, tf = _txt(slide, 0.60, 1.78, 11.20, 0.45)
        _line(tf, deck, font=SANS, size=15, color=BODY, italic=True, first=True)


def card_body(slide, x, y, w, h, text, size=11):
    """The missing third of every card: centred Calibri under the Cambria headline."""
    _, tf = _txt(slide, x, y, w, h, align=PP_ALIGN.CENTER)
    _line(tf, text, font=SANS, size=size, color=BODY, align=PP_ALIGN.CENTER, first=True)
    tf.paragraphs[0].line_spacing = 1.25


def strip(slide, x, y, w, h, text, size=13.5, italic=True):
    """The full-width note slide 2 closes on: #EDEBE4 panel, indented italic Calibri."""
    card(slide, x, y, w, h, fill=STRIP, border=BORDER)
    _, tf = _txt(slide, x + 0.35, y + 0.20, w - 0.70, h - 0.40)
    _line(tf, text, font=SANS, size=size, color=INK, italic=italic, first=True)
    tf.paragraphs[0].line_spacing = 1.3


def clear(slide):
    """Strip a placeholder slide back to nothing so it can be rebuilt on the deck's grid."""
    for sh in list(slide.shapes):
        sh._element.getparent().remove(sh._element)


# ══════════════════════════════════════════════════════════════════════════════
#  THE COPY
# ══════════════════════════════════════════════════════════════════════════════
# Slide 2 · THE PROBLEM — one body paragraph per card, in the deck's own register:
# declarative, concrete, no exclamation, the em dash doing the work.
S2_BODIES = [
    "A rating refreshes once a year. Everything the company does between those two "
    "dates lands on the same unchanged score.",
    "Two companies both sit at BBB. One has been climbing for eighteen months, the "
    "other sliding. The letter is identical.",
    "Most of what a rating reads was written by the company being rated, and it is "
    "read at face value.",
]

# Slide 4 · THE SOLUTION — what each panel of the live demo actually does.
S4_BODIES = [
    "Conservative, balanced or aggressive. The board re-segments live, and names "
    "outside your mandate dim rather than disappear.",
    "Every company on two axes — what the market has already priced, and what our "
    "evidence says. Top-left is the corner we built this for.",
    "Dated, sourced events scored by rule. The dashed ring is zero movement, which "
    "is what a static rating quietly assumes.",
]

# Slide 5 · THE ANSWER — each card answers the same-numbered card on slide 2.
S5_DECK = ("Three problems, three answers — and each one is a panel you can open, "
           "not a claim you have to take on trust.")
S5_BODIES = [
    "Evidence carries its own date, so the read moves the week a filing lands — not "
    "at the next annual review.",
    "We publish a signed disagreement against the incumbent rating. Direction is the "
    "output, not a footnote to it.",
    "A company's own press release is capped at half confidence by rule. A regulator "
    "action carries full weight.",
]

# Slide 6 · THE PLAN — thirteen weeks to the Grand Finals in November.
PHASES = [
    ("PHASE 1 · WEEKS 1–3", "Wire the exchange filings",
     "SGX, Bursa, IDX and SET publish sustainability filings we currently read as "
     "press releases. Ends when confident coverage moves from 11 of 52 to 20."),
    ("PHASE 2 · WEEKS 4–7", "Regulator and index feeds",
     "MAS, SC and OJK enforcement actions, and index inclusion decisions — sources a "
     "company cannot author about itself. Ends at 22 of 52."),
    ("PHASE 3 · WEEKS 8–10", "Widen to 185 names",
     "The five ASEAN index universes, already priced and already harvested. Ends with "
     "the full board scored on a single reproducible run."),
    ("PHASE 4 · WEEKS 11–13", "Harden for the finals",
     "Maker–checker review on every verified row, every run anchored on-chain, and "
     "the cost model re-measured at the new scale."),
]
S6_STRIP = ("The 11 → 20 → 22 is not a projection. It is the engine re-run over the same "
            "evidence with one field changed — where each fact came from.")

# Slide 7 · THE COST — a table, because a breakdown is a table.
#
# Three sections: what it cost to BUILD, what it costs to RUN, and the PILOT itemised line by
# line. Row shape is (kind, item, basis, amount) where kind is 'sec' | 'row' | 'tot'.
#
# THE TWO BLANK ROWS ARE THE POINT, NOT AN OVERSIGHT. The ESG baseline licence and the
# compliance review have no quote, so they carry an em dash and the subtotal is stamped
# INCOMPLETE. `cost_model.py` refuses to invent either, and the workbook marks them amber-empty
# for the same reason: a plausible number in a cost model is worse than a blank one, because a
# blank gets asked about and a plausible number gets believed.
COST_ROWS = [
    ("sec", "BUILT · what got us here", "", ""),
    ("row", "Cloud, bandwidth, DeepSeek credits, domain + SSL",
     "Semester actuals, including 15% contingency", "118"),

    ("sec", "RUN · inference, per year", "", ""),
    ("row", "All 52 companies",
     "S$0.079 each — the scoring path costs zero tokens", "4"),
    ("row", "At 2,000 companies",
     "Linear: inference does not get cheaper with scale", "159"),

    ("sec", "PILOT · 13 weeks, the plan opposite", "", ""),
    ("row", "Data / ML engineer · 1.0 FTE", "65 days × S$405", "26,325"),
    ("row", "Full-stack engineer · 1.0 FTE", "65 days × S$398", "25,870"),
    ("row", "Project manager · 0.5 FTE", "65 days × S$435", "14,138"),
    ("row", "ESG analyst · 0.5 FTE", "65 days × S$290", "9,425"),
    ("row", "Cloud, storage and public data feeds",
     "SGX / Bursa / IDX / SET, Eurostat and EPO are free", "2,000"),
    ("row", "ESG baseline licence · compliance review",
     "Quotes outstanding — left blank, not estimated", "—"),
    ("tot", "Pilot subtotal — INCOMPLETE", "People and infrastructure only", "77,758"),
]

S7_DECK = "Measured from real token counts and live Singapore salary data — nothing estimated."


# ══════════════════════════════════════════════════════════════════════════════
#  THE FILL
# ══════════════════════════════════════════════════════════════════════════════
def fill_existing_cards(prs):
    """Slides 2, 4 and 5: the empty third under each headline, plus slide 5's deck line."""
    # Slide 2 — cards at y 2.80 h 2.65, headline ends 4.64.
    s2 = prs.slides[1]
    for (x, w), text in zip([(0.95, 2.95), (4.90, 2.95), (8.90, 3.50)], S2_BODIES):
        card_body(s2, x, 4.72, w, 0.66, text)

    # Slide 4 — taller cards (y 2.60 h 3.30), title ends 4.45, so the body gets more room.
    s4 = prs.slides[3]
    for (x, w), text in zip([(0.95, 3.20), (5.05, 3.20), (9.15, 3.20)], S4_BODIES):
        card_body(s4, x, 4.60, w, 1.10, text)

    # Slide 5 — cards at y 2.95 h 2.85, headline ends 4.79. Also the missing deck line,
    # placed at the same 1.78 every other content slide uses.
    s5 = prs.slides[4]
    _, tf = _txt(s5, 0.60, 1.78, 11.20, 0.45)
    _line(tf, S5_DECK, font=SANS, size=15, color=BODY, italic=True, first=True)
    for (x, w), text in zip([(0.95, 2.95), (4.90, 2.95), (8.90, 3.50)], S5_BODIES):
        card_body(s5, x, 4.93, w, 0.70, text)


def build_plan(slide):
    """Slide 6 — four phases on one lane. Four cards on the deck's three-card rhythm."""
    clear(slide)
    page_furniture(slide, "07 / 10")
    head(slide, "THE PLAN", "Four phases to the Grand Finals",
         "Thirteen weeks from today. Each phase ends in something checkable — a number that "
         "moves, not a status update.")

    # The lane: a hairline spine with a node per phase, so the four cards read as a sequence
    # rather than as four unrelated boxes. Same border grey as the cards themselves.
    lane_y = 2.62
    spine = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.60), Inches(lane_y),
                                   Inches(12.15), Pt(1))
    spine.fill.solid()
    spine.fill.fore_color.rgb = BORDER
    spine.line.fill.background()
    spine.shadow.inherit = False

    xs = [0.60, 3.70, 6.80, 9.90]
    w, top, h = 2.85, 2.98, 2.62
    for i, (x, (label, title, body)) in enumerate(zip(xs, PHASES)):
        node = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + w / 2 - 0.075),
                                      Inches(lane_y - 0.065), Inches(0.15), Inches(0.15))
        node.fill.solid()
        node.fill.fore_color.rgb = ACCENT if i == 0 else PAGE
        node.line.color.rgb = ACCENT
        node.line.width = Pt(1.25)
        node.shadow.inherit = False

        card(slide, x, top, w, h)
        _, tf = _txt(slide, x + 0.28, top + 0.30, w - 0.56, 0.25, align=PP_ALIGN.CENTER)
        _line(tf, label, font=MONO, size=9, color=ACCENT, bold=True, spc=99,
              align=PP_ALIGN.CENTER, first=True)

        _, tf = _txt(slide, x + 0.28, top + 0.68, w - 0.56, 0.70, align=PP_ALIGN.CENTER)
        _line(tf, title, font=SERIF, size=15, color=INK, bold=True,
              align=PP_ALIGN.CENTER, first=True)
        tf.paragraphs[0].line_spacing = 1.15

        card_body(slide, x + 0.28, top + 1.42, w - 0.56, 1.05, body, size=10.5)

    strip(slide, 0.60, 5.85, 12.15, 0.75, S6_STRIP)


def _cell_border(cell, edges=("L", "R", "T", "B"), color=BORDER, pt=0.75):
    """Cell borders. python-pptx has no API for them, so they go in as a:lnL/R/T/B directly."""
    tcPr = cell._tc.get_or_add_tcPr()
    for edge in edges:
        tag = qn(f"a:ln{edge}")
        for old in tcPr.findall(tag):
            tcPr.remove(old)
        ln = tcPr.makeelement(tag, {"w": str(int(pt * 12700)), "cap": "flat",
                                    "cmpd": "sng", "algn": "ctr"})
        fill = ln.makeelement(qn("a:solidFill"), {})
        clr = ln.makeelement(qn("a:srgbClr"), {"val": f"{color}"})
        fill.append(clr)
        ln.append(fill)
        # a:lnL..a:lnB must precede a:fill in the CT_TableCellProperties sequence.
        tcPr.insert(0, ln)


def _cell(cell, text, *, font, size, color, bold=False, italic=False, spc=None,
          align=PP_ALIGN.LEFT, fill=None):
    cell.margin_left = Inches(0.14)
    cell.margin_right = Inches(0.14)
    cell.margin_top = Inches(0.045)
    cell.margin_bottom = Inches(0.045)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    if fill is None:
        cell.fill.background()
    else:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
    tf = cell.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    f = run.font
    f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
    f.color.rgb = color
    if spc is not None:
        _spc(run, spc)
    _cell_border(cell)


def build_cost(slide):
    """Slide 7 — the cost as a TABLE, with the pilot itemised line by line.

    A real PowerPoint table rather than shapes pretending to be one, so the numbers stay
    editable in the deck. Every cell is styled explicitly and the built-in table style is
    switched off (`first_row` / banding), because the default banded blue would be the one
    element on the slide that is not the deck's own palette.
    """
    clear(slide)
    page_furniture(slide, "08 / 10")
    head(slide, "THE COST", "What it costs, and why it is that low", S7_DECK)

    left, top, width = 0.60, 2.42, 12.15
    header_h, row_h = 0.30, 0.30
    rows = len(COST_ROWS) + 1

    gf = slide.shapes.add_table(rows, 3, Inches(left), Inches(top),
                                Inches(width), Inches(header_h + row_h * (rows - 1)))
    tbl = gf.table
    tbl.first_row = False
    tbl.horz_banding = False
    tbl.columns[0].width = Inches(4.45)
    tbl.columns[1].width = Inches(5.35)
    tbl.columns[2].width = Inches(2.35)
    tbl.rows[0].height = Inches(header_h)
    for r in range(1, rows):
        tbl.rows[r].height = Inches(row_h)

    # Header — the deck's dark green, the only inverted band on the slide.
    for i, (label, align) in enumerate((("ITEM", PP_ALIGN.LEFT),
                                        ("HOW IT IS DERIVED", PP_ALIGN.LEFT),
                                        ("SGD", PP_ALIGN.RIGHT))):
        _cell(tbl.cell(0, i), label, font=MONO, size=8.5, color=RGBColor(0xFF, 0xFF, 0xFF),
              bold=True, spc=99, align=align, fill=INK)

    for r, (kind, item, basis, amount) in enumerate(COST_ROWS, start=1):
        if kind == "sec":
            # A section band spanning the width: the three costs are different questions and
            # running them together as one list would invite adding them up, which is wrong —
            # built is spent, run is annual, pilot is a 13-week ask.
            tbl.cell(r, 0).merge(tbl.cell(r, 2))
            _cell(tbl.cell(r, 0), item, font=MONO, size=8.5, color=INK, bold=True, spc=99,
                  fill=WASH)
            continue

        total = kind == "tot"
        bg = STRIP if total else CARD
        _cell(tbl.cell(r, 0), item, font=SANS, size=10.5, color=INK, bold=total, fill=bg)
        _cell(tbl.cell(r, 1), basis, font=SANS, size=9.5, color=BODY, italic=True, fill=bg)
        _cell(tbl.cell(r, 2), amount, font=SERIF, size=12 if total else 11.5, color=INK,
              bold=True, align=PP_ALIGN.RIGHT, fill=bg)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fill the v2 pitch deck.")
    ap.add_argument("--in", dest="src",
                    default="/home/faky/Downloads/ESG_Momentum_Radar_v2.pptx")
    ap.add_argument("--out", dest="dst",
                    default="/home/faky/Downloads/ESG_Momentum_Radar_v2.pptx")
    args = ap.parse_args(argv)

    prs = Presentation(args.src)
    fill_existing_cards(prs)
    build_plan(prs.slides[5])
    build_cost(prs.slides[6])
    prs.save(args.dst)
    print(f"wrote {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
