import { useStore } from '../../store'
import type { ResidualTest, SolvePanel } from '../../types'

/**
 * THE 10% TEST — does our ESG evidence explain what a factor model cannot?
 *
 * The claim this panel exists to check is the one a fund manager will put to us first: a factor
 * model already explains most of the cross-section, so what is left for an ESG signal to do?
 * `residual.py` answers it in the only form that can — two stages, the factor block first, then
 * the ESG block on WHAT IT LEFT OVER — and this panel renders that result without softening it.
 *
 * THE ORDER ON SCREEN IS DELIBERATE AND IT IS NOT THE FLATTERING ONE. Stage 1 comes first, and
 * on this panel stage 1 has NO out-of-sample skill: the factor block scores a negative R², so
 * there is no measured "90%" here at all. A panel that opened with the incremental result would
 * be asserting a baseline it never established — the exact move this product criticises a stale
 * rating for. So the reader is told what the residual actually is (effectively all of it) before
 * being told anything was explained.
 *
 * THE HEADLINE STATISTIC IS THE IC, NOT R². Pooled R² on fat-tailed 6-month returns is decided
 * by a handful of outliers. The information coefficient — rank correlation between the stage-2
 * call and the actual residual, computed within each cutoff — is what a cross-sectional claim
 * should be graded on. It is rendered with its t-stat and its CUTOFF COUNT on the same line,
 * because a t of +2.5 on five overlapping observations is a direction of travel and not an
 * inference, and hiding the 5 would let it read as one.
 *
 * THE TWO THINGS THAT CUT AGAINST US ARE RENDERED, NOT FOOTNOTED. Stage 1 is missing SMB and
 * HML, which leaves a bigger residual and makes stage 2's job easier — the result is tilted our
 * way and says so. And the effect is confined to one horizon: every specification clears at 6
 * months and a minority clear at 3 or 12, which is robust-but-horizon-specific rather than
 * "the model works". Both come off the frozen file as text, so neither can drift from the run.
 *
 * THE HOLDOUT BLOCK LEADS, AND IT CONTRADICTS THE MEASUREMENT BELOW IT. The two-stage read
 * further down says the ESG block explains part of the residual. A stricter protocol — train,
 * then a validation block to choose every hyperparameter, then a holdout scored exactly ONCE —
 * says it does not. When two tests disagree the better-designed one wins, so the holdout is
 * rendered first and the measurement underneath is explicitly marked as superseded rather than
 * quietly deleted: a reader who saw the earlier verdict is entitled to see what replaced it and
 * why.
 *
 * AND THE GAP BETWEEN THEM IS THE POINT. On the CGSI panel validation chose a configuration
 * worth +7.6% of the residual and the holdout returned -1.8%. That is rendered as a single
 * arrow, because it is the most instructive number on this page: it is what searching 48
 * configurations against one evaluation set does, and without the third split it is the figure
 * that would have shipped. A product that argues stale confident numbers are dangerous has to be
 * willing to show its own being caught.
 *
 * `null` on the demo universe. Those companies are fictional and have no returns; a residual
 * test over invented prices is not a weaker finding, it is not a finding.
 */

const TONE: Record<string, string> = {
  'explains part of the residual': 'fc-warn',
  'predicts part of the residual': 'fc-warn',
  partial: 'fc-warn',
  marginal: 'fc-bad',
  'no measurable contribution': 'fc-bad',
  no: 'fc-bad',
  'not run': 'fc-muted',
  'not scored': 'fc-muted',
}

const pc = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`

/** One panel's validation -> holdout collapse, as a single row. Never validation on its own. */
function SolveRow({ p, primary }: { p: SolvePanel; primary: boolean }) {
  return (
    <div className={`rz-solve-row ${primary ? 'is-primary' : ''}`}>
      <span className="rz-solve-name">
        {p.panel}
        <span className="rz-solve-n">{p.companies} companies · {p.rows} rows</span>
      </span>
      <span className="rz-solve-arrow">
        <b className={(p.validation_pct ?? 0) > 0 ? 'is-up' : 'is-down'}>{pc(p.validation_pct)}</b>
        <span className="rz-solve-lbl">chosen on validation</span>
      </span>
      <span className="rz-solve-to">→</span>
      <span className="rz-solve-arrow">
        <b className={(p.holdout_pct ?? 0) > 0 ? 'is-up' : 'is-down'}>{pc(p.holdout_pct)}</b>
        <span className="rz-solve-lbl">sealed holdout</span>
      </span>
      <span className="rz-solve-cfg">{p.configs_tried} configs searched</span>
    </div>
  )
}

const num = (v: number | null | undefined, dp = 3) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(dp)}`

/** One cutoff's IC as a diverging bar off a shared zero line. Same grammar as the pillar bars. */
function IcBar({ ic }: { ic: number }) {
  const w = Math.min(50, Math.abs(ic) * 100)
  return (
    <span className="rz-bar">
      <span className="rz-bar-zero" />
      <span
        className={`rz-bar-fill ${ic >= 0 ? 'is-up' : 'is-down'}`}
        style={ic >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
      />
    </span>
  )
}

export default function ResidualPanel() {
  const { board } = useStore()
  const r: ResidualTest | null | undefined = board?.engine?.residual
  if (!r) return null

  if (!r.ran) {
    return (
      <div className="rz" data-tour="residual">
        <div className="fc-head">
          <span className="fc-title">The 10% test</span>
          <span className="cc-muted">not run — {r.why}</span>
        </div>
      </div>
    )
  }

  const s1 = r.stage1!
  const s2 = r.stage2!
  const v = r.verdict!
  const ab = r.ablation

  return (
    <div className="rz" data-tour="residual">
      <div className="fc-head">
        <span className="fc-title">The 10% test</span>
        <span className="cc-muted">
          does our evidence explain what the factor model cannot — {r.companies} companies ·{' '}
          {r.rows} rows · {r.horizon_months}-month horizon
        </span>
      </div>

      {/* THE STRICTER TEST FIRST. It outranks everything below it — see the header. */}
      {r.solve && (
        <div className="rz-stage rz-solve">
          <div className="rz-stage-h">
            <span className="rz-num">!</span>
            <span className="rz-k">Can it be PREDICTED? — validation vs a sealed holdout</span>
            <span className={`fc-verdict ${TONE[r.solve.verdict.word] || 'fc-muted'}`}>
              {r.solve.verdict.word}
            </span>
          </div>
          {r.solve.wide && <SolveRow p={r.solve.wide} primary={r.solve.primary === 'wide'} />}
          {r.solve.narrow && <SolveRow p={r.solve.narrow} primary={r.solve.primary === 'narrow'} />}
          <p className="rz-caveat">{r.solve.lesson}</p>
          <p className="fc-line">{r.solve.verdict.line}</p>
        </div>
      )}

      {/* The two-stage measurement, kept and labelled. Deleting it would hide the disagreement
          rather than resolve it, and the disagreement is the finding. */}
      {r.solve && (
        <p className="rz-superseded">
          Below: the earlier single-split measurement. It reports a positive contribution and the
          holdout above does not. Both are shown; the holdout is the better-designed test and is
          the one to quote.
        </p>
      )}

      {/* STAGE 1, and it is the uncomfortable one. The "90%" is not established here. */}
      <div className="rz-stage">
        <div className="rz-stage-h">
          <span className="rz-num">1</span>
          <span className="rz-k">The factor model — “the 90%”</span>
        </div>
        <div className="rz-blocks">{s1.block.map(b => <span key={b}>{b}</span>)}</div>
        <div className="fc-row">
          <div className="fc-est">
            <span className="fc-k">out-of-sample R²</span>
            <span className={`fc-v ${(s1.r2_oos ?? 0) > 0 ? 'is-up' : 'is-down'}`}>
              {num(s1.r2_oos, 4)}
            </span>
            <span className="fc-err">
              {(s1.r2_oos ?? 0) > 0
                ? 'The factor block explains part of the cross-section out of sample.'
                : 'Negative — the factor block does not beat guessing the average on this panel. '
                  + 'So there is no measured “90%” here: on these 41 companies over three years, '
                  + 'effectively the whole cross-section is residual. Read everything below in '
                  + 'that light.'}
            </span>
          </div>
          {/* Named `left over` rather than `the 10%` on purpose: it is 104% here, and a label
              that says 10 beside a number that says 104 teaches the reader to stop reading. */}
          <div className="fc-est">
            <span className="fc-k">variance left over</span>
            <span className="fc-v">
              {s1.residual_share === null ? '—' : `${(s1.residual_share * 100).toFixed(0)}%`}
            </span>
            <span className="fc-err">What stage 2 is given to work with.</span>
          </div>
        </div>
      </div>

      {/* STAGE 2 — the actual question. */}
      <div className="rz-stage">
        <div className="rz-stage-h">
          <span className="rz-num">2</span>
          <span className="rz-k">Our ESG block, on that residual — “the 10%”</span>
        </div>
        <div className="rz-blocks">{s2.block.map(b => <span key={b}>{b}</span>)}</div>
        <div className="fc-row">
          <div className="fc-est">
            <span className="fc-k">mean rank IC</span>
            <span className={`fc-v ${(s2.mean_ic ?? 0) >= 0 ? 'is-up' : 'is-down'}`}>
              {num(s2.mean_ic, 3)}
            </span>
            {/* The cutoff count rides on the same line as the t-stat. Five overlapping
                observations is a direction of travel, not an inference. */}
            <span className="fc-err">
              t {num(s2.ic_t_stat, 2)} over {s2.ic_cutoffs} test cutoffs — and those cutoffs
              overlap, so the effective count is smaller than {s2.ic_cutoffs}.
            </span>
          </div>
          <div className="fc-est">
            <span className="fc-k">incremental R² (oos)</span>
            <span className={`fc-v ${(s2.incremental_r2_oos ?? 0) >= 0 ? 'is-up' : 'is-down'}`}>
              {num(s2.incremental_r2_oos, 4)}
            </span>
            <span className="fc-err">
              Against predicting the average residual. Small — the rank ordering is the finding
              here, not the magnitude.
            </span>
          </div>
          <span className={`fc-verdict ${TONE[v.word] || 'fc-muted'}`}>{v.word}</span>
        </div>

        {/* Per-cutoff ICs. One good quarter and four flat ones would average to the same number
            as five consistent ones, and they are not the same claim. */}
        <div className="rz-ics">
          {s2.ic_series.map(s => (
            <div className="rz-ic" key={s.cutoff}>
              <span className="rz-ic-cut">{s.cutoff}</span>
              <IcBar ic={s.ic} />
              <span className={`rz-ic-v ${s.ic >= 0 ? 'is-up' : 'is-down'}`}>{num(s.ic, 3)}</span>
              <span className="rz-ic-n">n={s.n}</span>
            </div>
          ))}
        </div>
      </div>

      {ab && (
        <div className="rz-stage">
          <div className="rz-stage-h">
            <span className="rz-num">✓</span>
            <span className="rz-k">Cross-check — one model, with and without the ESG block</span>
          </div>
          <div className="fc-skill">
            <span>factors only <b>{num(ab.r2_factors_only, 4)}</b></span>
            <span>with ESG <b>{num(ab.r2_with_esg, 4)}</b></span>
            <span className={ab.esg_helps_mae ? 'is-on' : ''}>
              error {ab.mae_factors_only.toFixed(2)} → <b>{ab.mae_with_esg.toFixed(2)}</b>
            </span>
          </div>
        </div>
      )}

      <p className="fc-line">{v.line}</p>

      {/* The two caveats that cut against the result, at the same size as the result. */}
      <p className="rz-caveat">{r.bias_note}</p>
      {r.sweep_summary?.horizon_note && (
        <p className="rz-caveat">{r.sweep_summary.horizon_note}</p>
      )}

      <div className="fc-skill">
        <span title={r.spec_note}>spec <b>{r.spec}</b>, declared before the run</span>
        <span title={Object.entries(r.factors_missing || {})
          .map(([k, why]) => `${k} — ${why}`).join('\n')}>
          {Object.keys(r.factors_missing || {}).join(' + ')} missing from stage 1
        </span>
        <span title={r.sweep_summary?.note}>
          {r.sweep_summary?.with_contribution} of {r.sweep_summary?.configurations} specs
        </span>
        <span title={r.sample_caveat}>built {r.built_at}</span>
      </div>
    </div>
  )
}
