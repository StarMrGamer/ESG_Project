# Three fears — 3-minute script

**Drives:** the **Why it matters** track — `?fears=1`, or **Customise ▸ Demo ▸ Why it matters**.
Eleven clicks, four chapters, and the chapter numbers below are the ones on the bar.

**Budget:** 3:00. Spoken word count **415**, which at a conversational 2.5 words/second is **2:46** —
the fourteen seconds of headroom are for the clicks and the pauses, not for more words.

**Universe: the REAL basket, Demo OFF.** Every figure below is a real company on run
`1fc384a2fa92499d`. **No warm-up needed** — this track never calls the model, so it runs cold and
offline. (`demo_reset` is for the *other* script; running it here switches you to fictional names
and every number in this one goes wrong.)

**Stage directions** are in parentheses and match the track's own steps, so you can just press →.

---

## The script

Everyone wants to invest. Almost nobody starts. And when you ask why, it's never one big reason —
it's three small ones, and they're all fear. We built the Radar for those three. Let me take them
in order, and the app will answer each one live.

### 01 · Afraid of losing money

*(step 1 — the tier control lights up)*

Fear one: losing money. So **you** set the risk appetite, not us. Three tiers.

*(step 2 — Conservative)*

Conservative. Labelled, reviewed, profitable issuers only, and only where the evidence is strong.
Out of fifty-two companies, that leaves **three**.

*(step 3 — Aggressive)*

Aggressive is for loss-makers with traction. We have two loss-makers, and the data we hold can't
run the traction screen on either — so it's empty. We'd rather show you an empty board than a
fudged one.

*(step 4 — back to Balanced)*

And notice what happens to the names that don't fit. They **dim**. They never disappear. You still
have to be able to see the company you're choosing not to hold.

### 02 · Not knowing where to start

*(step 5 — the whole plot)*

Fear two: you don't know where to start. Fifty-two companies, and you're not scrolling a list —
every one of them is a dot.

*(step 6 — the x-axis)*

Side to side is what the published rating thinks. Up and down is what dated news and filings say.
That's it. Two directions.

*(step 7 — the top-left corner)*

Which gives you four corners. This one — rated low, still improving — is where the rating hasn't
caught up with the evidence yet. **Four companies** are in it today. That's where you start
looking.

### 03 · Never seeing it coming

*(step 8 — RHB Bank, the radar)*

Fear three, and it's the one that actually costs money: by the time you hear about it, it's
already in the price.

RHB Bank. The dashed ring is **no change** — that's what a rating quietly assumes while it waits
for its next refresh. The filled shape is what today's evidence says.

*(step 9 — the evidence trail)*

And here's that evidence. **Fourteen sources**, every one dated, sourced, in its own words. News,
filings, exchange notices. A rating updates on its own cycle. This moves when the evidence moves.

*(step 10 — what would change it)*

Its rating puts it in the **bottom fifth** of this basket. The evidence puts it in the **top two
percent**. And before you ask what that's standing on — take any single source away and nothing
changes. The **five heaviest** would all have to go.

### 04 · See it for yourself

*(step 11 — the assistant)*

And you don't have to take my word for any of it, because none of that was a slide. That was the
app, running. Ask it something.

It won't tell you what to buy. It never will. It tells you where the market's view and the
evidence part company — and exactly what would change its mind.

---

## Timing

| Chapter | Beat | Runs | Cumulative |
|---|---|---|---|
| — | Open — three fears | 0:18 | 0:18 |
| 01 | Tiers · three names · empty aggressive · dimming | 0:41 | 0:59 |
| 02 | Fifty-two dots · two directions · the corner | 0:34 | 1:33 |
| 03 | The ring · fourteen sources · bottom fifth vs top two percent | 0:52 | 2:25 |
| 04 | It was the app · never says buy | 0:25 | **2:46** |

**If you are running long**, cut in this order:

1. **The aggressive tier** *(−0:16)* — click through it and say nothing. You lose a good honesty
   beat, but chapter 1 still makes its point with Conservative and the dimming. **→ 2:30.**
2. **"Side to side… two directions"** *(−0:12)* — the axes are labelled on screen. **→ 2:18.**

**Never cut:** the dimming line (it is the whole mandate argument), *fourteen sources*, or
*bottom fifth / top two percent* — that pair **is** the product.

**If you are running short**, the honest filler is the one number that is not on this page: two of
the fifty-two have no dated evidence at all, and they are drawn hollow rather than quietly filled
in.

---

## Every number in this script

Read off run `1fc384a2fa92499d`, re-derived the day this was written. If the run is re-frozen,
re-read them — do not trust this table.

| Line | Figure | Source |
|---|---|---|
| "fifty-two companies" | 52 | `data/asean_universe.json` |
| "that leaves three" | 3 clear Conservative | `tiers.conservative` on the run |
| "we have two loss-makers… can't run the screen" | PCHEM, PTTGC → `screen_not_run` | `traction.py` |
| "aggressive… it's empty" | 0 clear | `tiers.aggressive` on the run |
| "four companies are in it" | hidden_winners = 4 | `label_counts` |
| "fourteen sources" | `signal_count` 14 | RHB Bank |
| "bottom fifth" | `lseg_percentile` 0.18 | RHB Bank |
| "top two percent" | `momentum_percentile` 0.98 | RHB Bank |
| "take any single source away" | `load_bearing_count` 0 | `python sensitivity.py KLSE:RHBBANK --real` |
| "the five heaviest" | `smallest_flip_set` 5 | same |

---

## Three things not to say

1. **No "buy", "sell", "hold", or "our score".** The close is written to end on this; don't
   undo it thirty seconds earlier.
2. **Don't call +0.80 a score.** If you reach for the number at all, it is *a disagreement, and it
   has a direction*. The script deliberately says "bottom fifth / top two percent" instead —
   plainer, and it cannot be misheard as a rating.
3. **Don't say the blockchain verifies the evidence.** It isn't in this script, and if a judge
   raises it: *"it's the receipt, not the check."*

## If a judge interrupts

Press **`i`**. The app unlocks and you can click anywhere. Press **`i`** again and the walk resumes
on the step you left. Nothing is lost, and you do not have to restart.
