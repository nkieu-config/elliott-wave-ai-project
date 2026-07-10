from __future__ import annotations

import pytest

from engine.parser import count_waves
from engine.types import PatternKind, WaveRole
from tests.engine.parser._builders import piv
from tests.fixtures import make_segments

pytestmark = pytest.mark.slow


def test_link_t_2_groups_real_pattern() -> None:
    from engine.types import Segment

    # g1 3W up: 100→130 (s1=30), 130→115 (s2=15), 115→145 (s3=30)
    p0 = piv(0, 100.0, "low", 0)
    p1 = piv(1, 130.0, "high", 1)
    p2 = piv(2, 115.0, "low", 2)
    p3 = piv(3, 145.0, "high", 3)
    # link 145→130 (Pull 15, 15/30=0.5 ok R8; 3 bars > 2×max(1,1) ok R9)
    p4 = piv(4, 130.0, "low", 6)
    # g2 3W up: 130→160 (s1=30 > link 15 ok), 160→145 (s2=15), 145→175 (s3=30)
    p5 = piv(5, 160.0, "high", 7)
    p6 = piv(6, 145.0, "low", 8)
    p7 = piv(7, 175.0, "high", 9)
    pivs = [p0, p1, p2, p3, p4, p5, p6, p7]
    segs = [Segment(start=pivs[i], end=pivs[i + 1]) for i in range(7)]

    anchor = segs[0].start
    report = count_waves(anchor, segs, "linear")
    link_t = [
        sc
        for sc in report.scenarios
        if sc.family == "LINK_T" and sc.is_complete and sc.pattern_kind == PatternKind.LINK_T
    ]
    assert len(link_t) >= 1, (
        f"Expected LINK_T complete scenario; got "
        f"{[(s.family, s.pattern_kind, s.is_complete, s.depth) for s in report.scenarios]}"
    )


def test_link_s_or_alternative_interpretation() -> None:
    prices = [100, 130, 115, 145, 107, 125, 117, 127]
    segs = make_segments(prices)
    anchor = segs[0].start
    report = count_waves(anchor, segs, "linear")
    valid_complete = [
        sc for sc in report.scenarios if sc.is_complete and sc.pattern_kind is not None
    ]
    assert len(valid_complete) >= 1, (
        f"Expected at least one valid complete scenario; got "
        f"{[(s.family, s.pattern_kind, s.is_complete) for s in report.scenarios]}"
    )


def test_5w_trend_still_works_with_link_seeds() -> None:
    segs = make_segments([100, 130, 115, 175, 155, 200])
    anchor = segs[0].start
    report = count_waves(anchor, segs, "linear")
    direct_5w = [
        sc
        for sc in report.scenarios
        if sc.family == "5W_TREND"
        and sc.is_complete
        and sc.pattern_kind == PatternKind.FIVE_TREND_S3_LONGEST
        and sc.depth == 1
    ]
    assert len(direct_5w) >= 1


def test_link_wave_does_not_hang() -> None:
    import random

    rng = random.Random(99)
    prices = [100.0]
    for _ in range(15):
        prices.append(prices[-1] * (1 + rng.uniform(-0.10, 0.10)))
    segs = make_segments(prices)
    anchor = segs[0].start
    report = count_waves(anchor, segs, "log")
    assert report is not None
    from engine.parser import BEAM_WIDTH

    assert len(report.scenarios) <= BEAM_WIDTH


# Incremental guards: R7/R8 (LINK_T) and R3 (LINK_S) only fired at full-pattern verify.


def _build_3w_leg(prices: list[float], kind: PatternKind = PatternKind.THREE_NORMAL):
    from engine.parser.types import _Leg
    from engine.types import WaveRole

    segs = make_segments(prices)
    assert len(segs) == 3, "3W group needs 3 segments"
    sub_legs = [
        _Leg(role=WaveRole.S1, span_start=segs[0].start, span_end=segs[0].end),
        _Leg(role=WaveRole.S2, span_start=segs[1].start, span_end=segs[1].end),
        _Leg(role=WaveRole.S3, span_start=segs[2].start, span_end=segs[2].end),
    ]
    return _Leg(
        role=WaveRole.SET_1,
        span_start=segs[0].start,
        span_end=segs[-1].end,
        pattern_kind=kind,
        sub_legs=sub_legs,
    )


def test_link_t_r8_link_size_enforced_incrementally() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context
    from engine.types import WaveRole

    # g1 = 3W with s3 length = 30 (segs s1=30, s2=15, s3=30)
    group1 = _build_3w_leg([100, 130, 115, 145])
    ctx = _Context(family="LINK_T", legs=[group1])

    s3_len = group1.sub_legs[-1].length("linear")
    assert s3_len == 30.0

    assert _incremental_ok(ctx, WaveRole.LINK, 15.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 18.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 19.0, "linear") is False
    assert _incremental_ok(ctx, WaveRole.LINK, 24.0, "linear") is False
    assert _incremental_ok(ctx, WaveRole.LINK, 0.15, "linear") is False


def test_link_s_r3_link_size_enforced_incrementally_for_3w_group() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context
    from engine.types import WaveRole

    # 3W up: total range = 145 − 100 = 45; floor = 78.6% × 45 = 35.37
    group1 = _build_3w_leg([100, 130, 115, 145])
    ctx = _Context(family="LINK_S", legs=[group1])

    assert _incremental_ok(ctx, WaveRole.LINK, 36.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 50.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear") is False
    assert _incremental_ok(ctx, WaveRole.LINK, 20.0, "linear") is False


def test_link_s_r3_link_size_for_5w_sideway_expand_uses_s5() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context, _Leg
    from engine.types import WaveRole

    # Fake 5W_SIDEWAY_EXPAND with sub_legs s1..s5, s5 length=50; floor=78.6%×50=39.3
    base = make_segments([100, 110, 105, 115, 108, 158])
    sub_legs = [
        _Leg(role=role, span_start=segs.start, span_end=segs.end)
        for role, segs in zip(
            [WaveRole.S1, WaveRole.S2, WaveRole.S3, WaveRole.S4, WaveRole.S5],
            base,
            strict=True,
        )
    ]
    s5_len = sub_legs[4].length("linear")
    assert s5_len == 50.0

    group1 = _Leg(
        role=WaveRole.SET_1,
        span_start=base[0].start,
        span_end=base[-1].end,
        pattern_kind=PatternKind.FIVE_SIDEWAY_EXPAND,
        sub_legs=sub_legs,
    )
    ctx = _Context(family="LINK_S", legs=[group1])

    assert _incremental_ok(ctx, WaveRole.LINK, 40.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear") is False


def test_link_s_r3_link_size_for_5w_sideway_balance_uses_total_range() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context, _Leg
    from engine.types import WaveRole

    base = make_segments([100, 130, 110, 125, 115, 130])
    sub_legs = [
        _Leg(role=role, span_start=segs.start, span_end=segs.end)
        for role, segs in zip(
            [WaveRole.S1, WaveRole.S2, WaveRole.S3, WaveRole.S4, WaveRole.S5],
            base,
            strict=True,
        )
    ]
    group1 = _Leg(
        role=WaveRole.SET_1,
        span_start=base[0].start,
        span_end=base[-1].end,
        pattern_kind=PatternKind.FIVE_SIDEWAY_BALANCE,
        sub_legs=sub_legs,
    )
    ctx = _Context(family="LINK_S", legs=[group1])

    # total_price_range = 130 − 100 = 30; need link > 101% × 30 = 30.3
    assert _incremental_ok(ctx, WaveRole.LINK, 35.0, "linear") is True
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear") is False
    assert _incremental_ok(ctx, WaveRole.LINK, 15.0, "linear") is False


def test_link_t_r7_next_group_s1_must_exceed_prior_link() -> None:
    from engine.parser.engine.closing import _close_top_into_parent
    from engine.parser.types import _Context, _Hypothesis, _Leg
    from engine.types import WaveRole

    # set_1 3W up: s1=30, s2=15, s3=30 (span 100→145)
    g1_segs = make_segments([100, 130, 115, 145])
    group1 = _Leg(
        role=WaveRole.SET_1,
        span_start=g1_segs[0].start,
        span_end=g1_segs[-1].end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g1_segs[0].start, span_end=g1_segs[0].end),
            _Leg(role=WaveRole.S2, span_start=g1_segs[1].start, span_end=g1_segs[1].end),
            _Leg(role=WaveRole.S3, span_start=g1_segs[2].start, span_end=g1_segs[2].end),
        ],
    )
    # link_1: 145→130 (Pull, len 15 within R8 of g1.s3=30); +6 bars satisfies both
    # R9 (link time >2× the ~1-bar sub-legs) and the Gann band (≤3× the ~3-bar set).
    link1_start = g1_segs[-1].end
    link1_end = piv(link1_start.index + 6, 130, "low")
    link1 = _Leg(role=WaveRole.LINK, span_start=link1_start, span_end=link1_end)

    # set_2 3W up: s1=35 (>15 ok R7), s2=20, s3=35 (span 130→180)
    g2_s1_start = link1_end
    g2_s1_end = piv(g2_s1_start.index + 1, 165, "high")
    g2_s2_end = piv(g2_s1_end.index + 1, 145, "low")
    g2_s3_end = piv(g2_s2_end.index + 1, 180, "high")
    group2 = _Leg(
        role=WaveRole.SET_2,
        span_start=g2_s1_start,
        span_end=g2_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g2_s1_start, span_end=g2_s1_end),
            _Leg(role=WaveRole.S2, span_start=g2_s1_end, span_end=g2_s2_end),
            _Leg(role=WaveRole.S3, span_start=g2_s2_end, span_end=g2_s3_end),
        ],
    )
    # link_2: 180→165 (Pull, len 15 within R8 of g2.s3=35); +6 bars (see link_1)
    link2_start = g2_s3_end
    link2_end = piv(link2_start.index + 6, 165, "low")
    link2 = _Leg(role=WaveRole.LINK, span_start=link2_start, span_end=link2_end)

    # Valid 2-group LINK_T; growing to 3 groups re-runs the 5-leg verifier (final_kind
    # is invalidated on leg append, so the fixture must be a genuine 3-group LINK_T).
    parent = _Context(
        family="LINK_T",
        legs=[group1, link1, group2, link2],
        final_kind=PatternKind.LINK_T,
    )
    assert parent.is_complete is False

    # set_3 with s1=14 (≤ link_2=15) violates R7
    g3_s1_start = link2_end
    g3_s1_end = piv(g3_s1_start.index + 1, 179, "high")
    g3_s2_end = piv(g3_s1_end.index + 1, 175, "low")
    g3_s3_end = piv(g3_s2_end.index + 1, 195, "high")
    closing_g3 = _Context(
        family="3W",
        legs=[
            _Leg(role=WaveRole.S1, span_start=g3_s1_start, span_end=g3_s1_end),
            _Leg(role=WaveRole.S2, span_start=g3_s1_end, span_end=g3_s2_end),
            _Leg(role=WaveRole.S3, span_start=g3_s2_end, span_end=g3_s3_end),
        ],
        final_kind=PatternKind.THREE_NORMAL,
        parent_role=WaveRole.SET_3,
    )
    h = _Hypothesis(id="t-r7-3grp", context_stack=[parent, closing_g3])

    # Bad set_3: the R7 gate rejects the close before the parent grows, so legs stay 4.
    ok = _close_top_into_parent(h, "linear")
    assert ok is False, (
        "LINK_T R7 must reject set_3 close when its s1 leg is not longer "
        f"than the prior link (s1={closing_g3.legs[0].length('linear')}, "
        f"link_2={link2.length('linear')})"
    )
    assert len(parent.legs) == 4, "rejected close must not mutate parent.legs"

    # Counterpart: longer s1 closes successfully
    g3_s1_end_long = piv(g3_s1_start.index + 1, 195, "high")
    g3_s2_end_long = piv(g3_s1_end_long.index + 1, 180, "low")
    g3_s3_end_long = piv(g3_s2_end_long.index + 1, 210, "high")
    closing_g3_ok = _Context(
        family="3W",
        legs=[
            _Leg(role=WaveRole.S1, span_start=g3_s1_start, span_end=g3_s1_end_long),
            _Leg(role=WaveRole.S2, span_start=g3_s1_end_long, span_end=g3_s2_end_long),
            _Leg(role=WaveRole.S3, span_start=g3_s2_end_long, span_end=g3_s3_end_long),
        ],
        final_kind=PatternKind.THREE_NORMAL,
        parent_role=WaveRole.SET_3,
    )
    parent_ok = _Context(
        family="LINK_T",
        legs=[group1, link1, group2, link2],
        final_kind=PatternKind.LINK_T,
    )
    h_ok = _Hypothesis(id="t-r7-3grp-ok", context_stack=[parent_ok, closing_g3_ok])
    assert _close_top_into_parent(h_ok, "linear") is True


# Gann Box link time-degree gate (theory p.94)


def test_link_t_link_time_degree_gate_rejects_below_200pct_ceiling() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context, _Leg
    from engine.types import WaveRole

    # set_1 3W up with sub-legs s1=10, s2=20, s3=30 bars; prices chosen so R8 passes
    g1_s1_start = piv(0, 100.0, "low", 0)
    g1_s1_end = piv(1, 200.0, "high", 10)
    g1_s2_end = piv(2, 150.0, "low", 30)
    g1_s3_end = piv(3, 250.0, "high", 60)

    group1 = _Leg(
        role=WaveRole.SET_1,
        span_start=g1_s1_start,
        span_end=g1_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g1_s1_start, span_end=g1_s1_end),
            _Leg(role=WaveRole.S2, span_start=g1_s1_end, span_end=g1_s2_end),
            _Leg(role=WaveRole.S3, span_start=g1_s2_end, span_end=g1_s3_end),
        ],
    )
    ctx = _Context(family="LINK_T", legs=[group1])
    # link_1 vs g1: ceiling=max(20,30)=30 → page-94 rule: link bars > 2×30 = 60 (strict)

    # Above 200% of ceiling — accepted
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=61) is True
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=80) is True
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=200) is True

    # Exactly at 200% — rejected (strict ">")
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=60) is False
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=30) is False
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=20) is False
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=7) is False
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=2) is False
    assert _incremental_ok(ctx, WaveRole.LINK, 30.0, "linear", leg_bars=6) is False


def test_link_t_link_time_degree_uses_g1_s2_not_g2_s2_for_link_2() -> None:
    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context, _Leg
    from engine.types import WaveRole

    # g1: s1=10, s2=20, s3=30 bars
    g1_s1_start = piv(0, 100.0, "low", 0)
    g1_s1_end = piv(1, 200.0, "high", 10)
    g1_s2_end = piv(2, 150.0, "low", 30)
    g1_s3_end = piv(3, 250.0, "high", 60)
    g1 = _Leg(
        role=WaveRole.SET_1,
        span_start=g1_s1_start,
        span_end=g1_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g1_s1_start, span_end=g1_s1_end),
            _Leg(role=WaveRole.S2, span_start=g1_s1_end, span_end=g1_s2_end),
            _Leg(role=WaveRole.S3, span_start=g1_s2_end, span_end=g1_s3_end),
        ],
    )
    # link_1 65 bars (above gate's 60-bar lower bound)
    link1_start = g1_s3_end
    link1_end = piv(4, 220.0, "low", 125)
    link1 = _Leg(role=WaveRole.LINK, span_start=link1_start, span_end=link1_end)

    # g2: s1=15, s2=15 (smaller than g1.s2=20), s3=25 bars
    g2_s1_start = link1_end
    g2_s1_end = piv(5, 320.0, "high", 140)
    g2_s2_end = piv(6, 270.0, "low", 155)
    g2_s3_end = piv(7, 370.0, "high", 180)
    g2 = _Leg(
        role=WaveRole.SET_2,
        span_start=g2_s1_start,
        span_end=g2_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g2_s1_start, span_end=g2_s1_end),
            _Leg(role=WaveRole.S2, span_start=g2_s1_end, span_end=g2_s2_end),
            _Leg(role=WaveRole.S3, span_start=g2_s2_end, span_end=g2_s3_end),
        ],
    )

    ctx = _Context(family="LINK_T", legs=[g1, link1, g2])

    # ceiling=max(g1.s2=20, g2.s3=25)=25 → link must >50; 51 passes, 50 rejected (strict)
    assert (
        _incremental_ok(
            ctx,
            WaveRole.LINK,
            20.0,
            "linear",
            leg_bars=51,
        )
        is True
    )
    assert (
        _incremental_ok(
            ctx,
            WaveRole.LINK,
            20.0,
            "linear",
            leg_bars=50,
        )
        is False
    ), "exactly 2 × ceiling does NOT satisfy 'must be larger than 200%'"

    # Differentiation case: g1.s2 = 50 (ceiling), prior.s3 = 20 → correct rule link > 100
    g1_big_s2 = _Leg(
        role=WaveRole.SET_1,
        span_start=g1_s1_start,
        span_end=g1_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g1_s1_start, span_end=g1_s1_end),
            _Leg(role=WaveRole.S2, span_start=g1_s1_end, span_end=piv(2, 150.0, "low", 60)),
            _Leg(
                role=WaveRole.S3,
                span_start=piv(2, 150.0, "low", 60),
                span_end=piv(3, 250.0, "high", 90),
            ),
        ],
    )
    g2_small = _Leg(
        role=WaveRole.SET_2,
        span_start=g2_s1_start,
        span_end=g2_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g2_s1_start, span_end=g2_s1_end),
            _Leg(role=WaveRole.S2, span_start=g2_s1_end, span_end=g2_s2_end),
            _Leg(role=WaveRole.S3, span_start=g2_s2_end, span_end=piv(7, 370.0, "high", 175)),
        ],
    )
    ctx2 = _Context(family="LINK_T", legs=[g1_big_s2, link1, g2_small])

    # 60 bars: REJECT with correct g1.s2=50; would ACCEPT if g2.s2=15 used by mistake
    assert (
        _incremental_ok(
            ctx2,
            WaveRole.LINK,
            20.0,
            "linear",
            leg_bars=60,
        )
        is False
    ), (
        "link_2 of 60 bars should be REJECTED with correct g1.s2 reference "
        "(ceiling=50, must >100) but would pass if g2.s2 (ceiling=20) used"
    )
    # 110 bars: passes with both refs
    assert (
        _incremental_ok(
            ctx2,
            WaveRole.LINK,
            20.0,
            "linear",
            leg_bars=110,
        )
        is True
    )


def test_link_t_link_time_degree_skips_when_bar_index_unknown() -> None:
    from datetime import datetime

    from engine.parser.families import incremental_ok as _incremental_ok
    from engine.parser.types import _Context, _Leg
    from engine.types import Pivot, WaveRole

    base = datetime(2020, 1, 1)
    p0 = Pivot(0, base, 100.0, "low", None)
    p1 = Pivot(1, base, 200.0, "high", None)
    p2 = Pivot(2, base, 150.0, "low", None)
    p3 = Pivot(3, base, 250.0, "high", None)
    g1 = _Leg(
        role=WaveRole.SET_1,
        span_start=p0,
        span_end=p3,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=p0, span_end=p1),
            _Leg(role=WaveRole.S2, span_start=p1, span_end=p2),
            _Leg(role=WaveRole.S3, span_start=p2, span_end=p3),
        ],
    )
    ctx = _Context(family="LINK_T", legs=[g1])

    # Bars unknown → gate skips (price OK at 30% of s3)
    assert (
        _incremental_ok(
            ctx,
            WaveRole.LINK,
            30.0,
            "linear",
            leg_bars=999,
        )
        is True
    )
    assert (
        _incremental_ok(
            ctx,
            WaveRole.LINK,
            30.0,
            "linear",
            leg_bars=None,
        )
        is True
    )
    # R8 (price) still fires: link 80 = 80% of s3 → out of [1%, 61.8%]
    assert (
        _incremental_ok(
            ctx,
            WaveRole.LINK,
            80.0,
            "linear",
            leg_bars=25,
        )
        is False
    )


# LINK_S group time-similarity gate removed (theory p.95 unquantified)


def test_link_s_close_top_into_parent_accepts_off_degree_set_2() -> None:
    from engine.parser.engine.closing import _close_top_into_parent
    from engine.parser.types import _Context, _Hypothesis, _Leg
    from engine.types import WaveRole

    # set_1 3W up spanning 30 bars (100→200)
    g1_s1_start = piv(0, 100.0, "low", 0)
    g1_s1_end = piv(1, 200.0, "high", 10)
    g1_s2_end = piv(2, 150.0, "low", 20)
    g1_s3_end = piv(3, 200.0, "high", 30)
    group1 = _Leg(
        role=WaveRole.SET_1,
        span_start=g1_s1_start,
        span_end=g1_s3_end,
        pattern_kind=PatternKind.THREE_NORMAL,
        sub_legs=[
            _Leg(role=WaveRole.S1, span_start=g1_s1_start, span_end=g1_s1_end),
            _Leg(role=WaveRole.S2, span_start=g1_s1_end, span_end=g1_s2_end),
            _Leg(role=WaveRole.S3, span_start=g1_s2_end, span_end=g1_s3_end),
        ],
    )
    # link_1: from end of g1 down (Pull); size irrelevant for this test
    link1_start = g1_s3_end
    link1_end = piv(4, 80.0, "low", 35)
    link1 = _Leg(role=WaveRole.LINK, span_start=link1_start, span_end=link1_end)

    parent = _Context(family="LINK_S", legs=[group1, link1])

    # OFF-DEGREE set_2 candidate: span = 5 bars (below floor 30/3 = 10), up direction
    g2_s1_start = link1_end
    g2_s1_end = piv(5, 130.0, "high", 37)
    g2_s2_end = piv(6, 100.0, "low", 39)
    g2_s3_end = piv(7, 145.0, "high", 40)
    closing_g2_off = _Context(
        family="3W",
        legs=[
            _Leg(role=WaveRole.S1, span_start=g2_s1_start, span_end=g2_s1_end),
            _Leg(role=WaveRole.S2, span_start=g2_s1_end, span_end=g2_s2_end),
            _Leg(role=WaveRole.S3, span_start=g2_s2_end, span_end=g2_s3_end),
        ],
        final_kind=PatternKind.THREE_NORMAL,
        parent_role=WaveRole.SET_2,
    )
    h_off = _Hypothesis(id="t-+s-off", context_stack=[parent, closing_g2_off])

    # Post-removal: off-degree set_2 no longer rejected by time-similarity gate
    ok = _close_top_into_parent(h_off, "linear")
    assert ok is True, (
        "LINK_S group time-similarity gate is removed (theory p.95 unquantified) — "
        "off-degree set_2 should now close into parent without rejection"
    )
    assert len(parent.legs) == 3, "successful close must append the closed group as a leg"


# Sub-pattern at LINK position (theory p.85/86)


def test_link_t_link_position_can_be_subpattern() -> None:
    prices = [100, 110, 105, 120, 115, 117, 113, 125, 120, 135]
    segs = make_segments(prices)
    anchor = segs[0].start
    report = count_waves(anchor, segs, "linear")

    link_t_with_sub_link = []
    for sc in report.scenarios:
        if sc.family != "LINK_T" or not sc.is_complete:
            continue
        for lg in sc.legs:
            if lg.role == WaveRole.LINK and (lg.pattern_kind is not None or len(lg.children) > 0):
                link_t_with_sub_link.append(sc)
                break

    assert link_t_with_sub_link, (
        "Theory p.85 — parser must surface a LINK_T scenario whose link is a "
        "sub-pattern when the chart structurally requires it. None found."
    )
    sc = link_t_with_sub_link[0]
    link_leg = next(lg for lg in sc.legs if lg.role == WaveRole.LINK)
    assert link_leg.pattern_kind == PatternKind.THREE_NORMAL, (
        f"Expected link sub-pattern to classify as 3W_NORMAL, got {link_leg.pattern_kind}"
    )
