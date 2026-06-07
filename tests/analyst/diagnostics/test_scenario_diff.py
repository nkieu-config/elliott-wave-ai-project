import pytest

from analyst.diagnostics.scenario_diff import ScenarioDiff, diff_top_scenarios
from engine.types import PatternKind
from tests.analyst._helpers import make_scenario


def test_diff_two_scenarios():
    sc1 = make_scenario(
        family="5W_TREND",
        pattern_kind=PatternKind.FIVE_TREND_S3_LONGEST,
        score_components={
            "speed_cluster": 0.8, "fib_push_pairs": 0.7,
            "pull_depth_discipline": 0.6, "leg_smoothness": 0.5,
            "structural_total": 0.6, "visual_total": 0.5,
        },
    )
    sc2 = make_scenario(
        family="5W_TREND",
        pattern_kind=PatternKind.FIVE_TREND_S1_LONGEST,
        score_components={
            "speed_cluster": 0.7, "fib_push_pairs": 0.6,
            "pull_depth_discipline": 0.5, "leg_smoothness": 0.55,
            "structural_total": 0.5, "visual_total": 0.55,
        },
    )
    diffs = diff_top_scenarios([sc1, sc2])
    assert len(diffs) == 1
    d: ScenarioDiff = diffs[0]
    assert d.primary_rank == 1
    assert d.competitor_rank == 2
    assert d.primary_bottleneck == "leg_smoothness"
    assert d.competitor_bottleneck == "pull_depth_discipline"
    assert d.pattern_kind_match is False


def test_diff_carries_family_and_relative_probability():
    sc1 = make_scenario(
        family="5W_SIDEWAY",
        pattern_kind=PatternKind.FIVE_SIDEWAY_BALANCE,
        score_components={"speed_cluster": 0.6}, score=0.6,
    )
    sc2 = make_scenario(
        family="3W",
        pattern_kind=PatternKind.THREE_NORMAL,
        score_components={"speed_cluster": 0.5}, score=0.3,
    )
    sc3 = make_scenario(
        family="5W_TREND",
        pattern_kind=PatternKind.FIVE_TREND_S1_LONGEST,
        score_components={"speed_cluster": 0.4}, score=0.1,
    )
    diffs = diff_top_scenarios([sc1, sc2, sc3])
    assert len(diffs) == 2
    assert diffs[0].primary_family == "5W_SIDEWAY"
    # approx: probability is score/sum, and 0.6+0.3+0.1 != 1.0 in float (version-dependent).
    assert diffs[0].primary_probability == pytest.approx(0.6)
    assert diffs[0].competitor_family == "3W"
    assert diffs[0].competitor_probability == pytest.approx(0.3)
    assert diffs[1].competitor_family == "5W_TREND"
    assert diffs[1].competitor_probability == pytest.approx(0.1)


def test_diff_probability_safe_when_scores_absent():
    sc1 = make_scenario(
        family="3W",
        pattern_kind=PatternKind.THREE_NORMAL,
        score_components={"speed_cluster": 0.5}, score=0.0,
    )
    sc2 = make_scenario(
        family="3W",
        pattern_kind=PatternKind.THREE_NORMAL,
        score_components={"speed_cluster": 0.4}, score=0.0,
    )
    diffs = diff_top_scenarios([sc1, sc2])
    assert diffs[0].primary_probability == 0.0
