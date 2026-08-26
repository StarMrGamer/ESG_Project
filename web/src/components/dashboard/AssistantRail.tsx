import { useEffect, useRef, useState } from 'react'
import { useStore } from '../../store'
import { Tone } from '../ui'

export default function AssistantRail() {
  const {
    board, settings, chatLog, sendChat, focusTicker, openDeepDive,
  } = useStore()
  const [text, setText] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const focused = board?.focused ?? null

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [chatLog.length])

  const submit = () => {
    if (!text.trim()) return
    void sendChat(text)
    setText('')
  }

  const hintName = focused?.constituent.company ?? '—'
  const hintTicker = focused?.constituent.ticker ?? ''

  return (
    <div className="rail">
      <div className="rail-section">
        <div className="cc-h">AI assistant</div>
        <div className="cc-muted">
          {settings.simplified
            ? 'Try “show banks”, “Singapore”, or a name like “DBS”.'
            : 'Filter (“show banks”), focus a company, or run the relay: “analyze DBS” · “interrogate Maybank”.'}
        </div>

        <div className="chat-log" ref={logRef}>
          {chatLog.slice(-8).map((m, i) => (
            <div key={i} className={`cc-bubble ${m.role === 'user' ? 'cc-bubble-u' : 'cc-bubble-a'}`}>
              {m.text}
            </div>
          ))}
        </div>

        {board && board.followups.length > 0 && (
          <div className="quick-row">
            {board.followups.map((c, i) => (
              <button key={i} className="btn btn-sm" title={c.prompt}
                onClick={() => void sendChat(c.prompt)}>{c.label}</button>
            ))}
          </div>
        )}

        <div className="chat-form">
          <input className="input" placeholder="Add a company or ask…" value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit() }} />
          <button className="btn btn-primary" onClick={submit}>Send</button>
        </div>

        <div className="cc-muted" style={{ marginTop: 12 }}>
          {settings.simplified ? `Look at ${hintName}` : `Analyse ${hintName}`}
        </div>
        <div className="action-pair">
          <button className="btn btn-primary" disabled={!hintTicker}
            title="Answer a standard question about this company now (Stage 2 + 3 — the Compete stage)."
            onClick={() => openDeepDive(hintTicker, 'compete')}>Answer now</button>
          <button className="btn" disabled={!hintTicker}
            title="A few adaptive questions first (Stage 1 — Interrogate), so the answer is shaped to your mandate, horizon and the concern you raise."
            onClick={() => openDeepDive(hintTicker, 'interrogate')}>Shape the question</button>
        </div>
      </div>

      <div className="rail-section">
        <div className="cc-h">{focused?.signals_kind === 'credentials' ? 'ESG credentials' : 'Live signals'}</div>
        {!focused || focused.signals.length === 0
          ? <div className="empty-note">
              {focused?.signals_kind === 'credentials'
                ? 'No rating credentials parsed from the focused company’s evidence.'
                : 'No live signals for the focused company yet.'}
            </div>
          : (
            <div className="cc-sigwrap">
              {focused.signals.map((r, i) => (
                <div className="cc-sig" key={i}>
                  <span>{r.label}</span>
                  <Tone tone={r.tone}>{r.value}</Tone>
                </div>
              ))}
            </div>
          )}

        {focused && focused.analyst.covered && (
          <div style={{ marginTop: 10 }}>
            <span className="cc-leftpill">
              {focused.analyst.label}{focused.analyst.as_of ? ` (${focused.analyst.as_of})` : ''}
              {settings.demo ? ' · illustrative' : ''}
            </span>
          </div>
        )}
      </div>

      <div className="rail-section">
        <div className="cc-h">Why the rating may be wrong</div>
        <div className="cc-panel-body">{focused?.why_wrong ?? 'Add or focus a company to see where its live signal diverges from the stale rating.'}</div>
        {focused && (
          <div className="cc-muted">
            Focused: {focused.constituent.company} · {focused.signals.length} {focused.signals_kind}
          </div>
        )}

        {!settings.simplified && focused && focused.check_action.has && (
          <>
            <hr className="divider" />
            <div className="cc-h">Check before Monday</div>
            {focused.check_action.verdict && <div className="cc-muted">{focused.check_action.verdict}</div>}
            <div className="cc-panel-body">{focused.check_action.check}</div>
            <div className="cc-muted">From the computed deep-dive. Not investment advice.</div>
          </>
        )}

        {focused?.foundation && (
          <details className="expander">
            <summary>Foundation evidence</summary>
            <div className="cc-muted">Confidence: <b>{focused.foundation.confidence || '—'}</b></div>
            <p style={{ fontSize: 13, lineHeight: 1.6 }}>{focused.foundation.basis}</p>
            {focused.foundation.source_url && (
              <a href={focused.foundation.source_url} target="_blank" rel="noreferrer">source</a>
            )}
          </details>
        )}

        {focusTicker && <div className="cc-muted">Focus pin: {focusTicker}</div>}
      </div>
    </div>
  )
}
