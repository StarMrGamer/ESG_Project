import type { Track } from './tour'

/**
 * SOLVING FOR THE 10% — the walk an ESG analyst actually does, in the order they do it.
 *
 * `PITCH` explains the product, `FEARS` answers a private investor's worries, `RECAP` reads the
 * loaded run back. This one has a different job: it is the analyst's WORKFLOW, and it is aimed at
 * the one question a quant in the room asks before any other —
 *
 *     "A factor model already explains most of the cross-section. What is left for you to do?"
 *
 * The track's shape is that question taken seriously rather than dodged: check what the incumbent
 * says, form your own view from dated evidence, ask what the market has already done about it,
 * then TEST whether your view survives a factor control — and finish on what would change it.
 *
 * STEP 04 IS DELIBERATELY NOT FIRST. An analyst who opens on the residual test is showing a
 * statistic; one who opens on a stale rating, builds the disagreement in front of you, and only
 * THEN asks whether it survives a control, is showing a method. The second is what this is for.
 *
 * WHAT THE NARRATION MAY NOT SAY, and this is the load-bearing rule of the track: **it never
 * claims the 10% is solved.** It is not. An earlier single-split read suggested the ESG block
 * explained part of the residual; a stricter protocol — hyperparameters chosen on a validation
 * block, a holdout scored exactly once — refused it. Chapter 04 therefore tells the story of the
 * REFUSAL, because that is both what happened and the stronger thing to show: validation offered
 * +7.6% of the residual, past the target that had been set, and the holdout returned -1.8%.
 * A tool whose whole argument is that confident unchecked numbers are dangerous has to be
 * willing to show one of its own being caught. See `residual.py` and `ResidualPanel.tsx`.
 *
 * IT IS GROUPED BY VIEW, NOT BY THEME. The rating and the provenance both live in the evidence
 * panel and the rest lives on the board, so the walk goes evidence -> board -> evidence rather
 * than bouncing per step: `establish` remounts a view on entry, and a track that alternates
 * makes the app flicker under the presenter for no argumentative gain.
 *
 * IT PINS ITS OWN PANEL. `residual` is a level-3 module, and step 04 rings `data-tour="residual"`
 * — so the opening step puts it on screen via `extras` rather than assuming a reader left it
 * there, and pins it EARLY so it has mounted and measured by the time the walk arrives. Same
 * reason `Card.ensure` exists in the tutorial: ringing an element that was never rendered looks
 * broken at exactly the moment it is explaining something.
 *
 * NO CUE ON SCREEN, like the other three tracks. Each `note` is the presenter's own line and
 * shows only as the tick's tooltip. It carries NO figures: a number typed into this file cannot
 * follow the run it came from, and the panel being rung is showing the real one anyway.
 */
export const ANALYST: Track = {
  key: 'analyst',
  label: 'Solving for the 10%',
  // The rehearsed subject. Chapters 02 and 05 are claims about a company with a thick dated trail
  // and a boundary close enough to be worth showing; they must land identically every time this
  // is given or recorded.
  subject: 'fixed',
  steps: [
    // ── 01 · what the incumbent sees ───────────────────────────────────────
    {
      chapter: '01 · Where the number comes from',
      view: 'evidence',
      // The note describes what this anchor ACTUALLY rings: the per-pillar decomposition, the
      // arithmetic under it, and the baseline line at its foot. An earlier draft called the whole
      // block "the incumbent view", which is only the last line of it — and a narration that
      // does not match the panel it points at is the one thing a live demo cannot survive.
      note: 'Start with provenance, because everything after this depends on it. Each pillar '
        + 'broken into the dated signals that moved it, the arithmetic spelled out underneath — '
        + 'and at the foot, the baseline this company is measured against: a stored score, and '
        + 'the percentile it puts them at. That baseline is the incumbent view. It is one number, '
        + 'carried forward, and it has no opinion about anything above it.',
      anchor: 'score-source',
      settle: 450,
      act: async d => {
        // The full opening state in one call, so this is a safe place to restart or jump back to.
        // `demo` is absent on purpose: which universe to present is the presenter's call, made
        // before they start. `residual` is pinned HERE, three chapters before it is rung.
        d.set({
          level: 3, tab: 'board', tier: 'all', horizon: 'long',
          pipelineOnly: false, greenFocus: false,
          filters: { country: 'All', sector: 'All' },
          extras: ['matrix', 'residual', 'roadmap', 'rails'],
        })
        d.focus(d.subject)
        d.evidence(d.subject)
      },
    },

    // ── 02 · what our evidence sees ────────────────────────────────────────
    {
      chapter: '02 · What the evidence sees',
      view: 'board',
      note: 'Now the same company read a second way. Dated, sourced events, each routed to a '
        + 'pillar by rule. The dashed ring is zero momentum — which is exactly what a static '
        + 'rating implicitly assumes. The gap between that ring and the filled shape IS the '
        + 'disagreement, and it is the whole product.',
      anchor: 'hub',
      settle: 450,
      act: d => { d.dashboard(); d.focus(d.subject) },
    },
    {
      chapter: '02 · What the evidence sees',
      view: 'board',
      // The axes are stated as the plot actually draws them. The rating percentile still drives
      // every quadrant LABEL in the legend, but it was dropped from the DRAWING — so a line
      // about "the rating across" would be contradicted by the axis caption underneath it.
      note: 'And it is not one company. Every name plotted twice: what the market has already '
        + 'done across, what our evidence says up. The labels beside it are the rating '
        + 'disagreement — same run, read against the incumbent rather than against the price.',
      anchor: 'matrix',
    },

    // ── 03 · what the market already did ───────────────────────────────────
    {
      chapter: '03 · What the market already did',
      view: 'board',
      note: 'The fair question straight back: has the price already run on exactly the '
        + 'improvement we are pointing at? So the twelve-minus-one momentum factor sits BESIDE '
        + 'the evidence read and never inside it. The moment those are folded together, the '
        + 'disagreement number stops meaning anything anybody can state out loud.',
      anchor: 'dual-momentum',
    },

    // ── 04 · the test ──────────────────────────────────────────────────────
    {
      chapter: '04 · Solving for the 10%',
      view: 'board',
      // Leads with the honest read, in the order the panel itself uses: stage 1 failed, so there
      // is no established "90%" — said BEFORE anything about what our own block did.
      note: 'Here is that quant question, taken seriously. We tried to predict the residual — and '
        + 'this is what happened. On the validation block the model was worth seven-point-six per '
        + 'cent of it. Past the bar. Then the holdout, scored once: minus one-point-eight.',
      anchor: 'residual',
      settle: 500,
      act: d => d.set({ level: 3, tab: 'board',
        extras: ['matrix', 'residual', 'roadmap', 'rails'] }),
    },
    {
      chapter: '04 · Solving for the 10%',
      view: 'board',
      note: 'Forty-eight configurations searched against one evaluation set, and it picked the '
        + 'least-regularised one of them. Without that third split, seven-point-six is the number '
        + 'that ships. So the answer is no — and the reason I can tell you it is no is that we '
        + 'built the thing that catches it. Everything below is the earlier, weaker test, kept on '
        + 'screen and marked as superseded rather than deleted.',
      anchor: 'residual',
    },

    // ── 05 · what would change it ──────────────────────────────────────────
    {
      chapter: '05 · What would change it',
      view: 'evidence',
      note: 'An analyst’s last question is never "what does it say", it is "what would move it". '
        + 'Every signal removed in turn, which removals change the label, and the signed distance '
        + 'to every boundary. No clock and no model in here — it replays exactly with the run it '
        + 'describes.',
      anchor: 'sensitivity',
      settle: 400,
      act: async d => { d.evidence(d.subject) },
    },
    {
      chapter: '05 · What would change it',
      view: 'evidence',
      note: 'And underneath, the sources themselves — dated, linked, and capped at half '
        + 'confidence wherever the company published them about itself. That cap is why no volume '
        + 'of press releases can manufacture a Hidden Winner, and it is what makes this an '
        + 'argument rather than a scrape.',
      anchor: 'trail',
    },

    // ── 06 · what would make it work ───────────────────────────────────────
    // The walk has to end somewhere forward-looking, or it closes on a limitation. This is the
    // one place the product answers "so what would fix it" with a number rather than a promise —
    // and it is the same 11 -> 20 -> 22 the deck's plan slide is built on, so the video and the
    // deck cannot drift into telling different stories.
    {
      chapter: '06 · What would make it work',
      view: 'board',
      note: 'And the honest close: what would actually fix this. Eighty-two per cent of what we '
        + 'gather is companies talking about themselves, capped at half confidence by rule. So we '
        + 'asked the engine — what if the same facts arrived through an exchange filing instead? '
        + 'Eleven companies we can act on becomes twenty. Add the regulator feeds and it is '
        + 'twenty-two. Same evidence, same companies, different source. That is a data contract, '
        + 'not a research project.',
      anchor: 'roadmap',
      settle: 500,
      act: async d => {
        d.dashboard()
        d.set({ level: 3, tab: 'board', extras: ['matrix', 'residual', 'roadmap', 'rails'] })
      },
    },
  ],
}
