import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import { Spinner } from '../ui'
import type { ClientBrief, ClientSummary } from '../../types'

/**
 * The analyst's book: a roster on the left, the selected client's pre-meeting brief on the right.
 *
 * The brief answers the four questions a sell-side analyst is actually asked in a client call —
 * what changed, where we are away from the rating, why we might be wrong, and what we do not
 * know. The third of those is the one that makes this a research tool rather than a marketing
 * deck, so the case AGAINST is given the same weight as the case for and is never collapsed.
 *
 * It carries no recommendation, no target and no ranking, and says so at the foot of the page.
 * The brief is composed by rule from a finished run — no model runs — so the same run always
 * produces the same document, which is the property that matters when it goes in front of an
 * institutional account.
 */

const ACCOUNT_LABEL: Record<string, string> = {
  long_only: 'Long only', hedge_fund: 'Hedge fund', pension: 'Pension',
  insurer: 'Insurer', sovereign: 'Sovereign', private_bank: 'Private bank',
}

const CHANGE_TONE: Record<string, string> = {
  label_move: 'is-major', confidence_move: 'is-mid',
  evidence_added: 'is-mid', momentum_move: '',
}

function pct(v: number | null | undefined) {
  return typeof v === 'number' ? `${Math.round(v * 100)}` : '—'
}
function sig(v: number | null | undefined, d = 3) {
  return typeof v === 'number' ? (v >= 0 ? '+' : '') + v.toFixed(d) : '—'
}

export default function ClientsTab() {
  const { setFocus, openEvidence } = useStore()
  const [roster, setRoster] = useState<ClientSummary[] | null>(null)
  const [selected, setSelected] = useState('')
  const [brief, setBrief] = useState<ClientBrief | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancel = false
    api.clients()
      .then(d => {
        if (cancel) return
        setRoster(d.clients)
        if (d.clients.length && !selected) setSelected(d.clients[0].client_id)
      })
      .catch(e => { if (!cancel) setError(String(e.message || e)) })
    return () => { cancel = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) return
    let cancel = false
    setLoading(true); setError(''); setBrief(null)
    api.clientBrief(selected)
      .then(b => { if (!cancel) setBrief(b) })
      .catch(e => { if (!cancel) setError(String(e.message || e)) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [selected])

  if (error && !roster) return <div className="panel-block"><div className="error-note">{error}</div></div>
  if (!roster) return <div className="panel-block"><Spinner label="Loading the book…" /></div>

  const d = brief?.delta

  return (
    <div className="clients-wrap">
      {/* ---- roster ------------------------------------------------------------------------ */}
      <aside className="panel-block client-roster">
        <div className="cc-h">The book</div>
        <div className="cc-muted">
          Fictional institutional accounts — no real client or holding appears in this build.
        </div>
        <ul className="client-list">
          {roster.map(c => (
            <li key={c.client_id}>
              <button
                className={`client-row ${c.client_id === selected ? 'on' : ''}`}
                onClick={() => setSelected(c.client_id)}>
                <span className="client-name">{c.name}</span>
                <span className="client-meta">
                  {ACCOUNT_LABEL[c.account_type] || c.account_type} · {c.coverage_n} names
                </span>
                <span className="client-meta">
                  {c.last_met ? `Last met ${c.last_met}` : 'Never met'}
                  {c.open_follow_ups > 0 && (
                    <span className="client-owed" title="Open follow-ups from the last meeting">
                      {c.open_follow_ups} owed
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* ---- brief -------------------------------------------------------------------------- */}
      <section className="client-brief">
        {loading && <div className="panel-block"><Spinner label="Composing the brief…" /></div>}
        {error && <div className="panel-block"><div className="error-note">{error}</div></div>}

        {brief && (
          <>
            <div className="panel-block brief-head">
              <div className="brief-title">
                <div>
                  <div className="cc-h">{brief.client.name}</div>
                  <div className="cc-muted">
                    {ACCOUNT_LABEL[brief.client.account_type] || brief.client.account_type}
                    {' · '}{brief.client.desk}
                    {' · mandate '}<b>{brief.client.mandate}</b>
                    {' · '}{brief.positions.length} of {brief.client.coverage_n} names
                  </div>
                </div>
                <a className="btn" href={api.clientBriefMarkdownUrl(brief.client.client_id)}
                   target="_blank" rel="noreferrer"
                   title="The same brief as a document, composed by rule from this run">
                  Export brief
                </a>
              </div>
              {brief.brief_note && <div className="brief-note">{brief.brief_note}</div>}
              <div className="cc-muted brief-run">
                Run <code>{brief.run_id}</code> · evidence as of {brief.as_of} · composed by rule,
                no model involved
              </div>
            </div>

            {/* 1 — what changed */}
            <div className="panel-block">
              <div className="cc-h">What changed since you last spoke</div>
              {!d?.has_baseline ? (
                <div className="cc-muted">{d?.note}</div>
              ) : d.changes.length === 0 ? (
                <div className="cc-muted">
                  Nothing material moved across the {d.covered} covered names since {d.since}.
                </div>
              ) : (
                <>
                  <div className="cc-muted">
                    Since {d.since} — measured against the snapshot this client was actually
                    shown, not against what today's config would have said back then.
                  </div>
                  <ul className="delta-list">
                    {d.changes.map(ch => (
                      <li key={ch.company_id} className={`delta-row ${CHANGE_TONE[ch.kind] || ''}`}>
                        <button className="delta-name"
                          onClick={() => { setFocus(ch.company_id) }}
                          title="Focus this company on the board">
                          {ch.company}
                        </button>
                        <span className="delta-note">{ch.note}</span>
                        <span className="delta-ev">
                          {ch.signals_from} → {ch.signals_to} signals
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="cc-muted">
                    {d.unchanged} of {d.covered} names unchanged.
                  </div>
                </>
              )}
            </div>

            {/* 2 — still owed */}
            {brief.open_follow_ups.length > 0 && (
              <div className="panel-block">
                <div className="cc-h">Still owed from last time</div>
                <ul className="owed-list">
                  {brief.open_follow_ups.map((f, i) => (
                    <li key={i}>
                      <span>{f.text}</span>
                      <span className="cc-muted"> — since {f.since}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 3 — the positions */}
            <div className="panel-block">
              <div className="cc-h">Where we are away from the rating</div>
              <div className="ind-scroll">
                <table className="ind-table brief-table">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Our read</th>
                      <th className="num">Rating pct</th>
                      <th className="num">Disagreement</th>
                      <th className="num">Confidence</th>
                      <th className="num">Evidence</th>
                      <th>Pipeline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {brief.positions.map(p => (
                      <tr key={p.company_id}>
                        <td>
                          <button className="ind-sector"
                            onClick={() => openEvidence(p.company_id)}
                            title="Open the evidence behind this verdict">
                            {p.company}
                          </button>
                          {p.delisted && <span className="ind-via">delisted</span>}
                        </td>
                        <td>{p.label_display}</td>
                        <td className="num">{pct(p.rating_percentile)}</td>
                        <td className="num">{sig(p.disagreement)}</td>
                        <td className="num">{sig(p.confidence, 2).replace('+', '')}</td>
                        <td className="num">{p.signal_count}</td>
                        <td>
                          {p.pipeline?.bucket
                            ? <span className={`badge tone-${p.pipeline.tone}`}>{p.pipeline.display}</span>
                            : <span className="cc-muted">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="cc-muted">
                Ordered by the size of the disagreement. This is not a ranking of the names
                against each other and carries no view on any of them.
              </div>
            </div>

            {/* 4 — why we might be wrong */}
            <div className="panel-block">
              <div className="cc-h">Why we might be wrong</div>
              <div className="cc-muted">
                What the client is likely to push on, and the dated answer. Sourced from the same
                rules that produced the verdict — a brief that only lists reasons to agree gets
                you ambushed.
              </div>
              {brief.objections.length === 0 && (
                <div className="cc-muted">
                  The rules surfaced no specific challenge on these names. That is not the same as
                  there being none.
                </div>
              )}
              <ul className="obj-list">
                {brief.objections.map(o => (
                  <li key={o.company_id} className="obj-row">
                    <div className="obj-head">
                      <button className="ind-sector" onClick={() => openEvidence(o.company_id)}>
                        {o.company}
                      </button>
                      <span className="obj-kind">{o.kind.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="obj-challenge">“{o.challenge}”</div>
                    <div className="obj-answer">{o.our_answer}</div>
                    {o.what_would_move_it && (
                      <div className="obj-margin">{o.what_would_move_it}</div>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            {/* 5 — what we do not know */}
            {brief.unknowns.length > 0 && (
              <div className="panel-block">
                <div className="cc-h">What we do not know</div>
                <div className="cc-muted">
                  Stated rather than omitted. An analyst who opens with their own gaps is harder
                  to catch out than one who waits to be.
                </div>
                <ul className="owed-list">
                  {brief.unknowns.map((u, i) => (
                    <li key={i}><b>{u.company}</b> — {u.gap}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* 6 — origination */}
            {brief.origination && (
              <div className="panel-block">
                <div className="cc-h">Origination across this book</div>
                <div className="nmk-strip">
                  <span><b>N {brief.origination.N}</b> issuers</span>
                  <span><b>M {brief.origination.M}</b> bond-ready</span>
                  <span><b>K {brief.origination.K}</b> review list</span>
                </div>
                <div className="cc-muted">
                  Disjoint by rule: M excludes anything already issuing, K is the explicit
                  remainder we disagree about but cannot place.
                </div>
              </div>
            )}

            <div className="panel-block brief-disclaimer">{brief.disclaimer}</div>
          </>
        )}
      </section>
    </div>
  )
}
