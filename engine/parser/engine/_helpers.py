from __future__ import annotations

from engine.parser.types import _Leg
from engine.types import Segment, WaveRole


def _seg_to_leg(seg: Segment, role: WaveRole) -> _Leg:
    return _Leg(role=role, span_start=seg.start, span_end=seg.end)
