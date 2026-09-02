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
  /**
   * Which source answered. 'direct' is the Eurostat join on the basket's own industry label
   * (22 of 22 industries, g CO2e/EUR); 'crosswalk' is the older ISIC mapping (4 of 22,
   * t CO2e/US$m). DELIBERATELY not named `basis` — that field already carries the provenance
   * sentence this panel prints, and overloading it would have replaced it with the word
   * "direct" without anything failing.
   */
  bar_basis?: 'direct' | 'crosswalk' | ''
  /** Heading for the block: the two sources are different bodies on different units. */
  heading?: string
  /** Log-scale bounds for the position pin, from whichever book the number came out of. */
  scale_min?: number | null
  scale_max?: number | null
  attribution?: string
  caveat?: string
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
  /**
   * The industry bar, from whichever source actually resolved. `bench_basis` says which:
   * 'direct' is the Eurostat join on CGSI's own industry label (22 of 22 resolve, g CO2e/EUR),
   * 'crosswalk' is the older ISIC mapping (4 of 22, t CO2e/US$m). The two are in DIFFERENT UNITS,
   * so `bench_unit` travels with the number and is rendered per row rather than in the header.
   */
  bench_basis: 'direct' | 'crosswalk' | ''
  bench_intensity: number | null
  bench_unit: string
  bench_label: string | null
  bench_code?: string | null
  bench_geo?: string
  bench_year?: string
  bench_rank: number | null
  bench_of: number | null
  bench_fallback?: boolean
  bench_note?: string
  bench_source?: string
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
  /** The two directions for THIS company, read together. null outside the scored universe. */
  dual?: DualRow | null
  /** Where this company's movement sits across Profit / People / Planet. */
  ppp?: PPPShares | null
  /** A model estimate of 6-month return, always carrying its measured skill. */
  forecast?: ForecastPayload | null
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
  /**
   * The SCALE of `momentum_series`. 'evidence' is a direction consensus on −1..+1 (the real
   * basket); 'numeric' is a momentum percentage (the demo set). They must never be rendered with
   * the same axis suffix — a consensus of 0.998 drawn as "1%" reads as a rounding error when it
   * means the evidence overwhelmingly agrees.
   */
  momentum_series_kind?: 'evidence' | 'numeric'
  /** Prose provenance for the series — a real quarterly replay, or an illustrative interpolation. */
  momentum_series_basis?: string
  /** Cutoff date per point, for the real replay. Empty for the interpolated demo series. */
  momentum_series_labels?: string[]
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
  /**
   * The SECOND axis: financial price momentum read beside the ESG evidence momentum the engine
   * produced. Never inside it — nothing here reaches `composite_momentum`, `disagreement` or a
   * quadrant label, and `selftest.py` pins that the engine cannot import the module it comes
   * from. See `price_momentum.py`.
   */
  dual: DualBlock
  ppp: PPPBlock
  outlook: OutlookPayload
  focused: FocusedPayload | null
  watchlist: WatchlistEntry[]
  followups: { label: string; prompt: string }[]
  built_at: number
  fresh: string
}

// --------------------------------------------------------------------------- //
//  Dual momentum: the financial axis, beside the ESG one and never inside it
// --------------------------------------------------------------------------- //
/**
 * The four combinations of two signed directions, plus the two honest non-answers.
 *
 * `unknown` is NOT `flat`, and neither is a finding. A company with no scorable evidence scores
 * `composite_momentum` exactly 0.000 — 28 of the verified 52 did before the harvest — and
 * calling that a divergence would manufacture a claim out of an absence. Same discipline the
 * traction screen follows: an unrun test is not a failed one.
 */
export type AlignmentKey =
  | 'aligned' | 'downside_trap' | 'evidence_ahead' | 'both_falling' | 'flat' | 'unknown'

export interface DualRow {
  /** 12-1 price momentum, in percent. null where the listing is not quotable. */
  price_pct: number | null
  price_window: string
  /** The engine's own direction consensus for the same company, −1..+1. */
  esg_momentum: number | null
  signal_count: number
  alignment: AlignmentKey
  display: string
  tone: 'good' | 'bad' | 'warn' | 'muted'
  /**
   * WHY the pair cannot be read, when `alignment` is 'unknown'. '' otherwise.
   *
   * It comes from the server rather than being derived here because three different absences
   * land on the same key and only the server knows which universe is loaded — and on the
   * FICTIONAL demo set the honest answer is "this company does not exist", not "our symbol
   * column does not cover it", which would imply the company is real.
   */
  why?: string
  /** Focused row only: the date the price snapshot was captured, and the factor's full name. */
  captured?: string
  window_label?: string
  tooltip?: string
}

/**
 * Where one company's MOVEMENT sits across Profit / People / Planet — three shares of one whole,
 * drawn as a ternary plot.
 *
 * It is a magnitude, never a verdict: a dot in the Planet corner can mean rapid environmental
 * progress OR an environmental collapse, so `directions` travels with the shares and the panel
 * prints both. `known` is false when an axis is unmeasured, and the shares are then null rather
 * than 0 — sharing two axes over a missing third would inflate both and put the dot somewhere no
 * measurement supports.
 */
export interface PPPShares {
  known: boolean
  missing: string[]
  planet: number | null
  people: number | null
  profit: number | null
  directions: Partial<Record<'planet' | 'people' | 'profit', number | null>>
  /** Which corner it leans to. '' when not placeable. */
  lean: '' | 'planet' | 'people' | 'profit'
  /** The full rule, printed on the panel — a normalising constant chosen in private is how a
   *  composition quietly becomes an opinion. */
  basis: string
  why: string
}

export interface PPPBlock {
  rows: Record<string, PPPShares>
  basis: string
  placeable: number
  total: number
  /** How many lean Profit. NOT a drawing artefact — it is the evidence gap in a third view. */
  profit_led: number
  corners: Record<'planet' | 'people' | 'profit', string>
}

/**
 * A model estimate of forward price return, WITH the out-of-sample skill it actually achieved.
 *
 * `skill` and `verdict` are not optional decoration: this repo's whole argument is that a number
 * without its reliability is what a stale rating looks like from the outside, so the estimate is
 * never rendered without them. See `forecast.py`.
 */
export interface ForecastSkill {
  r2_oos: number
  mae_oos: number
  baseline_mae: number
  beats_baseline: boolean
  hit_rate: number
  majority_class: number
  beats_majority: boolean
}

/** The direction model's read: which way, how far from a coin flip, and how often it is right. */
export interface DirectionPayload {
  up_probability: number
  call: 'up' | 'down'
  /** Distance from a coin flip, 0..1. Printed instead of the bare probability: 0.52 and 0.94 are
   *  both "up" and mean entirely different things. */
  confidence: number
  skill: {
    accuracy: number; majority_class: number; beats_majority: boolean
    brier: number; brier_baseline: number; beats_brier: boolean
  }
  verdict: { word: string; line: string }
  factors_present: string[]
  factors_missing: Record<string, string>
  factor_note: string
}

export interface ForecastPayload {
  direction?: DirectionPayload | null
  /** Which market factors were REAL for this company rather than falling back to the mean. */
  factors_live?: string[]
  factors_missing?: Record<string, string>
  factor_note?: string
  available: boolean
  why?: string
  estimate_pct?: number
  horizon_months?: number
  skill?: ForecastSkill
  verdict?: { word: string; line: string }
  /** The model's typical out-of-sample error. Printed WITH the estimate, always. */
  typical_error_pct?: number | null
  sample_caveat?: string
  not_advice: string
  tested_on?: string[]
}

/** CGSI's PUBLISHED base rates. Attributed, historical, and explicitly not a forecast. */
export interface OutlookPayload {
  available: boolean
  horizon: string
  horizons: Record<string, string | null>
  rate: string | null
  caveat: string
  source: { publisher: string; title: string; date: string }
  not_a_forecast: string
  context: string[]
}

export interface DualBlock {
  rows: Record<string, DualRow>
  /** Measured off THIS run and THIS price snapshot — never a remembered statistic. */
  counts: Record<AlignmentKey, number>
  quotable: number
  total: number
  captured: string
  demo: boolean
  /** Set when NOTHING in this universe is readable, so the zero row can say why. */
  unavailable: string
  window: string
  window_label: string
  alignment: Record<AlignmentKey, {
    display: string; short: string; tone: string; rule: string; tooltip: string
  }>
  note: string
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
  /**
   * FORWARD-LOOKING, and labelled so by its own `header`. The real engine re-run over the same
   * evidence with only the SOURCE TYPE varied — a computed counterfactual, never a measurement
   * and never a claim about returns. Present on both universes; see `_roadmap_summary`.
   */
  roadmap?: RoadmapPayload | null
  /**
   * THE 10% TEST — cohort-level, frozen, `null` on the fictional demo universe.
   *
   * Two stages: the factor block first, then the ESG block on WHAT IT LEFT OVER. `stage1.r2_oos`
   * is here on purpose and is the number to read first — a panel that quoted the incremental
   * result without saying whether the baseline explained anything would be asserting a "90%"
   * this panel has not measured.
   */
  residual?: ResidualTest | null
  anchor: AnchorSummary
  records: Record<string, EngineRecord>
  badges: Record<string, Badges>
}

export interface ResidualVerdict { word: string; line: string }

export interface ResidualTest {
  ran: boolean
  why?: string
  built_at?: string
  question?: string
  /** The specification, declared in `residual.py`'s header BEFORE the first run. */
  spec?: string
  spec_note?: string
  horizon_months?: number
  rows?: number
  companies?: number
  train?: { cutoffs: string[]; rows: number }
  test?: { cutoffs: string[]; rows: number }
  stage1?: {
    block: string[]
    /** Out-of-sample R2 of the factor model itself. Negative here — read the panel copy. */
    r2_oos: number | null
    residual_share: number | null
  }
  stage2?: {
    block: string[]
    incremental_r2_oos: number | null
    /** The headline: mean rank correlation between the stage-2 call and the actual residual. */
    mean_ic: number | null
    ic_t_stat: number | null
    ic_cutoffs: number
    ic_series: { cutoff: string; ic: number; n: number }[]
  }
  ablation?: {
    r2_factors_only: number | null
    r2_with_esg: number | null
    delta_r2: number | null
    mae_factors_only: number
    mae_with_esg: number
    esg_helps_mae: boolean
  } | null
  verdict?: ResidualVerdict
  factors_missing?: Record<string, string>
  bias_note?: string
  sweep_summary?: {
    configurations: number
    with_contribution: number
    by_horizon: { horizon_months: number; cells: number; positive_verdict: number
                  mean_ic_positive: number; ic_t_at_least_2: number
                  mean_ic_across_specs: number | null }[]
    note: string
    structure_note?: string
    horizon_note?: string
  }
  sample_caveat?: string
  not_advice?: string
  /**
   * THE SEALED-HOLDOUT RESULT — the stricter test, and the one that OUTRANKS `verdict` above.
   *
   * `verdict` comes from a single train/test split. This comes from train / validation / holdout
   * where the holdout is scored once, and the two DISAGREE. When both are on screen the holdout
   * leads, because it is the better-designed question and because the gap between them is the
   * most instructive thing either produced.
   */
  solve?: SolveResult | null
}

export interface RoadmapScenario {
  key: string
  title: string
  unlock: string
  /** 'measured' for today's row; 'counterfactual' for every forward one. Drives the badge. */
  reality: 'measured' | 'counterfactual'
  company_pr_share: number
  mean_company_confidence: number
  companies_confident: number
  companies: number
  hidden_winners: number
  confident_delta: number
}

export interface RoadmapPayload {
  /** Rendered verbatim. The disclosure lives with the data so the two cannot drift apart. */
  header: string
  deck_line: string
  illustrative: boolean
  dial: string
  source_quality: Record<string, number>
  scenarios: RoadmapScenario[]
}

export interface SolvePanel {
  panel: string
  companies: number
  rows: number
  configs_tried: number
  chosen: { transform: string; lambda: number; shrink: number }
  split: { train: string[]; validation: string[]; holdout: string[] }
  stage1_r2_holdout: number | null
  /** Never rendered alone — only beside the holdout that refuted it. See the panel component. */
  validation_pct: number | null
  holdout_pct: number | null
  holdout_ic: number | null
  holdout_ic_t: number | null
  verdict: ResidualVerdict
  sample_caveat: string
}

export interface SolveResult {
  primary: 'wide' | 'narrow'
  wide?: SolvePanel
  narrow?: SolvePanel
  verdict: ResidualVerdict
  lesson: string
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
    | { kind: 'monitor'; ticker: string; company: string; already: boolean }
    | { kind: 'relay'; ticker: string; mode: 'compete' | 'interrogate'; needs_build: boolean; company: string; demo_numeric?: boolean }
    | { kind: 'relay_live'; text: string; mode: 'compete' | 'interrogate' }
}

export interface ComparePayload {
  data: {
    rows: { company: string; ticker: string; esg_score: number | null; momentum: { E: number | null; S: number | null; G: number | null } }[]
    pillars: string[]
    has_momentum: boolean
    /** Scale of the momentum values: 'numeric' is a percentage, 'evidence' a −1..+1
     *  consensus. 'mixed' means the set spans both and must not be drawn on one axis. */
    momentum_basis?: 'numeric' | 'evidence' | 'mixed' | ""
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

/* ---------------------------------------------------------------------------------------------
 * The analyst's book.
 *
 * The audience is a SELL-SIDE ESG research analyst: they cover a universe and walk into client
 * calls needing to defend a view a portfolio manager will push back on. A client profile reuses
 * the setup answers (mandate / risk / horizon / green focus), so a client IS a saved setup plus a
 * coverage list and a meeting log.
 *
 * The brief carries NO recommendation by construction — it prepares evidence and objections, and
 * the analyst forms the view. Nothing in this payload is scored; it is composed from a finished
 * run, so `run_id` is untouched.
 * ------------------------------------------------------------------------------------------- */

export interface ClientProfile {
  risk?: string
  horizon?: string
  green_focus?: boolean
}

export interface ClientSummary {
  client_id: string
  name: string
  account_type: string
  desk: string
  mandate: string
  profile: ClientProfile
  coverage: string[]
  coverage_n: number
  last_met: string
  meetings_n: number
  open_follow_ups: number
  _origin?: string
}

/** One line of "what changed since you last spoke". `kind` orders the brief. */
export interface ClientChange {
  company_id: string
  company: string
  kind: 'label_move' | 'confidence_move' | 'evidence_added' | 'momentum_move'
  note: string
  label_from?: string | null
  label_to?: string | null
  label_from_display?: string | null
  label_to_display?: string | null
  confidence_from?: number | null
  confidence_to?: number | null
  confidence_delta?: number | null
  momentum_from?: number | null
  momentum_to?: number | null
  momentum_delta?: number | null
  signals_from?: number | null
  signals_to?: number | null
  signals_delta?: number | null
}

export interface ClientDelta {
  has_baseline: boolean
  since: string
  since_run: string
  current_run: string
  as_of: string
  changes: ClientChange[]
  unchanged: number
  new_names: string[]
  dropped: string[]
  covered: number
  note?: string
}

export interface BriefPosition {
  company_id: string
  company: string
  country: string
  industry: string
  label: string
  label_display: string
  disagreement: number | null
  momentum: number | null
  confidence: number | null
  signal_count: number | null
  momentum_percentile: number | null
  rating_percentile: number | null
  incumbent_notch?: string | null
  delisted: boolean
  summary: string
  case_for: string[]
  case_against: string[]
  financial: { verdict?: string; pros?: string[]; cons?: string[]; note?: string }
  watch_outs: string[]
  pipeline: { bucket?: string; display?: string; tone?: string; note?: string }
  headlines: { title: string; url: string; source: string; published_at: string }[]
  margins: {
    key: string; label: string; value: number; boundary: number
    boundary_name: string; distance: number; side: string; note?: string
  }[]
  load_bearing: number | null
  flip_note: string
  flip_error?: string
}

/** What the client will push on, in their words, with the dated answer beside it. */
export interface BriefObjection {
  company_id: string
  company: string
  challenge: string
  kind: string
  our_answer: string
  what_would_move_it: string
  evidence_n: number | null
  other_weaknesses?: number
}

export interface ClientBrief {
  client: ClientSummary
  brief_note: string
  run_id: string
  as_of: string
  delta: ClientDelta
  open_follow_ups: { text: string; since: string }[]
  positions: BriefPosition[]
  objections: BriefObjection[]
  unknowns: { company: string; company_id: string; gap: string }[]
  origination: { N: number; M: number; K: number } | null
  not_covered: string[]
  disclaimer: string
  no_llm: boolean
}
