import { useStore } from '../../store'
import { fmtPct, fmtPillar, signClass, Tone, TONE_CLASS } from '../ui'
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

/**
 * Plot geometry. The box is wider than it is tall because the spoke LABELS live outside the
 * rings — without them the chart was four unlabelled points and a dashed circle, which told a
 * first-time reader nothing at all about which corner was which.
 */
const CX = 240
const CY = 150
/** Zero sits here; positive momentum pushes out toward RMAX, negative pulls in toward RMIN. */
const R0 = 66
const RMAX = 106
const RMIN = 26

/** Where each pillar's spoke points, in degrees, 0 = east. Matches the satellite card layout. */
const ANGLE: Record<string, number> = {
  environment: -90,   // top
  governance: 0,      // right
  digital_ai: 90,     // bottom
  social: 180,        // left
}
const ORDER = ['environment', 'governance', 'digital_ai', 'social']

/** Where each spoke's label sits, and how it is anchored. */
const LABEL_AT: Record<string, { x: number; y: number; anchor: 'start' | 'middle' | 'end' }> = {
  environment: { x: CX, y: CY - RMAX - 26, anchor: 'middle' },
  governance: { x: CX + RMAX + 14, y: CY - 4, anchor: 'start' },
  digital_ai: { x: CX, y: CY + RMAX + 22, anchor: 'middle' },
  social: { x: CX - RMAX - 14, y: CY - 4, anchor: 'end' },
}

function polar(angleDeg: number, radius: number) {
  const a = (angleDeg * Math.PI) / 180
  return { x: CX + radius * Math.cos(a), y: CY + radius * Math.sin(a) }
}

/** A ring-shaped band, drawn as two circles in one path so evenodd punches the hole. */
function annulus(rOuter: number, rInner: number) {
  const ring = (r: number) =>
    `M ${CX - r},${CY} a ${r},${r} 0 1,0 ${r * 2},0 a ${r},${r} 0 1,0 ${-r * 2},0 Z`
  return `${ring(rOuter)} ${ring(rInner)}`
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

  // Spoken aloud for a screen reader, and it is also the sentence the picture is trying to say.
  const spoken = ORDER
    .map(k => `${pillars[k]?.label ?? k} ${fmtPillar(pillars[k]?.value, pillars[k]?.basis)}`)
    .join(', ')

  return (
    <svg viewBox="0 0 480 320" className="radar-plot" role="img"
      aria-label={`Live momentum per ESG pillar against the zero line a static rating assumes: ${spoken}`}>
      {/* Bands first: outside the dashed ring is improvement, inside it is decline. Shading them
          says which way is "better" before anyone has read a single label. */}
      <path d={annulus(RMAX, R0)} fillRule="evenodd" className="radar-band is-up" />
      <path d={annulus(R0, RMIN)} fillRule="evenodd" className="radar-band is-down" />

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
          <title>{`${pt.p?.label ?? pt.key}: ${fmtPillar(pt.p?.value, pt.p?.basis)}`}</title>
        </circle>
      ))}

      {/* The labels. A radar with unlabelled spokes is a decoration, not a chart. */}
      {ORDER.map(key => {
        const at = LABEL_AT[key]
        const p = pillars[key]
        return (
          <g key={`l${key}`}>
            <text x={at.x} y={at.y} textAnchor={at.anchor} className="radar-axis-name">
              {(p?.label ?? key).toUpperCase()}
            </text>
            <text x={at.x} y={at.y + 15} textAnchor={at.anchor}
              className={`radar-axis-val ${signClass(p?.value)}`}>
              {fmtPillar(p?.value, p?.basis)}
            </text>
          </g>
        )
      })}
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
  // A pillar with no evidence is a FINDING and keeps its card — but it should not carry the same
  // visual weight as a measured one. Two of the four are commonly empty for a single company, so
  // at equal weight half the row is a large dash competing with the readings that mean something.
  const empty = v == null
  return (
    <div className={`hub-sat is-${area} ${pillar.fast ? 'is-fast' : ''}${empty ? ' is-empty' : ''}`}>
      <div className="hub-sat-label">{pillar.label}</div>
      <div className={`hub-sat-val ${pillar.fast ? '' : sign}`}>{fmtPillar(v, pillar.basis)}</div>
      <div className="hub-sat-bar"
        title={pillar.basis === 'evidence'
          ? (pillar.scope === 'company'
            ? `${fmtPillar(v, pillar.basis)} direction consensus from ${pillar.n ?? 0} dated signal${pillar.n === 1 ? '' : 's'} for this pillar`
            : `${fmtPillar(v, pillar.basis)} direction consensus from ${pillar.n ?? 0} of ${pillar.of ?? 0} companies with evidence for this pillar`)
          : `${fmtPct(v)} against a ±${scale.toFixed(1)}% scale`}>
        <span className="hub-sat-axis" />
        <span className={`hub-sat-fill ${sign}`}
          style={{ left: pct < 0 ? `${50 + pct}%` : '50%', width: `${Math.abs(pct)}%` }} />
      </div>
      <div className={`hub-sat-trend ${pillar.fast ? '' : sign}`}>
        {empty
          ? (pillar.scope === 'company'
            ? 'no dated evidence on this pillar yet'
            : 'no company in this filter has evidence here')
          : <>{pillar.arrow} {pillar.trend}</>}
      </div>
    </div>
  )
}

export default function RadarHub({ solo = false }: { solo?: boolean }) {
  const { board, settings, openDeepDive, openEvidence } = useStore()
  if (!board) return null
  const focused = board.focused

  const byKey: Record<string, Pillar> = {}
  // Whose readings these are. `board.pillars` is the mean across everything in view — correct
  // when nothing is focused, and wrong the moment a company's name sits in the middle of them.
  // The hub used to draw the set average under whichever company you clicked, so the four
  // numbers never changed. A focused company's own readings win; with none we fall back to the
  // average AND say so, rather than passing one off as the other.
  const rows = focused?.pillars?.some(p => p.value != null) ? focused.pillars : board.pillars
  const perCompany = rows === focused?.pillars
  for (const p of rows) byKey[p.key] = p

  const vals = rows.map(p => p.value).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  // Two scales, because the cards carry two different units (see Pillar.basis). A momentum
  // PERCENT is unbounded and gets a floor of 5 so a quiet set is not exaggerated into a dramatic
  // shape by its own small numbers. A direction CONSENSUS is already bounded to +/-1, so its
  // scale is fixed at 1 — flooring that at 5 would divide every real reading by five and
  // collapse the whole shape onto the zero ring, which is precisely the "nothing is happening"
  // picture this fix exists to stop showing.
  const evidenceBasis = rows.some(p => p.basis === 'evidence')
  const scale = evidenceBasis ? 1 : Math.max(5, ...vals.map(Math.abs))

  const cls = focused?.classification
  const summary = focused?.plain_summary

  // At level 1 both rails are closed, so the live signals — the thing the rating cannot see, and
  // the reason any of this is interesting — have nowhere else to appear. They ride in the core.
  const signals = solo ? (focused?.signals ?? []).slice(0, 4) : []

  // The signal count comes off the engine record the board already carries, so this costs no
  // extra request. No record (a name outside the scored universe) means no claim is made.
  const focusTicker = (focused?.constituent as { ticker?: string } | undefined)?.ticker || ''
  const rec = focusTicker ? board.engine?.records?.[focusTicker] : undefined
  const backing = solo && rec && rec.signal_count > 0
    ? { ticker: focusTicker, n: rec.signal_count }
    : null

  return (
    <div className={`hub ${solo ? 'is-solo' : ''}`}>
      <Satellite pillar={byKey.environment} area="nw" scale={scale} />
      <Satellite pillar={byKey.governance} area="ne" scale={scale} />

      <div className="hub-core" data-tour="hub">
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

        {/*
          Plot and prose sit side by side once the core is wide enough to hold both, and stack
          when it is not. On a wide monitor the board runs edge to edge, and a 330px plot centred
          in a 1600px card would have re-created the dead ground the full-bleed change removed —
          just on the inside of a panel instead of at the window's edge.
        */}
        <div className="hub-core-body">
          <RadarPlot pillars={byKey} scale={scale} />

          <div className="hub-core-side">
            {/*
              A shape and a dashed circle mean nothing on their own. This is the sentence that
              turns the picture into a claim, and it sits above the legend rather than below the
              plot because it is the first thing to read, not a footnote.
            */}
            <p className="hub-read">
              Each corner is one ESG pillar. The dashed ring is <b>no change</b> — where a rating
              that has not been refreshed still assumes this company sits. Outside the ring is
              improvement it has not priced in; inside is deterioration.
            </p>
            <p className="hub-scope">
              {perCompany
                ? <>These four readings are <b>{focused?.constituent.company}</b>&rsquo;s own dated evidence.</>
                : focused
                  ? <>No pillar evidence on file for <b>{focused.constituent.company}</b> — showing the <b>{board.counts.showing}-company average</b> for this filter instead.</>
                  : <>The <b>{board.counts.showing}-company average</b> for the current filter.</>}
            </p>

            <div className="hub-legend">
              <span><i className="k-ring" /> no change · 0%</span>
              <span><i className="k-fill" /> our live momentum</span>
              <span className="hub-scale">outer ring ±{scale.toFixed(1)}%</span>
            </div>

            {summary && (
              <p className="hub-line">
                {summary.body}
                {settings.demo && <span className="cc-tag-illus">illustrative demo</span>}
              </p>
            )}

            <details className="hub-how">
              <summary>How do I read this?</summary>
              <dl>
                <dt>The four corners</dt>
                <dd>
                  The pillars we track: Environment, Social, Governance and Digital&nbsp;/&nbsp;AI.
                  The last one is the point — conventional ESG ratings do not carry it at all.
                </dd>

                <dt>Distance from the centre</dt>
                <dd>
                  How fast that pillar is <em>moving</em>, not how good it is. A company can sit
                  far out on a pillar it is still weak at, because it is improving quickly. That
                  is deliberate: this is a momentum radar, not a scoreboard.
                </dd>

                <dt>Why the ring is the interesting part</dt>
                <dd>
                  A static ESG rating is a snapshot with a date on it, and until someone refreshes
                  it, it implicitly assumes nothing has moved since. The dashed ring is that
                  assumption drawn out. The filled shape is what our live signals say instead — so
                  the gap between the two is the disagreement, which is the whole reason this tool
                  exists.
                </dd>

                <dt>The scale is relative</dt>
                <dd>
                  The outer ring is the largest pillar move among the companies currently in view
                  (±{scale.toFixed(1)}% right now), so the shape shows which pillars lead rather
                  than an absolute score. Change the industry or country filter and it re-fits.
                </dd>

                {settings.demo && (
                  <>
                    <dt>These numbers</dt>
                    <dd>
                      Illustrative demo data from a fictional universe. Turn Demo off in the header
                      for the real ASEAN base DB, where pillar momentum awaits the alt-data feed.
                    </dd>
                  </>
                )}
              </dl>
            </details>

            {/* "Fancy UI, but no explanation of where the evidence is from." Fair, and it was
                literally true at this level: the evidence trail is level-3 furniture and a
                first-time visitor lands on level 1, so the backing was real but invisible. One
                line, always present, one click from the receipts. */}
            {backing && (
              <button className="hub-backing" data-tour="backing"
                onClick={() => openEvidence(backing.ticker)}
                title="Every signal with its excerpt, source, date and the reason it counted">
                <span className="hub-backing-n">{backing.n}</span>
                <span className="hub-backing-t">
                  dated {backing.n === 1 ? 'source behind' : 'sources behind'} this verdict
                </span>
                <span className="hub-backing-go">see the evidence ›</span>
              </button>
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
        </div>
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
              Answer now · {focused.constituent.company}
            </button>
            <button className="btn"
              onClick={() => openDeepDive(focused.constituent.ticker, 'interrogate')}>
              Shape the question first
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
