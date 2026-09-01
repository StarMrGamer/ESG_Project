import { useStore } from '../../store'
import type { DirectionPayload, ForecastPayload, OutlookPayload } from '../../types'

/**
 * THE FORECAST — a model estimate of 6-month price return, and the skill it actually has.
 *
 * This panel is the one place in the product that predicts. It was asked for explicitly, and it
 * is built honestly, which here means one rule above all others:
 *
 *   **The estimate is never shown without its measured error and its verdict.**
 *
 * Not in a tooltip, not behind a fold, not in smaller type below — on the same line. A number
 * whose reliability the reader cannot check is precisely the object this whole product exists to
 * argue against; shipping one here, of all places, would make the pitch self-refuting.
 *
 * WHAT THE MODEL ACTUALLY IS. Ridge regression on a real panel: the engine replayed at quarterly
 * cutoffs (it is pure, so it can be), the PPP shares and evidence read as they stood at each
 * cutoff, paired against the return each stock actually delivered over the following six months.
 * Trained on the early cutoffs, graded on the later ones — split by TIME, never randomly.
 *
 * WHAT IT MEASURED. Nothing. Across nine configurations — three horizons by three train splits —
 * every out-of-sample R² came back negative and every directional hit rate came in below the
 * majority class. The model does not beat guessing the average. **That is the finding, and it is
 * the honest one**: on ~3 years, one market regime and ~43 companies, this panel does not
 * support forecasting a price from these features. The number is still rendered, because it was
 * asked for and because a failed model that says so is worth more than a plausible one that does
 * not — but the verdict is rendered louder.
 *
 * BESIDE IT, THE THING THAT IS ACTUALLY EVIDENCED: CGSI's own published base rates for how often
 * an ESG improver in this basket beat the index, attributed, with their own caveat that it does
 * not transfer to a single stock. That is a measured historical frequency rather than our guess,
 * and it is the honest answer to "so will it make money?".
 */

const TONE: Record<string, string> = {
  'some skill': 'fc-warn',
  marginal: 'fc-bad',
  'no measured skill': 'fc-bad',
  untrained: 'fc-muted',
}

const signed = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

export default function ForecastPanel({ forecast, company }:
  { forecast: ForecastPayload | null | undefined; company: string }) {
  const { board, settings } = useStore()
  const outlook = board?.outlook
  if (!forecast) return null

  return (
    <div className="fc" data-tour="forecast">
      <div className="fc-head">
        <span className="fc-title">Forward view</span>
        <span className="cc-muted">two model reads and a published base rate — none is advice</span>
      </div>

      {/* The three blocks are three readings of ONE question, so they lay out side by side in a
          row rather than stacking — see `.fc-blocks`. DIRECTION comes first: it is the question
          that was actually asked ("which way"), and it is a fairer test than magnitude, because
          a model can be hopeless at how far and still be useful about which way. This one is
          not, and says so. */}
      <div className="fc-blocks">
      {forecast.available && forecast.direction && (
        <Direction d={forecast.direction} live={forecast.factors_live || []} />
      )}

      {forecast.available && forecast.verdict ? (
        <div className={`fc-model ${TONE[forecast.verdict.word] || 'fc-muted'}`}
          title={`${forecast.not_advice}\n\n${forecast.sample_caveat}`}>
          <div className="fc-row">
            <div className="fc-est">
              <span className="fc-k">Model estimate · {forecast.horizon_months}-month return</span>
              <span className="fc-v">{signed(forecast.estimate_pct as number)}</span>
              {/* The error sits ON the estimate, not under it. An estimate of -3% from a model
                  routinely 15 points out is not a forecast of -3% and must never read as one. */}
              {forecast.typical_error_pct != null && (
                <span className="fc-err">
                  ± {forecast.typical_error_pct.toFixed(1)} pts typical error
                </span>
              )}
            </div>
            <span className={`fc-verdict ${TONE[forecast.verdict.word] || 'fc-muted'}`}>
              {forecast.verdict.word}
            </span>
          </div>
          <p className="fc-line">{forecast.verdict.line}</p>

          {forecast.skill && (
            <div className="fc-skill">
              <span title="Out-of-sample R² against predicting the training mean. Negative means it does worse than that baseline.">
                R² <b>{forecast.skill.r2_oos.toFixed(3)}</b> out of sample
              </span>
              <span title="Mean absolute error out of sample, against the same baseline.">
                error <b>{forecast.skill.mae_oos.toFixed(1)}%</b> vs baseline {forecast.skill.baseline_mae.toFixed(1)}%
              </span>
              <span title="How often it calls the direction, against always predicting the majority direction — which is the honest baseline in a trending market, not 50%.">
                direction <b>{(forecast.skill.hit_rate * 100).toFixed(0)}%</b> vs majority {(forecast.skill.majority_class * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      ) : (
        <p className="fc-line cc-muted">
          <b>No estimate for {company}.</b> {forecast.why}
        </p>
      )}

      {/* The evidenced half. A measured historical frequency, attributed, with its own author's
          warning that it does not transfer to one stock — on the block as a tooltip. */}
      {outlook?.available && <BaseRate outlook={outlook} holding={settings.profile.holding} />}
      </div>
    </div>
  )
}

/** The FACTOR row: what the model actually had, and the two it did not. */
const FACTOR_LABEL: Record<string, string> = {
  MKT: 'market beta', WML: '12-1 momentum', VOL: 'volatility',
  'RMW-proxy': 'profitability (proxy)', ESG: 'ESG evidence', PPP: 'PPP shares',
}

function Direction({ d, live }: { d: DirectionPayload; live: string[] }) {
  const up = d.call === 'up'
  return (
    <div className={`fc-model ${TONE[d.verdict.word] || 'fc-muted'}`}>
      <div className="fc-row">
        <div className="fc-est">
          <span className="fc-k">Direction · Fama-French style factors</span>
          <span className={`fc-v ${up ? 'is-up' : 'is-down'}`}>
            {up ? '↑ up' : '↓ down'}
          </span>
          {/* Distance from a coin flip, not the raw probability: 52% and 94% are both "up". */}
          <span className="fc-err">
            {(d.up_probability * 100).toFixed(0)}% chance up ·{' '}
            {d.confidence < 0.15 ? 'barely off a coin flip' : `${(d.confidence * 100).toFixed(0)}% off a coin flip`}
          </span>
        </div>
        <span className={`fc-verdict ${TONE[d.verdict.word] || 'fc-muted'}`}>{d.verdict.word}</span>
      </div>
      <p className="fc-line">{d.verdict.line}</p>
      <div className="fc-skill">
        <span title="How often it called the direction correctly out of sample.">
          right <b>{(d.skill.accuracy * 100).toFixed(0)}%</b> of the time
        </span>
        <span title="Always predicting the commoner direction. The honest baseline in a trending market — not 50%.">
          vs always-guess <b>{(d.skill.majority_class * 100).toFixed(0)}%</b>
        </span>
        <span title="Brier score: mean squared error of the probability itself. Accuracy alone hides a model that is right but wildly overconfident.">
          calibration <b>{d.skill.brier.toFixed(3)}</b> vs {d.skill.brier_baseline.toFixed(3)}
        </span>
      </div>
      {/* Naming the missing factors is still the point — this is Fama-French STYLE and calling
          it the real thing would be the overclaim — but it is a chip with the detail on hover
          rather than two paragraphs of prose under every company. */}
      <div className="fc-skill">
        <span title={`Factors used: ${d.factors_present.map(f => FACTOR_LABEL[f] || f).join(' · ')}`
          + (live.length ? '\n\nMarket factors read live for this company.' : '')}>
          {d.factors_present.length} factors
        </span>
        <span title={Object.entries(d.factors_missing).map(([k, why]) => `${k} — ${why}`).join('\n')
          + '\n\nNeither is proxied: substituting something else for size or value would be inventing a factor.'}>
          {Object.keys(d.factors_missing).join(' + ')} missing
        </span>
      </div>
    </div>
  )
}

const HORIZON_FOR: Record<string, string> = {
  under_2y: '1y', '2_5y': '3y', '5y_plus': '5y',
}
const HORIZON_WORD: Record<string, string> = {
  '1y': 'one year', '3y': 'three years', '5y': 'five years',
}

function BaseRate({ outlook, holding }: { outlook: OutlookPayload; holding: string }) {
  const key = HORIZON_FOR[holding] || '3y'
  const rate = outlook.horizons[key] ?? outlook.rate

  return (
    <div className="fc-base"
      title={`${outlook.source.publisher}, ${outlook.source.title}, ${outlook.source.date}.\n\n${outlook.not_a_forecast}`}>
      <div className="fc-row">
        <div className="fc-est">
          <span className="fc-k">Published base rate · {HORIZON_WORD[key]}</span>
          <span className="fc-v">{rate}</span>
          <span className="fc-err">of ESG improvers beat the index, historically</span>
        </div>
        <span className="fc-verdict fc-good">measured</span>
      </div>
      <div className="fc-skill">
        {(['1y', '3y', '5y'] as const).map(k => (
          <span key={k} className={k === key ? 'is-on' : ''}>
            {HORIZON_WORD[k]} <b>{outlook.horizons[k]}</b>
          </span>
        ))}
      </div>
      {/* The author's own caveat, at the same size as the figure it qualifies. */}
      <p className="fc-line">&ldquo;{outlook.caveat}&rdquo;</p>
    </div>
  )
}
