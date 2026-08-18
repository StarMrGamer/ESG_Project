import { useEffect, useState } from 'react'
import { useStore } from '../../store'
import { api } from '../../api'
import type { NarrowedQuestion, Stage2Answer, TierKey } from '../../types'
import Interrogation from './Interrogation'
import Stage2Runner from './Stage2Runner'
import AnswerPanel from './AnswerPanel'
import { known, Spinner } from '../ui'
import BenchmarkPanel from '../benchmark/BenchmarkPanel'

/**
 * The relay, drawn as three stations.
 *
 * Each stage hands the next a verified contract output — that baton IS the architecture, and a
 * row of small chips never showed it. Naming the baton under each station is what turns three
 * screens into one visible pipeline for someone watching a demo.
 */
const STAGES: { n: number; name: string; what: string; baton: string }[] = [
  { n: 1, name: 'Interrogate', what: 'Adaptive questions along four ESG-native axes. Never answers.',
    baton: 'baton · NarrowedQuestion' },
  { n: 2, name: 'Compete', what: 'Reasons over the data, the history and live retrieval — and disagrees.',
    baton: 'baton · Stage2Answer' },
  { n: 3, name: 'Answer', what: 'The verdict, the chain of thought, the evidence and the sources.',
    baton: 'output' },
]

function StageRail({ idx }: { idx: number }) {
  return (
    <div className="stage-rail" role="list" aria-label="Three-stage relay">
      {STAGES.map((st, i) => (
        <div key={st.n} role="listitem"
          className={`stage-card ${i < idx ? 'done' : i === idx ? 'on' : ''}`}>
          <span className="stage-num">{i < idx ? '✓' : st.n}</span>
          <span className="stage-name">{st.name}</span>
          <span className="stage-what">{st.what}</span>
          <span className="stage-baton">{st.baton}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Which risk tiers this company clears, from the engine record for the run on screen. The tiers
 * were only ever visible as a filter on the matrix, so during a deep dive — the moment you most
 * want to know whether this name survives a conservative screen — they were nowhere.
 */
function TierBadges({ ticker }: { ticker: string }) {
  const { board, settings } = useStore()
  const engine = board?.engine
  const rec = engine?.records?.[ticker]
  if (!engine || !rec) return null
  const keys = Object.keys(engine.tiers) as TierKey[]
  return (
    <div className="tier-badges">
      <span className="cc-muted" style={{ marginTop: 0 }}>Clears risk tier</span>
      {keys.map(k => (
        <span key={k}
          className={`tier-badge ${rec.tiers?.[k] ? 'on' : ''} ${settings.tier === k ? 'is-current' : ''}`}
          title={`${engine.tier_rules[k]}${rec.tiers?.[k] ? '' : ' — this company does not clear it.'}`}>
          {rec.tiers?.[k] ? '✓' : '·'} {engine.tiers[k]}
        </span>
      ))}
      <span className="cc-muted" style={{ marginTop: 0 }}>
        · {engine.half_life_days}d decay · {rec.signal_count} signals
      </span>
    </div>
  )
}

export default function DeepDive({ ticker, mode }: { ticker: string; mode: 'compete' | 'interrogate' }) {
  const { entries, goDashboard, settings, saveEntry } = useStore()
  const cached = entries[ticker]
  const [entry, setEntry] = useState(cached ?? null)
  const [loading, setLoading] = useState(!cached)

  const skipInterrogation = mode === 'compete' || Boolean(cached?.answer)
  const [s1Done, setS1Done] = useState(skipInterrogation)
  const [narrowedQ, setNarrowedQ] = useState<NarrowedQuestion | null>(
    cached?.narrowed_q ?? (mode === 'compete' ? cached?.default_nq ?? null : null),
  )
  const [answer, setAnswer] = useState<Stage2Answer | null>(cached?.answer ?? null)

  useEffect(() => {
    if (cached) { setEntry(cached); return }
    let cancel = false
    api.entry(ticker, settings.demo)
      .then(e => {
        if (cancel) return
        setEntry(e)
        saveEntry(e)
        if (mode === 'compete' && !e.answer && !e.narrowed_q) setNarrowedQ(e.default_nq)
      })
      .catch(() => { if (!cancel) goDashboard() })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker])

  if (loading || !entry) return <Spinner label="Opening the deep dive…" />

  const company = entry.company
  const snap = entry.snap
  const origin = company._origin || 'sample'
  const stepIdx = answer ? 2 : s1Done ? 1 : 0
  const hb = snap.score_higher_better

  const reset = () => {
    setS1Done(false)
    setNarrowedQ(null)
    setAnswer(null)
  }

  return (
    <div className="dd-shell">
      <div className="dd-top">
        <button className="btn" onClick={goDashboard}>← Dashboard</button>
        <h3>Deep dive</h3>
      </div>

      <div className="dd-hero">
        <h2>{company.company} · <kbd className="kbd">{company.ticker}</kbd></h2>
        <div className="cc-muted">
          {company.sector} · <span className="origin-badge">{entry.origin_badge}</span>
        </div>
        <div className="cc-muted">{entry.origin_disclaimer}</div>
        {origin === 'live' && (company._build_status === 'thin' || company._build_status === 'offline') && (
          <div className="banner-note">
            This live profile is <b>sparse</b> — public sources didn't yield much
            {company._build_status === 'offline' && ' and live retrieval couldn’t reach the network'}.
            Grounded-only mode marks unverified facts “unknown”, so the answer may be limited.
            {company._build_error && <><br />↳ retrieval reason: <i>{company._build_error}</i></>}
          </div>
        )}

        <div className="metric-strip">
          <div className="metric-cell">
            <div className="l">{hb ? 'ESG score (Layer A)' : 'ESG rating (Layer A)'}</div>
            <div className="v">{known(snap.rating) ? snap.rating : 'unknown'}</div>
          </div>
          <div className="metric-cell">
            <div className="l">{hb ? 'ESG band' : 'Risk band'}</div>
            <div className="v">{snap.band || '—'}</div>
          </div>
          <div className="metric-cell">
            <div className="l">Momentum E·S·G</div>
            <div className="v">{snap.arrows.E} {snap.arrows.S} {snap.arrows.G}</div>
          </div>
          <div className="metric-cell">
            <div className="l">Red flags</div>
            <div className="v">{snap.red_flags}</div>
          </div>
          <div className="metric-cell">
            <div className="l">Coverage</div>
            <div className="v">{snap.coverage}/{snap.coverage_total}</div>
          </div>
        </div>

        {entry.breakdown && (
          <div className="cc-muted">
            ESG breakdown — E {entry.breakdown.e_score.toFixed(0)} · S {entry.breakdown.s_score.toFixed(0)} ·
            G {entry.breakdown.g_score.toFixed(0)} · overall {entry.breakdown.overall.toFixed(0)} (0–100, higher=better)
          </div>
        )}
        <TierBadges ticker={ticker} />
        {company._data_provenance && <div className="cc-muted">{String(company._data_provenance)}</div>}
      </div>

      {/*
        Benchmarks sit above the relay on purpose: "how does this compare" is the question a
        reader has before they have any interest in a three-stage argument, and an uploaded file
        reaches this exact panel with nothing extra wired.
      */}
      <BenchmarkPanel benchmark={entry.benchmark} quote={entry.quote} />

      {entry.financial.have && (
        <div className="panel-block" style={{ marginBottom: 14 }}>
          <div className="cc-h">Financial snapshot</div>
          <div className="ev-grid">
            {(settings.simplified ? entry.financial.simple : entry.financial.rows).map(r => (
              <div className="metric-cell" key={r.label}>
                <div className="l">{r.label}</div>
                <div className="v" style={{ fontSize: 15 }}>{r.value}</div>
              </div>
            ))}
          </div>
          <div className="cc-muted">Illustrative figures — not real market data.</div>
        </div>
      )}

      <StageRail idx={stepIdx} />

      {!s1Done && (
        <div className="panel-block" style={{ marginBottom: 14 }}>
          <b>See the competing read now, or interrogate a sharper question first</b>
          <div className="dd-actions">
            <button className="btn btn-primary" onClick={() => {
              setNarrowedQ(entry.default_nq)
              setS1Done(true)
            }}>Compete now (default question)</button>
          </div>
          <hr className="divider" />
          <h3 style={{ margin: '0 0 8px', font: '600 16px/1.2 var(--r-font)' }}>1 · Interrogate</h3>
          <Interrogation entry={entry} onDone={nq => { setNarrowedQ(nq); setS1Done(true) }} />
        </div>
      )}

      {s1Done && narrowedQ && (
        <>
          <div className="cc-class cc-class-good" style={{ marginTop: 4 }}>
            <div className="cc-class-h">Narrowed question (Stage 1 → baton)</div>
            <div className="cc-class-line">{narrowedQ.narrowed_question}</div>
            <div className="cc-chips">
              <span className="cc-chip">Mandate · {narrowedQ.mandate}</span>
              <span className="cc-chip">Sector · {narrowedQ.sector}</span>
              <span className="cc-chip">Horizon · {narrowedQ.horizon}</span>
            </div>
          </div>

          <div className="panel-block" style={{ marginTop: 14 }}>
            <h3 style={{ margin: '0 0 10px', font: '600 16px/1.2 var(--r-font)' }}>2 · Compete over data</h3>
            {answer == null && (
              <Stage2Runner entry={entry} nq={narrowedQ} onAnswer={setAnswer}
                autoStart={mode === 'compete'} />
            )}

            {answer && (
              <>
                <h3 style={{ margin: '16px 0 10px', font: '600 16px/1.2 var(--r-font)' }}>3 · The competing answer</h3>
                <AnswerPanel answer={answer} company={company} narrowed={narrowedQ} />
                <div style={{ marginTop: 12 }}>
                  <button className="btn" onClick={reset}>Ask a different question about this company</button>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
