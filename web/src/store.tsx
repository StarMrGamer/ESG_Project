import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { Board, Entry, Health, HorizonKey, TierKey } from './types'

/** The mandate the user set up with — the same vocabulary Contract A's `mandate` uses. */
export type Mandate = 'risk' | 'return' | 'compliance'
/** Which of the two journeys the setup handed off to. */
export type Goal = 'screen' | 'investigate'
/**
 * How much of the board is on screen. This is the layering control: every widget declares the
 * level it earns its place at, and nothing above the current level renders. Level 1 is the
 * default for a first-time user — the dashboard used to open with all three at once, which is
 * the "overstimulating" complaint this exists to answer.
 */
export type Level = 1 | 2 | 3

export interface Profile {
  mandate: Mandate | ''
  goal: Goal | ''
  /** One line describing the setup, shown back to the user so the personalisation is legible. */
  label: string
}

export type View =
  | { name: 'dashboard' }
  | { name: 'deep'; ticker: string; mode: 'compete' | 'interrogate' }
  | { name: 'compare'; tickers: string[] }
  | { name: 'evidence'; ticker: string }

export interface Settings {
  demo: boolean
  dark: boolean
  /**
   * Kept as the server-facing flag (the board endpoint tailors its copy on it) but no longer set
   * directly — it is derived from `level` in setSettings, so the two can never disagree.
   */
  simplified: boolean
  /** Progressive disclosure: 1 Brief · 2 Analysis · 3 Everything. */
  level: Level
  /** False until the assistant-led setup has run; gates the whole dashboard. */
  setupDone: boolean
  profile: Profile
  /**
   * The universe filters live here, not in component state, because the setup chooses them and
   * the header reports them back ("set up for … in Singapore · Banks"). Held outside the
   * persisted blob they reset to All on the next reload while that line kept its promise.
   */
  filters: { country: string; sector: string }
  leftOpen: boolean
  rightOpen: boolean
  ragEnabled: boolean
  ragTopK: number
  /** A5 — risk appetite. 'all' shows the whole matrix; a tier DIMS the rest, never hides it. */
  tier: TierKey | 'all'
  /**
   * Decay horizon. Unlike `tier` this is not a client-side filter — it re-scores on the server,
   * so it belongs in the board fetch's dependency list below, not in the render path.
   */
  horizon: HorizonKey
  /** A6 — origination pipeline filter: the Balanced condition as a toggle. */
  pipelineOnly: boolean
}

/** Everything the setup flow decides, applied in one shot so the board refetches once. */
export interface SetupChoice {
  mandate: Mandate
  goal: Goal
  country: string
  sector: string
  tier: TierKey
  horizon: HorizonKey
  level: Level
  label: string
}

interface Toast { id: number; text: string; tone: 'good' | 'bad' | 'info' }
interface ChatMsg { role: 'user' | 'assistant'; text: string }

const SETTINGS_KEY = 'esg-radar-settings'
const DEFAULTS: Settings = {
  demo: true, dark: true, simplified: true, level: 1, setupDone: false,
  profile: { mandate: '', goal: '', label: '' },
  filters: { country: 'All', sector: 'All' },
  leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', horizon: 'long', pipelineOnly: false,
}

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch { /* fresh defaults */ }
  return DEFAULTS
}

interface Store {
  settings: Settings
  setSettings: (p: Partial<Settings>) => void
  health: Health | null
  view: View
  goDashboard: () => void
  filters: { country: string; sector: string }
  setFilters: (p: Partial<{ country: string; sector: string }>) => void
  focusTicker: string
  setFocus: (ticker: string) => void
  board: Board | null
  boardLoading: boolean
  boardError: string
  refreshBoard: () => void
  entries: Record<string, Entry>
  saveEntry: (e: Entry) => void
  monitorOnly: (ticker: string) => Promise<void>
  openDeepDive: (ticker: string, mode: 'compete' | 'interrogate') => Promise<void>
  openEvidence: (ticker: string) => void
  buildLiveAndDive: (text: string, mode: 'compete' | 'interrogate') => Promise<void>
  loadSample: () => Promise<void>
  uploadFile: (f: File) => Promise<void>
  unpin: (ticker: string) => Promise<void>
  compareSel: string[]
  toggleCompare: (ticker: string) => void
  openCompare: () => void
  applySetup: (c: SetupChoice) => void
  restartSetup: () => void
  chatLog: ChatMsg[]
  sendChat: (text: string) => Promise<void>
  toasts: Toast[]
  toast: (text: string, tone?: Toast['tone']) => void
}

const Ctx = createContext<Store | null>(null)

export function useStore(): Store {
  const s = useContext(Ctx)
  if (!s) throw new Error('StoreProvider missing')
  return s
}

let toastSeq = 1

export function StoreProvider({ children }: { children: ReactNode }) {
  const [settings, setSettingsState] = useState<Settings>(loadSettings)
  const [health, setHealth] = useState<Health | null>(null)
  const [view, setView] = useState<View>({ name: 'dashboard' })
  const [focusTicker, setFocusTicker] = useState('')
  const [board, setBoard] = useState<Board | null>(null)
  const [boardLoading, setBoardLoading] = useState(false)
  const [boardError, setBoardError] = useState('')
  const [boardVersion, setBoardVersion] = useState(0)
  const [entries, setEntries] = useState<Record<string, Entry>>({})
  const [compareSel, setCompareSel] = useState<string[]>([])
  const [chatLog, setChatLog] = useState<ChatMsg[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const busyRef = useRef(false)

  const filters = settings.filters

  const setSettings = useCallback((p: Partial<Settings>) => {
    setSettingsState(prev => {
      const next = { ...prev, ...p }
      // `simplified` is the server's flag and `level` is the UI's. Deriving one from the other
      // here means no caller has to remember to set both, and a stale localStorage blob that
      // predates `level` still lands somewhere coherent.
      if (p.level !== undefined) next.simplified = p.level === 1
      else if (p.simplified !== undefined) next.level = p.simplified ? 1 : 3
      try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)) } catch { /* private mode */ }
      return next
    })
  }, [])

  const toast = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = toastSeq++
    setToasts(t => [...t, { id, text, tone }])
    window.setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 6000)
  }, [])

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [])

  const refreshBoard = useCallback(() => setBoardVersion(v => v + 1), [])

  useEffect(() => {
    let cancel = false
    setBoardLoading(true)
    setBoardError('')
    api.board({
      demo: settings.demo, horizon: settings.horizon,
      country: filters.country, sector: filters.sector,
      focus: focusTicker, simplified: settings.simplified,
    })
      .then(b => { if (!cancel) setBoard(b) })
      .catch(e => { if (!cancel) setBoardError(String(e.message || e)) })
      .finally(() => { if (!cancel) setBoardLoading(false) })
    return () => { cancel = true }
  }, [settings.demo, settings.horizon, settings.simplified, filters.country, filters.sector,
      focusTicker, boardVersion])

  const saveEntry = useCallback((e: Entry) => {
    setEntries(prev => ({ ...prev, [e.ticker]: e }))
  }, [])

  const setFilters = useCallback((p: Partial<{ country: string; sector: string }>) => {
    setSettingsState(prev => {
      const next = { ...prev, filters: { ...prev.filters, ...p } }
      try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)) } catch { /* private mode */ }
      return next
    })
  }, [])

  const setFocus = useCallback((ticker: string) => setFocusTicker(ticker), [])

  const goDashboard = useCallback(() => setView({ name: 'dashboard' }), [])

  const openEvidence = useCallback((ticker: string) => {
    setFocusTicker(ticker)
    setView({ name: 'evidence', ticker })
  }, [])

  const ensureBuilt = useCallback(async (ticker: string): Promise<Entry | null> => {
    const existing = entries[ticker]
    if (existing) return existing
    try {
      const res = await api.monitor({ ticker, demo: settings.demo })
      saveEntry(res.entry)
      refreshBoard()
      return res.entry
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not build that snapshot.', 'bad')
      return null
    }
  }, [entries, settings.demo, saveEntry, refreshBoard, toast])

  const monitorOnly = useCallback(async (ticker: string) => {
    try {
      const res = await api.monitor({ ticker, demo: settings.demo })
      saveEntry(res.entry)
      setFocusTicker(ticker)
      refreshBoard()
      toast(`Monitoring ${res.entry.company.company}.`, 'good')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not build that snapshot.', 'bad')
    }
  }, [settings.demo, saveEntry, refreshBoard, toast])

  const openDeepDive = useCallback(async (ticker: string, mode: 'compete' | 'interrogate') => {
    const entry = await ensureBuilt(ticker)
    if (!entry) return
    setView({ name: 'deep', ticker, mode })
  }, [ensureBuilt])

  const buildLiveAndDive = useCallback(async (text: string, mode: 'compete' | 'interrogate') => {
    toast(`Building a live ESG profile for “${text}” (ASEAN check)…`)
    try {
      const res = await api.monitor({ text, demo: settings.demo })
      saveEntry(res.entry)
      refreshBoard()
      setFocusTicker(res.ticker)
      setView({ name: 'deep', ticker: res.ticker, mode })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Live build failed.', 'bad')
    }
  }, [settings.demo, saveEntry, refreshBoard, toast])

  const loadSample = useCallback(async () => {
    try {
      const res = await api.sample()
      saveEntry(res.entry)
      refreshBoard()
      setFocusTicker(res.ticker)
      setView({ name: 'deep', ticker: res.ticker, mode: 'compete' })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Sample failed.', 'bad')
    }
  }, [saveEntry, refreshBoard, toast])

  const uploadFile = useCallback(async (f: File) => {
    try {
      const res = await api.upload(f)
      saveEntry(res.entry)
      refreshBoard()
      toast(`Loaded ${res.entry.company.company} (${res.meta.mode}).`, 'good')
      setView({ name: 'deep', ticker: res.ticker, mode: 'compete' })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Upload failed.', 'bad')
    }
  }, [saveEntry, refreshBoard, toast])

  const unpin = useCallback(async (ticker: string) => {
    try {
      await api.unmonitor(ticker)
      setEntries(prev => {
        const next = { ...prev }
        delete next[ticker]
        return next
      })
      setCompareSel(sel => sel.filter(t => t !== ticker))
      refreshBoard()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Unpin failed.', 'bad')
    }
  }, [refreshBoard, toast])

  const toggleCompare = useCallback((ticker: string) => {
    setCompareSel(sel => sel.includes(ticker) ? sel.filter(t => t !== ticker) : [...sel, ticker])
  }, [])

  const openCompare = useCallback(() => {
    if (compareSel.length >= 2) setView({ name: 'compare', tickers: compareSel })
  }, [compareSel])

  const applySetup = useCallback((c: SetupChoice) => {
    setSettings({
      filters: { country: c.country, sector: c.sector },
      level: c.level, tier: c.tier, horizon: c.horizon, setupDone: true,
      profile: { mandate: c.mandate, goal: c.goal, label: c.label },
      // Screening wants the universe rails; investigating one name wants them out of the way.
      leftOpen: c.goal === 'screen' && c.level > 1,
      rightOpen: c.level > 1,
    })
  }, [setSettings])

  const restartSetup = useCallback(() => {
    setSettings({ setupDone: false })
    setView({ name: 'dashboard' })
  }, [setSettings])

  const sendChat = useCallback(async (text: string) => {
    const t = text.trim()
    if (!t || busyRef.current) return
    busyRef.current = true
    setChatLog(log => [...log, { role: 'user', text: t }])
    try {
      const res = await api.chat({
        text: t, demo: settings.demo, simplified: settings.simplified, focus_ticker: focusTicker,
      })
      setChatLog(log => [...log, { role: 'assistant', text: res.reply }])
      const a = res.action
      if (a.kind === 'filter') {
        setFilters({
          ...(a.country ? { country: a.country } : {}),
          ...(a.sector ? { sector: a.sector } : {}),
        })
      } else if (a.kind === 'focus') {
        setFocusTicker(a.ticker)
        if (a.needs_build) {
          api.monitor({ ticker: a.ticker, demo: settings.demo })
            .then(r => { saveEntry(r.entry); refreshBoard() })
            .catch(() => { /* board still shows the name */ })
        }
      } else if (a.kind === 'relay') {
        await openDeepDive(a.ticker, a.mode)
      } else if (a.kind === 'relay_live') {
        await buildLiveAndDive(a.text, a.mode)
      }
    } catch (e) {
      setChatLog(log => [...log, {
        role: 'assistant',
        text: e instanceof Error ? e.message : 'Something went wrong.',
      }])
    } finally {
      busyRef.current = false
    }
  }, [settings.demo, settings.simplified, focusTicker, openDeepDive, buildLiveAndDive, saveEntry,
    refreshBoard, setFilters])

  const value = useMemo<Store>(() => ({
    settings, setSettings, health, view, goDashboard, filters, setFilters,
    focusTicker, setFocus, board, boardLoading, boardError, refreshBoard,
    entries, saveEntry, monitorOnly, openDeepDive, openEvidence, buildLiveAndDive, loadSample,
    uploadFile, unpin, compareSel, toggleCompare, openCompare, applySetup, restartSetup,
    chatLog, sendChat, toasts, toast,
  }), [settings, setSettings, health, view, goDashboard, filters, setFilters, focusTicker,
    setFocus, board, boardLoading, boardError, refreshBoard, entries, saveEntry, monitorOnly,
    openDeepDive, openEvidence, buildLiveAndDive, loadSample, uploadFile, unpin, compareSel,
    toggleCompare, openCompare, applySetup, restartSetup, chatLog, sendChat, toasts, toast])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
