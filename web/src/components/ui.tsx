import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'

export function signClass(v: number | null | undefined): string {
  if (v == null) return 'cc-flat'
  return v > 0 ? 'cc-pos' : v < 0 ? 'cc-neg' : 'cc-flat'
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  const n = Number.isInteger(v) ? v : v
  return `${sign}${n}%`
}

/** A pillar reading formatted for the SCALE it is actually on.
 *
 *  'numeric' is a momentum percent and keeps the percent sign. 'evidence' is the engine's
 *  direction consensus, bounded to ±1.00, and must NOT carry one — "+0.59%" reads as a
 *  half-percent move when the number means "the evidence agrees, fairly strongly, that this is
 *  improving". Same digits, completely different claim, and the percent version is the kind of
 *  wrong that nobody spots because nothing looks broken. */
export function fmtPillar(v: number | null | undefined, basis?: string): string {
  if (v == null) return '—'
  if (basis !== 'evidence') return fmtPct(v)
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

export function shortSector(s: string | undefined | null): string {
  if (!s || s === 'All') return 'All industries'
  return s.split('—').pop()?.trim() || s
}

export function known(v: unknown): boolean {
  return Boolean(v) && String(v).trim().toLowerCase() !== 'unknown'
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="cc-chart-head">
      <span className="cc-chart-title">{children}</span>
      {sub && <span className="cc-chart-sub">{sub}</span>}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="loading-row">
      <span className="spinner" />
      {label && <span>{label}</span>}
    </div>
  )
}

export function Tone({ tone, children }: { tone: string; children: ReactNode }) {
  const cls = tone === 'good' ? 'cc-pos' : tone === 'warn' || tone === 'caution' ? 'cc-warn'
    : tone === 'bad' ? 'cc-neg' : 'cc-flat'
  return <b className={cls}>{children}</b>
}

export const TONE_CLASS: Record<string, string> = {
  good: 'cc-class-good', bad: 'cc-class-bad', neutral: 'cc-class-neutral',
}

export const AXIS_META: Record<string, { icon: string; name: string }> = {
  materiality: { icon: '🎯', name: 'Materiality' },
  time_horizon: { icon: '⏱️', name: 'Time horizon' },
  mandate: { icon: '🧭', name: 'Mandate' },
  blind_spot: { icon: '🕳️', name: 'Blind-spot' },
}

export function download(filename: string, text: string) {
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/* ---------------------------------------------------------------------------------------------
 * Collapsible sections.
 *
 * The board is layered already (`settings.level` decides WHAT is on the page), but layering
 * answers "how much detail do I want" and not "I want that one thing out of the way right now".
 * Those are different questions, so folding is per-panel, remembered per browser, and completely
 * independent of the level.
 *
 * `UniverseGrid` had its own Show/Hide toggle before this existed; these share its idiom rather
 * than introducing a second one.
 * ------------------------------------------------------------------------------------------- */

const SECTIONS_KEY = 'esg.sections'

function readSections(): Record<string, boolean> {
  // Every access is guarded: a private window, cleared site data, or a browser set to block
  // storage can make even the getter throw, and a board that will not render because a
  // preference could not be read is a far worse failure than a panel opening when it was folded.
  try {
    return JSON.parse(localStorage.getItem(SECTIONS_KEY) || '{}') || {}
  } catch { return {} }
}

/** Fold state for one panel: `[open, toggle]`, persisted per browser. */
export function useCollapsed(id: string, defaultOpen = true): [boolean, () => void] {
  const [open, setOpen] = useState<boolean>(() => {
    const stored = readSections()[id]
    return typeof stored === 'boolean' ? stored : defaultOpen
  })
  const toggle = useCallback(() => {
    setOpen(prev => {
      const next = !prev
      try {
        localStorage.setItem(SECTIONS_KEY, JSON.stringify({ ...readSections(), [id]: next }))
      } catch { /* preference is a convenience, never a requirement */ }
      return next
    })
  }, [id])
  return [open, toggle]
}

/**
 * One foldable panel. `id` is the persistence key, so keep it stable — renaming it silently
 * resets everyone's folds back to the default.
 */
export function Section({ id, title, sub, right, children, defaultOpen = true, className = '' }: {
  id: string
  title: ReactNode
  sub?: ReactNode
  right?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  const [open, toggle] = useCollapsed(id, defaultOpen)
  return (
    <div className={`panel-block section ${open ? 'is-open' : 'is-closed'} ${className}`}>
      <div className="section-head">
        <button className="section-toggle" onClick={toggle} aria-expanded={open}
          title={open ? 'Fold this section' : 'Unfold this section'}>
          <span className="section-chev" aria-hidden="true">▾</span>
          <span className="cc-h section-title">{title}</span>
        </button>
        {right}
      </div>
      {/* Unmounted rather than hidden: several of these panels fetch or measure on mount, and a
          folded panel should not be paying for either. */}
      {open && (
        <div className="section-body">
          {sub && <div className="cc-muted">{sub}</div>}
          {children}
        </div>
      )}
    </div>
  )
}
