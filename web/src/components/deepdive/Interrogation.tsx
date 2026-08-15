import { useRef, useState } from 'react'
import { api } from '../../api'
import type { Entry, Envelope, NarrowedQuestion } from '../../types'
import { AXIS_META, Spinner } from '../ui'
import { useStore } from '../../store'

const QUICK_REPLIES: Record<string, string[]> = {
  mandate: ['Risk — downside protection', 'Return — outperformance', 'Compliance'],
  time_horizon: ['A near-term catalyst', 'A structural concern'],
  blind_spot: ['Undisclosed AI / digital risk', 'Not sure — what should I watch?'],
  materiality: ['Yes, it’s material here', 'Maybe it’s the wrong lens'],
}
const MAX_QUESTIONS = 5

interface Turn { user: string; env: Envelope; raw: string }

function AxisBadge({ env }: { env: Envelope }) {
  if (env.type === 'narrowed') return <span className="axis-badge narrowed">✅ Narrowed question</span>
  const meta = env.axis ? AXIS_META[env.axis] : undefined
  if (meta) return <span className="axis-badge">{meta.icon} {meta.name}</span>
  return <span className="axis-badge challenge">{env.type === 'challenge' ? '⚡ Challenge' : '🔍 Question'}</span>
}

export default function Interrogation({ entry, onDone }: {
  entry: Entry
  onDone: (nq: NarrowedQuestion) => void
}) {
  const { toast } = useStore()
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const msgsRef = useRef<{ role: string; content: string }[]>([])

  const company = entry.company
  const last = turns.length > 0 ? turns[turns.length - 1].env : null
  const questionCount = turns.filter(t => t.env.type !== 'narrowed').length

  const submit = async (userText: string, force = false) => {
    const text = userText.trim()
    if (busy || (!force && !text)) return
    setBusy(true)
    setError('')
    const messages = force
      ? msgsRef.current
      : [...msgsRef.current, { role: 'user', content: text }]
    try {
      const res = await api.stage1Ask({
        messages,
        turns: force ? MAX_QUESTIONS : questionCount,
        ticker: entry.ticker,
        force,
      })
      const env = res.envelope
      msgsRef.current = [...messages, { role: 'assistant', content: res.raw }]
      const nextTurns = [...turns, { user: force ? '' : text, env, raw: res.raw }]
      setTurns(nextTurns)
      if (env.done) {
        const trail = nextTurns.map(t => ({
          axis: t.env.axis, type: t.env.type, text: t.env.text, rationale: t.env.rationale,
        }))
        const nqRes = await api.stage1Narrow({ trail, final_env: env })
        onDone(nqRes.narrowed_q)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t reach the model.')
      toast('Interrogation hiccup — you can retry.', 'bad')
    } finally {
      setBusy(false)
    }
  }

  const undo = () => {
    if (turns.length === 0 || busy) return
    setTurns(t => t.slice(0, -1))
    const m = msgsRef.current
    if (m.length >= 2 && m[m.length - 1].role === 'assistant' && m[m.length - 2].role === 'user') {
      msgsRef.current = m.slice(0, -2)
    }
  }

  const chips = last && (last.type === 'question' || last.type === 'challenge')
    ? (last.suggested_replies.length > 0 ? last.suggested_replies : QUICK_REPLIES[last.axis ?? ''] ?? [])
    : []

  return (
    <div>
      <div className="chat-thread">
        {turns.map((t, i) => (
          <div key={i} style={{ display: 'contents' }}>
            {t.user && <div className="msg user"><div className="bubble">{t.user}</div></div>}
            <div className="msg ai">
              <div className="bubble">
                <AxisBadge env={t.env} />
                <div>{t.env.text}</div>
                {t.env.rationale && t.env.type !== 'narrowed' && (
                  <div className="rationale">💭 Why I'm asking: {t.env.rationale}</div>
                )}
                {t.env._parse_failed && (
                  <div className="rationale">⚠️ The model didn't return valid JSON for this turn.</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {busy && <Spinner label="Thinking about what to ask next…" />}
      {error && <div className="error-note">{error}</div>}

      {!busy && (
        <>
          {chips.length > 0 && (
            <>
              <div className="cc-muted">💡 {last?.suggested_replies.length ? 'Suggested replies:' : 'Quick replies:'}</div>
              <div className="quick-row">
                {chips.map((c, i) => (
                  <button key={i} className="btn" onClick={() => void submit(c)}>{c}</button>
                ))}
              </div>
            </>
          )}

          {turns.length > 0 && (
            <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
              <button className="btn" onClick={undo} disabled={turns.length === 0}>↩︎ Undo last answer</button>
              <button className="btn btn-primary" style={{ flex: 1 }}
                onClick={() => void submit('', true)}>
                → I've said enough — narrow it & continue
              </button>
            </div>
          )}
          {turns.length > 0 && (
            <div className="cc-muted">Question {questionCount} of up to {MAX_QUESTIONS}.</div>
          )}

          <div className="chat-form">
            <input className="input" value={input}
              placeholder={turns.length > 0
                ? 'Your answer…'
                : `What do you want to understand about ${company.company}?`}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') { void submit(input); setInput('') }
              }} />
            <button className="btn btn-primary" onClick={() => { void submit(input); setInput('') }}>Ask →</button>
          </div>
        </>
      )}
    </div>
  )
}
