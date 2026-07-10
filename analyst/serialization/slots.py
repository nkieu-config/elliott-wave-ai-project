from __future__ import annotations

from analyst.serialization.analysis_blocks import slot_plain
from analyst.taxonomy import STRUCTURAL_SLOTS, VISUAL_SLOTS

_STRUCTURAL = STRUCTURAL_SLOTS
_VISUAL = VISUAL_SLOTS


def _rank_band(position: int, total: int) -> str:
    if position == 0:
        return "weakest"
    if position == total - 1:
        return "strongest"
    if position == 1:
        return "2nd-weakest"
    if position == total - 2:
        return "2nd-strongest"
    return "mid-ranked"


def format_slot_grid(components: dict, bottleneck: str | None) -> str:
    present = [
        s for s in (*_STRUCTURAL, *_VISUAL)
        if isinstance(components.get(s), (int, float))
    ]
    if not present:
        return "No scoring checks are available for this scenario."

    order = sorted(present, key=lambda s: components[s])
    rank = {s: i for i, s in enumerate(order)}
    n = len(order)

    def row(s: str) -> str:
        mark = " — the overall bottleneck" if s == bottleneck else ""
        return f"- the {slot_plain(s)} check: {_rank_band(rank[s], n)}{mark}"

    lines = ["Checks ranked weakest → strongest across all checks present.\n"]
    structural = [s for s in _STRUCTURAL if s in rank]
    if structural:
        lines.append("### Shape-and-proportion checks")
        lines += [row(s) for s in structural]
    visual = [s for s in _VISUAL if s in rank]
    if visual:
        lines.append("\n### Visual-appearance checks")
        lines += [row(s) for s in visual]

    st = components.get("structural_total")
    vt = components.get("visual_total")
    if isinstance(st, (int, float)) and isinstance(vt, (int, float)):
        if st == vt:
            lines.append(
                "\nThe shape-and-proportion and visual-appearance sides score "
                "equally; neither is the weaker dimension."
            )
        else:
            weaker = "shape-and-proportion" if st < vt else "visual-appearance"
            lines.append(
                f"\nThe {weaker} side is the weaker of the two dimensions and "
                f"sets the overall match quality."
            )
    return "\n".join(lines)
