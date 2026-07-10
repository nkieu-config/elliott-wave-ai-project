from __future__ import annotations

from dataclasses import replace

from analyst.schemas.targets import Target, TargetSet
from analyst.theory.citation_map import family_invalidation_pages
from engine import PatternKind, Scenario, WaveNode

_INTERNAL_LEVELS = (1.0, 1.236, 1.382, 1.618, 2.0)
_RETRACE_LEVELS = (0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def _direction_sign(leg: WaveNode) -> int:
    return 1 if leg.span_end.price > leg.span_start.price else -1


def _leg_size(leg: WaveNode) -> float:
    return abs(leg.span_end.price - leg.span_start.price)


def _ladder(
    *,
    base: float,
    size: float,
    sign: int,
    levels: tuple[float, ...],
    label_prefix: str,
    target_type: str,
    theory_page: int,
    deriv_fmt: str,
) -> list[Target]:
    # price = base + sign·lvl·size per level. `deriv_fmt` has a `{lvl}` slot.
    # Skip non-positive prices — a $-X target (deep extension of a large down leg)
    # is not a real level and must not reach the prompt/UI.
    out: list[Target] = []
    for lvl in levels:
        price = base + sign * lvl * size
        if price <= 0:
            continue
        out.append(
            Target(
                name=f"{label_prefix}_{lvl}",
                price=price,
                type=target_type,
                theory_page=theory_page,
                derivation=deriv_fmt.format(lvl=lvl),
            )
        )
    return out


def _internal_targets(source: WaveNode, label_prefix: str, theory_page: int) -> list[Target]:
    return _ladder(
        base=source.span_start.price,
        size=_leg_size(source),
        sign=_direction_sign(source),
        levels=_INTERNAL_LEVELS,
        label_prefix=label_prefix,
        target_type="internal",
        theory_page=theory_page,
        deriv_fmt=f"{label_prefix} = source.start + {{lvl}} × |source|",
    )


def _retracement_targets(source: WaveNode, label_prefix: str, theory_page: int) -> list[Target]:
    # Retrace runs back from leg end → negate direction sign.
    return _ladder(
        base=source.span_end.price,
        size=_leg_size(source),
        sign=-_direction_sign(source),
        levels=_RETRACE_LEVELS,
        label_prefix=label_prefix,
        target_type="retracement",
        theory_page=theory_page,
        deriv_fmt=f"{label_prefix} = source.end - {{lvl}} × |source|",
    )


def compute_targets(sc: Scenario) -> TargetSet:
    # No scale_mode: Fib ladders are linear-price by design (base + lvl × |leg|).
    if sc.family == "5W_TREND":
        return _targets_5wt(sc)
    if sc.family == "5W_SIDEWAY":
        return _targets_5ws(sc)
    if sc.family == "3W":
        return _targets_3w(sc)
    if sc.family == "LINK_T":
        return _targets_link_t(sc)
    if sc.family in ("LINK_S", "LINK_SE"):
        return _targets_link_s(sc)
    return TargetSet(
        confirmation_targets=(),
        fib_flow_targets=(),
        invalidation=_default_invalidation(sc),
    )


def _last_confirmed_price(sc: Scenario) -> float:
    # root end → last closed leg → anchor (always present), so an all-open count
    # yields a real on-chart price, never a fabricated 0.0 read as a trade level.
    if sc.root.span_end is not None:
        return sc.root.span_end.price
    for leg in reversed(sc.legs):
        if leg.span_end is not None:
            return leg.span_end.price
    return sc.root.span_start.price


def _default_invalidation(sc: Scenario) -> Target:
    # Page from family table; LINK families get 0 (§9.2 — no closed-form rule).
    inv_pages = family_invalidation_pages(sc.family)
    return Target(
        name="last_pivot",
        price=_last_confirmed_price(sc),
        type="invalidation",
        theory_page=min(inv_pages) if inv_pages else 0,
        derivation="price beyond the last confirmed pivot invalidates this count",
    )


def _project_5wt_wave5(sc: Scenario) -> TargetSet:
    # s1/s3 internal extensions — only sources not needing wave 5 (p.110).
    s1, _s2, s3, _s4 = sc.legs[:4]
    raw = (_internal_targets(s1, "wave 5 projected from s1", 110)
           + _internal_targets(s3, "wave 5 projected from s3", 110))
    return TargetSet(
        confirmation_targets=(),
        fib_flow_targets=tuple(replace(t, type="projected") for t in raw),
        invalidation=_default_invalidation(sc),
    )


def _targets_5wt(sc: Scenario) -> TargetSet:
    legs = sc.legs
    if len(legs) == 4:
        return _project_5wt_wave5(sc)
    if len(legs) < 5:
        return TargetSet(
            confirmation_targets=(),
            fib_flow_targets=(),
            invalidation=_default_invalidation(sc),
        )
    s1, _s2, s3, s4, s5 = legs[:5]
    subtype = sc.pattern_kind

    flow: list[Target] = []
    if subtype in (
        PatternKind.FIVE_TREND_S1_LONGEST,
        PatternKind.FIVE_TREND_S3_LONGEST,
    ):
        flow += _internal_targets(s1, "s1 → s3 internal", 110)
        flow += _internal_targets(s1, "s1 → s5 internal", 110)
        flow += _internal_targets(s3, "s3 → s5 internal", 110)
    elif subtype == PatternKind.FIVE_TREND_S5_LONGEST:
        flow += _internal_targets(s1, "s1 → s3 internal", 110)
        flow += _ladder(
            base=s1.span_start.price,
            size=_leg_size(s1) + _leg_size(s3),
            sign=_direction_sign(s1),
            levels=_INTERNAL_LEVELS,
            label_prefix="s1+s3 → s5 internal",
            target_type="internal",
            theory_page=110,
            deriv_fmt="s1+s3 → s5 = s1.start + {lvl} × (|s1|+|s3|)",
        )
        flow += _internal_targets(s3, "s3 → s5 internal", 110)
    elif subtype == PatternKind.FIVE_TREND_S5_SHORTER:
        flow += _internal_targets(s1, "s1 → s3 internal", 110)
        flow += _internal_targets(s1, "s1 → s5 internal", 110)
        flow += _retracement_targets(s4, "s4 → s5 retrace", 110)
    # EQUAL_PUSH → no entries (spec §9.2 advisor consult).

    full = s5.span_end.price - s1.span_start.price
    confirmation = (
        Target(name="s5_retrace_100", price=s5.span_start.price,
               type="retracement", theory_page=34,
               derivation="s5 retraced 100% = s5.start"),
        Target(name="full_set_retrace_61.8",
               price=s5.span_end.price - 0.618 * full,
               type="retracement", theory_page=34,
               derivation="s5.end - 0.618 × (s5.end - s1.start)"),
        Target(name="full_set_retrace_100", price=s1.span_start.price,
               type="retracement", theory_page=34,
               derivation="full retrace = s1.start"),
    )

    invalidation = Target(
        name="s5_end_close", price=s5.span_end.price, type="invalidation",
        theory_page=22, derivation="close past s5.end invalidates completion claim",
    )
    return TargetSet(
        confirmation_targets=confirmation,
        fib_flow_targets=tuple(flow),
        invalidation=invalidation,
    )


def _project_5ws_wave5(sc: Scenario) -> TargetSet:
    # 5W_SIDEWAY uses leg-by-leg retracement; wave 5 retraces s4 (p.111).
    s4 = sc.legs[3]
    raw = _retracement_targets(s4, "wave 5 projected", 111)
    return TargetSet(
        confirmation_targets=(),
        fib_flow_targets=tuple(replace(t, type="projected") for t in raw),
        invalidation=_default_invalidation(sc),
    )


def _targets_5ws(sc: Scenario) -> TargetSet:
    legs = sc.legs
    if len(legs) == 4:
        return _project_5ws_wave5(sc)
    if len(legs) < 5:
        return TargetSet(
            confirmation_targets=(),
            fib_flow_targets=(),
            invalidation=_default_invalidation(sc),
        )
    s1, s2, s3, s4, s5 = legs[:5]
    flow: list[Target] = []
    flow += _retracement_targets(s1, "s1 retrace", 103)
    flow += _retracement_targets(s2, "s2 retrace", 103)
    flow += _retracement_targets(s3, "s3 retrace", 103)
    flow += _retracement_targets(s4, "s4 retrace", 103)
    flow += _retracement_targets(s5, "s5 retrace", 111)
    full = s5.span_end.price - s1.span_start.price
    confirmation = (
        Target(name="s5_retrace_100", price=s5.span_start.price,
               type="retracement", theory_page=43,
               derivation="s5 retraced 100% (5W_SIDEWAY)"),
        Target(name="full_set_retrace_61.8",
               price=s5.span_end.price - 0.618 * full,
               type="retracement", theory_page=43,
               derivation="full retrace 61.8% (5W_SIDEWAY CB)"),
    )
    invalidation = Target(
        name="s5_end_close", price=s5.span_end.price, type="invalidation",
        theory_page=22, derivation="close past s5.end invalidates",
    )
    return TargetSet(
        confirmation_targets=confirmation,
        fib_flow_targets=tuple(flow),
        invalidation=invalidation,
    )


def _targets_3w(sc: Scenario) -> TargetSet:
    legs = sc.legs
    if len(legs) < 3:
        return TargetSet(
            confirmation_targets=(),
            fib_flow_targets=(),
            invalidation=_default_invalidation(sc),
        )
    s1, _s2, s3 = legs[:3]
    flow = _internal_targets(s1, "s1 → s3 internal", 112)
    confirmation = (
        Target(name="s3_retrace_100", price=s3.span_start.price,
               type="retracement", theory_page=55,
               derivation="s3 retraced 100% = s2.end"),
    )
    invalidation = Target(
        name="s3_end_close", price=s3.span_end.price, type="invalidation",
        theory_page=48, derivation="close past s3.end invalidates 3W completion",
    )
    return TargetSet(
        confirmation_targets=confirmation,
        fib_flow_targets=tuple(flow),
        invalidation=invalidation,
    )


def _set_legs(root: WaveNode, set_idx: int) -> list[WaveNode]:
    if not root.sets or set_idx >= len(root.sets):
        return []
    ls = root.sets[set_idx]
    return root.children[ls.leg_start : ls.leg_end + 1]


def _targets_link_t(sc: Scenario) -> TargetSet:
    if not sc.root.sets or len(sc.root.sets) < 2:
        return TargetSet(
            confirmation_targets=(),
            fib_flow_targets=(),
            invalidation=_default_invalidation(sc),
        )
    flow: list[Target] = []
    for set_idx in range(len(sc.root.sets) - 1):
        prev_set = _set_legs(sc.root, set_idx)
        next_set = _set_legs(sc.root, set_idx + 1)
        if len(prev_set) < 3 or len(next_set) < 1:
            continue
        prev_s3 = prev_set[2]
        next_s1 = next_set[0]
        flow += _ladder(
            base=next_s1.span_start.price,
            size=_leg_size(prev_s3),
            sign=_direction_sign(prev_s3),
            levels=_INTERNAL_LEVELS,
            label_prefix=f"link_set{set_idx}_prev.s3→next.s1 internal",
            target_type="internal",
            theory_page=113,
            deriv_fmt="prev_set.s3 → next_set.s1 = next.s1.start + {lvl} × |prev.s3|",
        )
    invalidation = _default_invalidation(sc)
    return TargetSet(
        confirmation_targets=(),
        fib_flow_targets=tuple(flow),
        invalidation=invalidation,
    )


def _targets_link_s(sc: Scenario) -> TargetSet:
    if not sc.root.sets:
        return TargetSet(
            confirmation_targets=(),
            fib_flow_targets=(),
            invalidation=_default_invalidation(sc),
        )
    flow: list[Target] = []
    for set_idx in range(len(sc.root.sets)):
        legs = _set_legs(sc.root, set_idx)
        if not legs:
            continue
        flow += _retracement_targets(legs[-1], f"link_set{set_idx}_lastleg retrace", 114)
    invalidation = _default_invalidation(sc)
    return TargetSet(
        confirmation_targets=(),
        fib_flow_targets=tuple(flow),
        invalidation=invalidation,
    )
