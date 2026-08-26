import { useState } from 'react'
import type { CompanyB, NarrowedQuestion, Stage2Answer } from '../../types'
import { AXIS_META, download, known } from '../ui'
import { HistoryChart } from '../charts'
import { useStore } from '../../store'

const FIELDS = ['question_to_ask', 'what_rating_sees', 'what_we_see', 'check_before_monday', 'competes_summary'] as const

function falsifiabilityLine(company: CompanyB): string | null {
  const ai = company.layer_b?.digital_ai_signal
  if (!ai) return null
  const disclosure = ai.ai_disclosure_level
  const velocity = ai.ai_governance_hiring_velocity
  if (!(known(disclosure) && known(velocity))) return null
  const name = company.company || 'the company'
  return `${name} publishing a credible AI-governance disclosure (today: “${disclosure}”), or the ${velocity} hiring signal reversing — either would blunt our disagreement.`
}

function monthsStale(asOf: string): number | null {
  const d = new Date(String(asOf).slice(0, 10))
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const months = (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth())
    - (now.getDate() < d.getDate() ? 1 : 0)
  return Math.max(months, 0)
}

function dirArrow(direction: string): { cls: string; arrow: string } {
  const d = (direction || '').toLowerCase()
  if (d === 'improving') return { cls: 'cc-pos', arrow: '↑' }
  if (d === 'declining') return { cls: 'cc-neg', arrow: '↓' }
  return { cls: 'cc-flat', arrow: '→' }
}

function scoreNum(v: string): number | null {
  const m = String(v || '').match(/-?\d+(?:\.\d+)?/)
  return m ? parseFloat(m[0]) : null
}

export default function AnswerPanel({ answer, company, narrowed }: {
  answer: Stage2Answer
  company: CompanyB
  narrowed: NarrowedQuestion | null
}) {
  const { settings } = useStore()
  const [showRaw, setShowRaw] = useState(false)

  const allUnknown = FIELDS.every(k => (answer[k] || 'unknown') === 'unknown')
  const failed = Boolean(answer._parse_failed || allUnknown)
  const flip = falsifiabilityLine(company)
  const stale = monthsStale(company.layer_a?.as_of_date || '')
  const origin = company._origin || 'sample'

  const trailSteps = (narrowed?.trail || []).filter(t => t.type === 'question' || t.type === 'challenge')
  const history = company.layer_a_history
  const historyPoints = (history?.series || [])
    .map(p => ({ as_of: p.as_of, value: scoreNum(p.esg_score_static), label: p.esg_score_static }))
    .filter(p => p.value != null) as { as_of: string; value: number }[]
  const controversies = company._controversies || []
  const buildSources = company._sources || []
  const aiSummary = answer._ai_summary

  const exportJson = () => download(
    `stage2-answer-${company.ticker.replace(/\W+/g, '_')}.json`,
    JSON.stringify({ narrowed_question: narrowed, answer }, null, 2),
  )
  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify({ narrowed_question: narrowed, answer }, null, 2))
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div>
      <div className="cc-muted">
        Subject: <b>{company.company}</b> · <kbd className="kbd">{company.ticker}</kbd> · {company.sector}
        {origin === 'sample' && ' · ⚠️ Illustrative sample — placeholder data.'}
        {origin === 'live' && ' · Built live from public sources — not investment advice.'}
        {origin === 'upload' && ' · Built from your uploaded data — not investment advice.'}
        {origin === 'dataset' && ' · Built from pre-scored local dataset values — not investment advice.'}
      </div>

      {failed && (
        <div className="error-note" style={{ marginTop: 10 }}>
          {answer._parse_failed
            ? '⚠️ Stage 2 reached the model but couldn’t parse a clean answer — usually a transient model hiccup or a wrong model name. Reason over the data again, or set DEEPSEEK_MODEL (e.g. deepseek-chat).'
            : origin === 'live'
              ? `⚠️ Couldn't build a competing answer for ${company.company} — the live profile came up too thin${answer._rag_status === 'offline' ? ' because live retrieval couldn\'t reach the network' : ''}. Grounded-only mode keeps anything it can't verify as “unknown”, so there wasn't enough to compete on. Try: reason again, upload your own ESG data, or load the offline sample.`
              : origin === 'upload'
                ? `⚠️ Couldn't build a competing answer from your uploaded data for ${company.company} — it may be missing the Layer A / Layer B fields the reasoner needs.`
                : `Stage 2 couldn't produce an answer for ${company.company}. Try reasoning again.`}
        </div>
      )}

      {(settings.simplified === false || answer._parse_failed) && answer._raw != null && (
        <details className="expander">
          <summary>🐞 raw Stage 2 output</summary>
          <pre className="raw-stream">{answer._raw || '<empty>'}</pre>
        </details>
      )}

      {!failed && (
        <>
          <h3 style={{ margin: '14px 0 4px' }}>⚔️ The verdict — where we disagree with the rating</h3>
          <div className="verdict-panel">
            <div className="h">⚔️ Where we compete</div>
            <div className="b">{answer.competes_summary || 'unknown'}</div>
          </div>
          {flip && (
            <div className="flip-panel">
              <div className="h">🔄 What would change our mind</div>
              {flip}
            </div>
          )}

          {answer.reasoning.length > 0 && (
            <details className="expander" open>
              <summary>🧠 Chain of thought ({answer.reasoning.length} steps)</summary>
              <ol className="cot-list">
                {answer.reasoning.map((r, i) => <li key={i}>{r}</li>)}
              </ol>
            </details>
          )}

          <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
            <button className="btn btn-sm" onClick={copyJson}>📋 Copy baton JSON</button>
            <button className="btn btn-sm" onClick={exportJson}>⬇ Download baton</button>
            {showRaw
              ? <button className="btn btn-sm btn-ghost" onClick={() => setShowRaw(false)}>hide raw</button>
              : null}
          </div>
        </>
      )}

      {trailSteps.length > 0 && (
        <details className="expander">
          <summary>🧭 How we narrowed your question — the ESG interrogation ({trailSteps.length} steps)</summary>
          <ol className="cot-list">
            {trailSteps.map((t, i) => {
              const meta = t.axis ? AXIS_META[t.axis] : undefined
              return (
                <li key={i}>
                  <b>{meta ? `${meta.icon} ${meta.name}` : '🔍 Question'}</b> — {t.text}
                </li>
              )
            })}
          </ol>
        </details>
      )}

      <h3 style={{ margin: '14px 0 4px' }}>🎯 The question</h3>
      <div className="cc-panel-body">{answer.question_to_ask || 'unknown'}</div>

      {/* THE HEADLINE. Everything else in a deep dive is working — the reasoning chain, the
          evidence trail, the pillar cards. This is the ANSWER: what the market thinks, what the
          evidence says, and the one thing to do about it. It used to sit as three loose elements
          in the middle of the page, so the single most important comparison in the product read
          as more body copy. Framed as one block, because the contrast BETWEEN the two panels is
          the argument — neither half means much alone.

          The two sides are deliberately not symmetrical. The rating recedes: muted, flat, no
          glow, and it carries its own age. Ours advances. That asymmetry IS the thesis rendered
          in CSS — a static snapshot against a live read — and making them look equal would be
          drawing the argument wrong. */}
      <div className="headline-block">
        <div className="headline-eyebrow">The answer · market view vs. reality</div>
        <div className="vs-grid">
          <div className="vs-panel rating">
            <div className="h">📊 What the rating sees</div>
            <div className="b">{answer.what_rating_sees || 'unknown'}</div>
            {stale != null && stale > 3 && (
              <div className="vs-age">⏳ This static view is ~{stale} months old.</div>
            )}
          </div>
          <div className="vs-panel we">
            <div className="h">🛰️ What we see</div>
            <div className="b">{answer.what_we_see || 'unknown'}</div>
          </div>
        </div>

        <div className="flip-panel headline-action" style={{ borderLeftColor: 'var(--r-pos)' }}>
          <div className="h" style={{ color: 'var(--r-pos)' }}>✅ Check before Monday — do this first</div>
          {answer.check_before_monday || 'unknown'}
        </div>
      </div>

      {!failed && (
        <>
          <h4 style={{ margin: '16px 0 4px' }}>Layer B — the evidence the rating can't see</h4>
          <div className="ev-grid">
            <div className="ev-card">
              <div className="h">Momentum (E·S·G)</div>
              {(['E', 'S', 'G'] as const).map(k => {
                const cell = company.layer_b?.momentum?.[k]
                if (!cell) return null
                const d = dirArrow(cell.direction)
                return (
                  <div className="ev-row" key={k}>
                    <span>{k === 'E' ? 'Environment' : k === 'S' ? 'Social' : 'Governance'}</span>
                    {/* Print the magnitude only when it IS one. It used to render
                        unconditionally, so an unknown magnitude beside a known direction read
                        "↑ unknown · improving" — which says less than the direction alone. */}
                    <b className={d.cls}>
                      {d.arrow}{known(cell.magnitude) ? ` ${cell.magnitude}` : ''}
                      {known(cell.direction) ? `${known(cell.magnitude) ? ' · ' : ' '}${cell.direction}` : ''}
                      {!known(cell.magnitude) && !known(cell.direction) ? ' unknown' : ''}
                    </b>
                  </div>
                )
              })}
            </div>
            <div className="ev-card">
              <div className="h">Digital / AI signal</div>
              <div className="ev-row"><span>AI-gov hiring velocity</span><b>{company.layer_b?.digital_ai_signal?.ai_governance_hiring_velocity || 'unknown'}</b></div>
              <div className="ev-row"><span>AI disclosure</span><b>{company.layer_b?.digital_ai_signal?.ai_disclosure_level || 'unknown'}</b></div>
              {known(company.layer_b?.digital_ai_signal?.gap_note) && (
                <div className="cc-muted" style={{ marginTop: 6 }}>{company.layer_b?.digital_ai_signal?.gap_note}</div>
              )}
            </div>
            <div className="ev-card">
              <div className="h">Conflicting signals</div>
              <div className="ev-row"><span>News sentiment</span><b>{company.layer_b?.conflicting_signals?.news_sentiment || 'unknown'}</b></div>
              <div className="ev-row"><span>Behaviour trend</span><b>{company.layer_b?.conflicting_signals?.behaviour_trend || 'unknown'}</b></div>
              {known(company.layer_b?.conflicting_signals?.conflict_note) && (
                <div className="cc-muted" style={{ marginTop: 6 }}>{company.layer_b?.conflicting_signals?.conflict_note}</div>
              )}
            </div>
            <div className="ev-card">
              <div className="h">Near-term catalyst</div>
              <div style={{ fontSize: 13, lineHeight: 1.55 }}>{company.layer_b?.near_term_catalyst || 'unknown'}</div>
            </div>
          </div>

          {history && (history.series || []).length > 0 && (
            <>
              <h4 style={{ margin: '16px 0 4px' }}>Historical static score vs the live signal</h4>
              {known(history.note) && <div className="cc-muted">{history.note}</div>}
              <div className="history-strip">
                {history.series.map((p, i) => (
                  <div className="history-cell" key={i}>
                    <div className="d">{p.as_of}</div>
                    <div className="s">{p.esg_score_static}</div>
                  </div>
                ))}
              </div>
              {historyPoints.length >= 2 && (
                <HistoryChart points={historyPoints} dark={settings.dark} />
              )}
              {known(history.trend_note) && <div className="cc-muted">{history.trend_note}</div>}
            </>
          )}

          {controversies.length > 0 && (
            <>
              <h4 style={{ margin: '16px 0 4px' }}>🚩 Red flags — leads to check, not verdicts</h4>
              <ul className="src-list">
                {controversies.map((c, i) => (
                  <li key={i}>
                    <span className="n">🚩</span>
                    <span>
                      {c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.title}</a> : c.title}
                      {c.snippet && <div className="cc-muted">{c.snippet}</div>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {aiSummary?.summary && (
            <>
              <h4 style={{ margin: '16px 0 4px' }}>🦆 DuckDuckGo AI summary — interpreted, not copied</h4>
              <div className="cc-panel-body">
                {aiSummary.summary}
                <div className="cc-muted" style={{ marginTop: 6 }}>
                  source: {aiSummary.source || 'DuckDuckGo'}
                  {aiSummary.url && <> · <a href={aiSummary.url} target="_blank" rel="noreferrer">link</a></>}
                </div>
              </div>
            </>
          )}

          {(answer.sources.length > 0 || buildSources.length > 0) && (
            <>
              <h4 style={{ margin: '16px 0 4px' }}>🔗 Live sources</h4>
              {answer.sources.length > 0 && (
                <ul className="src-list">
                  {answer.sources.map((s, i) => (
                    <li key={i}>
                      <span className="n">[{i + 1}]</span>
                      <span>{s.url
                        ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                        : s.title}</span>
                    </li>
                  ))}
                </ul>
              )}
              {buildSources.length > 0 && (
                <details className="expander">
                  <summary>📑 How this profile was built ({buildSources.length} source(s))</summary>
                  <ul className="src-list">
                    {buildSources.map((s, i) => (
                      <li key={i}>
                        <span className="n">·</span>
                        <span>{s.url
                          ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                          : s.title}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}

      <div className="cc-muted" style={{ marginTop: 14 }}>
        We disagree with the stale rating using a signal it can't see — we never say buy / sell / hold.
      </div>
    </div>
  )
}
