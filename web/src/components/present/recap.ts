import { api } from '../../api'
import type { Board, HorizonKey, SensitivityPayload } from '../../types'
import type { Track } from './tour'

/**
 * RECAP — the same clicker, pointed at the run you are actually looking at.
 *
 * Present mode argues the product to a stranger. This reviews the run in front of you and then
 * CONSOLIDATES it: six stops — the run, the pipeline, the focused company's verdict, what would
 * change that verdict, the receipt — and a closing card that gathers every figure it passed into
 * one block you can copy into a note, a hand-off or a slide.
 *
 * Three rules it inherits, and one of its own.
 *
 * Inherited: every step is absolute state, a step points at a real element, and nothing is
 * narrated on screen. Its own rule is the one that makes the card worth having:
 *
 *   **EVERY FIGURE IS READ OFF THE LOADED RUN, AT THE MOMENT YOU ASK.** Nothing here is typed
 *   in, cached from an earlier run, or carried between universes. The run id is stamped on the
 *   card and on the copied text, because a consolidated summary with no run id is exactly the
 *   stale-figure trap this repo has been bitten by twice — a number that outlives the run it
 *   came from and turns up in a document three days later.
 *
 * The subject is `focused`, not the rehearsed pitch name: a recap of the run is a recap of the
 * company you are on. With nothing focused it falls back to the track's fixed subject, so the
 * walk still has something to open.
 */

export interface RecapFacts {
  demo: boolean
  runId: string
  asOf: string
  halfLifeDays: number
  horizon: HorizonKey
  universe: number
  shown: number
  labelCounts: Record<string, number>
  labelNames: Record<string, string>
  nmk: { N: number; M: number; K: number }
  anchor: { status: string; chain: string; leaves: number } | null
  harvest: { events: number; companies: number } | null
  company: {
    name: string
    ticker: string
    label: string
    disagreement: number
    confidence: number
    signals: number
    ratingPct: number
    evidencePct: number
    notch: string
    /** strong | adequate | weak | unknown — `unknown` is NOT a failure, and never rendered as one. */
    financial: string
    loadBearing: number | null
    flipSet: number | null
    watchOuts: string[]
  } | null
}

const pct = (n: number) => `${Math.round(n * 100)}`
const signed = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}`

/**
 * Assemble the card from the board that is already loaded plus one extra call.
 *
 * The board payload carries the run, the counts, N/M/K and the focused company's record and
 * case, so the only thing worth a round trip is the sensitivity report — which is the one figure
 * a reader cannot get by looking at the screen behind the card.
 */
export async function buildRecap(board: Board | null, ticker: string,
                                 demo: boolean, horizon: HorizonKey): Promise<RecapFacts | null> {
  if (!board?.engine) return null
  const e = board.engine
  const rec = e.records?.[ticker] ?? null      // keyed by company_id, not a list

  /**
   * ONE TICKER DECIDES EVERYTHING BELOW.
   *
   * The first cut read the record by `ticker` and the NAME and the case off `board.focused`,
   * which are not the same company whenever the walk falls back to its default subject: it
   * printed "KLCC Towers" over SatBank's disagreement, confidence and signal count. A wrong
   * company is worse than no company — the exact failure `lseg.py` already has three guards
   * against — and it looks completely normal on screen, which is what makes it dangerous.
   *
   * So the focused payload is used only when it IS this ticker; otherwise the name comes from
   * the constituent list and the case is dropped rather than borrowed.
   */
  const focused = board.focused
  const focusedTicker = (focused?.constituent as { ticker?: string } | undefined)?.ticker
  const isFocused = !!focusedTicker && focusedTicker === ticker
  const kase = isFocused ? focused?.case ?? null : null
  const name = (isFocused ? focused?.constituent.company : undefined)
    ?? board.constituents?.find(c => c.ticker === ticker)?.company
    ?? ticker

  let sens: SensitivityPayload | null = null
  if (rec) sens = await api.sensitivity(ticker, demo, horizon).catch(() => null)

  // The anchor lives on the evidence payload, not the board. Best-effort: a run with no chain
  // reachable is `anchor_pending`, which is a finding to report rather than a gap to hide.
  let anchor: RecapFacts['anchor'] = null
  if (rec) {
    const ev = await api.evidence(ticker, demo, horizon).catch(() => null)
    if (ev?.anchor) {
      anchor = { status: ev.anchor.status, chain: ev.anchor.chain, leaves: ev.anchor.leaf_count }
    }
  }

  return {
    demo,
    runId: e.run_id,
    asOf: e.as_of,
    halfLifeDays: e.half_life_days,
    horizon,
    universe: e.nmk?.universe_size ?? board.counts.total,
    shown: board.counts.showing,
    labelCounts: e.label_counts ?? {},
    labelNames: e.labels ?? {},
    nmk: { N: e.nmk?.N ?? 0, M: e.nmk?.M ?? 0, K: e.nmk?.K ?? 0 },
    anchor,
    harvest: e.harvest?.events ? { events: e.harvest.events, companies: e.harvest.companies } : null,
    company: rec ? {
      name,
      ticker,
      label: e.labels?.[rec.label] ?? rec.label_display ?? rec.label,
      disagreement: rec.disagreement,
      confidence: rec.composite_confidence,
      signals: rec.signal_count,
      ratingPct: rec.lseg_percentile,
      evidencePct: rec.momentum_percentile,
      notch: rec.incumbent_notch || '',
      financial: kase?.financial.verdict || 'unknown',
      loadBearing: sens?.load_bearing_count ?? null,
      flipSet: sens?.smallest_flip_set ?? null,
      watchOuts: kase?.watch_outs ?? [],
    } : null,
  }
}

/**
 * The copied block. Plain Markdown, because the destination is a note or a slide, not this app.
 *
 * It carries its own provenance and its own limits — the run id, the horizon, whether the
 * universe is the fictional demo set, and the line about what `disagreement` means. A figure
 * pasted somewhere else has to arrive with the thing that makes it checkable, or it becomes a
 * number in a document with no way back to the run that produced it.
 */
export function recapMarkdown(f: RecapFacts): string {
  const L: string[] = []
  L.push(`# ASEAN ESG Momentum Radar — run recap`)
  L.push('')
  L.push(`- **Run** \`${f.runId}\` · as of ${f.asOf} · ${f.horizon} horizon (${f.halfLifeDays}d half-life)`)
  L.push(`- **Universe** ${f.universe} companies${f.shown !== f.universe ? ` · ${f.shown} in the current filter` : ''}`)
  if (f.demo) L.push(`- **DEMO DATA** — a fictional, fully-numeric universe. Illustrative, not company disclosure.`)
  if (f.harvest) L.push(`- **Evidence** ${f.harvest.events} harvested events across ${f.harvest.companies} companies`)
  L.push('')
  L.push(`## Where the run stands`)
  L.push('')
  for (const [key, n] of Object.entries(f.labelCounts)) {
    L.push(`- ${f.labelNames[key] ?? key}: **${n}**`)
  }
  L.push('')
  L.push(`- Issuers already priced in (N): **${f.nmk.N}**`)
  L.push(`- Bond-ready pipeline (M): **${f.nmk.M}**`)
  L.push(`- Review list (K): **${f.nmk.K}**`)
  if (f.company) {
    const c = f.company
    L.push('')
    L.push(`## ${c.name} (${c.ticker})`)
    L.push('')
    L.push(`- **${c.label}** — disagreement ${signed(c.disagreement)}, confidence ${c.confidence.toFixed(2)}, on ${c.signals} dated signals`)
    L.push(`- The rating puts it at the **${pct(c.ratingPct)}th** percentile; our evidence at the **${pct(c.evidencePct)}th**${c.notch ? ` (basket notch ${c.notch}, unattributed, display only)` : ''}`)
    L.push(`- Financial read: **${c.financial}** — reported beside the ESG verdict, never merged into it`)
    if (c.loadBearing !== null) {
      L.push(c.flipSet
        ? `- Sensitivity: **${c.loadBearing}** of ${c.signals} signals would move the label alone; the **${c.flipSet}** heaviest would all have to go`
        : `- Sensitivity: **${c.loadBearing}** of ${c.signals} signals would move the label alone`)
    }
    for (const w of c.watchOuts) L.push(`- Watch out: ${w}`)
  }
  if (f.anchor) {
    L.push('')
    L.push(`## Receipt`)
    L.push('')
    L.push(`- Merkle root over ${f.anchor.leaves} leaves · **${f.anchor.status}**${f.anchor.chain ? ` on ${f.anchor.chain}` : ''}`)
  }
  L.push('')
  L.push(`---`)
  L.push(`\`disagreement\` = our evidence percentile − the incumbent rating's percentile, within this run's cohort.`)
  L.push(`The baseline rating is a MOCK stand-in for the licensed figure. Never buy / sell / hold. Not investment advice.`)
  L.push(`Every figure above re-derives from run \`${f.runId}\`.`)
  return L.join('\n')
}

export const RECAP: Track = {
  key: 'recap',
  label: 'Recap this run',
  subject: 'focused',
  steps: [
    {
      chapter: '01 · The run',
      view: 'board',
      note: 'Where this run stands: every name read twice, the four quadrants, the id that '
        + 'rebuilds it.',
      anchor: 'matrix',
      settle: 450,
      act: d => {
        d.set({ level: 3, tab: 'board', tier: 'all', pipelineOnly: false, greenFocus: false })
        // Focus the subject the walk is about. With nothing focused the track falls back to a
        // default name, and a recap whose board shows one company while its card totals another
        // is worse than no recap: both halves have to be the same company by construction.
        d.focus(d.subject)
        d.dashboard()
      },
    },
    {
      chapter: '02 · The pipeline',
      view: 'board',
      note: 'Issuers already priced in, the bond-ready pipeline, and the names a human still has '
        + 'to look at.',
      anchor: 'nmk',
      act: d => d.set({ tier: 'all', pipelineOnly: false }),
    },
    {
      chapter: '03 · The company',
      view: 'compete',
      note: 'The focused company: the verdict, and where it parts company with the rating.',
      anchor: 'verdict',
      settle: 900,
    },
    {
      chapter: '04 · What would change it',
      view: 'evidence',
      note: 'Remove each signal in turn — which removals move the label, and which do not.',
      anchor: 'sensitivity',
      settle: 700,
    },
    {
      chapter: '05 · The receipt',
      view: 'evidence',
      note: 'Recompute the hashes against the anchored root. Pending is reported as pending.',
      anchor: 'verify-block',
      settle: 400,
      act: d => { d.click('verify') },
    },
    {
      chapter: '06 · Consolidated',
      view: 'board',
      note: 'Everything the walk passed, in one block you can copy.',
      settle: 300,
      summary: true,
    },
  ],
}
