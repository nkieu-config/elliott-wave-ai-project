"""Single-shot theory Q&A route (Layer-2, LLM + similarity retrieval). One blocking
call returning JSON — the answer is short, so SSE pacing buys nothing."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from apps.api import pipeline_ops
from apps.api.schemas import QaRequest
from apps.api.schemas_responses import QaCitation, QaResponse
from apps.api.services import analyst_service
from engine import Bar, Scenario

router = APIRouter(prefix="/api/v1", tags=["qa"])
_log = logging.getLogger(__name__)


@router.post("/qa")
async def qa(req: QaRequest) -> QaResponse:
    # Cheap env check up front: rejecting a disabled deployment must not trigger
    # the heavy analyst build just to answer 503.
    if not analyst_service.qa_enabled_setting():
        raise HTTPException(
            status_code=503,
            detail=(
                "Q&A unavailable: embedder not loaded (needs ANALYST_QA=1 and "
                "the `grounding` extra)."
            ),
        )

    # Off the event loop: fetch+pipeline and the answer call all block.
    def _run() -> QaResponse:
        scenario: Scenario | None = None
        bars: list[Bar] | None = None
        scale_mode = "linear"
        if req.chart is not None:
            # Chart-aware: rebuild the scenario the user is looking at.
            fetched = pipeline_ops.fetch_bars_or_502(req.chart)
            result = pipeline_ops.execute_pipeline(req.chart, fetched)
            _scenarios, scenario = pipeline_ops.resolve_scenario(
                result, req.chart.scenario_id
            )
            bars = list(fetched)
            scale_mode = req.chart.scale_mode
        try:
            output = analyst_service.answer_question(
                req.question,
                scenario=scenario,
                bars=bars,
                scale_mode=scale_mode,
                force_refresh=pipeline_ops.effective_force_refresh(req.force_refresh),
            )
        except HTTPException:
            raise
        except Exception as e:
            # Don't echo internal exception text to LAN clients.
            _log.exception("qa failed")
            raise HTTPException(status_code=500, detail="Q&A computation failed") from e
        return QaResponse(
            question=output.question,
            answer=output.answer,
            citations=[
                QaCitation(page=c.page, claim_sentence=c.claim_sentence)
                for c in output.citations
            ],
            retrieved_pages=list(output.retrieved_pages),
            out_of_scope=output.out_of_scope,
            fell_back=output.fell_back,
            cached=output.cached,
            model_id=output.model_id,
        )

    return await asyncio.to_thread(_run)
