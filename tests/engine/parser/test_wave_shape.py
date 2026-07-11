"""The [G,L,G,L,G] walk, which used to be written twice and tested zero times.

The verifier input and the output tree both flatten a linkwave's legs; they differ
only in the node factory. Pinning the walk here pins both.
"""

from __future__ import annotations

import pytest

from engine.parser.types import _Leg
from engine.parser.wave_shape import flatten_linkwave, leg_to_wavenode, legs_to_segments
from engine.types import PatternKind, WaveRole
from tests.engine.parser._builders import piv


def _leg(i: int, role: WaveRole = WaveRole.S1, subs: list[_Leg] | None = None,
         kind: PatternKind | None = None) -> _Leg:
    lg = _Leg(role=role, span_start=piv(2 * i, 100.0 + i, "low"),
              span_end=piv(2 * i + 1, 110.0 + i, "high"))
    if subs is not None:
        lg.sub_legs = subs
    if kind is not None:
        lg.pattern_kind = kind
    return lg


def _verified_set(i: int, n_subs: int) -> _Leg:
    subs = [_leg(100 * i + j) for j in range(n_subs)]
    return _leg(i, role=WaveRole.SET_1, subs=subs, kind=PatternKind.THREE_NORMAL)


def test_unverified_set_leg_stays_one_node_and_makes_no_linkset() -> None:
    children, sets, links = flatten_linkwave([_leg(0)], leg_to_wavenode)

    assert len(children) == 1
    assert sets == []
    assert links == []


def test_verified_set_expands_into_its_sub_legs_and_spans_them() -> None:
    children, sets, links = flatten_linkwave([_verified_set(0, 3)], leg_to_wavenode)

    assert len(children) == 3, "a verified set contributes its sub-legs, not itself"
    assert len(sets) == 1
    assert (sets[0].leg_start, sets[0].leg_end) == (0, 2)
    assert sets[0].pattern_kind is PatternKind.THREE_NORMAL
    assert links == []


def test_odd_legs_are_links_and_are_not_expanded() -> None:
    legs = [_verified_set(0, 3), _leg(1, role=WaveRole.LINK), _verified_set(2, 3)]
    children, sets, links = flatten_linkwave(legs, leg_to_wavenode)

    # 3 sub-legs, the link itself, 3 more sub-legs.
    assert len(children) == 7
    assert [(s.leg_start, s.leg_end) for s in sets] == [(0, 2), (4, 6)]
    assert len(links) == 1, "only the odd (link) legs contribute link segments"
    assert links[0].start.index == legs[1].span_start.index


def test_linkset_indices_address_the_children_list() -> None:
    # The contract the verifiers rely on: leg_start/leg_end index into `children`.
    legs = [_verified_set(0, 2), _leg(1, role=WaveRole.LINK), _verified_set(2, 3)]
    children, sets, _ = flatten_linkwave(legs, leg_to_wavenode)

    for s in sets:
        assert 0 <= s.leg_start <= s.leg_end < len(children)
    first, second = sets
    assert children[first.leg_start : first.leg_end + 1] == children[0:2]
    assert children[second.leg_start : second.leg_end + 1] == children[3:6]


def test_verifier_input_and_output_tree_agree_on_the_shape() -> None:
    # These two were separate implementations of this walk. The verifier grades a
    # linkwave on one, the user sees the other; if their children/LinkSets ever
    # disagree, the count on screen is not the count that was verified.
    from engine.parser.output.linkwave_flattening import _flatten_linkwave_children

    legs = [_verified_set(0, 3), _leg(1, role=WaveRole.LINK), _verified_set(2, 2)]
    parent = leg_to_wavenode(_leg(99))

    verifier_children, verifier_sets, _ = flatten_linkwave(legs, leg_to_wavenode)
    tree_children, tree_sets = _flatten_linkwave_children(legs, parent, nesting_level=1)

    assert len(verifier_children) == len(tree_children)
    assert [(s.pattern_kind, s.leg_start, s.leg_end) for s in verifier_sets] == [
        (s.pattern_kind, s.leg_start, s.leg_end) for s in tree_sets
    ]
    assert [(n.span_start.index, n.span_end.index) for n in verifier_children] == [
        (n.span_start.index, n.span_end.index) for n in tree_children
    ]
    # The tree's nodes are the parented ones — that is the only difference.
    assert all(n.parent is parent for n in tree_children)
    assert all(n.parent is None for n in verifier_children)


@pytest.mark.parametrize("n_legs", [0, 1, 2, 3, 4, 5])
def test_children_and_links_stay_consistent_for_every_leg_count(n_legs: int) -> None:
    legs = [
        _verified_set(i, 3) if i % 2 == 0 else _leg(i, role=WaveRole.LINK)
        for i in range(n_legs)
    ]
    children, sets, links = flatten_linkwave(legs, leg_to_wavenode)

    assert len(sets) == (n_legs + 1) // 2, "one LinkSet per verified even leg"
    assert len(links) == n_legs // 2, "one link segment per odd leg"
    assert len(children) == 3 * len(sets) + len(links)


def test_legs_to_segments_preserves_span_and_order() -> None:
    legs = [_leg(0), _leg(1), _leg(2)]
    segs = legs_to_segments(legs)

    assert [(s.start.index, s.end.index) for s in segs] == [
        (lg.span_start.index, lg.span_end.index) for lg in legs
    ]


def test_leg_to_wavenode_carries_sub_legs_as_segments_when_verified() -> None:
    plain = leg_to_wavenode(_leg(0))
    assert plain.pattern_kind is None
    assert len(plain.segments) == 1

    verified = leg_to_wavenode(_verified_set(0, 3))
    assert verified.pattern_kind is PatternKind.THREE_NORMAL
    assert len(verified.segments) == 3, "a verified leg's segments are its sub-legs"
