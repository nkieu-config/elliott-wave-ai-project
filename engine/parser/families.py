# Family registry. High module (imports verifiers + gates): must NOT be imported
# by parser/types or gates (lower) — would cycle.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.adaptive import Family
from engine.parser.gates import (
    _incremental_ok_5w_trend,
    _incremental_ok_link_s,
    _incremental_ok_link_t,
    _link_t_open_size_ok,
    _link_t_r7_close_ok,
    _ratio_band_ok,
    _RatioBand,
    bands_for_family,
)
from engine.parser.leg_structure import LEG_STRUCTURE, LegStructure
from engine.parser.types import _Leg
from engine.parser.wave_shape import flatten_linkwave, leg_to_wavenode, legs_to_segments
from engine.types import LinkSet, PatternKind, RuleResult, ScaleMode, Segment, WaveNode, WaveRole
from engine.verifiers import (
    verify_3wave,
    verify_5wave_sideway,
    verify_5wave_trend,
    verify_link_s,
    verify_link_t,
)

if TYPE_CHECKING:
    from engine.parser.types import _Context

Verdict = tuple[PatternKind, list[RuleResult]] | None

# The two shapes a verifier reads. A pattern is a run of segments; a linkwave is sets
# of sub-waves with the links between them.
SimpleVerifier = Callable[[list[Segment], ScaleMode], Verdict]
LinkVerifier = Callable[[list[LinkSet], list[WaveNode], list[Segment], ScaleMode], Verdict]

# What the registry exposes: legs in, verdict out. Each family binds its own input
# shape at construction (below), so the beam loop never dispatches on it.
VerifierFn = Callable[[list[_Leg], ScaleMode], Verdict]

IncrementalFn = Callable[["_Context", WaveRole, float, ScaleMode, "int | None"], bool]
OpenPregateFn = Callable[["_Context", WaveRole, Segment, ScaleMode], bool]
ClosePregateFn = Callable[["_Context", "_Context", WaveRole, ScaleMode], bool]


def _simple(verifier: SimpleVerifier) -> VerifierFn:
    def run(legs: list[_Leg], mode: ScaleMode) -> Verdict:
        return verifier(legs_to_segments(legs), mode)

    return run


def _link(verifier: LinkVerifier) -> VerifierFn:
    def run(legs: list[_Leg], mode: ScaleMode) -> Verdict:
        children, sets, links = flatten_linkwave(legs, leg_to_wavenode)
        return verifier(sets, children, links, mode)

    return run


@dataclass(frozen=True)
class FamilySpec:
    family: Family
    structure: LegStructure
    verifier: VerifierFn
    incremental: IncrementalFn
    is_root: bool
    set1_inner_families: tuple[Family, ...]
    open_pregate: OpenPregateFn | None = None
    close_pregate: ClosePregateFn | None = None


# Families whose incremental rule is a strict-inequality / degree handler (not a band).
_SPECIFIC_INCREMENTAL: dict[Family, IncrementalFn] = {
    "5W_TREND": _incremental_ok_5w_trend,
    "LINK_T": _incremental_ok_link_t,
    "LINK_S": _incremental_ok_link_s,
    "LINK_SE": _incremental_ok_link_s,
}


def _band_handler(bands: dict[WaveRole, _RatioBand]) -> IncrementalFn:
    def handler(ctx: _Context, role: WaveRole, leg_length: float, mode: ScaleMode, leg_bars: int | None) -> bool:
        band = bands.get(role)
        return True if band is None else _ratio_band_ok(ctx, leg_length, mode, band)

    return handler


def _incremental_for(family: Family) -> IncrementalFn:
    bands = bands_for_family(family)
    return _band_handler(bands) if bands else _SPECIFIC_INCREMENTAL[family]


def _spec(
    family: Family,
    verifier: VerifierFn,
    *,
    is_root: bool,
    set1: tuple[Family, ...] = (),
    open_pregate: OpenPregateFn | None = None,
    close_pregate: ClosePregateFn | None = None,
) -> FamilySpec:
    return FamilySpec(
        family=family,
        structure=LEG_STRUCTURE[family],
        verifier=verifier,
        incremental=_incremental_for(family),
        is_root=is_root,
        set1_inner_families=set1,
        open_pregate=open_pregate,
        close_pregate=close_pregate,
    )


# Insertion order is load-bearing: the seed family sets below derive root / set_1 order from it.
FAMILY_SPECS: dict[Family, FamilySpec] = {
    "5W_TREND": _spec("5W_TREND", _simple(verify_5wave_trend), is_root=True),
    "5W_SIDEWAY": _spec("5W_SIDEWAY", _simple(verify_5wave_sideway), is_root=True),
    "3W": _spec("3W", _simple(verify_3wave), is_root=True),
    "LINK_T": _spec(
        "LINK_T",
        _link(verify_link_t),
        is_root=True,
        set1=("3W",),
        open_pregate=_link_t_open_size_ok,
        close_pregate=_link_t_r7_close_ok,
    ),
    "LINK_S": _spec("LINK_S", _link(verify_link_s), is_root=True, set1=("3W", "5W_SIDEWAY")),
    # LINK_SE is verify-only — emerges from verify_link_s promotion, never seeded.
    "LINK_SE": _spec("LINK_SE", _link(verify_link_s), is_root=False),
}


def run_verifier(family: Family, legs: list[_Leg], mode: ScaleMode) -> Verdict:
    spec = FAMILY_SPECS.get(family)
    if spec is None:
        return None
    return spec.verifier(legs, mode)


def incremental_ok(
    ctx: _Context,
    role: WaveRole,
    leg_length: float,
    mode: ScaleMode,
    leg_bars: int | None = None,
) -> bool:
    spec = FAMILY_SPECS.get(ctx.family)
    if spec is None:
        return True
    return spec.incremental(ctx, role, leg_length, mode, leg_bars)


def open_pregate_ok(ctx: _Context, role: WaveRole, seg: Segment, mode: ScaleMode) -> bool:
    spec = FAMILY_SPECS.get(ctx.family)
    if spec is None or spec.open_pregate is None:
        return True
    return spec.open_pregate(ctx, role, seg, mode)


def close_pregate_ok(
    closed: _Context, parent_ctx: _Context, parent_role: WaveRole, mode: ScaleMode
) -> bool:
    # Keyed on the PARENT family.
    spec = FAMILY_SPECS.get(parent_ctx.family)
    if spec is None or spec.close_pregate is None:
        return True
    return spec.close_pregate(closed, parent_ctx, parent_role, mode)


# Seed family sets, derived from FAMILY_SPECS (single source).
ROOT_FAMILIES: tuple[Family, ...] = tuple(f for f, s in FAMILY_SPECS.items() if s.is_root)
SIMPLE_ROOT_FAMILIES: tuple[Family, ...] = tuple(
    f for f, s in FAMILY_SPECS.items() if s.is_root and not s.structure.is_link
)
KNOWN_SUB_FAMILIES: frozenset[Family] = frozenset(
    f for f, s in FAMILY_SPECS.items() if not s.structure.is_link
)
LINK_INNER_SET1_FAMILIES: dict[Family, tuple[Family, ...]] = {
    f: s.set1_inner_families for f, s in FAMILY_SPECS.items() if s.is_root and s.structure.is_link
}
