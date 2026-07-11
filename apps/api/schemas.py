"""Request models for the EWL API. Shared by routers and the web parity test."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PipelineRequest(BaseModel):
    # Defaults mirror the web client's CONFIG_DEFAULTS (lib/config.ts); keep in sync.
    # symbol is bounded + charset-checked before yfinance (allows BTC-USD/^GSPC/BRK.B/ES=F).
    symbol: str = Field(
        default="DDOG",
        description="Ticker symbol (yfinance compatible)",
        min_length=1,
        max_length=20,
        pattern=r"^[A-Za-z0-9.\-^=]+$",
    )
    period: Literal["2y", "5y", "10y", "max"] = Field(default="max")
    timeframe: Literal["day", "week", "month"] = Field(default="week")
    scale_mode: Literal["linear", "log"] = Field(default="linear")

    atr_period: int = Field(default=14, ge=4, le=60)
    atr_multiplier: float = Field(default=3.0, ge=0.5, le=6.0)
    atr_floor: float = Field(default=0.10, ge=0, le=0.3)
    min_bars_between: int = Field(default=4, ge=1, le=12)

    k_sigma: float = Field(default=0.5, ge=0.1, le=1.5)
    log_tol_fib: float = Field(default=0.05, ge=0.01, le=0.3)
    pull_depth_lo: float = Field(default=0.382, ge=0.0, le=0.95)
    pull_depth_hi: float = Field(default=0.618, ge=0.0, le=0.95)
    pull_depth_tol: float = Field(default=0.15, ge=0.01, le=0.5)
    pivot_window: int = Field(default=2, ge=1, le=5)
    commitment_curve: Literal["linear", "sqrt", "off"] = Field(default="linear")

    @model_validator(mode="after")
    def _check_pull_depth_window(self) -> PipelineRequest:
        # ScoringConfig doesn't validate this; a flipped window silently scores nonsense.
        if self.pull_depth_lo >= self.pull_depth_hi:
            raise ValueError("pull_depth_lo must be strictly less than pull_depth_hi")
        return self


class Layer1Request(PipelineRequest):
    # Scenario objects aren't JSON-round-trippable, so the server re-runs and picks by id.

    scenario_id: str = Field(..., description="Scenario.id from /api/pipeline response")


AnalystMode = Literal["explanation", "outlook", "risk", "differentiator"]


class AnalystStreamRequest(PipelineRequest):
    scenario_id: str = Field(..., description="Scenario.id from /api/pipeline")
    mode: AnalystMode = Field(default="explanation")
    # Typewriter pacing for fresh narration; skipped for pre-resolved text (see gen()).
    rate_tps: float = Field(default=40.0, gt=0, le=500)
    force_refresh: bool = Field(default=False)


class QaChartContext(PipelineRequest):
    """Pipeline params + scenario_id: reconstructs the chart the user is looking at."""

    scenario_id: str = Field(..., description="Scenario.id from /api/pipeline response")


class QaRequest(BaseModel):
    """chart optional: when set, its params reconstruct that chart for chart-aware
    answers; when omitted, the answer is pure theory RAG."""

    question: str = Field(..., min_length=1, max_length=500)
    chart: QaChartContext | None = Field(
        default=None, description="optional chart context for chart-aware Q&A"
    )
    force_refresh: bool = Field(default=False)


