import type { PPPShares } from '../../types'

/**
 * THE PPP TRIANGLE — Profit, People, Planet as three shares of one whole, with a dot showing
 * which corner a company's movement leans toward.
 *
 * A ternary plot is the right shape for exactly one kind of quantity: a composition, where the
 * parts sum to a whole and moving toward one corner necessarily means moving away from the other
 * two. That is a genuinely different question from the matrix below it — the matrix asks *which
 * way is this company going*, the triangle asks *what is its story ABOUT*.
 *
 * THREE THINGS THE PANEL HAS TO SAY OUT LOUD, and does:
 *
 * 1. **It is a magnitude, not a verdict.** The shares are built from |momentum| x evidence
 *    weight, so a dot in the Planet corner can mean rapid environmental progress OR an
 *    environmental collapse. The direction of each axis is therefore printed beside the shares
 *    rather than encoded in the position, because a corner label is a much stronger suggestion
 *    than a radius and a reader who assumed "Planet corner = good" would be reading a chart that
 *    never said so.
 *
 * 2. **The rule is printed.** Profit arrives from the price move divided by a full scale, and a
 *    normalising constant chosen in private is how a composition quietly becomes an opinion. It
 *    is the same 60% the dual matrix draws its x axis with, so the two cannot disagree.
 *
 * 3. **Most of this basket leans Profit because our ESG evidence is thin**, not because profit
 *    dominates those companies — the E/S/G pulls are small when there are few dated signals. The
 *    matrix already reports that gap (hollow dots, counted) and the header reports it again
 *    (harvest count), so this panel no longer repeats it in prose. `board.ppp` still carries
 *    `profit_led` and `placeable` if it is ever wanted back.
 *
 * An unplaceable company is NOT drawn at the centre. The centre means "equal thirds", which is a
 * measurement; a company missing an axis has no position at all and gets the reason instead.
 */

/** Plot geometry. Equilateral, with room under the base for the two bottom corner labels. */
const W = 300
const H = 262
const PAD = { top: 26, bottom: 34, side: 34 }

const TOP = { x: W / 2, y: PAD.top }
const LEFT = { x: PAD.side, y: H - PAD.bottom }
const RIGHT = { x: W - PAD.side, y: H - PAD.bottom }

/**
 * Barycentric -> cartesian. PROFIT at the apex, People bottom-left, Planet bottom-right.
 *
 * The apex is the corner a reader looks at first, so which axis sits there is a statement about
 * what the panel is for. Profit holds it.
 */
function place(planet: number, people: number, profit: number) {
  return {
    x: profit * TOP.x + people * LEFT.x + planet * RIGHT.x,
    y: profit * TOP.y + people * LEFT.y + planet * RIGHT.y,
  }
}

/** The three gridlines at 25/50/75% of each axis, so a position can actually be read off. */
const GRID = [0.25, 0.5, 0.75]

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)

const ARROW: Record<string, string> = { '1': '↑', '-1': '↓', '0': '→' }
const DIR_WORD: Record<string, string> = { '1': 'improving', '-1': 'deteriorating', '0': 'flat' }

function Leg({ k, label, share, dir }:
  { k: string; label: string; share: number | null; dir: number | null | undefined }) {
  const d = dir == null ? '' : String(dir)
  return (
    <div className={`tri-leg tri-leg-${k}`}>
      <span className="tri-leg-k">{label}</span>
      <span className="tri-leg-v">{pct(share)}</span>
      <span className={`tri-leg-d ${d === '1' ? 'is-up' : d === '-1' ? 'is-down' : 'is-flat'}`}>
        {d ? `${ARROW[d]} ${DIR_WORD[d]}` : 'no direction'}
      </span>
    </div>
  )
}

export default function PPPTriangle({ shares, company }:
  { shares: PPPShares | null | undefined; company: string }) {
  if (!shares) return null

  const dot = shares.known
    ? place(shares.planet as number, shares.people as number, shares.profit as number)
    : null

  return (
    <div className="tri" data-tour="ppp-triangle">
      <div className="tri-head">
        <span className="tri-title">Profit · People · Planet</span>
        <span className="cc-muted">where this company&rsquo;s movement sits</span>
      </div>

      <div className="tri-body">
        <svg viewBox={`0 0 ${W} ${H}`} className="tri-svg" role="img"
          aria-label={`Ternary plot of Profit, People and Planet shares for ${company}`}>
          {/* gridlines first, so the frame and the dot sit on top */}
          {/* One family of lines per axis: constant Planet, constant People, constant Profit.
              They are built through `place`, so moving an axis to the apex moves its gridlines
              with it and the two can never end up describing different corners. */}
          {GRID.map(t => (
            <g key={t} className="tri-grid">
              <line {...seg(place(t, 1 - t, 0), place(t, 0, 1 - t))} />
              <line {...seg(place(1 - t, t, 0), place(0, t, 1 - t))} />
              <line {...seg(place(1 - t, 0, t), place(0, 1 - t, t))} />
            </g>
          ))}

          <polygon className="tri-frame"
            points={`${TOP.x},${TOP.y} ${RIGHT.x},${RIGHT.y} ${LEFT.x},${LEFT.y}`} />

          <text x={TOP.x} y={TOP.y - 10} textAnchor="middle" className="tri-corner c-profit">
            PROFIT
          </text>
          <text x={LEFT.x - 4} y={LEFT.y + 18} textAnchor="start" className="tri-corner c-people">
            PEOPLE
          </text>
          <text x={RIGHT.x + 4} y={RIGHT.y + 18} textAnchor="end" className="tri-corner c-planet">
            PLANET
          </text>

          {dot && (
            <>
              {/* Guides from the dot to each edge, so the three shares can be read off the plot
                  rather than only from the numbers beside it. */}
              <circle cx={dot.x} cy={dot.y} r={11} className="tri-dot-halo" />
              <circle cx={dot.x} cy={dot.y} r={6} className={`tri-dot lean-${shares.lean}`}>
                <title>{`${company}
Profit ${pct(shares.profit)} · People ${pct(shares.people)} · Planet ${pct(shares.planet)}
Leans ${shares.lean}. A magnitude, not a verdict — the directions are printed beside it.`}</title>
              </circle>
            </>
          )}
        </svg>

        <div className="tri-side">
          {shares.known ? (
            <>
              <div className="tri-legs">
                <Leg k="profit" label="Profit" share={shares.profit} dir={shares.directions.profit} />
                <Leg k="people" label="People" share={shares.people} dir={shares.directions.people} />
                <Leg k="planet" label="Planet" share={shares.planet} dir={shares.directions.planet} />
              </div>
              <p className="tri-note cc-muted">
                <b>Where the movement is, not whether it is good news.</b> The shares are built
                from magnitudes, so a Planet-heavy dot can mean rapid progress or rapid
                deterioration — the direction of each axis is the line above, not the position.
              </p>
            </>
          ) : (
            <p className="tri-note cc-muted">
              <b>Not placeable.</b> {shares.why}
            </p>
          )}

          <details className="tri-how">
            <summary>How the three shares are built</summary>
            <p>{shares.basis}</p>
          </details>
        </div>
      </div>
    </div>
  )
}

function seg(a: { x: number; y: number }, b: { x: number; y: number }) {
  return { x1: a.x, y1: a.y, x2: b.x, y2: b.y }
}
