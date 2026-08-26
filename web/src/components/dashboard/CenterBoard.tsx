import { useStore } from '../../store'
import RadarHub from './RadarHub'
import { PriceChart } from '../charts'
import { Section, SectionTitle, TONE_CLASS, fmtPct, fmtPillar, signClass } from '../ui'
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
    <Section id="price" title="Share price · 90 days" sub={live
      ? `${focused.price.source}${focused.price.captured ? ` · as of ${focused.price.captured}` : ''} · rebased to 100`
      : 'illustrative · rebased to 100'}>
      {/* "Rebased to 100" is jargon on a card aimed at a reader who may not have met it. It is
          one sentence to explain and confusing to leave unexplained, so it is explained. */}
      <p className="strip-note">
        <b>Rebased to 100</b> means the price 90 days ago is drawn as 100, so the line shows the
        percent move rather than the currency — <b>112</b> is up 12%. It lets a Singapore dollar
        and a Thai baht listing sit on the same axis. Context only: a price never enters any
        score.
      </p>
      {focused.price.pct == null
        ? (
          focused.price.last
            ? (
              <>
                <div className="cc-muted">
                  Last traded{' '}
                  <b>{focused.price.last.currency} {focused.price.last.price}</b>
                  {focused.price.last.change_pct != null && <>
                    {' '}<b className={signClass(focused.price.last.change_pct)}>
                      {fmtPct(focused.price.last.change_pct)}
                    </b> on the day
                  </>}
                  {' · '}{focused.price.last.exchange} · {focused.price.last.source}
                  {focused.price.last.captured && <> · as of {focused.price.last.captured}</>}
                </div>
                <div className="empty-note">
                  No 90-day line for this listing — the Philippine board gives a live price but
                  carries no history, so there is nothing to draw. A single point is not a trend
                  and is not drawn as one.
                </div>
              </>
            )
            : (
              <div className="empty-note">
                No price for this listing. Singapore, Bursa, Bangkok and Jakarta carry history,
                the Philippine board carries a live price without one — but a <b>delisted</b>
                constituent has no price anywhere, which is the finding rather than a gap.
              </div>
            )
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
    </Section>
  )


  const checkPanel = focused && (
    <Section id="check" title="Check before Monday">
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
    </Section>
  )

  const newsPanel = focused && (
    <Section id="news" title="In the news">
      {/* Three states that must never blur into each other: seeded demo headlines, real gathered
          ones, and nothing. The label says which — a real headline and an illustrative one look
          identical on screen otherwise. */}
      {focused.news.status === 'demo' && (
        <div className="cc-muted">Illustrative demo headlines — not real news.</div>
      )}
      {focused.news.status === 'gathered' && (
        <div className="cc-muted">
          Gathered {focused.news.gathered_at || ''} · {focused.news.dated ?? 0} of{' '}
          {focused.news.headlines.length} carry a date the article itself states · titles and
          links copied from the source, never written by a model
        </div>
      )}
      {focused.news.headlines.slice(0, simple ? 3 : 5).map((h, i) => (
        <div className="cc-panel-body" style={{ margin: '6px 0' }} key={i}>
          {h.url
            ? <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a>
            : h.title}
          <div className="cc-muted">
            {[h.source, h.date || 'date not stated by the source'].filter(Boolean).join(' · ')}
          </div>
        </div>
      ))}
      {focused.news.headlines.length === 0 && (
        <div className="empty-note">No gathered headlines for this name yet — search it directly:</div>
      )}
      <div className="cc-muted" style={{ marginTop: 8 }}>
        <a href={focused.news.youtube_url} target="_blank" rel="noreferrer">Search YouTube</a>
        {!simple && <> &nbsp;·&nbsp; <a href={focused.news.news_url} target="_blank" rel="noreferrer">News search</a></>}
      </div>
    </Section>
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
      {/* ORDER IS THE ARGUMENT. This column used to run hub -> hidden winners -> verdict ->
          case, which put a peer ranking between the company and the reason for its verdict, and
          left the verdict itself fourth on the page even though the hub had already named it two
          panels earlier. The order below is the four questions a reader actually asks, in the
          order they ask them: who is this and what do we say · why · how does that sit against
          its peers · what else is going on. */}
      {lv >= 2 && classification}
      {lv >= 2 && <CasePanel />}
      {/* At level 3 the matrix panel already lists the hidden winners beside the plot, so this
          repeated the same four names on the same screen. It stays at level 2, where the matrix
          is not on the page and this is the only place they appear. */}
      {lv === 2 && !simple && (
        <div className="panel-block">
          <BarsPanel title="Hidden winners vs peer avg"
            subtitle={`${board.counts.showing} companies · avg ESG ${hw.peer_avg ?? '—'}`}
            rows={hw.rows} maxAbs={maxAbs} suffix="%"
            footer={board.hidden_winners.basis === 'disagreement'
              ? 'Bar = how far our evidence puts the company above where its published score does. Click a name to focus it.'
              : "Bar = live Digital/AI signal — the divergence the rating can't see. Click a name to focus it."}
            onFocus={focusByTicker} />
        </div>
      )}
      {!hasPillars && checkPanel}
      {/* Price and news are both short and both context. Stacked full-width they read as two
          more findings; side by side they read as the footnote they are. */}
      {lv >= 2 && (
        <div className="deep-row">
          {lv >= 3 && pricePanel}
          {newsPanel}
        </div>
      )}
      {!hasPillars && cta}
    </div>
  )
}
