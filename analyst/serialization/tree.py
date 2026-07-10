from __future__ import annotations

from analyst.enums import enum_value
from engine import WaveNode
from engine.display import family_label, pattern_label


def format_tree(root: WaveNode, family: str) -> str:
    lines: list[str] = []
    # Friendly labels only — raw codes get echoed and trip the gate.
    header = (
        pattern_label(root.pattern_kind, friendly=True)
        if root.pattern_kind
        else f"{family_label(family, friendly=True)} · ?"
    )
    lines.append(f"ROOT [{header}]")
    for child in root.children:
        # Open leg (span_end=None) has no settled direction — "·", not a false "↓"
        # that could contradict the Decision block's open-wave direction.
        if child.span_end is None:
            direction = "·"
        else:
            direction = "↑" if child.span_end.price > child.span_start.price else "↓"
        end_price = child.span_end.price if child.span_end else None
        start_price = child.span_start.price
        bar_span = (
            child.span_end.bar_index - child.span_start.bar_index
            if child.span_end and child.span_end.bar_index is not None
            and child.span_start.bar_index is not None
            else "?"
        )
        role = enum_value(child.role)
        # None for an open leg — placeholder avoids format(None, ".2f") crash.
        end_str = f"${end_price:.2f}" if end_price is not None else "(open)"
        lines.append(
            f"├── {role}  {direction}  "
            f"${start_price:.2f} → {end_str}  | {bar_span} bars"
        )
    return "\n".join(lines)
