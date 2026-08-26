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

/**
 * The four ESG-native axes, drawn as a map above the thread.
 *
 * The axis was already on every question as a small badge, but a badge only says where you are —
 * it never showed the shape being covered, so the interrogation read as an ordinary chatbot that
 * happened to be labelled. Laid out as a rail, the same four labels show what has been asked,
 * what is being asked now, and what is still open. That shape IS the pitch: this is interrogation
 * along ESG-native axes rather than a chat window.
 */
type AxisKey = 'materiality' | 'time_horizon' | 'mandate' | 'blind_spot'
const AXES: AxisKey[] = ['materiality', 'time_horizon', 'mandate', 'blind_spot']

const AXIS_ASKS: Record<AxisKey, string> = {
  materiality: 'Is this the ESG issue that actually moves this business?',
  time_horizon: 'A catalyst in months, or a structural shift over years?',
  mandate: 'Risk, return or compliance — what is the answer for?',
  blind_spot: 'What is not in the rating at all?',
}

function AxisMap({ covered, active }: { covered: Set<string>; active: string | null }) {
  return (
    <div className="axis-map" data-tour="axes">
      <div className="axis-map-h">
        ESG-native axes
        <span className="cc-muted">
          {covered.size} of {AXES.length} covered — each question maps to exactly one
        </span>
      </div>
      <div className="axis-rail">
        {AXES.map(a => {
          const meta = AXIS_META[a]
          const state = active === a ? 'on' : covered.has(a) ? 'done' : ''
          return (
            <div key={a} className={`axis-node ${state}`} title={AXIS_ASKS[a]}>
              <span className="axis-node-icon">{covered.has(a) && active !== a ? '✓' : meta.icon}</span>
              <span className="axis-node-name">{meta.name}</span>
              <span className="axis-node-ask">{AXIS_ASKS[a]}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface Turn { user: string; env: Envelope; raw: string }

function AxisBadge({ env }: { env: Envelope }) {
  if (env.type === 'narrowed') return <span className="axis-badge narrowed">✅ Narrowed question</span>
  const meta = env.axis ? AXIS_META[env.axis] : undefined
  if (meta) return <span className="axis-badge">{meta.icon} {meta.name}</span>
  return <span className="axis-badge challenge">{env.type === 'challenge' ? '⚡ Challenge' : '🔍 Question'}</span>
}


/**
 * One opener per ESG-native axis, so the first question a reader asks is already a question the
 * interrogation can do something with. The axes are Stage 1's own — materiality, time horizon,
 * mandate, blind-spot — and the panel directly above counts how many are covered, so these
 * double as an explanation of what that counter means.
 *
 * They are QUESTIONS, never verdicts: "what is the case against" is a request for evidence, and
 * nothing here asks the tool to recommend anything.
 */
const OPENERS: { axis: string; label: string; text: (name: string) => string }[] = [
  { axis: 'Blind-spot', label: 'The downside',
    text: n => `What is the strongest case against ${n} on ESG, and what evidence is behind it?` },
  { axis: 'Materiality', label: 'The upside',
    text: n => `Where is the evidence on ${n} most positive, and how solid are those sources?` },
  { axis: 'Mandate', label: 'Fit my mandate',
    text: n => `I am screening for a green-financing mandate — which parts of ${n}'s ESG record actually bear on that?` },
  { axis: 'Time horizon', label: 'Does it hold up',
    text: n => `Does the ESG story on ${n} matter in the next twelve months, or is it a structural shift over years?` },
]

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
  // Everything the model has already probed, and where it is standing right now.
  const covered = new Set(turns.map(t => t.env.axis).filter(Boolean) as string[])
  const activeAxis = last && last.type !== 'narrowed' ? last.axis ?? null : null

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
        // THE USER'S ANSWERS WERE BEING THROWN AWAY. Each turn holds both the assistant's
        // envelope (`t.env` — the question it asked) and `t.user` (what the reader actually
        // typed), and this mapped only the envelope. So the "trail" handed to Stage 2 was a
        // record of our own questions with every answer stripped out, and an instruction to
        // "address the concern they raised" had nothing to raise.
        //
        // Emitted as ordinary trail items with `type: "answer"` — the contract's `type` is a
        // free string and each item is already {axis, type, text, rationale}, so an answer is
        // just an item whose text is theirs. No change to the FROZEN Contract A.
        //
        // Answer before question, because that is the order they happened: the reader says
        // something, the interrogator responds with the next probe.
        const trail = nextTurns.flatMap(t => {
          const said = (t.user || '').trim()
          const items = said
            ? [{ axis: t.env.axis, type: 'answer', text: said, rationale: '' }]
            : []
          items.push({
            axis: t.env.axis, type: t.env.type, text: t.env.text, rationale: t.env.rationale,
          })
          return items
        })
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
    <div data-tour="interrogate">
      <AxisMap covered={covered} active={activeAxis} />
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

          {/* Openers, one per ESG-native axis. A blank box next to "0 of 4 covered — each
              question maps to exactly one" tells a first-time reader nothing about what a good
              question looks like, and the four axes are exactly the four things worth asking.
              Only on the first turn: after that the box is asking for an ANSWER, not a question,
              and suggesting questions there would be answering on the user's behalf. */}
          {turns.length === 0 && (
            <div className="q-suggest">
              <span className="q-suggest-h">Try:</span>
              {OPENERS.map(o => (
                <button key={o.axis} className="q-chip" title={`${o.axis} — ${o.text(company.company)}`}
                  onClick={() => { void submit(o.text(company.company)); setInput('') }}>
                  <span className="q-chip-axis">{o.axis}</span>{o.label}
                </button>
              ))}
            </div>
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
