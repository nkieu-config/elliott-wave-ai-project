import pytest

from analyst.diagnostics.succession import compute_succession
from engine.types import LinkSet, PatternKind
from tests.analyst._helpers import make_scenario


def _scenario(prices, family, pattern_kind=None, sets=None):
    pivots = [
        (p, i * 10, "low" if i % 2 == 0 else "high")
        for i, p in enumerate(prices)
    ]
    return make_scenario(
        family=family,
        pattern_kind=pattern_kind,
        pivots=pivots,
        score=0.4,
        scenario_id="s",
        score_components={},
        sets=sets or [],
    )


def test_5w_trend_is_terminal():
    sc = _scenario([100, 200, 180, 300, 260, 400], "5W_TREND",
                   PatternKind.FIVE_TREND_S3_LONGEST)
    rep = compute_succession(sc)
    assert rep.is_terminal is True
    assert rep.next_patterns == ()
    assert "p.59" in rep.note and "p.67" in rep.note


def test_3w_offers_both_t_and_s_links():
    sc = _scenario([100, 120, 110, 130], "3W", PatternKind.THREE_NORMAL)
    rep = compute_succession(sc)
    assert rep.is_terminal is False
    by_type = {pat.link_type: pat for pat in rep.next_patterns}
    assert set(by_type) == {"+T", "+S"}
    assert by_type["+T"].next_families == ("3W",)
    assert set(by_type["+S"].next_families) == {"3W", "5W_SIDEWAY"}


@pytest.mark.parametrize("family", ["LINK_T", "LINK_S"])
def test_open_link_root_with_no_sets_does_not_crash(family):
    # An open link root (first set not yet closed) has root.sets=None; compute_layer1
    # calls this unconditionally, so a crash here 500s the /scenario/layer1 route.
    sc = make_scenario(family=family, pattern_kind=None,
                       pivots=[(100, 0, "low"), (130, 10, "high"), (110, 20, "low")],
                       sets=None)
    assert sc.root.sets is None
    rep = compute_succession(sc)  # must not raise
    assert rep.family == family
    assert rep.is_terminal is False


def test_link_s_extension_uses_101pct_when_last_set_is_contract():
    # +S extension after a LINK_S must size off the last set's kind: a 5WS
    # Contract/Balance last set requires 101% of its range (p.74), not 78.6%.
    pivots = [(100, 0, "low"), (120, 10, "high"), (110, 20, "low"),
              (130, 30, "high"), (115, 40, "low"), (150, 50, "high")]
    sc = make_scenario(family="LINK_S", pattern_kind=None, pivots=pivots,
                       score_components={})
    sc.root.sets = [
        LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2),
        LinkSet(pattern_kind=PatternKind.FIVE_SIDEWAY_CONTRACT, leg_start=3, leg_end=5),
    ]
    s = {p.link_type: p for p in compute_succession(sc).next_patterns}["+S"]
    assert 74 in s.theory_pages
    assert s.link_wave_size == pytest.approx(35 * 1.01)


def test_3w_plus_t_band_is_counter_trend_within_s3_fractions():
    sc = _scenario([100, 120, 110, 130], "3W", PatternKind.THREE_NORMAL)
    t = {pat.link_type: pat for pat in compute_succession(sc).next_patterns}["+T"]
    assert t.link_band_near == 130 - 0.01 * 20
    assert t.link_band_far == 130 - 0.618 * 20
    assert 64 in t.theory_pages


def test_3w_plus_s_is_open_ended_above():
    sc = _scenario([100, 120, 110, 130], "3W", PatternKind.THREE_NORMAL)
    s = {pat.link_type: pat for pat in compute_succession(sc).next_patterns}["+S"]
    assert s.link_band_near is not None
    assert s.link_band_far is None
    assert 73 in s.theory_pages


def test_5w_sideway_offers_only_plus_s():
    sc = _scenario([100, 130, 105, 128, 98], "5W_SIDEWAY",
                   PatternKind.FIVE_SIDEWAY_BALANCE)
    rep = compute_succession(sc)
    assert rep.is_terminal is False
    assert [pat.link_type for pat in rep.next_patterns] == ["+S"]


def test_5w_sideway_balance_cites_p74_contract_balance_rule():
    sc = _scenario([100, 130, 105, 128, 98], "5W_SIDEWAY",
                   PatternKind.FIVE_SIDEWAY_BALANCE)
    pat0 = compute_succession(sc).next_patterns[0]
    assert 74 in pat0.theory_pages


def test_5w_sideway_expand_cites_p73_s5_rule():
    sc = _scenario([100, 130, 105, 135, 95], "5W_SIDEWAY",
                   PatternKind.FIVE_SIDEWAY_EXPAND)
    pat0 = compute_succession(sc).next_patterns[0]
    assert 73 in pat0.theory_pages


def test_link_t_with_two_sets_can_extend():
    sets = [LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2),
            LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=4, leg_end=6)]
    sc = _scenario([100, 120, 110, 130, 125, 145, 138, 160], "LINK_T",
                   PatternKind.LINK_T, sets=sets)
    rep = compute_succession(sc)
    assert rep.is_terminal is False
    assert [pat.link_type for pat in rep.next_patterns] == ["+T"]


def test_link_t_extension_band_from_last_set_s3():
    sets = [LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2),
            LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=4, leg_end=6)]
    sc = _scenario([100, 120, 110, 130, 125, 145, 138, 160], "LINK_T",
                   PatternKind.LINK_T, sets=sets)
    pat0 = compute_succession(sc).next_patterns[0]
    assert pat0.link_band_near == pytest.approx(160 - 0.01 * 22)
    assert pat0.link_band_far == pytest.approx(160 - 0.618 * 22)
    assert 64 in pat0.theory_pages


def test_link_s_extension_band_is_open_ended():
    sets = [LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2),
            LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=4, leg_end=6)]
    sc = _scenario([100, 120, 110, 130, 125, 145, 138, 160], "LINK_S",
                   PatternKind.LINK_S, sets=sets)
    pat0 = compute_succession(sc).next_patterns[0]
    assert pat0.link_type == "+S"
    assert pat0.link_band_near is not None
    assert pat0.link_band_far is None
    assert 73 in pat0.theory_pages


def test_link_t_with_three_sets_is_terminal():
    sets = [LinkSet(pattern_kind=PatternKind.THREE_NORMAL, leg_start=0, leg_end=2)] * 3
    sc = _scenario([100, 120, 110, 130], "LINK_T", PatternKind.LINK_T, sets=sets)
    rep = compute_succession(sc)
    assert rep.is_terminal is True
    assert "3 sets" in rep.note


def test_succession_band_withheld_while_pattern_open():
    sc = _scenario([100, 130, 105, 118, 98], "5W_SIDEWAY")
    assert sc.is_complete is False
    rep = compute_succession(sc)
    assert rep.next_patterns
    pat0 = rep.next_patterns[0]
    assert pat0.link_band_near is None
    assert pat0.link_band_far is None
    assert "once this pattern completes" in pat0.rationale


def test_succession_band_kept_when_pattern_complete():
    sc = _scenario([100, 120, 110, 130], "3W", PatternKind.THREE_NORMAL)
    assert sc.is_complete is True
    t = {n.link_type: n for n in compute_succession(sc).next_patterns}["+T"]
    assert t.link_band_near is not None
    assert "once this pattern completes" not in t.rationale
