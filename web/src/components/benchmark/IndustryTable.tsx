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

  // Every row currently resolves on the DIRECT join, so the table is single-unit in practice —
  // but the crosswalk fallback is in another unit entirely, so the unit is only promoted to the
  // header when every row that has a number agrees on it. Mixed units get labelled per row.
  const units = Array.from(new Set(rows.filter(r => r.bench_intensity != null).map(r => r.bench_unit)))
  const oneUnit = units.length === 1 ? units[0] : ''
  const anyCrosswalk = rows.some(r => r.bench_basis === 'crosswalk')
  const unmatched = rows.filter(r => r.bench_intensity == null).length

  return (
    <div className="panel-block ind-table-wrap">
      <div className="cc-h">Industry averages — ASEAN vs the industry bar</div>
      <div className="cc-muted">
        Left column: how our ASEAN names in that industry score, on average. Right column: how
        emissions-intense that industry is structurally. An industry can lead on one and lag on
        the other — a bank is structurally clean and only middling against its peers. The two are
        never subtracted from each other: they are different measures.
      </div>

      <div className="ind-scroll">
        <table className="ind-table">
          <thead>
            <tr>
              <th>Industry</th>
              <th className="num">Names</th>
              <th className="num">ASEAN avg</th>
              <th className="num">Industry intensity{oneUnit ? <><br /><span className="ind-unit">{oneUnit}</span></> : null}</th>
              <th className="num">Cleanest rank</th>
              <th>Benchmark sector</th>
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
                  <td className="num" title={r.bench_source || ''}>
                    {r.bench_intensity == null ? '—'
                      : r.bench_intensity.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                    {!oneUnit && r.bench_intensity != null && (
                      <span className="ind-unit"> {r.bench_unit}</span>
                    )}
                  </td>
                  <td className="num">
                    {r.bench_rank == null ? '—' : `${r.bench_rank} / ${r.bench_of}`}
                  </td>
                  <td className="ind-isic">
                    {r.bench_label ?? <span className="cc-muted">no benchmark row</span>}
                    {r.bench_fallback && r.bench_label && (
                      <span className="ind-via" title={r.bench_note || 'A coarser match than a direct join.'}>
                        {r.bench_basis === 'crosswalk' ? 'crosswalk' : 'fallback geo'}
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="cc-muted">
        {oneUnit
          ? `Industry intensity: ${oneUnit}, joined directly on the basket's own industry label.`
          : 'Industry intensity: unit shown per row — the rows come from two sources on different denominators.'}
        {' '}Despite the filename this is <b>Eurostat (EU-27)</b>, not the OECD: dataset
        env_ac_aeint_r2, GHG per euro of gross value added. Financials carry an operational-only
        caveat — financed emissions are the material metric for a bank, and are not in this figure.
      </div>
      {(anyCrosswalk || unmatched > 0) && (
        <div className="cc-muted">
          {anyCrosswalk && <>Rows marked <b>crosswalk</b> came through the stated ISIC mapping rather than a direct join. </>}
          {unmatched > 0 && <>{unmatched} {unmatched === 1 ? 'industry has' : 'industries have'} no benchmark row at all, and say so rather than borrowing a neighbouring number.</>}
        </div>
      )}
    </div>
  )
}
