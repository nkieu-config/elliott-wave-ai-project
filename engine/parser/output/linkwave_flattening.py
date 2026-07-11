from __future__ import annotations

from engine.types import LinkSet, NestingLevel, WaveNode, WaveRole

from ..types import _Context, _Leg
from ..wave_shape import flatten_linkwave

__all__ = [
    "_flatten_linkwave_children",
    "_merge_open_into_linkwave",
]


def _flatten_linkwave_children(
    set_and_link_legs: list[_Leg],
    parent: WaveNode,
    nesting_level: NestingLevel,
) -> tuple[list[WaveNode], list[LinkSet]]:
    from .tree_builders import _leg_to_wavenode_with_parent

    # Same walk the verifier input uses — the tree just wants parented nodes, and has
    # no use for the link segments.
    flat, sets, _links = flatten_linkwave(
        set_and_link_legs,
        lambda lg: _leg_to_wavenode_with_parent(lg, parent, nesting_level),
    )
    return flat, sets


def _merge_open_into_linkwave(
    parent: WaveNode,
    stack: list[_Context],
    start_idx: int,
) -> None:
    from .open_subtree import _build_open_subcontext_chain
    from .tree_builders import _leg_to_wavenode_with_parent

    if start_idx >= len(stack):
        return
    ctx = stack[start_idx]
    parent_role = ctx.parent_role

    if parent_role in (WaveRole.SET_1, WaveRole.SET_2, WaveRole.SET_3):
        for sub in ctx.legs:
            parent.children.append(
                _leg_to_wavenode_with_parent(
                    sub,
                    parent,
                    parent.nesting_level + 1,
                )
            )
        if start_idx + 1 < len(stack):
            deeper = _build_open_subcontext_chain(stack, start_idx + 1, parent)
            if deeper is not None:
                parent.children.append(deeper)
        return

    if parent_role == WaveRole.LINK:
        deeper = _build_open_subcontext_chain(stack, start_idx, parent)
        if deeper is not None:
            parent.children.append(deeper)
