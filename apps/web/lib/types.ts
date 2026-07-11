/**
 * The app's view of the wire shape. Every field name and nullability comes from
 * `api-types.gen.ts`, which is generated from the API's OpenAPI schema — rename a
 * field server-side and this file stops compiling.
 *
 * Regenerate with `npm run gen:api-types` (CI fails if it drifts).
 */

import type { components } from "./api-types.gen";

type Wire<K extends keyof components["schemas"]> = components["schemas"][K];

/**
 * Enum-ish wire fields arrive as `string`, on purpose: `schemas_responses.py` keeps
 * them wide so a new engine value never 500s a valid response. These unions are the
 * values the UI knows how to render — narrow with a total function at the point of
 * use (see `confidenceTier`, `TIER_FG`) so an unknown value degrades instead of
 * crashing. Do not bake them into the wire types below; that would be a lie.
 */
export type PivotKind = "high" | "low";
export type ScaleMode = "linear" | "log";
export type ConfidenceTier = "low" | "mid" | "high";
export type WaveStage = "complete" | "early" | "mid" | "late" | "overshot" | "unknown";
export type TargetType =
  | "retracement"
  | "internal"
  | "external"
  | "invalidation"
  | "projected";

export type Bar = Wire<"BarOut">;
export type Pivot = Wire<"PivotOut">;
export type Segment = Wire<"SegmentOut">;

// Only populated on Wave nodes whose pattern_kind is LINK_T/LINK_S/LINK_SE.
export type LinkSet = Wire<"LinkSetOut">;
export type Wave = Wire<"WaveOut">;

export type ConfidenceTierInfo = Wire<"ConfidenceTierOut">;
export type ScoreComponents = Wire<"ScenarioOut">["score_components"];
export type Scenario = Wire<"ScenarioOut">;

// suggested_action may be Thai.
export type Diagnostic = Wire<"DiagnosticOut">;
export type AnalysisReport = Wire<"ReportOut">;
export type ScenarioCounts = Wire<"ScenarioCountsOut">;

export type SampleData = Wire<"PipelineResponse">;

export type Target = Wire<"TargetOut">;
export type TargetSet = Wire<"TargetSetOut">;
export type TheoryRef = Wire<"TheoryRefOut">;
export type Bottleneck = Wire<"BottleneckOut">;
export type ConfirmationLevel = Wire<"ConfirmationLevelOut">;
export type ConfirmationReport = Wire<"ConfirmationReportOut">;
export type PriceMove = Wire<"PriceMoveOut">;

export type DecisionSummary = Wire<"DecisionSummaryOut">;
export type AlternativeBrief = Wire<"AlternativeBriefOut">;

export type NextPattern = Wire<"NextPatternOut">;
export type SuccessionReport = Wire<"SuccessionReportOut">;
export type Layer1Result = Wire<"Layer1Response">;

// Deterministic — no LLM involved.
export type FamilyEducation = Wire<"EducationResponse">;
export type CitationRef = Wire<"QaCitation">;

// SSE narration frames. Not reachable from a route signature server-side, so
// dump-openapi.py publishes them into the schema explicitly.
export type StartFrame = Wire<"StartFrame">;
export type TokenFrame = Wire<"TokenFrame">;
export type CitationsFrame = Wire<"CitationsFrame">;
export type DoneFrame = Wire<"DoneFrame">;
export type ErrorFrame = Wire<"ErrorFrame">;
