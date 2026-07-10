from __future__ import annotations

import random
from datetime import datetime

import pytest

from engine.pivot import compute_zigzag_pivots_atr
from engine.types import Bar
from tests.fixtures import make_bar as _bar
from tests.fixtures import make_flat_bar as _flat_bar


def _zigzag_fixed(bars: list[Bar], threshold: float) -> list:
    return compute_zigzag_pivots_atr(
        bars,
        atr_period=1,
        atr_multiplier=0.0,
        floor_threshold=threshold,
    )


def test_empty_input() -> None:
    assert _zigzag_fixed([], 0.10) == []
    assert _zigzag_fixed([_flat_bar(0, 100)], 0.10) == []


def test_simple_up_then_down() -> None:
    bars = [
        _flat_bar(0, 100),
        _flat_bar(1, 110),
        _flat_bar(2, 120),
        _flat_bar(3, 110),
        _flat_bar(4, 100),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    assert len(pivots) == 3
    assert pivots[0].kind == "low" and pivots[0].price == 100
    assert pivots[1].kind == "high" and pivots[1].price == 120
    assert pivots[2].kind == "low" and pivots[2].price == 100


def test_bar_index_tracked() -> None:
    bars = [
        _flat_bar(0, 100),
        _flat_bar(1, 120),
        _flat_bar(2, 100),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    assert pivots[0].bar_index == 0
    assert pivots[1].bar_index == 1
    assert pivots[2].bar_index == 2


def test_threshold_filters_small_moves() -> None:
    bars = [
        _flat_bar(0, 100),
        _flat_bar(1, 105),
        _flat_bar(2, 100),
        _flat_bar(3, 120),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    assert len(pivots) == 2
    assert pivots[0].kind == "low" and pivots[0].price == 100
    assert pivots[1].kind == "high" and pivots[1].price == 120


def test_alternating_high_low() -> None:
    bars = [
        _flat_bar(0, 100),
        _flat_bar(1, 130),
        _flat_bar(2, 110),
        _flat_bar(3, 140),
        _flat_bar(4, 120),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    kinds = [p.kind for p in pivots]
    for i in range(1, len(kinds)):
        assert kinds[i] != kinds[i - 1], f"Pivots at {i - 1},{i} both {kinds[i]}"


def test_uses_high_low_not_close() -> None:
    bars = [
        _flat_bar(0, 100),
        _bar(1, 100, 130, 95, 100),
        _flat_bar(2, 100),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    high_pivots = [p for p in pivots if p.kind == "high"]
    assert any(p.price == 130 for p in high_pivots)


@pytest.mark.parametrize("threshold", [0.05, 0.10, 0.15, 0.20])
def test_threshold_monotonic_count(threshold: float) -> None:
    rng = random.Random(42)
    prices = [100.0]
    for _ in range(100):
        prices.append(prices[-1] * (1 + rng.uniform(-0.05, 0.05)))

    bars = [_flat_bar(i, p) for i, p in enumerate(prices)]
    pivots = _zigzag_fixed(bars, threshold=threshold)
    for i in range(1, len(pivots)):
        assert pivots[i].kind != pivots[i - 1].kind


def test_outside_bar_in_uptrend_locks_in_high_pivot() -> None:
    bars = [
        _flat_bar(0, 80),
        _flat_bar(1, 100),
        _bar(2, 100, 120, 85, 100),
        _flat_bar(3, 115),
        _flat_bar(4, 118),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    got = [(p.bar_index, p.kind, p.price) for p in pivots]
    high_at_2 = next(
        (
            i
            for i, p in enumerate(pivots)
            if p.bar_index == 2 and p.kind == "high" and p.price == 120
        ),
        None,
    )
    assert high_at_2 is not None, f"expected high@bar 2 price 120; got {got}"
    assert high_at_2 < len(pivots) - 1, (
        f"high@2 must be emitted at bar 2 (not lingering as trailing extreme); got {got}"
    )


def test_outside_bar_in_downtrend_locks_in_low_pivot() -> None:
    bars = [
        _flat_bar(0, 100),
        _flat_bar(1, 80),
        _bar(2, 80, 95, 60, 80),
        _flat_bar(3, 65),
        _flat_bar(4, 62),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    got = [(p.bar_index, p.kind, p.price) for p in pivots]
    low_at_2 = next(
        (i for i, p in enumerate(pivots) if p.bar_index == 2 and p.kind == "low" and p.price == 60),
        None,
    )
    assert low_at_2 is not None, f"expected low@bar 2 price 60; got {got}"
    assert low_at_2 < len(pivots) - 1, (
        f"low@2 must be emitted at bar 2 (not lingering as trailing extreme); got {got}"
    )


def test_wide_range_bar_no_flip_when_low_above_threshold() -> None:
    bars = [
        _flat_bar(0, 80),
        _flat_bar(1, 100),
        _bar(2, 100, 120, 115, 120),
        _flat_bar(3, 130),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.10)
    got = [(p.bar_index, p.kind, p.price) for p in pivots]
    assert got == [(0, "low", 80), (3, "high", 130)], (
        f"expected [low@0=80, high@3=130] (no flip at bar 2); got {got}"
    )


def test_unsorted_bars_raise_value_error() -> None:
    bars = [
        _bar(2, 100, 110, 90, 105),
        _bar(1, 100, 110, 90, 105),
    ]
    with pytest.raises(ValueError, match="strictly ascending by time"):
        compute_zigzag_pivots_atr(bars)


def test_duplicate_timestamps_raise_value_error() -> None:
    same_t = datetime(2020, 1, 1)
    bars = [
        Bar(time=same_t, open=100, high=110, low=90, close=105),
        Bar(time=same_t, open=100, high=110, low=90, close=105),
    ]
    with pytest.raises(ValueError, match="strictly ascending by time"):
        compute_zigzag_pivots_atr(bars)


def test_bootstrap_outside_bar_picks_larger_excess_down() -> None:
    bars = [
        _bar(0, 95, 100, 90, 95),
        _bar(1, 95, 110, 50, 95),
    ]
    pivots = _zigzag_fixed(bars, threshold=0.20)
    assert pivots[0].kind == "high", (
        f"expected first pivot 'high' (down dominated); got {pivots[0].kind}"
    )
    assert pivots[0].bar_index == 0
    assert pivots[0].price == 100


def test_shrinking_threshold_keeps_true_swing_low() -> None:
    # A per-bar threshold that shrinks mid-retracement can fire on a shallow late low
    # (bar 4, low 82) while an earlier, deeper low (bar 3, low 80) never tripped its
    # larger threshold. The emitted low pivot must be the true swing low, not the
    # firing bar's.
    from engine.pivot import _zigzag_core

    bars = [
        _bar(0, 50, 51, 50, 50),
        _bar(1, 75, 100, 51, 100),
        _bar(2, 99, 100, 98, 99),
        _bar(3, 90, 100, 80, 90),
        _bar(4, 91, 100, 82, 91),
        _bar(5, 88, 95, 82, 88),
        _bar(6, 77, 95, 60, 77),
    ]
    thresholds = {3: 0.25, 4: 0.15}
    pivots = _zigzag_core(bars, lambda i: thresholds.get(i, 0.10))

    lows = [(p.bar_index, p.price) for p in pivots if p.kind == "low"]
    assert (3, 80.0) in lows
    assert (4, 82.0) not in lows
