"""SSE analyst narration route (Layer-2, LLM). ``analyze()`` returns full text in
one blocking call; ``gen()`` paces it as ``token`` events."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.api import pipeline_ops
from apps.api.middleware import RELEASE_SCOPE_KEY
from apps.api.schemas import AnalystStreamRequest
from apps.api.schemas_responses import (
    CitationsFrame,
    DoneFrame,
    ErrorFrame,
    QaCitation,
    StartFrame,
    TokenFrame,
)
from apps.api.services import analyst_service
from engine import Bar, Scenario

router = APIRouter(prefix="/api/v1", tags=["analyst"])
_log = logging.getLogger(__name__)

# Wire's terse mode names → the analyst module's prompt names.
_MODE_TO_ANALYST: dict[str, str] = {
    "explanation": "explanation",
    "outlook": "scenario_outlook",
    "risk": "slot_focus",
    "differentiator": "differentiator",
}


@router.post("/analyst/stream")
async def analyst_stream(req: AnalystStreamRequest, request: Request) -> StreamingResponse:
    """Server-Sent Events stream of an analyst narration.

    Event types:
        start      — { mode, model_id, scenario_id }
        token      — { text } (whitespace-split, paced by rate_tps)
        citations  — { citations[], cached, fell_back, model_id, prompt_version }
        done       — { total_tokens, gen_ms } (gen_ms = real LLM wall-time, not playback)
        error      — { message }
    """
    analyst_mode = _MODE_TO_ANALYST[req.mode]

    # Pre-flight off the event loop: failures surface as HTTP status (not mid-stream
    # `error`), and the blocking work doesn't stall the loop.
    def _preflight() -> tuple[tuple[Bar, ...], list[Scenario], Scenario, str]:
        bars = pipeline_ops.fetch_bars_or_502(req)
        result = pipeline_ops.execute_pipeline(req, bars)
        scenarios, scenario = pipeline_ops.resolve_scenario(result, req.scenario_id)
        try:
            model_id = analyst_service.get_model_id()
        except Exception as e:
            # Keep "analyst init" so the client can distinguish this failure.
            _log.exception("analyst init failed")
            raise HTTPException(status_code=500, detail="analyst init failed") from e
        return bars, scenarios, scenario, model_id

    bars, scenarios, scenario, model_id = await asyncio.to_thread(_preflight)

    def _frame(event: str, payload: BaseModel) -> bytes:
        return f"event: {event}\ndata: {payload.model_dump_json()}\n\n".encode()

    async def gen() -> AsyncIterator[bytes]:
        emitted = 0
        try:
            yield _frame(
                "start",
                StartFrame(
                    mode=req.mode,
                    model_id=model_id,
                    scenario_id=req.scenario_id,
                ),
            )

            # LLM call in a thread; time only generation (token loop below is playback).
            t_gen0 = time.perf_counter()
            output = await asyncio.to_thread(
                analyst_service.analyze,
                scenario,
                list(bars),
                analyst_mode,
                all_scenarios=scenarios,
                scale_mode=req.scale_mode,
                force_refresh=pipeline_ops.effective_force_refresh(req.force_refresh),
            )
            gen_ms = (time.perf_counter() - t_gen0) * 1000.0
            # Heavy work is done — free the concurrency slot so the paced
            # playback below doesn't hold capacity against other requests.
            release_slot = request.scope.get(RELEASE_SCOPE_KEY)
            if release_slot is not None:
                release_slot()
            # Skip pacing for pre-resolved text (cache hit / fallback): the
            # typewriter would falsely imply a live LLM.
            is_pre_resolved = bool(output.cached or output.fell_back)
            sleep_s = 0.0 if is_pre_resolved else (1.0 / req.rate_tps)

            # Filter empties: "".split(" ") == [""] would emit one ghost token.
            tokens = [t for t in (output.narration or "").split(" ") if t]
            for tok in tokens:
                yield _frame("token", TokenFrame(text=tok + " "))
                emitted += 1
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)

            yield _frame(
                "citations",
                CitationsFrame(
                    citations=[
                        QaCitation(page=c.page, claim_sentence=c.claim_sentence)
                        for c in (output.citations or ())
                    ],
                    cached=bool(output.cached),
                    fell_back=bool(output.fell_back),
                    model_id=output.model_id,
                    prompt_version=output.prompt_version,
                ),
            )

            yield _frame(
                "done",
                DoneFrame(total_tokens=emitted, gen_ms=round(gen_ms, 1)),
            )
        except asyncio.CancelledError:
            # Re-raise so cancellation propagates instead of being swallowed.
            _log.info(
                "stream cancelled after %d tokens (mode=%s)",
                emitted,
                req.mode,
            )
            raise
        except Exception:
            # Don't echo internal exception text to LAN clients.
            _log.exception("analyst.analyze failed (mode=%s)", req.mode)
            yield _frame("error", ErrorFrame(message="analyst narration failed"))
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            # `Connection` is hop-by-hop — the ASGI server owns it; don't set here.
        },
    )
