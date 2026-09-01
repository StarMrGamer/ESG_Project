import { useMemo } from 'react'
import { useStore } from '../../store'
import { dimSplit, PPP_DIM_REASON } from '../../lib/tierMatch'
import type { PPP } from '../../store'

/**
 * THE PPP RISK FILTER STRIP — the lens, and what it is currently doing to the board.
 *
 * WHY IT CARRIES NO ACCURACY FIGURE. The brief for this strip asked it to read "downside failure
 * rate reduced from 10% to 5% on dual-aligned assets". That number, and the "95% accuracy" that
 * came with it, are not in this repo and cannot be derived from what is: the basket holds a
 * dated price snapshot and dated documentary evidence, and no forward-return series, so there is
 * nothing to measure a failure rate against. Printing it would have been a HARD RULE 2 breach —
 * and the specific one this product exists to argue against, since a confident statistic beside
 * a real chart is exactly what a stale rating looks like from the outside.
 *
 * So the strip states what IS measured, off the loaded run and the dated snapshot: how many
 * names have both directions pointing the same way, how many diverge, and out of how many the
 * pair can be read for at all. Every figure re-derives from the run id printed beside it. When a
 * backtest produces a real hit rate, it belongs here — with its cutoffs, its cohort and its id.
 */

const LENS_COPY: Record<PPP, { name: string; does: string }> = {
  profit: {
    name: 'Profit first',
    does: 'Financial return leads and ESG runs as a downside gate: a name whose dated evidence '
        + 'is deteriorating is dimmed however well the price has run.',
  },
  balanced: {
    name: 'Balanced',
    does: 'Profit, People and Planet weighted equally. Both directions shown, nothing dimmed.',
  },
  planet: {
    name: 'Sustainability focus',
    does: 'The labelled green-bond hurdle first — read from green_bond_status, the same field '
        + 'the Conservative tier and the N bucket use.',
  },
}

export default function PPPBanner() {
  const { board, settings, setSettings } = useStore()
  const dual = board?.dual
  const engine = board?.engine

  /**
   * How many names the LENS is dimming — from `dimSplit`, the same function the matrix caption
   * reads, because two widgets on one screen must not describe the same control with different
   * numbers. A name already dimmed by the risk tier is not counted here: the lens's effect is
   * what it removes from what was otherwise in view, and anything else is a claim about a board
   * nobody is looking at.
   */
  const dimmed = useMemo(() => dimSplit(
    Object.values(engine?.records ?? {}), settings, r => ({
      greenStatus: engine?.badges?.[r.company_id]?.green_bond?.status || '',
      bucket: engine?.badges?.[r.company_id]?.pipeline?.bucket || '',
    })).lens, [engine, settings])

  if (!dual || !engine) return null
  const c = dual.counts

  return (
    <div className="ppp-banner" data-tour="ppp">
      <div className="ppp-lens">
        <span className="ppp-lens-k">PPP risk filter</span>
        <div className="seg" role="group" aria-label="Profit, People, Planet balance">
          {(Object.keys(LENS_COPY) as PPP[]).map(key => (
            <button key={key} className={`btn ${settings.ppp === key ? 'on' : ''}`}
              title={LENS_COPY[key].does}
              onClick={() => setSettings({ ppp: key })}>{LENS_COPY[key].name}</button>
          ))}
        </div>
      </div>

      {/* Measured off this run, every time. No stored statistic, no hit rate, no failure rate —
          see the note at the top of this file for why that is a deliberate absence. */}
      <div className="ppp-counts"
        title={`Counts measured off run ${engine.run_id}`
          + (dual.captured ? ` · prices captured ${dual.captured} · ${dual.window} factor` : '')
          + '\n\nNo accuracy or failure-rate figure is shown, because no backtest in this repo has produced one.'
          + (dual.unavailable ? `\n\n${dual.unavailable}` : '')}>
        <span className="ppp-pill ppp-good">
          <b>{c.aligned}</b> dual-momentum aligned
        </span>
        <span className="ppp-pill ppp-bad" title={dual.alignment.downside_trap.tooltip}>
          <b>{c.downside_trap}</b> divergence — downside risk
        </span>
        <span className="ppp-pill ppp-warn" title={dual.alignment.evidence_ahead.tooltip}>
          <b>{c.evidence_ahead}</b> divergence — evidence ahead
        </span>
        <span className="ppp-pill ppp-muted" title={dual.alignment.unknown.tooltip}>
          <b>{dual.quotable}</b> of {dual.total} readable on both axes
        </span>
      </div>

      {/* The prose that used to sit here — what the lens does, the run id, the capture date and
          the no-accuracy-figure disclosure — is on the controls and the pills as tooltips. It is
          the same information; four lines of grey text under every board is not where it earns
          its place. What stays visible is the ONE thing that changes as you click: how many
          names this lens is dimming right now. */}
      {(dimmed > 0 || dual.unavailable) && (
        <div className="ppp-foot cc-muted">
          {dual.unavailable && <b>No price axis in this universe. </b>}
          {dimmed > 0 && <><b>{dimmed}</b> dimmed — {PPP_DIM_REASON[settings.ppp]}. Dimmed, never hidden.</>}
        </div>
      )}
    </div>
  )
}
