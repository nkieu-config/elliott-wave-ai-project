from analyst.citations import extract_pages as _extract_pages
from analyst.diagnostics.scenario_diff import ScenarioDiff
from analyst.schemas.bottleneck import BottleneckDiagnosis
from analyst.schemas.citation import TheoryRef
from analyst.schemas.confirmation import ConfirmationLevel, ConfirmationReport
from analyst.schemas.decision import AlternativeBrief, DecisionSummary, PriceMove
from analyst.schemas.succession import NextPattern, SuccessionReport
from analyst.schemas.targets import Target, TargetSet
from analyst.serialization.analysis_blocks import (
    _diversified_fib_flow_subset,
    _slot_detail_line,
    format_alternative_brief,
    format_bottleneck,
    format_confirmation,
    format_decision_summary,
    format_scenario_diff,
    format_succession,
    format_targets,
    format_weakness_detail,
)


def test_format_bottleneck_names_the_check_in_plain_words():
    bd = BottleneckDiagnosis(
        slot_name="leg_smoothness", slot_value=0.589, dimension="visual",
        is_dim_minimum=True, is_overall_minimum=True, gap_to_next=0.123,
        intermediates={},
        plain_explanation="The swing smoothness check is the weakest.",
        theory_ref=TheoryRef(pages=(), concept="Chart appearance",
                             binding="heuristic", note="no binding"),
    )
    md = format_bottleneck(bd)
    assert "swing smoothness check" in md
    assert "heuristic" in md
    assert "leg_smoothness" not in md
    assert "0.589" not in md


def test_format_bottleneck_renders_multi_page_citations_parseable_by_gate():
    bd = BottleneckDiagnosis(
        slot_name="speed_cluster", slot_value=0.5, dimension="structural",
        is_dim_minimum=True, is_overall_minimum=True, gap_to_next=0.1,
        intermediates={}, plain_explanation="…",
        theory_ref=TheoryRef(pages=(91, 96), concept="Same-degree principle",
                             binding="concept_operationalization", note="…"),
    )
    md = format_bottleneck(bd)
    assert _extract_pages(md) == {91, 96}


def test_format_confirmation_lists_levels():
    rep = ConfirmationReport(
        family="5W_TREND",
        levels=(
            ConfirmationLevel(name="L1", condition="s2-s4 trendline broken",
                              met=True, triggered_at_bar=200, theory_page=33),
            ConfirmationLevel(name="L2", condition="s5 retraced 100%",
                              met=False, triggered_at_bar=None, theory_page=34),
        ),
    )
    md = format_confirmation(rep)
    assert "L1" in md and "L2" in md
    assert "p.33" in md and "p.34" in md


def test_format_confirmation_citations_parseable_by_gate():
    rep = ConfirmationReport(
        family="5W_TREND",
        levels=(
            ConfirmationLevel("L1", "s2-s4 trendline broken", True, 200, 33),
            ConfirmationLevel("L2", "s5 retraced 100%", False, None, 34),
        ),
    )
    md = format_confirmation(rep)
    assert _extract_pages(md) == {33, 34}


def test_format_targets_citations_parseable_by_gate():
    ts = TargetSet(
        confirmation_targets=(
            Target(name="s5_retrace_100", price=42.0, type="retracement",
                   theory_page=34, derivation="s5 retraced 100% = s5.start"),
        ),
        fib_flow_targets=(
            Target(name="s1 → s3 internal_1.618", price=50.0, type="internal",
                   theory_page=110, derivation="…"),
        ),
        invalidation=Target(name="s5_end_close", price=99.0, type="invalidation",
                            theory_page=22, derivation="close past s5.end"),
    )
    md = format_targets(ts)
    assert {34, 110} <= _extract_pages(md)


def _retrace_targets(stem: str, levels=(0.236, 0.382, 0.5, 0.618, 0.786, 1.0)):
    return tuple(
        Target(name=f"{stem}_{lvl}", price=10.0 + lvl, type="retracement",
               theory_page=103, derivation=f"{stem} retrace {lvl}")
        for lvl in levels
    )


def test_format_targets_surfaces_every_source_group():
    fib_flow = (
        _retrace_targets("s1 retrace")
        + _retrace_targets("s2 retrace")
        + _retrace_targets("s3 retrace")
        + _retrace_targets("s4 retrace")
        + _retrace_targets("s5 retrace")
    )
    ts = TargetSet(
        confirmation_targets=(),
        fib_flow_targets=fib_flow,
        invalidation=Target(name="inv", price=0.0, type="invalidation",
                            theory_page=22, derivation="…"),
    )
    md = format_targets(ts)
    for stem in ("s1 retrace", "s2 retrace", "s3 retrace", "s4 retrace", "s5 retrace"):
        assert stem in md, f"missing {stem!r} in rendered targets"
    assert "omitted for brevity" in md


def test_format_targets_renders_projected_under_its_own_heading():
    projected = tuple(
        Target(name=f"wave 5 projected_{lvl}", price=100.0 + lvl * 10,
               type="projected", theory_page=111, derivation="proj")
        for lvl in (0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
    )
    ts = TargetSet(
        confirmation_targets=(), fib_flow_targets=projected,
        invalidation=Target(name="inv", price=98.0, type="invalidation",
                            theory_page=22, derivation="…"),
    )
    md = format_targets(ts)
    assert "Projected (pattern still open)" in md
    assert "Fibonacci Flow" not in md
    for lvl in (0.382, 0.5, 0.618):
        assert f"wave 5 projected_{lvl}" in md, (
            f"key Fib level {lvl} should be visible"
        )
    for lvl in (0.236, 0.786, 1.0):
        assert f"wave 5 projected_{lvl}" not in md, (
            f"non-key level {lvl} should be filtered out"
        )
    assert "additional Fibonacci levels" in md
    assert "0.236" in md and "1.0" in md


def test_format_scenario_diff_empty_states_no_competitor():
    md = format_scenario_diff(())
    assert "Scenario Comparison" in md
    assert "no rank-2 competitor" in md


def test_format_scenario_diff_renders_ranked_table_and_pair():
    d = ScenarioDiff(
        primary_rank=1, competitor_rank=2,
        primary_bottleneck="leg_smoothness",
        competitor_bottleneck="pull_depth_discipline",
        slot_deltas={"leg_smoothness": -0.12, "speed_cluster": 0.31},
        structural_winner=1, visual_winner=2, pattern_kind_match=False,
        primary_family="5W_SIDEWAY", competitor_family="3W",
        primary_probability=0.62, competitor_probability=0.38,
    )
    md = format_scenario_diff((d,))
    assert "Relative probability" in md
    assert "5-Wave Sideway" in md and "3-Wave" in md
    assert "62%" in md and "38%" in md
    assert "5W_SIDEWAY" not in md
    assert "rank 1 vs rank 2" in md
    assert "leg_smoothness" not in md
    assert "pull_depth_discipline" not in md
    assert "swing smoothness" in md
    assert "pullback depth" in md
    table = md[md.index("| Check | Gap (score points) |"):]
    assert table.index("wave pacing") < table.index("swing smoothness")
    assert "+31" in table
    assert "%" not in table
    assert "0.31" not in table


def test_format_scenario_diff_ranked_table_spans_three_scenarios():
    d1 = ScenarioDiff(
        primary_rank=1, competitor_rank=2,
        primary_bottleneck="leg_smoothness", competitor_bottleneck="speed_cluster",
        slot_deltas={}, structural_winner=1, visual_winner=1,
        pattern_kind_match=False,
        primary_family="5W_SIDEWAY", competitor_family="3W",
        primary_probability=0.5, competitor_probability=0.3,
    )
    d2 = ScenarioDiff(
        primary_rank=2, competitor_rank=3,
        primary_bottleneck="speed_cluster", competitor_bottleneck="leg_smoothness",
        slot_deltas={}, structural_winner=1, visual_winner=2,
        pattern_kind_match=False,
        primary_family="3W", competitor_family="5W_TREND",
        primary_probability=0.3, competitor_probability=0.2,
    )
    md = format_scenario_diff((d1, d2))
    assert "5-Wave Trend" in md
    assert "20%" in md


def test_format_succession_terminal_renders_note_only():
    rep = SuccessionReport(
        family="5W_TREND", is_terminal=True, next_patterns=(),
        note="A 5-Wave Trend admits no Link-Wave successor (p.59) (p.67).",
    )
    md = format_succession(rep)
    assert "What Can Follow This Pattern" in md
    assert "(p.59)" in md and "(p.67)" in md


def test_format_succession_renders_link_types_families_and_bands():
    rep = SuccessionReport(
        family="3W", is_terminal=False, note="",
        next_patterns=(
            NextPattern(link_type="+T", next_families=("3W",),
                        link_band_near=129.8, link_band_far=117.64,
                        theory_pages=(57, 59, 64), rationale="+T linkage."),
            NextPattern(link_type="+S", next_families=("3W", "5W_SIDEWAY"),
                        link_band_near=98.0, link_band_far=None,
                        theory_pages=(57, 67, 73), rationale="+S linkage."),
        ),
    )
    md = format_succession(rep)
    assert "Trend linkage → 3-Wave" in md
    assert "Sideway linkage → 3-Wave or 5-Wave Sideway" in md
    assert "5W_SIDEWAY" not in md
    assert "### +T linkage →" not in md
    assert "### +S linkage →" not in md
    for page in (57, 59, 64, 67, 73):
        assert f"(p.{page})" in md
    assert "$117.64" in md and "$129.80" in md
    assert "open-ended" in md


def test_format_confirmation_not_applicable_with_and_without_citation():
    with_cite = format_confirmation(
        ConfirmationReport.not_applicable("3W", "Corrective sets need no confirmation.", 88)
    )
    assert "Not applicable" in with_cite
    assert "Corrective sets need no confirmation." in with_cite
    assert "(p.88)" in with_cite

    no_cite = format_confirmation(
        ConfirmationReport.not_applicable("3W", "No rule applies.", None)
    )
    assert "(no citation)" in no_cite


def test_format_succession_pct_from_current_and_link_wave_size():
    band = SuccessionReport(
        family="3W", is_terminal=False, note="",
        next_patterns=(
            NextPattern(link_type="+T", next_families=("3W",),
                        link_band_near=110.0, link_band_far=120.0,
                        theory_pages=(57,), rationale="+T linkage."),
        ),
    )
    md = format_succession(band, current_price=100.0)
    assert "from current)" in md
    assert "+10.0%" in md  # (110 - 100) / 100

    open_size = SuccessionReport(
        family="3W", is_terminal=False, note="",
        next_patterns=(
            NextPattern(link_type="+S", next_families=("3W",),
                        link_band_near=None, link_band_far=None,
                        theory_pages=(67,), rationale="+S linkage.",
                        link_wave_size=42.5),
        ),
    )
    md = format_succession(open_size)
    assert "Link wave size" in md
    assert "$42.50" in md


def test_format_succession_open_size_bound_follows_link_type():
    # +T size is the 61.8% cap (up to); +S size is the 78.6% floor (at least).
    def _report(link_type: str) -> SuccessionReport:
        return SuccessionReport(
            family="3W", is_terminal=False, note="",
            next_patterns=(
                NextPattern(link_type=link_type, next_families=("3W",),
                            link_band_near=None, link_band_far=None,
                            theory_pages=(64,), rationale="x", link_wave_size=18.5),
            ),
        )
    assert "up to $18.50" in format_succession(_report("+T"))
    assert "at least $18.50" in format_succession(_report("+S"))


def test_diversified_fib_flow_subset_caps_total_at_16():
    # 9 stems × 3 each, 2/group → 18 candidates, trimmed to the 16 total cap.
    targets = tuple(
        Target(name=f"g{g} retrace_{i}", price=1.0, type="retracement",
               theory_page=1, derivation="…")
        for g in range(9) for i in range(3)
    )
    assert len(_diversified_fib_flow_subset(targets)) == 16


def test_format_targets_projected_all_key_levels_omits_nothing():
    projected = tuple(
        Target(name=f"wave 5 projected_{lvl}", price=100.0, type="projected",
               theory_page=111, derivation="proj")
        for lvl in (0.382, 0.5, 0.618)  # every level is a "key" level
    )
    ts = TargetSet(
        confirmation_targets=(), fib_flow_targets=projected,
        invalidation=Target("inv", 98.0, "invalidation", 22, "…"),
    )
    md = format_targets(ts)
    assert "Projected (pattern still open)" in md
    assert "additional Fibonacci levels" not in md  # nothing hidden → no omission note


def _pm(price: float, pct: float) -> PriceMove:
    return PriceMove(label="x", price=price, pct_from_current=pct)


def test_format_decision_summary_full_covers_every_field():
    ds = DecisionSummary(
        current=_pm(100.0, 0.0),
        target_low=_pm(110.0, 10.0), target_high=_pm(120.0, 20.0),
        invalidation=_pm(95.0, -5.0),
        risk_reward=2.5, direction="up",
        horizon_bars=8, bar_interval="1w", horizon_human="2 months",
        stage="mid", open_wave_start=90.0, open_wave_direction="up",
        wave_progress_pct=55.0,
    )
    md = format_decision_summary(ds)
    assert "$100.00" in md
    assert "$90.00" in md and "+11.1% to current" in md
    assert "↑ UP" in md
    assert "55% of the" in md
    assert "MID-WAVE" in md
    assert "Projection band" in md
    assert "Invalidation" in md
    assert "1 : 2.5" in md
    assert "Implied direction:** up" in md
    assert "8 bars" in md and "2 months" in md and "weekly chart" in md


def test_format_decision_summary_minimal_and_zero_start_guard():
    minimal = format_decision_summary(DecisionSummary(current=_pm(50.0, 0.0)))
    assert "$50.00" in minimal
    assert "Open wave started" not in minimal
    assert "Risk:Reward" not in minimal

    # open_wave_start == 0 → the `> 0` guard yields a 0% delta, not a divide error.
    zero = format_decision_summary(
        DecisionSummary(current=_pm(10.0, 0.0), open_wave_start=0.0)
    )
    assert "+0.0% to current" in zero


def _bd(slot: str = "leg_smoothness") -> BottleneckDiagnosis:
    return BottleneckDiagnosis(
        slot_name=slot, slot_value=0.2, dimension="visual",
        is_dim_minimum=True, is_overall_minimum=True, gap_to_next=0.1,
        intermediates={}, plain_explanation="…",
        theory_ref=TheoryRef(pages=(), concept="x", binding="heuristic", note="…"),
    )


def test_format_weakness_detail_returns_blank_when_nothing_to_show():
    assert format_weakness_detail(None, {"speed_cluster": 0.5}) == ""
    assert format_weakness_detail(_bd(), None) == ""
    assert format_weakness_detail(_bd(), {}) == ""
    assert format_weakness_detail(_bd(), {"not_a_slot": 0.5}) == ""  # no active slots


def test_format_weakness_detail_ranks_top3_with_detail_then_fallback():
    components = {
        "leg_smoothness": 0.2, "speed_cluster": 0.3, "pivot_sharpness": 0.4,
        "fib_push_pairs": 0.9,  # 4th — excluded from the top-3
    }
    inter = {"leg_smoothness": {"per_leg": [{"leg_idx": 1, "ratio": 0.45}]}}
    md = format_weakness_detail(_bd(), components, intermediates_map=inter)
    assert "Top-3 Weakness Detail" in md
    assert "Weakest — swing smoothness:" in md
    assert "leg 2" in md                         # leg_idx 1 → human "leg 2"
    assert "fib_push_pairs" not in md
    assert "ranked by score only" in md          # speed_cluster has no intermediates


def test_slot_detail_line_per_slot_and_empty():
    assert "spread" in _slot_detail_line("speed_cluster", {"leg_speeds": [1.0, 2.0]})
    assert "nearest Fibonacci" in _slot_detail_line(
        "fib_push_pairs", {"pairs": [{"pair": "s1/s3", "distance": 0.12}]}
    )
    assert "outside the healthy" in _slot_detail_line(
        "pull_depth_discipline", {"pairs": [{"depth": 0.9, "in_window": False}]}
    )
    assert "inside the 0.382-0.618" in _slot_detail_line(
        "pull_depth_discipline", {"pairs": [{"depth": 0.5, "in_window": True}]}
    )
    assert "drawdown ratio" in _slot_detail_line(
        "leg_smoothness", {"per_leg": [{"leg_idx": 0, "ratio": 0.3}]}
    )
    assert "dullest turning point" in _slot_detail_line(
        "pivot_sharpness", {"per_pivot": [{"pivot_idx": 2, "sharpness_score": 0.1}]}
    )
    # Missing intermediates / unknown slot → empty (caller renders the fallback line).
    assert _slot_detail_line("speed_cluster", {}) == ""
    assert _slot_detail_line("unknown_slot", {"x": 1}) == ""


def test_format_alternative_brief_full_and_minimal():
    full = format_alternative_brief(
        AlternativeBrief(
            family="3W", family_label="3-Wave",
            target_low=_pm(90.0, -10.0), target_high=_pm(110.0, 10.0),
            invalidation=_pm(80.0, -20.0), direction="down", stage="late",
        )
    )
    assert "Alternative Scenario" in full
    assert "3-Wave" in full
    assert "Implied direction (from current):** down" in full
    assert "LATE" in full
    assert "Projection band" in full and "Invalidation" in full

    minimal = format_alternative_brief(AlternativeBrief(family="3W", family_label="3-Wave"))
    assert "3-Wave" in minimal
    assert "Implied direction" not in minimal
    assert "Stage of its open wave" not in minimal
