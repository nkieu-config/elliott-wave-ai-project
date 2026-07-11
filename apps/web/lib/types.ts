export type PivotKind = "high" | "low";
export type ScaleMode = "linear" | "log";

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Pivot {
  index: number;
  time: string;
  price: number;
  kind: PivotKind;
  bar_index: number | null;
}

export interface Segment {
  start: Pivot;
  end: Pivot;
}

// Only populated on Wave nodes whose pattern_kind is LINK_T/LINK_S/LINK_SE.
export interface LinkSet {
  pattern_kind: string;
  pattern_label: string;
  /** Inclusive index range into the parent Wave's `children`. */
  leg_start: number;
  leg_end: number;
  degree_label: string | null;
}

export interface Wave {
  role: string;
  pattern_kind: string | null;
  degree_label: string | null;
  span_start: Pivot;
  span_end: Pivot | null;
  nesting_level: number;
  segments: Segment[];
  children: Wave[];
  /** Null for non-link nodes. */
  sets: LinkSet[] | null;
}

export type ConfidenceTier = "low" | "mid" | "high";

export interface ConfidenceTierInfo {
  key: ConfidenceTier;
  word: "Low" | "Moderate" | "Strong";
}

// Arbitrary slot keys plus the named roll-ups the bottleneck logic reads, typed
// so `total`/`quality`/`commitment` narrow to `number | undefined`.
export type ScoreComponents = Record<string, number> & {
  total?: number;
  quality?: number;
  commitment?: number;
};

export interface Scenario {
  id: string;
  score: number;
  score_components: ScoreComponents;
  family: string;
  family_label: string;
  pattern_kind: string | null;
  pattern_label: string | null;
  is_complete: boolean;
  depth: number;
  confidence_tier: ConfidenceTierInfo;
  root: Wave;
  /** Open sub-pattern tree (not yet in root.children); projection walks it DFS
   * so the dashed line traces the partial sub-count. Null when complete. */
  open_subtree: Wave | null;
}

// suggested_action may be Thai.
export interface Diagnostic {
  death_reason: string;
  suggested_action: string;
  first_divergence_index: number;
  last_alive_segment_index: number;
}

export interface AnalysisReport {
  anchor: Pivot | null;
  segments: Segment[];
  scenarios: Scenario[];
  /** Null only for pre-diagnostic snapshots; the live API always emits it. */
  diagnostic: Diagnostic | null;
  summary: string;
}

export interface ScenarioCounts {
  total: number;
  complete: number;
  open: number;
}

export interface SampleData {
  meta: {
    symbol: string;
    period: string;
    timeframe: string;
    generated_at: string;
    config: {
      scale_mode: ScaleMode;
      atr_period: number;
      atr_multiplier: number;
      atr_floor: number;
      min_bars_between: number;
      k_sigma: number;
      log_tol_fib: number;
      pull_depth_lo: number;
      pull_depth_hi: number;
      pull_depth_tol: number;
      pivot_window: number;
      commitment_curve: string;
    };
  };
  bars: Bar[];
  raw_pivots: Pivot[];
  active_pivots: Pivot[];
  selected_anchor: Pivot | null;
  report: AnalysisReport | null;
  top_scenario: Scenario | null;
  /** Pre-computed Layer-1 for top_scenario; hydrates the ["layer1", config,
   * top.id] cache without a second request. Null on eager failure / no
   * scenarios — clients fall back to /api/scenario/layer1. */
  top_scenario_layer1: Layer1Result | null;
  scenario_counts: ScenarioCounts;
  load_error: string | null;
}

// analyst.compute_layer1 output
export type TargetType =
  | "retracement"
  | "internal"
  | "external"
  | "invalidation"
  | "projected";

export interface Target {
  name: string;
  price: number;
  type: TargetType;
  theory_page: number;
  derivation: string;
}

export interface TargetSet {
  confirmation_targets: Target[];
  fib_flow_targets: Target[];
  invalidation: Target;
}

export interface TheoryRef {
  pages: number[];
  concept: string;
  binding: "rule_implementation" | "concept_operationalization" | "heuristic";
  note: string;
}

export interface Bottleneck {
  slot_name: string;
  slot_value: number;
  dimension: "structural" | "visual";
  is_dim_minimum: boolean;
  is_overall_minimum: boolean;
  gap_to_next: number;
  intermediates: Record<string, unknown>;
  plain_explanation: string;
  theory_ref: TheoryRef;
}

export interface ConfirmationLevel {
  name: string;
  condition: string;
  met: boolean;
  triggered_at_bar: number | null;
  theory_page: number;
}

export interface ConfirmationReport {
  family: string;
  levels: ConfirmationLevel[];
  is_applicable: boolean;
  not_applicable_reason: { text: string; citation: number | null } | null;
  highest_met: string | null;
}

export interface PriceMove {
  label: string;
  price: number;
  pct_from_current: number;
}

export type WaveStage = "complete" | "early" | "mid" | "late" | "overshot" | "unknown";

export interface DecisionSummary {
  current: PriceMove | null;
  target_low: PriceMove | null;
  target_high: PriceMove | null;
  invalidation: PriceMove | null;
  risk_reward: number | null;
  direction: string | null;
  horizon_bars: number | null;
  bar_interval: string | null;
  horizon_human: string | null;
  stage: WaveStage;
  open_wave_start: number | null;
  open_wave_direction: string | null;
  wave_progress_pct: number | null;
}

export interface AlternativeBrief {
  family: string;
  family_label: string;
  target_low: PriceMove | null;
  target_high: PriceMove | null;
  invalidation: PriceMove | null;
  direction: string | null;
  stage: WaveStage;
}

export interface NextPattern {
  link_type: string;
  next_families: string[];
  link_band_near: number | null;
  link_band_far: number | null;
  theory_pages: number[];
  rationale: string;
  link_wave_size: number | null;
}

export interface SuccessionReport {
  family: string;
  is_terminal: boolean;
  next_patterns: NextPattern[];
  note: string;
}

export interface Layer1Result {
  scenario_id: string;
  bottleneck: Bottleneck | null;
  confirmation: ConfirmationReport | null;
  targets: TargetSet | null;
  succession: SuccessionReport | null;
  decision: DecisionSummary | null;
  alternative: AlternativeBrief | null;
  score_intermediates: Record<string, unknown>;
}

// Deterministic — no LLM involved.
export interface FamilyEducation {
  family: string;
  title: string;
  one_line: string;
  rules: string[];
  visual_cues: string[];
}

export interface CitationRef {
  page: number;
  claim_sentence: string;
}
