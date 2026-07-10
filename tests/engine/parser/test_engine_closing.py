from __future__ import annotations

import uuid
from datetime import datetime

from engine.parser.engine import closing
from engine.parser.engine.closing import _can_close_top, _close_top_into_parent
from engine.parser.types import _Context, _Hypothesis, _Leg
from engine.types import Pivot


def _make_hypothesis(*contexts: _Context) -> _Hypothesis:
    return _Hypothesis(id=str(uuid.uuid4()), context_stack=list(contexts))


def _leg(role: str = "s1") -> _Leg:
    return _Leg(
        role=role,  # type: ignore[arg-type]
        span_start=Pivot(0, datetime(2024, 1, 1), 100.0, "low"),
        span_end=Pivot(1, datetime(2024, 1, 1), 110.0, "high"),
    )


def test_can_close_top_rejects_depth_1():
    ctx = _Context(family="3W", legs=[])
    h = _make_hypothesis(ctx)
    assert h.depth == 1
    assert _can_close_top(h) is False


def test_can_close_top_rejects_incomplete_top():
    parent_ctx = _Context(family="5W_TREND", legs=[])
    top_ctx = _Context(family="3W", legs=[])
    assert top_ctx.is_complete is False
    h = _make_hypothesis(parent_ctx, top_ctx)
    assert h.depth == 2
    assert _can_close_top(h) is False


def test_close_top_into_parent_rolls_back_when_finalize_rejects(monkeypatch):
    # Invariant: a leg appended to the parent must be popped (and the context kept)
    # when _maybe_finalize_parent rejects — otherwise the parser accrues a phantom leg.
    parent = _Context(family="5W_TREND", legs=[], parent_role=None)
    closed = _Context(family="3W", legs=[], parent_role="s1")
    h = _make_hypothesis(parent, closed)
    leg = _Leg(
        role="s1",
        span_start=Pivot(0, datetime(2024, 1, 1), 100.0, "low"),
        span_end=Pivot(1, datetime(2024, 1, 1), 110.0, "high"),
    )
    # All pre-finalize gates pass; only the final verifier rejects.
    monkeypatch.setattr(closing, "_can_close_top", lambda _h: True)
    monkeypatch.setattr(closing, "_kind_allowed_under_parent", lambda *a: True)
    monkeypatch.setattr(closing, "_build_closed_leg", lambda *a: leg)
    monkeypatch.setattr(closing, "_check_close_direction_and_ratio", lambda *a: True)
    monkeypatch.setattr(closing, "close_pregate_ok", lambda *a: True)
    monkeypatch.setattr(closing, "gann_band_ok", lambda *a: True)
    monkeypatch.setattr(closing, "_maybe_finalize_parent", lambda ctx, mode: False)

    assert _close_top_into_parent(h, "linear") is False
    assert parent.legs == []  # rolled back
    assert h.depth == 2  # context not popped


def test_append_leg_invalidates_stale_final_kind():
    # A link context is complete at 3 legs and again at 5; growing past the 3-leg
    # finalize must drop the cached verdict so the 5-leg verifier (e.g. LINK_T R4
    # middle-set / LINK_SE promotion) reruns instead of emitting the stale kind.
    from engine.parser.engine.closing import _append_leg
    from engine.types import PatternKind, RuleResult

    ctx = _Context(
        family="LINK_T",
        legs=[_leg(), _leg(), _leg()],
        final_kind=PatternKind.LINK_T,
        rules_log=[RuleResult("stale", True)],
    )
    _append_leg(ctx, _leg())
    assert len(ctx.legs) == 4
    assert ctx.final_kind is None
    assert ctx.rules_log == []


def test_append_leg_leaves_unfinalized_context_untouched():
    from engine.parser.engine.closing import _append_leg

    ctx = _Context(family="5W_TREND", legs=[_leg()])
    _append_leg(ctx, _leg())
    assert len(ctx.legs) == 2
    assert ctx.final_kind is None
