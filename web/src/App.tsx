import { useEffect } from 'react'
import { StoreProvider, useStore } from './store'
import Header from './components/Header'
import Dashboard from './components/dashboard/Dashboard'
import DeepDive from './components/deepdive/DeepDive'
import CompareView from './components/compare/CompareView'
import Setup from './components/setup/Setup'
import EvidencePanel from './components/evidence/EvidencePanel'
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
  const { settings } = useStore()
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.dark ? 'dark' : 'light')
  }, [settings.dark])

  // The assistant configures the board before the board exists. Header and footer stay out of
  // the way until it has — a first screen with a settings bar on it is already a dashboard.
  if (!settings.setupDone) {
    return (
      <div className="app-shell is-setup">
        <Setup />
        <Toasts />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <Router />
        <div className="footer-note">
          Thinks · Challenges · Competes — disagrees with ratings using signals they can't see.
          Never buy / sell / hold. Not investment advice.
        </div>
      </main>
      <Toasts />
    </div>
  )
}

export default function App() {
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  )
}
