"""The wire shape's single source of truth: ``serializers.py`` constructs these
models and routes return them directly.

``apps/web/lib/types.ts`` is *generated* from these via OpenAPI, so renaming a field
here stops the web compiling. Regenerate with ``apps/web/scripts/dump-openapi.py``,
then ``npm run gen:api-types`` in apps/web; CI fails if either artefact is stale.

Enum-ish fields are typed ``str`` not ``Literal`` so a new enum value never 500s a valid
response. The web narrows them at the point of use (``asTier``, ``asScaleMode``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PivotOut(BaseModel):
    index: int
    time: str
    price: float
    kind: str
    bar_index: int | None


class BarOut(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class SegmentOut(BaseModel):
    start: PivotOut
    end: PivotOut


class LinkSetOut(BaseModel):
    pattern_kind: str
    pattern_label: str
    leg_start: int
    leg_end: int
    degree_label: str | None


class WaveOut(BaseModel):
    role: str
    pattern_kind: str | None
    degree_label: str | None
    span_start: PivotOut
    span_end: PivotOut | None
    nesting_level: int
    segments: list[SegmentOut]
    children: list[WaveOut]
    sets: list[LinkSetOut] | None


class ConfidenceTierOut(BaseModel):
    key: str
    word: str


class ScenarioOut(BaseModel):
    id: str
    score: float
    score_components: dict[str, float]
    family: str
    family_label: str
    pattern_kind: str | None
    pattern_label: str | None
    is_complete: bool
    depth: int
    confidence_tier: ConfidenceTierOut
    root: WaveOut
    open_subtree: WaveOut | None


class DiagnosticOut(BaseModel):
    death_reason: str
    suggested_action: str
    first_divergence_index: int
    last_alive_segment_index: int


class ReportOut(BaseModel):
    anchor: PivotOut | None
    segments: list[SegmentOut]
    scenarios: list[ScenarioOut]
    diagnostic: DiagnosticOut | None
    summary: str


class ScenarioCountsOut(BaseModel):
    total: int
    complete: int
    open: int


class PipelineConfigOut(BaseModel):
    scale_mode: str
    atr_period: int
    atr_multiplier: float
    atr_floor: float
    min_bars_between: int
    k_sigma: float
    log_tol_fib: float
    pull_depth_lo: float
    pull_depth_hi: float
    pull_depth_tol: float
    pivot_window: int
    commitment_curve: str


class MetaOut(BaseModel):
    symbol: str
    period: str
    timeframe: str
    generated_at: str
    config: PipelineConfigOut


class TheoryRefOut(BaseModel):
    pages: list[int]
    concept: str
    binding: str
    note: str


class TargetOut(BaseModel):
    name: str
    price: float
    type: str
    theory_page: int
    derivation: str


class TargetSetOut(BaseModel):
    confirmation_targets: list[TargetOut]
    fib_flow_targets: list[TargetOut]
    invalidation: TargetOut


class BottleneckOut(BaseModel):
    slot_name: str
    slot_value: float
    dimension: str
    is_dim_minimum: bool
    is_overall_minimum: bool
    gap_to_next: float
    intermediates: dict[str, Any]
    plain_explanation: str
    theory_ref: TheoryRefOut


class ConfirmationLevelOut(BaseModel):
    name: str
    condition: str
    met: bool
    triggered_at_bar: int | None
    theory_page: int


class NotApplicableReasonOut(BaseModel):
    text: str
    citation: int | None


class ConfirmationReportOut(BaseModel):
    family: str
    levels: list[ConfirmationLevelOut]
    is_applicable: bool
    not_applicable_reason: NotApplicableReasonOut | None
    highest_met: str | None


class PriceMoveOut(BaseModel):
    label: str
    price: float
    pct_from_current: float


class DecisionSummaryOut(BaseModel):
    current: PriceMoveOut | None
    target_low: PriceMoveOut | None
    target_high: PriceMoveOut | None
    invalidation: PriceMoveOut | None
    risk_reward: float | None
    direction: str | None
    horizon_bars: int | None
    bar_interval: str | None
    horizon_human: str | None
    stage: str
    open_wave_start: float | None
    open_wave_direction: str | None
    wave_progress_pct: float | None


class AlternativeBriefOut(BaseModel):
    family: str
    family_label: str
    target_low: PriceMoveOut | None
    target_high: PriceMoveOut | None
    invalidation: PriceMoveOut | None
    direction: str | None
    stage: str


class NextPatternOut(BaseModel):
    link_type: str
    next_families: list[str]
    link_band_near: float | None
    link_band_far: float | None
    theory_pages: list[int]
    rationale: str
    link_wave_size: float | None


class SuccessionReportOut(BaseModel):
    family: str
    is_terminal: bool
    next_patterns: list[NextPatternOut]
    note: str


class Layer1Response(BaseModel):
    scenario_id: str
    bottleneck: BottleneckOut | None
    confirmation: ConfirmationReportOut | None
    targets: TargetSetOut | None
    succession: SuccessionReportOut | None
    decision: DecisionSummaryOut | None
    alternative: AlternativeBriefOut | None
    score_intermediates: dict[str, Any]


class PipelineResponse(BaseModel):
    meta: MetaOut
    bars: list[BarOut]
    raw_pivots: list[PivotOut]
    active_pivots: list[PivotOut]
    selected_anchor: PivotOut | None
    report: ReportOut | None
    top_scenario: ScenarioOut | None
    top_scenario_layer1: Layer1Response | None
    scenario_counts: ScenarioCountsOut
    load_error: str | None


class EducationResponse(BaseModel):
    family: str
    title: str
    one_line: str
    rules: list[str]
    visual_cues: list[str]


class QaCitation(BaseModel):
    page: int
    claim_sentence: str


class QaResponse(BaseModel):
    question: str
    answer: str
    citations: list[QaCitation]
    # Pages similarity surfaced — the answer's allowed-citation set.
    retrieved_pages: list[int]
    # True when the question fell below the theory-relevance floor (no LLM call).
    out_of_scope: bool
    # True when the gate rejected the answer (generic fallback returned).
    fell_back: bool
    cached: bool
    model_id: str | None


# SSE narration frames. FastAPI can't infer these from the route (the body is a
# stream, not a model), so `apps/web/scripts/dump-openapi.py` publishes them into
# the schema by hand — otherwise the web would be back to hand-typing them.
class StartFrame(BaseModel):
    mode: str
    model_id: str | None
    scenario_id: str


class TokenFrame(BaseModel):
    text: str


class CitationsFrame(BaseModel):
    citations: list[QaCitation]
    cached: bool
    fell_back: bool
    model_id: str | None
    prompt_version: str | None


class DoneFrame(BaseModel):
    total_tokens: int
    gen_ms: float


class ErrorFrame(BaseModel):
    message: str


# Not reachable from any route signature — see the note above.
SSE_FRAMES: tuple[type[BaseModel], ...] = (
    StartFrame,
    TokenFrame,
    CitationsFrame,
    DoneFrame,
    ErrorFrame,
)


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    analyst_prewarmed: bool
    qa_enabled: bool


# WaveOut.children is a self-reference — resolve the forward ref.
WaveOut.model_rebuild()
