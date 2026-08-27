# Financial backing — I checked whether we should add price or Yahoo data

**To:** Jayden
**From:** Sean
**Date:** 27 August 2026
**Read time:** ~5 minutes. §1 is the one that changes what we say to a CIO.

---

## Why I looked at this

I raised a worry this morning that we are missing a bit of financial backing — that the pitch is
all ESG evidence and a CIO is going to ask *"but does the money side hold up?"*. My instinct was
that we should pull share price, or financial data off Yahoo Finance, and put it behind the
judgement.

I went and checked it properly. Three findings, and the first one surprised me:

| | Verdict |
|---|---|
| **Share price as validation of the ESG call** | ❌ **No.** CGSI's own note says it would contradict us ~7 times in 10 even when we are right |
| **Fundamentals as a financial gate** | ✅ **We already have it** — two audited fiscal years for all 52, with a source on every row |
| **My worry that backing is missing** | ⚠️ **Half right — it is a display problem, not a data problem** |

---

## 1 · Price would weaken the case, and the evidence is our own source document

This is not a judgement call. It is in CGSI's published note — the same 43-page document our 52
names come from (`data/cgsi_note_figures.json`). They tested whether an ESG improver beats the
index:

| Horizon | Probability an ESG improver beats the index |
|---|---|
| **1 year** | **28.9%** |
| 3 years | 46.2% |
| 5 years | 61.5% |

CGSI state it outright: *"ESG improvements alone do not guarantee stronger share price performance
at the single-stock level."*

**Read what that does to us.** At the horizon a CIO review or a demo actually looks at, an ESG
improver beats the index fewer than three times in ten. So if we put price beside our ESG call as
evidence the call was good, our own foundation document predicts price will disagree with us
about **71% of the time even when the thesis is sound.** We would be handing the CIO a stick to
beat us with, and we would have sourced it ourselves.

> ### TAKE NOTE
> If a judge or a CIO asks *"does the share price back this up?"*, the winning answer is not a
> chart. It is: **"CGSI tested that — 28.9% at one year — which is exactly why we do not score on
> price. We score on evidence and gate on fundamentals."** That answer makes us look like we read
> the research. A chart makes us look like we did not.

There is also a hard product constraint I had not fully weighed. **HARD RULE 4: we never give
buy/sell/hold or a score.** The moment price becomes validation we are implicitly making a
performance claim, and the product stops being *"we disagree with this rating"* and becomes a
stock picker with extra steps — a worse MSCI, which is the one thing this project exists not to
be.

---

## 2 · The financial backing already exists, and it is fundamentals rather than sentiment

`financials.py` reads **two audited fiscal years of net income for all 52 companies** out of
`data/company_metadata.csv`, each row carrying its own source. Run it today and you get:

```
17 strong   ·   22 adequate   ·   11 weak   ·   2 unknown
```

Two things in there are worth saying out loud to a CIO, because both are the kind of thing that
gets noticed when it is missing:

- **`unknown` is not `weak`.** Two companies genuinely cannot be read from the data we hold, and
  they are reported as unknown rather than marked down for *our* missing information. Same
  discipline in `traction.py`, the four-test screen for the two loss-makers: a test we could not
  run returns `screen_not_run`, never a fail.
- **Eleven of fifty-two are weak, and we say so.** Not a flattering number. It is a credible one,
  and a CIO will trust the 17 "strong" precisely because the 11 "weak" were not quietly dropped.

This is stronger backing than a price chart: audited company reporting, dated and sourced, rather
than market sentiment.

---

## 3 · What Yahoo can and cannot give us

Worth knowing before anyone spends an afternoon on it.

| | Status |
|---|---|
| **Fundamentals** (revenue, cash flow, balance sheet) | ❌ Gone. Yahoo's `quoteSummary` needs a crumb now. MSCI / S&P / Sustainalytics are licensed products we cannot fetch, show or redistribute |
| **Live share price** | ✅ Works. Checked today — all five ASEAN exchanges responding (IDX, KLSE, PSE, SET, SGX) |

So the fundamentals question is half settled by availability anyway: the free keyless financial
endpoints do not exist any more, which is why the net income sits in our own verified CSV where
we can point at it.

The live price **is already on screen**, in `quotes.py`, labelled on its face: *"Last price for
context only — not a signal, and no part of the ESG score."* That is the right place for it.
Context, never evidence.

One caveat if anyone touches that file: ~20 of 52 resolve, and the Bursa misses need a numeric
stock code. They must **not** be closed with a name search — a price for the wrong company is
worse than no price.

---

## 4 · Where I was actually right, and where I was wrong

I was wrong about *what* was missing and right that *something* was.

The financial gate renders in **`CasePanel`, inside the deep dive** — pros and cons on both axes,
the verdict, what would change it. It is good. But there is **nothing financial anywhere on the
board.** No dashboard component reads it.

So anyone watching the pitch sees ESG at every level and finance only if they open one specific
company and scroll past the fold. Built, tested, documented — and absent at exactly the altitude
where we pitch a CIO. That is what I was reacting to this morning. **I read it as missing data
when it is missing on the screen.**

The fix is one panel: put the `17 / 22 / 11 / 2` on the board as a **gate beside the score**. It
is a small, safe change — read-only, and `selftest.py` already pins that `engine.py` and
`signals.py` import neither `financials.py` nor `rationale.py`, so the separation cannot rot by
accident.

**I think we should do it. Your call, since it changes the board.**

---

## 5 · The bridge already has a name, and it is the M bucket

The thing a CIO actually wants — *where do ESG and financial meet in one output?* — exists
already. It is **M**, the origination pipeline: companies **below their sector benchmark, with
positive evidence momentum, that pass the profitability / traction screen.** ESG on one side,
financials on the other, one actionable list out of the middle. That is the commercial story, and
it is already on the board behind the *Origination pipeline* toggle.

> ### TAKE NOTE — check your slides for M = 11
> The note Rai sent you on 24 August puts the M bucket at **11** companies. **That figure is
> stale.** It was correct when written, and then the deep + quality evidence sweep re-froze the
> run the next day. The current frozen counts, read from `data/nmk_frozen.json` rather than from
> anyone's prose:
>
> ```
> N = 13 issuers (priced in)  ·  M = 10 pipeline (bond-ready)  ·  K = 1 review list
> run 1fc384a2fa92499d · as of 2026-08-20 · frozen 2026-08-25
> ```
>
> Worth grepping the deck before we present. Any figure we put on a slide should carry the
> `run_id` it came from — that is the only thing that makes staleness visible, and it is how this
> one got caught.

---

## 6 · Why keeping them separate is worth defending

I said "although supposed to be separate" when I raised this, half as a caveat. Having looked at
it, I want to put the actual reason on paper, because it is the answer if a judge pushes.

`disagreement` currently means one specific, defensible thing: **our evidence-based momentum
percentile, minus the incumbent rating's percentile.** Fold an earnings term into it and nobody —
including us — can say what a disagreement of +0.6 is claiming any more. The output stops being a
disagreement with a rating and becomes a composite pick.

So the financial read is a **context gate**: computed after the scoring, reported beside it, never
inside it. Side by side, an analyst can see both and decide. Merged into one number, they can see
neither.

It is the same error `benchmarks.py` refuses to make when it declines to difference a company ESG
score against an industry GHG intensity — two different measures subtracted. Same mistake,
arriving through a different door.

---

## What I need from you

1. **Agree that price stays context, not validation?** I think §1 settles it, but you should see
   the 28.9% before we're asked about it on stage.
2. **Do we surface `17 / 22 / 11 / 2` on the board?** I think yes. It is a positioning call — how
   prominent finance should be in an ESG product — more than a code one.
3. **Grep the deck for M = 11** and replace with 10, per §5.

---

## Sources

All of it re-derivable, no network needed:

| Claim | Where |
|---|---|
| 28.9% / 46.2% / 61.5% | `data/cgsi_note_figures.json` → `performance.single_stock_caveat` |
| 55.1% vs 6.4% cumulative, and the −4.6% YTD lag | same file → `performance` |
| 17 / 22 / 11 / 2 | `python financials.py` |
| Traction screen, loss-makers | `python traction.py` |
| N / M / K with its run id | `data/nmk_frozen.json` |
| Live price coverage | `python quotes.py` |
| Why fundamentals are not fetchable | module docstring, `financials.py` |

Figures pulled against the repo with Rai.
