import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { Board, Entry, Health, HorizonKey, TierKey } from './types'

/** The mandate the user set up with — the same vocabulary Contract A's `mandate` uses. */
export type Mandate = 'risk' | 'return' | 'compliance'
/** Which of the two journeys the setup handed off to. */
export type Goal = 'screen' | 'investigate'
/**
 * How long the user expects to hold. NOT the same quantity as the decay horizon — that is how
 * fast EVIDENCE goes stale, measured in days — but it is the honest input the horizon should be
 * derived FROM, which is why it is asked for directly instead of inferred from the mandate.
 */
export type Holding = 'under_2y' | '2_5y' | '5y_plus'
/**
 * Thematic focus. `green` prefers issuers carrying a labelled green bond — real metadata
 * (`green_bond_status`), not a sentiment guess. Non-matching names DIM, never disappear, which
 * is the same discipline the risk tiers already follow.
 */
export type Focus = 'broad' | 'green'
/**
 * How much of the board is on screen. This is the layering control: every widget declares the
 * level it earns its place at, and nothing above the current level renders. Level 1 is the
 * default for a first-time user — the dashboard used to open with all three at once, which is
 * the "overstimulating" complaint this exists to answer.
 */
/**
 * Two levels, not three. `2 · Analysis` was the middle of a ladder, and once modules became
 * pinnable (`extras`, see lib/modules.ts) it had no job left: it was "Preferences plus five
 * specific panels", which is exactly what pinning five chips does, only fixed. What remains is
 * the honest pair — the board your setup answers shaped, or all of it.
 *
 * A stored `2` migrates to 3 in `loadSettings`, upward on purpose: a returning browser should
 * find everything it had on screen still on screen, never less.
 */
export type Level = 1 | 3

export interface Profile {
  mandate: Mandate | ''
  goal: Goal | ''
  holding: Holding | ''
  focus: Focus | ''
  /** One line describing the setup, shown back to the user so the personalisation is legible. */
  label: string
}

export type View =
  | { name: 'dashboard' }
  | { name: 'deep'; ticker: string; mode: 'compete' | 'interrogate' }
  | { name: 'compare'; tickers: string[] }
  | { name: 'evidence'; ticker: string }

/**
 * WHO is reading. Not a permission and not a data switch — the same run, the same arithmetic,
 * rendered for two different readers.
 *
 *   investor — the default, and the one a first-time visitor gets. Findings as sentences, the
 *              desk furniture (percentiles, N/M/K, tiers, run ids, the Merkle root) folded away.
 *   analyst  — the app as built: every number, every control, nothing translated.
 *
 * It is deliberately NOT another level. `level` answers "how much of the board", `audience`
 * answers "in whose vocabulary" — and an analyst on Preferences and an investor on Everything
 * are both coherent things to be.
 */
export type Audience = 'investor' | 'analyst'

/** Which half of the app is on screen. See `Settings.tab`. */
export type BoardTab = 'board' | 'context' | 'clients' | 'manual'

/**
 * A board module that can be pinned on regardless of `level`. The registry — what each one is
 * and which level shows it on its own — lives in `lib/modules.ts`; only the key is here, so
 * `Settings` stays the single description of what is persisted.
 */
export type ModuleKey = 'matrix' | 'case' | 'classification' | 'rankings' | 'universe'
  | 'news' | 'price' | 'rails'

export interface Settings {
  demo: boolean
  dark: boolean
  /**
   * Kept as the server-facing flag (the board endpoint tailors its copy on it) but no longer set
   * directly — it is derived from `level` in setSettings, so the two can never disagree.
   */
  simplified: boolean
  /** Progressive disclosure: 1 Preferences · 3 Everything. */
  level: Level
  /**
   * Board vs Context. `level` answers "how much detail", which is a different question from
   * "does this move when I click a company". Several panels — the foundation backtest, the
   * industry benchmark table, the five validation cases, the pillar momentum series — are the
   * same picture whichever constituent is focused, so on the board they read as bloat between
   * the reader and the thing that did change. They are not less important; they answer a
   * question about the METHOD rather than about a company, so they get their own tab.
   */
  tab: BoardTab
  /** False until the assistant-led setup has run; gates the whole dashboard. */
  setupDone: boolean
  /**
   * False until the first-run tutorial has been seen or skipped. Separate from `setupDone`
   * because they answer different questions — setup shapes the board, the tutorial teaches the
   * board — and because Reconfigure must be able to re-run one without replaying the other.
   */
  tourDone: boolean
  audience: Audience
  /**
   * The company on screen, remembered across reloads.
   *
   * It used to live only in component state, which is right for an analyst sweeping a universe
   * and wrong for the reader who came to look at one name: they type it once, reload, and are
   * back on somebody else's company while the header still says "looking at" theirs.
   */
  focus: string
  /** Investor view only: reveal the analyst rendering in place. Never a wall, always a click. */
  showNumbers: boolean
  /**
   * A walkthrough asked for BY NAME, rather than the first-run one. '' is none; 'matrix' explains
   * the disagreement plot corner by corner. It outranks `tourDone` — someone who clicks "What am
   * I looking at?" is asking now, and having seen a different tour once is no reason to refuse.
   */
  tourDeck: '' | 'matrix'
  /**
   * Modules pinned ON TOP of the level — "Preferences, plus the disagreement matrix". The level is a
   * good default and a bad cage: wanting the verdict and the matrix should not cost you the
   * whole of Analysis and Everything. Empty for everyone who never opens the picker.
   */
  extras: ModuleKey[]
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
  /**
   * Thematic preference from the setup. Like `tier` this DIMS rather than hides: a green-finance
   * mandate still has to be able to see the name it is choosing not to hold.
   */
  greenFocus: boolean
}

/** Everything the setup flow decides, applied in one shot so the board refetches once. */
export interface SetupChoice {
  mandate: Mandate
  goal: Goal
  holding: Holding
  focus: Focus
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
  demo: true, dark: true, simplified: true, level: 1, tab: 'board', setupDone: false,
  tourDone: false, extras: [], audience: 'investor', showNumbers: false, focus: '', tourDeck: '',
  profile: { mandate: '', goal: '', holding: '', focus: '', label: '' },
  filters: { country: 'All', sector: 'All' },
  leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', horizon: 'long', pipelineOnly: false,
  greenFocus: false,
}

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) {
      const stored = { ...DEFAULTS, ...JSON.parse(raw) }
      // Level 2 is gone. Migrate up, never down — losing panels you had is a worse surprise
      // than gaining the matrix, and every one of them is a chip away either direction.
      if ((stored.level as number) === 2) stored.level = 3
      return stored
    }
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
  /**
   * True while RECONFIGURE is running. The one-question start is for a first-time visitor who
   * has no preferences yet; somebody who deliberately went looking for "Reconfigure" is asking
   * to choose them, and handing them the same single question back is a dead end wearing a
   * button's clothes. Not persisted — it describes what the user is doing right now.
   */
  setupFull: boolean
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
  const [focusTicker, setFocusTicker] = useState(() => loadSettings().focus)
  const [setupFull, setSetupFull] = useState(false)
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

  const setFocus = useCallback((ticker: string) => {
    setFocusTicker(ticker)
    setSettings({ focus: ticker })
  }, [setSettings])

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
    setSetupFull(false)
    setSettings({
      filters: { country: c.country, sector: c.sector },
      level: c.level, tier: c.tier, horizon: c.horizon, setupDone: true,
      greenFocus: c.focus === 'green',
      profile: { mandate: c.mandate, goal: c.goal, holding: c.holding, focus: c.focus,
                 label: c.label },
      // Screening wants the universe rails; investigating one name wants them out of the way.
      leftOpen: c.goal === 'screen' && c.level > 1,
      rightOpen: c.level > 1,
    })
  }, [setSettings])

  const restartSetup = useCallback(() => {
    setSetupFull(true)
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
      } else if (a.kind === 'monitor') {
        // "add DBS" keeps it: build the snapshot and pin it to the watchlist, which is what the
        // left rail lists and what survives a reload. Focus alone would have looked identical
        // for one click and then quietly lost the name.
        if (a.already) setFocusTicker(a.ticker)
        else await monitorOnly(a.ticker)
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
      monitorOnly,
    refreshBoard, setFilters])

  const value = useMemo<Store>(() => ({
    settings, setSettings, health, view, goDashboard, filters, setFilters,
    focusTicker, setFocus, board, boardLoading, boardError, refreshBoard,
    entries, saveEntry, monitorOnly, openDeepDive, openEvidence, buildLiveAndDive, loadSample,
    uploadFile, unpin, compareSel, toggleCompare, openCompare, applySetup, restartSetup, setupFull,
    chatLog, sendChat, toasts, toast,
  }), [settings, setSettings, health, view, goDashboard, filters, setFilters, focusTicker,
    setFocus, board, boardLoading, boardError, refreshBoard, entries, saveEntry, monitorOnly,
    openDeepDive, openEvidence, buildLiveAndDive, loadSample, uploadFile, unpin, setupFull, compareSel,
    toggleCompare, openCompare, applySetup, restartSetup, chatLog, sendChat, toasts, toast])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
