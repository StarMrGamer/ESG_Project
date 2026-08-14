import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export const PILLAR_COLORS: Record<string, string> = {
  digital_ai: '#f5a524', environment: '#35d39a', governance: '#f4737d', social: '#5e9cf6',
}
export const PILLAR_LABEL: Record<string, string> = {
  environment: 'Environment', social: 'Social', governance: 'Governance', digital_ai: 'Digital / AI',
}
export const CMP_PALETTE = ['#35d39a', '#5e9cf6', '#f5a524', '#f4737d']

interface Theme {
  grid: string
  tick: string
  panel: string
  text: string
}

export function chartTheme(dark: boolean): Theme {
  return dark
    ? { grid: 'rgba(148,163,184,.10)', tick: '#8b97ab', panel: '#121a29', text: '#e7ebf3' }
    : { grid: 'rgba(15,23,42,.08)', tick: '#56627a', panel: '#ffffff', text: '#0f1729' }
}

const tooltipStyle = (t: Theme) => ({
  backgroundColor: t.panel, border: `1px solid ${t.grid}`, borderRadius: 10,
  color: t.text, fontSize: 12, fontFamily: "'IBM Plex Sans', sans-serif",
})

export function MomentumChart({ series, dark, height = 340 }: {
  series: Record<string, number[]>
  dark: boolean
  height?: number
}) {
  const t = chartTheme(dark)
  const keys = Object.keys(series)
  const n = Math.max(...keys.map(k => series[k].length), 0)
  const data = Array.from({ length: n }, (_, i) => {
    const row: Record<string, number | string> = { i }
    for (const k of keys) row[k] = series[k][i]
    return row
  })
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="i" hide />
        <YAxis tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          tickFormatter={v => `${v}%`} axisLine={false} tickLine={false} />
        <ReferenceLine y={0} stroke={t.tick} strokeOpacity={0.4} />
        <Tooltip contentStyle={tooltipStyle(t)}
          formatter={(v: unknown, name: unknown) => [`${Number(v).toFixed(1)}%`, PILLAR_LABEL[String(name)] || String(name)]}
          labelFormatter={() => ''} />
        <Legend formatter={(k: string) => PILLAR_LABEL[k] || k}
          wrapperStyle={{ fontSize: 11, color: t.tick }} />
        {keys.map(k => (
          <Line key={k} type="monotone" dataKey={k} stroke={PILLAR_COLORS[k] || '#9aa6b2'}
            strokeWidth={k === 'digital_ai' ? 3.2 : k === 'environment' ? 2.6 : 2.2}
            dot={false} isAnimationActive />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function PriceChart({ series, pct, dark, height = 200 }: {
  series: number[]
  pct: number
  dark: boolean
  height?: number
}) {
  const t = chartTheme(dark)
  const data = series.map((v, i) => ({ i, v }))
  const color = pct >= 0 ? '#35d39a' : '#f4737d'
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="i" hide />
        <YAxis tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          axisLine={false} tickLine={false} domain={['auto', 'auto']} />
        <Tooltip contentStyle={tooltipStyle(t)}
          formatter={(v: unknown) => [Number(v).toFixed(1), 'rebased']}
          labelFormatter={() => ''} />
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2.6} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function HistoryChart({ points, dark, height = 180 }: {
  points: { as_of: string; value: number }[]
  dark: boolean
  height?: number
}) {
  const t = chartTheme(dark)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 10, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="as_of" tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          axisLine={false} tickLine={false} domain={['auto', 'auto']} />
        <Tooltip contentStyle={tooltipStyle(t)} />
        <Line type="monotone" dataKey="value" stroke="#5e9cf6" strokeWidth={2.4}
          dot={{ r: 3, fill: '#5e9cf6' }} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function CompareMomentumBars({ rows, dark, height = 300 }: {
  rows: { company: string; ticker: string; momentum: { E: number | null; S: number | null; G: number | null } }[]
  dark: boolean
  height?: number
}) {
  const t = chartTheme(dark)
  const data = (['E', 'S', 'G'] as const).map(p => {
    const row: Record<string, number | string | null> = { pillar: p }
    for (const r of rows) row[r.company] = r.momentum[p]
    return row
  })
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="pillar" tick={{ fontSize: 12, fill: t.tick }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          tickFormatter={v => `${v}%`} axisLine={false} tickLine={false} />
        <ReferenceLine y={0} stroke={t.tick} strokeOpacity={0.4} />
        <Tooltip contentStyle={tooltipStyle(t)}
          formatter={(v: unknown) => [`${Number(v).toFixed(1)}%`]} cursor={{ fill: t.grid }} />
        <Legend wrapperStyle={{ fontSize: 11, color: t.tick }} />
        {rows.map((r, i) => (
          <Bar key={r.ticker} dataKey={r.company} fill={CMP_PALETTE[i % CMP_PALETTE.length]}
            radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function CompareScoreBars({ rows, dark, height = 300 }: {
  rows: { company: string; ticker: string; esg_score: number | null }[]
  dark: boolean
  height?: number
}) {
  const t = chartTheme(dark)
  const scored = rows.filter(r => r.esg_score != null)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={scored} margin={{ top: 18, right: 10, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="company" tick={{ fontSize: 11, fill: t.tick }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: t.tick, fontFamily: 'IBM Plex Mono' }}
          axisLine={false} tickLine={false} />
        <Tooltip contentStyle={tooltipStyle(t)} cursor={{ fill: t.grid }} />
        <Bar dataKey="esg_score" radius={[4, 4, 0, 0]} label={{ position: 'top', fill: t.tick, fontSize: 11 }}>
          {scored.map((r, i) => (
            <Cell key={r.ticker} fill={CMP_PALETTE[i % CMP_PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
