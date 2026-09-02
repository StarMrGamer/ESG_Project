/**
 * Anchoring — scroll a `data-tour` element into the free band, and ring it.
 *
 * Two features point at the live DOM: PRESENT MODE (the pitch, driven through the real app) and
 * the first-run TUTORIAL. They want the same three behaviours and nothing else in common, so the
 * behaviours live here rather than being written twice — a second spotlight implementation would
 * drift from this one the first time either bar changed height.
 *
 * The only thing that differs between the two callers is how much of the bottom of the screen
 * their own chrome is covering, so that is the parameter.
 */
import { useLayoutEffect, useState } from 'react'

/**
 * The sticky header both callers sit under — MEASURED, not assumed.
 *
 * This was a constant 62 and the header is now 124: it grew a second row (the tab strip) and the
 * number never followed. Nothing broke loudly — every anchored step simply scrolled its target
 * about sixty pixels too high, so the ring landed correctly and the panel's own TITLE sat under
 * the tab bar. That is the worst kind of drift for a demo: the step points at the right thing
 * and the first line of it is covered.
 *
 * So it is read off the DOM, the same discipline the matrix uses for its own width. The constant
 * survives only as the fallback for the moment before the header has painted, and any future row
 * added to the header is now free.
 */
export const HEADER_FALLBACK_H = 124

export function headerH(): number {
  const h = document.querySelector('.cc-header')
  if (!h) return HEADER_FALLBACK_H
  const r = h.getBoundingClientRect()
  // A header scrolled out of a non-sticky context, or not yet laid out, must not report ~0 and
  // send every anchor to the top of the document.
  return r.height > 8 ? r.height : HEADER_FALLBACK_H
}
/** Present mode's bar — a control strip since the cue line came off it. */
export const PRESENT_BAR_H = 104

export const el = (anchor: string) => document.querySelector(`[data-tour="${anchor}"]`)

/**
 * `scrollIntoView({block: 'center'})` centres against the WHOLE viewport, which is wrong twice
 * here: the top is under a sticky header and the bottom is under the caller's own bar. On a
 * panel taller than what is left — the evidence trail is — centring pushes its heading off the
 * top of the screen, so the step that says "fourteen signals, each one dated" scrolled past the
 * dates. Tall anchors pin their top instead; short ones centre in the free band.
 */
export function anchorTarget(node: Element, barH = PRESENT_BAR_H): number {
  const head = headerH()
  const free = window.innerHeight - head - barH
  const r = node.getBoundingClientRect()
  const top = r.top + window.scrollY
  return Math.max(0, r.height > free
    ? top - head - 16
    : top - head - Math.max(12, (free - r.height) / 2))
}

/**
 * Align, then KEEP aligning for a moment.
 *
 * A deep dive mounts and then grows: the LSEG panel fetches the live incumbent rating and the
 * benchmark strip fetches a quote, and both land ABOVE the relay a second or two later. A
 * one-shot scroll computed before they arrive leaves the anchor a thousand pixels below the
 * fold — measured, on the step whose whole job is to point at the relay. So the alignment is
 * re-checked while the page settles, and gives up the moment it has been stable twice or the
 * viewer has taken the wheel.
 */
export function trackAnchor(anchor: string, alive: () => boolean, barH = PRESENT_BAR_H) {
  let stable = 0
  let expected = -1
  const tick = () => {
    if (!alive()) return
    const node = el(anchor)
    if (!node) return
    // They scrolled somewhere themselves — stop fighting them.
    if (expected >= 0 && Math.abs(window.scrollY - expected) > 120) return
    const target = anchorTarget(node, barH)
    if (Math.abs(target - window.scrollY) < 24) { if (++stable >= 2) return }
    else stable = 0
    expected = target
    window.scrollTo({ top: target, behavior: 'smooth' })
  }
  tick()
  const ids = [400, 900, 1500, 2200, 3000].map(ms => window.setTimeout(tick, ms))
  return () => ids.forEach(clearTimeout)
}

/** Rings the element a step points at. Purely decorative — never eats a click. */
export function Spotlight({ anchor, className = 'present-ring' }:
                          { anchor: string | undefined; className?: string }) {
  const [box, setBox] = useState<DOMRect | null>(null)

  useLayoutEffect(() => {
    if (!anchor) { setBox(null); return }
    let raf = 0
    const measure = () => {
      const node = el(anchor)
      setBox(node ? node.getBoundingClientRect() : null)
      raf = requestAnimationFrame(measure)
    }
    // Tracked per frame rather than on scroll/resize listeners: the ring has to stay glued to a
    // panel that is being smooth-scrolled AND may still be growing as its data lands.
    raf = requestAnimationFrame(measure)
    return () => cancelAnimationFrame(raf)
  }, [anchor])

  if (!box || box.width === 0) return null
  return (
    <div className={className} style={{
      top: box.top - 8, left: box.left - 8, width: box.width + 16, height: box.height + 16,
    }} />
  )
}
