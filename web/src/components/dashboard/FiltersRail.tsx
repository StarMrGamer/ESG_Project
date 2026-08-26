import { useStore } from '../../store'
import { shortSector } from '../ui'

export default function FiltersRail() {
  const { board, settings, filters, setFilters, openDeepDive, monitorOnly, unpin, compareSel, toggleCompare, openCompare, focusTicker, setFocus } = useStore()
  if (!board) return null
  const { universe, mode } = board

  const note = settings.demo
    ? 'Fictional companies — toggle off in the header for the real ASEAN base DB.'
    : mode === 'evidence'
      ? 'Real ASEAN improvers (evidence) — pillar momentum awaits the alt-data feed.'
      : 'Live ASEAN improvers — competing with each stale rating.'

  const cmpValid = compareSel.filter(tk => board.watchlist.some(w => w.ticker === tk && w.built))

  return (
    <div className="rail">
      <div className="rail-section">
        <span className="cc-leftpill">{universe.banner}</span>
        <div className="cc-muted">{note}</div>

        <div className="cc-h" style={{ marginTop: 14 }}>Filters</div>
        <label className="field">
          <span>Industry</span>
          <select className="select" value={filters.sector}
            onChange={e => setFilters({ sector: e.target.value })}>
            {board.sectors.map(s => <option key={s} value={s}>{shortSector(s)}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Country</span>
          <select className="select" value={filters.country}
            onChange={e => setFilters({ country: e.target.value })}>
            {board.countries.map(c => <option key={c} value={c}>{c === 'All' ? 'All ASEAN' : c}</option>)}
          </select>
        </label>
        <div className="cc-muted">Universe: {board.counts.total} listed · showing {board.counts.showing}</div>

        <div className="cc-card avg-card">
          <div className="cc-pill-h">{board.avg.title}</div>
          <div className="cc-big cc-flat">{board.avg.value ?? '—'}</div>
          <div className="cc-muted">{board.avg.sub}</div>
        </div>
      </div>

      <div className="rail-section">
        <div className="cc-h">Monitored</div>
        {board.watchlist.length === 0 && (
          <div className="empty-note">
            Nothing pinned yet — ask the assistant to add a company, or browse the universe below.
          </div>
        )}
        {cmpValid.length >= 2 && (
          <button className="btn btn-primary btn-block" style={{ marginBottom: 8 }} onClick={openCompare}>
            Compare {cmpValid.length} →
          </button>
        )}
        {/* Two-stage click, the same as the matrix: the first press FOCUSES the company on the
            board so you can see what you are about to open, the second opens the deep dive.
            Going straight to a deep dive skipped the step where you find out what you picked —
            and from a list of names, that step is the whole reason to look. */}
        {board.watchlist.map(w => {
          const isFocus = focusTicker === w.ticker
          return (
          <div className={`mon-row ${isFocus ? 'is-focus' : ''}`} key={w.ticker}>
            <button className="btn"
              title={!w.built ? 'Build snapshot'
                : isFocus ? 'Open the deep dive' : 'Focus this company on the board — click again to open it'}
              onClick={() => {
                if (!w.built) { void monitorOnly(w.ticker); return }
                if (isFocus) void openDeepDive(w.ticker, 'compete')
                else setFocus(w.ticker)
              }}>
              {w.built ? '★' : '☆'} {w.name}{w.built && w.band_emoji !== '⚪' ? ` ${w.band_emoji}` : ''}
            </button>
            {w.built && (
              <button className={`btn cmp ${compareSel.includes(w.ticker) ? 'btn-primary' : ''}`}
                title={compareSel.includes(w.ticker) ? 'Remove from comparison' : 'Add to comparison'}
                onClick={() => toggleCompare(w.ticker)}>
                {compareSel.includes(w.ticker) ? '✓' : '⊕'}
              </button>
            )}
            <button className="btn cmp" title="Unpin" onClick={() => unpin(w.ticker)}>✕</button>
          </div>
          )
        })}
      </div>
    </div>
  )
}
