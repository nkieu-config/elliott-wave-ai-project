from __future__ import annotations

from engine.adaptive import (
    Family,
    allowed_sub_families,
    expected_direction,
)
from engine.degree import gann_band_ok
from engine.parser.engine._helpers import _seg_to_leg
from engine.parser.engine.closing import _append_leg, _close_top_into_parent, _try_finalize
from engine.parser.families import (
    KNOWN_SUB_FAMILIES,
    LINK_INNER_SET1_FAMILIES,
    incremental_ok,
    open_pregate_ok,
)
from engine.parser.gates import _bar_span
from engine.parser.types import (
    MAX_RECURSION_DEPTH,
    _Context,
    _Hypothesis,
    _Leg,
)
from engine.types import ScaleMode, Segment, WaveRole


def _can_extend_with_segment(ctx: _Context, seg: Segment, mode: ScaleMode) -> bool:
    role = ctx.next_role
    if role is None:
        return False
    # Link-Wave: extend only at link (odd) positions, never at set position.
    if ctx.struct.is_link and ctx.is_set_position:
        return False
    expected = expected_direction(ctx.family, role, ctx.trend_dir)
    if seg.direction != expected:
        return False
    leg_len = _Leg(role=role, span_start=seg.start, span_end=seg.end).length(mode)
    leg_bars = _bar_span(seg.start, seg.end)
    return incremental_ok(ctx, role, leg_len, mode, leg_bars=leg_bars)


def _option_a_extend(
    h: _Hypothesis,
    seg: Segment,
    mode: ScaleMode,
) -> _Hypothesis | None:
    ctx = h.top
    if not _can_extend_with_segment(ctx, seg, mode):
        return None
    new_leg = _seg_to_leg(seg, ctx.next_role)  # type: ignore[arg-type]
    # Same-degree gate pp.91-95.
    if not gann_band_ok(ctx, new_leg, mode):
        return None
    h2 = h.clone()
    _append_leg(h2.top, new_leg)
    if h2.top.is_complete and not _try_finalize(h2.top, mode):
        return None
    return h2


def _option_b_open_subwave(
    h: _Hypothesis,
    seg: Segment,
    mode: ScaleMode,
) -> list[_Hypothesis]:
    # LINK_SE not seeded — subsumed by LINK_S (verifier promotes by link size).
    if h.depth >= MAX_RECURSION_DEPTH:
        return []
    ctx = h.top
    role = ctx.next_role
    if role is None:
        return []

    if ctx.legs:
        expected_dir = expected_direction(ctx.family, role, ctx.trend_dir)
        if seg.direction != expected_dir:
            return []

    if not open_pregate_ok(ctx, role, seg, mode):
        return []

    out: list[_Hypothesis] = []
    for sub_family in allowed_sub_families(ctx.family, role):
        if sub_family in KNOWN_SUB_FAMILIES:
            out.append(_bootstrap_simple_subwave(h, seg, role, sub_family))
        elif sub_family in LINK_INNER_SET1_FAMILIES:
            out.extend(_bootstrap_link_subwave(h, seg, role, sub_family))
    return out


def _bootstrap_simple_subwave(
    h: _Hypothesis,
    seg: Segment,
    parent_role: WaveRole,
    sub_family: Family,
) -> _Hypothesis:
    h2 = h.clone()
    h2.context_stack.append(
        _Context(
            family=sub_family,
            legs=[_seg_to_leg(seg, WaveRole.S1)],
            parent_role=parent_role,
        )
    )
    return h2


def _bootstrap_link_subwave(
    h: _Hypothesis,
    seg: Segment,
    parent_role: WaveRole,
    sub_family: Family,
) -> list[_Hypothesis]:
    # Mirrors seed_hypotheses root-level Link bootstrap; needs 2 new contexts.
    if h.depth + 2 > MAX_RECURSION_DEPTH:
        return []
    out: list[_Hypothesis] = []
    for inner_fam in LINK_INNER_SET1_FAMILIES[sub_family]:
        h2 = h.clone()
        h2.context_stack.append(
            _Context(
                family=sub_family,
                legs=[],
                parent_role=parent_role,
            )
        )
        h2.context_stack.append(
            _Context(
                family=inner_fam,
                legs=[_seg_to_leg(seg, WaveRole.S1)],
                parent_role=WaveRole.SET_1,
            )
        )
        out.append(h2)
    return out


def _option_c_close_then_branch(
    h: _Hypothesis,
    seg: Segment,
    mode: ScaleMode,
) -> list[_Hypothesis]:
    if h.depth < 2 or not h.top.is_complete:
        return []
    if not _try_finalize(h.top, mode):
        return []
    h2 = h.clone()
    if not _close_top_into_parent(h2, mode):
        return []
    return _branch(h2, seg, mode)


def _branch(h: _Hypothesis, seg: Segment, mode: ScaleMode) -> list[_Hypothesis]:
    next_states: list[_Hypothesis] = []

    a = _option_a_extend(h, seg, mode)
    if a is not None:
        next_states.append(a)

    if h.top.next_role is not None:
        next_states.extend(_option_b_open_subwave(h, seg, mode))

    next_states.extend(_option_c_close_then_branch(h, seg, mode))

    return next_states
