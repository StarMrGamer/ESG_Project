import { useCallback, useEffect, useRef, useState } from 'react'
import { streamStage2 } from '../../api'
import type { Entry, NarrowedQuestion, Stage2Answer } from '../../types'
import { useStore } from '../../store'

const RAG_LABELS: Record<string, string> = {
  live: '🦆 Retrieved {n} live source(s) from DuckDuckGo (+ AI summary when available).',
  cache: '🗃️ Loaded {n} DuckDuckGo source(s) from cache.',
  offline: '📴 Couldn\'t fetch usable DuckDuckGo sources — reasoning on the data.',
  disabled: '🔌 Live retrieval is off — reasoning on the data.',
}

type Phase = 'idle' | 'rag' | 'reasoning' | 'done' | 'error'

export default function Stage2Runner({ entry, nq, onAnswer, autoStart }: {
  entry: Entry
  nq: NarrowedQuestion
  onAnswer: (a: Stage2Answer) => void
  autoStart?: boolean
}) {
  const { settings, saveEntry, refreshBoard } = useStore()
  const [phase, setPhase] = useState<Phase>('idle')
  const [ragLine, setRagLine] = useState('')
  const [ragError, setRagError] = useState('')
  const [phaseLabel, setPhaseLabel] = useState('Competing against the stale rating…')
  const [raw, setRaw] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(() => {
    setPhase('rag')
    setRagLine('🌐 Retrieving live ESG context (RAG)…')
    setRagError('')
    setError('')
    setRaw('')
    const ctrl = new AbortController()
    abortRef.current = ctrl
    streamStage2(
      { ticker: entry.ticker, nq, use_rag: settings.ragEnabled, top_k: settings.ragTopK },
      {
        onRag: r => {
          const label = (RAG_LABELS[r.status] || '{n} source(s).').replace('{n}', String(r.snippets))
          setRagLine(label)
          if (r.status === 'offline' && r.error) setRagError(r.error)
          setPhase('reasoning')
        },
        onPhase: label => setPhaseLabel(label),
        onDelta: text => setRaw(prev => prev + text),
        onAnswer: payload => {
          setPhase('done')
          saveEntry({ ...entry, answer: payload.answer, narrowed_q: payload.narrowed_q })
          refreshBoard()
          onAnswer(payload.answer)
        },
        onError: err => {
          setPhase('error')
          setError(err.message)
        },
      },
      ctrl.signal,
    ).catch(e => {
      if ((e as Error).name !== 'AbortError') {
        setPhase('error')
        setError(e instanceof Error ? e.message : String(e))
      }
    })
  }, [entry, nq, settings.ragEnabled, settings.ragTopK, saveEntry, refreshBoard, onAnswer])

  useEffect(() => {
    if (!autoStart) return
    run()
    return () => {
      abortRef.current?.abort()
      abortRef.current = null
    }
  }, [autoStart, run])

  useEffect(() => () => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  if (phase === 'idle') {
    return (
      <div>
        <div className="cc-muted">
          A FRESH DeepSeek agent reasons over Layer A + its history + Layer B
          {settings.ragEnabled
            ? ', grounded by ASEAN-scoped context it fetches live (RAG). '
            : '. '}
          It sees only the narrowed-question baton — not the interrogation chat.
        </div>
        <div style={{ marginTop: 10 }}>
          <button className="btn btn-primary" onClick={run}>Reason over the data →</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="s2-status">
        <div className={`s2-line ${phase !== 'rag' ? 'on' : ''}`}>
          {phase === 'rag' ? <span className="spinner" /> : <span>✓</span>}
          <span>{ragLine}</span>
        </div>
        {ragError && <div className="cc-muted">↳ {ragError}</div>}
        {(phase === 'reasoning' || phase === 'done') && (
          <div className="s2-line on">
            {phase === 'reasoning' ? <span className="spinner" /> : <span>✓</span>}
            <span>{phase === 'done' ? 'Done — here’s where we compete.' : `⚔️ ${phaseLabel}`}</span>
          </div>
        )}
      </div>

      {phase === 'reasoning' && raw && (
        <div style={{ marginTop: 8 }}>
          <button className="btn btn-sm btn-ghost" onClick={() => setShowRaw(s => !s)}>
            {showRaw ? '▾ Hide' : '▸ Watch'} the model stream
          </button>
          {showRaw && <div className="raw-stream">{raw}</div>}
        </div>
      )}

      {phase === 'error' && (
        <>
          <div className="error-note">
            ⚠️ {error || 'Something went wrong reaching the model — usually a network blip or a wrong model name (try setting DEEPSEEK_MODEL).'}
          </div>
          <button className="btn" onClick={run}>↻ Retry</button>
        </>
      )}
    </div>
  )
}
