import { useEffect, useRef, useState } from 'react'
import { useStore } from '../../store'
import type { ModuleKey, Settings } from '../../store'
import { Spotlight, el, trackAnchor } from '../../lib/anchor'

/**
 * The first-run tutorial — six cards, once, straight after setup.
 *
 * Setup answers "what do you want", and then the board appears with a radar, a matrix, four
 * pillar tiles and a rail on it. Everything on that screen is explainable, and none of it
 * explains ITSELF to somebody seeing it for the first time — which is how a board that is doing
 * something quite specific reads as "a dashboard".
 *
 * THIS IS NOT PRESENT MODE, and the difference is worth stating because the two look alike.
 * Present mode is the PITCH: it drives the app into each state, walks into the deep dive, calls
 * the model, and says nothing on screen — a presenter talks over it. This teaches the reader to
 * read one screen, drives nothing, and is finished in about twenty seconds. They share the
 * anchoring helpers (`lib/anchor`) and nothing else.
 *
 * TWO RULES IT KEEPS
 *
 * 1. **A step whose anchor is not on screen is SKIPPED, not faked.** The board is layered
 *    (`settings.level`), and setup can land the user on any of the three levels, so which of
 *    these elements exist is genuinely unknown at write time. Pointing at a thing that is not
 *    there is worse than not mentioning it, and a hard-coded level would fight the answer the
 *    user just gave.
 * 2. **It never blocks the board.** The ring dims, it does not trap: a first-time visitor who
 *    would rather click something than read is right, and clicking is how this app is learned.
 *    If they navigate away the remaining anchors vanish, rule 1 takes over, and the tutorial
 *    winds up at its closing card instead of stranding them mid-lesson.
 */

interface Card {
  /** `data-tour` value. Omitted = a plain card in the middle of nothing, for the closer. */
  anchor?: string
  title: string
  body: string
  /**
   * Put the thing on screen before pointing at it.
   *
   * A card's anchor may simply not be rendered in the board the reader happens to be on — the
   * one-line assistant only exists at Preferences with the rails shut, the matrix only when the
   * level or a pinned chip asks for it. The first version left those cards pointing at nothing:
   * the text showed, no ring appeared, and the tour looked broken at exactly the moment it was
   * explaining something.
   *
   * So a card can ESTABLISH its own subject, the way present mode establishes a view. It runs
   * only when the anchor is missing, so a reader who already has the panel open is never
   * re-arranged around it.
   */
  ensure?: (s: Settings) => Partial<Settings>
}

/** Bring the assistant into view: the rail at any level, since the one-line bar is level-1 only. */
const ensureAssistant = (s: Settings): Partial<Settings> => ({
  rightOpen: true,
  extras: s.extras.includes('rails') ? s.extras : [...s.extras, 'rails' as ModuleKey],
})

/** Bring the plot into view: pin it rather than moving the reader's level under them. */
const ensureMatrix = (s: Settings): Partial<Settings> => ({
  extras: s.extras.includes('matrix') ? s.extras : [...s.extras, 'matrix' as ModuleKey],
})

/**
 * The investor's four. Same rules, different board: there is no radar and no percentile to
 * explain, so the cards teach what that reader can act on — the verdict, the receipts, the
 * assistant, and the fact that the numbers are one click away rather than gone.
 */
const INVESTOR_CARDS: Card[] = [
  {
    anchor: 'verdict-plain',
    title: 'What this is',
    body: 'A published ESG rating is a level, and it refreshes slowly. This says where dated news '
      + 'and filings disagree with it — in sentences, not scores. It never says buy or sell.',
  },
  {
    anchor: 'receipts',
    title: 'Every line has a source',
    body: 'These are the actual filings and news items behind the verdict, with their dates. '
      + 'Click one to read it yourself — and the ones that argue the other way are in the full '
      + 'list too, never dropped.',
  },
  {
    anchor: 'assistant',
    ensure: ensureAssistant,
    title: 'Just ask',
    body: '“How is DBS doing?”, “show me banks”, “monitor Maybank” to keep one on your list. It '
      + 'moves what is on screen and it will not invent an answer.',
  },
  {
    anchor: 'matrix',
    ensure: ensureMatrix,
    title: 'The whole basket, in one picture',
    body: 'Every company we track is a dot here, placed by two different readings at once. Side '
      + 'to side is what its published rating thinks — left, unimpressed; right, impressed. Up '
      + 'and down is what dated news and filings say — top, improving; bottom, getting worse.',
  },
  {
    anchor: 'matrix',
    ensure: ensureMatrix,
    title: 'The four corners are just those two, combined',
    body: 'Left + top: rated low but improving — the corner this whole product exists for. Right '
      + '+ top: rated well and improving, everyone agrees. Right + bottom: rated well but '
      + 'slipping — what a slow-moving score cannot show you. Left + bottom: rated low and still '
      + 'slipping. Most companies sit on the agreeing diagonal; the interesting ones do not.',
  },
  {
    anchor: 'explain-matrix',
    ensure: ensureMatrix,
    title: 'Corner by corner, whenever you want it',
    body: 'This button walks the plot properly — both directions, the two dividing lines, each '
      + 'corner on its own, and what a dimmed or hollow dot means. It is always there on the '
      + 'chart, so nothing here has to be remembered.',
  },
  {
    anchor: 'show-numbers',
    title: 'The numbers are right here',
    body: 'Nothing is hidden from you — this puts the full analyst view back on screen: the '
      + 'radar, the percentiles and the score record. The Analyst switch at the top keeps it '
      + 'that way.',
  },
  {
    anchor: 'manual',
    title: 'And the long version',
    body: '“How it works” explains the whole thing line by line — where the companies come from, '
      + 'how a news item becomes evidence, how sure we are and why that is capped, and what this '
      + 'app cannot do. It reads itself out of the run you are looking at.',
  },
]

const CARDS: Card[] = [
  {
    anchor: 'hub',
    title: 'The dashed ring is the argument',
    body: 'That ring is zero momentum — what a rating quietly assumes while it waits for its '
      + 'next refresh. The filled shape is what today’s evidence says. The gap between them is '
      + 'the entire product.',
  },
  {
    anchor: 'backing',
    title: 'Every verdict has receipts',
    body: 'This line counts the dated sources underneath it. One click gets you each excerpt, '
      + 'its source, its date — and the ones that point the other way, which we never drop.',
  },
  {
    anchor: 'assistant',
    ensure: ensureAssistant,
    title: 'Ask it in plain English',
    body: '“Show banks” filters. “Monitor DBS” keeps a company on your list. Ask it something '
      + 'loose and it hands the question back sharper. It will not invent an answer, and it '
      + 'never says buy or sell.',
  },
  {
    anchor: 'level',
    title: 'Two views, not five',
    body: 'Preferences is the board your setup answers asked for — the verdict and one action. '
      + 'Everything is every panel at once: the matrix, the evidence trail, the provenance and '
      + 'the run id that rebuilds all of it.',
  },
  {
    anchor: 'add-modules',
    title: 'Or take one piece of a level',
    body: 'You do not have to take everything to get one thing. These chips pin a single panel '
      + 'onto the view you are on — Preferences plus the disagreement matrix, if that is the '
      + 'shape you want. Click the same chip again to drop it; it stays where it is in the row.',
  },
  {
    anchor: 'matrix',
    ensure: ensureMatrix,
    title: 'The whole basket, in one picture',
    body: 'Every company we track is a dot here, placed by two different readings at once. Side '
      + 'to side is what its published rating thinks — left, unimpressed; right, impressed. Up '
      + 'and down is what dated news and filings say — top, improving; bottom, getting worse.',
  },
  {
    anchor: 'matrix',
    ensure: ensureMatrix,
    title: 'The four corners are just those two, combined',
    body: 'Left + top: rated low but improving — the corner this whole product exists for. Right '
      + '+ top: rated well and improving, everyone agrees. Right + bottom: rated well but '
      + 'slipping — what a slow-moving score cannot show you. Left + bottom: rated low and still '
      + 'slipping. Most companies sit on the agreeing diagonal; the interesting ones do not.',
  },
  {
    anchor: 'explain-matrix',
    ensure: ensureMatrix,
    title: 'Corner by corner, whenever you want it',
    body: 'This button walks the plot properly — both directions, the two dividing lines, each '
      + 'corner on its own, and what a dimmed or hollow dot means. It is always there on the '
      + 'chart, so nothing here has to be remembered.',
  },
  {
    anchor: 'manual',
    title: 'And the long version',
    body: '“How it works” is the full explanation — the pipeline in order, every label rule and '
      + 'threshold printed from the loaded run, and a plain list of what this app cannot do.',
  },
  {
    title: 'That’s the whole idea',
    body: 'It tells you where we disagree with a published rating, on which dated sources, and '
      + 'what would change our mind. Reconfigure re-runs setup and Tutorial replays this — both '
      + 'live under the ⚙ menu.',
  },
]

/**
 * THE MATRIX, CORNER BY CORNER — asked for by name, from the plot itself or the ⚙ menu.
 *
 * The disagreement plot is the densest thing in the product and the one that carries its whole
 * argument, and for most of this app's life its only explanation was an axis caption written in
 * percentiles. Four corners, two axes, two boundaries and one honest oddity (a hollow dot), each
 * ringed while it is described.
 *
 * The quadrant cards deliberately do NOT say which companies are in each corner. Naming names
 * here would turn an explanation of the axes into a tip sheet, and the plot is right there — the
 * reader can click a dot the moment they understand what a dot means.
 */
const MATRIX_CARDS: Card[] = [
  {
    anchor: 'matrix',
    title: 'One dot per company, two questions at once',
    body: 'Every company we track is on this plot twice over: where its published rating puts it, '
      + 'and where the dated evidence puts it. The gap between those two is the whole product, '
      + 'and it is what the position of a dot means.',
  },
  {
    anchor: 'axis-x',
    title: 'Side to side: what the rating thinks',
    body: 'A dot on the LEFT means the published ESG rating is unimpressed with that company. On '
      + 'the RIGHT, the rating thinks well of it. That is all this direction says — it is a '
      + 'level, and it tells you nothing about which way the company is moving.',
  },
  {
    anchor: 'axis-y',
    title: 'Up and down: which way it is moving',
    body: 'A dot near the TOP means dated news and filings say the company is improving. Near the '
      + 'BOTTOM, they say it is getting worse. That is all this direction says — it is a '
      + 'direction, and it tells you nothing about whether the company is good today.',
  },
  {
    anchor: 'boundaries',
    title: 'The two dashed lines cut it into four',
    body: 'The upright line is the middle of the rating: left of it, rated below average for this '
      + 'list; right of it, above. The flat line is standing still: above it, improving; below '
      + 'it, slipping. Crossing either one changes what we call a company — no other line on the '
      + 'plot does that.',
  },
  {
    // The card the corners exist for: names like "value trap" are jargon until you can read them
    // straight off the two directions you were just shown.
    anchor: 'matrix',
    title: 'Now read the two together',
    body: 'Every corner is just one combination of those two directions. Side tells you what the '
      + 'rating thinks; height tells you what the evidence is doing. Left + top: rated low but '
      + 'improving. Right + top: rated well and improving. Right + bottom: rated well but '
      + 'slipping. Left + bottom: rated low and slipping. The next four cards are those four, one '
      + 'at a time.',
  },
  {
    anchor: 'quad-hidden',
    title: 'Left and high — rated low, but improving',
    body: 'The rating is unimpressed while the evidence says things are getting better. This is '
      + 'the corner the product exists for, and the hardest to earn: a name only gets our '
      + 'strictest label here with enough evidence, from good enough sources. Otherwise it just '
      + 'sits here as ordinary agreement.',
  },
  {
    anchor: 'quad-future',
    title: 'Right and high — rated well, and improving',
    body: 'The rating thinks well of it and the evidence agrees it is still improving. We are not '
      + 'disagreeing with anybody here, and that is a finding too: most companies are not an '
      + 'argument, and a screen that never agrees with anything is not measuring.',
  },
  {
    anchor: 'quad-overrated',
    title: 'Right and low — rated well, but slipping',
    body: 'The rating still thinks well of it while the evidence points down. This is the blind '
      + 'spot of a score that refreshes slowly: nothing in the published number can show you a '
      + 'company on the way down until its next revision.',
  },
  {
    anchor: 'quad-traps',
    title: 'Left and low — rated low, and still slipping',
    body: 'The rating is unimpressed and the evidence agrees it is getting worse. Both readings '
      + 'point the same way, downward — no disagreement to report.',
  },
  {
    // Anchored to the plot rather than to the tier control: at investor audience that control is
    // folded away, and the dimming it causes is exactly the thing a newcomer needs explained.
    anchor: 'matrix',
    title: 'The bright ones fit what you asked for',
    body: 'Solid dots match the risk setting and focus you chose; dimmed ones do not. They are '
      + 'dimmed rather than removed on purpose — you still have to be able to see the name you '
      + 'are choosing not to hold, and a filter that deletes companies is quietly making the '
      + 'decision for you.',
  },
  {
    anchor: 'matrix',
    title: 'A hollow dot means we found nothing',
    body: '“No evidence” and “the evidence says flat” both sit on the flat line and they are '
      + 'completely different claims, so a company with no dated sources at all is drawn hollow '
      + 'and counted beside the plot. An absence is a finding, not a blank.',
  },
  {
    title: 'The diagonal is the boring one',
    body: 'Bottom-left to top-right is where the rating and the evidence agree, and most companies '
      + 'live there. The two opposite corners are where they part company — that is the entire '
      + 'point of the plot, and every dot in them opens onto its sources.',
  },
]

/** The card's own footprint, so `trackAnchor` scrolls into the band above it, not under it. */
const CARD_H = 150

export default function Tutorial() {
  const { settings, setSettings } = useStore()
  const [i, setI] = useState(0)
  const stopTracking = useRef<(() => void) | null>(null)
  const deck = settings.tourDeck === 'matrix' ? MATRIX_CARDS
    : settings.audience === 'investor' && !settings.showNumbers ? INVESTOR_CARDS
    : CARDS
  const card = deck[i]

  const close = () => {
    stopTracking.current?.()
    // A named deck clears itself; the first-run one is what `tourDone` remembers.
    setSettings(settings.tourDeck ? { tourDeck: '' } : { tourDone: true })
  }
  const next = () => (i + 1 >= deck.length ? close() : setI(i + 1))

  /**
    * Skip a card whose anchor NEVER TURNS UP — and only then.
    *
    * The first version re-checked on every render with no dependency array, so any moment the
    * element was missing could push the tour forward. The board refetches (the header's "2 min
    * ago" clock) and swaps the whole dashboard for a spinner while it does, which took the
    * anchor away for longer than the timeout and auto-advanced card 2 out from under the reader.
    *
    * So: watch for up to ~600ms after the card appears, and the moment the anchor is seen, STOP
    * WATCHING for good. A card that has found its element can never be skipped by a later
    * re-render, which is the only behaviour a reader can trust.
    */
  // A named deck starts at its own first card, not wherever the last one left off.
  useEffect(() => { setI(0) }, [settings.tourDeck])

  useEffect(() => {
    if (!card.anchor) return
    // Not on screen? Ask for it. The watcher below then gives React a moment to paint before it
    // decides the card has nothing to point at.
    if (!el(card.anchor) && card.ensure) setSettings(card.ensure(settings))
    let tries = 0
    const id = window.setInterval(() => {
      if (el(card.anchor!) || ++tries >= 6) {
        window.clearInterval(id)
        if (!el(card.anchor!)) next()
      }
    }, 100)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i])

  useEffect(() => {
    let dead = false
    stopTracking.current?.()
    stopTracking.current = card.anchor
      ? trackAnchor(card.anchor, () => !dead, CARD_H)
      : null
    return () => { dead = true; stopTracking.current?.() }
  }, [i, card.anchor])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'Enter' || e.key === 'ArrowRight') next()
      else if (e.key === 'ArrowLeft' && i > 0) setI(i - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const last = i === deck.length - 1
  return (
    <>
      <Spotlight anchor={card.anchor} className="tut-ring" />
      <div className="tut-card" role="dialog" aria-label="Getting started">
        <div className="tut-head">
          <span className="tut-step">{i + 1} of {deck.length}</span>
          <span className="tut-title">{card.title}</span>
        </div>
        <p className="tut-body">{card.body}</p>
        <div className="tut-foot">
          <button className="btn tut-skip" onClick={close}>Skip the tour</button>
          <div className="tut-nav">
            {i > 0 && <button className="btn" onClick={() => setI(i - 1)}>Back</button>}
            <button className="btn btn-primary" onClick={next}>
              {last ? 'Start using it' : 'Next →'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
