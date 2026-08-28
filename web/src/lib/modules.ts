/**
 * The board's modules — what each LEVEL shows, and what you can pin ON TOP of it.
 *
 * `settings.level` is progressive disclosure: 1 Preferences · 3 Everything. It answers
 * "how much do you want on screen" with one number, which is the right default and the wrong
 * cage. A reader who wants the verdict and the disagreement matrix — and nothing else — had to
 * take the whole of Analysis and Everything to get it, and then read past six panels they did
 * not ask for. That is the same failure the levels were introduced to fix, arrived at from the
 * other direction.
 *
 * So a module is on when EITHER its level has arrived or the reader has pinned it:
 *
 *     shown = at(level)  ||  extras.includes(key)
 *
 * Both halves live here, in one list, because the picker and the panels have to agree about
 * what is currently on screen — a picker offering to add something already rendered, or hiding
 * something that is not, is worse than no picker.
 *
 * `at` is a predicate rather than a minimum level because one module is not monotonic:
 * `rankings` appears at level 2 and is deliberately GONE at level 3, where the matrix panel
 * already lists the same four names beside the plot. It can still be pinned there, which is the
 * point of pinning.
 */
import type { Level, ModuleKey, Settings } from '../store'

export interface ModuleDef {
  key: ModuleKey
  label: string
  /** One line, in the picker. Say what it shows, not what it is called. */
  blurb: string
  /** Where it turns up on its own. */
  at: (level: Level) => boolean
}

export const MODULES: ModuleDef[] = [
  { key: 'matrix', label: 'Disagreement matrix', at: lv => lv === 3,
    blurb: 'All 52 plotted: the rating across, our evidence up. The four quadrants.' },
  { key: 'case', label: 'Why this verdict', at: lv => lv === 3,
    blurb: 'The case for and against, on both axes, plus what would change it.' },
  { key: 'classification', label: 'Classification', at: lv => lv === 3,
    blurb: 'What we call this company, and the rule that decided it.' },
  // Pin-only, and deliberately so: at Everything the matrix panel already lists the same four
  // names beside the plot, which is where this panel used to duplicate them.
  { key: 'rankings', label: 'Hidden winners vs peers', at: () => false,
    blurb: 'How far our evidence puts each name above its published score.' },
  { key: 'universe', label: 'Universe grid', at: lv => lv === 3,
    blurb: 'Every company in the filter, as one clickable grid.' },
  { key: 'news', label: 'Recent news', at: lv => lv === 3,
    blurb: 'Dated headlines for the focused company. Context, never a signal.' },
  { key: 'price', label: 'Price strip', at: lv => lv === 3,
    blurb: 'Last price and the 90-day move. Context only — no part of any score.' },
  { key: 'rails', label: 'Side rails', at: lv => lv === 3,
    blurb: 'Filters and the monitored list on the left, the assistant log on the right.' },
]

const byKey = new Map(MODULES.map(m => [m.key, m]))

/** The single question every level-gated block and the picker both ask. */
export function showModule(key: ModuleKey, s: Settings): boolean {
  const m = byKey.get(key)
  if (!m) return false
  return m.at(s.level) || s.extras.includes(key)
}

/** On because the LEVEL brings it — so it keeps its designed position on the page. */
export const isNative = (key: ModuleKey, s: Settings) => byKey.get(key)?.at(s.level) ?? false

/** Pinned by hand, rather than arriving with the level — what the picker draws as removable. */
export const isPinned = (key: ModuleKey, s: Settings) =>
  s.extras.includes(key) && !isNative(key, s)
