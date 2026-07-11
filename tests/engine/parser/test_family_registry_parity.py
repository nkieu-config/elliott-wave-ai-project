"""Behaviour oracle for the PatternFamily registry refactor.

Pins per-family structural dispatch, degree axis, and seed family sets as explicit
CONTRACT literals so registry changes can't drift unnoticed. Covers every `Family`,
including verify-only LINK_SE.
"""
from __future__ import annotations

from datetime import datetime
from typing import get_args

import pytest

from engine.adaptive import Family
from engine.degree.measure import axis_for_family
from engine.parser.families import (
    KNOWN_SUB_FAMILIES,
    LINK_INNER_SET1_FAMILIES,
    ROOT_FAMILIES,
)
from engine.parser.types import LINK_FAMILIES, _Context, _Leg
from engine.types import Pivot, WaveRole

ALL_FAMILIES = get_args(Family)


def _leg(i: int) -> _Leg:
    p0 = Pivot(index=2 * i, time=datetime(2020, 1, 1), price=100.0 + i, kind="low", bar_index=2 * i)
    p1 = Pivot(index=2 * i + 1, time=datetime(2020, 1, 1), price=101.0 + i, kind="high", bar_index=2 * i + 1)
    return _Leg(role=WaveRole.S1, span_start=p0, span_end=p1)


def _ctx(family: str, n_legs: int) -> _Context:
    return _Context(family=family, legs=[_leg(i) for i in range(n_legs)])


# (max_legs, min_legs_to_complete, is_link)
_STRUCT = {
    "3W": (3, 3, False),
    "5W_TREND": (5, 5, False),
    "5W_SIDEWAY": (5, 5, False),
    "LINK_T": (5, 3, True),
    "LINK_S": (5, 3, True),
    "LINK_SE": (5, 3, True),
}

_SET_SLOTS = (WaveRole.SET_1, WaveRole.SET_2, WaveRole.SET_3)
_ROLE_SEQ = (WaveRole.S1, WaveRole.S2, WaveRole.S3, WaveRole.S4, WaveRole.S5)


def _expected_next_role(family: str, n: int) -> WaveRole | None:
    max_legs, _, is_link = _STRUCT[family]
    if is_link:
        if n >= 5:
            return None
        return _SET_SLOTS[n // 2] if n % 2 == 0 else WaveRole.LINK
    return None if n >= max_legs else _ROLE_SEQ[n]


def _expected_is_complete(family: str, n: int) -> bool:
    max_legs, _, is_link = _STRUCT[family]
    return n in (3, 5) if is_link else n >= max_legs


def test_registry_covers_every_family():
    assert set(_STRUCT) == set(ALL_FAMILIES)


def test_family_specs_cover_every_family():
    # Enforces the "add a family in one place" contract: a new Family literal without a
    # FamilySpec fails here rather than silently mis-dispatching.
    from engine.parser.families import FAMILY_SPECS

    assert set(FAMILY_SPECS) == set(ALL_FAMILIES)


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_max_and_min_legs(family):
    max_legs, min_legs, _ = _STRUCT[family]
    ctx = _ctx(family, 0)
    assert ctx.max_legs == max_legs
    assert ctx.min_legs_to_complete == min_legs


@pytest.mark.parametrize("family", ALL_FAMILIES)
@pytest.mark.parametrize("n", range(7))
def test_is_complete_and_next_role(family, n):
    ctx = _ctx(family, n)
    assert ctx.is_complete is _expected_is_complete(family, n)
    assert ctx.next_role == _expected_next_role(family, n)


@pytest.mark.parametrize("family", ALL_FAMILIES)
@pytest.mark.parametrize("n", range(7))
def test_is_set_position(family, n):
    _, _, is_link = _STRUCT[family]
    expected = is_link and n % 2 == 0
    assert _ctx(family, n).is_set_position is expected


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_axis_for_family_time_vs_price(family):
    expected = "time" if family in ("5W_TREND", "LINK_T") else "price"
    assert axis_for_family(family) == expected


def test_seed_family_sets_unchanged():
    assert ROOT_FAMILIES == ("5W_TREND", "5W_SIDEWAY", "3W", "LINK_T", "LINK_S")
    assert {"5W_TREND", "5W_SIDEWAY", "3W"} == KNOWN_SUB_FAMILIES
    assert frozenset({"LINK_T", "LINK_S", "LINK_SE"}) == LINK_FAMILIES
    assert LINK_INNER_SET1_FAMILIES == {"LINK_T": ("3W",), "LINK_S": ("3W", "5W_SIDEWAY")}
