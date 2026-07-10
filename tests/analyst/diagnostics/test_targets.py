from dataclasses import fields as dc_fields
from dataclasses import replace

from analyst.diagnostics.targets import compute_targets
from engine.parser.output.types import Scenario
from engine.types import LinkSet, OpenState, PatternKind, WaveNode, WaveRole
from tests.analyst._helpers import _pv, make_scenario


def _build_5wt(subtype):
    return make_scenario(
        family="5W_TREND",
        pattern_kind=subtype,
        pivots=[
            (100.0, 0, "low"),
            (200.0, 40, "high"),
            (180.0, 50, "low"),
            (300.0, 100, "high"),
            (260.0, 130, "low"),
            (400.0, 200, "high"),
        ],
        score=0.5,
        scenario_id="t",
        score_components={},
    )


def test_5wt_s3_longest_has_three_internal_pair_targets():
    sc = _build_5wt(PatternKind.FIVE_TREND_S3_LONGEST)
    ts = compute_targets(sc)
    derivations = {t.derivation for t in ts.fib_flow_targets}
    assert any("s1 → s3" in d for d in derivations)
    assert any("s1 → s5" in d for d in derivations)
    assert any("s3 → s5" in d for d in derivations)
    assert all(t.theory_page == 110 for t in ts.fib_flow_targets)


def test_targets_never_serialize_non_positive_prices():
    # A deep extension of a large down leg would compute a $-X price; such a level
    # is not real and must be dropped (this fixture would produce one un-clamped).
    sc = make_scenario(
        family="5W_TREND", pattern_kind=PatternKind.FIVE_TREND_S3_LONGEST,
        pivots=[(100, 0, "high"), (40, 40, "low"), (55, 50, "high"),
                (15, 100, "low"), (30, 130, "high"), (5, 200, "low")],
        score_components={},
    )
    ts = compute_targets(sc)
    all_targets = []
    for f in dc_fields(ts):
        v = getattr(ts, f.name)
        if isinstance(v, (list, tuple)):
            all_targets.extend(t for t in v if hasattr(t, "price"))
    assert all_targets
    assert all(t.price > 0 for t in all_targets)


def test_5wt_s5_longest_uses_combined_s1_s3_internal():
    sc = _build_5wt(PatternKind.FIVE_TREND_S5_LONGEST)
    ts = compute_targets(sc)
    derivations = {t.derivation for t in ts.fib_flow_targets}
    assert any("s1+s3 → s5" in d for d in derivations)
    assert any("s1 → s3 internal" in d for d in derivations)
    assert any("s3 → s5 internal" in d for d in derivations)
    assert all(t.theory_page == 110 for t in ts.fib_flow_targets)


def test_5wt_s5_shorter_adds_s4_retracement_flow():
    sc = _build_5wt(PatternKind.FIVE_TREND_S5_SHORTER)
    ts = compute_targets(sc)
    derivations = {t.derivation for t in ts.fib_flow_targets}
    assert any("s4 → s5" in d for d in derivations)
    assert any("s1 → s3 internal" in d for d in derivations)
    assert {"internal", "retracement"} <= {t.type for t in ts.fib_flow_targets}


def test_5wt_equal_push_emits_no_flow_but_keeps_confirmation():
    sc = _build_5wt(PatternKind.FIVE_TREND_EQUAL_PUSH)
    ts = compute_targets(sc)
    assert ts.fib_flow_targets == ()
    assert {t.name for t in ts.confirmation_targets} == {
        "s5_retrace_100", "full_set_retrace_61.8", "full_set_retrace_100",
    }


def test_5wt_has_invalidation_target():
    sc = _build_5wt(PatternKind.FIVE_TREND_S3_LONGEST)
    ts = compute_targets(sc)
    assert ts.invalidation.price == 400.0
    assert ts.invalidation.type == "invalidation"


def test_5wt_confirmation_targets_when_closed():
    sc = _build_5wt(PatternKind.FIVE_TREND_S3_LONGEST)
    ts = compute_targets(sc)
    names = {t.name for t in ts.confirmation_targets}
    assert "s5_retrace_100" in names
    assert "full_set_retrace_61.8" in names
    assert "full_set_retrace_100" in names


def _build_3w():
    return make_scenario(
        family="3W",
        pattern_kind=PatternKind.THREE_NORMAL,
        pivots=[
            (100.0, 0, "low"),
            (120.0, 30, "high"),
            (110.0, 60, "low"),
            (130.0, 100, "high"),
        ],
        score=0.3,
        scenario_id="t3",
        score_components={},
    )


def test_3w_targets_use_s1_internal():
    sc = _build_3w()
    ts = compute_targets(sc)
    derivations = {t.derivation for t in ts.fib_flow_targets}
    assert any("s1 → s3 internal" in d for d in derivations)
    assert all(t.theory_page in (104, 112) for t in ts.fib_flow_targets)


def test_5ws_targets_use_retracement_only():
    sc_legs = _build_5wt(PatternKind.FIVE_SIDEWAY_BALANCE)
    sc_legs = replace(sc_legs, _family="5W_SIDEWAY")
    ts = compute_targets(sc_legs)
    for t in ts.fib_flow_targets:
        assert t.type == "retracement"


def _build_link_t_2_set():
    pivots = [
        _pv(0, 100.0, 0, "low"),
        _pv(1, 120.0, 20, "high"),
        _pv(2, 110.0, 40, "low"),
        _pv(3, 140.0, 60, "high"),
        _pv(4, 130.0, 80, "low"),
        _pv(5, 150.0, 100, "high"),
        _pv(6, 140.0, 120, "low"),
        _pv(7, 170.0, 140, "high"),
    ]
    root = WaveNode(
        role=WaveRole.ANCHOR, span_start=pivots[0], span_end=pivots[7],
        pattern_kind=PatternKind.LINK_T,
        sets=[
            LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2),
            LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=4, leg_end=6),
        ],
    )
    roles = [WaveRole.S1, WaveRole.S2, WaveRole.S3, WaveRole.LINK,
             WaveRole.S1, WaveRole.S2, WaveRole.S3]
    for i, role in enumerate(roles):
        leg = WaveNode(role=role, span_start=pivots[i], span_end=pivots[i+1])
        root.children.append(leg)
    return Scenario(id="lt2", root=root, score=0.4, open_state=OpenState(), _family="LINK_T")


def test_link_t_targets_use_prev_s3_to_next_s1():
    sc = _build_link_t_2_set()
    ts = compute_targets(sc)
    derivations = {t.derivation for t in ts.fib_flow_targets}
    assert any("prev_set.s3 → next_set.s1" in d for d in derivations)
    assert all(t.theory_page in (105, 113) for t in ts.fib_flow_targets)


def test_link_s_has_only_retracement_targets():
    sc = _build_link_t_2_set()
    sc = replace(sc, _family="LINK_S")
    sc.root.pattern_kind = PatternKind.LINK_S
    ts = compute_targets(sc)
    for t in ts.fib_flow_targets:
        assert t.type == "retracement"


def _build_incomplete_5ws():
    return make_scenario(
        family="5W_SIDEWAY",
        pattern_kind=None,
        pivots=[
            (100.0, 0, "low"),
            (120.0, 20, "high"),
            (105.0, 40, "low"),
            (118.0, 60, "high"),
            (98.01, 80, "low"),
        ],
        score=0.3,
        scenario_id="ws4",
        score_components={},
    )


def test_incomplete_5ws_invalidation_carries_family_theory_page():
    sc = _build_incomplete_5ws()
    ts = compute_targets(sc)
    assert ts.invalidation.type == "invalidation"
    assert ts.invalidation.theory_page == 22
    assert "last known pivot" not in ts.invalidation.derivation


def test_link_default_invalidation_has_no_theory_page():
    sc = _build_link_t_2_set()
    sc = replace(sc, _family="LINK_T")
    sc.root.sets = []
    ts = compute_targets(sc)
    assert ts.invalidation.theory_page == 0


def _build_5w_4legs(family):
    return make_scenario(
        family=family,
        pattern_kind=None,
        pivots=[
            (100.0, 0, "low"),
            (170.0, 30, "high"),
            (130.0, 50, "low"),
            (170.08, 80, "high"),
            (98.01, 110, "low"),
        ],
        score=0.3,
        scenario_id="w4",
        score_components={},
    )


def test_open_5ws_projects_wave5_as_projected_retracements():
    sc = _build_5w_4legs("5W_SIDEWAY")
    ts = compute_targets(sc)
    assert ts.fib_flow_targets
    assert all(t.type == "projected" for t in ts.fib_flow_targets)
    assert all(t.theory_page == 111 for t in ts.fib_flow_targets)
    assert all(t.price >= 98.01 for t in ts.fib_flow_targets)
    assert ts.confirmation_targets == ()


def test_open_5wt_projects_wave5_as_projected_internals():
    sc = _build_5w_4legs("5W_TREND")
    ts = compute_targets(sc)
    assert ts.fib_flow_targets
    assert all(t.type == "projected" for t in ts.fib_flow_targets)
    assert all(t.theory_page == 110 for t in ts.fib_flow_targets)
    stems = {t.name.rsplit("_", 1)[0] for t in ts.fib_flow_targets}
    assert any("s1" in s for s in stems)
    assert any("s3" in s for s in stems)


def test_5w_with_three_legs_is_still_too_early_to_project():
    sc = make_scenario(
        family="5W_SIDEWAY",
        pattern_kind=None,
        pivots=[(100.0 + i * 10, i * 10, "high") for i in range(4)],
        score=0.3,
        scenario_id="w3",
        score_components={},
    )
    ts = compute_targets(sc)
    assert ts.fib_flow_targets == ()


def test_default_invalidation_survives_empty_legs():
    # Incomplete scenario, zero closed legs: invalidation must fall back to the
    # anchor (last confirmed pivot), not a fabricated 0.0 that reads as a live $0.
    root = WaveNode(
        role=WaveRole.ANCHOR,
        span_start=_pv(0, 100.0, 0, "low"),
        span_end=None,
        pattern_kind=None,
    )
    sc = Scenario(id="empty", root=root, score=0.0, open_state=OpenState(), _family="3W")
    sc.score_components = {}
    ts = compute_targets(sc)
    assert ts.invalidation.type == "invalidation"
    assert ts.invalidation.price == 100.0  # the anchor, not 0.0
