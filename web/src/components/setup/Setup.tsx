import { useRef, useState } from 'react'
import { useStore } from '../../store'
import type { Focus, Goal, Holding, Level, Mandate, SetupChoice } from '../../store'
import type { HorizonKey, TierKey } from '../../types'
import { shortSector } from '../ui'

/**
 * Setup — the assistant, first.
 *
 * The dashboard used to open on every widget at once, for every visitor, in the same
 * configuration. This asks four short questions before anything is drawn and hands the board a
 * shape that fits the answers, so the first screen a judge sees is already about them.
 *
 * It runs entirely locally: chips and a local matcher, no LLM call. A hackathon demo cannot be
 * one flaky network hop away from its own opening screen, and the interrogation in Stage 1 is
 * where real model reasoning belongs.
 *
 * The `goal` question is the fork in the road, and the two arms are genuinely different
 * journeys, not one journey with a different filter:
 *   screen      — a universe question. Country and industry follow, and it lands on the board.
 *   investigate — a single-company question. It asks which name, and lands in the relay.
 *
 * WHY THERE IS A PROFILE STEP (added 2026-08-19, review feedback). The first version asked four
 * questions and DERIVED the risk tier and decay horizon from the mandate alone. The reviewer's
 * objection was fair: a vague question earns a vague answer, and "protect the downside" is a
 * thin basis for setting somebody's risk appetite and evidence window for them. So the inputs
 * that actually move the board are now asked for — risk appetite, how long you hold, and
 * whether green finance is the point — as one step rather than three, because they are one
 * thought. The mandate still PRE-FILLS every answer with its reason attached, so the fast path
 * is unchanged and nothing is decided silently on the user's behalf.
 *
 * EVERY ANSWER HAS TO DO SOMETHING. A question whose answer only changes a summary line is
 * decoration, and worse than not asking. Risk appetite sets the A5 tier, holding period sets the
 * decay horizon (a re-score, not a filter), and the green-finance focus reads
 * `green_bond_status` from the metadata CSV — real data, marked provisional where it is.
 */

type StepKey = 'mandate' | 'profile' | 'goal' | 'country' | 'sector' | 'company' | 'ready'

const MANDATES: { key: Mandate; label: string; blurb: string }[] = [
  { key: 'risk', label: 'Protect the downside', blurb: 'Find what the rating has not marked down yet.' },
  { key: 'return', label: 'Find the upside', blurb: 'Find improvement the rating has not priced in.' },
  { key: 'compliance', label: 'Satisfy a mandate', blurb: 'Show the evidence trail behind every claim.' },
]

/** Risk appetite — the A5 tiers, in the user's words rather than the config's. */
const RISKS: { key: TierKey; label: string; blurb: string }[] = [
  { key: 'conservative', label: 'Low', blurb: 'Only labelled, reviewed, profitable issuers, and only where the evidence is strong.' },
  { key: 'balanced', label: 'Moderate', blurb: 'Profitable names where we disagree with the rating and no reviewed label has priced it.' },
  { key: 'aggressive', label: 'High', blurb: 'Includes loss-making names with traction — thinner evidence, earlier.' },
]

/**
 * How long you hold. This sets the decay horizon, which is a genuinely different quantity —
 * days of evidence memory, not years of holding — so the mapping is stated on screen rather
 * than implied. A short holder wants only what is moving now; a longer one wants the record.
 */
const HOLDINGS: { key: Holding; label: string; blurb: string; horizon: HorizonKey }[] = [
  { key: 'under_2y', label: 'Under 2 years', horizon: 'short',
    blurb: 'Signals decay fast (45 days) — only what is moving now counts.' },
  { key: '2_5y', label: '2 to 5 years', horizon: 'long',
    blurb: 'Signals decay slowly (180 days) — the fuller record counts.' },
  { key: '5y_plus', label: '5 to 10 years+', horizon: 'long',
    blurb: 'Signals decay slowly (180 days) — structural change over noise.' },
]

/** Thematic focus. `green` is backed by the green-bond metadata, not by sentiment. */
const FOCUSES: { key: Focus; label: string; blurb: string }[] = [
  { key: 'broad', label: 'Broad ESG', blurb: 'Every improver in the universe, whatever it funds with.' },
  { key: 'green', label: 'Green finance', blurb: 'Lean towards issuers carrying a labelled green bond.' },
]

const GOALS: { key: Goal; label: string; blurb: string }[] = [
  { key: 'screen', label: 'Screen the universe', blurb: 'Sweep ASEAN for names where we disagree with the rating.' },
  { key: 'investigate', label: 'Investigate one company', blurb: 'Interrogate a single name, then compete with its rating.' },
]

/**
 * Mandate implies a risk tier and a decay horizon. Both are shown back with the reason on the
 * summary card and both stay editable there — a derived default the user cannot see or change
 * is just a hidden setting.
 */
const DERIVED: Record<Mandate, { tier: TierKey; holding: Holding; focus: Focus; why: string }> = {
  risk: { tier: 'balanced', holding: 'under_2y', focus: 'broad',
    why: 'Downside work reacts to what is happening now, so I have started you on a short evidence window and a moderate appetite. Change either.' },
  return: { tier: 'aggressive', holding: '5y_plus', focus: 'broad',
    why: 'Upside work needs a longer memory and tolerates thinner evidence, so I have started you high and long. Change either.' },
  compliance: { tier: 'conservative', holding: '2_5y', focus: 'green',
    why: 'A mandate wants corroboration over reach, so I have started you low, long, and pointed at labelled issuance. Change any of it.' },
}

const LEVELS: { key: Level; label: string; blurb: string }[] = [
  { key: 1, label: 'Brief', blurb: 'The verdict and one action.' },
  { key: 2, label: 'Analysis', blurb: 'Adds the momentum chart and the rankings.' },
  { key: 3, label: 'Everything', blurb: 'Adds the disagreement matrix, evidence and provenance.' },
]

function Bubble({ children }: { children: React.ReactNode }) {
  return <div className="setup-bubble">{children}</div>
}

function Said({ children }: { children: React.ReactNode }) {
  return <div className="setup-said">{children}</div>
}

export default function Setup() {
  const { board, applySetup, openDeepDive, buildLiveAndDive, settings } = useStore()
  const [mandate, setMandate] = useState<Mandate | ''>('')
  const [goal, setGoal] = useState<Goal | ''>('')
  const [country, setCountry] = useState('All')
  const [sector, setSector] = useState('All')
  const [company, setCompany] = useState('')
  const [level, setLevel] = useState<Level>(1)
  const [tier, setTier] = useState<TierKey>('balanced')
  const [holding, setHolding] = useState<Holding>('2_5y')
  const [focus, setFocus] = useState<Focus>('broad')
  // The horizon is not asked for directly — it is what the holding period MEANS in evidence
  // days, so it is derived here and shown with that reason on the summary card.
  const horizon: HorizonKey = HOLDINGS.find(h => h.key === holding)!.horizon
  const [typed, setTyped] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const countries = board?.countries ?? ['All']
  const sectors = board?.sectors ?? ['All']
  const names = board?.constituents ?? []

  // Country and sector default to 'All', so "answered" cannot be read off their value —
  // the screening arm carries its own cursor instead.
  const [screenStep, setScreenStep] = useState<'country' | 'sector' | 'ready'>('country')

  // The profile step is pre-filled by the mandate, so it is a confirmation, not a blocker —
  // `profileDone` flips on the first interaction OR on Continue.
  const [profileDone, setProfileDone] = useState(false)

  const effStep: StepKey = !mandate ? 'mandate'
    : !profileDone ? 'profile'
      : !goal ? 'goal'
        : goal === 'investigate' ? (company ? 'ready' : 'company')
          : screenStep === 'ready' ? 'ready' : screenStep

  const suggestions = names.slice(0, 6)

  const pickMandate = (m: Mandate) => {
    setMandate(m)
    setTier(DERIVED[m].tier)
    setHolding(DERIVED[m].holding)
    setFocus(DERIVED[m].focus)
  }

  /** Free text, matched locally against whatever the current step is asking for. */
  const submitTyped = () => {
    const t = typed.trim()
    if (!t) return
    const low = t.toLowerCase()
    setTyped('')
    if (effStep === 'mandate') {
      const hit = /risk|downside|protect|safe/.test(low) ? 'risk'
        : /return|upside|alpha|growth|outperform/.test(low) ? 'return'
          : /compl|mandate|regul|report|audit/.test(low) ? 'compliance' : ''
      if (hit) pickMandate(hit as Mandate)
      return
    }
    if (effStep === 'profile') {
      if (/high|aggress|risky/.test(low)) setTier('aggressive')
      else if (/low|conserv|safe|cautious/.test(low)) setTier('conservative')
      else if (/mod|balanc|medium/.test(low)) setTier('balanced')
      if (/green|climate|transition|bond/.test(low)) setFocus('green')
      const yrs = low.match(/(\d+)\s*(?:to|-|–)?\s*(\d+)?\s*year/)
      if (yrs) {
        const n = Number(yrs[2] || yrs[1])
        setHolding(n < 2 ? 'under_2y' : n <= 5 ? '2_5y' : '5y_plus')
      }
      setProfileDone(true)
      return
    }
    if (effStep === 'goal') {
      setGoal(/one|single|company|name|dive|investig/.test(low) ? 'investigate' : 'screen')
      return
    }
    if (effStep === 'country') {
      const hit = countries.find(c => c.toLowerCase() === low)
        || countries.find(c => c !== 'All' && low.includes(c.toLowerCase()))
      setCountry(hit || 'All')
      setScreenStep('sector')
      return
    }
    if (effStep === 'sector') {
      const hit = sectors.find(sc => sc !== 'All' && sc.toLowerCase().includes(low))
      setSector(hit || 'All')
      setScreenStep('ready')
      return
    }
    if (effStep === 'company') setCompany(t)
  }

  const label = [
    mandate ? MANDATES.find(m => m.key === mandate)!.label.toLowerCase() : '',
    goal === 'investigate' ? `on ${company}` : country === 'All' ? 'across ASEAN' : `in ${country}`,
    goal === 'screen' && sector !== 'All' ? `· ${shortSector(sector)}` : '',
    `· ${RISKS.find(r => r.key === tier)!.label.toLowerCase()} risk`,
    `· ${HOLDINGS.find(h => h.key === holding)!.label.toLowerCase()}`,
    focus === 'green' ? '· green finance' : '',
  ].filter(Boolean).join(' ')

  const finish = () => {
    const choice: SetupChoice = {
      mandate: (mandate || 'risk') as Mandate, goal: (goal || 'screen') as Goal,
      holding, focus,
      country: goal === 'investigate' ? 'All' : country,
      sector: goal === 'investigate' ? 'All' : sector,
      tier, horizon, level, label,
    }
    applySetup(choice)
    if (goal === 'investigate' && company) {
      const hit = names.find(c => c.ticker === company)
        || names.find(c => c.company.toLowerCase() === company.toLowerCase())
        || names.find(c => c.company.toLowerCase().includes(company.toLowerCase()))
      if (hit) void openDeepDive(hit.ticker, 'interrogate')
      else void buildLiveAndDive(company, 'interrogate')
    }
  }

  const skip = () => applySetup({
    mandate: 'risk', goal: 'screen', holding: '2_5y', focus: 'broad',
    country: 'All', sector: 'All',
    tier: 'balanced', horizon: 'long', level: 3, label: 'everything, unfiltered',
  })

  const order: StepKey[] = goal === 'investigate'
    ? ['mandate', 'profile', 'goal', 'company', 'ready']
    : ['mandate', 'profile', 'goal', 'country', 'sector', 'ready']
  const idx = Math.max(0, order.indexOf(effStep))

  return (
    <div className="setup-wrap">
      <div className="setup-card">
        <div className="setup-head">
          <div>
            <div className="setup-kicker">Setup · {idx + 1} of {order.length}</div>
            <h2 className="setup-title">Let me set the board up for you</h2>
          </div>
          <button className="btn setup-skip" onClick={skip}>Skip — show me everything</button>
        </div>

        <div className="setup-dots" aria-hidden>
          {order.map((k, i) => (
            <span key={k} className={`setup-dot ${i < idx ? 'done' : i === idx ? 'on' : ''}`} />
          ))}
        </div>

        <div className="setup-thread">
          {mandate && (
            <>
              <Bubble>What are you trying to do?</Bubble>
              <Said>{MANDATES.find(m => m.key === mandate)!.label}</Said>
            </>
          )}
          {profileDone && (
            <>
              <Bubble>And a bit about you?</Bubble>
              <Said>
                {RISKS.find(r => r.key === tier)!.label} risk ·{' '}
                {HOLDINGS.find(h => h.key === holding)!.label} ·{' '}
                {FOCUSES.find(f => f.key === focus)!.label}
              </Said>
            </>
          )}
          {goal && (
            <>
              <Bubble>And how do you want to start?</Bubble>
              <Said>{GOALS.find(g => g.key === goal)!.label}</Said>
            </>
          )}
          {goal === 'screen' && screenStep !== 'country' && (
            <>
              <Bubble>Where should I look?</Bubble>
              <Said>{country === 'All' ? 'All ASEAN' : country}</Said>
            </>
          )}
          {goal === 'screen' && screenStep === 'ready' && (
            <>
              <Bubble>Any industry in particular?</Bubble>
              <Said>{sector === 'All' ? 'All industries' : shortSector(sector)}</Said>
            </>
          )}
          {goal === 'investigate' && company && (
            <>
              <Bubble>Which company?</Bubble>
              <Said>{company}</Said>
            </>
          )}
        </div>

        {effStep === 'mandate' && (
          <div className="setup-step">
            <Bubble>
              I am a radar, not a screener — I take a position against a stale rating and show the
              evidence. What are you trying to do?
            </Bubble>
            <div className="setup-opts">
              {MANDATES.map(m => (
                <button key={m.key} className="setup-opt" onClick={() => pickMandate(m.key)}>
                  <b>{m.label}</b><span>{m.blurb}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {effStep === 'profile' && (
          <div className="setup-step">
            <Bubble>
              Before I show you anything — a bit about you, so what I show is about you too.
              I have guessed from your mandate; correct whatever is wrong.
            </Bubble>

            <div className="setup-profile">
              <div className="setup-q">
                <div className="setup-q-h">How much risk do you take?</div>
                <div className="setup-chips">
                  {RISKS.map(r => (
                    <button key={r.key} className={`setup-chip ${tier === r.key ? 'on' : ''}`}
                      title={r.blurb} onClick={() => setTier(r.key)}>{r.label}</button>
                  ))}
                </div>
                <div className="setup-q-f">{RISKS.find(r => r.key === tier)!.blurb}</div>
              </div>

              <div className="setup-q">
                <div className="setup-q-h">How long do you hold?</div>
                <div className="setup-chips">
                  {HOLDINGS.map(h => (
                    <button key={h.key} className={`setup-chip ${holding === h.key ? 'on' : ''}`}
                      title={h.blurb} onClick={() => setHolding(h.key)}>{h.label}</button>
                  ))}
                </div>
                {/* Years of holding and days of evidence memory are different quantities, so
                    the translation between them is printed rather than assumed. */}
                <div className="setup-q-f">{HOLDINGS.find(h => h.key === holding)!.blurb}</div>
              </div>

              <div className="setup-q">
                <div className="setup-q-h">Anything you are specifically after?</div>
                <div className="setup-chips">
                  {FOCUSES.map(f => (
                    <button key={f.key} className={`setup-chip ${focus === f.key ? 'on' : ''}`}
                      title={f.blurb} onClick={() => setFocus(f.key)}>{f.label}</button>
                  ))}
                </div>
                <div className="setup-q-f">{FOCUSES.find(f => f.key === focus)!.blurb}</div>
              </div>
            </div>

            {mandate && <div className="setup-why">{DERIVED[mandate].why}</div>}

            <button className="btn btn-primary setup-go" onClick={() => setProfileDone(true)}>
              That's me →
            </button>
          </div>
        )}

        {effStep === 'goal' && (
          <div className="setup-step">
            <Bubble>And how do you want to start?</Bubble>
            <div className="setup-opts">
              {GOALS.map(g => (
                <button key={g.key} className="setup-opt" onClick={() => setGoal(g.key)}>
                  <b>{g.label}</b><span>{g.blurb}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {effStep === 'country' && (
          <div className="setup-step">
            <Bubble>Where should I look?</Bubble>
            <div className="setup-chips">
              {countries.map(c => (
                <button key={c} className="setup-chip"
                  onClick={() => { setCountry(c); setScreenStep('sector') }}>
                  {c === 'All' ? 'All ASEAN' : c}
                </button>
              ))}
            </div>
          </div>
        )}

        {effStep === 'sector' && (
          <div className="setup-step">
            <Bubble>Any industry in particular?</Bubble>
            <div className="setup-chips">
              {sectors.map(sc => (
                <button key={sc} className="setup-chip"
                  onClick={() => { setSector(sc); setScreenStep('ready') }}>
                  {sc === 'All' ? 'All industries' : shortSector(sc)}
                </button>
              ))}
            </div>
          </div>
        )}

        {effStep === 'company' && (
          <div className="setup-step">
            <Bubble>Which company should I interrogate?</Bubble>
            <div className="setup-chips">
              {suggestions.map(c => (
                <button key={c.ticker} className="setup-chip" onClick={() => setCompany(c.company)}>
                  {c.company}
                </button>
              ))}
            </div>
            <div className="cc-muted" style={{ marginTop: 8 }}>
              Or type any ASEAN name — I will build a live profile from public sources.
            </div>
          </div>
        )}

        {effStep === 'ready' && (
          <div className="setup-step">
            <Bubble>
              Ready. Here is how I have set myself up — change anything you disagree with.
            </Bubble>

            <div className="setup-derived">
              <div className="setup-derived-row">
                <span className="setup-derived-k">Risk tier</span>
                <div className="seg">
                  {(['conservative', 'balanced', 'aggressive'] as TierKey[]).map(t => (
                    <button key={t} className={`btn ${tier === t ? 'on' : ''}`}
                      onClick={() => setTier(t)}>{t[0].toUpperCase() + t.slice(1)}</button>
                  ))}
                </div>
              </div>
              <div className="setup-derived-row">
                <span className="setup-derived-k">Holding period</span>
                <div className="seg">
                  {HOLDINGS.map(h => (
                    <button key={h.key} className={`btn ${holding === h.key ? 'on' : ''}`}
                      onClick={() => setHolding(h.key)}>{h.label}</button>
                  ))}
                </div>
              </div>
              <div className="setup-derived-row">
                <span className="setup-derived-k">Focus</span>
                <div className="seg">
                  {FOCUSES.map(f => (
                    <button key={f.key} className={`btn ${focus === f.key ? 'on' : ''}`}
                      onClick={() => setFocus(f.key)}>{f.label}</button>
                  ))}
                </div>
              </div>
              {/* The one derived value left, and it says both what it is and where it came from. */}
              <div className="setup-derived-row">
                <span className="setup-derived-k">Signal decay</span>
                <span className="setup-derived-v">
                  {horizon === 'short' ? '45 days' : '180 days'}
                  <span className="cc-muted"> — from your holding period</span>
                </span>
              </div>
              {mandate && <div className="setup-why">{DERIVED[mandate].why}</div>}
            </div>

            <div className="setup-levels">
              <div className="setup-derived-k">How much on screen at once</div>
              {LEVELS.map(l => (
                <button key={l.key} className={`setup-level ${level === l.key ? 'on' : ''}`}
                  onClick={() => setLevel(l.key)}>
                  <b>{l.key} · {l.label}</b><span>{l.blurb}</span>
                </button>
              ))}
              <div className="cc-muted">
                You can move up a level at any time from the header — nothing is hidden for good.
              </div>
            </div>

            <button className="btn btn-primary setup-go" onClick={finish}>
              {goal === 'investigate' ? `Interrogate ${company} →` : 'Build my board →'}
            </button>
          </div>
        )}

        {effStep !== 'ready' && (
          <div className="setup-form">
            <input ref={inputRef} className="input" value={typed}
              placeholder={effStep === 'company' ? 'Type a company name…' : '…or just tell me'}
              onChange={e => setTyped(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submitTyped() }} />
            <button className="btn" onClick={submitTyped}>Send</button>
          </div>
        )}

        <div className="setup-foot">
          {settings.demo
            ? 'Demo data is on — a fictional, fully-numeric universe, labelled illustrative throughout.'
            : 'Real ASEAN base DB — 52 companies with evidence-backed ESG improvement.'}
        </div>
      </div>
    </div>
  )
}
