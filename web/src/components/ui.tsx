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
