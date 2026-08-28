"""
build_pitch_pptx.py — the 9-slide judge deck as a real, editable PowerPoint file.
=================================================================================

`docs/pitch/slides.md` is the SCRIPT (what you say, when, and what to do if pushed).
This is the PICTURE. Same nine sections, same run id, same numbers — and every figure on
every slide traces to the appendix table in that file, which traces to a file in the repo.

WHY A GENERATOR AND NOT A HAND-BUILT .pptx
------------------------------------------
The organisers require the whitepaper and the presentation to carry the same numbers. A deck
someone edited by hand drifts from the run the moment a figure moves; a deck built by a script
re-renders in two seconds and drifts never. Change a number in `NUMBERS` below, re-run, done.

    python -m scripts.build_pitch_pptx
    python -m scripts.build_pitch_pptx --pdf     # also render a PDF via LibreOffice

TYPOGRAPHY — editorial, not corporate
-------------------------------------
IBM Plex Sans Condensed for headlines, Plex Sans for text, Plex Mono for every figure, which is
the same three-family system as `docs/pitch/pitch_slide.html` and `docs/whitepaper/whitepaper.html`.
Rules and white space do the structural work; there are no boxes, no shadows, no icons and no
gradients anywhere in this file. Colour is used for exactly three things and never for decoration:
GREEN marks our evidence read, BLUE marks the published rating, RED marks a caution and always has
a word beside it.

**If Plex is not installed on the presenting machine PowerPoint will substitute a default face and
the line breaks will move.** Either install IBM Plex (free, OFL) or present the rendered PDF, which
embeds the fonts. `--pdf` writes that PDF next to the deck.

The speaker notes on each slide are the `YOU SAY` and `IF PUSHED` blocks from `slides.md`, so the
presenter view carries the script without a second document open.
"""

import argparse
import os
import subprocess
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

try:                                    # measurement only — the deck builds without it
    from PIL import ImageFont
except ImportError:                     # pragma: no cover
    ImageFont = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root, one level up
OUT_PPTX = os.path.join(BASE_DIR, "docs", "pitch", "ASEAN_ESG_Momentum_Radar.pptx")

# ── the run every figure comes from ─────────────────────────────────────────────────────────
RUN_ID = "1fc384a2fa92499d"
TEAM = "QUILL & CANDLE"
CATEGORY = "ESG"

# ── palette (identical to pitch_slide.html) ─────────────────────────────────────────────────
PAPER = RGBColor(0xF7, 0xF8, 0xF7)
INK = RGBColor(0x12, 0x15, 0x1A)
INK2 = RGBColor(0x4B, 0x55, 0x63)
INK3 = RGBColor(0x76, 0x7F, 0x89)
GREEN = RGBColor(0x0F, 0x51, 0x32)      # structure: eyebrows, rules
EVIDENCE = RGBColor(0x1A, 0x7F, 0x4F)   # data mark: our live read
RATING = RGBColor(0x1D, 0x4E, 0xD8)     # data mark: the published rating
CAUTION = RGBColor(0x8A, 0x1C, 0x1C)    # status only, always with a word beside it
LINE = RGBColor(0xDF, 0xE4, 0xE4)
LINE2 = RGBColor(0xEE, 0xF1, 0xF1)

COND = "IBM Plex Sans Condensed"
SANS = "IBM Plex Sans"
MONO = "IBM Plex Mono"

# ── the grid ────────────────────────────────────────────────────────────────────────────────
SW, SH = 13.333, 7.5
M = 0.78                     # left / right margin
CW = SW - 2 * M              # content width
Y_EYEBROW = 0.36
Y_IDRULE = 0.70
Y_HEAD = 1.00
Y_FOOTRULE = 6.74
Y_FOOT = 6.86


# ── primitives ──────────────────────────────────────────────────────────────────────────────
def rule(slide, x, y, w, pt=0.75, color=LINE):
    """A hairline. Rectangles, not connectors — connectors move when a slide is edited."""
    h = Pt(pt)
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def vrule(slide, x, y, h, pt=0.75, color=LINE):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Pt(pt), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def dot(slide, cx, cy, d, color):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def box(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def para(tf, first=False, align=PP_ALIGN.LEFT, space_before=0, line=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    if space_before:
        p.space_before = Pt(space_before)
    if line:
        p.line_spacing = line
    return p


def run(p, text, size, font=SANS, color=INK, bold=False, spc=None, caps=False):
    """spc is letter-spacing in POINTS — PowerPoint stores it as hundredths in @spc."""
    r = p.add_run()
    r.text = text.upper() if caps else text
    r.font.size = Pt(size)
    r.font.name = font
    r.font.bold = bold
    r.font.color.rgb = color
    if spc is not None:
        r._r.get_or_add_rPr().set("spc", str(int(round(spc * 100))))
    return r


_FONT_FILES = {}


def _font_file(family, bold):
    """Ask fontconfig for the actual file, so a headline is measured, not guessed."""
    key = (family, bold)
    if key not in _FONT_FILES:
        try:
            out = subprocess.run(
                ["fc-match", "-f", "%{file}",
                 "%s:weight=%s" % (family, "demibold" if bold else "regular")],
                check=True, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            out = ""
        _FONT_FILES[key] = out
    return _FONT_FILES[key]


def text_width(text, size, family=COND, bold=True, spc=-0.55):
    """Width in INCHES, measured off the TTF. None when the font cannot be found."""
    if ImageFont is None:
        return None
    path = _font_file(family, bold)
    if not path or not os.path.exists(path):
        return None
    font = ImageFont.truetype(path, int(round(size * 4)))   # 4x oversample
    return (font.getlength(text) / 4.0 + spc * len(text)) / 72.0


def headline(slide, y, lines, size=44, width=None, line=1.0):
    """A display headline. `lines` is one [(text, colour), ...] list, or a list of them.

    Line breaks are EXPLICIT, never left to the renderer: a headline that auto-wraps on the
    build machine wraps somewhere else on the presenting machine and lands on top of the block
    below it. Each line is measured against the column and an overflow raises here, at build
    time, rather than showing up as an overlap in front of a judge.
    """
    if lines and isinstance(lines[0], tuple):
        lines = [lines]
    w = width or CW
    tf = box(slide, M, y, w, 0.1 + 0.86 * (size / 44.0) * len(lines))
    for i, parts in enumerate(lines):
        text = "".join(t for t, _ in parts)
        measured = text_width(text, size)
        if measured is not None and measured > w:
            raise ValueError(
                "headline line overflows by %.2fin at %gpt — shorten it or drop a point:\n  %r"
                % (measured - w, size, text))
        p = para(tf, first=(i == 0), line=line)
        for t, color in parts:
            run(p, t, size, COND, color, bold=True, spc=-0.55)
    return tf


def standfirst(slide, y, text, width=None, size=15.5, color=INK2):
    tf = box(slide, M, y, width or 10.4, 1.0)
    p = para(tf, first=True, line=1.36)
    run(p, text, size, SANS, color)
    return tf


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ── the frame every slide wears ─────────────────────────────────────────────────────────────
def new_slide(prs, num, section, footnote=""):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(SW), Inches(SH))
    bg.fill.solid()
    bg.fill.fore_color.rgb = PAPER
    bg.line.fill.background()
    bg.shadow.inherit = False

    tf = box(slide, M, Y_EYEBROW, 7.0, 0.3)
    p = para(tf, first=True)
    run(p, "%02d" % num, 10, MONO, GREEN, bold=True, spc=1.0)
    run(p, "   /   ", 10, MONO, RGBColor(0xB6, 0xBE, 0xC4), spc=1.0)
    run(p, section, 10, SANS, INK, bold=True, spc=1.3, caps=True)

    tf = box(slide, SW - M - 6.0, Y_EYEBROW, 6.0, 0.3)
    p = para(tf, first=True, align=PP_ALIGN.RIGHT)
    run(p, "%s · %s · RUN %s" % (TEAM, CATEGORY, RUN_ID[:8].upper()), 9.5, MONO, INK3, spc=0.6)

    rule(slide, M, Y_IDRULE, CW, pt=1.6, color=INK)
    rule(slide, M, Y_FOOTRULE, CW, pt=0.75, color=LINE)

    if footnote:
        tf = box(slide, M, Y_FOOT, CW - 0.9, 0.4)
        p = para(tf, first=True, line=1.3)
        run(p, footnote, 9.5, SANS, INK3)

    tf = box(slide, SW - M - 0.8, Y_FOOT, 0.8, 0.3)
    p = para(tf, first=True, align=PP_ALIGN.RIGHT)
    run(p, "%02d" % num, 10, MONO, INK3, spc=0.6)
    return slide


def kpi_band(slide, y, items, num_size=30, num_color=INK, height=1.05):
    """The editorial number band: mono figure over a small caption, hairline-divided."""
    rule(slide, M, y, CW, pt=1.6, color=INK)
    n = len(items)
    colw = CW / n
    for i, (value, caption, color) in enumerate(items):
        x = M + i * colw
        if i:
            vrule(slide, x - 0.16, y + 0.16, height - 0.28, color=LINE)
        tf = box(slide, x, y + 0.20, colw - 0.34, 0.5)
        p = para(tf, first=True)
        run(p, value, num_size, MONO, color or num_color, bold=True, spc=-0.4)
        tf = box(slide, x, y + 0.20 + num_size / 72.0 + 0.12, colw - 0.34, 0.6)
        p = para(tf, first=True, line=1.28)
        run(p, caption, 10.5, SANS, INK2)


def rows(slide, y, items, row_h=0.62, label_w=3.5, gap=0.30,
         label_color=INK, body_size=12.6, label_size=12.6, label_font=SANS,
         label_bold=True, top_rule=True):
    """Hairline-divided editorial rows: a bold label, then its gloss."""
    if top_rule:
        rule(slide, M, y, CW, pt=1.2, color=INK)
    cy = y + 0.16
    for label, body, color in items:
        tf = box(slide, M, cy, label_w, row_h)
        p = para(tf, first=True, line=1.2)
        run(p, label, label_size, label_font, color or label_color, bold=label_bold)
        tf = box(slide, M + label_w + gap, cy, CW - label_w - gap, row_h)
        p = para(tf, first=True, line=1.3)
        run(p, body, body_size, SANS, INK2)
        cy += row_h
        rule(slide, M, cy - 0.12, CW, pt=0.75, color=LINE2)
    return cy


def caution_note(slide, y, w, lead, body):
    """A note with a red left rule. Red is a status, and it always has a word beside it."""
    h = 0.62
    vrule(slide, M, y, h, pt=2.5, color=CAUTION)
    tf = box(slide, M + 0.18, y + 0.02, w, h)
    p = para(tf, first=True, line=1.34)
    run(p, lead, 11.5, SANS, CAUTION, bold=True)
    run(p, body, 11.5, SANS, INK2)


# ── the nine slides ─────────────────────────────────────────────────────────────────────────
def slide_1_hook(prs):
    s = new_slide(prs, 1, "Hook",
                  "RHB Bank, Malaysia. Both readings are defensible. Only one of them is current.")
    headline(s, Y_HEAD, [[("Same company. Same day.", INK)],
                         [("Two different answers.", GREEN)]], size=46)
    standfirst(s, Y_HEAD + 1.58,
               "Its published ESG grade puts it in the bottom fifth of its own basket. Fourteen "
               "dated filings, exchange notices and news items say it is the fastest-improving "
               "name in it.", width=10.6)

    rail_y = 4.86
    rule(s, M + 2.6, rail_y, CW - 5.2, pt=2.0, color=LINE)
    x_left, x_right = M + 2.6, M + CW - 2.6
    dot(s, x_left, rail_y + 0.014, 0.17, RATING)
    dot(s, x_right, rail_y + 0.014, 0.17, EVIDENCE)

    tf = box(s, M + 2.6, rail_y - 1.05, CW - 5.2, 0.9)
    p = para(tf, first=True, align=PP_ALIGN.CENTER)
    run(p, "+0.80", 46, MONO, EVIDENCE, bold=True, spc=-1.6)
    p = para(tf, align=PP_ALIGN.CENTER)
    run(p, "DISAGREEMENT", 10, SANS, INK3, bold=True, spc=1.2)

    tf = box(s, M, rail_y + 0.30, 2.9, 1.1)
    p = para(tf, first=True)
    run(p, "ITS RATING SAYS", 10.5, SANS, RATING, bold=True, spc=0.6)
    p = para(tf, space_before=4)
    run(p, "18th", 21, MONO, INK, bold=True, spc=-0.6)
    run(p, "  of 52", 12, SANS, INK3)
    p = para(tf, space_before=3)
    run(p, "grade BB · bottom fifth", 10.5, SANS, INK3)

    tf = box(s, SW - M - 3.4, rail_y + 0.30, 3.4, 1.1)
    p = para(tf, first=True, align=PP_ALIGN.RIGHT)
    run(p, "THE EVIDENCE SAYS", 10.5, SANS, EVIDENCE, bold=True, spc=0.6)
    p = para(tf, align=PP_ALIGN.RIGHT, space_before=4)
    run(p, "98th", 21, MONO, INK, bold=True, spc=-0.6)
    run(p, "  percentile", 12, SANS, INK3)
    p = para(tf, align=PP_ALIGN.RIGHT, space_before=3)
    run(p, "14 dated sources · 2023–2026", 10.5, SANS, INK3)

    notes(s, """YOU SAY (~25s)
“One company, one day, two answers. Its ESG grade puts it in the bottom fifth of this basket. Fourteen dated sources — filings, exchange notices, news — say it's the fastest improver in the same basket. Neither of those is made up. Only one of them is current. So we built the thing that tells you which, and shows you the sources.”

IF PUSHED — “is the rating just wrong?”
“Not wrong, just late. It's a level, and the file closed months ago. We're not replacing it — we're putting a second opinion next to it with a date on every claim.”""")


def slide_2_problem(prs):
    s = new_slide(prs, 2, "Problem",
                  "Basket vs MSCI AC ASEAN, Jan 2021 – 28 Aug 2025, and the same note's YTD "
                  "figure. Source: CGSI, ESG momentum as an Alpha selection tool, 29 Aug 2025.")
    headline(s, Y_HEAD, [("A rating tells you where a company ", INK), ("stood.", GREEN)], size=46)
    standfirst(s, Y_HEAD + 0.80,
               "Not which way it is moving, and not what would change the answer. ESG momentum "
               "is a real edge — here is the half its own author reports too.", width=10.6)

    rows(s, 2.62, [
        ("A level, published late", "A score in a file closed months ago, refreshed on the "
                                    "rater's cycle — not the company's.", None),
        ("No direction", "Nothing in the number tells you whether the company is improving or "
                         "deteriorating right now.", None),
        ("Not challengeable", "You cannot ask a rating which piece of evidence is holding it up, "
                              "or what would change it.", None),
    ], row_h=0.70, label_w=3.5)

    kpi_band(s, 5.30, [
        ("+55.1%", "the basket, cumulative — against +6.4% for MSCI AC ASEAN", EVIDENCE),
        ("−4.6%", "the same basket, year-to-date 2025, on a ~45% banking weight", CAUTION),
        ("28.9%", "probability an ESG improver beats the index at one year", INK),
    ], num_size=31)

    notes(s, """YOU SAY (~35s)
“ESG momentum works — this basket beat the index by nearly fifty points over four years. Here's the other half, from the same research note: it's down 4.6% against the index this year, and a single ESG improver only beats the index about three times in ten at one year. So the question isn't whether ESG pays. It's that a rating gives you a level, and a level can't tell you which way anything is moving. That's the gap we went after.”

IF PUSHED — “why put your own bad number up?”
“Because it's in our own source document. Anyone who opens that note finds it in ten seconds, and then nothing else we said counts. Cheaper to say it first.”

Rule: the −4.6% goes in the same breath as the 55.1%, every time.""")


def slide_3_what(prs):
    s = new_slide(prs, 3, "What it is",
                  "All 52 names, one deterministic run. It never says buy, sell or hold, and it "
                  "publishes no score.")
    headline(s, Y_HEAD, [("We rank all 52 companies ", INK), ("twice.", GREEN)], size=46)
    standfirst(s, Y_HEAD + 0.78,
               "Once on the rating the market already uses. Once on dated public evidence. Then "
               "we report the gap — with a direction, a date on every source, and a list of what "
               "would change it.", width=10.6)

    col_w = (CW - 2 * 0.55) / 3
    beats = [
        ("Thinks", "It interrogates before it shows: four short questions that set the filters, "
                   "the risk tier and how fast old news stops counting. Every answer changes "
                   "what is on screen.", None),
        ("Challenges", "A loose framing comes back sharper. It pushes back on the question "
                       "instead of answering the wrong one.", None),
        ("Competes", "It takes a position against a named rating, on evidence the rating cannot "
                     "see — and shows its working.", EVIDENCE),
    ]
    top = 2.58
    for i, (title, body, color) in enumerate(beats):
        x = M + i * (col_w + 0.55)
        rule(s, x, top, col_w, pt=1.6, color=color or INK)
        tf = box(s, x, top + 0.16, col_w, 0.45)
        p = para(tf, first=True)
        run(p, title, 21, COND, color or INK, bold=True, spc=-0.3)
        if color:
            run(p, "   THE DIFFERENTIATOR", 8.5, SANS, EVIDENCE, bold=True, spc=1.1)
        tf = box(s, x, top + 0.70, col_w - 0.15, 1.4)
        p = para(tf, first=True, line=1.35)
        run(p, body, 12.4, SANS, INK2)

    kpi_band(s, 5.02, [
        ("24", "both agree — and we say so", INK),
        ("21", "improving, already rated for it", INK),
        ("4", "rated behind the evidence", EVIDENCE),
        ("2", "flattered by an old score", CAUTION),
        ("1", "poorly rated, still slipping", CAUTION),
    ], num_size=29)

    notes(s, """YOU SAY (~35s)
“Three things it does. It asks first — four short questions, and every answer actually changes what's on the board, so it's not a survey. It pushes back: give it something vague and you get the question back, sharper. And it competes — it takes a position against a named rating using dated evidence, and shows the working. Twenty-four times out of fifty-two we just agree with the rating, and we say so. Four times we think the rating is behind. Two companies are rated well while their evidence gets worse, and that quadrant is why this is an argument and not another ranking.”

IF PUSHED — “so it's a stock picker?”
“No. It doesn't rank anything for investment and it never recommends. It says we disagree with this rating, here's the dated evidence. Blend that into one number and none of us could tell you what the number means.”""")


def slide_4_prototype(prs):
    s = new_slide(prs, 4, "Prototype · live",
                  "Pre-flight: harness.py prints ALL CHECKS PASSED · server.py · real basket, "
                  "Demo OFF, tier Balanced. Held in reserve for Q&A: the tamper demo — one "
                  "character changes and the check flips to NO MATCH in about five seconds.")
    headline(s, Y_HEAD, [("Ninety seconds. Six clicks. ", INK),
                         ("Same answer.", GREEN)], size=46)

    beats = [
        ("0:00", "The board", "52 real companies, one deterministic run — the id is top-right. "
                              "Same files in, same answer out."),
        ("0:15", "Disagreement matrix", "Left–right: what the rating thinks. Bottom–top: what the "
                                        "evidence says. Hollow dots are companies with no "
                                        "evidence — we draw the absence."),
        ("0:30", "The RHB chip", "Rated 18th. Evidence 98th. Fourteen dated sources. One click, "
                                 "no hunting for the dot."),
        ("0:45", "Evidence trail", "Every signal dated, sourced, directional, with the reason it "
                                   "was weighted that way. Three clicks to the primary source."),
        ("1:05", "What would change this", "Pull any one source out and we re-score, and show "
                                           "which removals flip the verdict."),
        ("1:20", "Verify this evidence", "Recompute every hash against the root anchored on a "
                                         "public chain. MATCH — proof on-chain, no licensed data "
                                         "off the machine."),
    ]
    y = 2.02
    rule(s, M, y, CW, pt=1.2, color=INK)
    cy = y + 0.16
    for t, click, body in beats:
        tf = box(s, M, cy, 0.75, 0.4)
        p = para(tf, first=True)
        run(p, t, 12.5, MONO, INK3, bold=True, spc=-0.2)
        tf = box(s, M + 0.95, cy, 2.7, 0.4)
        p = para(tf, first=True)
        run(p, click, 12.8, SANS, INK, bold=True)
        tf = box(s, M + 3.85, cy, CW - 3.85, 0.7)
        p = para(tf, first=True, line=1.3)
        run(p, body, 12.2, SANS, INK2)
        cy += 0.63
        rule(s, M, cy - 0.13, CW, pt=0.75, color=LINE2)

    caution_note(s, 5.98, CW - 0.4, "No chain endpoint? The run says anchor_pending. ",
                 "It never claims to be anchored when it is not, and the check still runs "
                 "locally against the stored record.")

    notes(s, "RUN ORDER — six clicks, no hunting. Real basket, not Demo.\n\n"
             "0:00 board · 0:15 matrix · 0:30 RHB chip · 0:45 evidence trail + one source link · "
             "1:05 sensitivity · 1:20 verify.\n\n"
             "HELD IN RESERVE for Q&A: Tamper demo — change one character of one excerpt, the "
             "check flips to NO MATCH in about five seconds. That failure IS the feature.\n\n"
             "FAILURE MODES: no network → verification still runs locally and reports "
             "anchor_pending; never say 'anchored' when the chip says pending. A filter with "
             "nothing in it → say so: 'no name clears Conservative today' is a legitimate answer, "
             "and the counts prove it.")


def slide_5_holds(prs):
    s = new_slide(prs, 5, "Why the number holds",
                  "The rule was published on 25 Aug 2026, before the sweep ran and while the data "
                  "it judges did not yet exist. Adaro (2023) — the case we get wrong — stays in "
                  "the backtest, flagged.")
    headline(s, Y_HEAD, [("We wrote the bar down ", INK), ("before", GREEN),
                         (" the evidence.", INK)], size=44)

    qy = 1.92
    vrule(s, M, qy, 1.62, pt=3.0, color=GREEN)
    tf = box(s, M + 0.26, qy, 6.05, 1.6)
    p = para(tf, first=True, line=1.30)
    run(p, "A parameter may change for a reason that can be argued without reference to the "
           "answer it produces. It may not change because we dislike the answer.", 16.5, COND,
        INK, bold=True, spc=-0.2)
    tf = box(s, M + 0.26, qy + 1.72, 6.05, 0.4)
    p = para(tf, first=True)
    run(p, "PRE-REGISTERED · 25 AUG 2026 · BEFORE THE SWEEP", 9.5, SANS, INK3, bold=True, spc=1.1)

    rx = M + 6.85
    rule(s, rx, qy, CW - 6.85, pt=1.6, color=INK)
    guards = [
        ("Deterministic", "No clock, no randomness, no model in the scoring path. Same files, "
                          "same run id, same quadrants."),
        ("Five guards", "No date or no working source, the fact is dropped. We decide the source "
                        "type from the domain — never the publisher."),
        ("The cap that costs us", "Company-published material is capped at 0.5 confidence. 86% of "
                                  "a public search is company-published."),
    ]
    cy = qy + 0.18
    for label, body in guards:
        tf = box(s, rx, cy, CW - 6.85, 0.35)
        p = para(tf, first=True)
        run(p, label, 12.8, SANS, INK, bold=True)
        tf = box(s, rx, cy + 0.30, CW - 6.85, 0.7)
        p = para(tf, first=True, line=1.3)
        run(p, body, 11.8, SANS, INK2)
        cy += 1.02
        rule(s, rx, cy - 0.16, CW - 6.85, pt=0.75, color=LINE2)

    kpi_band(s, 5.08, [
        ("0", "thresholds moved to produce that list", INK),
        ("4", "names crossed the unmoved bar, on better sources", EVIDENCE),
        ("25", "signals on the best-covered company — the bar is reachable", INK),
        ("1", "published failure case kept in the backtest", CAUTION),
    ], num_size=32)

    notes(s, """YOU SAY (~45s)
“Two things hold this up. First, the model never scores anything — it reads, the rules score. Same files in, same answer out, and the test suite fails the build if that stops being true. Second, and this is the one I'd poke at if I were you: our top bar returned zero companies for weeks. The tempting fix is to lower it. Instead we wrote down, before the sweep ran, when we're allowed to move a threshold at all — you can move it for a reason you can argue without mentioning the answer, never because you don't like the answer. Then we went and found better sources. Four names crossed. Nobody touched a threshold. And the one we got wrong — Adaro, 2023 — is still in the backtest, because a backtest you can only pass isn't worth much.”

IF PUSHED — “a bug could still be hiding in there”
“One was, and it's written up. The model read target years as publication dates — 'net zero by 2050' came back dated 2050. That quietly decayed every company's momentum to zero while the signal counts still looked completely normal. Nothing crashed, nothing flagged. So now anything dated later than the basket's own cut-off gets dropped, and we can re-run the filters over evidence we already have without fetching it again.”""")


def slide_6_separates(prs):
    s = new_slide(prs, 6, "What separates us",
                  "Financial read: 17 strong · 22 adequate · 11 weak · 2 unknown, from two "
                  "audited fiscal years per company. A gate, computed after the scoring and "
                  "reported beside it — never inside it.")
    headline(s, Y_HEAD, [("The AI reads. The rules ", INK), ("score.", GREEN)], size=46)

    y = 2.02
    rule(s, M, y, CW, pt=1.6, color=INK)
    tf = box(s, M + 3.95, y + 0.10, 3.3, 0.3)
    p = para(tf, first=True)
    run(p, "THEY DO", 9, SANS, INK3, bold=True, spc=1.2)
    tf = box(s, M + 7.55, y + 0.10, 4.0, 0.3)
    p = para(tf, first=True)
    run(p, "WE DO", 9, SANS, EVIDENCE, bold=True, spc=1.2)
    cy = y + 0.44
    comparisons = [
        ("A rating", "Publishes a level, late",
         "Publishes a gap, with a direction and a date on every source"),
        ("A stock picker", "One blended number",
         "Two axes, never merged — ESG evidence, and a separate money gate"),
        ("Chain ESG platforms", "Issuer-side: the company writes its own data to a chain",
         "Investor-side and adversarial — the company's own word is our least-trusted source"),
        ("“AI-scored ESG”", "A model assigns the score",
         "The model only gathers; scoring is rule-based and costs zero tokens"),
    ]
    for label, them, us in comparisons:
        tf = box(s, M, cy, 3.7, 0.6)
        p = para(tf, first=True, line=1.25)
        run(p, label, 13, SANS, INK, bold=True)
        tf = box(s, M + 3.95, cy, 3.4, 0.7)
        p = para(tf, first=True, line=1.28)
        run(p, them, 11.8, SANS, INK3)
        tf = box(s, M + 7.55, cy, CW - 7.55, 0.7)
        p = para(tf, first=True, line=1.28)
        run(p, us, 11.8, SANS, INK2)
        cy += 0.80
        rule(s, M, cy - 0.16, CW, pt=0.75, color=LINE2)

    ny = cy + 0.16
    vrule(s, M, ny, 0.86, pt=3.0, color=EVIDENCE)
    tf = box(s, M + 0.26, ny, CW - 0.5, 0.9)
    p = para(tf, first=True, line=1.32)
    run(p, "UOB clears the ESG bar and fails the money read", 15, COND, INK, bold=True, spc=-0.2)
    run(p, "  — earnings down 22.6%. We show both and never average them. One combined score "
           "would have buried it.", 13, SANS, INK2)

    notes(s, """YOU SAY (~35s)
“Three separations do the work. The model reads and the rules score, so a verdict can't be a hallucination — and scoring costs nothing in tokens, because there's no model in it. The ESG side and the money side never get averaged: UOB is rated behind its evidence and its earnings are down 22.6%, and you can see both because we refused to merge them. And the chain-based ESG platforms people compare us to are issuer-side — a company evidencing its own claims. We're at the other end of that pipe. A company's own press release is the least trusted thing we hold.”

IF PUSHED — “what's the blockchain actually for?”
“It's the receipt, not the check. A chain can't verify anything that happened off it — make a false claim immutable and all you've got is a permanent false claim. The checking is done by rules you can read. The chain just proves the verdict you saw was built on the evidence we said it was.”""")


def slide_7_investment(prs):
    s = new_slide(prs, 7, "Investment",
                  "Measured over a full 28-company sweep: 4 calls and ~6,059 tokens per company, "
                  "yielding ~5.3 dated facts. DeepSeek published card, off-peak; peak is exactly "
                  "2×, and a sweep is a batch job.")
    headline(s, Y_HEAD, [("S$0.079 per company per year. ", INK), ("Measured.", GREEN)],
             size=44)

    kpi_band(s, 1.86, [
        ("S$4.12", "a year to cover the whole 52-company basket", INK),
        ("S$39.65", "a year at 500 companies", INK),
        ("S$158.60", "a year at 2,000 companies", INK),
        ("S$118.45", "total spend to build what you just saw", EVIDENCE),
    ], num_size=29)

    rows(s, 3.22, [
        ("Zero marginal scoring", "Rules route the evidence and deterministic code scores it. No "
                                  "language model is reachable from either — per-signal token "
                                  "cost is structurally zero.", EVIDENCE),
        ("All AI cost is gathering", "Charged per sweep of a company, not per signal. Running "
                                     "sweeps off-peak is an exact 50% saving.", None),
        ("People, not tokens", "Metadata verification is hand-done. Day rates come from live "
                               "Singapore job postings — ESG analyst S$290/day — and are flagged "
                               "as a floor.", None),
        ("Pilot: S$34,965 people cost", "The pilot total is stamped INCOMPLETE, because the data "
                                        "licence and compliance lines are still blank.", None),
    ], row_h=0.68, label_w=3.7)

    caution_note(s, 6.06, CW - 0.4, "No falling cost-per-company curve until a licence quote exists. ",
                 "Inference is linear in companies, so on this cost alone that line is flat. Two "
                 "inputs are on the slide as blanks: a baseline-data licence quote, and one timed "
                 "batch of ten companies.")

    notes(s, """YOU SAY (~40s)
“The economics are odd, because of how it's built. Scoring is rules, not a model, so it costs nothing. All the AI spend is in gathering, and it's charged per sweep of a company rather than per signal — about eight cents a company a year, four dollars for the whole basket. The entire prototype cost a hundred and eighteen Singapore dollars. What I'm not going to show you is a falling cost-per-company curve. Inference is linear, so that line only bends once a data licence gets spread across clients, and we don't have a quote yet. Two cells on that slide are blank on purpose — a made-up number in a cost model is worse than an empty one, because nobody asks about a number that looks plausible.”

IF PUSHED — “what would you do with support?”
“Better sources, not more of them. Regulator actions, exchange filings, index-provider decisions — the things that aren't press releases. That's the ceiling on how confident this can get, and it's a procurement problem, not an engineering one.”""")


def slide_8_earth(prs):
    s = new_slide(prs, 8, "Down to earth",
                  "Green-bond and traction thresholds are ours — team-designed, never confirmed "
                  "by the CGSI panel — and every surface says so.")
    headline(s, Y_HEAD, [("What it does ", INK), ("not", CAUTION), (" do.", INK)], size=46)
    standfirst(s, Y_HEAD + 0.78,
               "On the slide, before anyone has to ask.", width=10.6)

    rows(s, 2.42, [
        ("86% is self-published", "Most of what a public search returns is written by the "
                                  "companies themselves, and we cap how far that can ever count. "
                                  "That is why the top quadrant holds four names, not forty.",
         None),
        ("Documentary, not telemetry", "We read filings, regulator actions, exchange notices and "
                                       "press. We do not meter a smokestack.", None),
        ("2 of 52 have no evidence", "Drawn hollow on the matrix and counted. An absence of "
                                     "evidence is a finding, not a hole to fill.", None),
        ("11 of 52 are financially weak", "And 2 are unreadable — reported as unknown, never "
                                          "marked down for our missing data.", None),
        ("Licensed raters stay off-screen", "MSCI, S&P and Sustainalytics cannot be shown — "
                                            "licence, not capability. LSEG is fetched live "
                                            "because it is the one free keyless endpoint.", None),
        ("Two delisted names stay in", "Badged, and excluded from investable output by rule. A "
                                       "static list going stale is the argument.", None),
    ], row_h=0.68, label_w=3.9, body_size=12.2)

    notes(s, """YOU SAY (~30s)
“The limits, up front. We read documents, not sensors — no satellites, no meters on anything. Most of what a public search gives you is written by the companies themselves, and we cap how much that can ever count, which is exactly why the top quadrant has four names in it and not forty. Two companies have no evidence at all, and we draw the hole instead of filling it. Eleven are financially weak and we say so — you'll only believe the seventeen strong ones if we didn't quietly drop the weak ones.”

IF PUSHED — “only four? that's thin”
“It is thin, and it's what the rules gave us. A screen that returns a third of the universe isn't a screen. More names means better sources, not a lower bar — drop the bar and 'rated behind the evidence' starts to mean 'we found a lot of press releases', which is exactly how the Adaro case went wrong.”""")


def slide_9_close(prs):
    s = new_slide(prs, 9, "Close",
                  "Every figure on this deck re-derives from run %s on a judge's laptop, offline. "
                  "Whitepaper and deck carry the same numbers." % RUN_ID)
    headline(s, Y_HEAD, [[("It never says buy or sell. It says where it ", INK),
                          ("disagrees", GREEN)],
                         [("— and exactly what would change its mind.", INK)]], size=40)

    kpi_band(s, 3.30, [
        ("52", "ASEAN companies, one verified research basket", INK),
        ("391", "dated, sourced events behind the verdicts — 48 of 52 covered", INK),
        ("S$0.079", "AI cost per company per year, measured", INK),
        ("0", "thresholds moved to produce our list", EVIDENCE),
    ], num_size=40, height=1.35)

    ny = 5.40
    vrule(s, M, ny, 0.92, pt=3.0, color=GREEN)
    tf = box(s, M + 0.26, ny, CW - 0.6, 1.0)
    p = para(tf, first=True, line=1.34)
    run(p, "The bar was fixed before the evidence existed, and the quadrant filled because we "
           "found better sources — not a smaller number.", 15.5, SANS, INK2)

    notes(s, """YOU SAY (~25s)
“Fifty-two companies. Three hundred and ninety-one dated sources. Eight cents a company a year. And zero thresholds moved to get there — we fixed the bar before we had the evidence, and the names showed up because we found better sources, not a smaller number. All of it rebuilds from that run id on your laptop, offline. It won't tell you what to buy. It'll tell you where the market's view and the evidence disagree, and what would change its mind.”

Running long? Cut the third sentence. The rest is doing work.

Never: buy · sell · hold · “our score”. Never 55.1% without −4.6%. Never 29.4% without CGSI's three filters.""")


def build(path=OUT_PPTX):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
    for fn in (slide_1_hook, slide_2_problem, slide_3_what, slide_4_prototype, slide_5_holds,
               slide_6_separates, slide_7_investment, slide_8_earth, slide_9_close):
        fn(prs)
    cp = prs.core_properties
    cp.title = "ASEAN ESG Momentum Radar — a second opinion on every ESG rating in ASEAN"
    cp.author = "Quill & Candle"
    cp.comments = ("Every figure derives from engine run %s. Script and source table: "
                   "docs/pitch/slides.md" % RUN_ID)
    prs.save(path)
    return path


def to_pdf(pptx_path):
    outdir = os.path.dirname(pptx_path)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir,
                    pptx_path], check=True, capture_output=True, timeout=300)
    return os.path.splitext(pptx_path)[0] + ".pdf"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=OUT_PPTX)
    ap.add_argument("--pdf", action="store_true",
                    help="also render a PDF via LibreOffice (embeds the fonts)")
    args = ap.parse_args(argv)
    path = build(args.out)
    print("wrote %s" % os.path.relpath(path, BASE_DIR))
    if args.pdf:
        print("wrote %s" % os.path.relpath(to_pdf(path), BASE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
