import { useStore } from '../../store'
import { Spinner } from '../ui'
import FiltersRail from './FiltersRail'
import CenterBoard from './CenterBoard'
import AssistantRail from './AssistantRail'
import EngineBoard from './EngineBoard'
import UniverseGrid from './UniverseGrid'

export default function Dashboard() {
  const { board, boardLoading, boardError, settings } = useStore()
  const lo = settings.leftOpen
  const ro = settings.rightOpen
  const cls = lo && ro ? 'both' : lo ? 'left-only' : ro ? 'right-only' : 'neither'

  const bs = board?.universe.benchmark_stats ?? {}

  return (
    <div>
      {!settings.demo && bs.basket_return && board && (
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
          <EngineBoard />
          <div className={`dash-grid ${cls}`}>
            {lo && <div><FiltersRail /></div>}
            <div><CenterBoard /></div>
            {ro && <div><AssistantRail /></div>}
          </div>
          <UniverseGrid />
        </>
      )}
    </div>
  )
}
