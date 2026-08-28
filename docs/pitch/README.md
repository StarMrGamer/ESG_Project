# The pitch folder

Three artefacts, one set of numbers. Every figure in all three comes from run `1fc384a2fa92499d`
— the run `data/nmk_frozen.json` is frozen on. **If a number changes in one, change it in all
three and in `docs/whitepaper/whitepaper.html`**, which the organisers require to match.

| File | What it is | When you use it |
|---|---|---|
| `ASEAN_ESG_Momentum_Radar.pptx` | **The 9-slide deck** — editable PowerPoint, speaker notes on every slide | The Category Finals presentation |
| `slides.md` | The **script** behind the deck: what you say, when, what to say if pushed, and the source of every figure | Rehearsal, and the sheet you hold |
| `pitch_slide.html` → `.pdf` | The **1-minute** single slide | When you get 60 seconds, not 6 minutes |

---

## The 9-slide deck

```bash
python -m scripts.build_pitch_pptx          # -> docs/pitch/ASEAN_ESG_Momentum_Radar.pptx
python -m scripts.build_pitch_pptx --pdf    # also renders the PDF via LibreOffice
```

**It is generated, not hand-built, and that is the point.** A deck someone edits by hand drifts
from the run the moment a figure moves. This one re-renders in two seconds: change the figure in
`scripts/build_pitch_pptx.py`, re-run, and the deck, its notes and the PDF are all current
together. The output is ordinary editable PowerPoint — every headline, number and caption is a
real text box, so anyone can still nudge it on the day.

**The nine sections** are the ones in `slides.md`, in order: Hook · Problem · What It Is ·
Prototype (live) · Why the Number Holds · What Separates Us · Investment · Down to Earth · Close.
Slide 4 is the live-demo run order — six clicks, ninety seconds — so the deck stays on screen
while you drive the app beside it.

**Speaker notes carry the script.** The `YOU SAY` and `IF PUSHED` blocks from `slides.md` are in
the notes pane of each slide, so presenter view is the only thing you need open.

**Typography — IBM Plex, and it must be installed.** Headlines are Plex Sans Condensed, text is
Plex Sans, every figure is Plex Mono — the same system as `pitch_slide.html` and the whitepaper.
Line breaks in the headlines are EXPLICIT and measured against the real font file at build time
(an overflow raises rather than silently landing on the block below). **If Plex is missing on the
presenting machine PowerPoint substitutes a different face and those breaks move** — install IBM
Plex (free, OFL) or present `ASEAN_ESG_Momentum_Radar.pdf`, which embeds the fonts.

**Colour means three things and is never decoration:** green is our evidence read, blue is the
published rating, red is a caution and always has a word beside it. There are no boxes, shadows,
icons or gradients anywhere in the deck — rules and white space do the structural work.

**Optional dependency.** `python-pptx` (and `Pillow`, for the headline measurement) are commented
out in `requirements.txt`, like `openpyxl`. Nothing in the app, the engine or the tests imports
them.

---

## 1-minute pitch slide

**Source:** `pitch_slide.html` — one slide, 16:9, renders to a 13.333in × 7.5in PDF, which is
exactly the standard PowerPoint widescreen page. Drop the PDF straight into a deck or present the
HTML full-screen.

Every figure on it comes from run `1fc384a2fa92499d` — the same run the board and
`data/nmk_frozen.json` are on. Nothing is rounded up and nothing is estimated.

---

## Before you present — two edits, then render

**1 · Fill in the two placeholders.** They are the *same* placeholders the whitepaper uses, so one
command does both files:

```bash
sed -i 's/\[TEAM NAME\]/YourTeam/g; s/\[CATEGORY NAME\]/YourCategory/g' \
  docs/pitch/pitch_slide.html docs/whitepaper/whitepaper.html
```

**2 · Render:**

```bash
chromium --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=docs/pitch/pitch_slide.pdf docs/pitch/pitch_slide.html
```

Check it came out as one page at 960 × 540 pts:

```bash
pdfinfo docs/pitch/pitch_slide.pdf | grep -E 'Pages|Page size'
```

The fonts (IBM Plex Sans / Condensed / Mono) are read from the system, not fetched — it renders
identically offline.

---

## The 60 seconds

163 words. At a normal pitch pace (~160 wpm) that lands on 61 seconds. **If you are running long,
cut the last sentence** — everything before it is load-bearing.

| Beat | Say |
|:--:|---|
| **0:00** *the problem* | "Every ESG rating tells you a **level** — where a company stood, in a report filed a year ago. Not which way it's moving. Not what would change it." |
| **0:09** *the move* | "So we rank all 52 ASEAN companies **twice**. Once on dated public evidence. Once on the rating the market already uses. Then we report the gap." |
| **0:21** *the proof* | "RHB Bank. Its rating puts it in the bottom fifth. Fourteen dated sources say it's the fastest-improving name in the basket. A gap of **plus 0.80** — and we'll show you every source, and which one, if it vanished, would change our answer." |
| **0:36** *the discipline* | "Four companies clear that bar. UOB clears it on ESG and **fails** our money read. We show both. We never blend them — one combined score would hide exactly that." |
| **0:48** *the close* | "We fixed that bar **before** we had the evidence, and never moved it. Eight cents per company per year. And it never says buy or sell — it says where it disagrees, and what would change its mind." |

**Where to point.** One gesture per beat, no more: at 0:21 the plot; at 0:36 the `weak` in the last
column; at 0:48 the `0` in the KPI band. The slide is a backdrop — do not read it aloud.

---

## Three things that must not slip out of your mouth

1. **Never "buy", "sell", "hold", or "our score".** The moment you say one, a judge who knows the
   rules stops listening. The line to reach for instead: *"it moves when the evidence moves, and we
   can show you which piece is holding it up."*
2. **Never 55.1% without −4.6% in the same breath.** CGSI's own note has the basket lagging the
   index by 4.6% YTD. Neither number is on this slide — keep it that way at one minute. If a judge
   raises the backtest, give them both.
3. **Never 29.4% without CGSI's three filters.** Only one of the three is an ESG signal, so 29.4% is
   agreement on one criterion out of three — *not* a 70% disagreement about ESG.

---

## The four questions you will get, and the one-line answer

| They ask | You say |
|---|---|
| *"So it's a stock picker?"* | "No — it never ranks or recommends. It reports a disagreement with a named rating, and shows you the dated evidence under it." |
| *"Why should I trust your evidence?"* | "No date and no working source means the fact is dropped. We decide the source type, not the publisher — a company's own announcement is capped so it can never count like a regulator's filing." |
| *"What's the blockchain for?"* | "It's the receipt, not the check. It proves the verdict you saw in 2026 was built on exactly the evidence we said — it cannot make a false claim true, and anyone who tells you otherwise is selling something." |
| *"Only four hidden winners?"* | "86% of what a public search returns is written by the companies themselves, and we cap that. Four is what survives the cap. The fix is better sources, not a smaller number." |

---

## ✓ The whitepaper matches this slide

The organisers require the whitepaper and the presentation to carry the same numbers. Since
`whitepaper.html` was first written, the full deep + quality sweep landed and **four figures
moved**. All four were reconciled on 2026-08-25 and `CategoryName_TeamName.pdf` was re-rendered:

| Was | Now | Where the current number comes from |
|---|---|---|
| "four separate searches per company" | **up to 27**, along four angles | `harvest.py` |
| "180 dated, sourced pieces of evidence" | **391** events, 48 of 52 companies | `data/harvest/` |
| "a shortlist of 11 companies" | **10** (M) | `data/nmk_frozen.json` |
| "Nothing currently clears our top hidden-winner bar" | **4 clear it** — thresholds unchanged | run `1fc384a2fa92499d` |

The last one is the strongest paragraph in the document, not a patch. The bar was pre-registered
before the evidence existed, never moved, and the quadrant filled because better sources arrived.
**Say that.**

**Still to do before 27 Aug noon:** fill the two placeholders (command at the top of this file) and
re-render both PDFs.

---

## The public landing page

`docs/landing/index.html` — same run, same four numbers, published at
https://claude.ai/code/artifact/d313c17c-b15a-4e09-8038-8f7abc9a5f91. If any figure here changes,
it changes there too.
