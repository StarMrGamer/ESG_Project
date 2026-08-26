# Whitepaper — NYP Category Finals submission

**Deadline:** 27 August 2026 (Thursday), 12:00 noon
**Email to:** eunice_ho@nyp.edu.sg ; leow_seng_heang@nyp.edu.sg
**Subject:** `Whitepaper submission by CategoryName_TeamName`
**Attachment filename:** `CategoryName_TeamName.pdf` (e.g. `ESG_ABC.pdf`)

Source is `whitepaper.html`; the PDF is rendered from it. Two A4 pages exactly, no cover page,
team + category on the top of both pages — all four stated requirements.

**Two versions exist. The one that renders is the plain-language one.**

| File | Written for | Use it when |
|---|---|---|
| `whitepaper.html` | **A general reader** — a sponsor, a judge, an investor with no engineering background. No jargon: "how quickly old news stops counting", not "decay horizon". | **This is the submission.** |
| `whitepaper_technical.html` | Someone who wants the mechanism — percentiles, determinism, the guard rules, the Merkle-style receipt. | Only if a sponsor asks for depth. Render it to a different filename; do not submit it. |

Both carry the same numbers and the same limits. The plain version explains them; the technical
one names them.

---

## Before you send — two edits, then re-render

**1 · Fill in the two placeholders.** They appear twice each (top of page 1 and page 2):

```bash
sed -i 's/\[TEAM NAME\]/YourTeam/g; s/\[CATEGORY NAME\]/YourCategory/g' whitepaper.html
```

**2 · Re-render and rename to match the convention:**

```bash
chromium --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=YourCategory_YourTeam.pdf whitepaper.html
```

**3 · Check it is still exactly 2 pages** (the requirement is a maximum of two):

```bash
pdftoppm -png -r 80 YourCategory_YourTeam.pdf /tmp/wp && ls /tmp/wp-*.png
```

If a third page appears, you added text — cut, do not shrink the type below 8pt.

---

## What is on each page

| Page | Sections |
|:--:|---|
| 1 | The problem · what we built, in six plain steps · **nothing we ask you is decoration** · what "disagreeing with the rating" actually means |
| 2 | Does the company also make money? · what to look out for before investing · can you trust the evidence? · what it costs to run and grow · what we are honest about |

## Rules this document keeps — do not edit them out

- No buy / sell / hold, no published score, no ranking anywhere in it.
- The −4.6% YTD appears in the same sentence as the 55.1%.
- No licensed rater (MSCI / Sustainalytics / S&P) is quoted or scored.
- The chain is described as the **ledger** layer, never as verification.
- The four Hidden Winners are stated **with the fact that the threshold never moved** — the
  rule for changing it was published before the evidence existed. Never present them as a
  discovery that required a smaller number.

**Consistency requirement from the organisers:** the whitepaper is shared with the sponsor and
must match the Category Finals presentation. If a number changes in the deck, change it here too.

Every figure in this document traces to a file in the repo — the frozen N/M/K counts, the
financial-gate verdicts, the measured token costs, the CGSI note figures. Nothing is estimated.

---

## Changed 2026-08-25 — after the deep + quality sweep

Four figures moved. All four are re-derivable; none was rounded.

| Was | Now | Where it comes from |
|---|---|---|
| "Four separate searches per company" | **up to 27**, four angles x site-scoped x past years | `harvest.py` |
| 180 pieces of evidence | **391**, across 48 of 52 companies | `data/harvest/` |
| shortlist of 11 | **10** | `data/nmk_frozen.json`, M |
| nothing clears the hidden-winner bar | **four do, on unmoved thresholds** | run `1fc384a2fa92499d` |

The shortlist gloss also changed from "better than their rating suggests" to "scoring below their
own industry's ASEAN peer average" — the first was a loose paraphrase, and M is measured against the
sector-peer average, not against the rating.

**Matching deck:** `docs/pitch/pitch_slide.html` carries the same four numbers and the same run id.
Change one, change both.
