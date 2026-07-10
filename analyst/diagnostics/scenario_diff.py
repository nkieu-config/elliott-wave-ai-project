from __future__ import annotations

from dataclasses import dataclass

from analyst.taxonomy import ALL_SLOTS


@dataclass(frozen=True)
class ScenarioDiff:
    primary_rank: int
    competitor_rank: int
    primary_bottleneck: str
    competitor_bottleneck: str
    slot_deltas: dict[str, float]
    # 1 = primary wins, 2 = competitor wins, 0 = exact tie (no edge either way).
    structural_winner: int
    visual_winner: int
    pattern_kind_match: bool
    # Defaulted so hand-built ScenarioDiffs (tests) stay valid.
    primary_family: str = ""
    competitor_family: str = ""
    primary_probability: float = 0.0
    competitor_probability: float = 0.0


def _winner(primary: float, competitor: float) -> int:
    # 0 on an exact tie so serializers don't award the edge to whichever ranks second.
    if primary > competitor:
        return 1
    return 2 if competitor > primary else 0


def _bottleneck_slot(components: dict) -> str:
    # Type filter — a None slot would break min().
    active = {
        k: v for k, v in components.items()
        if k in ALL_SLOTS and isinstance(v, (int, float))
    }
    return min(active, key=active.get) if active else ""


def _relative_probabilities(scenarios: list) -> list[float]:
    scores = [max(float(getattr(s, "score", 0.0)), 0.0) for s in scenarios]
    total = sum(scores) or 1.0
    return [s / total for s in scores]


def diff_top_scenarios(scenarios: list, top_k: int = 3) -> list[ScenarioDiff]:
    out: list[ScenarioDiff] = []
    bounded = scenarios[:top_k]
    probs = _relative_probabilities(bounded)
    for i in range(len(bounded) - 1):
        primary = bounded[i]
        comp = bounded[i + 1]
        p_comp = primary.score_components or {}
        c_comp = comp.score_components or {}
        deltas: dict[str, float] = {}
        for slot in ALL_SLOTS:
            pv = p_comp.get(slot)
            cv = c_comp.get(slot)
            if pv is not None and cv is not None:
                deltas[slot] = float(pv - cv)
        struct_winner = _winner(
            p_comp.get("structural_total", 0), c_comp.get("structural_total", 0)
        )
        visual_winner = _winner(
            p_comp.get("visual_total", 0), c_comp.get("visual_total", 0)
        )
        out.append(ScenarioDiff(
            primary_rank=i + 1,
            competitor_rank=i + 2,
            primary_bottleneck=_bottleneck_slot(p_comp),
            competitor_bottleneck=_bottleneck_slot(c_comp),
            slot_deltas=deltas,
            structural_winner=struct_winner,
            visual_winner=visual_winner,
            pattern_kind_match=primary.pattern_kind == comp.pattern_kind,
            primary_family=getattr(primary, "family", ""),
            competitor_family=getattr(comp, "family", ""),
            primary_probability=probs[i],
            competitor_probability=probs[i + 1],
        ))
    return out
