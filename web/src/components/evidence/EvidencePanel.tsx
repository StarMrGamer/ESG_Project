import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import VerdictSensitivity from '../future/VerdictSensitivity'
import ClaimVsEvidence from './ClaimVsEvidence'
import { useStore } from '../../store'
import { Spinner } from '../ui'
import type { Badges, EvidencePayload, HorizonKey, VerifyPayload } from '../../types'

/**
 * EvidencePanel — the three-click destination: card → evidence → source.
 *
 * Shows the two metadata badges (A4), every signal behind the score WITH its stored one-line
 * `rationale` (INSTRUCTIONS step 5) and its real source URL, and the on-chain verification
 * panel (C4) that recomputes each leaf hash, walks the Merkle path, and compares the root with
 * the anchored one — including the tamper demo that breaks it on purpose.
 */

function BadgeRow({ badges }: { badges: Badges }) {
  const cells = [
    { key: 'gb', b: badges.green_bond, label: 'Green bond' },
    { key: 'pf', b: badges.profitability, label: 'Profitability' },
  ]
  return (
    <div className="badge-row">
      {cells.map(({ key, b, label }) => {
        const inner = (
          <>
            <span className="badge-label">{label}</span>
            <b>{b.display}</b>
            {'traction' in b && b.traction && <i className="traction-pip" title="Traction evidence on a loss-maker">▲ traction</i>}
          </>
        )
        return b.url
          ? <a key={key} className={`badge tone-${b.tone}`} href={b.url} target="_blank"
            rel="noreferrer" title={`${b.note}\n\nOpens the evidence source.`}>{inner}</a>
          : <span key={key} className={`badge tone-${b.tone}`} title={b.note || 'No evidence URL on file yet.'}>{inner}</span>
      })}

      {/* CGSI's own delisting note, worn rather than hidden: a basket meant to be current
          holding two companies that went private in 2025 is a finding about static baskets,
          which is the argument the whole tool makes. */}
      {badges.delisted && (
        <span className={`badge tone-${badges.delisted.tone}`} title={badges.delisted.note}>
          <span className="badge-label">Listing</span>
          <b>{badges.delisted.value}</b>
        </span>
      )}

      {/* The INDUSTRY's bar. Deliberately worded as the industry's, and deliberately not
          differenced against the company — we hold no per-company emissions intensity here. */}
      {badges.sector_benchmark && (
        <span className="badge tone-neutral"
          title={`${badges.sector_benchmark.attribution}\n\n${badges.sector_benchmark.note}` +
                 (badges.sector_benchmark.caveat ? `\n\n${badges.sector_benchmark.caveat}` : '')}>
          <span className="badge-label">Industry bar ({badges.sector_benchmark.industry})</span>
          <b>{badges.sector_benchmark.value}</b>
          <i className="badge-sub">
            {badges.sector_benchmark.rank} of {badges.sector_benchmark.of} — vs sector peers
          </i>
        </span>
      )}
    </div>
  )
}

function Verification({ ticker, demo, horizon }:
  { ticker: string; demo: boolean; horizon: HorizonKey }) {
  const [payload, setPayload] = useState<VerifyPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = useCallback(async (tamper: boolean) => {
    setBusy(true); setErr('')
    try {
      setPayload(await api.verify({ ticker, demo, horizon, tamper }))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Verification failed.')
    } finally {
      setBusy(false)
    }
  }, [ticker, demo, horizon])

  return (
    <div className="panel-block verify-block">
      <div className="cc-h">On-chain verification</div>
      <div className="cc-muted">
        Recomputes every evidence hash, walks the Merkle path to the run's root, and compares it
        with the root anchored on the public chain. Proof on-chain, not data — no raw or licensed
        evidence ever leaves this machine.
      </div>
      {/*
        The claim discipline from the persona doc, on screen rather than only in a slide. A MATCH
        is an integrity proof, and the obvious question from a judge — "so you have verified the
        green bond?" — has to be answered before it is asked. The Radar informs; the analyst
        verifies. Saying so costs one line and losing that distinction costs the whole pitch.
      */}
      <div className="cc-muted verify-scope">
        <b>What this does not claim.</b> A match proves this evidence has not changed since the run
        was anchored. It does not make the underlying claim true, and it does not verify a green
        bond, a rating or a disclosure. The Radar surfaces what it found and where it came from —
        the analyst still does the verifying.
      </div>
      <div className="verify-actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => run(false)}>
          {busy ? 'Verifying…' : 'Verify this evidence'}
        </button>
        <button className="btn" disabled={busy} onClick={() => run(true)}
          title="Rehearsal demo: edit one character of one excerpt and watch verification fail.">
          Tamper demo
        </button>
      </div>
      {err && <div className="error-note">{err}</div>}
      {payload && (
        <div className={`verify-result ${payload.ok ? 'is-match'
          : payload.status === 'no_evidence' ? 'is-empty' : 'is-broken'}`}>
          <div className="verify-verdict">
            {payload.ok ? '✔ MATCH'
              : payload.status === 'no_evidence' ? '— NOTHING TO VERIFY'
                : '✘ NO MATCH'}
            {payload.tampered && <em> — one character changed, on purpose</em>}
            {payload.status === 'no_evidence' && (
              <em> — we hold no evidence leaves for this company in this run</em>
            )}
          </div>
          <dl className="verify-facts">
            <div><dt>run</dt><dd>{payload.run_id}</dd></div>
            <div><dt>leaves checked</dt><dd>{payload.rows.length} of {payload.leaf_count}</dd></div>
            <div><dt>stored root</dt><dd className="mono">{payload.stored_root.slice(0, 32)}…</dd></div>
            <div><dt>recomputed</dt><dd className="mono">{payload.recomputed_root.slice(0, 32)}…</dd></div>
            <div><dt>anchor</dt><dd>{payload.anchor_status}{payload.block_number ? ` · block ${payload.block_number}` : ''}</dd></div>
            {payload.chain_checked && (
              <div><dt>chain</dt><dd>{payload.chain_match ? `${payload.chain} root agrees` : `${payload.chain} root does NOT agree`}</dd></div>
            )}
            {payload.signer && <div><dt>signer</dt><dd className="mono">{payload.signer}</dd></div>}
          </dl>
          {payload.explorer_url && (
            <a className="btn" href={payload.explorer_url} target="_blank" rel="noreferrer">
              Open on {payload.chain} explorer ↗
            </a>
          )}
          {!payload.chain_checked && (
            <div className="cc-muted">
              {payload.note || 'No RPC configured — verified locally against the stored anchor record. '}
              The run is marked <b>{payload.anchor_status}</b> rather than silently unanchored.
            </div>
          )}
          {payload.rows.some(r => !r.leaf_ok) && (
            <div className="cc-muted">
              Broken leaves: {payload.rows.filter(r => !r.leaf_ok).map(r => r.leaf_id).join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function EvidencePanel({ ticker }: { ticker: string }) {
  const { settings, goDashboard, openDeepDive } = useStore()
  const [data, setData] = useState<EvidencePayload | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancel = false
    setData(null); setErr('')
    api.evidence(ticker, settings.demo, settings.horizon)
      .then(d => { if (!cancel) setData(d) })
      .catch(e => { if (!cancel) setErr(e instanceof Error ? e.message : String(e)) })
    return () => { cancel = true }
  }, [ticker, settings.demo, settings.horizon])

  if (err) return <div className="error-note">Couldn't load the evidence trail: {err}</div>
  if (!data) return <Spinner label="Reading the evidence trail…" />

  const r = data.record
  return (
    <div className="evidence-view">
      <div className="evidence-head">
        <div>
          <button className="btn" onClick={goDashboard}>‹ Dashboard</button>
          <h2>{data.company} <span className="cc-muted">{data.ticker}</span></h2>
          <div className="evidence-verdict">
            <span className={`legend-chip q-${r.label.replace('_', '-')}`}>{r.label_display}</span>
            <span>momentum <b className={r.composite_momentum >= 0 ? 'cc-pos' : 'cc-neg'}>
              {r.composite_momentum >= 0 ? '+' : ''}{r.composite_momentum.toFixed(2)}</b></span>
            <span>confidence <b>{r.composite_confidence.toFixed(2)}</b></span>
            <span title="Our momentum percentile minus the incumbent rating's percentile. Positive means we are more positive than the rating.">
              disagreement <b>{r.disagreement >= 0 ? '+' : ''}{r.disagreement.toFixed(2)}</b></span>
            <span>{r.signal_count} signals · breadth {data.breadth}</span>
          </div>
        </div>
        <div className="evidence-actions">
          <button className="btn btn-primary" onClick={() => openDeepDive(ticker, 'compete')}>
            Deep dive (Stage 1→2→3)
          </button>
        </div>
      </div>

      <BadgeRow badges={data.badges} />
      {data.metadata_note && <div className="cc-muted">{data.metadata_note}</div>}

      <div className="panel-block">
        <div className="cc-h">Where the score comes from</div>
        <div className="subcomp-grid">
          {Object.entries(data.subcomponents).map(([component, subs]) => (
            <div key={component} className="subcomp-col">
              <div className="subcomp-head">{component}
                <b className={(r.components[component] ?? 0) >= 0 ? 'cc-pos' : 'cc-neg'}>
                  {(r.components[component] ?? 0) >= 0 ? '+' : ''}{(r.components[component] ?? 0).toFixed(2)}
                </b>
              </div>
              {Object.entries(subs).map(([sub, cell]) => (
                <div key={sub} className="subcomp-row">
                  <span>{sub.replace(/_/g, ' ')}</span>
                  <i className={cell.momentum >= 0 ? 'cc-pos' : 'cc-neg'}>
                    {cell.momentum >= 0 ? '+' : ''}{cell.momentum.toFixed(2)}
                  </i>
                  <em>{cell.signal_count}</em>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="momentum-maths" title="Momentum is not a raw average: an extreme score
          has to be earned by evidence that is both one-sided and substantial.">
          <span>direction consensus <b>{r.direction_consensus >= 0 ? '+' : ''}{r.direction_consensus.toFixed(2)}</b></span>
          <span>×</span>
          <span>evidence weight {r.evidence_weight.toFixed(2)} → shrinkage <b>{r.shrinkage.toFixed(2)}</b></span>
          <span>=</span>
          <span>momentum <b className={r.composite_momentum >= 0 ? 'cc-pos' : 'cc-neg'}>
            {r.composite_momentum >= 0 ? '+' : ''}{r.composite_momentum.toFixed(2)}</b></span>
        </div>
        <div className="cc-muted">
          Baseline: {r.baseline_origin} ({r.baseline_basis.replace(/_/g, ' ')}) at percentile
          {' '}{(r.lseg_percentile * 100).toFixed(0)}%. Coverage {data.coverage.toFixed(2)} ·
          corroboration {data.corroboration.toFixed(2)} · mean source quality
          {' '}{data.mean_source_quality.toFixed(2)}.
        </div>
      </div>

      {/* Between "where the number came from" and "here is every row" sits the question a
          reviewer asks next: the evidence will change, so what is this actually standing on? */}
      <div className="panel-block">
        <VerdictSensitivity ticker={ticker} />
      </div>

      <div className="panel-block">
        <ClaimVsEvidence ticker={ticker} />
      </div>

      <div className="panel-block">
        <div className="cc-h">Evidence trail · {data.trail.length} signals</div>
        <div className="cc-muted">
          Every row is one dated, sourced signal, with the one-line rationale for why it was
          routed and weighted the way it was. Nothing here is generated: the excerpt is the
          source's own words.
        </div>
        {data.trail.length === 0 && (
          <div className="empty-note">
            No signals in the window — that is an honest answer, not a zero score.
          </div>
        )}
        <div className="trail">
          {data.trail.map(row => (
            <div className="trail-row" key={row.signal_id}>
              <div className="trail-when">
                <b>{row.published_at || 'undated'}</b>
                {row.date_basis !== 'stated' && (
                  <em title="The source states no exact date — the dataset as-of is used, and the row says so.">
                    {row.date_basis.replace(/_/g, ' ')}
                  </em>
                )}
              </div>
              <div className={`trail-dir ${row.direction > 0 ? 'cc-pos' : 'cc-neg'}`}>
                {row.direction > 0 ? '▲' : '▼'}
              </div>
              <div className="trail-body">
                <div className="trail-routes">
                  {row.routes.map(rt => (
                    <span key={`${rt.component}/${rt.subcomponent}`} className="route-chip">
                      {rt.component}/{rt.subcomponent.replace(/_/g, ' ')}
                    </span>
                  ))}
                  <span className="cc-muted">
                    materiality {row.materiality.toFixed(2)} · confidence {row.confidence.toFixed(2)}
                    {' · '}{row.source_type.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="trail-text">“{row.raw_text}”</div>
                <div className="trail-rationale" title="Stored per-signal justification">
                  {row.rationale}
                </div>
                <div className="trail-src">
                  {row.source_url
                    ? <a href={row.source_url} target="_blank" rel="noreferrer">source ↗</a>
                    : <span className="cc-muted">no source URL on file</span>}
                  <span className="cc-muted mono"> {row.model_version}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
        {data.foundation.basis && (
          <div className="cc-muted">
            Foundation evidence: {data.foundation.basis}
            {data.foundation.source_url && <> · <a href={data.foundation.source_url} target="_blank" rel="noreferrer">source</a></>}
          </div>
        )}
      </div>

      <Verification ticker={ticker} demo={settings.demo} horizon={settings.horizon} />
    </div>
  )
}
