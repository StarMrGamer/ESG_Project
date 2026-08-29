import type { Track } from './tour'

/**
 * WHY IT MATTERS — the same clicker, arranged as three fears and their answers.
 *
 * `PITCH` explains what the product is, in the order the work happens. This one is arranged the
 * way a room actually listens: it names a worry a private investor already has, and then the app
 * does the thing that answers it. Nobody has to be told the answer matters, because the fear was
 * stated first and the board moves in front of them.
 *
 *   01  "I'm afraid of losing money."          -> the risk tiers, and the board re-segmenting
 *   02  "I don't know where to start."         -> 52 names as four corners, not a scroll
 *   03  "I'd never have seen it coming."       -> dated sources, and momentum against a stale level
 *   04  "You don't have to imagine it."        -> hand over to the live demo
 *
 * IT SETS `audience: 'analyst'`, and that is not a detail. The tier control and the run
 * provenance are FOLDED AWAY in the investor view, so a walk that stops on the tiers would ring
 * an element with no width and appear broken. Every step is absolute state, so establishing it in
 * step 1 is enough — a presenter who jumps backwards with the ticks still lands on a board that
 * matches the line being spoken over it.
 *
 * NO CUE ON SCREEN, like the other two tracks. The `note` on each step is the presenter's own
 * line, shown only as the tick's tooltip: the room should be watching the board and listening to
 * a person, not reading a caption of what they are about to hear.
 */
export const FEARS: Track = {
  key: 'fears',
  label: 'Why it matters',
  // The rehearsed subject, not whatever is focused: chapter 03 is a claim about a company with a
  // thick dated trail, and it has to land the same way every time it is given.
  subject: 'fixed',
  steps: [
    // ── 01 · "I'm afraid of losing money" ──────────────────────────────────
    {
      chapter: '01 · Afraid of losing money',
      view: 'board',
      note: 'Start with the fear, not the feature. You are afraid of losing money — so the risk '
        + 'appetite is yours to set, in three tiers, and the board answers to whichever one you '
        + 'pick.',
      anchor: 'tiers',
      settle: 450,
      act: d => {
        // The whole opening state in one call, so this step is a safe place to restart from.
        // `demo` is deliberately absent: which universe to present is the presenter's call.
        d.set({
          level: 3, tab: 'board', audience: 'analyst', showNumbers: false,
          tier: 'conservative', horizon: 'long', pipelineOnly: false, greenFocus: false,
          filters: { country: 'All', sector: 'All' },
        })
        d.dashboard()
      },
    },
    {
      chapter: '01 · Afraid of losing money',
      view: 'board',
      note: 'Conservative: only labelled, reviewed, profitable issuers, and only where the '
        + 'evidence is strong. Watch how much of the board that leaves.',
      anchor: 'matrix',
      act: d => d.set({ tier: 'conservative', pipelineOnly: false }),
    },
    {
      chapter: '01 · Afraid of losing money',
      view: 'board',
      note: 'Balanced — and now aggressive: thinner evidence, earlier. Same run, same evidence, a '
        + 'different appetite. Nothing was re-scored; the board re-segmented.',
      anchor: 'matrix',
      act: d => d.set({ tier: 'aggressive', pipelineOnly: false }),
    },
    {
      chapter: '01 · Afraid of losing money',
      view: 'board',
      note: 'And what falls outside your tier DIMS rather than disappearing. You still have to be '
        + 'able to see the name you are choosing not to hold — a filter that deletes companies is '
        + 'making the decision for you.',
      anchor: 'matrix',
      act: d => d.set({ tier: 'balanced', pipelineOnly: false }),
    },

    // ── 02 · "I don't know where to start" ─────────────────────────────────
    {
      chapter: '02 · Not knowing where to start',
      view: 'board',
      note: 'Second fear: you do not know where to start. You are not scrolling hundreds of '
        + 'names here — every company we track is one dot, placed by two readings at once.',
      anchor: 'matrix',
      act: d => d.set({ tier: 'all', pipelineOnly: false }),
    },
    {
      chapter: '02 · Not knowing where to start',
      view: 'board',
      note: 'Side to side is what the published rating thinks. Up and down is what dated evidence '
        + 'says. Four corners, and they are just those two directions combined.',
      anchor: 'axis-x',
      act: d => d.set({ tier: 'all', pipelineOnly: false }),
    },
    {
      chapter: '02 · Not knowing where to start',
      view: 'board',
      note: 'This corner is the one the product exists for: rated low, but improving. The rating '
        + 'has not caught up with the evidence yet — and that is a place to start looking.',
      anchor: 'quad-hidden',
      act: d => d.set({ tier: 'all', pipelineOnly: false }),
    },

    // ── 03 · "I'd never have seen it coming" ───────────────────────────────
    //
    // Deliberately EVIDENCE, not the Compete answer. The verdict panel needs a Stage-2 call, and
    // a cold one is 40-70 seconds — which on a stage is the demo dying in front of the room. The
    // trail and the sensitivity report are pure engine reads: instant, offline, and they make the
    // same point harder, because they are the sources rather than a paragraph about them.
    {
      chapter: '03 · Never seeing it coming',
      view: 'board',
      note: 'Third fear: by the time you hear about it, it is in the headline and in the price. '
        + 'So watch one company — the dashed ring is no change, which is what a rating that has '
        + 'not been refreshed quietly assumes. The filled shape is what today’s evidence says.',
      anchor: 'hub',
      settle: 450,
      act: d => {
        d.set({ tier: 'all', pipelineOnly: false })
        d.focus(d.subject)
        d.dashboard()
      },
    },
    {
      chapter: '03 · Never seeing it coming',
      view: 'evidence',
      note: 'This is what the model reads: news, filings, exchange notices — every one dated and '
        + 'sourced, in the source’s own words. A rating refreshes on its own cycle; this moves '
        + 'when the evidence moves.',
      anchor: 'trail',
      settle: 700,
    },
    {
      chapter: '03 · Never seeing it coming',
      view: 'evidence',
      note: 'And we can show you what the verdict is standing on: pull each source out in turn '
        + 'and re-score. That is the question a published rating structurally cannot answer.',
      anchor: 'sensitivity',
    },

    // ── 04 · the handover ──────────────────────────────────────────────────
    {
      chapter: '04 · See it for yourself',
      view: 'board',
      note: 'You do not have to imagine what this would be like — everything you just watched was '
        + 'the running app. Ask it something now, and it will answer from the same evidence.',
      anchor: 'assistant',
      settle: 450,
      act: d => {
        d.set({ tier: 'all', pipelineOnly: false, rightOpen: true })
        d.dashboard()
      },
    },
  ],
}
