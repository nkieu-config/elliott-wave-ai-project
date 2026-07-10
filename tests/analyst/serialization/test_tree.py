from datetime import datetime

from analyst.serialization.tree import format_tree
from engine.types import PatternKind, Pivot, WaveNode, WaveRole


def test_format_tree_root_with_5_legs():
    def pv(p, t=datetime(2020, 1, 1)):
        return Pivot(index=0, time=t, price=p, kind="high", bar_index=0)
    root = WaveNode(
        role=WaveRole.ANCHOR, span_start=pv(100), span_end=pv(200),
        pattern_kind=PatternKind.FIVE_TREND_S3_LONGEST,
    )
    for i, p in enumerate([(100, 140), (140, 120), (120, 180), (180, 150), (150, 200)]):
        leg = WaveNode(role=WaveRole(f"s{i+1}"), span_start=pv(p[0]), span_end=pv(p[1]))
        root.children.append(leg)
    text = format_tree(root, family="5W_TREND")
    assert "[5-Wave Trend ·" in text
    assert "s1" in text and "s5" in text
    assert "→" in text


def test_format_tree_open_leg_renders_neutral_direction():
    def pv(p):
        return Pivot(index=0, time=datetime(2020, 1, 1), price=p, kind="low", bar_index=0)
    root = WaveNode(role=WaveRole.ANCHOR, span_start=pv(100), span_end=pv(120),
                    pattern_kind=None)
    # Open leg (span_end=None) must not render a false "↓".
    root.children.append(WaveNode(role=WaveRole.S1, span_start=pv(100), span_end=None))
    text = format_tree(root, family="5W_TREND")
    assert "·" in text
    assert "↓" not in text
