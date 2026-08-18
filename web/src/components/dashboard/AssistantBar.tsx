import { useState } from 'react'
import { useStore } from '../../store'

/**
 * The level-1 assistant: one line, always reachable.
 *
 * Level 1 closes both rails, which would otherwise take the assistant off the screen entirely —
 * and the assistant is the product's front door, not a side panel. This keeps it present without
 * bringing back the log, the signal list and the three stacked panels that made the rail heavy.
 * Its last reply shows inline; the full transcript lives at level 2.
 */
export default function AssistantBar() {
  const { board, chatLog, sendChat, settings, setSettings } = useStore()
  const [text, setText] = useState('')

  const submit = () => {
    if (!text.trim()) return
    void sendChat(text)
    setText('')
  }

  const last = [...chatLog].reverse().find(m => m.role === 'assistant')
  const chips = (board?.followups ?? []).slice(0, 3)

  return (
    <div className="abar">
      <div className="abar-row">
        <span className="abar-dot" aria-hidden />
        <input className="input" value={text}
          placeholder={settings.profile.goal === 'investigate'
            ? 'Ask about this company, or name another…'
            : 'Ask me to filter, focus a name, or compete with a rating…'}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }} />
        <button className="btn btn-primary" onClick={submit}>Ask</button>
      </div>
      {chips.length > 0 && (
        <div className="quick-row">
          {chips.map((c, i) => (
            <button key={i} className="btn btn-sm" title={c.prompt}
              onClick={() => void sendChat(c.prompt)}>{c.label}</button>
          ))}
        </div>
      )}
      {last && (
        <div className="abar-reply">
          {last.text}
          <button className="btn btn-sm abar-more"
            onClick={() => setSettings({ level: 2, rightOpen: true })}>Open assistant</button>
        </div>
      )}
    </div>
  )
}
