import { useStore } from '../../store'
import { fmtPct, signClass, Tone, TONE_CLASS } from '../ui'
import type { Pillar } from '../../types'

/**
 * RadarHub — the board, centred.
 *
 * The dashboard was a vertical stack: cards in a column, each one full width, most of the
 * viewport left empty below them at level 1. This puts the company in the middle and arranges
 * its four pillar readings around it, which is both a denser use of the screen and the shape the
 * product is named after.
 *
 * The plot earns its place rather than decorating: the emphasised ring is ZERO momentum — what a
 * static rating implicitly assumes, that nothing has moved since it was published — and the
 * filled shape is what our live signals say. The gap between ring and shape is the disagreement,
 * which is the entire thesis, drawn once instead of argued in four separate cards.
 *
 * No sweep, no rotation, no pulse. The brief was a calmer screen, and an animated radar would
 * have been the first thing to undo it.
 */

const CX = 160
const CY = 160
/** Zero sits here; positive momentum pushes out toward RMAX, negative pulls in toward RMIN. */
const R0 = 74
const RMAX = 118
const RMIN = 30

/** Where each pillar's spoke points, in degrees, 0 = east. Matches the satellite card layout. */
const ANGLE: Record<string, number> = {
  environment: -90,   // top
  governance: 0,      // right
  digital_ai: 90,     // bottom
  social: 180,        // left
}
const ORDER = ['environment', 'governance', 'digital_ai', 'social']

function polar(angleDeg: number, radius: number) {
  const a = (angleDeg * Math.PI) / 180
  return { x: CX + radius * Math.cos(a), y: CY + radius * Math.sin(a) }
}

function RadarPlot({ pillars, scale }: { pillars: Record<string, Pillar>; scale: number }) {
  const radiusFor = (v: number | null | undefined) => {
    if (v == null) return R0
    const t = Math.max(-1, Math.min(1, v / scale))
    return R0 + t * (t >= 0 ? RMAX - R0 : R0 - RMIN)
  }

  const points = ORDER.map(key => {
    const p = pillars[key]
    return { key, p, ...polar(ANGLE[key], radiusFor(p?.value)) }
  })
  const path = points.map((pt, i) => `${i ? 'L' : 'M'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ') + ' Z'

  const known = ORDER.map(k => pillars[k]?.value).filter((v): v is number => v != null)
  const mean = known.length ? known.reduce((a, b) => a + b, 0) / known.length : 0
  const tone = mean > 0 ? 'is-pos' : mean < 0 ? 'is-neg' : 'is-flat'

  return (
    <svg viewBox="0 0 320 320" className="radar-plot" role="img"
      aria-label="Live pillar momentum against the zero line a static rating assumes">
      {/* Scale rings. The R0 one is emphasised because it carries a meaning the others don't. */}
      {[RMIN, (RMIN + R0) / 2, (R0 + RMAX) / 2, RMAX].map(r => (
        <circle key={r} cx={CX} cy={CY} r={r} className="radar-ring" />
      ))}
      <circle cx={CX} cy={CY} r={R0} className="radar-zero" />

      {ORDER.map(key => {
        const end = polar(ANGLE[key], RMAX + 6)
        return <line key={key} x1={CX} y1={CY} x2={end.x} y2={end.y} className="radar-spoke" />
      })}

      <path d={path} className={`radar-shape ${tone}`} />

      {points.map(pt => (
        <circle key={pt.key} cx={pt.x} cy={pt.y} r={4.5} className={`radar-node ${tone}`}>
          <title>{`${pt.p?.label ?? pt.key}: ${fmtPct(pt.p?.value)}`}</title>
        </circle>
      ))}
    </svg>
  )
}

function Satellite({ pillar, area, scale }: {
  pillar: Pillar | undefined
  area: string
  scale: number
}) {
  if (!pillar) return <div className={`hub-sat is-${area}`} />
  const v = pillar.value
  // A diverging bar off the same centre line as the plot's dashed ring: it grows right when the
  // pillar is improving and left when it is not, so the card and the shape agree at a glance.
  // A real but tiny reading would round to a sliver of a pixel and read as a rendering fault,
  // so anything non-zero keeps a visible stub.
  const raw = v == null ? 0 : Math.max(-1, Math.min(1, v / scale)) * 50
  const pct = raw === 0 ? 0 : Math.sign(raw) * Math.max(Math.abs(raw), 1.6)
  const sign = signClass(v)
  return (
    <div className={`hub-sat is-${area} ${pillar.fast ? 'is-fast' : ''}`}>
      <div className="hub-sat-label">{pillar.label}</div>
      <div className={`hub-sat-val ${pillar.fast ? '' : sign}`}>{fmtPct(v)}</div>
      <div className="hub-sat-bar" title={`${fmtPct(v)} against a ±${scale.toFixed(1)}% scale`}>
        <span className="hub-sat-axis" />
        <span className={`hub-sat-fill ${sign}`}
          style={{ left: pct < 0 ? `${50 + pct}%` : '50%', width: `${Math.abs(pct)}%` }} />
      </div>
      <div className={`hub-sat-trend ${pillar.fast ? '' : sign}`}>
        {pillar.arrow} {pillar.trend}
      </div>
    </div>
  )
}

export default function RadarHub({ solo = false }: { solo?: boolean }) {
  const { board, settings, openDeepDive } = useStore()
  if (!board) return null
  const focused = board.focused

  const byKey: Record<string, Pillar> = {}
  for (const p of board.pillars) byKey[p.key] = p

  const vals = board.pillars.map(p => p.value).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  // A shared scale across all four spokes, floored so a quiet set does not get exaggerated into
  // a dramatic shape by its own small numbers.
  const scale = Math.max(5, ...vals.map(Math.abs))

  const cls = focused?.classification
  const summary = focused?.plain_summary

  // At level 1 both rails are closed, so the live signals — the thing the rating cannot see, and
  // the reason any of this is interesting — have nowhere else to appear. They ride in the core.
  const signals = solo ? (focused?.signals ?? []).slice(0, 4) : []

  return (
    <div className={`hub ${solo ? 'is-solo' : ''}`}>
      <Satellite pillar={byKey.environment} area="nw" scale={scale} />
      <Satellite pillar={byKey.governance} area="ne" scale={scale} />

      <div className="hub-core">
        <div className="hub-core-head">
          {focused
            ? (
              <>
                <div className="hub-co">{focused.constituent.company}</div>
                {cls && (
                  <span className={`hub-verdict ${TONE_CLASS[cls.tone] || 'cc-class-neutral'}`}>
                    {cls.label}
                  </span>
                )}
              </>
            )
            : <div className="hub-co">{board.counts.showing} companies in view</div>}
        </div>

        <RadarPlot pillars={byKey} scale={scale} />

        <div className="hub-legend">
          <span><i className="k-ring" /> no change — what the stale rating assumes</span>
          <span><i className="k-fill" /> our live momentum</span>
        </div>

        {summary && (
          <p className="hub-line">
            {summary.body}
            {settings.demo && <span className="cc-tag-illus">illustrative demo</span>}
          </p>
        )}

        {signals.length > 0 && (
          <div className="hub-signals">
            <div className="hub-signals-h">
              {focused?.signals_kind === 'credentials' ? 'ESG credentials' : 'Live signals the rating cannot see'}
            </div>
            <div className="hub-signals-row">
              {signals.map((sg, i) => (
                <span className="hub-sig" key={i}>
                  <span className="hub-sig-k">{sg.label}</span>
                  <Tone tone={sg.tone}>{sg.value}</Tone>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <Satellite pillar={byKey.social} area="sw" scale={scale} />
      <Satellite pillar={byKey.digital_ai} area="se" scale={scale} />

      {focused && (
        <div className="hub-foot">
          <div className="hub-check">
            <div className="hub-check-h">Check before Monday</div>
            <div className="hub-check-b">
              {focused.check_action.has
                ? focused.check_action.check
                : 'No competing read computed yet — run a Compete on this company to surface one concrete action.'}
            </div>
          </div>
          <div className="hub-cta">
            <button className="btn btn-primary"
              onClick={() => openDeepDive(focused.constituent.ticker, 'compete')}>
              Compete · {focused.constituent.company}
            </button>
            <button className="btn"
              onClick={() => openDeepDive(focused.constituent.ticker, 'interrogate')}>
              Interrogate first
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
