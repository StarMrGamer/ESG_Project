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
 *
 * NO CUE LINE ON SCREEN (changed 2026-08-28). Each step used to carry a `say` string — often a
 * function of the loaded run — which present mode printed under the board. It is gone: the room
 * should be watching the app and listening to a person, not reading a caption of what they are
 * about to hear. What remains is the highlight and the state change.
 *
 * `note` replaces it as a PRESENTER-ONLY tooltip on the progress ticks, and it deliberately
 * carries **no figures**. A number typed into this file cannot follow the run it came from —
 * that is the staleness trap this repo has already been bitten by twice — and the panel being
 * highlighted is showing the real one anyway.
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
  /** Presenter-facing only — the tick's tooltip. Never rendered to the room, never a figure. */
  note?: string
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
  /** The closing card of a track that consolidates what it walked. See `recap.ts`. */
  summary?: boolean
}

/**
 * A TRACK is a named walk. Present mode is the driver; what it drives is data.
 *
 * Two exist: `PITCH` argues the product to a room, `RECAP` reviews the run that is loaded and
 * hands you the consolidated figures at the end. They share every mechanism — the absolute-state
 * rule, the anchors, the ring, the keys, interact mode — because the difference between "show a
 * stranger why this matters" and "tell me what this run says" is a list of steps, not an engine.
 */
export interface Track {
  key: 'pitch' | 'recap'
  label: string
  /** The subject a track walks. 'fixed' is the rehearsed one; 'focused' is whatever is on screen. */
  subject: 'fixed' | 'focused'
  steps: Step[]
}

export const TOUR: Step[] = [
  // ── 01 · the board ─────────────────────────────────────────────────────────
  {
    chapter: '01 · The board',
    view: 'board',
    note: 'Every name read twice — dated evidence up, the incumbent rating across. The gap is '
      + 'the product, and the argument is the diagonal.',
    anchor: 'matrix',
    settle: 450,
    act: d => {
      // The full opening state in one call, so this step is a safe place to restart from.
      // `demo` is deliberately absent. Which universe to present is the presenter's call,
      // made before they start; the tour adapts its subject to whichever is loaded rather than
      // yanking the board out from under them.
      d.set({
        level: 3, tab: 'board', tier: 'all', horizon: 'long',
        pipelineOnly: false, greenFocus: false, filters: { country: 'All', sector: 'All' },
      })
      d.dashboard()
    },
  },

  // ── 02 · the mandate ───────────────────────────────────────────────────────
  {
    chapter: '02 · The mandate',
    view: 'board',
    note: 'Conservative. The mandate re-segments the same evidence — and what falls outside it '
      + 'dims rather than disappears.',
    anchor: 'tiers',
    act: d => d.set({ tier: 'conservative', pipelineOnly: false }),
  },
  {
    chapter: '02 · The mandate',
    view: 'board',
    note: 'Aggressive. Same run, different fund, different shortlist.',
    anchor: 'tiers',
    act: d => d.set({ tier: 'aggressive', pipelineOnly: false }),
  },

  // ── 03 · the call list ─────────────────────────────────────────────────────
  {
    chapter: '03 · The call list',
    view: 'board',
    note: 'One filter turns the board into a call list: improving on evidence, financially '
      + 'sound, not yet an issuer. Tomorrow’s issuers, not today’s league table.',
    anchor: 'nmk',
    act: d => d.set({ tier: 'all', pipelineOnly: true }),
  },

  // ── 04 · it asks before it answers ─────────────────────────────────────────
  {
    chapter: '04 · It asks first',
    view: 'interrogate',
    note: 'The part that is not a dashboard. Four ESG-native axes, one question each — and it '
      + 'never answers the ESG question itself.',
    anchor: 'relay',
    settle: 900,
    act: d => d.set({ pipelineOnly: false }),
  },
  {
    chapter: '04 · It asks first',
    view: 'interrogate',
    note: 'Ask it something loose. It pushes back, says why, and hands the next stage a sharper '
      + 'question. LIVE — you drive this one.',
    anchor: 'interrogate',
    live: true,
  },

  // ── 05 · the case ──────────────────────────────────────────────────────────
  {
    chapter: '05 · The case',
    view: 'compete',
    note: 'The competing answer: the verdict, and where it disagrees with the rating.',
    anchor: 'verdict',
    settle: 900,
  },
  {
    chapter: '05 · The case',
    view: 'compete',
    note: 'What the rating sees, beside what we see. Our evidence rank minus the rating’s — not '
      + 'a score, a disagreement with a sign.',
    anchor: 'market',
  },

  // ── 06 · the evidence trail ────────────────────────────────────────────────
  {
    chapter: '06 · The trail',
    view: 'evidence',
    note: 'Take one signal away and re-score: which removals move the label, and which do not. '
      + 'Corroborated, or carried.',
    anchor: 'sensitivity',
    settle: 700,
  },
  {
    chapter: '06 · The trail',
    view: 'evidence',
    note: 'The trail itself — every signal dated and sourced, the excerpt in the source’s own '
      + 'words. Nothing here is generated.',
    anchor: 'trail',
  },

  // ── 07 · verify ────────────────────────────────────────────────────────────
  {
    chapter: '07 · Verify',
    view: 'evidence',
    note: 'Recompute every hash, walk the Merkle path, compare with the root anchored on a '
      + 'public chain. Proof on-chain — never the data.',
    anchor: 'verify-block',
    settle: 400,
    act: d => { d.click('verify') },
  },
  {
    chapter: '07 · Verify',
    view: 'evidence',
    note: 'Change one character on purpose, and it breaks. That failure is the feature.',
    anchor: 'verify-block',
    settle: 400,
    act: d => { d.click('tamper') },
  },
]

export const PITCH: Track = {
  key: 'pitch',
  label: 'Present mode',
  // The rehearsed subject, not whatever happens to be focused: this walk is a claim about a
  // specific company with a thick trail and a dissenting signal, and it has to land the same way
  // every time it is given.
  subject: 'fixed',
  steps: TOUR,
}
