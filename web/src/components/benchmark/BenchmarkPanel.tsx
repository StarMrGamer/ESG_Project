import type { Benchmark, Quote } from '../../types'
import { signClass } from '../ui'

/**
 * Two benchmarks for one company, kept visibly apart.
 *
 * The ASEAN block is a PEER comparison in the company's own unit — is this name ahead of or
 * behind the other ASEAN companies in its industry? The OECD block is the INDUSTRY's structural
 * footprint in tonnes of CO2e per million dollars of value added, which is a different unit
 * answering a different question: how much should a good score in this industry impress you?
 *
 * They are never averaged together. A single blended "benchmark score" would be a number nobody
 * measured, and the two halves genuinely disagree for a name like a bank — small footprint,
 * middling peers.
 *
 * An uploaded file lands here too. The upload carries a sector, and a sector is all either
 * benchmark needs, so "how does my company compare" works on day one for data we have never
 * seen before.
 */

/** Intensity spans 3.6 to 1,597 t/US$m, so position on a linear scale would be meaningless. */
function logPos(v: number, lo: number, hi: number): number {
  const l = Math.log10(Math.max(v, 0.01))
  const a = Math.log10(Math.max(lo, 0.01))
  const b = Math.log10(Math.max(hi, 0.01))
  return b === a ? 50 : Math.max(0, Math.min(100, ((l - a) / (b - a)) * 100))
}

function QuoteRow({ quote }: { quote: Quote }) {
  if (!quote) return null
  if (!quote.available) {
    return <div className="cc-muted bm-quote-none">No live quote — {quote.reason}</div>
  }
  const chg = quote.change_pct
  return (
    <div className="bm-quote">
      <span className="bm-quote-px">
        {quote.currency} {quote.price?.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </span>
      {chg != null && (
        <span className={`bm-quote-chg ${signClass(chg)}`}>{chg > 0 ? '+' : ''}{chg.toFixed(2)}%</span>
      )}
      <span className="cc-muted">
        {quote.symbol} · {quote.exchange} · {quote.source}
      </span>
      <span className="cc-muted bm-quote-note">{quote.note}</span>
    </div>
  )
}

export default function BenchmarkPanel({ benchmark, quote }: {
  benchmark: Benchmark | undefined
  quote?: Quote
}) {
  if (!benchmark) return null
  const { asean, oecd, own_score: own, gap_vs_asean: gap, verdict } = benchmark

  return (
    <div className="panel-block bm">
      <div className="cc-h">Industry benchmarks</div>
      <div className="cc-muted">
        Where this company sits against its ASEAN peers, and what its industry's footprint looks
        like across the OECD. Two different questions, two different units — never combined.
      </div>

      {/* ---- peers ---- */}
      <div className="bm-block">
        <div className="bm-block-h">vs ASEAN peers</div>
        {!asean.available
          ? <div className="empty-note">{asean.reason}</div>
          : (
            <>
              <div className="bm-nums">
                <div className="bm-num">
                  <span className="l">this company</span>
                  <span className="v" title={benchmark.own_score_source || benchmark.own_score_note}>
                    {own == null ? 'unknown' : own.toFixed(1)}
                  </span>
                </div>
                <div className="bm-num">
                  <span className="l">ASEAN peer avg</span>
                  <span className="v">{asean.average?.toFixed(1)}</span>
                </div>
                <div className="bm-num">
                  <span className="l">peers in set</span>
                  <span className="v">{asean.n}</span>
                </div>
                {gap != null && (
                  <div className="bm-num">
                    <span className="l">gap</span>
                    <span className={`v ${signClass(gap)}`}>{gap > 0 ? '+' : ''}{gap.toFixed(1)}</span>
                  </div>
                )}
              </div>
              {verdict && <div className="bm-verdict">{verdict}</div>}
              {benchmark.own_score_note && (
                <div className="cc-muted bm-note">{benchmark.own_score_note}</div>
              )}
              <div className="cc-muted">{asean.metric} · {asean.unit}</div>
            </>
          )}
      </div>

      {/* ---- industry footprint ---- */}
      <div className="bm-block">
        <div className="bm-block-h">OECD industry footprint</div>
        {!oecd.available
          ? <div className="empty-note">{oecd.reason}</div>
          : (
            <>
              <div className="bm-oecd-head">
                <b>{oecd.isic_label}</b>
                <span className="cc-muted">ISIC {oecd.isic_sections} · matched on {oecd.via}</span>
              </div>
              <div className="bm-nums">
                <div className="bm-num">
                  <span className="l">intensity</span>
                  <span className="v">{oecd.intensity?.toLocaleString(undefined, { maximumFractionDigits: 1 })}</span>
                </div>
                <div className="bm-num">
                  <span className="l">cleanest rank</span>
                  <span className="v">{oecd.rank} of {oecd.of}</span>
                </div>
                <div className="bm-num">
                  <span className="l">industry median</span>
                  <span className="v">{oecd.median?.toLocaleString(undefined, { maximumFractionDigits: 1 })}</span>
                </div>
              </div>
              <div className="cc-muted">{oecd.unit} · {oecd.year}</div>

              {/* Log scale: the range spans nearly three orders of magnitude. */}
              <div className="bm-scale" title="Log scale — industry intensity spans three orders of magnitude.">
                <div className="bm-scale-track">
                  <div className="bm-scale-pin"
                    style={{ left: `${logPos(oecd.intensity ?? 1, 3.6, 1600)}%` }} />
                </div>
                <div className="bm-scale-ends">
                  <span>cleanest · {oecd.cleanest}</span>
                  <span>most intense · {oecd.dirtiest}</span>
                </div>
              </div>

              <details className="expander">
                <summary>Where these numbers come from</summary>
                <div className="cc-muted">{oecd.basis}</div>
                <div className="cc-muted">Retrieved {oecd.retrieved} from the OECD public SDMX API.</div>
                {(oecd.sources ?? []).map((u, i) => (
                  <div key={i} className="bm-src"><a href={u} target="_blank" rel="noreferrer">{u}</a></div>
                ))}
              </details>
            </>
          )}
      </div>

      {quote && (
        <div className="bm-block">
          <div className="bm-block-h">Market quote</div>
          <QuoteRow quote={quote} />
        </div>
      )}

      <div className="cc-muted">{benchmark.disclaimer}</div>
    </div>
  )
}
