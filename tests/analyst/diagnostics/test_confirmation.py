from datetime import datetime, timedelta

from analyst.diagnostics.confirmation import evaluate_confirmation
from engine.types import Bar, PatternKind
from tests.analyst._helpers import make_scenario
from tests.analyst._helpers import make_uptrend_then_drop_bars as _bars_uptrend_then_drop


def _flat_bars(prices: list[float]) -> list[Bar]:
    base = datetime(2024, 1, 1)
    return [
        Bar(time=base + timedelta(weeks=i), open=p, high=p + 1, low=p - 1, close=p)
        for i, p in enumerate(prices)
    ]


def _up_3w() -> "object":
    # s2 (110) stays above the 0 low (100), so the 0-s2 line slopes up.
    return make_scenario(
        family="3W", pattern_kind=PatternKind.THREE_NORMAL,
        pivots=[(100.0, 0, "low"), (120.0, 1, "high"), (110.0, 2, "low"), (130.0, 3, "high")],
        score_components={},
    )


def _build_5w_trend_scenario():
    return make_scenario(score_components={})


def test_5wt_l1_broken_when_close_below_s2_s4_trendline():
    sc = _build_5w_trend_scenario()
    bars = _bars_uptrend_then_drop(n=300)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    assert rep.family == "5W_TREND"
    assert rep.is_applicable
    assert len(rep.levels) == 4
    l1 = rep.levels[0]
    assert l1.name == "L1"
    assert l1.theory_page == 33
    assert l1.met is True


def test_5wt_l4_met_when_price_retraces_to_anchor():
    sc = _build_5w_trend_scenario()
    bars = _bars_uptrend_then_drop(n=300)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    l4 = rep.levels[3]
    assert l4.theory_page == 34
    assert l4.met is True


def test_5wt_l4_unmet_when_price_does_not_retrace_to_anchor():
    sc = _build_5w_trend_scenario()
    bars = _bars_uptrend_then_drop(n=250)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    l4 = rep.levels[3]
    assert l4.theory_page == 34
    assert l4.met is False


def _build_5ws_scenario(pattern_kind):
    return make_scenario(
        family="5W_SIDEWAY",
        pattern_kind=pattern_kind,
        pivots=[
            (100.0, 0, "low"),
            (105.0, 40, "high"),
            (95.0, 50, "low"),
            (110.0, 100, "high"),
            (92.0, 130, "low"),
            (108.0, 200, "high"),
        ],
        score=0.4,
        scenario_id="ws1",
        score_components={},
    )


def test_5ws_contract_uses_4_levels_like_trend():
    sc = _build_5ws_scenario(PatternKind.FIVE_SIDEWAY_CONTRACT)
    bars = _bars_uptrend_then_drop(n=300)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    assert rep.is_applicable
    assert len(rep.levels) == 4
    assert rep.levels[0].theory_page == 43


def test_5ws_expand_returns_not_applicable():
    sc = _build_5ws_scenario(PatternKind.FIVE_SIDEWAY_EXPAND)
    bars = _bars_uptrend_then_drop(n=300)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    assert not rep.is_applicable
    assert "Expand" in rep.not_applicable_reason.text
    assert rep.not_applicable_reason.citation == 43


def _build_3w(pattern_kind):
    return make_scenario(
        family="3W",
        pattern_kind=pattern_kind,
        pivots=[
            (100.0, 0, "low"),
            (120.0, 30, "high"),
            (90.0, 60, "low"),
            (115.0, 100, "high"),
        ],
        score=0.3,
        scenario_id="t3w",
        score_components={},
    )


def test_3w_normal_has_two_conditions():
    sc = _build_3w(PatternKind.THREE_NORMAL)
    bars = _bars_uptrend_then_drop(n=200)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    assert rep.is_applicable
    assert len(rep.levels) == 2
    assert rep.levels[0].name == "C1"
    assert rep.levels[1].name == "C2"
    assert rep.levels[0].theory_page == 54
    assert rep.levels[1].theory_page == 55


def test_3w_s2_longer_skips_c1():
    sc = _build_3w(PatternKind.THREE_S2_LONGER)
    bars = _bars_uptrend_then_drop(n=200)
    rep = evaluate_confirmation(sc, bars, mode="linear")
    assert rep.is_applicable
    assert len(rep.levels) == 1
    assert rep.levels[0].name == "C2"


def test_3w_c1_not_met_while_price_keeps_advancing():
    # C1 (0-s2 trendline break) is a COUNTER-trend break: an up 3W that keeps
    # rallying with no reversal must not report C1 met (regression — it did when
    # the break was checked in the trend direction).
    c1 = evaluate_confirmation(_up_3w(), _flat_bars([100, 120, 110, 130, 135, 140, 145]),
                               mode="linear").levels[0]
    assert c1.name == "C1"
    assert c1.met is False


def test_3w_c1_met_on_counter_trend_reversal():
    c1 = evaluate_confirmation(_up_3w(), _flat_bars([100, 120, 110, 130, 120, 105, 95]),
                               mode="linear").levels[0]
    assert c1.name == "C1"
    assert c1.met is True


def test_link_t_returns_not_applicable():
    sc = make_scenario(
        family="LINK_T",
        pattern_kind=PatternKind.LINK_T,
        pivots=[
            (100.0, 0, "low"),
            (120.0, 20, "high"),
            (110.0, 40, "low"),
            (130.0, 60, "high"),
        ],
        score=0.2,
        scenario_id="lt",
        score_components={},
    )
    rep = evaluate_confirmation(sc, [], mode="linear")
    assert not rep.is_applicable
    assert "Link-Wave" in rep.not_applicable_reason.text
