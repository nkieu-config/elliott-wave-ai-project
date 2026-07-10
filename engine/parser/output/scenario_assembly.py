from __future__ import annotations

import hashlib

from engine.degree import assign_degree_labels
from engine.types import OpenState, ScaleMode, WaveNode, WaveRole

from ..runtime import RuntimeContext
from ..scoring import _score_components_for_display
from ..types import LINK_FAMILIES, _Context, _Hypothesis
from .linkwave_flattening import _merge_open_into_linkwave
from .open_subtree import _build_open_subcontext_chain
from .tree_builders import _build_root_wavenode, _first_pivot_in_stack
from .types import Scenario

__all__ = ["to_scenario"]


def _enum_value(v: object) -> str:
    return v.value if hasattr(v, "value") else ("" if v is None else str(v))


def _node_structural_key(node: WaveNode) -> str:
    # Run-independent subtree fingerprint. Pivot `index` is stable across runs
    # (deterministic ATR zigzag), unlike object identity.
    start = node.span_start.index if node.span_start is not None else "-"
    end = node.span_end.index if node.span_end is not None else "-"
    children = ",".join(_node_structural_key(c) for c in node.children)
    return (
        f"{_enum_value(node.role)}:{_enum_value(node.pattern_kind)}"
        f":{start}:{end}:{node.nesting_level}[{children}]"
    )


def _deterministic_scenario_id(
    root: WaveNode, open_subtree: WaveNode | None, family: str
) -> str:
    # Content-addressed, structure-only (not uuid4): the stateless API re-runs the
    # pipeline to resolve `scenario_id`, so shared `?scenario=` links must survive
    # cache eviction and restarts.
    raw = f"{family}||{_node_structural_key(root)}"
    if open_subtree is not None:
        raw += f"||open::{_node_structural_key(open_subtree)}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


def _next_expected_roles(ctx: _Context) -> list[WaveRole]:
    nr = ctx.next_role
    return [nr] if nr is not None else []


def to_scenario(
    h: _Hypothesis,
    mode: ScaleMode = "linear",
    *,
    runtime: RuntimeContext,
) -> Scenario:
    root_ctx = h.root
    top_ctx = h.top

    fallback = _first_pivot_in_stack(h.context_stack)
    root_node = _build_root_wavenode(root_ctx, fallback_pivot=fallback)

    open_subtree: WaveNode | None = None
    if len(h.context_stack) > 1:
        if root_ctx.family in LINK_FAMILIES:
            _merge_open_into_linkwave(root_node, h.context_stack, start_idx=1)
        else:
            open_subtree = _build_open_subcontext_chain(
                h.context_stack,
                1,
                root_node,
            )

    assign_degree_labels(root_node)
    if open_subtree is not None:
        # The open subtree is a root-child leg, so its own children start one degree
        # below the root (SECONDARY), matching a closed sibling leg's sub-waves.
        assign_degree_labels(open_subtree, children_level=1)

    open_state = OpenState(
        current_role=top_ctx.next_role,
        root_role=root_ctx.next_role,
        current_pattern=top_ctx.final_kind if top_ctx.is_complete else None,
        nesting_level=h.depth - 1,
        next_expected=_next_expected_roles(top_ctx),
    )

    components = _score_components_for_display(h, mode, runtime=runtime)

    return Scenario(
        id=_deterministic_scenario_id(root_node, open_subtree, root_ctx.family),
        root=root_node,
        score=round(components["total"], 3),
        score_components=components,
        open_state=open_state,
        rules_log=list(root_ctx.rules_log),
        open_subtree=open_subtree,
        _family=root_ctx.family,
    )
