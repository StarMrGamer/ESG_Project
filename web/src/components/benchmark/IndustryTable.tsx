import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import { shortSector, Spinner } from '../ui'
import type { BenchmarksPayload } from '../../types'

/**
 * Every industry in the active universe, with both benchmarks side by side.
 *
 * This is the "average for each industry, so you can see which is good and bad" view. The two
 * columns are deliberately not merged into a ranking: ASEAN average orders our own names, OECD
 * intensity orders the industries themselves, and an industry can easily be top of one column
 * and bottom of the other. Reading them together is the point.
 *
 * Fetched on demand rather than ridden along on the board payload — it is a level-2 panel, and
 * the board should not pay for a table nobody has opened.
 */
export default function IndustryTable() {
  const { settings, filters, setFilters } = useStore()
  const [data, setData] = useState<BenchmarksPayload | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancel = false
    setError('')
    api.benchmarks(settings.demo)
      .then(d => { if (!cancel) setData(d) })
      .catch(e => { if (!cancel) setError(String(e.message || e)) })
    return () => { cancel = true }
  }, [settings.demo])

  if (error) return <div className="panel-block"><div className="error-note">{error}</div></div>
  if (!data) return <div className="panel-block"><Spinner label="Loading industry benchmarks…" /></div>

  const rows = data.table
  const withAvg = rows.filter(r => r.asean_avg != null)
  const best = withAvg.length ? Math.max(...withAvg.map(r => r.asean_avg as number)) : 0
  const worst = withAvg.length ? Math.min(...withAvg.map(r => r.asean_avg as number)) : 0

  return (
    <div className="panel-block ind-table-wrap">
      <div className="cc-h">Industry averages — ASEAN vs OECD</div>
      <div className="cc-muted">
        Left column: how our ASEAN names in that industry score, on average. Right column: how
        emissions-intense that industry is across the OECD. An industry can lead on one and lag on
        the other — a bank is structurally clean and only middling against its peers.
      </div>

      <div className="ind-scroll">
        <table className="ind-table">
          <thead>
            <tr>
              <th>Industry</th>
              <th className="num">Names</th>
              <th className="num">ASEAN avg</th>
              <th className="num">OECD intensity</th>
              <th className="num">Cleanest rank</th>
              <th>OECD industry matched</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const avg = r.asean_avg
              const tone = avg == null ? '' : avg === best ? 'is-best' : avg === worst ? 'is-worst' : ''
              return (
                <tr key={r.sector} className={filters.sector === r.sector ? 'is-current' : ''}>
                  <td>
                    <button className="ind-sector"
                      title="Filter the whole board to this industry"
                      onClick={() => setFilters({ sector: r.sector })}>
                      {shortSector(r.sector)}
                    </button>
                  </td>
                  <td className="num">{r.n}</td>
                  <td className={`num ${tone}`}>{avg == null ? '—' : avg.toFixed(1)}</td>
                  <td className="num">
                    {r.oecd_intensity == null ? '—'
                      : r.oecd_intensity.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  </td>
                  <td className="num">
                    {r.oecd_rank == null ? '—' : `${r.oecd_rank} / ${r.oecd_of}`}
                  </td>
                  <td className="ind-isic">
                    {r.oecd_isic ?? <span className="cc-muted">no crosswalk rule</span>}
                    {r.oecd_via === 'GICS sector' && r.oecd_isic && (
                      <span className="ind-via" title="Matched on the GICS sector, not a specific
 sub-industry rule — a coarser match.">sector-level</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="cc-muted">
        OECD intensity: tonnes CO2e per US$m of gross value added, {data.meta.year || ''}
        {data.industries[0]?.year ? ` ${data.industries[0].year}` : ''}. {data.meta.basis}
      </div>
      <div className="cc-muted">
        The industry crosswalk is a stated mapping from our GICS-style sectors onto ISIC groups,
        not a measurement — rows marked <b>sector-level</b> matched on the broad sector only.
      </div>
    </div>
  )
}
