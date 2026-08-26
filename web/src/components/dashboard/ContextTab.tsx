import { useStore } from '../../store'
import { MomentumChart } from '../charts'
import { SectionTitle } from '../ui'
import IndustryTable from '../benchmark/IndustryTable'
import TrackRecord from '../future/TrackRecord'

/**
 * ContextTab — everything that is the same picture whichever company you clicked.
 *
 * These panels were on the board, between the reader and the widgets that actually respond to a
 * focus change. That is a real cost: a reader who clicks four companies and watches the bottom
 * two-thirds of the page sit still learns, wrongly, that the board is static.
 *
 * Nothing here is demoted. The foundation backtest is the reason the basket exists, the industry
 * bar is the answer to "compared to what?", and the five validation cases are the honest half of
 * "can it see the future". They are evidence about the METHOD, and grouping them says so more
 * clearly than scattering them under a company's name ever did.
 */
export default function ContextTab() {
  const { board, settings } = useStore()
  if (!board) return null
  const bs = board.universe.benchmark_stats || {}
  const hasSeries = Object.keys(board.momentum_series).length > 0

  return (
    <div className="context-tab">
      <p className="context-lede">
        These four answer questions about the <b>method</b>, not about one company — so they read
        the same whichever constituent is focused. They live here rather than on the board, where
        they sat still while everything around them moved.
      </p>

      {!settings.demo && bs.basket_return && (
        <div className="panel-block">
          <SectionTitle sub={bs.source || undefined}>
            Foundation backtest{bs.window ? ` · ${bs.window}` : ''}
          </SectionTitle>
          <div className="bench-strip is-inline">
            <span>basket <b>{bs.basket_return || '—'}</b> vs {board.universe.benchmark} <b>{bs.benchmark_return || '—'}</b></span>
            <span>Sharpe <b>{bs.basket_sharpe || '—'}</b> vs <b>{bs.benchmark_sharpe || '—'}</b></span>
            {bs.basket_max_drawdown && (
              <span>max drawdown <b>{bs.basket_max_drawdown}</b> vs <b>{bs.benchmark_max_drawdown}</b></span>
            )}
            {/* CGSI's own note reports the basket LAGGING the index in the most recent period.
                The cumulative figure is the one every deck reaches for, and showing it alone
                presents a strategy as uniformly winning when its author says otherwise. */}
            {bs.shortfall_ytd_2025 && (
              <span className="bench-against" title={bs.shortfall_note}>
                but <b>{bs.shortfall_ytd_2025}</b> vs the index YTD 2025 — ~45% bank weight
              </span>
            )}
          </div>
        </div>
      )}

      <div className="panel-block">
        <SectionTitle sub="90 days · % change · the filtered set, not one company">
          ESG momentum
        </SectionTitle>
        {hasSeries
          ? <MomentumChart series={board.momentum_series} dark={settings.dark} height={360} />
          : <div className="empty-note">No momentum data for this filter yet.</div>}
      </div>

      <IndustryTable />

      {/* "The AI can see now and last time, but not the future." This is the honest half of the
          answer: five cases, each point a real engine run scored only on what was published
          before that date. */}
      <div className="panel-block"><TrackRecord /></div>
    </div>
  )
}
