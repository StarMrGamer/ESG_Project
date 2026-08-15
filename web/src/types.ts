export type Mandate = 'risk' | 'return' | 'compliance' | string
export type Horizon = 'near_term' | 'structural' | string
export type Tone = 'good' | 'bad' | 'neutral' | 'warn' | 'caution' | string

export interface TrailStep {
  axis: string | null
  type: string
  text: string
  rationale?: string
}

export interface NarrowedQuestion {
  narrowed_question: string
  mandate: Mandate
  sector: string
  horizon: Horizon
  trail: TrailStep[]
}

export interface MomentumCell {
  direction: string
  magnitude: string
}

export interface CompanyB {
  company: string
  ticker: string
  sector: string
  layer_a: { esg_score_static: string; as_of_date: string; note?: string }
  layer_a_history?: {
    note?: string
    series: { as_of: string; esg_score_static: string }[]
    trend_note?: string
  }
  layer_b: {
    momentum: { E: MomentumCell; S: MomentumCell; G: MomentumCell }
    digital_ai_signal: {
      ai_governance_hiring_velocity: string
      ai_disclosure_level: string
      gap_note?: string
    }
    conflicting_signals: {
      news_sentiment: string
      behaviour_trend: string
      conflict_note?: string
    }
    near_term_catalyst: string
  }
  _origin?: string
  _country?: string
  _exchange?: string
  _build_status?: string
  _build_error?: string
  _sources?: { title: string; url: string }[]
  _controversies?: { title: string; url?: string; snippet?: string }[]
  _market?: Record<string, unknown>
  _price_change_90d?: string | number
  _esg_breakdown?: EsgBreakdown
  _data_provenance?: string
  _score_higher_better?: boolean
  _constituent_ticker?: string
  analyst_coverage?: { analysts?: number; as_of?: string }
  [key: string]: unknown
}

export interface Stage2Answer {
  question_to_ask: string
  what_rating_sees: string
  what_we_see: string
  check_before_monday: string
  competes_summary: string
  reasoning: string[]
  sources: { title: string; url: string }[]
  _raw?: string
  _parse_failed?: boolean
  _rag_status?: string
  _rag_query?: string
  _ai_summary?: { summary?: string; source?: string; url?: string } | null
}

export interface Snapshot {
  company: string
  ticker: string
  country: string
  sector: string
  rating: string
  rating_num: string
  band: string
  band_tone: string
  score_higher_better: boolean
  as_of: string
  momentum: { E: string; S: string; G: string }
  arrows: { E: string; S: string; G: string }
  red_flags: number
  coverage: number
  coverage_total: number
  status: string
  origin: string
}

export interface EsgBreakdown {
  e_score: number
  s_score: number
  g_score: number
  overall: number
}

export interface FinancialSnapshot {
  have: boolean
  currency: string
  as_of: string | null
  price: string | null
  day_change: string | null
  price_change_90d: string | null
  range_52w: string | null
  rows: { label: string; value: string }[]
  simple: { label: string; value: string }[]
}

export interface Entry {
  ticker: string
  company: CompanyB
  snap: Snapshot
  answer: Stage2Answer | null
  narrowed_q: NarrowedQuestion | null
  default_nq: NarrowedQuestion
  built_at: number
  financial: FinancialSnapshot
  breakdown: EsgBreakdown | null
  origin_badge: string
  origin_disclaimer: string
}

export interface Constituent {
  id: string
  company: string
  ticker: string
  exchange: string
  country: string
  sector: string
  esg_cagr_2019_2023?: string
  esg_score?: number
  esg_as_of?: string
  momentum?: { environment?: number; social?: number; governance?: number; digital_ai?: number }
  live_signals?: Record<string, unknown>
  price_change_90d?: string
  esg_basis?: string
  source_url?: string
  confidence?: string
  esg_breakdown?: EsgBreakdown
  data_provenance?: string
  market?: Record<string, unknown>
  news?: { title: string; source?: string; date?: string }[]
  analyst_coverage?: { analysts?: number; as_of?: string }
}

export interface Pillar {
  key: string
  label: string
  value: number | null
  arrow: string
  trend: string
  fast: boolean
}

export interface WinnerRow {
  company: string
  ticker: string
  value: number
  is_new: boolean
}

export interface Credential {
  label: string
  value: string
  tone: Tone
}

export interface FocusedPayload {
  constituent: Constituent | CompanyB
  from_snapshot: boolean
  classification: { label: string; tone: Tone; line: string }
  credentials: Credential[]
  leadership: { score: number; band: string; has: boolean } | null
  signals: { label: string; value: string; tone: Tone }[]
  signals_kind: 'signals' | 'credentials'
  why_wrong: string
  plain_summary: { headline: string; body: string; verdict: string; tone: Tone; label: string }
  forecast: {
    available: boolean
    label: string
    tone: Tone
    headline: string
    mean: number | null
    lead: { key: string; label: string; value: number; arrow: string; word: string } | null
    pillars: { key: string; label: string; value: number; arrow: string; word: string }[]
  }
  news: {
    name: string
    illustrative: boolean
    status: string
    headlines: { title: string; source: string; date: string }[]
    youtube_url: string
    news_url: string
  }
  analyst: { covered: boolean; analysts: number | null; as_of: string; label: string; illustrative: boolean }
  check_action: { check: string; verdict: string; has: boolean }
  price: { pct: number | null; series: number[] }
  foundation: { basis: string; source_url?: string; confidence?: string } | null
}

export interface WatchlistEntry {
  ticker: string
  name: string
  built: boolean
  band: string
  band_emoji: string
  has_answer: boolean
  in_universe: boolean
}

export interface Board {
  universe: {
    note: string
    selection: string
    benchmark: string
    benchmark_stats: Record<string, string>
    as_of: string
    banner: string
    quarter: string
  }
  mode: 'numeric' | 'evidence' | 'empty'
  demo: boolean
  sectors: string[]
  countries: string[]
  filter: { country: string; sector: string }
  counts: { total: number; showing: number }
  industries: number
  avg: { kind: string; value: number | null; n: number; title: string; sub: string }
  pillars: Pillar[]
  momentum_series: Record<string, number[]>
  hidden_winners: { rows: WinnerRow[]; peer_avg: number | null; n: number }
  evidence: {
    coverage: { label: string; count: number; n: number; pct: number | null }[]
    leaders: WinnerRow[]
  }
  constituents: Constituent[]
  engine: EngineBlock
  focused: FocusedPayload | null
  watchlist: WatchlistEntry[]
  followups: { label: string; prompt: string }[]
  built_at: number
  fresh: string
}

// --------------------------------------------------------------------------- //
//  Engine (Prototype Build Spec v2): score records, CGSI quadrants, tiers, N/M/K
// --------------------------------------------------------------------------- //
export type TierKey = 'conservative' | 'balanced' | 'aggressive'
export type LabelKey =
  | 'hidden_winners' | 'future_leaders' | 'overrated_leaders' | 'value_traps' | 'consensus'

export interface EngineRecord {
  company_id: string
  label: LabelKey
  label_display: string
  composite_momentum: number
  composite_confidence: number
  direction_consensus: number
  evidence_weight: number
  shrinkage: number
  disagreement: number
  lseg_percentile: number
  momentum_percentile: number
  signal_count: number
  baseline_origin: string
  baseline_basis: string
  components: Record<string, number>
  tiers: Record<TierKey, boolean>
}

export interface Badge {
  display: string
  tone: Tone
  url: string
  note: string
}
export interface GreenBondBadge extends Badge { status: string; rank: number; provisional: boolean }
export interface ProfitabilityBadge extends Badge { state: string; traction: boolean }
export interface Badges { green_bond: GreenBondBadge; profitability: ProfitabilityBadge }

export interface AnchorSummary {
  status: string
  run_id: string
  root: string
  leaf_count: number
  tx_hash: string
  block_number?: number | null
  signer?: string
  contract?: string
  chain: string
  explorer_url: string
  note: string
}

export interface EngineBlock {
  run_id: string
  as_of: string
  engine_version: string
  config_version: string
  config_hash: string
  theta: number
  labels: Record<string, string>
  label_tooltips: Record<string, string>
  label_rules: Record<string, string>
  label_counts: Record<string, number>
  tiers: Record<TierKey, string>
  tier_rules: Record<TierKey, string>
  default_tier: TierKey
  nmk: {
    N: number; M: number; K: number
    labels: Record<'N' | 'M' | 'K', string>
    rules: Record<'N' | 'M' | 'K', string>
    members: Record<'N' | 'M' | 'K', string[]>
    universe_size: number
    theta: number
  }
  metadata: { path: string; rows: number; provisional: number; ok: boolean; note: string }
  anchor: AnchorSummary
  records: Record<string, EngineRecord>
  badges: Record<string, Badges>
}

export interface TrailRow {
  signal_id: string
  routes: { component: string; subcomponent: string }[]
  component: string
  subcomponent: string
  direction: number
  materiality: number
  confidence: number
  published_at: string
  date_basis: string
  source_url: string
  source_type: string
  raw_text: string
  rationale: string
  model_version: string
  prompt_version: string
}

export interface EvidencePayload {
  ticker: string
  company: string
  record: EngineRecord
  subcomponents: Record<string, Record<string, { momentum: number; weight: number; signal_count: number }>>
  coverage: number
  breadth: number
  corroboration: number
  mean_source_quality: number
  trail: TrailRow[]
  badges: Badges
  metadata_row: Record<string, string | boolean>
  metadata_note: string
  foundation: { basis: string; source_url: string; confidence: string }
  anchor: AnchorSummary
  run_id: string
  as_of: string
}

export interface VerifyRow {
  leaf_id: string
  kind: string
  preimage: string
  stored_hash: string
  recomputed_hash: string
  leaf_ok: boolean
  path_ok: boolean
  index: number
}

export interface VerifyPayload {
  ok: boolean
  status: 'MATCH' | 'NO MATCH' | string
  run_id: string
  company_id: string
  stored_root: string
  recomputed_root: string
  leaf_count: number
  rows: VerifyRow[]
  anchor_status: string
  tx_hash: string
  block_number: number | null
  block_timestamp: number | null
  signer: string
  contract: string
  chain: string
  explorer_url: string
  chain_checked: boolean
  chain_match: boolean | null
  note: string
  tampered: boolean
  chain_config: { rpc: string; contract: string; chain: string; explorer: string; ready: boolean; readable: boolean }
}

export interface Envelope {
  axis: string | null
  type: 'question' | 'challenge' | 'narrowed' | string
  text: string
  rationale: string
  suggested_replies: string[]
  done: boolean
  mandate: string | null
  sector: string | null
  horizon: string | null
  _parse_failed?: boolean
  _raw?: string
}

export interface ChatResult {
  reply: string
  action:
    | { kind: 'none' }
    | { kind: 'filter'; country: string | null; sector: string | null }
    | { kind: 'focus'; ticker: string; needs_build: boolean; company: string }
    | { kind: 'relay'; ticker: string; mode: 'compete' | 'interrogate'; needs_build: boolean; company: string; demo_numeric?: boolean }
    | { kind: 'relay_live'; text: string; mode: 'compete' | 'interrogate' }
}

export interface ComparePayload {
  data: {
    rows: { company: string; ticker: string; esg_score: number | null; momentum: { E: number | null; S: number | null; G: number | null } }[]
    pillars: string[]
    has_momentum: boolean
    has_score: boolean
  }
  cards: { ticker: string; snap: Snapshot; band_emoji: string; verdict: string }[]
  higher_better_all: boolean
}

export interface Health {
  ok: boolean
  llm_configured: boolean
  model: string
  entries: number
  watchlist: number
}
