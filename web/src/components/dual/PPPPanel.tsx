import { useStore } from '../../store'
import PPPTriangle from './PPPTriangle'

/**
 * The PPP triangle, given the width it was built for.
 *
 * It used to render inside `RadarHub`'s `hub-panels` grid. That grid gives `.dual` a full-width
 * row and splits what is left between the triangle and the forecast — so whenever the forecast
 * was absent, the triangle sat alone in one narrow cell with an empty cell beside it. Worse,
 * `.tri-body` is a flex row of a 300px plot and a ~240px minimum side column: under about 560px
 * it wraps, the plot shrinks, and a ternary chart squeezed to a third of its width stops
 * reading as a composition — which is the only thing a ternary chart is for.
 *
 * So it is a board module of its own, full width, below the company row. `.tri-body` then lays
 * out exactly as designed: plot on the left, the three shares and the direction note on the
 * right, on one line.
 *
 * IT STAYS A PER-COMPANY PANEL, which is why it sits with the company content rather than down
 * with `residual` and `roadmap` — those are statements about the whole cohort, this is a
 * statement about the name currently focused. A reader who has just looked at one company's
 * radar should not have to scroll past two cohort panels to find that company's composition.
 *
 * `PPPTriangle` itself is untouched and still takes props: this wrapper only reads the store,
 * so the drawing component stays pure and testable.
 */
export default function PPPPanel() {
  const { board } = useStore()
  const focused = board?.focused
  if (!focused?.ppp) return null
  return <PPPTriangle shares={focused.ppp} company={focused.constituent.company} />
}
