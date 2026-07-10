from __future__ import annotations

from engine.adaptive import KIND_TO_FAMILY
from engine.constants import R5_LINK_SE_THRESHOLD_LINK_S
from engine.helpers import price_length, total_price_range
from engine.link_rules import link_s_min_required, link_s_ratio_mode
from engine.types import (
    LinkSet,
    PatternKind,
    RuleResult,
    ScaleMode,
    Segment,
    WaveNode,
)
from engine.verifiers._link_helpers import (
    check_link_count,
    check_links_pull,
    link_set_view,
)
from engine.verifiers._runner import Checker, run_checkers


def verify_link_s(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> tuple[PatternKind, list[RuleResult]] | None:
    """Validate link sets as a sideway linkage (LINK_S/LINK_SE); return its kind + rule results, or None."""
    # pp.71-78. R1-R4 hard; R5 promotes to LINK_SE when any link > 161.8% of prior set.
    rules = run_checkers(CHECKERS, sets, children, links, mode)
    if rules is None:
        return None
    kind = _classify_link_s_or_se(sets, children, links, mode)
    rules.append(RuleResult("link_s.r5.subtype", True, detail=kind.value))
    return kind, rules


def _check_r1_count(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> list[RuleResult] | None:
    del children, mode
    return check_link_count("link_s", sets, links)


def _check_r2_set_types(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> list[RuleResult] | None:
    del children, links, mode
    for s in sets:
        if KIND_TO_FAMILY.get(s.pattern_kind) not in ("3W", "5W_SIDEWAY"):
            return [RuleResult("link_s.r2.group_types", False)]
    return [RuleResult("link_s.r2.group_types", True)]


def _check_r3_link_size(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> list[RuleResult] | None:
    # Per-link min varies by prior set kind (see link_s_min_required).
    rules: list[RuleResult] = []
    for i, lk in enumerate(links):
        prev_set = sets[i]
        prev_view = link_set_view(children, prev_set)
        if prev_view is None:
            return None
        r = _link_size_ratio(prev_view, lk, mode)
        min_required = link_s_min_required(prev_set.pattern_kind)

        if r < min_required:
            rules.append(
                RuleResult(
                    f"link_s.r3.link_size_{i}",
                    False,
                    measured=r,
                    detail=f"required >= {min_required}",
                )
            )
            return rules
        rules.append(RuleResult(f"link_s.r3.link_size_{i}", True, measured=r))
    return rules


def _check_r4_links_pull(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> list[RuleResult] | None:
    # p.56: every '+' link is a Pull-Wave. Only place catching link-with-trend
    # slip-throughs from 3W_S2_LONGER sets (parser uses NET span direction).
    del mode
    return check_links_pull("link_s.r4", children, sets, links)


CHECKERS: tuple[Checker, ...] = (
    _check_r1_count,
    _check_r2_set_types,
    _check_r3_link_size,
    _check_r4_links_pull,
)


def _classify_link_s_or_se(
    sets: list[LinkSet],
    children: list[WaveNode],
    links: list[Segment],
    mode: ScaleMode,
) -> PatternKind:
    for i, lk in enumerate(links):
        prev_view = link_set_view(children, sets[i])
        if prev_view is None:
            continue
        r = _link_size_ratio(prev_view, lk, mode)
        if r > R5_LINK_SE_THRESHOLD_LINK_S:
            return PatternKind.LINK_SE
    return PatternKind.LINK_S


def _link_size_ratio(prev: WaveNode, link: Segment, mode: ScaleMode) -> float:
    # 3W / 5WS Contract / Balance: link / total_range. Expand: link / s5_leg.
    ratio_mode = link_s_ratio_mode(prev.pattern_kind)
    if ratio_mode is None:
        return 0.0
    link_len = price_length(link, mode)

    if ratio_mode == "total_range":
        rng = total_price_range(_all_segments(prev), mode)
        return link_len / rng if rng > 0 else 0.0

    # "s5_leg" (Expand): s5 leg span (not flat seg[4]) — s5 may be nested.
    s5 = _leg_span_segment(prev, 4)
    if s5 is None:
        return 0.0
    l5 = price_length(s5, mode)
    return link_len / l5 if l5 > 0 else 0.0


def _all_segments(node: WaveNode) -> list[Segment]:
    if node.segments:
        return list(node.segments)
    out: list[Segment] = []
    for c in node.children:
        out.extend(_all_segments(c))
    return out


def _leg_span_segment(group: WaveNode, idx: int) -> Segment | None:
    # Tree-style children first, legacy direct segments fallback.
    if 0 <= idx < len(group.children):
        leg = group.children[idx]
        end = leg.span_end
        if end is not None:
            return Segment(start=leg.span_start, end=end)
    if 0 <= idx < len(group.segments):
        return group.segments[idx]
    return None


__all__ = ["verify_link_s"]
