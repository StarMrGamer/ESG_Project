# Demo script v5 — the 90-second judge walk

**Build Spec v2 A9.** Written against the shipped build, with the real button labels. Target:
a judge walks it **unaided in under 90 seconds, twice in a row, identically**.

## Before you start (30 seconds, off-stage)

```bash
python harness.py            # must print ALL n CHECKS PASSED
python anchor.py             # builds + anchors the runs (anchor_pending without an RPC)
python server.py             # http://localhost:8000
```

Set the header to **Demo on** (the fictional numeric universe — the real 52 carry evidence text
but no alt-data yet, so the pillar/tier panels would honestly read "awaiting data"). Leave the
tier selector on **Balanced**, the default.

State to reset between runs: none. The engine is deterministic — same files, same `run_id`,
same quadrants, same counts. That is the point of Gate 1 and it is what makes "twice in a row,
identically" a promise rather than a hope.

---

## The walk

| Time | Screen | What you say |
|------|--------|--------------|
| **0:00–0:15** | Dashboard, universe of 36 | "36 ASEAN names. Every number on this screen came from one deterministic run — `run_id` top right. Same inputs, same output, every time." |
| **0:15–0:30** | Disagreement matrix | "Left-to-right is what the incumbent rating thinks. Bottom-to-top is what our live evidence says. The four quadrants are CGSI's: **Future Leaders** (14), **Value Traps** (2), **Consensus** (8), and the one we added — **Overrated Leaders** (3): rated above the median while the evidence deteriorates. *Orchid Bank* sits at the **81st rating percentile with momentum −0.63** — that's the Top Glove shape, live." |
| **0:30–0:45** | Tier flip: Conservative → Balanced → Aggressive | "Risk appetite is a filter, not a different model. **Conservative** wants a reviewed green-bond label, positive momentum, high confidence, profitable. **Balanced** is the origination view. **Aggressive** takes loss-makers with traction and no label at all. Names that don't match **dim — they never disappear.**" |
| **0:45–1:00** | N/M/K + the Hidden Winners strip under the matrix | "N, M, K update live: 12 issuers already priced in, 1 in the pipeline, 3 on the review list. And here are the **Hidden Winners** — take *Selat Bank*: our evidence sits **+0.77** above its rating percentile, on 11 signals, and no labelled issue has priced it. It's the one name that clears every Balanced bar. One click." *(Click the `Selat Bank +0.77` chip — don't hunt for its dot.)* |
| **1:00–1:15** | Evidence trail | "Every signal behind that call: dated, sourced, directional — and each one carries **the one-line rationale** for why it was routed and weighted that way. Company PR is capped at half confidence, and forward-looking language gets its materiality halved. That's the Adaro lesson, in arithmetic." |
| **1:15–1:20** | Click a source link | "Three clicks from the card to the primary source. Not our summary of it — the source." |
| **1:20–1:35** | **Verify this evidence** | "We recompute every hash, walk the Merkle path, and compare with the root anchored on a public chain. **MATCH.** A database operator can rewrite history; this can't be rewritten quietly. Proof on-chain, not data — nothing licensed or raw ever leaves the machine." |

**If a judge pushes** — hit **Tamper demo**: one character of one excerpt changes, and the verdict
flips to **NO MATCH** in about five seconds. That failure *is* the feature. (Keep this button for
rehearsal and Q&A; it is not part of the timed walk.)

---

## Lines to have ready

**On the natural-language question.** The Build Spec's stock line —
*"Natural-language interrogation is on the roadmap — today every answer is a click, not a
prompt"* — **does not fit this build**: the shipped app already has the assistant rail and the
Stage 1→2→3 interrogation relay. ⚠️ Team decision needed before the dry run: either drop the
line, or say what is actually true here:

> "Every number on this screen is a click, and reproducible. The assistant on the right is the
> interrogation layer on top of it — it narrows your question, it never invents the answer."

**On the mocked baseline.** "The rating percentile is a mocked stand-in for the licensed LSEG
figure — it says MOCK on the screen. Swapping in the real baseline changes one field, not the
method."

**On provisional metadata.** "Green-bond and profitability fields are PROVISIONAL until the
verified CSV lands. The badge says so rather than pretending. That swap is a file, not a code
change — the schema froze on 14 Aug for exactly this reason."

**On the wrong answer.** If asked whether the engine is ever wrong: "Yes — Adaro, February 2023.
Announcement momentum was positive; the outcome was three banks declining financing. It's in the
harness as a published failure case, with the confidence cap that keeps it from being a
*confident* wrong answer."

**Never say** buy, sell, hold, or a recommendation. The product disagrees with ratings; it does
not pick.

---

## The 90-second failure modes (rehearse these)

- **Demo toggle off** → real names, no alt-data, honest "awaiting data" panels. Fine to show, but
  it is not the timed walk.
- **A tier with nothing in it** → say so and flip on: "no name in this filter clears Conservative
  today" is a legitimate answer, and the counts prove it. The tiers are deliberately narrow —
  Conservative 2, Balanced 1, Aggressive 1 out of 36. If a judge calls that thin, agree: an
  origination filter that returns a third of the universe isn't a filter.
- **No network** → verification still runs locally against the stored anchor record and reports
  `anchor_pending`. Never claim "anchored" when the chip says pending.
