/**
 * PRESENT MODE — the demo video's flow, driven live against the running application.
 *
 * The 2-minute render is a recording; this is the same route through the product with a human
 * at the clicker. Every step drives the REAL app through the store and the real DOM — there are
 * no screenshots, no canned frames and no mock state. What the room sees is the application
 * doing the thing.
 *
 * Two rules this file keeps, and they are the reason it is a data structure rather than a script:
 *
 *  1. **Every step is ABSOLUTE, never a toggle.** `tier: 'balanced'`, not "switch tier". A
 *     presenter who steps backwards, or jumps with the number keys, has to land on exactly the
 *     state that step describes — a toggle would invert and the board would contradict the line
 *     being said over it.
 *  2. **A step that needs the model is `live: true` and drives nothing.** The interrogation is a
 *     real DeepSeek call over the network. Auto-firing it on a stage, behind conference wifi,
 *     with a countdown running, is how a demo dies. Those steps set the scene and hand over.
 */
import type { Settings } from '../../store'

/**
 * The subject, per universe. Both are the same argument: a Hidden Winner with a thick evidence
 * trail AND at least one sub-signal pointing the other way, because "we show you the one that
 * disagrees" is a claim the tour has to be able to point at.
 *
 *   live  RHB Bank   — 14 signals, disagreement +0.80, controversy dissenting
 *   demo  SatBank    — 11 signals, disagreement +0.69, emissions dissenting
 *
 * The FICTIONAL demo set stays labelled fictional throughout: the deep dive carries its own
 * "Illustrative sample — placeholder data" badge and present mode does nothing to hide it.
 * Matching the live set means exercising the same PATHS, never dressing invented numbers up as
 * real ones.
 */
export const SUBJECTS = { live: 'KLSE:RHBBANK', demo: 'IDX:SATB' } as const

/**
 * BEFORE PRESENTING — warm the subject, or chapter 05 waits 40-70s for a cold Compete.
 *
 *   demo   python -m scripts.demo_reset            (pins and warms the demo subject)
 *   live   curl -X POST localhost:8000/api/monitor -d '{"ticker":"KLSE:RHBBANK","demo":false}'
 *          curl -X POST localhost:8000/api/stage2/quick -d '{"ticker":"KLSE:RHBBANK","use_rag":true}'
 *
 * `demo_reset` CLEARS the watchlist to get a deterministic state, which drops the live
 * subject's warm answer too. Present whichever universe you warmed last, or warm both.
 */

export const subjectFor = (demo: boolean) => demo ? SUBJECTS.demo : SUBJECTS.live

/**
 * What a cue line is allowed to know. Every figure below is READ OFF THE RUN THAT IS LOADED,
 * never typed into this file.
 *
 * The earlier draft hard-coded "+0.80", "nine governance signals" and "fourteen signals" from
 * the live basket. That is the staleness trap this repo already learned once with N/M/K: a
 * number written into prose cannot follow the run it came from, and a cue that contradicts the
 * panel behind it is worse on stage than no cue at all. It also made the tour simply wrong in
 * the demo universe, where every one of those figures differs.
 */
export interface Cue {
  demo: boolean
  universe: number
  pipeline: number
  company: string
  disagreement: number
  signals: number
  /** Signals whose removal alone would move the label — 0 means the verdict is corroborated. */
  flips: number
  /** How many of the heaviest would ALL have to go before it moved. null = not even all of them. */
  flipSet: number | null
  /** The most negative sub-signal — the one that disagrees. */
  dissent: { label: string; value: number } | null
  /** A pillar whose own signals disagree with each other. */
  split: { pillar: string; total: number; up: number; down: number } | null
}

const PILLAR = { E: 'environment', S: 'social', G: 'governance', DIGITAL: 'digital' } as const
const pillarName = (k: string) => (PILLAR as Record<string, string>)[k] ?? k.toLowerCase()
const signed = (n: number) => `${n >= 0 ? '+' : '\u2212'}${Math.abs(n).toFixed(2)}`

export interface Driver {
  /** The subject for the universe currently loaded — demo or live. */
  subject: string
  set: (p: Partial<Settings>) => void
  dashboard: () => void
  deep: (ticker: string, mode: 'compete' | 'interrogate') => Promise<void>
  evidence: (ticker: string) => void
  focus: (ticker: string) => void
  /** Open a deep dive from a clean mount — see the note on the implementation. */
  reopen: (ticker: string, mode: 'compete' | 'interrogate') => Promise<void>
  /** Synthesise a real click on a `data-tour` element — the same event a mouse would make. */
  click: (anchor: string) => boolean
}

/**
 * Which screen a step needs. Declared per step, not just on the step that navigates, because
 * the progress ticks let a presenter JUMP — and a jump straight to chapter 07 would otherwise
 * land on whatever was on screen, since the step that opened the evidence view never ran.
 * Establishing is skipped when the view is already the right one, so walking 17 -> 18 -> 19
 * does not remount the panel under the presenter.
 */
export type ViewSpec = 'board' | 'interrogate' | 'compete' | 'evidence'

export interface Step {
  chapter: string
  /** The screen this step is talking about. Established on entry, from any other step. */
  view: ViewSpec
  /** The line. A cue for the presenter, and a caption the room can read. */
  say: string | ((c: Cue) => string)
  /** `data-tour` value to scroll to and ring. Omitted = leave the viewport alone. */
  anchor?: string
  /** Drive the app into the state this step describes. Absolute, never relative. */
  act?: (d: Driver) => void | Promise<void>
  /**
   * This step calls the model over the network. The tour sets the scene and stops; the presenter
   * drives it. Marked on screen so nobody clicks past waiting for something to happen.
   */
  live?: boolean
  /** Extra ms to let the app settle before scrolling — a view change needs a paint. */
  settle?: number
}

export const TOUR: Step[] = [
  // ── 01 · the board ─────────────────────────────────────────────────────────
  {
    chapter: '01 · The board',
    view: 'board',
    say: 'Monday morning. An ESG analyst opens the Radar.',
    anchor: 'matrix',
    settle: 450,
    act: d => {
      // The full opening state in one call, so this step is a safe place to restart from.
      // `demo` is deliberately absent. Which universe to present is the presenter's call,
      // made before they start; the tour adapts its subject and every figure to whichever is
      // loaded rather than yanking the board out from under them.
      d.set({
        level: 3, tab: 'board', tier: 'all', horizon: 'long',
        pipelineOnly: false, greenFocus: false, filters: { country: 'All', sector: 'All' },
      })
      d.dashboard()
    },
  },
  {
    chapter: '01 · The board',
    view: 'board',
    say: c => `${c.universe} ASEAN companies, read twice overnight — once from dated evidence, `
      + `once from the rating the market already uses.`,
    anchor: 'matrix',
    act: d => d.set({ tier: 'all', pipelineOnly: false }),
  },
  {
    chapter: '01 · The board',
    view: 'board',
    say: 'The gap between the two is the product. Across, what the incumbent rating thinks. '
      + 'Up, what our evidence is doing. Four quadrants, and the argument is the diagonal.',
    anchor: 'matrix',
    act: d => d.set({ tier: 'all', pipelineOnly: false }),
  },

  // ── 02 · the mandate ───────────────────────────────────────────────────────
  {
    chapter: '02 · The mandate',
    view: 'board',
    say: 'Her mandate re-segments the board. Conservative — and the board answers to it.',
    anchor: 'tiers',
    act: d => d.set({ tier: 'conservative', pipelineOnly: false }),
  },
  {
    chapter: '02 · The mandate',
    view: 'board',
    say: 'Balanced. The same evidence, a different fund, a different shortlist.',
    anchor: 'tiers',
    act: d => d.set({ tier: 'balanced', pipelineOnly: false }),
  },
  {
    chapter: '02 · The mandate',
    view: 'board',
    say: 'Aggressive.',
    anchor: 'tiers',
    act: d => d.set({ tier: 'aggressive', pipelineOnly: false }),
  },
  {
    chapter: '02 · The mandate',
    view: 'board',
    say: 'And nothing is hidden. What falls outside the mandate is dimmed, never dropped — '
      + 'you still have to be able to see the name you are choosing not to hold.',
    anchor: 'matrix',
    act: d => d.set({ tier: 'all', pipelineOnly: false }),
  },

  // ── 03 · the call list ─────────────────────────────────────────────────────
  {
    chapter: '03 · The call list',
    view: 'board',
    say: 'One filter turns the board into a call list.',
    anchor: 'pipeline',
    act: d => d.set({ tier: 'all', pipelineOnly: true }),
  },
  {
    chapter: '03 · The call list',
    view: 'board',
    say: c => `${c.pipeline} names — improving on evidence, financially sound, and not yet `
      + `green-bond issuers. Tomorrow’s issuers, not today’s league table.`,
    anchor: 'nmk',
    act: d => d.set({ tier: 'all', pipelineOnly: true }),
  },

  // ── 04 · it asks before it answers ─────────────────────────────────────────
  {
    chapter: '04 · It asks before it answers',
    view: 'interrogate',
    say: 'Then the part that isn’t a dashboard. It asks.',
    anchor: 'relay',
    settle: 900,
    act: d => d.set({ pipelineOnly: false }),
  },
  {
    chapter: '04 · It asks before it answers',
    view: 'interrogate',
    say: 'Four ESG-native axes — materiality, time horizon, mandate, blind spot. One question '
      + 'each, and it never answers the ESG question itself.',
    anchor: 'axes',
  },
  {
    chapter: '04 · It asks before it answers',
    view: 'interrogate',
    say: 'Ask it something loose and it pushes back — and tells you why it is asking.',
    anchor: 'interrogate',
    live: true,
  },
  {
    chapter: '04 · It asks before it answers',
    view: 'interrogate',
    say: 'What comes out is a sharper question: the baton the next stage answers.',
    anchor: 'interrogate',
    live: true,
  },

  // ── 05 · the case ──────────────────────────────────────────────────────────
  {
    chapter: '05 · The case',
    view: 'compete',
    say: c => `${c.company}. The competing answer — the verdict, and where we disagree `
      + `with the rating.`,
    anchor: 'verdict',
    settle: 900,
  },
  {
    chapter: '05 · The case',
    view: 'compete',
    say: c => `What the rating sees, beside what we see. ${signed(c.disagreement)} — our `
      + `evidence rank, minus the rating’s. Not a score. A disagreement, with a sign.`,
    anchor: 'market',
  },
  {
    chapter: '05 · The case',
    view: 'compete',
    say: c => c.split
      ? `And underneath, the evidence the rating cannot see: ${c.split.total} `
        + `${pillarName(c.split.pillar)} signals — ${c.split.up} up, ${c.split.down} down. `
        + `Contested, not absent.`
      : 'And underneath, the evidence the rating cannot see — momentum by pillar, the digital '
        + 'signal, and the near-term catalyst no score can price yet.',
    anchor: 'layerb',
  },

  // ── 06 · the evidence trail ────────────────────────────────────────────────
  {
    chapter: '06 · The evidence trail',
    view: 'evidence',
    say: c => c.dissent
      ? `Every number opens. Where the score comes from — each sub-signal, and the one that `
        + `disagrees: ${c.dissent.label}, at ${signed(c.dissent.value)}.`
      : 'Every number opens. Where the score comes from — every sub-signal behind the number, '
        + 'and what each one is worth.',
    anchor: 'score-source',
    settle: 700,
  },
  {
    chapter: '06 · The evidence trail',
    view: 'evidence',
    say: c => c.flips === 0 && c.flipSet
      ? `Take one signal away — none of the ${c.signals} moves the label on its own. `
        + `The ${c.flipSet} heaviest would all have to go. Corroborated, not carried.`
      : `Take one signal away — ${c.flips} of ${c.signals} would move the label alone. `
        + `That is what this verdict is standing on.`,
    anchor: 'sensitivity',
  },
  {
    chapter: '06 · The evidence trail',
    view: 'evidence',
    say: c => `And the trail itself: ${c.signals} signals, each one dated and sourced. `
      + `The excerpt is the source’s own words — nothing here is generated.`,
    anchor: 'trail',
  },

  // ── 07 · verify ────────────────────────────────────────────────────────────
  {
    chapter: '07 · Verify',
    view: 'evidence',
    say: 'Then she verifies.',
    anchor: 'verify-block',
  },
  {
    chapter: '07 · Verify',
    view: 'evidence',
    say: 'Every hash recomputes, walks the Merkle path, and matches the root anchored on a '
      + 'public chain. Proof on-chain — never the data.',
    anchor: 'verify-block',
    settle: 400,
    act: d => { d.click('verify') },
  },
  {
    chapter: '07 · Verify',
    view: 'evidence',
    say: 'Change one character on purpose, and it breaks.',
    anchor: 'verify-block',
    settle: 400,
    act: d => { d.click('tamper') },
  },
  {
    chapter: '07 · Verify',
    view: 'evidence',
    say: 'One analyst. One Monday. Every number checkable.',
    anchor: 'verify-block',
  },
]
