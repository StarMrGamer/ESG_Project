import { useStore } from '../../store'
import RadarHub from './RadarHub'
import { MomentumChart, PriceChart } from '../charts'
import { fmtPct, fmtPillar, SectionTitle, signClass, TONE_CLASS } from '../ui'
import CasePanel from '../case/CasePanel'
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
  // `lv` is the layering control; `simple` stays as the level-1 copy switch the panels below
  // already read. Level 1 promises "the verdict and one action" in the header tooltip and in the
  // setup card, so anything that is not the verdict or the action has to earn level 2.
  const lv = settings.level
  const simple = lv === 1
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
      {/* "AWAITING DATA" on a company that HAS evidence is a false negative: the signals exist,
          they have simply decayed past this horizon's half-life. Saying so turns an apparently
          broken card into the finding it actually is, and points at the fix (the longer
          horizon) instead of leaving the reader to conclude we have nothing. */}
      {focused.decay_note && <div className="cc-muted">{focused.decay_note}</div>}
    </div>
  )

  // A real listing gets its ACTUAL closes from Yahoo, rebased to 100; the fictional demo set
  // keeps its synthetic curve and keeps saying so. `price.source` is the discriminator — set
  // only when a live series was genuinely fetched, so neither label can end up on the other's
  // data. Context only: a price is never an input to any score (see quotes.py).
  const live = !!focused?.price.source
  const pricePanel = focused && (
    <div className="panel-block">
      <SectionTitle sub={live ? `${focused.price.source} · rebased to 100` : 'illustrative · rebased to 100'}>
        Share price · 90 days
      </SectionTitle>
      {focused.price.pct == null
        ? (
          <div className="empty-note">
            No 90-day price for this listing — the source covers SGX, Bursa, IDX and SET; PSE and
            HOSE lines are not available and an ADR is not shown in their place.
          </div>
        )
        : (
          <>
            <div className="cc-muted">
              90-day change <b className={signClass(focused.price.pct)}>{fmtPct(focused.price.pct)}</b>
              {live
                ? <> · {focused.price.points} sessions · context only, never a signal</>
                : <> · illustrative demo data</>}
            </div>
            <PriceChart series={focused.price.series} pct={focused.price.pct} dark={dark} />
          </>
        )}
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
              <CasePanel />
              {checkPanel}
              {lv >= 3 && pricePanel}
              {lv >= 2 && newsPanel}
              {cta}
            </>
          )}
      </div>
    )
  }

  const hw = hidden_winners
  const maxAbs = Math.max(...hw.rows.map(r => Math.abs(r.value)), 1)
  // The hub needs at least one pillar reading to draw a shape. When the filter has none it
  // renders nothing, so the old three-card strip stays as the fallback rather than leaving a hole.
  const hasPillars = board.pillars.some(p => p.value != null)
  const strip = board.pillars.filter(p => ['environment', 'governance', 'digital_ai'].includes(p.key))
  return (
    <div className="center-stack">
      {hasPillars
        ? <RadarHub solo={lv === 1} />
        : (
          <>
            {simple && plainSummary}
            <div className="kpi-row">
              {strip.map(p => (
                <div className={`cc-kpi ${p.fast ? 'cc-fast' : ''}`} key={p.key}>
                  <div className="cc-kpi-label">{p.label}</div>
                  <div className={`cc-kpi-val ${p.fast ? '' : signClass(p.value)}`}>{fmtPillar(p.value, p.basis)}</div>
                  <div className={`cc-kpi-trend ${p.fast ? '' : signClass(p.value)}`}>{p.arrow} {p.trend}</div>
                </div>
              ))}
            </div>
          </>
        )}
      {simple
        ? null
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
      {lv >= 2 && classification}
      {lv >= 2 && <CasePanel />}
      {!hasPillars && checkPanel}
      {lv >= 3 && pricePanel}
      {lv >= 2 && newsPanel}
      {!hasPillars && cta}
    </div>
  )
}
