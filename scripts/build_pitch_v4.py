#!/usr/bin/env python3
"""
build_pitch_v4.py — the SPOKEN pitch as a deck, in the v3 house style.
======================================================================

`ESG_Radar_Pitch_v3.pptx` was built by copying an existing deck (`IT2513_DS.pptx`) and
remapping content onto it, so the type system, palette, chips, footers and grid survived
intact. This does the same thing one generation on: **v3 is the template**, and the content
remapped onto it is the six-speaker pitch script (Sean · Cayden · Brina · Rai · Grace ·
Jayden), in the order it is actually said.

    venv/bin/python -m scripts.build_pitch_v4            # -> docs/pitch/ESG_Radar_Pitch_v4.pptx
    venv/bin/python -m scripts.build_pitch_v4 --pdf      # also render a PDF via LibreOffice

WHY REMAP RATHER THAN DRAW
--------------------------
Every measurement on these slides — the 0.85in margin, the 4.55in left column, the hairline
weights, the chip box, the footer baseline — was decided once and is correct. Re-drawing them
from primitives is how a deck drifts. So the geometry is inherited and only the words move.

THE ORDER CHANGED, NOT JUST THE WORDS
-------------------------------------
The script COLD-OPENS on the hook and only then introduces the team, so slide 1 is v3's slide 3
and the cover moves to position 2. v3's cost and constraints slides are not in the spoken
script — they are kept as APPENDIX A1/A2, because they are the two questions a judge asks and
their numbers are real.

EVERY FIGURE ON A SLIDE TRACES TO A FILE
----------------------------------------
    52 companies · run 1fc384a2fa92499d · 391 dated events   data/nmk_frozen.json
    N 13 / M 10 / K 1                                        data/nmk_frozen.json
    S$0.079 per company per year                             cost_model.py (measured tokens)
    Top Glove: 19 months (2018-12-15 -> 2020-07-15)          docs/backtest/series.json
    Conservative / Balanced / Aggressive                     data/engine_config.json
The two market figures (75% of EM sustainable bonds unrated; 0bp EM greenium) are external and
carry their source on the References slide, exactly as they did in v3.

FONTS: IBM Plex Serif / Sans / Sans Light / Mono. Installed here; on a machine without them
PowerPoint substitutes and the line breaks move — present the PDF instead.
"""

import argparse
import copy
import os
import shutil
import subprocess
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root, one level up
TEMPLATE = os.path.join(BASE_DIR, "docs", "pitch", "ESG_Radar_Pitch_v3.pptx")
OUT = os.path.join(BASE_DIR, "docs", "pitch", "ESG_Radar_Pitch_v4.pptx")

RUN_ID = "1fc384a2fa92499d"
EVENTS = "391"
UNIVERSE = "52"
MEMBERS = "Sean Liu · Jayden Yip · Vrishabd Rai · Cayden Sar · Brina Ng · Grace Kang"


# ── style registry: harvest every run style already in the deck ─────────────────────────────
def fam(name):
    if not name:
        return ""
    if "Light" in name:
        return "sanslight"
    if "Mono" in name:
        return "mono"
    if "Serif" in name:
        return "serif"
    return "sans"


def build_registry(slides):
    reg = {}

    def scan(shape_iter):
        for s in shape_iter:
            if s.shape_type == 6:
                scan(s.shapes)
                continue
            if not getattr(s, "has_text_frame", False):
                continue
            for p in s.text_frame.paragraphs:
                for r in p.runs:
                    rPr = r._r.find(qn("a:rPr"))
                    if rPr is None:
                        continue
                    col = None
                    fill = rPr.find(qn("a:solidFill"))
                    if fill is not None:
                        srgb = fill.find(qn("a:srgbClr"))
                        if srgb is not None:
                            col = srgb.get("val")
                    reg.setdefault((r.font.name, rPr.get("sz"), rPr.get("b"), col), rPr)

    for sl in slides:
        scan(sl.shapes)
    return reg


def make_donor(reg):
    def donor(name=None, famx=None, size=None, color=None, bold=None):
        for (n, sz, b, c), rPr in reg.items():
            if name and n != name:
                continue
            if famx and fam(n) != famx:
                continue
            if size is not None and sz != str(int(round(size * 100))):
                continue
            if color and c != color:
                continue
            if bold is not None and (b or "0") != ("1" if bold else "0"):
                continue
            return rPr
        raise KeyError(("donor missing", name, famx, size, color, bold))
    return donor


# ── shape helpers ───────────────────────────────────────────────────────────────────────────
def walk(shapes):
    for s in shapes:
        if s.shape_type == 6:
            yield from walk(s.shapes)
        else:
            yield s


def by(slide, name):
    """Look a shape up by NAME. Names are stable across a re-text; text is not."""
    for s in walk(slide.shapes):
        if s.name == name:
            return s
    raise KeyError((name, [s.name for s in walk(slide.shapes)]))


def find(slide, snippet, nth=0):
    hits = [s for s in walk(slide.shapes)
            if getattr(s, "has_text_frame", False) and snippet in s.text_frame.text]
    if not hits:
        raise KeyError(snippet)
    return hits[min(nth, len(hits) - 1)]


def set_text(shape, paras):
    """paras: list of paragraphs, each a list of (text, donor_rPr_or_None)."""
    tf = shape.text_frame
    body = tf._txBody
    ps = body.findall(qn("a:p"))
    pPr0 = ps[0].find(qn("a:pPr"))
    for p in ps[1:]:
        body.remove(p)
    p0 = ps[0]
    for tag in ("a:r", "a:br", "a:fld"):
        for el in p0.findall(qn(tag)):
            p0.remove(el)
    first = True
    for para in paras:
        if first:
            p, first = p0, False
        else:
            p = p0.makeelement(qn("a:p"), {})
            if pPr0 is not None:
                p.append(copy.deepcopy(pPr0))
            body.append(p)
        for text, rPr in para:
            r = p.makeelement(qn("a:r"), {})
            if rPr is not None:
                r.append(copy.deepcopy(rPr))
            t = p.makeelement(qn("a:t"), {})
            t.text = text
            r.append(t)
            end_el = p.find(qn("a:endParaRPr"))
            if end_el is not None:
                end_el.addprevious(r)
            else:
                p.append(r)


def move(shape, x=None, y=None, w=None, h=None):
    if x is not None:
        shape.left = Inches(x)
    if y is not None:
        shape.top = Inches(y)
    if w is not None:
        shape.width = Inches(w)
    if h is not None:
        shape.height = Inches(h)


def rm(shape):
    shape._element.getparent().remove(shape._element)


def outline(shape, rgb):
    """Chips and panels carry their meaning in the outline colour, not only the text."""
    shape.line.color.rgb = RGBColor.from_string(rgb)


def emphasis(shape, fill=None, line="C9C0B2"):
    """Move a diagram's highlight. `fill=None` returns a box to plain."""
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
    shape.line.color.rgb = RGBColor.from_string(line)


def set_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def dup_slide(prs, src):
    """Clone a slide, shapes and all, onto the end of the deck."""
    dst = prs.slides.add_slide(src.slide_layout)
    for shp in list(dst.shapes):                       # drop the layout's placeholders
        rm(shp)
    for shp in src.shapes:
        dst.shapes._spTree.append(copy.deepcopy(shp._element))
    return dst


def reorder(prs, order):
    """order: list of slide objects, in the sequence they should appear."""
    lst = prs.slides._sldIdLst
    ids = {id(s): sid for s, sid in zip(prs.slides, list(lst))}
    for sid in list(lst):
        lst.remove(sid)
    for s in order:
        lst.append(ids[id(s)])


# ── the build ───────────────────────────────────────────────────────────────────────────────
def build(template=TEMPLATE, out=OUT):
    shutil.copy(template, out)
    prs = Presentation(out)
    sl = list(prs.slides)
    donor = make_donor(build_registry(sl))

    S = {
        "title":   donor(famx="serif", size=46, color="1A1714", bold=True),
        "head":    donor(famx="serif", size=30, color="1A1714", bold=True),
        "sub22":   donor(famx="sanslight", size=22, color="6E655A"),
        "lab13":   donor(name="IBM Plex Mono Medium", size=13, color="6E655A"),
        "val15":   donor(name="IBM Plex Mono", size=15, color="1A1714"),
        "val13":   donor(name="IBM Plex Mono", size=13, color="1A1714"),
        "sch13":   donor(famx="sans", size=13, color="6E655A"),
        "seclab":  donor(name="IBM Plex Mono Medium", size=11, color="6E655A"),
        "foot":    donor(name="IBM Plex Mono", size=11, color="6E655A"),
        "chip_t":  donor(name="IBM Plex Mono Medium", size=12, color="0F6B5F", bold=True),
        "chip_a":  donor(name="IBM Plex Mono Medium", size=12, color="9C5B15", bold=True),
        "chip10t": donor(name="IBM Plex Mono Medium", size=10, color="0F6B5F", bold=True),
        "b18":     donor(famx="sans", size=18, color="1A1714"),
        "m17":     donor(famx="mono", size=17, color="1A1714"),
        "b17":     donor(famx="sans", size=17, color="1A1714"),
        "m21":     donor(famx="mono", size=21, color="6E655A"),
        "lab_t12": donor(name="IBM Plex Mono Medium", size=12, color="0F6B5F"),
        "lab_a12": donor(name="IBM Plex Mono Medium", size=12, color="9C5B15"),
        "box11":   donor(name="IBM Plex Mono Medium", size=11, color="1A1714"),
        "box11a":  donor(name="IBM Plex Mono Medium", size=11, color="9C5B15"),
        "lab_t11": donor(name="IBM Plex Mono Medium", size=11, color="0F6B5F"),
        "lab_a11": donor(name="IBM Plex Mono Medium", size=11, color="9C5B15"),
        "cap13":   donor(famx="sans", size=13, color="6E655A"),
        "cap15":   donor(famx="sans", size=15, color="1A1714"),
        "m13g":    donor(name="IBM Plex Mono", size=13, color="6E655A"),
        "m13t":    donor(name="IBM Plex Mono", size=13, color="0F6B5F"),
        "m13a":    donor(name="IBM Plex Mono Medium", size=13, color="9C5B15"),
        "sm14g":   donor(famx="sans", size=14, color="6E655A"),
        "sm14a":   donor(famx="sans", size=14, color="9C5B15"),
        "m14i":    donor(name="IBM Plex Mono", size=14, color="1A1714"),
        "m14t":    donor(name="IBM Plex Mono Medium", size=14, color="0F6B5F"),
        "s16":     donor(famx="sans", size=16, color="1A1714"),
        "s16a":    donor(famx="sans", size=16, color="9C5B15"),
        "m15a":    donor(famx="mono", size=15, color="9C5B15"),
        "m15t":    donor(name="IBM Plex Mono Medium", size=15, color="0F6B5F"),
        "s12g":    donor(famx="sans", size=12, color="6E655A"),
        "demolab": donor(name="IBM Plex Mono Medium", size=9, color="6E655A"),
    }

    def foot(slide, label):
        shp = find(slide, "POLYFINTECH100  ·  ESG  ·")
        set_text(shp, [[(f"POLYFINTECH100  ·  ESG  ·  {label}", S["foot"])]])
        move(shp, w=5.00)          # the appendix labels are longer than "10 / 10"

    def head(slide, eyebrow, title, chip, chip_style="chip_t"):
        if eyebrow is not None:
            set_text(by(slide, "TextBox 1"), [[(eyebrow, S["seclab"])]])
        set_text(by(slide, "TextBox 2"), [[(title, S["head"])]])
        if chip is not None:
            set_text(by(slide, "Rectangle 5"), [[(chip, S[chip_style])]])

    cover, s_problem, s_hook, s_solve, s_diff, s_demo, s_cost, s_face, s_cta, s_refs = sl

    # ═══ 1 · THE HOOK — Sean (was v3 slide 3: three statements + two bars) ═══════════════════
    s = s_hook
    head(s, "(A)  THE HOOK", "You see the return. Not the risk.", "UNPRICED", "chip_a")
    set_text(by(s, "TextBox 7"),
             [[("Put in ", S["b18"]), ("S$100", S["m17"]), (" expecting ", S["b18"]),
               ("S$150", S["m17"]), (" back — and walk away with ", S["b18"]),
               ("S$50", S["m17"]), (" instead", S["b18"])]])
    set_text(by(s, "TextBox 9"),
             [[("What if a score told you how much risk a company carries — the higher the score, "
                "the lower the risk?", S["b18"])]])
    set_text(by(s, "TextBox 11"),
             [[("And what if you could see that score ", S["b18"]), ("moving", S["m17"]),
               (" — before the headline, not after?", S["b18"])]])
    set_text(by(s, "TextBox 13"), [[("WHAT YOU EXPECTED", S["seclab"])]])
    move(by(s, "Rectangle 14"), w=4.60)                          # 150 -> 4.60in
    set_text(by(s, "TextBox 15"), [[("S$150", S["m13g"])]])
    move(by(s, "TextBox 15"), x=6.05 + 4.60 + 0.15, y=2.54)      # beside the bar, not under it
    set_text(by(s, "TextBox 16"), [[("WHAT YOU GOT", S["lab_a11"])]])
    move(by(s, "Rectangle 17"), w=4.60 / 3.0)                    # 50 on the same scale as 150
    set_text(by(s, "TextBox 18"), [[("S$50", S["m13a"])]])
    move(by(s, "TextBox 18"), x=6.05 + 4.60 / 3.0 + 0.15)
    set_text(by(s, "TextBox 19"),
             [[("Illustrative. We are not removing the risk — we are letting you see it before "
                "you commit.", S["cap13"])]])
    foot(s, "01 / 09")
    set_notes(s, "SEAN — Who doesn't like making money? I certainly do. And what are the main ways "
                 "to earn it? Jobs, business, and investing. [BEAT] But investing feels risky and "
                 "uncertain. You could put a hundred dollars into a stock expecting a hundred and "
                 "fifty back and walk away with fifty instead. What if there were a score that told "
                 "you how much risk a company carries — the higher the score, the lower the risk? "
                 "And a tool that uses that score, and its momentum, to show you where the risk is "
                 "heading? [BEAT] We're not eliminating risk. We are finally letting you see it "
                 "before you commit.")

    # ═══ 2 · TITLE + TEAM — Sean (v3 slide 1) ═══════════════════════════════════════════════
    s = cover
    set_text(by(s, "TextBox 1"), [[("ESG Momentum Radar", S["title"])]])
    set_text(by(s, "TextBox 2"), [[("See the risk before you commit", S["sub22"])]])
    set_text(by(s, "TextBox 6"), [[("ESG  ·  MOMENTUM RADAR", S["val15"])]])
    set_text(by(s, "TextBox 8"), [[("Quill & Candle", S["val15"])]])
    set_text(by(s, "TextBox 10"), [[(MEMBERS, S["val13"])]])
    set_text(by(s, "TextBox 12"), [[("PolyFinTech100  ·  2026", S["val15"])]])
    set_notes(s, "SEAN — We're Quill and Candle: Sean, Jayden, Rai, Cayden, Brina and Grace. And "
                 "this is the ESG Momentum Radar.")

    # ═══ 3 · THE PROBLEM — Cayden (was v3 slide 2: four statements + two pipelines) ══════════
    s = s_problem
    head(s, "(B)  THE PROBLEM", "By the time you find out, it's gone.", "LATE", "chip_a")
    set_text(by(s, "TextBox 7"),
             [[("We have all heard the stories — a stock that crashed overnight", S["b18"])]])
    set_text(by(s, "TextBox 9"),
             [[("Hundreds of companies to choose from, and nothing to tell them apart",
                S["b18"])]])
    set_text(by(s, "TextBox 11"),
             [[("The rating meant to warn you comes ", S["b18"]),
               ("once a year", S["m17"]), (", after the fact", S["b18"])]])
    set_text(by(s, "TextBox 13"),
             [[("By the time something goes wrong, you have already lost the money", S["b18"])]])
    outline(by(s, "Rectangle 5"), "9C5B15")                      # the chip reads LATE, not VALID
    set_text(by(s, "TextBox 15"), [[("WHAT YOU GET TODAY", S["seclab"])]])
    move(by(s, "TextBox 15"), w=3.60)
    set_text(by(s, "Rectangle 16"), [[("DISCLOSE", S["box11"])]])
    set_text(by(s, "Rectangle 18"), [[("RATE", S["box11"])]])
    set_text(by(s, "Rectangle 20"), [[("PUBLISH", S["box11"])]])
    set_text(by(s, "Rectangle 22"), [[("TOO LATE", S["box11a"])]])
    emphasis(by(s, "Rectangle 20"))                              # PUBLISH is not the point
    emphasis(by(s, "Rectangle 22"), fill="EFE3D2", line="9C5B15")  # being late is
    set_text(by(s, "TextBox 23"), [[("WHAT THE RADAR DOES", S["seclab"])]])
    move(by(s, "TextBox 23"), w=3.60)
    set_text(by(s, "Rectangle 24"), [[("EVENT", S["box11"])]])
    set_text(by(s, "Rectangle 26"), [[("SIGNAL", S["box11"])]])
    set_text(by(s, "Rectangle 28"), [[("YOU SEE IT", S["box11"])]])
    set_text(by(s, "TextBox 29"),
             [[("A rating tells you where a company stands. Nobody was telling you which way it "
                "was moving.", S["cap13"])],
              [("The warning is usually public long before the crash — it just isn't being read.",
                S["cap13"])]])
    foot(s, "03 / 09")
    set_notes(s, "CAYDEN — So what exactly makes investing feel so risky and uncertain? We have "
                 "heard the stories of stocks crashing overnight. There are dozens of companies to "
                 "choose from and nothing to tell them apart. [BEAT] And the rating that was "
                 "supposed to warn you comes out once a year, after the fact — so by the time "
                 "something goes wrong, you've already lost your money.")

    # ═══ 4 · HOW WE SOLVE IT — Brina (was v3 slide 4: statements + the four quadrants) ═══════
    s = s_solve
    head(s, "(C)  WHAT WE BUILT", "Three fears. Three answers.", "ANSWERED")
    set_text(by(s, "TextBox 7"),
             [[("Afraid of losing money — set one of ", S["b18"]),
               ("three risk tiers", S["m17"])]])
    set_text(by(s, "TextBox 9"),
             [[("Don't know where to start — ", S["b18"]), (UNIVERSE, S["m17"]),
               (" names sorted into four quadrants, not a list", S["b18"])]])
    set_text(by(s, "TextBox 11"),
             [[("Never saw it coming — live sources read daily: news, filings, hiring",
                S["b18"])]])
    set_text(by(s, "TextBox 13"),
             [[("Momentum, not a rating that moves once a year — a company sliding for three "
                "months shows up as a warning", S["b18"])]])
    for qn_, qlab, qdesc, qstyle in (
            ("Q_HW", "HIDDEN WINNERS", "rated low, rising fast", "lab_t11"),
            ("Q_FL", "FUTURE LEADERS", "rated high, still rising", "box11"),
            ("Q_VT", "VALUE TRAPS", "rated low, and declining", "lab_a11"),
            ("Q_OL", "OVERRATED LEADERS", "rated high, but eroding", "lab_a11")):
        set_text(by(s, qn_), [[(qlab, S[qstyle])], [(qdesc, S["cap13"])]])
    set_text(by(s, "TextBox 16"),
             [[("Four quadrants — CGSI's own framework, drawn live from " + EVENTS + " dated "
                "events, re-segmented by the tier you set: Conservative, Balanced or "
                "Aggressive.", S["cap13"])]])
    set_text(by(s, "TextBox 18"), [[("NEXT · A LIVE WALK THROUGH ALL THREE", S["demolab"])]])
    set_text(by(s, "TextBox 19"), [[(UNIVERSE + " companies, scored on CGSI's own data",
                                     S["m13t"])]])
    move(by(s, "TextBox 19"), w=6.40)
    set_text(by(s, "TextBox 20"), [[(EVENTS + " dated events behind every call", S["m13g"])]])
    move(by(s, "TextBox 20"), w=6.40)
    foot(s, "04 / 09")
    set_notes(s, "BRINA — So how does our app solve these issues? [BEAT] You're afraid of losing "
                 "money, so we let you set your risk appetite, split into three tiers. The radar "
                 "adjusts what it shows you based on how much risk you're comfortable with. "
                 "[BEAT] You don't know where to start, so we sort every company into four "
                 "quadrants. You're not scrolling through hundreds of names — you're looking at a "
                 "graph that tells you where each one stands. [BEAT] You had no way of seeing it "
                 "coming, so our AI reads live sources daily: news, filings, hiring patterns. It "
                 "tracks the company's momentum, not a rating that updates once a year. If a "
                 "company's been declining for three months, you see the trend before the headline "
                 "hits. [BEAT] But you don't need to imagine it — we'll show you right now.")

    # ═══ 5 · THE DEMO — Rai (was v3 slide 6: the four-column table) ══════════════════════════
    s = s_demo
    head(s, "(C)  WHAT WE BUILT", "You don't have to imagine it.", "RUNNING")
    set_text(by(s, "TextBox 7"), [[("STEP", S["seclab"])]])
    set_text(by(s, "TextBox 8"), [[("THE FEAR", S["seclab"])]])
    set_text(by(s, "TextBox 9"), [[("WHAT RAI DOES", S["seclab"])]])
    set_text(by(s, "TextBox 10"), [[("WHAT THE BOARD DOES", S["seclab"])]])
    table = [
        ("TextBox 12", "TextBox 13", "TextBox 14", "TextBox 15",
         "01", "losing money", "sets a risk appetite", "52 names re-segment"),
        ("TextBox 17", "TextBox 18", "TextBox 19", "TextBox 20",
         "02", "where do I start", "reads the four quadrants", "every name placed"),
        ("TextBox 22", "TextBox 23", "TextBox 24", "TextBox 25",
         "03", "never saw it coming", "opens one company", "its dated trail"),
        ("TextBox 28", "TextBox 29", "TextBox 30", "TextBox 31",
         "04", "can I trust this", "clicks any figure", "source · date · link"),
        ("R5C1", "R5C2", "R5C3", "R5C4",
         "05", "just ask it", "types a company name", "found, and kept"),
    ]
    for n1, n2, n3, n4, v1, v2, v3, v4 in table:
        set_text(by(s, n1), [[(v1, S["m14t"])]])
        set_text(by(s, n2), [[(v2, S["m14i"])]])
        set_text(by(s, n3), [[(v3, S["sm14g"])]])
        set_text(by(s, n4), [[(v4, S["m14t"])]])
    set_text(by(s, "TextBox 33"),
             [[("Everything on this list runs on the live prototype — " + UNIVERSE +
                " companies, " + EVENTS + " dated events, run " + RUN_ID + ". "
                "Nothing on screen is a mock-up.", S["sm14g"])]])
    foot(s, "05 / 09")
    set_notes(s, "RAI — Live demonstration. One: set the risk appetite and watch 52 names "
                 "re-segment — the ones that fail your filter dim, they don't disappear. Two: the "
                 "four quadrants, so you're not reading a list. Three: open a company and show the "
                 "dated trail behind the verdict. [BEAT] If anyone asks whether it can be trusted: "
                 "click any figure and it gives you the source, the date and the link. Top Glove's "
                 "warnings were public nineteen months before the US ban — and it stayed on the "
                 "sustainability index the whole time. That's the gap this reads.")

    # ═══ 6 · WHAT MAKES OURS DIFFERENT — Grace (was v3 slide 5: two panels + arrow) ══════════
    s = s_diff
    head(s, "(D)  WHAT SETS US APART", "They read the price. We read the change.", "DIFFERENT")
    set_text(by(s, "TextBox 7"),
             [[("Other platforms track the price. ", S["sub22"]), ("We track the risk", S["m21"]),
               (" — and whether anyone else has noticed.", S["sub22"])]])
    set_text(by(s, "TextBox 8"), [[("WHAT THEY TRACK", S["lab_a12"])]])
    outline(by(s, "Rectangle 9"), "9C5B15")                      # theirs: caution
    outline(by(s, "Rectangle 16"), "0F6B5F")                     # ours: evidence
    move(by(s, "Rectangle 16"), w=4.63)                          # out to the content edge
    set_text(by(s, "TextBox 11"),
             [[("price · volume · earnings — is this stock going up?", S["sm14g"])]])
    set_text(by(s, "TextBox 13"), [[("we ask", S["m13a"])]])
    set_text(by(s, "TextBox 14"), [[("instead", S["sm14a"])]])
    set_text(by(s, "TextBox 15"), [[("WHAT WE TRACK", S["lab_t12"])]])
    set_text(by(s, "Rectangle 16"),
             [[("momentum", S["b17"])], [("credibility", S["b17"])], [("your risk", S["b17"])]])
    set_text(by(s, "TextBox 17"), [[("ASEAN issuers · green bonds", S["sm14a"])]])
    move(by(s, "TextBox 17"), w=4.40)
    set_text(by(s, "TextBox 18"),
             [[("A perfect score that has been sliding for three months shows up here as a "
                "warning.", S["cap15"])]])
    set_text(by(s, "TextBox 19"),
             [[("→ 75% OF EM SUSTAINABLE BONDS CARRY NO INTERNATIONAL RATING — NOBODY COVERS IT",
                S["lab_a11"])]])
    foot(s, "06 / 09")
    set_notes(s, "GRACE — You might be thinking: don't other platforms already do this? They don't. "
                 "Those platforms track financial performance — price movement, volume, earnings. "
                 "They answer 'is this stock going up?' We answer a different question: 'is this "
                 "company becoming riskier — and more importantly, does anyone else see it yet?' "
                 "[BEAT] Three things separate us. First, we measure ESG momentum, not just the "
                 "rating: a company with a perfect score that's been declining for three months "
                 "shows up as a warning. Second, we focus on ASEAN-listed issuers and green bonds — "
                 "a market where seventy-five percent of sustainable bonds carry no international "
                 "rating at all. Nobody's covering that gap. Third, you set your own risk appetite, "
                 "and the radar adjusts to it.")

    # ═══ 7 · CALL TO ACTION — Jayden (was v3 slide 9: three rows + the timeline) ═════════════
    s = s_cta
    head(s, "(E)  THE ASK", "Who it's for, and what we need.", "OPEN", "chip10t")
    set_text(by(s, "TextBox 7"), [[("WHO", S["lab_t11"])]])
    set_text(by(s, "TextBox 8"),
             [[("Any investor — beginning or seasoned — who wants to see ESG risk before the "
                "headline, not after", S["s16"])]])
    set_text(by(s, "TextBox 10"), [[("WHERE", S["lab_t11"])]])
    set_text(by(s, "TextBox 11"),
             [[("ASEAN — where the data gap is widest and demand for sustainable finance tools is "
                "growing fastest", S["s16"])]])
    set_text(by(s, "TextBox 13"), [[("THE ASK", S["lab_a11"])]])
    set_text(by(s, "TextBox 14"),
             [[("A design partner: six weeks piloting the radar inside a real portfolio workflow",
                S["s16"])]])
    set_text(by(s, "TextBox 18"), [[("NOW", S["m15t"])]])
    set_text(by(s, "TextBox 19"), [[(UNIVERSE + " companies scored, live", S["s12g"])]])
    set_text(by(s, "TextBox 21"), [[("PILOT", S["m15a"])]])
    set_text(by(s, "TextBox 22"), [[("six weeks, one partner", S["s12g"])]])
    set_text(by(s, "TextBox 24"), [[("SCALE", S["m15a"])]])
    set_text(by(s, "TextBox 25"), [[("S$159/yr at 2,000 names", S["s12g"])]])
    set_text(by(s, "TextBox 26"),
             [[("If you're in green finance and tired of reading the rating after the scandal — we "
                "built this for you.", S["cap13"])]])
    foot(s, "07 / 09")
    set_notes(s, "JAYDEN — So who is this for? Any investor, whether you're just beginning or have "
                 "been in the market for some time, who wants to see ESG risk before the headline, "
                 "not after. We're starting with ASEAN, where the data gap is widest and demand for "
                 "sustainable finance tools is growing fastest. [BEAT] Right now we've scored "
                 "fifty-two companies using CGSI's own data. The prototype you just saw is live. "
                 "What we need next is a design partner — investors willing to pilot the radar for "
                 "six weeks so we can validate it in a real portfolio workflow. If you're in green "
                 "finance and you're tired of reading the rating after the scandal, we built this "
                 "for you.")

    # ═══ 8 · CLOSE + Q&A — Jayden (a second cover, so the deck ends where it opened) ═════════
    s_close = dup_slide(prs, cover)
    s = s_close
    set_text(by(s, "TextBox 1"), [[("Thank you.", S["title"])]])
    set_text(by(s, "TextBox 2"),
             [[("ESG was built to grade companies. We built something to read the change.",
                S["sub22"])]])
    move(by(s, "TextBox 2"), w=11.63)
    set_text(by(s, "TextBox 5"), [[("TEAM", S["lab13"])]])
    set_text(by(s, "TextBox 6"), [[("Quill & Candle", S["val15"])]])
    set_text(by(s, "TextBox 7"), [[("MEMBERS", S["lab13"])]])
    set_text(by(s, "TextBox 8"), [[(MEMBERS, S["val13"])]])
    move(by(s, "TextBox 8"), w=8.60)
    set_text(by(s, "TextBox 9"), [[("RUN", S["lab13"])]])
    set_text(by(s, "TextBox 10"),
             [[(RUN_ID + "  ·  " + EVENTS + " dated events  ·  " + UNIVERSE + " companies",
                S["val13"])]])
    set_text(by(s, "TextBox 11"), [[("NEXT", S["lab13"])]])
    set_text(by(s, "TextBox 12"), [[("Questions", S["val15"])]])
    set_text(by(s, "TextBox 13"),
             [[("CGSI PolyFinTech100 API Hackathon 2026 — Track: ESG & Sustainable Finance",
                S["sch13"])]])
    set_notes(s, "JAYDEN — ESG was built to grade companies. We built something to read the change "
                 "before the market does. [BEAT] Thank you — we're Quill and Candle, and we'd love "
                 "to take your questions. (Appendix A1 is the cost, A2 is what we still face.)")

    # ═══ 9 · REFERENCES (v3 slide 10, unchanged but for the footer) ══════════════════════════
    foot(s_refs, "09 / 09")
    set_notes(s_refs, "The sources behind every number in this deck. Where a figure came from a "
                      "sponsor-provided brief or from our own methodology, it is labelled as such.")

    # ═══ APPENDIX — kept from v3, because these are the two questions a judge asks ═══════════
    set_text(by(s_cost, "TextBox 1"), [[("APPENDIX  ·  THE HONEST NUMBER", S["seclab"])]])
    foot(s_cost, "APPENDIX A1")
    set_text(by(s_face, "TextBox 1"), [[("APPENDIX  ·  WHAT WE FACE", S["seclab"])]])
    # v3 left this fix line centred in a box that had been widened under it -- it reads as an
    # indent bug on screen, so it is pulled back to the column edge with its siblings.
    for para in by(s_face, "TextBox 26").text_frame.paragraphs:
        para.alignment = PP_ALIGN.LEFT
    foot(s_face, "APPENDIX A2")

    reorder(prs, [s_hook, cover, s_problem, s_solve, s_demo, s_diff, s_cta, s_close,
                  s_refs, s_cost, s_face])

    prs.core_properties.title = "ESG Momentum Radar — PolyFinTech100 2026"
    prs.core_properties.author = "Team Quill & Candle"
    prs.save(out)
    return out


def to_pdf(path):
    out_dir = os.path.dirname(path)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.splitext(path)[0] + ".pdf"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--template", default=TEMPLATE)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--pdf", action="store_true", help="also render a PDF via LibreOffice")
    args = ap.parse_args(argv)
    path = build(args.template, args.out)
    print("wrote", path)
    if args.pdf:
        print("wrote", to_pdf(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
