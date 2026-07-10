from __future__ import annotations

from datetime import datetime, timedelta

from engine.degree import assign_degree_labels
from engine.parser import count_waves
from engine.types import (
    DegreeLabel,
    PatternKind,
    Pivot,
    WaveNode,
    WaveRole,
)
from tests.fixtures import make_segments


def test_label_root_and_children_are_primary() -> None:
    base = datetime(2020, 1, 1)
    p0 = Pivot(0, base, 100.0, "low", 0)
    p1 = Pivot(1, base + timedelta(weeks=1), 130.0, "high", 1)
    p2 = Pivot(2, base + timedelta(weeks=2), 115.0, "low", 2)
    p3 = Pivot(3, base + timedelta(weeks=3), 145.0, "high", 3)
    root = WaveNode(
        role=WaveRole.ANCHOR,
        span_start=p0,
        span_end=p3,
        pattern_kind=PatternKind.THREE_NORMAL,
        children=[
            WaveNode(role=WaveRole.S1, span_start=p0, span_end=p1),
            WaveNode(role=WaveRole.S2, span_start=p1, span_end=p2),
            WaveNode(role=WaveRole.S3, span_start=p2, span_end=p3),
        ],
    )
    assign_degree_labels(root)
    assert root.degree_label == DegreeLabel.PRIMARY
    for child in root.children:
        assert child.degree_label == DegreeLabel.PRIMARY


def test_label_nested_pattern_children_are_secondary() -> None:
    base = datetime(2020, 1, 1)
    p0 = Pivot(0, base, 100.0, "low", 0)
    p1 = Pivot(1, base + timedelta(weeks=1), 130.0, "high", 1)
    p2 = Pivot(2, base + timedelta(weeks=2), 115.0, "low", 2)
    p3 = Pivot(3, base + timedelta(weeks=3), 145.0, "high", 3)
    # Sub-pattern (3W) inside a leg of an outer 5W_TREND
    sub_pattern = WaveNode(
        role=WaveRole.S3,
        span_start=p0,
        span_end=p3,
        pattern_kind=PatternKind.THREE_NORMAL,
        children=[
            WaveNode(role=WaveRole.S1, span_start=p0, span_end=p1),
            WaveNode(role=WaveRole.S2, span_start=p1, span_end=p2),
            WaveNode(role=WaveRole.S3, span_start=p2, span_end=p3),
        ],
    )
    root = WaveNode(
        role=WaveRole.ANCHOR,
        span_start=p0,
        span_end=p3,
        pattern_kind=PatternKind.FIVE_TREND_S3_LONGEST,
        children=[sub_pattern],
    )
    assign_degree_labels(root)
    assert root.degree_label == DegreeLabel.PRIMARY
    assert sub_pattern.degree_label == DegreeLabel.PRIMARY
    for inner in sub_pattern.children:
        assert inner.degree_label == DegreeLabel.SECONDARY


def test_label_no_op_on_none() -> None:
    assign_degree_labels(None)


def test_open_subtree_labels_children_secondary_and_never_none() -> None:
    # #5/#6: the open subtree is a root-child leg (PRIMARY), so its waves are
    # SECONDARY — and an open (pattern_kind=None) sub-wave's descendants must still
    # be labeled rather than left None (which renders blank in the UI).
    base = datetime(2020, 1, 1)

    def p(i: int, price: float, kind: str) -> Pivot:
        return Pivot(i, base + timedelta(weeks=i), price, kind, i)  # type: ignore[arg-type]

    open_sub = WaveNode(
        role=WaveRole.S3,
        span_start=p(0, 100, "low"),
        span_end=None,
        pattern_kind=None,
        children=[
            WaveNode(role=WaveRole.S1, span_start=p(0, 100, "low"), span_end=p(1, 120, "high")),
            WaveNode(
                role=WaveRole.S2,
                span_start=p(1, 120, "high"),
                span_end=None,
                pattern_kind=None,
                children=[
                    WaveNode(role=WaveRole.S1, span_start=p(1, 120, "high"), span_end=p(2, 110, "low")),
                ],
            ),
        ],
    )
    assign_degree_labels(open_sub, children_level=1)

    assert open_sub.degree_label == DegreeLabel.PRIMARY
    assert all(c.degree_label == DegreeLabel.SECONDARY for c in open_sub.children)
    assert open_sub.children[1].children[0].degree_label == DegreeLabel.MINOR


def test_e2e_size_consistent_3w_completes_with_primary_labels() -> None:
    segs = make_segments([100, 130, 115, 145])
    report = count_waves(segs[0].start, segs, "linear")
    complete_3w = [sc for sc in report.scenarios if sc.family == "3W" and sc.is_complete]
    assert complete_3w
    sc = complete_3w[0]
    assert sc.root.degree_label == DegreeLabel.PRIMARY
    for child in sc.root.children:
        assert child.degree_label == DegreeLabel.PRIMARY


def test_e2e_size_mismatch_blocks_3w_completion() -> None:
    segs = make_segments([100, 110, 105, 1105])
    report = count_waves(segs[0].start, segs, "linear")
    complete_3w = [sc for sc in report.scenarios if sc.family == "3W" and sc.is_complete]
    assert not complete_3w, "size-mismatched 3W must not complete at parse time"
