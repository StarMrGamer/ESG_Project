import { useStore } from '../../store'
import { MomentumChart } from '../charts'
import { Section } from '../ui'
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
        <Section id="ctx-backtest" sub={bs.source || undefined}
          title={`Foundation backtest${bs.window ? ` · ${bs.window}` : ''}`}>
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
        </Section>
      )}

      {/* The subtitle used to read "90 days · % change" for both universes. Neither half was true
          of the real basket: its points are quarterly engine replays spanning nine months, and
          the values are a direction consensus, not a percentage. */}
      <Section id="ctx-momentum" title="ESG momentum"
        sub={board.momentum_series_kind === 'evidence'
          ? `${board.momentum_series_basis || 'engine replay'} · direction consensus −1 to +1, not a percentage`
          : '90 days · % change · the filtered set, not one company'}>
        {hasSeries
          ? <MomentumChart series={board.momentum_series} dark={settings.dark} height={360}
              basis={board.momentum_series_kind} labels={board.momentum_series_labels} />
          : <div className="empty-note">No momentum data for this filter yet.</div>}
      </Section>

      <IndustryTable />

      {/* "The AI can see now and last time, but not the future." This is the honest half of the
          answer: five cases, each point a real engine run scored only on what was published
          before that date. */}
      <Section id="ctx-track" title="Has the verdict moved before?">
        <TrackRecord />
      </Section>
    </div>
  )
}
