from __future__ import annotations

from analyst.diagnostics.chart_primitives import (
    bars_break_trendline,
    bars_reach_price,
)
from analyst.schemas.confirmation import ConfirmationLevel, ConfirmationReport
from engine import Bar, PatternKind, Pivot, ScaleMode, Scenario, TrendDir


def _resolve_end_bar(pivot: Pivot | None, bars: list[Bar]) -> int:
    # Guard bar_index None too: a formed pivot can carry None → range(None+1) crash.
    if pivot is not None and pivot.bar_index is not None:
        return pivot.bar_index
    return len(bars) - 1


def evaluate_confirmation(
    sc: Scenario, bars: list[Bar], mode: ScaleMode,
) -> ConfirmationReport:
    if sc.family == "5W_TREND":
        return _eval_5wt(sc, bars, mode)
    if sc.family == "5W_SIDEWAY":
        if sc.pattern_kind == PatternKind.FIVE_SIDEWAY_EXPAND:
            return ConfirmationReport.not_applicable(
                family="5W_SIDEWAY",
                reason="Expand subtype has no s2-s4 trendline; theory explicitly directs alternative methods (p.43)",
                citation=43,
            )
        return _eval_5ws_cb(sc, bars, mode)
    if sc.family == "3W":
        return _eval_3w(sc, bars, mode)
    if sc.family in ("LINK_T", "LINK_S", "LINK_SE"):
        return ConfirmationReport.not_applicable(
            family=sc.family,
            reason="Theory does not specify Link-Wave confirmation; treated as not_applicable pending advisor consult (spec §9.2)",
            citation=None,
        )
    return ConfirmationReport.not_applicable(
        family=sc.family,
        reason=f"Unknown family {sc.family!r}",
        citation=None,
    )


def _eval_5w(
    sc: Scenario,
    bars: list[Bar],
    mode: ScaleMode,
    *,
    family: str,
    pages: tuple[int, int, int, int],
) -> ConfirmationReport:
    # `pages` are per-level (L1..L4) theory pages.
    legs = sc.legs
    if len(legs) < 5:
        # Open wave IS the still-forming fifth — frame as pending-close, not absent.
        return ConfirmationReport.not_applicable(
            family=family,
            reason=(
                f"{family}: {len(legs)} of 5 legs are formed and the final "
                "wave is still open — confirmation fires only once it closes"
            ),
            citation=None,
        )

    s1, s2, _s3, s4, s5 = legs[:5]
    trend_dir: TrendDir = "up" if s1.span_end.price > s1.span_start.price else "down"
    opposite_dir: TrendDir = "down" if trend_dir == "up" else "up"
    s5_end_bar = _resolve_end_bar(s5.span_end, bars)

    l1_bar = bars_break_trendline(
        bars, s2.span_end, s4.span_end,
        direction=opposite_dir, mode=mode, after_bar=s5_end_bar,
    )
    l2_bar = bars_reach_price(
        bars, s5.span_start.price,
        direction=opposite_dir, after_bar=s5_end_bar,
    )
    full_span = s5.span_end.price - s1.span_start.price
    l3_target = s5.span_end.price - 0.618 * full_span
    l3_bar = bars_reach_price(
        bars, l3_target, direction=opposite_dir, after_bar=s5_end_bar,
    )
    l4_bar = bars_reach_price(
        bars, s1.span_start.price,
        direction=opposite_dir, after_bar=s5_end_bar,
    )

    p1, p2, p3, p4 = pages
    levels = (
        ConfirmationLevel(
            name="L1", condition="s2-s4 trendline broken",
            met=l1_bar is not None, triggered_at_bar=l1_bar, theory_page=p1,
        ),
        ConfirmationLevel(
            name="L2", condition="s5 retraced 100%",
            met=l2_bar is not None, triggered_at_bar=l2_bar, theory_page=p2,
        ),
        ConfirmationLevel(
            name="L3", condition="full set retraced 61.8%",
            met=l3_bar is not None, triggered_at_bar=l3_bar, theory_page=p3,
        ),
        ConfirmationLevel(
            name="L4", condition="full set retraced 100%",
            met=l4_bar is not None, triggered_at_bar=l4_bar, theory_page=p4,
        ),
    )
    return ConfirmationReport(family=family, levels=levels)


def _eval_5wt(sc: Scenario, bars: list[Bar], mode: ScaleMode) -> ConfirmationReport:
    return _eval_5w(sc, bars, mode, family="5W_TREND", pages=(33, 34, 34, 34))


def _eval_5ws_cb(sc: Scenario, bars: list[Bar], mode: ScaleMode) -> ConfirmationReport:
    # Contract/Balance: same 4 levels, reference p.43.
    return _eval_5w(sc, bars, mode, family="5W_SIDEWAY", pages=(43, 43, 43, 43))


def _eval_3w(sc: Scenario, bars: list[Bar], mode: ScaleMode) -> ConfirmationReport:
    legs = sc.legs
    if len(legs) < 3:
        return ConfirmationReport.not_applicable(
            family="3W",
            reason=(
                f"3W: {len(legs)} of 3 legs are formed and the final wave is "
                "still open — confirmation fires only once it closes"
            ),
            citation=None,
        )
    s1, s2, s3 = legs[:3]
    trend_dir: TrendDir = "up" if s1.span_end.price > s1.span_start.price else "down"
    opposite_dir: TrendDir = "down" if trend_dir == "up" else "up"
    s3_end_bar = _resolve_end_bar(s3.span_end, bars)

    levels: list[ConfirmationLevel] = []
    s2_longer = sc.pattern_kind in (
        PatternKind.THREE_S2_LONGER,
        PatternKind.THREE_S2_LONGER_S3_SHORTER,
    )

    # C1 only when s2 is NOT Longer (p.54).
    if not s2_longer:
        c1_bar = bars_break_trendline(
            bars, s1.span_start, s2.span_end,
            direction=opposite_dir, mode=mode, after_bar=s3_end_bar,
        )
        levels.append(ConfirmationLevel(
            name="C1", condition="0-s2 trendline broken",
            met=c1_bar is not None, triggered_at_bar=c1_bar, theory_page=54,
        ))

    c2_bar = bars_reach_price(
        bars, s3.span_start.price,
        direction=opposite_dir, after_bar=s3_end_bar,
    )
    levels.append(ConfirmationLevel(
        name="C2", condition="s3 retraced 100%",
        met=c2_bar is not None, triggered_at_bar=c2_bar, theory_page=55,
    ))
    return ConfirmationReport(family="3W", levels=tuple(levels))
