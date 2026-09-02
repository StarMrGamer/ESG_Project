import { useEffect, useState } from 'react'
import { StoreProvider, useStore } from './store'
import Header from './components/Header'
import Dashboard from './components/dashboard/Dashboard'
import DeepDive from './components/deepdive/DeepDive'
import CompareView from './components/compare/CompareView'
import Setup from './components/setup/Setup'
import EvidencePanel from './components/evidence/EvidencePanel'
import Present from './components/present/Present'
import { PITCH } from './components/present/tour'
import { FEARS } from './components/present/fears'
import { RECAP } from './components/present/recap'
import { ANALYST } from './components/present/analyst'
import type { Track } from './components/present/tour'
import Tutorial from './components/tour/Tutorial'
import './styles.css'

function Toasts() {
  const { toasts } = useStore()
  return (
    <div className="toasts">
      {toasts.map(t => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}
    </div>
  )
}

function Router() {
  const { view } = useStore()
  if (view.name === 'deep') return <DeepDive ticker={view.ticker} mode={view.mode} />
  if (view.name === 'compare') return <CompareView tickers={view.tickers} />
  if (view.name === 'evidence') return <EvidencePanel ticker={view.ticker} />
  return <Dashboard />
}

function Shell() {
  const { settings, board, view } = useStore()
  // `?present=1` / `?recap=1` so either walk opens straight from a bookmark on the presenting
  // machine, without hunting for the button in front of a room.
  const [track, setTrack] = useState<Track | null>(() => {
    const q = new URLSearchParams(window.location.search)
    if (q.get('present') === '1') return PITCH
    if (q.get('fears') === '1') return FEARS
    if (q.get('recap') === '1') return RECAP
    if (q.get('analyst') === '1') return ANALYST
    return null
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.dark ? 'dark' : 'light')
  }, [settings.dark])

  // The assistant configures the board before the board exists. Header and footer stay out of
  // the way until it has — a first screen with a settings bar on it is already a dashboard.
  if (!settings.setupDone) {
    // The full set of preferences, every time. The one-question start belonged to the removed
    // investor rendering — a CGSI ESG investor is setting a mandate, a risk appetite, a holding
    // period and a PPP balance, and every one of those changes what the board shows.
    return (
      <div className="app-shell is-setup">
        <Setup />
        <Toasts />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Header onPresent={() => setTrack(PITCH)} onFears={() => setTrack(FEARS)}
        onRecap={() => setTrack(RECAP)} onAnalyst={() => setTrack(ANALYST)} />
      <main className="app-main">
        <Router />
        <div className="footer-note">
          Thinks · Challenges · Competes — disagrees with ratings using signals they can't see.
          Never buy / sell / hold. Not investment advice.
        </div>
      </main>
      <Toasts />
      {/* Straight after setup, and only with a board on screen to point at: every card anchors
          to a real element, and one that has not rendered yet would be skipped as missing. Present
          mode owns the screen while it runs, so the two never overlap. */}
      {(!settings.tourDone || settings.tourDeck) && board && view.name === 'dashboard' && !track
        && <Tutorial />}
      {track && <Present track={track} onExit={() => setTrack(null)} />}
    </div>
  )
}

/**
 * `?fresh=1` — meet the app as a stranger would.
 *
 * Setup and the tutorial are gated on `localStorage`, which no server-side reset can reach: run
 * `demo_reset` all you like and a browser that has already seen the tour will never show it
 * again. That is correct for a returning user and useless five minutes before handing the laptop
 * to a judge, when the console is the last place anyone wants to be.
 *
 * It runs BEFORE the provider mounts, because the store reads localStorage in a `useState`
 * initialiser — clearing it afterwards would leave the old settings live until a reload. The
 * parameter is then stripped from the URL so a refresh does not wipe the answers they just gave.
 */
function freshStart() {
  const q = new URLSearchParams(window.location.search)
  if (q.get('fresh') !== '1') return
  try { localStorage.removeItem('esg-radar-settings') } catch { /* private mode */ }
  q.delete('fresh')
  const rest = q.toString()
  window.history.replaceState({}, '', window.location.pathname + (rest ? `?${rest}` : ''))
}

export default function App() {
  freshStart()
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  )
}
