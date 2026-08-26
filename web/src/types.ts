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

/**
 * The ASEAN peer average for an industry — same unit as the company's own score, so the
 * comparison is direct. `available: false` carries the reason instead of a zero.
 */
export interface AseanBenchmark {
  available: boolean
  reason?: string
  sector?: string
  average?: number
  n?: number
  metric?: string
  /** 'static' (comparable to a company's own score) or 'evidence' (a different measurement). */
  metric_kind?: string
  unit?: string
  universe?: string
}

/**
 * The OECD industry footprint: greenhouse-gas intensity in tonnes CO2e per US$m of gross value
 * added, and where that industry ranks among the OECD's. A different unit and a different
 * question from the ASEAN average, which is why the two are never combined into one number.
 */
export interface OecdBenchmark {
  available: boolean
  reason?: string
  sector?: string
  isic_code?: string
  isic_label?: string
  isic_sections?: string
  /** How the crosswalk matched — 'sub-industry' is a specific rule, 'GICS sector' is the fallback. */
  via?: string
  matched_on?: string
  intensity?: number
  unit?: string
  rank?: number
  of?: number
  percentile?: number
  cleanest?: string
  dirtiest?: string
  median?: number
  year?: string
  basis?: string
  retrieved?: string
  sources?: string[]
}

export interface Benchmark {
  company?: string
  sector: string
  own_score: number | null
  /** Where the own score came from, when there is one. */
  own_score_source: string
  /** Why there is no gap — a missing score, or two measures that must not be differenced. */
  own_score_note: string
  asean: AseanBenchmark
  oecd: OecdBenchmark
  gap_vs_asean: number | null
  verdict: string
  disclaimer: string
}

/** A last traded price, for context only. Never an input to any score. */
export interface Quote {
  ticker: string
  available: boolean
  reason?: string
  symbol?: string
  price?: number
  currency?: string
  change_pct?: number | null
  exchange?: string
  as_of?: number
  fifty_two_high?: number
  fifty_two_low?: number
  source?: string
  note?: string
}

export interface IndustryRow {
  sector: string
  n: number
  asean_avg: number | null
  asean_metric?: string
  oecd_isic: string | null
  oecd_intensity: number | null
  oecd_rank: number | null
  oecd_of: number | null
  oecd_percentile: number | null
  oecd_via: string | null
  matched: boolean
}

/**
 * LSEG's own published ESG score — the REAL incumbent view, on LSEG's 0–5 scale where HIGHER
 * IS BETTER. Deliberately a separate shape from anything of ours: it is never averaged into
 * our momentum, and its scale runs the opposite way to the Sustainalytics-style risk score in
 * the sample company, so the two can only ever sit side by side.
 */
export interface LsegTheme {
  key: string
  label: string
  score: number | null
  band: string
}

export interface LsegPillar extends LsegTheme {
  short: string
  tooltip: string
  themes: LsegTheme[]
}

export interface LsegScores {
  company: string
  ric: string
  esg_score: number | null
  band: string
  scale_max: number
  scale_note: string
  fiscal_year: string
  basis: string
  industry: string
  rank: number | null
  rank_total: number | null
  rank_top_pct: number | null
  pillars: LsegPillar[]
  _origin: string
  source_url: string
  attribution: string
  note: string
  matched_from?: string
}

export interface LsegPayload {
  ticker: string
  company: string
  available: boolean
  reason?: string
  scores?: LsegScores
  source_url: string
  attribution: string
}

export interface BenchmarksPayload {
  available: boolean
  meta: Record<string, string>
  industries: {
    isic_code: string; isic_label: string; isic_sections: string; year: string
    intensity_t_per_musd: number; rank_cleanest: number; cleanliness_percentile: number
  }[]
  table: IndustryRow[]
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
  benchmark: Benchmark
  quote: Quote
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
  /** Whose reading this is. 'set' = the mean across every company in view (the board cards).
   *  'company' = one focused company's own evidence. Printing a set average under a company's
   *  name is how the hub came to show the same four numbers for every company you clicked. */
  scope?: 'set' | 'company'
  arrow: string
  trend: string
  fast: boolean
  /** Which SCALE `value` is on. 'numeric' = a momentum percent from a constituent's own fields
   *  (the fictional demo set). 'evidence' = the engine's -1..+1 direction consensus, derived
   *  from dated signals for universes that carry no numeric block (the real ASEAN basket).
   *  The two are not interchangeable: rendering a consensus of 0.59 as "+0.59%" is a real
   *  number under a wrong unit. Absent on older payloads -> treat as 'numeric'. */
  basis?: 'numeric' | 'evidence'
  /** How many companies in view actually carried a reading for this pillar, out of how many are
   *  in view at all. A mean over 3 names and a mean over 44 are different claims. */
  n?: number
  of?: number
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
  /** This company's OWN four pillar readings. null when neither its numeric block nor an engine
   *  record can answer — the hub then falls back to the set average and labels it as such. */
  pillars?: Pillar[] | null
  credentials: Credential[]
  leadership: { score: number; band: string; has: boolean } | null
  signals: { label: string; value: string; tone: Tone }[]
  signals_kind: 'signals' | 'credentials' | 'scored signals'
  /** Why a company WITH evidence can read zero momentum on this horizon: its signals have all
   *  decayed past the half-life. '' when it does not apply. */
  decay_note?: string
  /** The pro/con case behind the verdict — both axes, never merged. null outside the scored
   *  universe, because a case with no cohort behind it is a verdict about nobody. */
  case?: CompanyCase | null
  why_wrong: string
  plain_summary: { headline: string; body: string; verdict: string; tone: Tone; label: string }
  news: {
    name: string
    illustrative: boolean
    /** 'demo' seeded and labelled · 'gathered' real, from news.py · 'awaiting' nothing yet. */
    status: string
    /** Date the sweep ran, and how many items carry a date the article itself states. */
    gathered_at?: string
    dated?: number
    headlines: { title: string; source: string; date: string; url?: string }[]
    youtube_url: string
    news_url: string
  }
  analyst: { covered: boolean; analysts: number | null; as_of: string; label: string; illustrative: boolean }
  check_action: { check: string; verdict: string; has: boolean }
  /** `source` is set ONLY for a real fetched series (Yahoo); the demo's synthetic curve leaves
   *  it null, which is how the strip knows whether it may drop the "illustrative" label. */
  price: { pct: number | null; series: number[]; source?: string | null
           points?: number | null
           /** Date the series was captured. The basket runs off a dated snapshot so the
            *  demo needs no network; the card prints this rather than implying a live tick. */
           captured?: string | null
           /** The last traded price. Separate from the series because the PSE source gives a
            *  real price and no history — 'no 90-day line' must not read as 'no price'. */
           last?: { price: number; currency: string; change_pct: number | null
                    exchange: string; source: string; captured?: string | null } | null }
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
  /** `basis` says what the bar measures. 'digital_ai' = the demo set's own signal.
   *  'disagreement' = the engine's signed evidence-minus-rating gap, used for the real basket,
   *  where the Digital/AI field does not exist. The footer must name the right one. */
  hidden_winners: { rows: WinnerRow[]; peer_avg: number | null; n: number
                    basis?: 'digital_ai' | 'disagreement' }
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
/**
 * Decay horizon. NOT a filter like TierKey: the tiers are flags already stamped on a finished
 * record, so switching one re-segments what is on screen. Switching the horizon changes the
 * decay half-life, which re-scores everything — so it is a server round-trip, and each horizon
 * carries its own run_id.
 */
export type HorizonKey = 'short' | 'long'
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
  /** Notch grade from the basket (BBB / BB / B). Unattributed by design — CGSI's column names
   *  no agency — and displayed only; it never enters the maths. '' where none is carried. */
  incumbent_notch: string
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

/** CGSI's own note that a basket member has gone private. Surfaced, not hidden — a static
 *  list going stale is the product's argument (Prototype_Build_Notes.md §3). */
export interface DelistedBadge extends Badge { value: string; note: string; tone: string }

/** The INDUSTRY's transition bar, joined on CGSI's industry label. Never differenced against
 *  the company: we hold no per-company emissions intensity for this basket. */
export interface SectorBenchmarkBadge extends Badge {
  value: string; industry: string; nace: string
  rank: number; of: number; above_median: boolean
  attribution: string; caveat: string; note: string
}
export interface ProfitabilityBadge extends Badge { state: string; traction: boolean }
export interface PipelineBadge {
  /** 'N' issuer · 'M' bond-ready · 'K' review list · '' in none of the three. */
  bucket: 'N' | 'M' | 'K' | ''
  display: string
  tone: string
  /** The bucket's own rule, verbatim from engine_config — the badge can always be defended. */
  note: string
}

export interface Badges {
  green_bond: GreenBondBadge
  profitability: ProfitabilityBadge
  /** Which origination bucket this company is in. The counts strip shows the totals; this puts
   *  the label on the company, which is where someone asking "is THIS one a lead?" looks. */
  pipeline?: PipelineBadge
  /** Present only when CGSI's own notes record a delisting. */
  delisted?: DelistedBadge
  /** Present when the company's industry has a benchmark row. */
  sector_benchmark?: SectorBenchmarkBadge
}

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
  horizon: HorizonKey
  horizons: Record<HorizonKey, number>
  default_horizon: HorizonKey
  half_life_days: number
  nmk: {
    N: number; M: number; K: number
    labels: Record<'N' | 'M' | 'K', string>
    rules: Record<'N' | 'M' | 'K', string>
    members: Record<'N' | 'M' | 'K', string[]>
    universe_size: number
    theta: number
  }
  metadata: {
    path: string; rows: number; provisional: number; ok: boolean; note: string
    /** Honesty layer — see Prototype_Build_Notes.md §4/§5. `header` is the exact wording the
     *  green-bond table must carry; `review_chip` is the maker-checker state. */
    verified?: boolean; verified_by?: string; review_state?: string
    review_chip?: string; header?: string
  }
  /** Live-gathered evidence merged into this run (real universe only). */
  harvest?: { companies: number; events: number; note: string }
  anchor: AnchorSummary
  records: Record<string, EngineRecord>
  badges: Record<string, Badges>
}

export interface TrailRow {
  /** "harvested" = gathered live by us; "supplied" = came in the verified basket. */
  origin?: string
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

/* ------------------------------------------------------------------------- *
 *  "But what about the future?" — the two payloads that answer it.
 *
 *  Neither is a forecast. `SensitivityPayload` looks forward by measuring what the CURRENT
 *  verdict is standing on; `BacktestPayload` looks back at what the verdict actually did as
 *  evidence arrived. Between them they answer the question a static rating never faces: the
 *  data will change — then what?
 * ------------------------------------------------------------------------- */

/** One signal, re-scored with itself removed. `flips` is the whole point of the row. */
export interface FlipRow {
  signal_id: string
  published_at: string
  source_type: string
  source_url: string
  rationale: string
  excerpt: string
  component: string
  direction: number
  momentum_without: number
  momentum_delta: number
  label_without: string
  label_without_display: string
  flips: boolean
}

/** Distance from one label boundary. A measurement of the record, never a prediction. */
export interface MarginRow {
  key: string
  label: string
  value: number
  boundary: number
  boundary_name: string
  distance: number
  side: 'above' | 'below'
  note: string
}

export interface SensitivityPayload {
  company_id: string
  company: string
  run_id: string
  as_of: string
  horizon: HorizonKey
  label: LabelKey
  label_display: string
  signal_count: number
  signals: FlipRow[]
  load_bearing_count: number
  /** How many signals would have to go before the label moved. null = not even all of them. */
  smallest_flip_set: number | null
  margins: MarginRow[]
  verdict_note: string
  disclaimer: string
}

/** One monthly re-run: what the Radar would have said on `date`, from evidence dated before it. */
export interface BacktestPoint {
  date: string
  momentum: number
  confidence: number
  signal_count: number
  label: string
}

export interface BacktestCase {
  case_id: string
  company: string
  ticker: string
  profile: string
  cutoff_date: string
  outcome_date: string
  outcome: string
  outcome_source: string
  is_known_failure: boolean
  baseline: { value: number; basis: string; note: string }
  events: { date: string; text: string; source_type: string }[]
  points: BacktestPoint[]
  final: { momentum: number; confidence: number; signal_count: number; label: string }
}

export interface BacktestPayload {
  available: boolean
  note?: string
  reason?: string
  lookback_months?: number
  generated_from?: string
  cases: BacktestCase[]
  disclaimer?: string
}


/** Claim vs Evidence (Prototype_Build_Notes.md §6) — ILLUSTRATIVE, and `checked` says which
 *  side of a row has actually been determined. See ClaimVsEvidence.tsx for why that is per-row
 *  rather than one banner. */
export interface ClaimSide {
  text: string
  source: string
  date: string
  source_url: string
  checked: boolean
  basis: string
}

export interface ClaimEvidenceRow {
  company_id: string
  company: string
  why_this_one: string
  claim: ClaimSide
  evidence: ClaimSide
  verdict: string
  verdict_checked: boolean
  verdict_note: string
}

export interface ClaimEvidencePayload {
  available: boolean
  header: string
  deck_line: string
  verdicts: Record<string, string>
  rows: ClaimEvidenceRow[]
  illustrative: boolean
  reason?: string
}


/** The rule-derived case for one company: why this verdict, what argues against it, and what
 *  would change it. Built by `rationale.py` — no LLM, so it replays with the run it describes.
 *  ESG and financial are reported SIDE BY SIDE and never combined into a single judgement: the
 *  financial read gates whether an ESG disagreement is worth acting on, it never moves the ESG
 *  verdict. Nothing here is a recommendation. */
export interface CompanyCase {
  company_id: string
  company: string
  label: string
  label_display: string
  summary: string
  esg: { pros: string[]; cons: string[] }
  financial: {
    pros: string[]
    cons: string[]
    /** strong | adequate | weak | unknown — `unknown` is deliberately NOT a failure. */
    verdict: string
    earnings: { latest_text: string; prior_text: string; growth_pct: number | null; direction: string; note: string }
    label: string
  }
  watch_outs: string[]
  counts: { esg_pros: number; esg_cons: number; fin_pros: number; fin_cons: number }
}
