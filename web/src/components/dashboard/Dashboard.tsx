import { useStore } from '../../store'
import { Spinner } from '../ui'
import FiltersRail from './FiltersRail'
import CenterBoard from './CenterBoard'
import AssistantRail from './AssistantRail'
import AssistantBar from './AssistantBar'
import EngineBoard from './EngineBoard'
import UniverseGrid from './UniverseGrid'
import TrackRecord from '../future/TrackRecord'
import IndustryTable from '../benchmark/IndustryTable'

/**
 * The board, layered.
 *
 * Every block below declares the level it earns. Nothing above the current level renders, and
 * the step-up bar at the foot says what the next level would add — so depth is something the
 * user walks into, not something they arrive inside.
 *
 * The disagreement matrix is deliberately last to appear. It is the most information-dense thing
 * on the page and it used to be the first thing on it, which is most of why the board read as
 * overwhelming: a wall of dots before you knew what a dot meant.
 */

const NEXT: Record<number, string> = {
  1: 'Add the momentum chart, the pillar cards and the hidden-winner ranking.',
  2: 'Add the disagreement matrix, the risk tiers and the run provenance.',
}

function StepUp() {
  const { settings, setSettings } = useStore()
  const lv = settings.level
  if (lv >= 3) return null
  const next = (lv + 1) as 2 | 3
  return (
    <div className="step-up">
      <div>
        <div className="step-up-h">There is more underneath</div>
        <div className="cc-muted">{NEXT[lv]}</div>
      </div>
      <button className="btn btn-primary"
        onClick={() => setSettings({ level: next, leftOpen: true, rightOpen: true })}>
        Show level {next} →
      </button>
    </div>
  )
}

export default function Dashboard() {
  const { board, boardLoading, boardError, settings } = useStore()
  const lv = settings.level
  // Rails are level-2 furniture. At level 1 the centre column runs full width whatever the
  // toggles say, so "Brief" is genuinely brief rather than brief-plus-two-sidebars.
  const lo = lv > 1 && settings.leftOpen
  const ro = lv > 1 && settings.rightOpen
  const cls = lo && ro ? 'both' : lo ? 'left-only' : ro ? 'right-only' : 'neither'

  const bs = board?.universe.benchmark_stats ?? {}

  return (
    <div>
      {lv > 1 && !settings.demo && bs.basket_return && board && (
        <div className="bench-strip">
          <span>Foundation backtest</span>
          <span>basket <b>{bs.basket_return || '—'}</b> vs {board.universe.benchmark} <b>{bs.benchmark_return || '—'}</b></span>
          <span>Sharpe <b>{bs.basket_sharpe || '—'}</b> vs <b>{bs.benchmark_sharpe || '—'}</b></span>
          {bs.source && <span className="src">{bs.source}</span>}
        </div>
      )}
      {boardError && <div className="error-note">Couldn't load the board: {boardError}</div>}
      {!board && boardLoading && <Spinner label="Loading the command center…" />}
      {board && (
        <>
          {lv >= 3 && <EngineBoard />}
          {lv === 1 && <AssistantBar />}
          <div className={`dash-grid ${cls}`}>
            {lo && <div><FiltersRail /></div>}
            <div><CenterBoard /></div>
            {ro && <div><AssistantRail /></div>}
          </div>
          {lv >= 2 && <IndustryTable />}
          {/* "The AI can see now and last time, but not the future." This is the honest half of
              the answer and it earns level 2: it is evidence about the method, not another
              reading to interpret. */}
          {lv >= 2 && <div className="panel-block"><TrackRecord /></div>}
          {lv >= 2 && <UniverseGrid />}
          <StepUp />
        </>
      )}
    </div>
  )
}
