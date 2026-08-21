import type {
  AnchorSummary, BacktestPayload, BenchmarksPayload, Board, ChatResult, ClaimEvidencePayload,
  ComparePayload, Entry,
  Envelope, EvidencePayload, Health, HorizonKey, LsegPayload, NarrowedQuestion, Quote,
  SensitivityPayload, Stage2Answer, VerifyPayload,
} from './types'

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch { /* keep the status line */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => http<Health>('/api/health'),
  board: (p: { demo: boolean; country: string; sector: string; focus: string; simplified: boolean; horizon: HorizonKey }) => {
    const q = new URLSearchParams({
      demo: String(p.demo), country: p.country, sector: p.sector, horizon: p.horizon,
      focus: p.focus, simplified: String(p.simplified),
    })
    return http<Board>(`/api/board?${q}`)
  },
  chat: (p: { text: string; demo: boolean; simplified: boolean; focus_ticker: string }) =>
    http<ChatResult>('/api/chat', { method: 'POST', body: JSON.stringify(p) }),
  monitor: (p: { ticker?: string; text?: string; demo: boolean }) =>
    http<{ ok: boolean; ticker: string; entry: Entry; live_added?: boolean }>(
      '/api/monitor', { method: 'POST', body: JSON.stringify(p) }),
  unmonitor: (ticker: string) =>
    http<{ ok: boolean }>(`/api/monitor/${encodeURIComponent(ticker)}`, { method: 'DELETE' }),
  entry: (ticker: string, demo = false) =>
    http<Entry>(`/api/entry/${encodeURIComponent(ticker)}?demo=${demo}`),
  benchmarks: (demo: boolean, sector = '') => {
    const q = new URLSearchParams({ demo: String(demo) })
    if (sector) q.set('sector', sector)
    return http<BenchmarksPayload>(`/api/benchmarks?${q}`)
  },
  quote: (ticker: string, demo = false) =>
    http<Quote>(`/api/quote/${encodeURIComponent(ticker)}?demo=${demo}`),
  // One outbound call to LSEG per company, so it is asked for on the deep dive and never from
  // the board — a screen of 52 cards must not fan out into a rating provider.
  lseg: (ticker: string, demo = false) =>
    http<LsegPayload>(`/api/lseg/${encodeURIComponent(ticker)}?demo=${demo}`),
  sample: () => http<{ ok: boolean; ticker: string; entry: Entry }>('/api/sample', { method: 'POST' }),
  upload: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/upload', { method: 'POST', body: fd })
    if (!res.ok) {
      let detail = `${res.status}`
      try { detail = (await res.json()).detail || detail } catch { /* status only */ }
      throw new Error(detail)
    }
    return res.json() as Promise<{ ok: boolean; ticker: string; entry: Entry; meta: { mode: string } }>
  },
  stage1Ask: (p: { messages: { role: string; content: string }[]; turns: number; ticker: string; force?: boolean }) =>
    http<{ envelope: Envelope; raw: string }>('/api/stage1/ask', { method: 'POST', body: JSON.stringify(p) }),
  stage1Narrow: (p: { trail: unknown[]; final_env: unknown }) =>
    http<{ narrowed_q: NarrowedQuestion }>('/api/stage1/narrow', { method: 'POST', body: JSON.stringify(p) }),
  compare: (tickers: string[]) =>
    http<ComparePayload>('/api/compare', { method: 'POST', body: JSON.stringify({ tickers }) }),
  evidence: (ticker: string, demo: boolean, horizon: HorizonKey = 'long') =>
    http<EvidencePayload>(
      `/api/engine/company/${encodeURIComponent(ticker)}?demo=${demo}&horizon=${horizon}`),
  verify: (p: { ticker: string; demo: boolean; horizon?: HorizonKey; tamper?: boolean; tamper_leaf_id?: string }) =>
    http<VerifyPayload>('/api/verify', { method: 'POST', body: JSON.stringify(p) }),
  anchors: () => http<{ records: AnchorSummary[]; chain: Record<string, unknown> }>('/api/anchors'),
  // The horizon rides along for the same reason `evidence` carries it: a sensitivity report
  // computed against a different re-score would name signals behind a number nobody is looking at.
  sensitivity: (ticker: string, demo: boolean, horizon: HorizonKey = 'long') =>
    http<SensitivityPayload>(
      `/api/sensitivity/${encodeURIComponent(ticker)}?demo=${demo}&horizon=${horizon}`),
  backtest: () => http<BacktestPayload>('/api/backtest'),
  claimEvidence: (ticker?: string) =>
    http<ClaimEvidencePayload>(
      `/api/claim-evidence${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ''}`),
}

export interface Stage2Events {
  onRag?: (rag: { status: string; doc_count: number; query: string; error: string | null; snippets: number }) => void
  onPhase?: (label: string) => void
  onDelta?: (text: string) => void
  onAnswer?: (payload: { answer: Stage2Answer; narrowed_q: NarrowedQuestion }) => void
  onError?: (err: { kind: string; message: string }) => void
}

export async function streamStage2(
  p: { ticker: string; nq: NarrowedQuestion; use_rag: boolean; top_k: number },
  events: Stage2Events,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/stage2/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(p),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = `${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* status only */ }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      let kind = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) kind = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload: Record<string, unknown> | null = null
      try { payload = JSON.parse(data) } catch { continue }
      if (!payload) continue
      if (kind === 'rag') events.onRag?.(payload as never)
      else if (kind === 'phase') events.onPhase?.((payload as { label: string }).label)
      else if (kind === 'delta') events.onDelta?.((payload as { text: string }).text)
      else if (kind === 'answer') events.onAnswer?.(payload as never)
      else if (kind === 'error') events.onError?.(payload as { kind: string; message: string })
    }
  }
}
