from __future__ import annotations

from engine.adaptive import (
    allowed_sub_patterns,
    expected_direction,
)
from engine.degree import gann_band_ok
from engine.parser.families import close_pregate_ok, incremental_ok, run_verifier
from engine.parser.gates import _bar_span
from engine.parser.types import _Context, _Hypothesis, _Leg
from engine.types import (
    PatternKind,
    ScaleMode,
    WaveRole,
)


def _run_and_cache_verifier(ctx: _Context, mode: ScaleMode) -> bool:
    # Caller must have checked ctx.is_complete and ctx.final_kind is None. False iff rejected.
    result = run_verifier(ctx.family, ctx.legs, mode)
    if result is None:
        return False
    ctx.final_kind, ctx.rules_log = result
    return True


def _try_finalize(ctx: _Context, mode: ScaleMode) -> bool:
    if not ctx.is_complete:
        return False
    if ctx.final_kind is not None:
        return True
    return _run_and_cache_verifier(ctx, mode)


def _close_up_at_end(h: _Hypothesis, mode: ScaleMode) -> None:
    while h.depth > 1 and h.top.is_complete:
        if not _try_finalize(h.top, mode):
            break
        if not _close_top_into_parent(h, mode):
            break


def _close_top_into_parent(h: _Hypothesis, mode: ScaleMode) -> bool:
    if not _can_close_top(h):
        return False

    closed = h.context_stack[-1]
    parent_ctx = h.context_stack[-2]
    parent_role = closed.parent_role
    if parent_role is None:   # pragma: no cover — invariant
        raise RuntimeError(
            "closed sub-context has parent_role=None despite _can_close_top "
            "returning True — parser invariant violated"
        )

    if not _kind_allowed_under_parent(closed.final_kind, parent_ctx, parent_role):
        return False

    leg = _build_closed_leg(closed, parent_role)

    if not _check_close_direction_and_ratio(leg, parent_ctx, parent_role, mode):
        return False
    if not close_pregate_ok(closed, parent_ctx, parent_role, mode):
        return False
    if not gann_band_ok(parent_ctx, leg, mode):
        return False

    _append_leg(parent_ctx, leg)
    if not _maybe_finalize_parent(parent_ctx, mode):
        parent_ctx.legs.pop()
        return False

    h.context_stack.pop()
    return True


def _can_close_top(h: _Hypothesis) -> bool:
    if h.depth < 2:
        return False
    if not h.top.is_complete or h.top.final_kind is None:
        return False
    return h.top.parent_role is not None


def _kind_allowed_under_parent(
    closed_kind: PatternKind | None,
    parent_ctx: _Context,
    parent_role: WaveRole,
) -> bool:
    # Only gate catching 3W_S2_LONGER under 5W_TREND.s1 (p.80); verifier strips kind.
    return closed_kind in allowed_sub_patterns(parent_ctx.family, parent_role)


def _build_closed_leg(closed: _Context, parent_role: WaveRole) -> _Leg:
    return _Leg(
        role=parent_role,
        span_start=closed.legs[0].span_start,
        span_end=closed.legs[-1].span_end,
        pattern_kind=closed.final_kind,
        sub_legs=list(closed.legs),
    )


def _check_close_direction_and_ratio(
    leg: _Leg,
    parent_ctx: _Context,
    parent_role: WaveRole,
    mode: ScaleMode,
) -> bool:
    if not parent_ctx.legs:  # first leg defines trend; no checks apply
        return True
    expected_dir = expected_direction(
        parent_ctx.family,
        parent_role,
        parent_ctx.trend_dir,
    )
    if leg.direction != expected_dir:
        return False
    leg_bars = _bar_span(leg.span_start, leg.span_end)
    return incremental_ok(
        parent_ctx,
        parent_role,
        leg.length(mode),
        mode,
        leg_bars=leg_bars,
    )


def _append_leg(ctx: _Context, leg: _Leg) -> None:
    # A link context is complete at 3 legs and again at 5; growing past a 3-leg
    # finalize must drop the cached verdict so the 5-leg verifier reruns (else
    # LINK_T R4 middle-set / LINK_SE promotion are never re-checked).
    ctx.legs.append(leg)
    if ctx.final_kind is not None:
        ctx.final_kind = None
        ctx.rules_log = []


def _maybe_finalize_parent(parent_ctx: _Context, mode: ScaleMode) -> bool:
    # True keeps a still-growing parent; False ⇒ complete-but-rejected, caller MUST roll back the append.
    if not parent_ctx.is_complete or parent_ctx.final_kind is not None:
        return True
    return _run_and_cache_verifier(parent_ctx, mode)
