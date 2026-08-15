import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { Board, Entry, Health, TierKey } from './types'

export type View =
  | { name: 'dashboard' }
  | { name: 'deep'; ticker: string; mode: 'compete' | 'interrogate' }
  | { name: 'compare'; tickers: string[] }
  | { name: 'evidence'; ticker: string }

export interface Settings {
  demo: boolean
  dark: boolean
  simplified: boolean
  leftOpen: boolean
  rightOpen: boolean
  ragEnabled: boolean
  ragTopK: number
  /** A5 — risk appetite. 'all' shows the whole matrix; a tier DIMS the rest, never hides it. */
  tier: TierKey | 'all'
  /** A6 — origination pipeline filter: the Balanced condition as a toggle. */
  pipelineOnly: boolean
}

interface Toast { id: number; text: string; tone: 'good' | 'bad' | 'info' }
interface ChatMsg { role: 'user' | 'assistant'; text: string }

const SETTINGS_KEY = 'esg-radar-settings'
const DEFAULTS: Settings = {
  demo: true, dark: true, simplified: true, leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', pipelineOnly: false,
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
  const [filters, setFiltersState] = useState({ country: 'All', sector: 'All' })
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

  const setSettings = useCallback((p: Partial<Settings>) => {
    setSettingsState(prev => {
      const next = { ...prev, ...p }
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
      demo: settings.demo, country: filters.country, sector: filters.sector,
      focus: focusTicker, simplified: settings.simplified,
    })
      .then(b => { if (!cancel) setBoard(b) })
      .catch(e => { if (!cancel) setBoardError(String(e.message || e)) })
      .finally(() => { if (!cancel) setBoardLoading(false) })
    return () => { cancel = true }
  }, [settings.demo, settings.simplified, filters.country, filters.sector, focusTicker, boardVersion])

  const saveEntry = useCallback((e: Entry) => {
    setEntries(prev => ({ ...prev, [e.ticker]: e }))
  }, [])

  const setFilters = useCallback((p: Partial<{ country: string; sector: string }>) => {
    setFiltersState(prev => ({ ...prev, ...p }))
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
        setFiltersState(prev => ({
          country: a.country ?? prev.country,
          sector: a.sector ?? prev.sector,
        }))
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
  }, [settings.demo, settings.simplified, focusTicker, openDeepDive, buildLiveAndDive, saveEntry, refreshBoard])

  const value = useMemo<Store>(() => ({
    settings, setSettings, health, view, goDashboard, filters, setFilters,
    focusTicker, setFocus, board, boardLoading, boardError, refreshBoard,
    entries, saveEntry, monitorOnly, openDeepDive, openEvidence, buildLiveAndDive, loadSample,
    uploadFile, unpin, compareSel, toggleCompare, openCompare, chatLog, sendChat, toasts, toast,
  }), [settings, setSettings, health, view, goDashboard, filters, setFilters, focusTicker,
    setFocus, board, boardLoading, boardError, refreshBoard, entries, saveEntry, monitorOnly,
    openDeepDive, openEvidence, buildLiveAndDive, loadSample, uploadFile, unpin, compareSel,
    toggleCompare, openCompare, chatLog, sendChat, toasts, toast])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
