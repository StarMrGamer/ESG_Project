import { useMemo, useState } from 'react'
import { useStore } from '../../store'

/**
 * The investor's way in: one question.
 *
 * The full setup asks six — mandate, risk appetite, holding period, green focus, then country
 * and industry — and every one of them earns its place for the analyst it was written for. For
 * somebody who came to find out whether the bank they hold is actually improving, it is a form
 * standing between them and the answer, and four of the six questions are about a job they do
 * not have.
 *
 * So the investor path asks the only question that is genuinely theirs — WHICH COMPANY — and
 * derives the rest from sensible middles (balanced tier, long horizon, broad focus), all of them
 * changeable later and none of them silently claimed to be the reader's own choices.
 *
 * The other two doors stay in plain sight rather than being buried: browse the whole basket, or
 * switch to the analyst setup. A simplified path that traps you is worse than the long form.
 */
export default function SetupLite() {
  const { board, applySetup, setSettings, setFocus, sendChat } = useStore()
  const [typed, setTyped] = useState('')

  const names = useMemo(() => (board?.constituents ?? []).map(c => c.company), [board])
  // Five real names off the loaded universe, never a hard-coded list: the demo set and the real
  // basket share no names at all, and a suggestion that resolves to nothing teaches distrust on
  // the first screen.
  const suggestions = useMemo(() => names.slice(0, 5), [names])

  const start = (company: string) => {
    const name = company.trim()
    if (!name) return
    applySetup({
      mandate: 'risk', goal: 'investigate', holding: '2_5y', focus: 'broad',
      country: 'All', sector: 'All', tier: 'balanced', horizon: 'long', level: 1,
      label: `looking at ${name}`,
    })
    setSettings({ audience: 'investor', showNumbers: false })
    // A name in the loaded universe focuses directly. Anything else goes to the assistant, which
    // is already the thing that resolves loose names — and answers in words when it cannot,
    // rather than landing the reader on an empty board.
    const q = name.toLowerCase()
    const hit = (board?.constituents ?? []).find(
      c => c.company.toLowerCase().includes(q) || c.ticker.toLowerCase() === q)
    if (hit) setFocus(hit.ticker)
    else void sendChat(name)
  }

  const browse = () => applySetup({
    mandate: 'risk', goal: 'screen', holding: '2_5y', focus: 'broad',
    country: 'All', sector: 'All', tier: 'balanced', horizon: 'long', level: 1,
    label: 'looking across ASEAN',
  })

  return (
    <div className="setup-wrap">
      <div className="setup-card setup-lite">
        <div className="setup-eyebrow">A second opinion on ESG ratings</div>
        <h1 className="setup-title">Which company are you looking at?</h1>
        <p className="setup-lite-lead">
          Tell me a name and I will show you what its published ESG rating says, what dated news
          and filings say, and where the two disagree — with the sources attached. No scores, no
          buy or sell.
        </p>

        <div className="setup-lite-ask">
          <input className="input" autoFocus value={typed} placeholder="e.g. a bank you hold…"
            onChange={e => setTyped(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') start(typed) }} />
          <button className="btn btn-primary" onClick={() => start(typed)}>Show me</button>
        </div>

        {suggestions.length > 0 && (
          <div className="setup-chips">
            {suggestions.map(n => (
              <button key={n} className="setup-chip" onClick={() => start(n)}>{n}</button>
            ))}
          </div>
        )}

        <div className="setup-lite-alt">
          <button className="btn" onClick={browse}>Browse all the companies instead</button>
          <button className="btn setup-lite-pro"
            onClick={() => setSettings({ audience: 'analyst' })}
            title="The full setup: mandate, risk appetite, holding period, green-finance focus, country and industry.">
            I work with ESG data →
          </button>
        </div>

        <div className="setup-foot">
          Demo data is on — a fictional, fully-numeric universe, labelled illustrative throughout.
        </div>
      </div>
    </div>
  )
}
