# ASEAN ESG Momentum Radar — 9-slide judge deck

**Team:** Quill & Candle · **Category:** ESG · **Run:** `1fc384a2fa92499d` (every number below comes
from this one run — the same run in `data/nmk_frozen.json`, the whitepaper and `pitch_slide.html`)

**Format of this file.** One section per slide. Each has **ON SCREEN** (what the judge reads — keep
it to what is listed, nothing more), **YOU SAY** (spoken, timed), and **IF PUSHED** (the answer to
the question that slide invites). Don't read the slide out loud — it's a backdrop, not a script.

| # | Slide | Time | The one thing it has to land |
|:--:|---|:--:|---|
| 1 | Hook | 0:00–0:25 | One company, two ranks, a gap of +0.80 |
| 2 | Problem | 0:25–1:00 | A rating is a **level**; nobody sells you the **direction** |
| 3 | What It Is | 1:00–1:35 | We rank all 52 twice and report the gap. We never pick |
| 4 | Prototype (live) | 1:35–3:05 | It's real, it's clickable, and it runs the same every time |
| 5 | Why the Number Holds | 3:05–3:50 | The bar was written down **before** the evidence existed |
| 6 | What Separates Us | 3:50–4:25 | The AI reads, the rules score — and we're on the investor's side |
| 7 | Investment | 4:25–5:05 | S$0.079 per company per year — measured, not estimated |
| 8 | Down to Earth | 5:05–5:35 | The limits are on the slide before anyone asks |
| 9 | Close | 5:35–6:00 | It says where it disagrees, and what would change its mind |

**Three things that must never leave your mouth** — repeated here because one of them ends the pitch:

1. **No "buy", "sell", "hold", or "our score".** Say instead: *"it moves when the evidence moves, and
   we can show you which piece is holding it up."*
2. **Never 55.1% without −4.6% in the same breath** (slide 2 puts them together for you).
3. **Never 29.4% without CGSI's three filters** — only one of the three is an ESG signal.

---

## 1 · Hook

> **RHB Bank. Its rating says 18th of 52. The evidence says 98th.**

**ON SCREEN**

- One rail, two marks: `ITS RATING SAYS — 18th, grade BB, bottom fifth` → `THE EVIDENCE SAYS — 98th,
  14 dated sources, 2023–2026`
- The gap, big: **+0.80**
- Footline: *same company · same day · two different answers*

**YOU SAY** *(~25s)*

> “One company, one day, two answers. Its ESG grade puts it in the bottom fifth of this basket. Fourteen dated sources — filings, exchange notices, news — say it's the fastest improver in the same basket. Neither of those is made up. Only one of them is current. So we built the thing that tells you which, and shows you the sources.”

**IF PUSHED — *“is the rating just wrong?”*** → “Not wrong, just late. It's a level, and the file closed months ago. We're not replacing it — we're putting a second opinion next to it with a date on every claim.”

---

## 2 · Problem

> **A rating tells you where a company stood. Not which way it is moving, and not what would change
> the answer.**

**ON SCREEN**

- **A level, published late** — a score in a file closed months ago, refreshed on the rater's cycle
- **No direction** — nothing in it says improving or deteriorating *now*
- **Not challengeable** — you cannot ask a rating which piece of evidence is holding it up
- The basket this comes from: **+55.1% vs +6.4%** for MSCI AC ASEAN (Jan 2021 – Aug 2025) — **and
  −4.6% year-to-date in 2025**, on a ~45% banking weight *(CGSI's own note, both numbers)*
- **28.9%** — probability an ESG improver beats the index at one year *(same note)*

**YOU SAY** *(~35s)*

> “ESG momentum works — this basket beat the index by nearly fifty points over four years. Here's the other half, from the same research note: it's down 4.6% against the index this year, and a single ESG improver only beats the index about three times in ten at one year. So the question isn't whether ESG pays. It's that a rating gives you a level, and a level can't tell you which way anything is moving. That's the gap we went after.”

**IF PUSHED — *“why put your own bad number up?”*** → “Because it's in our own source document. Anyone who opens that note finds it in ten seconds, and then nothing else we said counts. Cheaper to say it first.”

**Rule:** the −4.6% goes in the same breath as the 55.1%, every time.

---

## 3 · What It Is

> **We rank all 52 ASEAN companies twice — once on the rating the market already uses, once on dated
> public evidence — and report the gap, with a direction.**

**ON SCREEN**

- **Thinks** — it asks first: four short questions that set the filters, the risk tier and how
  fast old news stops counting. Every answer changes what's on screen.
- **Challenges** — it pushes back on a loose framing instead of answering it.
- **Competes** — it takes a position against the rating, on evidence the rating cannot see. ← *the
  differentiator*
- The four quadrants of this run, all 52 names: **24** both agree · **21** improving and already
  rated for it · **4** rated behind the evidence · **2** flattered by an old score · **1** poorly
  rated and still slipping
- **It never says buy, sell or hold, and it publishes no score.**

**YOU SAY** *(~35s)*

> “Three things it does. It asks first — four short questions, and every answer actually changes what's on the board, so it's not a survey. It pushes back: give it something vague and you get the question back, sharper. And it competes — it takes a position against a named rating using dated evidence, and shows the working. Twenty-four times out of fifty-two we just agree with the rating, and we say so. Four times we think the rating is behind. Two companies are rated well while their evidence gets worse, and that quadrant is why this is an argument and not another ranking.”

**IF PUSHED — *“so it's a stock picker?”*** → “No. It doesn't rank anything for investment and it never recommends. It says we disagree with this rating, here's the dated evidence. Blend that into one number and none of us could tell you what the number means.”

---

## 4 · Prototype (live)

> **Everything on the next screen is clickable, and it is the same every time you click it.**

**RUN ORDER — 90 seconds, six clicks, no hunting.** *(Pre-flight, off-stage: `python harness.py`
prints ALL CHECKS PASSED → `python server.py` → http://localhost:8000. Real basket, not Demo.)*

| Beat | Click | Say |
|:--:|---|---|
| 0:00 | **The board**, run id top-right | "52 real ASEAN companies. Every number came from one deterministic run — that id. Same files in, same answer out, every time." |
| 0:15 | **The disagreement matrix** | "Left-to-right, what the rating thinks. Bottom-to-top, what the evidence says. Two dashed lines — cross one and a company's label changes. Hollow dots are companies with no evidence at all; we draw the absence rather than hide it." |
| 0:30 | **The RHB chip** *(don't hunt for the dot)* | "Rated 18th. Evidence 98th. Fourteen dated sources." |
| 0:45 | **Evidence trail** → one source link | "Every signal: dated, sourced, directional, with the one-line reason it was weighted that way. A company's own press release is capped at half confidence by rule. Three clicks to the primary source — not our summary of it." |
| 1:05 | **What would change this** *(sensitivity)* | "Pull any one source out and we re-score. This tells you which removals flip the verdict — that is the thing a rating structurally cannot do." |
| 1:20 | **Verify this evidence** | "We recompute every hash and compare with the root anchored on a public chain. **MATCH.** Proof on-chain — no licensed or raw data ever leaves the machine." |

**Held in reserve, for Q&A only:** **Tamper demo** — change one character of one excerpt, the check
flips to **NO MATCH** in about five seconds. That failure *is* the feature.

**Failure modes, rehearse them:** no network → verification still runs locally and reports
`anchor_pending`; **never say "anchored" when the chip says pending.** A filter with nothing in it →
say so: "no name clears Conservative today" is a legitimate answer, and the counts prove it.

---

## 5 · Why the Number Holds

> **We wrote down the bar before we had the evidence, and never moved it.**

**ON SCREEN**

- **Deterministic** — no clock, no randomness, no model in the scoring path. Same files → same
  `run_id` → same quadrants. Checked by a harness on every run.
- **Five guards on every gathered fact** — a source URL the model was not shown is dropped; an
  undated claim is dropped; the source *type* is decided by us from the domain, never by the
  publisher; the verified basket is never overwritten.
- **The cap that costs us** — company-published material is capped at 0.5 confidence. 86% of what a
  public search returns *is* company-published. That cap is why this list is four names, not forty.
- **Pre-registered** — the rule for when a threshold may move was published **before** the sweep ran:
  *a parameter may change for a reason you can argue without reference to the answer it produces.*
- **0** — thresholds moved to produce that list.
- **Backtest keeps the case we get wrong** (Adaro, 2023), flagged.

**YOU SAY** *(~45s)*

> “Two things hold this up. First, the model never scores anything — it reads, the rules score. Same files in, same answer out, and the test suite fails the build if that stops being true. Second, and this is the one I'd poke at if I were you: our top bar returned zero companies for weeks. The tempting fix is to lower it. Instead we wrote down, before the sweep ran, when we're allowed to move a threshold at all — you can move it for a reason you can argue without mentioning the answer, never because you don't like the answer. Then we went and found better sources. Four names crossed. Nobody touched a threshold. And the one we got wrong — Adaro, 2023 — is still in the backtest, because a backtest you can only pass isn't worth much.”

**IF PUSHED — *“a bug could still be hiding in there”*** → “One was, and it's written up. The model read target years as publication dates — 'net zero by 2050' came back dated 2050. That quietly decayed every company's momentum to zero while the signal counts still looked completely normal. Nothing crashed, nothing flagged. So now anything dated later than the basket's own cut-off gets dropped, and we can re-run the filters over evidence we already have without fetching it again.”

---

## 6 · What Separates Us

> **The AI reads. The rules score. And we are on the investor's side of the table.**

**ON SCREEN — four comparisons, one line each**

| | They do | We do |
|---|---|---|
| **A rating** | Publishes a level, late | Publishes a **gap** with a direction and a date on every source |
| **A stock picker / robo-score** | One blended number | Two axes, **never merged** — ESG evidence, and a separate money gate |
| **Chain-based ESG platforms** *(TraceX, Sustainability Track)* | Issuer-side: the company writes its own data to a chain | **Investor-side and adversarial** — the company's own word is our *least*-trusted source |
| **"AI-scored ESG"** | A model assigns the score | The model only **gathers**; scoring is rule-based and costs **zero tokens** |

- The money read is a **gate, computed after the scoring, reported beside it**: 17 strong · 22
  adequate · **11 weak** · 2 unknown, from two audited fiscal years per company.
- **UOB clears the ESG bar and fails the money read** — earnings down 22.6%. We show both. One
  combined score would have hidden exactly that.

**YOU SAY** *(~35s)*

> “Three separations do the work. The model reads and the rules score, so a verdict can't be a hallucination — and scoring costs nothing in tokens, because there's no model in it. The ESG side and the money side never get averaged: UOB is rated behind its evidence and its earnings are down 22.6%, and you can see both because we refused to merge them. And the chain-based ESG platforms people compare us to are issuer-side — a company evidencing its own claims. We're at the other end of that pipe. A company's own press release is the least trusted thing we hold.”

**IF PUSHED — *“what's the blockchain actually for?”*** → “It's the receipt, not the check. A chain can't verify anything that happened off it — make a false claim immutable and all you've got is a permanent false claim. The checking is done by rules you can read. The chain just proves the verdict you saw was built on the evidence we said it was.”

---

## 7 · Investment

> **S$0.079 per company per year. Measured from real token counts, not estimated.**

**ON SCREEN**

| | |
|---|---|
| **S$4.12 / year** | to cover the whole 52-company basket |
| **S$39.65 / year** | at 500 companies |
| **S$158.60 / year** | at 2,000 companies |
| **Zero marginal** | the scoring path — rules and deterministic code, no model reachable |
| **S$118.45** | total spend to build what you just saw |

- All AI cost sits in **gathering**: 4 calls, ~6,059 tokens per company per sweep, yielding ~5.3
  dated facts. Off-peak batching is an exact **50% saving**.
- **Pilot people cost: S$34,965** — and the pilot total is stamped **INCOMPLETE**, because the data
  licence and compliance lines are still blank.
- Day rates derived from **live Singapore job postings**, not a remembered band (ESG analyst
  S$290/day) — and flagged as a floor.
- **What we still need:** a baseline-data licence quote, and one timed batch of ten companies to
  price manual verification. Both are named as missing rather than filled with something plausible.

**YOU SAY** *(~40s)*

> “The economics are odd, because of how it's built. Scoring is rules, not a model, so it costs nothing. All the AI spend is in gathering, and it's charged per sweep of a company rather than per signal — about eight cents a company a year, four dollars for the whole basket. The entire prototype cost a hundred and eighteen Singapore dollars. What I'm not going to show you is a falling cost-per-company curve. Inference is linear, so that line only bends once a data licence gets spread across clients, and we don't have a quote yet. Two cells on that slide are blank on purpose — a made-up number in a cost model is worse than an empty one, because nobody asks about a number that looks plausible.”

**IF PUSHED — *“what would you do with support?”*** → “Better sources, not more of them. Regulator actions, exchange filings, index-provider decisions — the things that aren't press releases. That's the ceiling on how confident this can get, and it's a procurement problem, not an engineering one.”

---

## 8 · Down to Earth

> **What this does not do — said here, before you have to ask.**

**ON SCREEN**

- **86% of what a public search returns is company-published**, and we cap it. That's why four
  names clear the top bar and not forty.
- **Our sensors are documentary, not telemetry.** We read filings, regulator actions, exchange
  notices and press. We do not meter a smokestack.
- **2 of 52 companies carry no dated evidence at all.** Drawn hollow, counted, never filled in.
- **11 of 52 are financially weak** and 2 are unreadable — reported as `unknown`, never marked down
  for *our* missing data.
- **Licensed raters (MSCI, S&P, Sustainalytics) cannot be shown** — licence, not capability. LSEG's
  real published score is fetched live because it is the one free keyless per-company endpoint.
- **Green-bond and traction thresholds are ours**, team-designed, never confirmed by the CGSI panel —
  and every surface says so.
- **Two delisted names stay in the basket**, badged. A static list going stale *is* the argument.
- Without a chain endpoint the run records **`anchor_pending`** and says so. We never claim anchored.

**YOU SAY** *(~30s)*

> “The limits, up front. We read documents, not sensors — no satellites, no meters on anything. Most of what a public search gives you is written by the companies themselves, and we cap how much that can ever count, which is exactly why the top quadrant has four names in it and not forty. Two companies have no evidence at all, and we draw the hole instead of filling it. Eleven are financially weak and we say so — you'll only believe the seventeen strong ones if we didn't quietly drop the weak ones.”

**IF PUSHED — *“only four? that's thin”*** → “It is thin, and it's what the rules gave us. A screen that returns a third of the universe isn't a screen. More names means better sources, not a lower bar — drop the bar and 'rated behind the evidence' starts to mean 'we found a lot of press releases', which is exactly how the Adaro case went wrong.”

---

## 9 · Close

> **It never says buy or sell. It says where it disagrees, on which dated sources, and what would
> change its mind.**

**ON SCREEN — four numbers, nothing else**

| **52** | **391** | **S$0.079** | **0** |
|:--:|:--:|:--:|:--:|
| ASEAN companies, one verified research basket | dated, sourced events behind the verdicts — 48 of 52 covered | AI cost per company per year, measured | thresholds moved to produce our list |

Footline: *every figure reproducible from run `1fc384a2fa92499d`.*

**YOU SAY** *(~25s)*

> “Fifty-two companies. Three hundred and ninety-one dated sources. Eight cents a company a year. And zero thresholds moved to get there — we fixed the bar before we had the evidence, and the names showed up because we found better sources, not a smaller number. All of it rebuilds from that run id on your laptop, offline. It won't tell you what to buy. It'll tell you where the market's view and the evidence disagree, and what would change its mind.”

*(Running long? Cut the third sentence. The rest is doing work.)*

---

## Appendix A — every figure, and where it comes from

Anything you say on stage should be findable here. If a number is not in this table, do not say it.

| Figure | Value | Source |
|---|---|---|
| Run id behind the whole deck | `1fc384a2fa92499d` | `data/nmk_frozen.json` |
| Universe | 52 ASEAN companies, positive ESG-score CAGR 2019–2023, MSCI AC ASEAN constituents throughout | `data/asean_universe.json` (CGSI note, 29 Aug 2025) |
| Quadrants | consensus 24 · future leaders 21 · **rated behind the evidence 4** · overrated leaders 2 · value traps 1 | engine run, verified 2026-08-27 |
| The four | RHB Bank +0.80 (14 src) · SM Prime +0.63 (13) · OCBC +0.58 (17) · UOB +0.46 (10, **money weak**) | same run |
| Evidence base | **391** dated events, 48 of 52 companies; max 25 signals on one name | `data/harvest/` |
| No evidence at all | **2 of 52** | same run |
| N / M / K | **13 issuers · 10 pipeline · 1 review list** | `data/nmk_frozen.json` |
| Financial gate | 17 strong · 22 adequate · 11 weak · 2 unknown | `python financials.py` |
| Basket vs benchmark | +55.1% vs +6.4% cumulative (Jan 2021 – 28 Aug 2025); alpha 7.74%; Sharpe 0.57 vs −0.22 | `data/cgsi_note_figures.json` |
| **The other half** | **−4.6% YTD** to 28 Aug 2025, ~45% banking weight | same file — **always in the same breath** |
| Improver beats index | 28.9% at 1y · 46.2% at 3y · 61.5% at 5y | same file |
| Blind 17-pick overlap | 5 of 17 (29.4%) — **agreement on one of CGSI's three filters**, two of which we cannot see | `tools/phase_b.py` |
| Cost per company/year | **S$0.0793** (off-peak, DeepSeek published card) | `cost_model.py` |
| Scale | S$4.12 (52) · S$39.65 (500) · S$158.60 (2,000) | same |
| Tokens per sweep | 4 calls, 6,059 tokens/company, 5.3 facts kept | `data/harvest_cost.json` |
| Pilot people | S$34,965 — pilot total stamped INCOMPLETE | `data/ESG_Radar_Cost_Model_filled.xlsx` |
| Hackathon actuals | S$118.45 | same |
| Day rates | Data/ML S$405 · Full-stack S$398 · PM S$435 · ESG analyst S$290 (a floor) | `data/sg_day_rates.json`, live MyCareersFuture postings |
| Company-published share | 86% of retrieved sources, capped at 0.5 confidence | `signals.py` |
| LSEG coverage | 50 of 52 resolve by RIC; the 2 misses are the 2 delisted names | `lseg.py` |

## Appendix B — the four questions you will get

| They ask | One line back |
|---|---|
| *"So it's a stock picker?"* | "No — it never ranks or recommends. It reports a disagreement with a named rating and shows the dated evidence under it." |
| *"Why trust your evidence?"* | "No date and no working source means the fact is dropped. **We** decide the source type from the domain — a company announcement can never count like a regulator's filing." |
| *"What's the blockchain for?"* | "The receipt, not the check. It proves the verdict rested on exactly the evidence we said. It cannot make a false claim true — anyone who says otherwise is selling something." |
| *"Only four?"* | "86% of a public search is written by the companies themselves and we cap it. Four is what survives the cap. The fix is better sources, not a smaller number." |

## Appendix C — pre-flight

```bash
python harness.py     # must print ALL n CHECKS PASSED
python anchor.py      # anchors the runs; anchor_pending without an RPC — say pending if it says pending
python server.py      # http://localhost:8000 — real basket, Demo OFF, tier Balanced
```

**Consistency rule from the organisers:** the whitepaper and this presentation must carry the same
numbers. If a figure changes here, change it in `docs/whitepaper/whitepaper.html` and
`docs/pitch/pitch_slide.html` too — and re-render both PDFs.
