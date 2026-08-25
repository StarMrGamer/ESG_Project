# Things to do — answered

**To:** Jayden
**From:** Vrishabd
**Date:** 24 August 2026
**Read time:** ~8 minutes. The four **TAKE NOTE** boxes are the parts that change what we say on stage.

---

## Where the list stands

| You asked for | Status | One line |
|---|:--:|---|
| ESG scoring + OECD matrices | ✅ | 52 companies, 180 signals, all four quadrants populated |
| Add Sustainalytics / S&P | ⚠️ | Licensed — cannot be fetched or shown. LSEG is the free substitute and is already live |
| A financial layer | ✅ | Built. 17 strong / 22 adequate / 11 weak / 2 unknown across all 52 |
| Bridge ESG + financial into a conclusion | ✅ | **This is the M bucket — 11 companies.** It already existed; the financial half was just invisible |
| "What to look out for" per company | ✅ | Pros and cons on both axes, plus what would change the verdict |
| Compare with a random company | ✅ | Assistant yes, engine no — and the reason is our *strong* answer |
| Blockchain: wallet + key, RPC URL | 🔴 | Everything is built and tested. Needs three env vars from you |
| Blockchain: 3-layer framing | ⚠️ | Right idea, one important correction below |
| Cost to scale | ⚠️ | 3 of 4 components measured. One needs a stopwatch, one needs a quote |
| Overall summary + feature breakdown | ✅ | Published — link at the end |

---

# 1 · Features

## 1.1 The OECD matrices — one correction worth having

The industry benchmark is **not an ESG rating and never stood in for one**. It is a greenhouse-gas
intensity measured in **grams of CO₂e per euro of gross value added** — it sizes how carbon-heavy
an *industry* structurally is, so a bank and a cement producer are not judged on the same bar.

Two things follow:

- Our code **refuses** to subtract that intensity from a company's ESG score. They are different
  measures, and differencing them would be exactly the sloppiness this project exists to call out
  in others.
- Despite the filename, the data is **Eurostat, not the OECD**. Every screen says *"OECD-Europe
  (EU-27) benchmark"* and cites the dataset. All 22 rows re-download from a free, keyless API in
  about ten seconds — **a judge can reproduce our benchmark on their own laptop.** That is worth
  saying out loud.

## 1.2 Sustainalytics and S&P — why we use LSEG instead

> **TAKE NOTE**
> This is not a technical shortfall we can engineer around. MSCI, Sustainalytics and S&P are
> **licensed products**. Fetching, displaying or redistributing their scores without a contract is
> a licence breach — a real legal exposure at a public demo, not a style preference.

**LSEG is the only major rater with a free, keyless, per-company endpoint.** That is the entire
reason it was chosen. We use it attributed, on demand, one company at a time, cached locally, and
we never write a scrape to disk.

**We are not blind to the other houses.** Two things you can say confidently:

1. Wherever a company's own evidence cites **MSCI, Sustainalytics, S&P Global / DJSI, CDP,
   FTSE4Good or GRESB**, we read it and it feeds the evidence score.
2. The basket carries an **industry-standard notch grade** — BBB / BB / B, which is the MSCI
   scale — and it is now displayed in the evidence panel. It travels **unattributed**, because the
   source column names no agency, and it is **display-only**: letting a second rating into the
   maths would be two rulers in one number.

**One thing to tell CGSI:** their `lseg_rating` column is mislabelled. Its values are BB/BBB/B —
the MSCI notch scale. LSEG's own scale runs A+ to D−. We verified this against the live LSEG
endpoint (SGX 62 vs 52, Siam Cement 70 vs 78, PTT 73 vs 78 on a 0–100 basis).

## 1.3 The financial layer — built

Two fiscal years of net income for **all 52 companies**, already verified with sources on the row.
No fetch was needed, which matters: the free financial endpoints are gone (Yahoo's fundamentals API
now requires an authenticated token) and the licensed ones are off the table for the same reason as
S&P.

**Result across the basket:**

| Verdict | Count | Meaning |
|---|:--:|---|
| **strong** | 17 | Profitable *and* earnings growing |
| **adequate** | 22 | Profitable, earnings flat or modestly up |
| **weak** | 11 | Profitable but earnings declining |
| **unknown** | 2 | Loss-making — the traction screen decides these |

> **TAKE NOTE — `unknown` is not a failure.**
> The two loss-makers are not disqualified. They route to the four-test traction screen, and until
> that screen has been run the honest answer is "we don't know." Scoring an unrun test as a failure
> would disqualify a company for *our* missing data rather than its own numbers. If anyone asks why
> two companies have no verdict, that is the answer, and it is a strength.

**Three parsing bugs were found and fixed while building this.** Each one had been producing a
confidently wrong number under a real company's name:

| The cell | Reported | Actually |
|---|---:|---:|
| `S$789m (S$1.1b cont. ops)` | +83,836% | −16.1% |
| `~RM3.3–3.4b` | −99.9% | **+8.1%** |
| `9M2024 RM606m` | −98.3% | not comparable |

The middle one is **RHB Bank — our single largest ESG disagreement.** It read as a bank that had
almost stopped earning; it actually grew 8%. All three are now locked into the test suite so they
cannot come back.

## 1.4 The bridge — it already exists, and it is called M

This is the centre of your ask: *"bridge between ESG and financial data into a conclusion to find
hidden winners (green-bond companies)."*

That conclusion already ships as **N / M / K**:

| | Count | Rule |
|---|:--:|---|
| **N — issuers** | 13 | Already a labelled/reviewed or CBI-certified green-bond issuer. Priced in. |
| **M — pipeline** | **11** | Below its industry's ASEAN peer ESG average **and** positive evidenced momentum **and** passes the financial screen **and** not already an issuer **and** not delisted |
| **K — review list** | 3 | We disagree, but something still blocks it — confidence, profitability, sector position, unverified metadata. A human looks at these. |

**M is the bridge.** The ESG half says the company is improving and under-rated; the financial half
says it can carry a bond. What was missing until now was not the logic — it was that the financial
half was invisible on screen. It isn't any more.

> **TAKE NOTE — the two axes are shown side by side and never merged.**
> There was a version of this where we blend earnings growth into the ESG momentum score. **We must
> not build that**, and here is the argument in one sentence: *the moment the output is one combined
> number, nobody — including us — can say which half is driving it, and we stop being a tool that
> disagrees with ratings and become a tool that picks stocks.*
>
> "Disagreement" currently means one precise, defensible thing: our evidence-based momentum rank
> minus the incumbent rating's rank. That precision is the product. The financial read is a **gate**
> — it tells you whether an ESG disagreement is worth acting on. It never moves the ESG verdict.
> Our test suite now enforces this: the engine is checked to make sure it cannot even import the
> financial module.

## 1.5 Every verdict now explains itself

New on every company: **ESG pros and cons, financial pros and cons, and a "what to look out for"
list** — how close it sits to a boundary, whether its metadata is still provisional, whether its
evidence is too old for the selected horizon.

All of it derived by rule from the stored run. No language model wrote any of it, so it reproduces
exactly and cannot drift between two readings of the same company.

**The cons are never hidden or collapsed.** They render at the same size, in the same column, as
the pros. A case that only lists reasons to agree is marketing — and a tool whose whole argument is
that inconvenient evidence must surface cannot make an exception for its own verdicts.

*Example — RHB Bank:* 7 ESG pros, 2 ESG cons (*confidence 0.33, below the bar; zero social and
digital evidence*), 2 financial pros, gate verdict **adequate**.

## 1.6 Hidden Winners is zero — and that is the honest answer

Twelve companies clear the disagreement threshold. **Every one of them fails on confidence.**

The reason is not the signal count, and lowering the count threshold changes nothing. The reason is
that **79% of what live search returns is company-published material**, which our source-quality
rule caps at 0.50 confidence. So confidence mathematically cannot climb past roughly half of
coverage, however much more we gather.

> **TAKE NOTE — do not let anyone lower the bar to populate this quadrant.**
> That is precisely the Adaro failure. If we relax the threshold, "Hidden Winner" comes to mean
> *"we found a lot of press releases about this company"* — which is how ESG ratings got their
> reputation in the first place.
>
> The line to use: *"That's the confidence model working. It refuses to be confident about
> self-reported evidence, which is the entire reason the cap exists. The route to a real Hidden
> Winner is better sources — regulator actions, exchange filings, index-provider decisions — not
> more press releases and not a smaller number."*
>
> A screen that returns zero when the evidence doesn't support a claim is more credible than one
> that always finds something.

## 1.7 Comparing a random company

Different answer for each half of the system, and the honest one is the stronger one.

| | The assistant | The engine |
|---|---|---|
| **Scope** | Any company on earth | A defined peer cohort |
| **Output** | An argument, in sentences | Momentum, disagreement, quadrant |
| **Needs** | A working search | Dated evidence for *every* name in the set |

A random company works **today** through the assistant: live retrieval builds a grounded profile,
LSEG's real published score is available for roughly 12,500 issuers, and the relay argues about it.

> **TAKE NOTE — never demo an off-basket company through the engine board.**
> Momentum percentile is a **rank**. Hand the engine a company outside the cohort and it still
> returns numbers — misleading ones. With no supplied rating, the baseline defaults to zero, which
> ranks the company dead last, which produces a disagreement of **+0.673**.
>
> That reads on screen as *"the market badly underrates this company."* It actually means *"we
> don't have their rating."* An absence rendered as a finding — and it looks completely normal,
> which is what makes it dangerous.
>
> The line to use: *"The engine scores against a defined peer set — that's what makes a percentile
> mean anything. Hand us a company outside it and the assistant does the work. What we won't do is
> print a momentum percentile, because we'd be ranking it against nobody."*

---

# 2 · Blockchain

## 2.1 The framing — right idea, one correction

Your three-layer framing is correct and it maps cleanly onto what we already built:

| Layer | What it is here |
|---|---|
| **1 · Sensors** | Four-angle live search, the live LSEG rating, the industry benchmark, the verified basket |
| **2 · Verification** | Five harvest guards, source type decided by domain, company PR capped at 0.50, forward-looking claims halved, rule-based scoring, provisional-until-reviewed, maker-checker |
| **3 · Ledger** | One Merkle root per run, append-only `run_id → root` |

> **TAKE NOTE — the chain is the LEDGER layer, not the verification layer.**
> Your message put blockchain in verification. **The Blockchain Council quote you sent actually
> argues the opposite** — a chain is closed and cannot reach real-world information, so it has no
> way to check an off-chain fact. Immutability applied to a false claim just makes the false claim
> permanent.
>
> Our verification is done entirely **off-chain**, by rules any reviewer can read. The chain records
> a *commitment* to what those rules saw.
>
> This matters on stage: if we pitch "blockchain = verification," the first informed judge dismantles
> us using the exact quote we were given. If we say "sensors, verification, ledger — and the chain is
> the third one," we are ahead of the question.

## 2.2 What the chain actually stores

The entire contract state is a run id, a 32-byte hash and a timestamp — **72 bytes per run**. No
company names, no scores, no signals, no URLs, no evidence text. A run containing 234 pieces of
evidence puts **one** number on chain.

**It is not a database:**

- You cannot read the data back out. The chain returns a hash; it does not know what any signal says.
- The operator cannot rewrite a row. A run id can be written **once, ever** — a second write is
  rejected by the contract. *That single rule is the whole tamper-evidence story.*
- No token, no DAO, no on-chain scoring, and no licensed data ever written (putting LSEG data on a
  public chain would be a redistribution breach on its own).

**Where it earns its place:** an investor acting on our August 2026 verdict, asking in 2028 whether
that verdict was really built on this evidence or backfilled later. A hash anchored at the time
answers that, and nobody has to trust us to check it.

**On stage it is one click:** *Verify → MATCH*, showing the raw string being hashed — then flip the
tamper toggle and watch the root break.

## 2.3 What you need to do — wallet and RPC

Everything else is built and tested. This is the only blocker.

**1. Make a throwaway wallet.** MetaMask → new account, used for nothing else. Switch to the Sepolia
test network (Settings → Advanced → *Show test networks*).

**2. Fund it.** Any Sepolia faucet — Google Cloud Web3 or Alchemy both work with just the address.
0.01 test ETH is plenty; a full anchoring run is four transactions and costs effectively nothing.

**3. Get an RPC URL.** No signup needed: `https://ethereum-sepolia-rpc.publicnode.com`.
Alchemy or Infura free tier is more reliable if you prefer.

**4. Deploy the contract.** Go to remix.ethereum.org → new file → paste our `EvidenceAnchor.sol`
(30 lines) → compile with Solidity 0.8.20+ → Deploy tab → Environment = *Injected Provider –
MetaMask* → confirm it says **Sepolia** → Deploy. Copy the deployed address.

> **⚠️ The one trap that will bite you.** The contract records whoever deploys it as the only
> permitted signer. **The wallet that deploys must be the same wallet whose key you use to anchor.**
> Deploy from account A and anchor from account B, and every transaction fails with `"not signer"`.

**5. Send Vrishabd three values** — the RPC URL, the contract address, and the private key — and the
anchoring run takes about a minute.

Two more things worth knowing:

- **Anchor last, not first.** The run id is a hash of every input. If anyone re-harvests or edits the
  basket after anchoring, the id moves and the old anchor points at a run that no longer exists on
  screen. Freeze the data, *then* anchor.
- **Re-running is safe.** The contract rejects a duplicate rather than crashing, so it can be run as
  many times as you like.

## 2.4 TraceX and Sustainability Track — not competitors

Both are **supply-chain platforms**: the company itself writes its own operational data to a chain
to evidence its own claims. That is issuer-side layers 1 and 3, with layer 2 amounting to "immutable
once written."

**We are investor-side and adversarial to the issuer.** The company's own publication is the
*least*-trusted source we hold — capped at 0.50 confidence by rule — and our entire output is a
disagreement with a rating rather than a report for the rated company.

Opposite ends of the same pipe. Worth saying if a judge raises them, because it reframes them as
evidence the space is real rather than as competition.

---

# 3 · Pitching

## 3.1 What it costs to scale

Measured from real token counts over a full sweep, not estimated.

| Component | Cost shape | Status |
|---|---|:--:|
| ESG evidence gathering | Linear in companies — **S$0.079 per company per year** | ✅ measured |
| Scoring, bridging, the case | **Zero marginal** — deterministic code, no model involved | ✅ measured |
| Financial + green-bond metadata | **People, not tokens** — verified by hand, per company | ⚠️ needs one timing |
| Baseline ESG data licence | Fixed. *The only cost that falls per company as clients are added* | 🔴 no quote |

**The headline numbers:** S$4.12/year to cover all 52 companies. S$39.65 at 500. S$158.60 at 2,000.
Running sweeps off-peak is an exact 50% saving, and a sweep is a batch job — so that is free money.

**Why so cheap:** the scoring path costs **zero tokens**. Rules route the evidence, deterministic
code scores it, and no language model is reachable from either. All AI cost sits in *gathering*, and
is charged per sweep of a company rather than per signal.

**The one number nobody has:** how many minutes it takes to verify one company's metadata by hand.
Day rates are measured from live Singapore job postings (ESG analyst **S$290/day**, ≈S$36/hour), so
the formula is `minutes per company × S$36/hour`. At an illustrative 20–40 minutes that is roughly
**S$12–24 per company one-off**, or S$600–1,200 to build a fresh 52.

**Action: time one batch of ten companies.** That converts our weakest cost line into a fact, and it
is an afternoon's work.

> **TAKE NOTE — do not draw a falling cost-per-company curve in the deck yet.**
> Inference is linear in companies, so on this cost alone the line is **flat**. It only falls once
> the fixed data licence is spread across clients — and no licence quote exists. Drawing that curve
> before the number arrives is drawing the conclusion first, which is the one thing a cost model
> exists to prevent. An investor who spots it will assume the rest of the model is decorative too.

## 3.2 The selling point — stated correctly

You wrote: *"the selling point is that data now says buy but later it might say sell."*

The instinct is exactly right. The wording is not, and it is worth fixing, because **we never say
buy or sell** — that is a regulated claim, and it is also a weaker version of what we can actually
prove.

**The stronger version:**

> A rating is a *level*, published late and updated slowly. Our verdict is built from dated
> evidence, so **it moves when the evidence moves** — and we can show you exactly which piece of
> evidence is holding it up.

And unlike "buy", we can demo both directions:

- **Forwards** — remove each signal in turn and show which removals change the verdict. *"This
  company's label rests on two filings. Here they are."*
- **Backwards** — five validation cases where every point is a real engine run at its own historical
  cutoff, showing our verdict changing on real dates while the incumbent rating sat still.

That is a live view against a stale one, and it is **checkable**. "Buy" never is.

*(We deliberately kept the case we get wrong — Adaro — in the backtest, flagged. A backtest you can
only pass is not a backtest, and a judge who spots a curated one discounts everything else.)*

## 3.3 Two numbers that must not go on a slide alone

> **TAKE NOTE — the −4.6% has to sit beside the 55.1%.**
> CGSI's own note reports the basket **lagging the index by −4.6% year-to-date** as of 28 Aug 2025,
> on a roughly 45% banking weight — and that ESG improvement alone does not predict single-stock
> performance (probability an improver beats the index: 28.9% at 1 year, 46.2% at 3 years, 61.5% at
> 5 years).
>
> Our board already shows this next to the 55.1% vs 6.4%. **It must stay in the deck.** A tool whose
> entire thesis is that inconvenient evidence has to surface cannot make an exception for its own
> foundation — and any judge who reads the CGSI note finds it in ten seconds, after which everything
> else we said is suspect.

**And never show 29.4% without CGSI's three filters.** Their high-conviction 17 are selected by
(i) above-average ESG CAGR, (ii) inclusion in their coverage universe, and (iii) an *Add*
recommendation. **Only the first is an ESG signal** — the other two are invisible to our engine, and
our rules forbid it from ever forming an investment recommendation. So 29.4% is agreement on one
criterion out of three. It is **not** a 70% disagreement about ESG, and presenting it that way is an
error a sharp judge will catch.

---

# 4 · Everything to take note of, in one place

1. **The chain is the ledger layer, not verification.** Your own quote proves it.
2. **The two axes never merge.** Financial data is a gate, not part of the ESG score.
3. **Hidden Winners is zero and stays zero.** Nobody lowers the threshold.
4. **Never run an off-basket company through the engine board.** It produces a convincing, meaningless +0.673.
5. **The −4.6% goes on the slide** next to the 55.1%.
6. **29.4% never appears without CGSI's three filters.**
7. **No falling cost curve** until a licence quote exists.
8. **We never say buy or sell.** We say what changes the verdict.
9. **MSCI / S&P / Sustainalytics cannot be shown** — licence, not capability.
10. **Tell CGSI their `lseg_rating` column is mislabelled** — it is the MSCI notch scale.

---

# 5 · Blocked on you

| Item | What is needed |
|---|---|
| **Sepolia anchoring** | RPC URL, contract address, private key — §2.3 above. Everything else is built |
| **Metadata timing** | Someone times one batch of ten companies, so the cost model stops guessing |
| **Licence quote** | LSEG or CGSI, pilot scope. The last blank in the business model |
| **PTTGC reconciliation** | Cayden's audited FY2025 loss is THB 15,572m; CGSI's row says THB 14.6b |

---

## Reference

- **Operating manual** — full feature breakdown, how each part runs, what the blockchain does, and the scaling cost:
  https://claude.ai/code/artifact/7b41ded6-7518-48bf-b81f-fccd25e5662e
- **Codebase field guide** — how the system is built, for anyone who has to defend it:
  https://claude.ai/code/artifact/d328257f-727a-41cd-bcde-07d77c2658c9

Every figure in this document was verified against the running system on 24 August 2026.
