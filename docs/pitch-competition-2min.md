# The competition reel — 2:30, narrated, one analyst's Monday

**What this is.** A 1080p60 screen recording of the running app with a synchronised AI voiceover.
Institutional, rapid, analytical — 125 words/minute, no music bed, no hype. Every frame is the
real basket on run **`9680adf087a74dcb`**, Demo OFF. Nothing is mocked.

**Budget.** 2:23 of narration + a 0:07 silent end card. At 125 wpm that allows **298 words**;
this script is **292**, and every scene fits its own window with a second or two to breathe. The
counts are checked mechanically — if you edit a line, re-run the check at the foot of this file.

**Subject company.** RHB Bank Bhd — Hidden Winners, disagreement **+0.78**, 14 dated signals,
confidence 0.78, governance **8 up / 1 down**, price momentum **+32.7%**, PPP **26 / 53 / 21**.

---

## Two things to settle before recording

### 1. The number moved, and the script must move with it

The original draft said **+0.804**. After the index-universe harvest merged evidence into the 35
companies both baskets share, RHB reads **+0.784** and the header renders **`+0.78`**. The
narration says *"plus zero point seven eight"* rather than rounding up — a figure spoken louder
than it is printed is the one thing a judge can catch on a freeze-frame.

If the app is re-harvested before the take, **re-read every number off the screen and re-cut
those lines.** Do not trust this document; it is one harvest away from being wrong.

### 2. Scene 10 is now TRUE — the anchor is live

This section previously said the reel could not claim a public ledger. That is no longer the
case. Jayden's `EvidenceAnchor` contract was deployed and verified on Sepolia, and the run this
reel records is **anchored on chain**:

```
run       9680adf087a74dcb
root      69ea18733d3f20d65dcd6d8c200a1a2242d6688645895d129238cb2835d0605e
leaves    423
tx        0x749800584ae9ee3cc8a654268a2401584a83d11d80ea1907b91767275602ea7b
contract  0x73649B84B79892EbdFbBF2eeA69C3d82Db5d165a  (Sepolia, chain id 11155111)
```

`python anchor.py --verify 9680adf087a74dcb` reports **MATCH**, 423 of 423 leaves, recomputed
root identical to the anchored one. The board's chip reads `⛓ anchored` and its explorer button
opens the real transaction.

**So Scene 10 speaks the ledger line as written.** Two details to keep honest:

- **"Seventy-two bytes"** is right and worth saying precisely: `run_id` (32) + Merkle root (32) +
  timestamp (8). No company names, no scores, no signals, no source URLs, and no LSEG data ever
  go on chain — putting licensed data on a public ledger would be a licence breach independent
  of everything else.
- **Do not say the chain verifies anything.** It records a commitment to what the off-chain rules
  already decided. A closed, deterministic system cannot check a real-world fact, and that is the
  one framing a judge can dismantle in a sentence. The narration below says "matches", never
  "verifies".

**ANCHOR LAST, NOT FIRST.** `run_id` hashes every input, so re-harvesting or editing the basket
after this point produces a new run and leaves the anchor pointing at one nobody can see on
screen. The data is frozen as of this anchor; if anything changes, re-anchor and re-read the
figures before recording.

---

## The script

Stage directions in parentheses are each scene's own clock.

### Scene 1 · The board and the core thesis — 0:00–0:13

**VISUAL** Fullscreen disagreement matrix, 52 companies, four quadrants. Hollow zero-evidence
dots clearly visible.
**ACTION** Slow cursor glide across the top-right and bottom-right quadrants.

> Monday, eight a.m. Fifty-two ASEAN companies, read twice overnight — once from dated public
> evidence, once from the rating the market already uses. The product is the gap.

### Scene 2 · Mandate re-segmentation — 0:13–0:23

**VISUAL** The configuration bar.
**ACTION** Click the risk tier **Conservative → Balanced**. Dots re-segment live; dimmed names
stay on screen.

> First, her mandate — set by her fund, not her mood. Risk, holding period, green financing.
> Watch it re-segment.

### Scene 3 · She builds her own board — 0:23–0:32

**VISUAL** The level switch, then the module chips at the foot of the board.
**ACTION** Flip **Everything → Preferences** — the board contracts. Pin two chips back on, one at
a time. Flip back to **Everything**.

*(Demonstrate the picker at Preferences, not at Everything: at level 3 almost every module is
already native, so exactly one chip is offerable and the row has nothing to show.)*

> And the board is hers. Pin the panels she wants, drop the rest. Same run underneath.

*(Layout only — nothing dims or hides, so it reads as customisation rather than a filter. Keep
the clicks unhurried; this is the shortest scene and the easiest to fumble.)*

**The universe control is deliberately not touched.** The whole reel is the CGSI 52 — the only
selection the basket-performance claim describes. Flipping to the 185-name index universe
mid-scene, even briefly, puts a board on screen the narration is not describing, and every figure
spoken over it (fifty-two companies, ten names, plus zero point seven eight) belongs to the other
one.

### Scene 4 · Adaptive interrogation — 0:32–0:49

**VISUAL** The interrogation panel, four ESG-native axes, **0 of 4 covered**.
**ACTION** Click an opener. Show the framing adapt between a risk question and a compliance one.

> Then the part that isn't a dashboard: it asks. Four ESG-native axes, and it pushes back when
> the framing is wrong. Asked as risk it returns a downside check; asked as compliance, a
> disclosure cycle.

⚠️ The original draft named **"BNM's next climate disclosure cycle"**. That sentence is generated
live and cannot be guaranteed to appear. Record the scene first and cut narration to what it
actually returned, or keep the generic line above. Scripting a specific model output and hoping
it appears is how a demo dies on stage.

### Scene 5 · The call list — 0:49–0:57

**VISUAL** The origination pipeline, **M = 10**.
**ACTION** Turn the pipeline filter on. Hover a momentum arrow and a `green_bond_status` of
"none".

> That produces the call list. Ten names — improving, financially sound, not yet green-bond
> issuers. Tomorrow's issuers.

### Scene 6 · Deep dive, RHB Bank — 0:57–1:13

**VISUAL** RHB Bank Bhd. Header reads **`+0.78`**.
**ACTION** Pan the live LSEG twelve-theme wheel, then the pros/cons column and the separate
financial read.

> She opens RHB Bank. Plus zero point seven eight — our evidence rank, minus the rating's.
> Beside it, LSEG's real published score, fetched live. The money read sits beside the ESG
> verdict, never inside it.

### Scene 7 · Two directions, and what the story is about — 1:13–1:31 · **NEW**

**VISUAL** The dual-momentum card, then the PPP triangle.
**ACTION** Hover the **ALIGNED** tag. Move to the triangle; pause on the dot and the three shares.

> Two momentum readings, side by side. The share price over the past year — the classical
> momentum factor. And our evidence. Here both point up. Elsewhere, twelve names run the opposite
> way. Then the triangle: profit, people, or planet?

### Scene 8 · The forecast that reports its own failure — 1:31–1:51 · **NEW**

**VISUAL** The Forward View row — direction, model estimate, published base rate.
**ACTION** Pause on the red **NO MEASURED SKILL** badge, then on the green **MEASURED** badge.

> You want a forecast. We built one. It has no measured skill — negative R-squared, direction
> worse than always guessing up. We ship it saying so, beside the number that is measured:
> CGSI's own published base rate. That is the product.

### Scene 9 · Three clicks to source — 1:51–2:07

**VISUAL** The evidence trail and the signal records.
**ACTION** Three countable clicks: a positive claim → the signal record, dated and scored → the
original filing. Pause on the governance line: **8 up, 1 down**.

> Every claim is three clicks from source. The signal, dated and scored. The record, with its
> hash. The original filing. And the governance line — eight up, one down. We show the one that
> disagrees.

### Scene 10 · Verification and the tamper demo — 2:07–2:23

**VISUAL** The verification panel.
**ACTION** **Verify this evidence** → 423 leaf hashes recompute, root matches, green. **Tamper
demo** → red, hash mismatch, "one character changed, on purpose". Verify again → green restored.
If the chip is on screen, let the `⛓ anchored` badge land in frame.

> Then she verifies. Four hundred and twenty-three hashes recompute, and the fingerprint matches
> a public ledger — seventy-two bytes, written once, ever. Change one character, it breaks. Put
> it back, it matches. Every number checkable.

### Scene 11 · End card — 2:23–2:30

**VISUAL** App URL, repository, team name. **Seven seconds, completely silent.**

---

## What is deliberately not in the reel

Named here so nobody thinks it was forgotten. At 125 wpm, 2:30 buys about 298 words and each of
these would cost 20 or more.

- **The assistant.** "Show banks", "monitor Maybank" — it drives filters and pins companies, and
  it demos beautifully. It is cut because Scene 4 already carries "the app asks questions", and
  two conversational scenes in one reel read as one long one.
- **The Compete answer.** Stage 2's four-line output is the product's headline, and a cold call
  takes 40–70 seconds — a quarter of the reel spent watching a spinner. Pre-warm it with
  `python -m scripts.demo_reset` and hold it on the end card if you want it visible.
- **The in-app manual.** Every rule printed from the loaded run. It is the answer to "how do we
  know", and it is a reading surface, not a watching one.
- **The 185-name index universe.** It appears for two seconds in Scene 3 as a universe swap. The
  `Unrated` story — 185 companies we refuse to place because no rating exists to disagree with —
  is a good 20 seconds that this cut cannot afford.

## Recording notes

All of this cost a rebuild to learn on the previous reel. Full versions in the header of
`scripts/record_demo_reel.mjs`.

- **Hide the present bar with `opacity: 0`, never `display: none`.** `lib/anchor` reserves its
  height as a constant, so any other way shifts the layout out from under every highlight ring.
- **Never use page zoom for legibility.** `documentElement.style.zoom` desynchronises
  `getBoundingClientRect` from what is painted and every ring lands near, but not on, its
  subject. Capture native 1920×1080 and buy legibility with the camera in the composition.
- **Cut on the picture, not on this script's clock.** Chromium's screencast starts before the
  page settles; wall-clock time runs up to four seconds adrift from the frame it produced. Open
  each take on a solid magenta sync frame and measure every cut from it.
- **Render with `--video-frame-format png`.** The default extracts frames as JPEG, and JPEG
  ringing on a dark UI full of one-pixel rules and 11px monospace is visible at slide size.
- **Set the board deterministically** with `python -m scripts.demo_reset` before each take, or a
  coach-mark overlay can appear mid-shot.

## What to check on the finished cut

1. Every number spoken matches the number on screen at that moment. Freeze-frame and compare.
2. The chain anchor is live and `anchor.py --verify` says MATCH. If the basket is re-harvested
   after recording, that stops being true — re-anchor before the final cut.
3. The hollow dots are visible in Scene 1 — an absence of evidence is part of the argument, and a
   cut that crops them out is selling a cleaner board than we have.
4. The dimmed names stay visible in Scene 2. A filter that deletes companies makes the decision
   for the analyst, and the whole point is that ours does not.


## Re-checking the timing after an edit

The word budget is not a guideline — a line that overruns its scene pushes every later cut out of
sync with the picture, and the fix is always a rewrite rather than a faster read. After editing
any spoken line:

```bash
python - <<'EOF'
import re
t = open('docs/pitch-competition-2min.md').read()
body = t.split('## The script')[1].split('## What is deliberately not in')[0]
alt = {l for l in body.split('[Option A alternative')[1].splitlines() if l.startswith('> ')}
for m in re.finditer(r'### (Scene \d+[^\n]*)\n(.*?)(?=\n### |\Z)', body, re.S):
    q = [l for l in m.group(2).splitlines() if l.startswith('> ') and l not in alt]
    w = sum(len(re.findall(r"[A-Za-z0-9'\u2019.-]+", x[2:])) for x in q)
    win = re.search(r'(\d):(\d\d)\u2013(\d):(\d\d)', m.group(1))
    if not w or not win: continue
    span = (int(win.group(3))*60+int(win.group(4))) - (int(win.group(1))*60+int(win.group(2)))
    print(f'{"ok  " if w/125*60 <= span+0.6 else "OVER"} {w:3}w {w/125*60:5.1f}s / {span}s  {m.group(1)[:46]}')
EOF
```

Every line must read `ok`. 125 wpm is the institutional pace the tone calls for; reading faster to
fit a long line is how a confident delivery turns into a rushed one.
