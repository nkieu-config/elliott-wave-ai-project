from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine.types import LinkSet, PatternKind, Pivot, Segment, WaveNode, WaveRole
from engine.verifiers.link_t import _check_r9_link_time
from tests.engine.verifiers._link_helpers import (
    build_3w_group as _build_3w_group,
)
from tests.engine.verifiers._link_helpers import (
    call_verify_link_t as verify_link_t,
)
from tests.engine.verifiers._link_helpers import (
    link_segment,
)
from tests.fixtures import make_segments


def _link_segment(start_pivot: Pivot, end_price: float, weeks_after: int = 3) -> Segment:
    return link_segment(start_pivot, end_price, weeks=weeks_after)


def test_link_t_2_groups_valid() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=130, weeks_after=3)
    base_time = link.end.time
    base_bar = link.end.bar_index
    g2_segs = [
        Segment(
            start=Pivot(0, base_time, 130, "low", base_bar),
            end=Pivot(1, base_time + timedelta(weeks=1), 165, "high", base_bar + 1),
        ),
        Segment(
            start=Pivot(1, base_time + timedelta(weeks=1), 165, "high", base_bar + 1),
            end=Pivot(2, base_time + timedelta(weeks=2), 145, "low", base_bar + 2),
        ),
        Segment(
            start=Pivot(2, base_time + timedelta(weeks=2), 145, "low", base_bar + 2),
            end=Pivot(3, base_time + timedelta(weeks=3), 180, "high", base_bar + 3),
        ),
    ]
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=g2_segs[0].start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=g2_segs,
        span_end=g2_segs[-1].end,
    )

    result = verify_link_t([g1, g2], [link], "linear")
    assert result is not None
    kind, _ = result
    assert kind == PatternKind.LINK_T


def test_link_t_3_groups_with_last_longer() -> None:
    g1 = _build_3w_group([100, 120, 110, 130])
    link1 = _link_segment(g1.segments[-1].end, end_price=125)

    g2_segs = make_segments([125, 155, 140, 170])
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=g2_segs[0].start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=g2_segs,
        span_end=g2_segs[-1].end,
    )
    link2 = _link_segment(g2.segments[-1].end, end_price=160)

    g3_segs = make_segments([160, 175, 150, 200])
    g3 = WaveNode(
        role=WaveRole.SET_3,
        span_start=g3_segs[0].start,
        pattern_kind=PatternKind.THREE_S2_LONGER,
        segments=g3_segs,
        span_end=g3_segs[-1].end,
    )

    result = verify_link_t([g1, g2, g3], [link1, link2], "linear")
    assert result is not None
    assert result[0] == PatternKind.LINK_T


def test_reject_first_group_not_normal() -> None:
    g1 = _build_3w_group([100, 120, 90, 110], kind=PatternKind.THREE_S2_LONGER)
    link = _link_segment(g1.segments[-1].end, end_price=100)
    g2 = _build_3w_group([100, 130, 115, 140])
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_reject_set_that_is_not_3w() -> None:
    # r2 (all_3w): a 5-wave set can't appear in a trend linkage. Without a failing
    # fixture, deleting _check_r2_all_3w leaves the suite green.
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=130)
    g2 = _build_3w_group([130, 160, 145, 180], kind=PatternKind.FIVE_SIDEWAY_BALANCE)
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_reject_sets_with_divergent_trend() -> None:
    # r5 (same_trend): every set must share the linkage's trend direction — an
    # up set followed by a down set must be rejected.
    g1 = _build_3w_group([100, 130, 110, 140])  # net up
    link = _link_segment(g1.segments[-1].end, end_price=130)
    g2 = _build_3w_group([130, 105, 120, 95])  # net down
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_reject_middle_group_not_normal_in_3groups() -> None:
    g1 = _build_3w_group([100, 120, 110, 130])
    link1 = _link_segment(g1.segments[-1].end, end_price=125)
    g2 = _build_3w_group([125, 145, 115, 140], kind=PatternKind.THREE_S2_LONGER)
    link2 = _link_segment(g2.segments[-1].end, end_price=135)
    g3 = _build_3w_group([135, 160, 145, 175])
    assert verify_link_t([g1, g2, g3], [link1, link2], "linear") is None


def test_reject_link_too_large() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=115)
    g2 = _build_3w_group([115, 150, 130, 160])
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_reject_s1_not_longer_than_link() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=120)
    g2_segs = make_segments([120, 135, 125, 145])
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=g2_segs[0].start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=g2_segs,
        span_end=g2_segs[-1].end,
    )
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_reject_only_one_group() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    assert verify_link_t([g1], [], "linear") is None


def test_reject_4_groups() -> None:
    g1 = _build_3w_group([100, 120, 110, 130])
    g2 = _build_3w_group([125, 145, 135, 155])
    g3 = _build_3w_group([150, 170, 160, 180])
    g4 = _build_3w_group([175, 195, 185, 205])
    links = [
        _link_segment(g1.segments[-1].end, 125),
        _link_segment(g2.segments[-1].end, 150),
        _link_segment(g3.segments[-1].end, 175),
    ]
    assert verify_link_t([g1, g2, g3, g4], links, "linear") is None


def test_reject_link_same_direction_as_trend() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=145)
    g2 = _build_3w_group([145, 175, 155, 185])
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_r7_aggregate_records_min_s1_to_link_ratio() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=130)
    g2 = _build_3w_group([130, 165, 145, 180])
    result = verify_link_t([g1, g2], [link], "linear")
    assert result is not None
    _, rules = result
    r7 = next(r for r in rules if r.id == "link_t.r7.s1_gt_link")
    assert r7.passed is True
    assert r7.measured is not None
    assert r7.measured == pytest.approx(3.5)


def test_r8_aggregate_records_max_link_to_s3_ratio() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link1 = _link_segment(g1.segments[-1].end, end_price=125)
    g2_segs = make_segments([125, 165, 140, 175])
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=g2_segs[0].start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=g2_segs,
        span_end=g2_segs[-1].end,
    )
    link2 = _link_segment(g2.segments[-1].end, end_price=170)
    g3_segs = make_segments([170, 210, 190, 230])
    g3 = WaveNode(
        role=WaveRole.SET_3,
        span_start=g3_segs[0].start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=g3_segs,
        span_end=g3_segs[-1].end,
    )
    result = verify_link_t([g1, g2, g3], [link1, link2], "linear")
    assert result is not None
    _, rules = result
    r8 = next(r for r in rules if r.id == "link_t.r8.link_sizes")
    assert r8.passed is True
    assert r8.measured is not None
    assert r8.measured == pytest.approx(0.5)


def test_r7_compares_leg_span_not_first_leaf_when_s1_is_subpattern() -> None:
    g1 = _build_3w_group([200, 280, 240, 340])

    link = _link_segment(g1.segments[-1].end, end_price=290, weeks_after=3)

    base_t = link.end.time
    s1_start = Pivot(0, base_t, 290, "low", link.end.bar_index)
    s1_seg1_end = Pivot(1, base_t + timedelta(weeks=1), 320, "high", link.end.bar_index + 1)
    s1_seg2_end = Pivot(2, base_t + timedelta(weeks=2), 305, "low", link.end.bar_index + 2)
    s1_seg3_end = Pivot(3, base_t + timedelta(weeks=3), 390, "high", link.end.bar_index + 3)
    s1_subpattern = WaveNode(
        role=WaveRole.S1,
        span_start=s1_start,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=[
            Segment(start=s1_start, end=s1_seg1_end),
            Segment(start=s1_seg1_end, end=s1_seg2_end),
            Segment(start=s1_seg2_end, end=s1_seg3_end),
        ],
        span_end=s1_seg3_end,
    )

    s2_end = Pivot(4, base_t + timedelta(weeks=4), 360, "low", link.end.bar_index + 4)
    s3_end = Pivot(5, base_t + timedelta(weeks=5), 410, "high", link.end.bar_index + 5)
    s2_node = WaveNode(
        role=WaveRole.S2,
        span_start=s1_seg3_end,
        segments=[Segment(start=s1_seg3_end, end=s2_end)],
        span_end=s2_end,
    )
    s3_node = WaveNode(
        role=WaveRole.S3,
        span_start=s2_end,
        segments=[Segment(start=s2_end, end=s3_end)],
        span_end=s3_end,
    )

    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=s1_start,
        pattern_kind=PatternKind.THREE_NORMAL,
        children=[s1_subpattern, s2_node, s3_node],
        span_end=s3_end,
    )

    result = verify_link_t([g1, g2], [link], "linear")
    assert result is not None, (
        "R7 rejected a valid Link-T because it compared the s1 leaf (30) "
        "to the link (50) instead of the s1 leg span (100)"
    )
    _, rules = result
    r7 = next(r for r in rules if r.id == "link_t.r7.s1_gt_link")
    assert r7.passed is True
    assert r7.measured is not None and r7.measured > 1.5, (
        f"expected leg-span ratio (~2.0); got {r7.measured!r}"
    )


def test_link_t_r9_records_link_times_when_passing() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=130)
    base_time = link.end.time
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=Pivot(0, base_time, 130, "low", link.end.bar_index),
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=[
            Segment(
                start=Pivot(0, base_time, 130, "low", link.end.bar_index),
                end=Pivot(1, base_time + timedelta(weeks=1), 165, "high", link.end.bar_index + 1),
            ),
            Segment(
                start=Pivot(1, base_time + timedelta(weeks=1), 165, "high", link.end.bar_index + 1),
                end=Pivot(2, base_time + timedelta(weeks=2), 145, "low", link.end.bar_index + 2),
            ),
            Segment(
                start=Pivot(2, base_time + timedelta(weeks=2), 145, "low", link.end.bar_index + 2),
                end=Pivot(3, base_time + timedelta(weeks=3), 180, "high", link.end.bar_index + 3),
            ),
        ],
        span_end=Pivot(3, base_time + timedelta(weeks=3), 180, "high", link.end.bar_index + 3),
    )
    result = verify_link_t([g1, g2], [link], "linear")
    assert result is not None
    _, rules = result
    r9 = next(r for r in rules if r.id == "link_t.r9.link_times")
    assert r9.passed is True
    assert r9.measured is not None
    assert r9.measured > 2.0


def test_link_t_r9_rejects_link_time_at_or_below_200pct_ceiling() -> None:
    g1 = _build_3w_group([100, 130, 110, 140])
    link = _link_segment(g1.segments[-1].end, end_price=125, weeks_after=2)
    base_time = link.end.time
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=Pivot(0, base_time, 125, "low", link.end.bar_index),
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=[
            Segment(
                start=Pivot(0, base_time, 125, "low", link.end.bar_index),
                end=Pivot(1, base_time + timedelta(weeks=1), 165, "high", link.end.bar_index + 1),
            ),
            Segment(
                start=Pivot(1, base_time + timedelta(weeks=1), 165, "high", link.end.bar_index + 1),
                end=Pivot(2, base_time + timedelta(weeks=2), 140, "low", link.end.bar_index + 2),
            ),
            Segment(
                start=Pivot(2, base_time + timedelta(weeks=2), 140, "low", link.end.bar_index + 2),
                end=Pivot(3, base_time + timedelta(weeks=3), 175, "high", link.end.bar_index + 3),
            ),
        ],
        span_end=Pivot(3, base_time + timedelta(weeks=3), 175, "high", link.end.bar_index + 3),
    )
    assert verify_link_t([g1, g2], [link], "linear") is None


def test_link_t_r9_skipped_when_bar_index_unavailable() -> None:
    base = datetime(2020, 1, 1)
    p0 = Pivot(0, base, 100.0, "low", None)
    p1 = Pivot(1, base + timedelta(weeks=1), 130.0, "high", None)
    p2 = Pivot(2, base + timedelta(weeks=2), 110.0, "low", None)
    p3 = Pivot(3, base + timedelta(weeks=3), 140.0, "high", None)
    g1 = WaveNode(
        role=WaveRole.SET_1,
        span_start=p0,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=[
            Segment(start=p0, end=p1),
            Segment(start=p1, end=p2),
            Segment(start=p2, end=p3),
        ],
        span_end=p3,
    )
    p4 = Pivot(4, base + timedelta(weeks=4), 130.0, "low", -1)
    link = Segment(start=p3, end=p4)
    p5 = Pivot(5, base + timedelta(weeks=5), 165.0, "high", -1)
    p6 = Pivot(6, base + timedelta(weeks=6), 145.0, "low", -1)
    p7 = Pivot(7, base + timedelta(weeks=7), 180.0, "high", -1)
    g2 = WaveNode(
        role=WaveRole.SET_2,
        span_start=p4,
        pattern_kind=PatternKind.THREE_NORMAL,
        segments=[
            Segment(start=p4, end=p5),
            Segment(start=p5, end=p6),
            Segment(start=p6, end=p7),
        ],
        span_end=p7,
    )
    result = verify_link_t([g1, g2], [link], "linear")
    assert result is not None, "R9 must skip (not reject) when bar_index data is unavailable"
    _, rules = result
    skipped = [r for r in rules if r.id.startswith("link_t.r9.") and "skipped" in r.id]
    assert skipped, "expected an R9 skipped-rule log entry"


# White-box: these skip branches only fire past the early-return guard (first-set s2
# has a valid bar_index), so call the R9 checker directly.


def _leg(start_price: float, start_bar, end_price: float, end_bar) -> WaveNode:
    base = datetime(2020, 1, 1)
    start = Pivot(0, base + timedelta(days=start_bar or 0), start_price, "low", start_bar)
    end = Pivot(1, base + timedelta(days=end_bar or 0), end_price, "high", end_bar)
    return WaveNode(role=WaveRole.S1, span_start=start, span_end=end)


_ONE_SET = [LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2)]


def test_r9_skips_individual_link_when_link_bar_index_missing() -> None:
    # first-set s2 has bar_index → past the early guard; the link itself does not.
    children = [
        _leg(100.0, 0, 130.0, 1),   # s1
        _leg(130.0, 1, 110.0, 2),   # s2 → first_s2_time = 1 (valid)
        _leg(110.0, 2, 140.0, 3),   # s3 → prev_s3_time valid
    ]
    base = datetime(2020, 1, 1)
    link = Segment(
        start=Pivot(0, base, 140.0, "high", None),
        end=Pivot(1, base + timedelta(days=4), 130.0, "low", None),
    )
    rules = _check_r9_link_time(_ONE_SET, children, [link], "linear")
    assert rules is not None
    assert rules[0].id == "link_t.r9.link_time_skipped_0"
    assert rules[0].passed is True
    assert "bar_index unavailable on link or prev s3" in rules[0].detail


def test_r9_skips_individual_link_on_zero_bar_reference() -> None:
    # first_s2 and prev_s3 both span zero bars → ceiling_time == 0 → skip.
    children = [
        _leg(100.0, 5, 130.0, 5),   # s1
        _leg(130.0, 5, 110.0, 5),   # s2 → first_s2_time = 0 (not None)
        _leg(110.0, 5, 140.0, 5),   # s3 → prev_s3_time = 0
    ]
    base = datetime(2020, 1, 1)
    link = Segment(
        start=Pivot(0, base, 140.0, "high", 5),
        end=Pivot(1, base + timedelta(days=2), 130.0, "low", 7),  # link_time = 2 (valid)
    )
    rules = _check_r9_link_time(_ONE_SET, children, [link], "linear")
    assert rules is not None
    assert rules[0].id == "link_t.r9.link_time_skipped_0"
    assert rules[0].passed is True
    assert "zero-bar reference" in rules[0].detail
