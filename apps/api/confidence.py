"""Headline-score → confidence tier. Sole source — the web reads `confidence_tier` off the wire."""

from __future__ import annotations

from typing import NamedTuple


class ConfidenceTier(NamedTuple):
    key: str
    word: str


def confidence_tier(score: float) -> ConfidenceTier:
    # Bands aren't thirds: final = min(structural, visual) × commitment sits low.
    if score >= 0.50:
        return ConfidenceTier("high", "Strong")
    if score >= 0.25:
        return ConfidenceTier("mid", "Moderate")
    return ConfidenceTier("low", "Low")
