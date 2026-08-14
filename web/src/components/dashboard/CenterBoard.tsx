import { useStore } from '../../store'
import { MomentumChart, PriceChart } from '../charts'
import { fmtPct, SectionTitle, signClass, TONE_CLASS } from '../ui'
import type { WinnerRow } from '../../types'

function BarsPanel({ title, subtitle, rows, suffix, footer, tier, maxAbs, onFocus }: {
  title: string
  subtitle: string
  rows: WinnerRow[]
  suffix: string
  footer?: string
  tier?: boolean
  maxAbs: number
  onFocus: (ticker: string) => void
}) {
  const mx = maxAbs || 1
  return (
    <div className="panel-block">
      <div className="cc-h">{title}</div>
      <div className="cc-muted">{subtitle}</div>
      {rows.length === 0
        ? <div className="empty-note">Nothing to rank in this filter yet.</div>
        : (
          <div className="cc-hwwrap">
            {rows.map(r => {
              const w = Math.max(4, Math.round((Math.abs(r.value) / mx) * 100))
              const sign = r.value >= 0 ? 'cc-pos' : 'cc-neg'
              const barCls = tier
                ? r.value >= 80 ? 'cc-pos' : r.value >= 60 ? 'cc-tier-mid' : 'cc-tier-low'
                : sign
              const val = suffix === '%' ? fmtPct(r.value) : `${r.value}${suffix}`
              return (
                <div className="cc-hw" key={r.ticker}>
                  <button className="cc-hw-name" onClick={() => onFocus(r.ticker)}
                    title={`Focus ${r.company} in the right-rail panels`}>
                    {r.company}{r.is_new && <em className="cc-new">new</em>}
                  </button>
                  <div className="cc-hw-track"><div className={`cc-hw-fill ${barCls}`} style={{ width: `${w}%` }} /></div>
                  <div className={`cc-hw-val ${sign}`}>{val}</div>
                </div>
              )
            })}
          </div>
        )}
      {footer && <div className="cc-muted">{footer}</div>}
    </div>
  )
}

export default function CenterBoard() {
  const { board, settings, setFocus, openDeepDive } = useStore()
  if (!board) return null
  const { mode, focused, hidden_winners, evidence } = board
  const simple = settings.simplified
  const dark = settings.dark

  const focusByTicker = (ticker: string) => setFocus(ticker)

  const classification = focused && (
    <div className={`cc-class ${TONE_CLASS[focused.classification.tone] || 'cc-class-neutral'}`}>
      <div className="cc-class-h">
        Classification &nbsp; <b>{focused.classification.label}</b> &nbsp;
        <span className="cc-muted">· {focused.constituent.company}</span>
      </div>
      {mode === 'evidence' && focused.credentials.length > 0 && (
        <div className="cc-chips">
          {focused.credentials.slice(0, 5).map((cr, i) => (
            <span className="cc-chip" key={i}>{cr.label} {cr.value}</span>
          ))}
        </div>
      )}
      <div className="cc-class-line">{focused.classification.line}</div>
    </div>
  )

  const pricePanel = focused && (
    <div className="panel-block">
      <SectionTitle sub="illustrative · rebased to 100">Share price · 90 days</SectionTitle>
      {focused.price.pct == null
        ? <div className="empty-note">Awaiting data — no price feed wired for this name.</div>
        : (
          <>
            <div className="cc-muted">
              90-day change <b className={signClass(focused.price.pct)}>{fmtPct(focused.price.pct)}</b> · illustrative demo data
            </div>
            <PriceChart series={focused.price.series} pct={focused.price.pct} dark={dark} />
          </>
        )}
    </div>
  )

  const forecast = focused && (
    <div className="panel-block">
      <div className="cc-h">Forecast outlook <span className="cc-tag-illus">illustrative</span></div>
      {!focused.forecast.available
        ? <div className="cc-card cc-muted" style={{ marginBottom: 0 }}>{focused.forecast.headline}</div>
        : (
          <>
            <div className={`cc-class ${TONE_CLASS[focused.forecast.tone] || 'cc-class-neutral'}`}>
              <div className="cc-class-h">Outlook &nbsp; <b>{focused.forecast.label}</b></div>
              <div className="cc-class-line">{focused.forecast.headline}</div>
            </div>
            {!simple && (
              <>
                <div className="cc-chips">
                  {focused.forecast.pillars.map(p => (
                    <span className="cc-chip" key={p.key}>{p.label} {p.arrow} {p.word}</span>
                  ))}
                </div>
                <div className="cc-muted">
                  Basis: avg live pillar momentum {fmtPct(focused.forecast.mean)} (illustrative demo signal).
                </div>
              </>
            )}
          </>
        )}
      <div className="cc-muted">
        Illustrative directional outlook — not a forecast, prediction, or price target. Never investment advice.
      </div>
    </div>
  )

  const checkPanel = focused && (
    <div className="panel-block">
      <div className="cc-h">Check before Monday</div>
      {!focused.check_action.has
        ? (
          <div className="cc-panel-body">
            No competing read computed yet — run a deep-dive Compete on this company to surface one
            concrete action to check.
          </div>
        )
        : (
          <>
            {!simple && focused.check_action.verdict && (
              <div className="cc-muted">{focused.check_action.verdict}</div>
            )}
            <div className="cc-panel-body">{focused.check_action.check}</div>
          </>
        )}
    </div>
  )

  const newsPanel = focused && (
    <div className="panel-block">
      <div className="cc-h">In the news</div>
      {focused.news.headlines.length > 0 && (
        <div className="cc-muted">Illustrative demo headlines — not real news.</div>
      )}
      {focused.news.headlines.slice(0, simple ? 3 : 5).map((h, i) => (
        <div className="cc-panel-body" style={{ margin: '6px 0' }} key={i}>
          {h.title}
          <div className="cc-muted">{[h.source, h.date].filter(Boolean).join(' · ')}</div>
        </div>
      ))}
      {focused.news.headlines.length === 0 && (
        <div className="empty-note">General news not wired for this name yet — search it directly:</div>
      )}
      <div className="cc-muted" style={{ marginTop: 8 }}>
        <a href={focused.news.youtube_url} target="_blank" rel="noreferrer">Search YouTube</a>
        {!simple && <> &nbsp;·&nbsp; <a href={focused.news.news_url} target="_blank" rel="noreferrer">News search</a></>}
      </div>
    </div>
  )

  const plainSummary = focused && (
    <>
      <div className={`cc-class ${TONE_CLASS[focused.plain_summary.tone] || 'cc-class-neutral'}`}>
        <div className="cc-class-h">
          In plain terms &nbsp; <b>{focused.plain_summary.headline}</b>
          {settings.demo && <span className="cc-tag-illus">illustrative demo</span>}
        </div>
        <div className="cc-class-line">{focused.plain_summary.body}</div>
        {focused.plain_summary.verdict && (
          <div className="cc-class-line"><b>What we see:</b> {focused.plain_summary.verdict}</div>
        )}
      </div>
      <div className="cc-muted">Plain-language read — not investment advice; we never say buy / sell / hold.</div>
    </>
  )

  const cta = focused && (
    <div className="focus-cta">
      <button className="btn btn-primary" onClick={() => openDeepDive(focused.constituent.ticker, 'compete')}>
        Compete · {focused.constituent.company}
      </button>
      <button className="btn" onClick={() => openDeepDive(focused.constituent.ticker, 'interrogate')}>
        Interrogate first
      </button>
    </div>
  )

  if (mode === 'evidence') {
    const leaders = evidence.leaders
    const mx = Math.max(...leaders.map(r => r.value), 100)
    return (
      <div className="center-stack">
        {simple && plainSummary}
        <div className="pill-row">
          {evidence.coverage.map(cv => (
            <div className="cc-pill" key={cv.label}>
              <div className="cc-pill-h">{cv.label}</div>
              <div className="cc-big cc-pos">{cv.pct ?? '—'}%</div>
              <div className="cc-pill-sub">{cv.count}/{cv.n} of set</div>
            </div>
          ))}
        </div>
        {simple
          ? (
            <>
              {classification}
              {checkPanel}
              {forecast}
              {newsPanel}
              {cta}
            </>
          )
          : (
            <>
              <div className="split-board">
                <div className="panel-block">
                  <SectionTitle sub="90 days · % change">ESG momentum</SectionTitle>
                  <div className="empty-note">
                    Live pillar momentum needs the alt-data feed (AI hiring, patents, news/behaviour) —
                    not in the evidence set. <b>This is the radar's real edge</b> once those signals
                    are wired.
                  </div>
                </div>
                <BarsPanel title="ESG leaders"
                  subtitle={`${board.counts.showing} companies · derived 0–100 score`}
                  rows={leaders} maxAbs={mx} suffix="/100" tier
                  footer="Score = ratings each name's evidence cites (MSCI/DJSI/CDP/FTSE4Good/…)."
                  onFocus={focusByTicker} />
              </div>
              {classification}
              {pricePanel}
              {forecast}
              {newsPanel}
              {cta}
            </>
          )}
      </div>
    )
  }

  const strip = board.pillars.filter(p => ['environment', 'governance', 'digital_ai'].includes(p.key))
  const hw = hidden_winners
  const maxAbs = Math.max(...hw.rows.map(r => Math.abs(r.value)), 1)
  return (
    <div className="center-stack">
      {simple && plainSummary}
      <div className="kpi-row">
        {strip.map(p => (
          <div className={`cc-kpi ${p.fast ? 'cc-fast' : ''}`} key={p.key}>
            <div className="cc-kpi-label">{p.label}</div>
            <div className={`cc-kpi-val ${p.fast ? '' : signClass(p.value)}`}>{fmtPct(p.value)}</div>
            <div className={`cc-kpi-trend ${p.fast ? '' : signClass(p.value)}`}>{p.arrow} {p.trend}</div>
          </div>
        ))}
      </div>
      {simple
        ? (
          <div className="panel-block">
            <SectionTitle sub="90 days · % change">ESG momentum</SectionTitle>
            {Object.keys(board.momentum_series).length === 0
              ? <div className="empty-note">No momentum data for this filter yet.</div>
              : <MomentumChart series={board.momentum_series} dark={dark} height={430} />}
          </div>
        )
        : (
          <div className="split-board">
            <div className="panel-block">
              <SectionTitle sub="90 days · % change">ESG momentum</SectionTitle>
              {Object.keys(board.momentum_series).length === 0
                ? <div className="empty-note">No momentum data for this filter yet.</div>
                : <MomentumChart series={board.momentum_series} dark={dark} height={360} />}
            </div>
            <BarsPanel title="Hidden winners vs peer avg"
              subtitle={`${board.counts.showing} companies · avg ESG ${hw.peer_avg ?? '—'}`}
              rows={hw.rows} maxAbs={maxAbs} suffix="%"
              footer="Bar = live Digital/AI signal — the divergence the rating can't see. Click a name to focus it."
              onFocus={focusByTicker} />
          </div>
        )}
      {classification}
      {pricePanel}
      {forecast}
      {simple && checkPanel}
      {newsPanel}
      {cta}
    </div>
  )
}
