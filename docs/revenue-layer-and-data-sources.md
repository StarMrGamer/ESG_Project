# Adding a financial variable, S&P, and the "awaiting data" screen

**To:** Jayden
**From:** Vrishabd
**Date:** 2026-08-24
**Status:** two of three asks are actionable now; one needs a decision from you before anyone builds it.

---

## TL;DR

| your ask | verdict |
|---|---|
| Another variable — will the company make more money | **Yes, as a FILTER. No, as a score component.** Half of it already exists. |
| Fetch S&P (or build our own) | **No — licence breach, and it makes us a rating agency.** Free alternatives below. |
| Fix the "awaiting data" everywhere | **Yes — mostly a wiring gap, not a data gap.** ~2 hours. |

---

## 1. The "awaiting data" screen — diagnosed

There are **four separate causes** in that screenshot, and three are fixable with data we already hold.

### (a) The pillar cards are discarding numbers the engine already computed

The E / S / G / Digital cards read a `momentum` field that only the **fictional demo set** carries. But the
engine has already computed per-pillar momentum for the real 52, and it is sitting in
`records[*].components` right now:

```
E        44 of 52 companies        G        38 of 52
DIGITAL   3 of 52                  S         3 of 52
```

Computed, stored, and the card beside it says "awaiting data". **This is a wiring gap.** Fixing it
fabricates nothing — the numbers are rule-derived from dated evidence.

Note S and Digital stay thin (3 of 52). That is honest and still better than a blank: "3 of 52 have social
evidence" is a finding about our sourcing, which is exactly the alt-data gap we already name.

### (b) You were on the Short 45d horizon

PTT Global Chemical has **3 real signals**. On a 45-day half-life all three decay to zero weight:

| horizon | momentum | label |
|---|---|---|
| Long 180d | +0.054 | `future_leaders` |
| **Short 45d** | **0.000** | `consensus` |

Same company, same evidence, different question. Short asks "what has changed *recently*" — and PTTGC's
evidence is too old to answer it. That is the decay model working. The screen's failure is that it does not
*say* so; it just goes blank, which reads as broken.

### (c) "PTT Global Chemical · 0 signals" is a mislabel

That counter reads `live_signals` — a demo-only field — while the engine holds **3 scored signals** for
that company. Straightforward fix.

### (d) Price and news are not wired

`quotes.py` works and fetches live prices. It is simply not connected to the focused-company card.

### What stays blank on purpose

- **Only 3 of 52 companies genuinely have no evidence**: `KLSE:AMM`, `SET:INTUCH`, `SGX:WIL`. They are drawn
  hollow on the matrix with the count stated. An absence of evidence is a finding, not a hole to fill.
- **Forecast outlook** is labelled ILLUSTRATIVE and stays demo-only. We do not project numbers for real,
  named, listed companies.

---

## 2. The financial / revenue variable

The ask is reasonable. There are two ways to build it and they end in very different places.

### The version that kills the project

Blend revenue growth or profitability **into the momentum score**.

The moment we do that, our output is a composite number ranking companies by expected profit. That is a
**stock score**. It breaks HARD RULE 4 ("never give buy/sell/hold or a score"), and it deletes the pitch —
"we disagree with ratings, we don't pick" stops being true, and we become a worse MSCI with 52 names.

It also breaks the thing that makes the argument legible. Right now `disagreement` means one specific
thing: *our evidence-based momentum percentile minus the incumbent's rating percentile.* Add a revenue term
and nobody — including us — can say what a disagreement of +0.6 is claiming any more.

### The version that works, and is already half-built

Financial data as a **gate**, evaluated *after* the ESG scoring, never inside it.

We already have all of this:

| what | where |
|---|---|
| Four-test traction screen — revenue growth >=10% compound, operating cash flow, order book, signed PPAs / green capex | `traction.py` |
| `profitability_flag`, `fy_minus1_net_income`, `fy_minus2_net_income`, `operating_cf_trend` | `data/company_metadata.csv` |
| **The M bucket already requires passing the financial screen** | `pipeline_counts.py` |

So the bridge you are describing partly exists: M is *"below its sector-peer ESG average AND positive
evidenced momentum AND passes the financial screen."* That is already an ESG signal gated by financial
viability.

**What's missing is that it isn't a control you can see or touch.** The build is: a "financially viable"
toggle on the matrix that dims names failing the screen — the same treatment `greenFocus` gets. Roughly a
day. It answers "show me the disagreements that can also pay for themselves" without putting a revenue
number anywhere near the score.

One discipline to keep: **`unknown` is not `not_met`.** The basket holds net income and nothing else, so
tests 1 and 2 are unanswered for both loss-makers and they return `screen_not_run` — neither cleared nor
disqualified. Scoring an unrun test as a failure disqualifies a company for *our* missing data rather than
its own numbers.

### Decision needed from you

Is this a **filter** (recommended) or a **score component** (not recommended)? Everything downstream
depends on the answer, and it is much cheaper to settle now than to unpick later.

---

## 3. S&P / MSCI / Sustainalytics

### Fetching them: not possible, and not a technical problem

All three are **licensed products**. Their scores cannot be fetched, displayed or redistributed without a
contract. This is the same reason LSEG got picked in the first place: **it is the only major rater with a
free, keyless, per-company endpoint**, and even that we use attributed, on-demand, one company at a time,
cached locally, with no scrape ever written to `data/`.

There is no engineering route around a licence. Publishing S&P scores we did not license would be a real
legal exposure at a public demo.

### Building our own: that is a rating agency

"Make our own S&P" means producing a proprietary company score — HARD RULE 4 again, and this time for both
an ESG score and a financial one. It also throws away the strongest structural claim we have: *the AI never
touches a score, and the scorer never writes a sentence.*

### What we already hold from the other houses

We are not blind to them. `metrics.parse_evidence` reads MSCI, Sustainalytics, S&P Global / DJSI, CDP,
FTSE4Good and GRESB wherever a company's own `esg_basis` cites them. And the basket carries a notch grade
(`incumbent_notch` — BBB / BB / B, the MSCI scale) which is now **on the engine record and shown in the
evidence panel**. It travels unattributed, because CGSI's own column header reads "ESG Rating" and names no
agency, and it is display-only — letting a second incumbent measure into the maths would be two rulers in
one number.

### Free financial sources that are actually available

- Two fiscal years of net income and an operating cash-flow trend — **already in our CSV**
- Live prices — `quotes.py`, already working
- Exchange filings and regulator actions — reachable through `harvest.py`

That is enough for a viability gate. It is not enough for a rating, and it should not pretend to be.

---

## 4. One thing worth knowing before we chase more data

After the live harvest, **79% of our signals are company press releases** (142 of 180). `source_quality`
caps company-published material at 0.5 by rule — the Adaro lesson — so gathering more of it raises signal
counts and cannot raise confidence. That is why Hidden Winners is still zero.

The route to a real Hidden Winner is **better sources, not more of them**: regulator actions, exchange
filings, index-provider decisions. Adding a revenue variable does not touch this constraint, so it will
not populate that quadrant either. Worth being clear about, so nobody expects it to.

---

## 5. Proposed next steps

**Do now (~2 hours, no decision needed):**

1. Wire the pillar cards to the engine's component momenta
2. Fix the "0 signals" mislabel
3. Say "evidence too old for this window" when a short-horizon company decays to zero, instead of going blank
4. Wire the price strip to `quotes.py`

**Do after you decide (~1 day):**

5. Financial-viability filter on the matrix — pending your filter-vs-score call above

**Not doing:**

6. Fetching or reproducing S&P / MSCI / Sustainalytics
