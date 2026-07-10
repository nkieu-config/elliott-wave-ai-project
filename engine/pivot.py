from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from engine.constants import (
    MIN_BARS_BETWEEN_DEFAULT,
    ZIGZAG_ATR_FLOOR_DEFAULT,
    ZIGZAG_ATR_MULTIPLIER_DEFAULT,
    ZIGZAG_ATR_PERIOD_DEFAULT,
)
from engine.types import Bar, Pivot, PivotKind, TrendDir

__all__ = [
    "MIN_BARS_BETWEEN_DEFAULT",
    "ZIGZAG_ATR_FLOOR_DEFAULT",
    "ZIGZAG_ATR_MULTIPLIER_DEFAULT",
    "ZIGZAG_ATR_PERIOD_DEFAULT",
    "compute_zigzag_pivots_atr",
    "enforce_min_bars",
]


def _lowest_low_idx(bars: list[Bar], after_idx: int, end_idx: int) -> int:
    # Lowest low over (after_idx, end_idx]; falls back to end_idx for an outside-bar
    # fire where the new high and the reversal land on the same bar.
    lo = end_idx
    for j in range(after_idx + 1, end_idx + 1):
        if bars[j].low < bars[lo].low:
            lo = j
    return lo


def _highest_high_idx(bars: list[Bar], after_idx: int, end_idx: int) -> int:
    hi = end_idx
    for j in range(after_idx + 1, end_idx + 1):
        if bars[j].high > bars[hi].high:
            hi = j
    return hi


def _zigzag_core(bars: list[Bar], threshold_for: Callable[[int], float]) -> list[Pivot]:
    if len(bars) < 2:
        return []

    pivots: list[Pivot] = []

    # Bootstrap: first threshold break fixes the OPPOSITE extreme as pivot 0.
    direction: TrendDir | None = None
    extreme_high = bars[0].high
    extreme_high_idx = 0
    extreme_low = bars[0].low
    extreme_low_idx = 0

    for i in range(1, len(bars)):
        b = bars[i]
        threshold = threshold_for(i)

        if direction is None:
            # Outside-bar both-ways break: pick larger excess.
            up_target = extreme_low * (1.0 + threshold)
            down_target = extreme_high * (1.0 - threshold)
            up_fires = b.high >= up_target
            down_fires = b.low <= down_target

            if up_fires and down_fires:
                up_excess = b.high - up_target
                down_excess = down_target - b.low
                if up_excess >= down_excess:
                    down_fires = False
                else:
                    up_fires = False

            if up_fires:
                pivots.append(
                    _make_pivot(len(pivots), bars[extreme_low_idx], "low", extreme_low_idx)
                )
                direction = "up"
                extreme_high_idx = _highest_high_idx(bars, extreme_low_idx, i)
                extreme_high = bars[extreme_high_idx].high
            elif down_fires:
                pivots.append(
                    _make_pivot(len(pivots), bars[extreme_high_idx], "high", extreme_high_idx)
                )
                direction = "down"
                extreme_low_idx = _lowest_low_idx(bars, extreme_high_idx, i)
                extreme_low = bars[extreme_low_idx].low
            else:
                if b.high > extreme_high:
                    extreme_high = b.high
                    extreme_high_idx = i
                if b.low < extreme_low:
                    extreme_low = b.low
                    extreme_low_idx = i

        elif direction == "up":
            # Two ifs (not if/elif): outside-bar reversal emits new high as pivot at bar i.
            if b.high > extreme_high:
                extreme_high = b.high
                extreme_high_idx = i
            if b.low <= extreme_high * (1.0 - threshold):
                pivots.append(
                    _make_pivot(len(pivots), bars[extreme_high_idx], "high", extreme_high_idx)
                )
                direction = "down"
                # Firing bar isn't necessarily the deepest retracement low: a shrinking
                # per-bar threshold can fire on a shallow late low while an earlier
                # deeper low never tripped its (larger) threshold — take the true min.
                extreme_low_idx = _lowest_low_idx(bars, extreme_high_idx, i)
                extreme_low = bars[extreme_low_idx].low

        else:  # direction == "down"
            if b.low < extreme_low:
                extreme_low = b.low
                extreme_low_idx = i
            if b.high >= extreme_low * (1.0 + threshold):
                pivots.append(
                    _make_pivot(len(pivots), bars[extreme_low_idx], "low", extreme_low_idx)
                )
                direction = "up"
                extreme_high_idx = _highest_high_idx(bars, extreme_low_idx, i)
                extreme_high = bars[extreme_high_idx].high

    if direction == "up":
        pivots.append(_make_pivot(len(pivots), bars[extreme_high_idx], "high", extreme_high_idx))
    elif direction == "down":
        pivots.append(_make_pivot(len(pivots), bars[extreme_low_idx], "low", extreme_low_idx))

    return pivots


def _rolling_sma(values: list[float], period: int) -> list[float]:
    out: list[float] = []
    rolling_sum = 0.0
    for i, v in enumerate(values):
        rolling_sum += v
        if i >= period:
            rolling_sum -= values[i - period]
        denom = min(i + 1, period)
        out.append(rolling_sum / denom)
    return out


def _compute_atr(bars: list[Bar], period: int) -> list[float]:
    # Causal: ATR[i] uses only bars[0..i]; TR[0] = high-low (no prev_close).
    if period < 1:
        raise ValueError(f"atr_period must be >= 1, got {period}")
    if not bars:
        return []

    tr: list[float] = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        tr.append(
            max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - prev_close),
                abs(bars[i].low - prev_close),
            )
        )

    return _rolling_sma(tr, period)


def _assert_time_sorted(bars: list[Bar]) -> None:
    for i in range(1, len(bars)):
        if bars[i].time <= bars[i - 1].time:
            raise ValueError(
                "bars must be strictly ascending by time; "
                f"bars[{i - 1}].time={bars[i - 1].time} >= "
                f"bars[{i}].time={bars[i].time}"
            )


def compute_zigzag_pivots_atr(
    bars: list[Bar],
    atr_period: int = ZIGZAG_ATR_PERIOD_DEFAULT,
    atr_multiplier: float = ZIGZAG_ATR_MULTIPLIER_DEFAULT,
    floor_threshold: float = ZIGZAG_ATR_FLOOR_DEFAULT,
) -> list[Pivot]:
    """Turn bars into alternating high/low pivots, reversal threshold scaled per-bar by ATR."""
    # threshold(i) = max(atr_multiplier * ATR(period)[i] / close[i], floor_threshold)
    # floor guards calm regimes (ATR→0); default 10% weekly.
    if len(bars) < 2:
        return []
    _assert_time_sorted(bars)

    atr_values = _compute_atr(bars, atr_period)

    def threshold_for(i: int) -> float:
        close = bars[i].close
        if close <= 0.0:
            return floor_threshold
        return max(atr_multiplier * atr_values[i] / close, floor_threshold)

    return _zigzag_core(bars, threshold_for)


def _make_pivot(index: int, bar: Bar, kind: PivotKind, bar_idx: int) -> Pivot:
    price = bar.high if kind == "high" else bar.low
    return Pivot(
        index=index,
        time=bar.time,
        price=price,
        kind=kind,
        bar_index=bar_idx,
    )


def enforce_min_bars(
    pivots: list[Pivot],
    min_bars: int = MIN_BARS_BETWEEN_DEFAULT,
) -> list[Pivot]:
    # Loop until stable: drop right pivot of too-short pair, collapse same-kind adjacents.
    if min_bars <= 1 or len(pivots) <= 1:
        return list(pivots)

    work = list(pivots)
    while True:
        idx = -1
        for i in range(len(work) - 1):
            if work[i + 1].bar_index - work[i].bar_index >= min_bars:
                continue
            idx = i
            break
        if idx < 0:
            break

        del work[idx + 1]

        j = max(idx - 1, 0)
        while j + 1 < len(work):
            if work[j].kind != work[j + 1].kind:
                j += 1
                continue
            keep_left = (work[j].kind == "high" and work[j].price >= work[j + 1].price) or (
                work[j].kind == "low" and work[j].price <= work[j + 1].price
            )
            if keep_left:
                del work[j + 1]
            else:
                del work[j]
                if j > 0:
                    j -= 1

    return [replace(p, index=i) for i, p in enumerate(work)]
