"""Projects the parser's private `_Leg`s onto the public wave types.

Low module (imports only engine.types + parser.types) so both the hot beam loop —
which feeds verifiers — and the output tree builders can share it without cycling.

`flatten_linkwave` is the [G,L,G,L,G] layout, and it lives here because it used to
live in two places: the verifier input builder and the output tree walked the same
alternation, allocated the same LinkSets, and drifted apart with only a comment
holding them together. They differ in how a node is built, nothing more.
"""

from __future__ import annotations

from collections.abc import Callable

from engine.parser.types import _Leg
from engine.types import LinkSet, Segment, WaveNode

__all__ = ["flatten_linkwave", "leg_to_wavenode", "legs_to_segments"]

MakeNode = Callable[[_Leg], WaveNode]


def legs_to_segments(legs: list[_Leg]) -> list[Segment]:
    return [Segment(start=lg.span_start, end=lg.span_end) for lg in legs]


def leg_to_wavenode(leg: _Leg) -> WaveNode:
    if leg.pattern_kind is None or not leg.sub_legs:
        seg = Segment(start=leg.span_start, end=leg.span_end)
        return WaveNode(
            role=leg.role,
            pattern_kind=None,
            segments=[seg],
            span_start=leg.span_start,
            span_end=leg.span_end,
        )
    return WaveNode(
        role=leg.role,
        pattern_kind=leg.pattern_kind,
        segments=[Segment(start=lg.span_start, end=lg.span_end) for lg in leg.sub_legs],
        span_start=leg.span_start,
        span_end=leg.span_end,
    )


def flatten_linkwave(
    legs: list[_Leg],
    make_node: MakeNode,
) -> tuple[list[WaveNode], list[LinkSet], list[Segment]]:
    """[G,L,G,L,G] → (children, sets, links).

    Even legs are sets — a verified one expands into its sub-legs and contributes a
    LinkSet spanning them. Odd legs are the links between them. `links` is empty for
    a 1-leg wave and is ignored by the output tree, which only needs children + sets.
    """
    children: list[WaveNode] = []
    sets: list[LinkSet] = []
    links: list[Segment] = []
    for i, lg in enumerate(legs):
        if i % 2 == 0:
            if lg.pattern_kind is None or not lg.sub_legs:
                children.append(make_node(lg))
                continue
            start = len(children)
            for sub in lg.sub_legs:
                children.append(make_node(sub))
            sets.append(
                LinkSet(
                    pattern_kind=lg.pattern_kind,
                    leg_start=start,
                    leg_end=len(children) - 1,
                )
            )
        else:
            children.append(make_node(lg))
            links.append(Segment(start=lg.span_start, end=lg.span_end))
    return children, sets, links
