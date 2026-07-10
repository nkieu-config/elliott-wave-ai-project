from __future__ import annotations

from analyst.schemas.analysis import AnalysisResult
from analyst.serialization.analysis_blocks import _LINK_TYPE_DISPLAY, slot_plain
from analyst.taxonomy import humanize_family_codes


def _join_sentences(parts: list[str]) -> str:
    # Ensure each fragment ends in punctuation so " ".join doesn't run them together.
    out: list[str] = []
    for part in parts:
        text = part.strip()
        if text and text[-1] not in ".!?":
            text += "."
        out.append(text)
    return " ".join(out)


def mode_fallback(mode: str, layer1: AnalysisResult) -> str:
    if mode == "differentiator":
        return _differentiator(layer1)
    if mode == "scenario_outlook":
        return _outlook(layer1)
    # explanation / slot_focus (and unknown modes) → bottleneck summary
    if layer1.bottleneck is not None:
        return layer1.bottleneck.plain_explanation
    return "No bottleneck diagnosis is available for this scenario."


def _differentiator(layer1: AnalysisResult) -> str:
    diffs = layer1.scenario_diffs
    if not diffs:
        return (
            "No rank-2 competitor is available, so this scenario could not "
            "be compared against an alternative."
        )
    d = diffs[0]
    parts = [
        f"This scenario's weakest check is the "
        f"{slot_plain(d.primary_bottleneck)} check; the rank-"
        f"{d.competitor_rank} competitor's is the "
        f"{slot_plain(d.competitor_bottleneck)} check."
    ]
    if d.slot_deltas:
        # Score-points, NOT % — slot_deltas are a 0-1 grade; the differentiator
        # prompt forbids "+19%" framing, and the block render uses ×100 too.
        ranked = sorted(d.slot_deltas.items(), key=lambda kv: -abs(kv[1]))
        top = ", ".join(
            f"the {slot_plain(name)} check {val * 100:+.0f}" for name, val in ranked[:3]
        )
        parts.append(
            f"Largest gaps in score points (this scenario minus the competitor): {top}."
        )
    struct = "are tied" if d.structural_winner == 0 else f"favour scenario {d.structural_winner}"
    visual = "are tied" if d.visual_winner == 0 else f"favour scenario {d.visual_winner}"
    parts.append(
        f"The shape-and-proportion checks {struct}; "
        f"the visual-appearance checks {visual}."
    )
    return _join_sentences(parts)


def _succession_summary(succession) -> str:
    if succession.is_terminal:
        return "This structure is terminal: theory permits no Link-Wave successor."
    if not succession.next_patterns:
        return "No Link-Wave succession applies to this family."
    # Friendly label, not raw +T/+S (which the gate rejects); display ends in "linkage".
    bits = [
        f"a {_LINK_TYPE_DISPLAY.get(npat.link_type, npat.link_type)} into a "
        f"{humanize_family_codes(' or '.join(npat.next_families))} set"
        for npat in succession.next_patterns
    ]
    return "Once this pattern completes, theory permits " + ", or ".join(bits) + "."


def _outlook(layer1: AnalysisResult) -> str:
    parts: list[str] = []
    conf = layer1.confirmation
    if conf is not None:
        if not conf.is_applicable:
            parts.append(
                "Confirmation is not applicable: "
                + humanize_family_codes(conf.not_applicable_reason.text)
            )
        else:
            parts.append(
                f"Highest confirmation level reached: {conf.highest_met or 'none'}."
            )
            unmet = [lv for lv in conf.levels if not lv.met]
            if unmet:
                parts.append(
                    f"The next level, {unmet[0].name}, triggers when "
                    f"{unmet[0].condition}."
                )
    ts = layer1.targets
    if ts is not None:
        projected = [t for t in ts.fib_flow_targets if t.type == "projected"]
        measured = [t for t in ts.fib_flow_targets if t.type != "projected"]
        if projected:
            lo = min(t.price for t in projected)
            hi = max(t.price for t in projected)
            parts.append(
                f"The pattern is still open; its final wave is projected to "
                f"a zone of ${lo:.2f} to ${hi:.2f}."
            )
        elif measured:
            parts.append(
                f"{len(measured)} Fibonacci Flow target(s) are defined."
            )
        else:
            parts.append("No Fibonacci Flow targets are defined for this scenario.")
        parts.append(f"Invalidation sits at ${ts.invalidation.price:.2f}.")
    if layer1.succession is not None:
        parts.append(_succession_summary(layer1.succession))
    if not parts:
        return "No outlook data is available for this scenario."
    return _join_sentences(parts)
