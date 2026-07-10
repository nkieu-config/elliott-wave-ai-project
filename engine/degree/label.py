from __future__ import annotations

from engine.types import DegreeLabel, LinkSet, WaveNode

__all__ = ["assign_degree_labels"]


_LEVEL_TO_LABEL: tuple[DegreeLabel, ...] = (
    DegreeLabel.PRIMARY,
    DegreeLabel.SECONDARY,
    DegreeLabel.MINOR,
)
_MAX_LEVEL = len(_LEVEL_TO_LABEL) - 1


def _level_label(level: int) -> DegreeLabel:
    return _LEVEL_TO_LABEL[min(max(level, 0), _MAX_LEVEL)]


def assign_degree_labels(root: WaveNode | None, *, children_level: int = 0) -> None:
    if root is None:
        return
    # The entry node is the top of its local tree (PRIMARY). children_level lets a
    # caller label a subtree that is really a root-child — the open subtree — one
    # degree deeper, so its waves match a closed sibling leg's (SECONDARY) rather
    # than restarting at PRIMARY.
    root.degree_label = _level_label(0)
    _walk(root, level=children_level)


def _walk(node: WaveNode, level: int) -> None:
    child_label = _level_label(level)
    for child in node.children:
        child.degree_label = child_label
        # Recurse into any node with sub-structure, including still-open sub-patterns
        # (pattern_kind is None until close) — else their descendants keep
        # degree_label=None and render blank.
        if child.children:
            _walk(child, level=level + 1)
    if node.sets is not None:
        node.sets = [
            LinkSet(
                pattern_kind=s.pattern_kind,
                leg_start=s.leg_start,
                leg_end=s.leg_end,
                degree_label=child_label,
            )
            for s in node.sets
        ]
