from __future__ import annotations

import math
from typing import TYPE_CHECKING

from engine.types import Bar, ScaleMode, WaveNode

from ..runtime import RuntimeContext
from ..scoring_config import CommitmentCurve, ScoringConfig
from ..types import _Hypothesis, _Leg
from .structural import (
    fib_push_pairs,
    fib_push_pairs_verbose,
    pull_depth_discipline,
    pull_depth_discipline_verbose,
    speed_cluster,
    speed_cluster_verbose,
)
from .visual import (
    leg_smoothness,
    leg_smoothness_verbose,
    pivot_sharpness,
    pivot_sharpness_verbose,
)

if TYPE_CHECKING:
    # Annotation only — output imports scoring, so a runtime import would cycle.
    from ..output import Scenario


def _commitment_factor(
    h: _Hypothesis, *, curve: CommitmentCurve = "linear",
) -> float:
    # Display-only — beam skips this so single-leg hypotheses survive to grow.
    if curve == "off":
        return 1.0
    target = h.root.min_legs_to_complete
    if target <= 0:
        return 0.0
    ratio = min(1.0, len(h.root.legs) / target)
    if curve == "sqrt":
        return math.sqrt(ratio)
    return ratio


def _select_display_legs(h: _Hypothesis) -> list[_Leg]:
    # First ctx with >=2 legs; else first single-leg ctx with sub_legs (early Link-Wave SET_1).
    for ctx in h.context_stack:
        if len(ctx.legs) >= 2:
            return ctx.legs
    for ctx in h.context_stack:
        if len(ctx.legs) == 1 and ctx.legs[0].sub_legs:
            return ctx.legs[0].sub_legs
    return h.root.legs


# (name, plain fn, verbose fn). Plain runs on the beam hot path; verbose only for display.
_STRUCTURAL_SLOTS = (
    ("speed_cluster", speed_cluster, speed_cluster_verbose),
    ("fib_push_pairs", fib_push_pairs, fib_push_pairs_verbose),
    ("pull_depth_discipline", pull_depth_discipline, pull_depth_discipline_verbose),
)
_VISUAL_SLOTS = (
    ("pivot_sharpness", pivot_sharpness, pivot_sharpness_verbose),
    ("leg_smoothness", leg_smoothness, leg_smoothness_verbose),
)

STRUCTURAL_SLOTS: tuple[str, ...] = tuple(name for name, _, _ in _STRUCTURAL_SLOTS)
VISUAL_SLOTS: tuple[str, ...] = tuple(name for name, _, _ in _VISUAL_SLOTS)


def _compute_components_from_legs(
    legs: list[_Leg],
    runtime: RuntimeContext,
    *,
    intermediates: dict | None = None,
) -> dict[str, float]:
    # intermediates given → verbose per-slot detail; else plain fns (hot beam path, no detail-dict alloc).
    out: dict[str, float] = {}
    config = runtime.scoring
    verbose = intermediates is not None

    struct_slot_values: list[float] = []
    for name, fn, verbose_fn in _STRUCTURAL_SLOTS:
        if verbose:
            v, inter = verbose_fn(legs, config)
        else:
            v = fn(legs, config)
        if v is not None:
            out[name] = v
            struct_slot_values.append(v)
            if verbose:
                intermediates[name] = inter
    out["structural_total"] = min(struct_slot_values) if struct_slot_values else 0.0

    if runtime.bars:
        bars = runtime.bars
        visual_slot_values: list[float] = []
        for name, fn, verbose_fn in _VISUAL_SLOTS:
            if verbose:
                v, inter = verbose_fn(legs, bars, config)
            else:
                v = fn(legs, bars, config)
            if v is not None:
                out[name] = v
                visual_slot_values.append(v)
                if verbose:
                    intermediates[name] = inter
        if visual_slot_values:
            out["visual_total"] = min(visual_slot_values)

    if "visual_total" in out:
        out["total"] = min(out["structural_total"], out["visual_total"])
    else:
        out["total"] = out["structural_total"]
    return out


def _apply_commitment(
    out: dict, h: _Hypothesis, runtime: RuntimeContext,
) -> dict:
    # total = quality * commitment so early scenarios can't outrank committed ones.
    quality = out["total"]
    out["quality"] = quality
    out["commitment"] = _commitment_factor(h, curve=runtime.scoring.commitment_curve)
    out["total"] = quality * out["commitment"]
    return out


# `mode` is unused below: structural/visual scores are ratios / log-CVs of price
# differences, so linear and log axes give the same score. Kept for engine-interface parity.
def _score_components(
    h: _Hypothesis,
    mode: ScaleMode,
    *,
    runtime: RuntimeContext,
) -> dict[str, float]:
    # Beam path: root.legs only — scoring inner sub-pattern legs biases toward nested.
    return _compute_components_from_legs(h.root.legs, runtime)


def _score_components_for_display(
    h: _Hypothesis,
    mode: ScaleMode,
    *,
    runtime: RuntimeContext,
) -> dict[str, float]:
    out = _compute_components_from_legs(_select_display_legs(h), runtime)
    return _apply_commitment(out, h, runtime)


def _score_components_verbose(
    h: _Hypothesis,
    mode: ScaleMode,
    *,
    runtime: RuntimeContext,
) -> dict:
    intermediates: dict = {}
    out = _compute_components_from_legs(
        _select_display_legs(h), runtime, intermediates=intermediates,
    )
    _apply_commitment(out, h, runtime)
    out["intermediates"] = intermediates
    return out


def _select_display_nodes(root: WaveNode) -> list[WaveNode]:
    # WaveNode analog of _select_display_legs: an early Link-Wave SET_1 wraps its
    # sub-legs in one child, so score those (root.children alone is 1 leg → no score).
    children = root.children
    if len(children) >= 2:
        return list(children)
    if len(children) == 1 and children[0].children:
        return list(children[0].children)
    return list(children)


def score_intermediates(
    scenario: Scenario,
    bars: list[Bar] | None,
    scoring: ScoringConfig | None = None,
) -> dict:
    # Public seam so callers outside the engine don't import scoring internals.
    # Keeps stored score_components; overlays an "intermediates" detail map.
    # Open legs (span_end=None, e.g. a Link-Wave's still-forming leg merged into the
    # root) have no settled length/speed and would crash the length-based scorers, so
    # they're excluded from the detail computation.
    legs = [lg for lg in _select_display_nodes(scenario.root) if lg.span_end is not None]
    cfg = scoring or ScoringConfig()
    out: dict = dict(scenario.score_components or {})
    intermediates: dict = {}
    for name, fn in (
        ("speed_cluster", speed_cluster_verbose),
        ("fib_push_pairs", fib_push_pairs_verbose),
        ("pull_depth_discipline", pull_depth_discipline_verbose),
    ):
        v, inter = fn(legs, cfg)
        if v is not None:
            intermediates[name] = inter
    if bars:
        bars_tuple = tuple(bars)
        for name, fn in (
            ("pivot_sharpness", pivot_sharpness_verbose),
            ("leg_smoothness", leg_smoothness_verbose),
        ):
            v, inter = fn(legs, bars_tuple, cfg)
            if v is not None:
                intermediates[name] = inter
    out["intermediates"] = intermediates
    return out
