from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial

import pytest

from engine.types import PatternKind, Pivot, Segment
from engine.verifiers import verify_5wave_trend
from tests.fixtures import build_5w_trend_segments, make_segments

_trend_up = build_5w_trend_segments
_trend_down = partial(build_5w_trend_segments, trend_dir="down")


@pytest.mark.parametrize(
    "builder, lengths, expected",
    [
        (_trend_up, (30, 15, 60, 20, 45), PatternKind.FIVE_TREND_S3_LONGEST),
        (_trend_up, (80, 30, 60, 25, 40), PatternKind.FIVE_TREND_S1_LONGEST),
        (_trend_up, (40, 20, 50, 30, 100), PatternKind.FIVE_TREND_S5_LONGEST),
        (_trend_up, (50, 20, 50, 25, 50), PatternKind.FIVE_TREND_EQUAL_PUSH),
        (_trend_up, (50, 20, 51, 25, 49), PatternKind.FIVE_TREND_EQUAL_PUSH),
        (_trend_up, (30, 15, 60, 40, 20), PatternKind.FIVE_TREND_S5_SHORTER),
        (_trend_up, (40, 15, 60, 50, 20), PatternKind.FIVE_TREND_S5_SHORTER),
        (_trend_down, (30, 15, 60, 20, 45), PatternKind.FIVE_TREND_S3_LONGEST),
    ],
    ids=[
        "s3_longest",
        "s1_longest",
        "s5_longest",
        "equal_push_within_5pct",
        "equal_push_just_within_tolerance",
        "s5_shorter_requires_s3_longest",
        "boundary_s5_at_38_2_pct",
        "works_for_down_trend",
    ],
)
def test_trend_kind_classification(builder, lengths, expected) -> None:
    segs = builder(*lengths)
    result = verify_5wave_trend(segs, "linear")
    assert result is not None
    assert result[0] == expected


def test_walk_through_s3_longest_all_rules_pass() -> None:
    segs = _trend_up(30, 15, 60, 20, 45)
    result = verify_5wave_trend(segs, "linear")
    assert result is not None
    kind, rules = result
    assert kind == PatternKind.FIVE_TREND_S3_LONGEST
    assert all(r.passed for r in rules)


@pytest.mark.parametrize(
    "lengths",
    [
        (80, 15, 60, 40, 20),
        (50, 30, 20, 15, 40),
        (80, 20, 30, 15, 100),
        (30, 50, 100, 30, 40),
        (40, 20, 60, 70, 30),
        (40, 20, 80, 50, 15),
    ],
    ids=[
        "s5_shorter_rejected_when_s3_not_longest",
        "s3_lt_s2",
        "s3_shortest_among_pushes",
        "s2_gt_s1",
        "s4_gt_s3",
        "s5_below_38_2_pct_of_s4",
    ],
)
def test_trend_rejects(lengths) -> None:
    segs = _trend_up(*lengths)
    assert verify_5wave_trend(segs, "linear") is None


def test_reject_not_5_segments() -> None:
    segs = make_segments([100, 110, 105, 120])
    assert verify_5wave_trend(segs, "linear") is None


@pytest.mark.parametrize("mode", ["linear", "log"])
def test_works_in_both_modes(mode: str) -> None:
    segs = _trend_up(30, 15, 60, 20, 45)
    result = verify_5wave_trend(segs, mode)  # type: ignore[arg-type]
    assert result is not None


def test_log_mode_flips_classification_for_exponential_prices() -> None:
    segs = make_segments([100.0, 150.0, 130.0, 180.0, 160.0, 210.0])

    res_lin = verify_5wave_trend(segs, "linear")
    res_log = verify_5wave_trend(segs, "log")

    assert res_lin is not None
    assert res_log is not None
    assert res_lin[0] == PatternKind.FIVE_TREND_EQUAL_PUSH
    assert res_log[0] == PatternKind.FIVE_TREND_S1_LONGEST


def test_r5_records_s3_to_min_other_push_ratio() -> None:
    segs = _trend_up(30, 15, 60, 20, 45)
    result = verify_5wave_trend(segs, "linear")
    assert result is not None
    _, rules = result
    r5 = next(r for r in rules if r.id == "5wt.r5.s3_not_shortest")
    assert r5.passed is True
    assert r5.measured is not None
    assert r5.measured == pytest.approx(2.0)


def test_r5_measured_below_1_when_s3_shorter_than_one_other_push() -> None:
    segs = _trend_up(80, 30, 60, 25, 40)
    result = verify_5wave_trend(segs, "linear")
    assert result is not None
    _, rules = result
    r5 = next(r for r in rules if r.id == "5wt.r5.s3_not_shortest")
    assert r5.passed is True
    assert r5.measured == pytest.approx(1.5)


# ── r2/r3 push-pull rules: r1's alternation guard means these never fail through the
# public verify(), so pin their logic directly with a non-alternating leg set. ──


def _seg(i: int, p0: float, p1: float) -> Segment:
    base = datetime(2024, 1, 1)
    a = Pivot(index=i, time=base + timedelta(weeks=i), price=p0, kind="low", bar_index=i)
    b = Pivot(index=i + 1, time=base + timedelta(weeks=i + 1), price=p1, kind="high", bar_index=i + 1)
    return Segment(start=a, end=b)


def test_r2_rejects_odd_leg_that_is_not_a_push() -> None:
    from engine.verifiers.trend import _check_r2_odd_are_push
    # trend=up (s1 up); s3 goes DOWN — an odd leg that isn't a push.
    segs = [_seg(0, 100, 130), _seg(1, 130, 115), _seg(2, 115, 105),
            _seg(3, 105, 120), _seg(4, 120, 160)]
    [r] = _check_r2_odd_are_push(segs, "linear")
    assert r.id == "5wt.r2.odd_are_push"
    assert r.passed is False


def test_r2_passes_when_all_odd_legs_push() -> None:
    from engine.verifiers.trend import _check_r2_odd_are_push
    segs = [_seg(0, 100, 130), _seg(1, 130, 115), _seg(2, 115, 175),
            _seg(3, 175, 155), _seg(4, 155, 200)]
    [r] = _check_r2_odd_are_push(segs, "linear")
    assert r.passed is True


def test_r3_rejects_even_leg_that_is_not_a_pull() -> None:
    from engine.verifiers.trend import _check_r3_even_are_pull
    # trend=up (s1 up); s2 goes UP — an even leg that isn't a pull.
    segs = [_seg(0, 100, 130), _seg(1, 130, 145), _seg(2, 145, 120),
            _seg(3, 120, 160), _seg(4, 160, 140)]
    [r] = _check_r3_even_are_pull(segs, "linear")
    assert r.id == "5wt.r3.even_are_pull"
    assert r.passed is False


def test_r3_passes_when_all_even_legs_pull() -> None:
    from engine.verifiers.trend import _check_r3_even_are_pull
    segs = [_seg(0, 100, 130), _seg(1, 130, 115), _seg(2, 115, 175),
            _seg(3, 175, 155), _seg(4, 155, 200)]
    [r] = _check_r3_even_are_pull(segs, "linear")
    assert r.passed is True
