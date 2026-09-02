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
 * The PPP trilemma — how this fund balances Profit, People and Planet. It is a LENS over one
 * unchanged run, not a second scoring model: no weight in `engine_config.json` moves, no record
 * is re-scored, and `disagreement` keeps meaning exactly what every surface says it means.
 * What changes is which names are dimmed and which of the two momentum directions leads.
 *
 *   profit  — Profit First. Price momentum leads and ESG is a strict DOWNSIDE GATE: a name
 *             whose dated evidence is deteriorating dims however well the price has run. That
 *             is the "Divergence — downside risk" shape, used as a veto rather than a note.
 *   balanced— the default. Both directions shown, neither leading, nothing dimmed.
 *   planet  — Sustainability Focus. The labelled green-bond hurdle first, which is the same
 *             `green_bond_status` field the Conservative tier and the N bucket read.
 *
 * Every one of the three DOES something on screen. A question whose answer only changes a
 * summary line is decoration, and worse than not asking — see the setup note in CLAUDE.md.
 */
export type PPP = 'profit' | 'balanced' | 'planet'

/**
 * WHICH universe the board is scoring.
 *
 *   cgsi    — CGSI's verified 52, the ESG Momentum foundation basket. The default, and the only
 *             one the "55.1% vs 6.4%" claim describes.
 *   indexes — the ~185 largest listings across five ASEAN markets (STI, KLCI, SET50, LQ45,
 *             PSEi). Selected for size and liquidity with NO ESG screen, so none carries an
 *             incumbent rating and every one is labelled `unrated` until one is supplied.
 *
 * It is deliberately NOT folded into `demo`. `demo` means FICTIONAL and gates prices, quotes and
 * the harvest — none of which may run against invented companies (rule 2). These are both real.
 */
export type UniverseKey = 'cgsi' | 'indexes'
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

/*
 * THERE IS NO `audience` SETTING ANY MORE (removed 2026-09-01).
 *
 * The app carried two renderings of one run: an `investor` view that put every finding in plain
 * sentences and folded the desk furniture away, and the `analyst` view it was built as. That
 * fork existed for a reader holding forty shares of the bank in question — and that is not who
 * this is for. The audience is a CGSI ESG investor: someone who reads a research note, knows
 * what a percentile is, and needs the run id, the cohort, the tiers and the thresholds ON SCREEN
 * rather than one click behind a "Show the numbers" button.
 *
 * So the plain rendering is gone rather than defaulted-off — `InvestorCard`, `MatchList` and
 * `lib/plain.ts` with it. Two renderings of one number always drift, and the softer one wins the
 * drift: it is the one nobody re-checks against the engine. Every surface now states the figure
 * the engine computed, with its provenance beside it, and says plainly what it cannot answer.
 */

/** Which half of the app is on screen. See `Settings.tab`. */
export type BoardTab = 'board' | 'context' | 'clients' | 'manual'

/**
 * A board module that can be pinned on regardless of `level`. The registry — what each one is
 * and which level shows it on its own — lives in `lib/modules.ts`; only the key is here, so
 * `Settings` stays the single description of what is persisted.
 */
export type ModuleKey = 'matrix' | 'case' | 'classification' | 'rankings' | 'universe'
  | 'news' | 'price' | 'rails' | 'residual' | 'roadmap' | 'triangle'

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
  /**
   * The company on screen, remembered across reloads.
   *
   * It used to live only in component state, which is right for an analyst sweeping a universe
   * and wrong for the reader who came to look at one name: they type it once, reload, and are
   * back on somebody else's company while the header still says "looking at" theirs.
   */
  focus: string
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
   *
   * DERIVED from `ppp` in setSettings, exactly as `simplified` is derived from `level`: the
   * Sustainability Focus lens IS the green-bond hurdle, and two controls that can express the
   * same preference differently will eventually disagree on screen.
   */
  greenFocus: boolean
  /** The PPP trilemma lens. See the `PPP` type for what each one actually does. */
  ppp: PPP
  /** Which real universe is on the board. Ignored while `demo` is on. */
  universe: UniverseKey
  /*
   * `matrixPlot` is gone (2026-09-01). The panel briefly carried two plots behind a toggle —
   * incumbent rating across, or price across — and the rating one was removed on instruction.
   * With one plot left the setting had nothing to select, so it went rather than persisting a
   * value nothing reads. The rating percentile is still on every record and still drives every
   * quadrant LABEL; it is the drawing that was dropped, not the engine.
   */
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
  ppp: PPP
  label: string
}

interface Toast { id: number; text: string; tone: 'good' | 'bad' | 'info' }
interface ChatMsg { role: 'user' | 'assistant'; text: string }

const SETTINGS_KEY = 'esg-radar-settings'
const DEFAULTS: Settings = {
  demo: true, dark: true, simplified: true, level: 1, tab: 'board', setupDone: false,
  tourDone: false, extras: [], focus: '', tourDeck: '',
  profile: { mandate: '', goal: '', holding: '', focus: '', label: '' },
  filters: { country: 'All', sector: 'All' },
  leftOpen: false, rightOpen: false,
  ragEnabled: true, ragTopK: 5, tier: 'balanced', horizon: 'long', pipelineOnly: false,
  greenFocus: false, ppp: 'balanced', universe: 'cgsi',
}

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) {
      const stored = { ...DEFAULTS, ...JSON.parse(raw) }
      // Level 2 is gone. Migrate up, never down — losing panels you had is a worse surprise
      // than gaining the matrix, and every one of them is a chip away either direction.
      if ((stored.level as number) === 2) stored.level = 3
      // The investor rendering is gone. A browser that stored `audience: 'investor'` also stored
      // `level: 1`, which was that view's home — leaving it there would open the full analyst
      // board with most of it switched off, which reads as a broken upgrade rather than a
      // removed feature. Both keys are dropped and the level comes up with them.
      if ('audience' in stored) {
        if (stored.audience === 'investor' && (stored.level as number) === 1) stored.level = 3
        delete (stored as Record<string, unknown>).audience
        delete (stored as Record<string, unknown>).showNumbers
      }
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
  /*
   * `setupFull` is gone with the investor rendering. It existed to force the six-step flow for a
   * reader whose first run was a single question ("which company?"); there is only one setup
   * now, and it always asks the full set — a CGSI ESG investor is choosing a mandate, an
   * appetite, a holding period and a PPP balance, and each one changes what the board shows.
   */
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
      // Same discipline, one setting over: the Sustainability Focus lens IS the green-bond
      // hurdle, so `greenFocus` is derived rather than set alongside it. Setting `greenFocus`
      // directly still works and pulls `ppp` with it, so the older control and the new lens can
      // never end up describing different preferences on the same screen.
      if (p.ppp !== undefined) next.greenFocus = p.ppp === 'planet'
      else if (p.greenFocus !== undefined && prev.ppp !== 'profit') {
        next.ppp = p.greenFocus ? 'planet' : 'balanced'
      }
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
      focus: focusTicker, simplified: settings.simplified, universe: settings.universe,
    })
      .then(b => { if (!cancel) setBoard(b) })
      .catch(e => { if (!cancel) setBoardError(String(e.message || e)) })
      .finally(() => { if (!cancel) setBoardLoading(false) })
    return () => { cancel = true }
  }, [settings.demo, settings.horizon, settings.simplified, settings.universe,
      filters.country, filters.sector, focusTicker, boardVersion])

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
    setSettings({
      filters: { country: c.country, sector: c.sector },
      level: c.level, tier: c.tier, horizon: c.horizon, setupDone: true,
      // `ppp` is set here rather than `greenFocus`, and setSettings derives the other from it.
      ppp: c.ppp,
      profile: { mandate: c.mandate, goal: c.goal, holding: c.holding, focus: c.focus,
                 label: c.label },
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
    uploadFile, unpin, compareSel, toggleCompare, openCompare, applySetup, restartSetup,
    chatLog, sendChat, toasts, toast,
  }), [settings, setSettings, health, view, goDashboard, filters, setFilters, focusTicker,
    setFocus, board, boardLoading, boardError, refreshBoard, entries, saveEntry, monitorOnly,
    openDeepDive, openEvidence, buildLiveAndDive, loadSample, uploadFile, unpin, compareSel,
    toggleCompare, openCompare, applySetup, restartSetup, chatLog, sendChat, toasts, toast])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
