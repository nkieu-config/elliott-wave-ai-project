from __future__ import annotations

import pytest

from engine.types import PatternKind
from engine.verifiers import verify_5wave_sideway
from tests.fixtures import build_5w_trend_segments, make_segments

_sideway = build_5w_trend_segments


@pytest.mark.parametrize(
    "lengths, expected",
    [
        ((100, 80, 60, 50, 30), PatternKind.FIVE_SIDEWAY_CONTRACT),
        ((100, 80, 100, 80, 50), PatternKind.FIVE_SIDEWAY_BALANCE),
        ((100, 80, 120, 100, 150), PatternKind.FIVE_SIDEWAY_EXPAND),
        ((100, 80, 40, 50, 30), PatternKind.FIVE_SIDEWAY_CONTRACT),
        ((100, 80, 60, 50, 11.8), PatternKind.FIVE_SIDEWAY_CONTRACT),
    ],
    ids=[
        "contract",
        "balance",
        "expand",
        "contract_boundary_r_s3_at_lower",
        "contract_boundary_r_s5_at_lower",
    ],
)
def test_sideway_kind_classification(lengths, expected) -> None:
    segs = _sideway(*lengths)
    result = verify_5wave_sideway(segs, "linear")
    assert result is not None
    assert result[0] == expected


def test_reject_not_5_segments() -> None:
    segs = make_segments([100, 120, 110, 130])
    assert verify_5wave_sideway(segs, "linear") is None


@pytest.mark.parametrize(
    "lengths",
    [
        (100, 30, 50, 50, 30),
        (100, 300, 100, 100, 50),
        (100, 80, 100, 30, 50),
        (100, 80, 60, 50, 5),
        (100, 80, 70, 50, 120),
    ],
    ids=[
        "s2_too_small",
        "s2_too_large",
        "s4_too_small",
        "no_subtype_match",
        # s3 contracts (r32=0.875) but s5 expands (r54=2.4) → matches no subtype → None.
        "s3_contracts_s5_expands_deadzone",
    ],
)
def test_sideway_rejects(lengths) -> None:
    segs = _sideway(*lengths)
    assert verify_5wave_sideway(segs, "linear") is None


def test_works_starting_down() -> None:
    p = [100.0]
    p.append(p[-1] - 100)
    p.append(p[-1] + 80)
    p.append(p[-1] - 60)
    p.append(p[-1] + 50)
    p.append(p[-1] - 30)
    segs = make_segments(p)
    result = verify_5wave_sideway(segs, "linear")
    assert result is not None
    assert result[0] == PatternKind.FIVE_SIDEWAY_CONTRACT
