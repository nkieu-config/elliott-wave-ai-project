from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from engine.parser.scoring.components import _select_display_nodes, score_intermediates
from engine.types import Pivot, WaveNode

_T = datetime(2024, 1, 1)


def _pv(idx: int, price: float, bar: int) -> Pivot:
    return Pivot(idx, _T, float(price), "low", bar)


def _wave(start: Pivot | None = None, end: Pivot | None = None,
          children: list[WaveNode] | None = None) -> WaveNode:
    return WaveNode(
        role="s1", span_start=start or _pv(0, 100.0, 0),
        span_end=end, children=children or [],
    )


def _leg(bar0: int, bar1: int, p0: float, p1: float) -> WaveNode:
    return _wave(start=_pv(bar0, p0, bar0), end=_pv(bar1, p1, bar1))


# ── _select_display_nodes: WaveNode analog of _select_display_legs ──


def test_select_display_nodes_uses_children_when_multiple():
    kids = [_wave(), _wave()]
    out = _select_display_nodes(_wave(children=kids))
    assert [id(n) for n in out] == [id(kids[0]), id(kids[1])]


def test_select_display_nodes_unwraps_single_wrapper_set1():
    # Early Link-Wave SET_1: one wrapper child → score its sub-legs, not the wrapper.
    sub = [_wave(), _wave(), _wave()]
    root = _wave(children=[_wave(children=sub)])
    out = _select_display_nodes(root)
    assert [id(n) for n in out] == [id(s) for s in sub]


def test_select_display_nodes_single_leaf_falls_back_to_children():
    leaf = _wave()  # no grandchildren
    out = _select_display_nodes(_wave(children=[leaf]))
    assert [id(n) for n in out] == [id(leaf)]


# ── score_intermediates: SET_1 no longer yields an empty detail map ──

_LEGS = [_leg(0, 2, 100, 110), _leg(2, 5, 110, 104), _leg(5, 9, 104, 120)]


def test_score_intermediates_set1_is_not_empty():
    # Regression: root.children == [wrapper] previously gave every slot <2 legs → {}.
    root = _wave(children=[_wave(children=list(_LEGS))])
    sc = SimpleNamespace(root=root, score_components={})
    inter = score_intermediates(sc, bars=None)["intermediates"]
    assert inter, "SET_1 wrapper sub-legs should produce intermediates"


def test_score_intermediates_normal_unaffected():
    sc = SimpleNamespace(root=_wave(children=list(_LEGS)), score_components={})
    inter = score_intermediates(sc, bars=None)["intermediates"]
    assert inter


def test_score_intermediates_skips_open_leg_without_crashing():
    # A Link-Wave's still-forming leg is merged into root.children with span_end=None.
    # The length-based scorers would deref span_end and crash — the open leg must be
    # dropped from the detail computation (would 500 /scenario/layer1 otherwise).
    open_leg = _wave(start=_pv(9, 120, 9), end=None)
    root = _wave(children=[*_LEGS, open_leg])
    sc = SimpleNamespace(root=root, score_components={})
    inter = score_intermediates(sc, bars=None)["intermediates"]
    assert inter  # still scored from the three closed legs
