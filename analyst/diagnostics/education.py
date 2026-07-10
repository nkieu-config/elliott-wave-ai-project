from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyEducation:
    title: str
    one_line: str
    rules: tuple[str, ...]
    visual_cues: tuple[str, ...]


FAMILY_EDUCATION: dict[str, FamilyEducation] = {
    "5W_TREND": FamilyEducation(
        title="5-Wave Trend",
        one_line=(
            "Five waves moving in one direction — the classic Elliott "
            "Wave 'impulse'. Three pushes in the direction of the move "
            "(Waves 1, 3, 5), separated by two corrections against it "
            "(Waves 2, 4)."
        ),
        rules=(
            "Wave 2 never retraces past the start of Wave 1.",
            "Wave 3 is never the shortest among Waves 1, 3, and 5.",
            "Wave 4 does not overlap into Wave 1's price range.",
        ),
        visual_cues=(
            "Five distinct turning points — peaks and troughs that step "
            "in one direction overall.",
            "Wave 3 is usually the longest leg; the chart 'pushes' "
            "hardest in the middle.",
            "Pivots between waves are sharp, not gentle curves.",
        ),
    ),
    "5W_SIDEWAY": FamilyEducation(
        title="5-Wave Sideway",
        one_line=(
            "Five waves trapped inside a horizontal range — a pause, "
            "not a trend. The stock oscillates between the same two "
            "broad price boundaries instead of stepping in one "
            "direction."
        ),
        rules=(
            "All five waves stay within a horizontal channel — there is "
            "no net directional move.",
            "Each wave reaches near the channel's opposite boundary; "
            "the structure 'breathes' the full range.",
            "The fifth wave does not break decisively above or below the "
            "channel — if it does, the pattern transitions to a Trend.",
        ),
        visual_cues=(
            "Highs and lows that roughly line up at the same two prices.",
            "Five legs of similar size — none dominates the way Wave 3 "
            "dominates a Trend.",
            "The chart looks like a rectangle being filled in with "
            "zig-zag lines, not a staircase climbing or descending.",
        ),
    ),
    "3W": FamilyEducation(
        title="3-Wave Correction",
        one_line=(
            "Three waves running counter to a prior trend — the "
            "'A-B-C' correction in classic Elliott terminology. Wave A "
            "starts the move against the trend; B retraces it; C "
            "extends past A."
        ),
        rules=(
            "There are exactly three legs — never more — before the "
            "correction is done.",
            "Wave B may retrace only part of Wave A or extend well beyond "
            "it (a deeper 'B-longer' correction is still valid).",
            "Wave C usually exceeds the end of Wave A in the same "
            "direction.",
        ),
        visual_cues=(
            "A clear three-step move — peak / dip / peak (or trough / "
            "rally / trough) — not five.",
            "Wave B looks like a brief 'fakeout' against the broader "
            "correction.",
            "The pattern often ends near a Fibonacci retracement of the "
            "prior trend (38%, 50%, or 62%).",
        ),
    ),
    "LINK_T": FamilyEducation(
        title="Trend Linkage",
        one_line=(
            "Two or three 3-Wave corrections joined by short connector "
            "waves — Elliott's way of describing a sustained correction "
            "that takes longer than a single A-B-C."
        ),
        rules=(
            "Each set is a complete 3-Wave correction; the linkage holds "
            "2 or 3 sets at most.",
            "The connector between sets runs counter to the linkage "
            "trend and spans 1%-62% of the previous Wave 3.",
            "A 5-Wave Trend cannot be the linked structure — only "
            "3-Wave sets link this way.",
        ),
        visual_cues=(
            "Multiple A-B-C patterns stacked one after another, each in "
            "the same direction.",
            "Small counter-trend kinks between each set — these are the "
            "connectors.",
            "The chart looks like one big correction that 'restarts' "
            "two or three times before exhausting.",
        ),
    ),
    "LINK_S": FamilyEducation(
        title="Sideway Linkage",
        one_line=(
            "Two or three sets linked sideways — the patient cousin of "
            "the Trend linkage. The linked structures can be 3-Wave "
            "corrections or 5-Wave Sideways; the link wave between them "
            "is large enough to be its own wave."
        ),
        rules=(
            "The link wave is at least 78.6% of the linked structure's "
            "full range.",
            "The linkage holds 2 or 3 sets at most.",
            "Linked structures may be 3-Wave or 5-Wave Sideway; never a "
            "5-Wave Trend.",
        ),
        visual_cues=(
            "The chart oscillates between two broad price zones for an "
            "extended period.",
            "The transitions between zones are full-sized waves, not "
            "tiny kinks.",
            "The whole structure looks like a broader version of a "
            "5-Wave Sideway, with each 'wave' being itself a complete "
            "smaller pattern.",
        ),
    ),
    "LINK_SE": FamilyEducation(
        title="Sideway-Expand Linkage",
        one_line=(
            "A Sideway linkage whose range expands as it progresses — "
            "each new set reaches further out than the last."
        ),
        rules=(
            "Follows the Sideway linkage rules but with the price range "
            "broadening across the sets.",
            "Each set's extreme is further from the linkage's centre "
            "than the prior set's.",
            "Often resolves with a sharp move out of the widest zone, "
            "either into a fresh Trend or into a new correction.",
        ),
        visual_cues=(
            "A megaphone shape on the chart — successively higher highs "
            "and lower lows.",
            "Each oscillation feels bigger than the previous.",
            "Volatility builds visibly; the calmer earlier portion gives "
            "way to wider swings.",
        ),
    ),
}


def family_education(family: str) -> FamilyEducation | None:
    return FAMILY_EDUCATION.get(family)
