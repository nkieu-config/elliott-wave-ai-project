from __future__ import annotations

from dataclasses import replace

from analyst.schemas.citation import TheoryRef

SLOT_CITATIONS: dict[str, TheoryRef] = {
    "speed_cluster": TheoryRef(
        pages=(91, 96),
        concept="Same-degree principle",
        binding="concept_operationalization",
        note=(
            "Operationalizes Gann Box's same-degree check (time × price) as "
            "continuous log-CV of pace; slot value reflects how uniform legs' "
            "pace is, not the discrete Gann band pass/fail."
        ),
    ),
    # pages=() — Fib measurement is family-dependent; resolved via slot_theory_ref().
    # Direct SLOT_CITATIONS["fib_push_pairs"].pages read is a bug.
    "fib_push_pairs": TheoryRef(
        pages=(),
        concept="Fibonacci measurement",
        binding="concept_operationalization",
        note=(
            "Smooths the discrete Fib ratio check into log-tolerance scoring; "
            "rewards pairs that land near canonical Fib levels in log space."
        ),
    ),
    "pull_depth_discipline": TheoryRef(
        pages=(99, 100),
        concept="Fibonacci Retracement window",
        binding="concept_operationalization",
        note=(
            "Plateau-then-decay shape over the [0.382, 0.618] window from "
            "theory's Fibonacci Retracement levels."
        ),
    ),
    "pivot_sharpness": TheoryRef(
        pages=(),
        concept="Chart appearance",
        binding="heuristic",
        note="No theory binding — visual sharpness heuristic for pivot quality.",
    ),
    "leg_smoothness": TheoryRef(
        pages=(),
        concept="Chart appearance",
        binding="heuristic",
        note="No theory binding — intra-leg drawdown heuristic.",
    ),
}


# Family → Fib Flow pages (§4.3).
_FAMILY_FIB_FLOW: dict[str, set[int]] = {
    "5W_TREND": {101, 110},
    "5W_SIDEWAY": {103, 111},
    "3W": {104, 112},
    "LINK_T": {105, 113},
    "LINK_S": {106, 114},
    "LINK_SE": {106, 114},   # SE follows LINK_S
}


# Slots with family-dependent theory pages (Fib measurement differs per family).
_FAMILY_DEPENDENT_SLOTS: frozenset[str] = frozenset({"fib_push_pairs"})


# Family → confirmation pages (matches diagnostics/confirmation.py).
_FAMILY_CONFIRMATION: dict[str, set[int]] = {
    "5W_TREND": {33, 34},
    "5W_SIDEWAY": {43},
    "3W": {54, 55},
    "LINK_T": set(),
    "LINK_S": set(),
    "LINK_SE": set(),
}


# Family → invalidation pages (matches diagnostics/targets.py).
_FAMILY_INVALIDATION: dict[str, set[int]] = {
    "5W_TREND": {22},
    "5W_SIDEWAY": {22},
    "3W": {48},
    "LINK_T": set(),
    "LINK_S": set(),
    "LINK_SE": set(),
}


# Family → Link-Wave succession pages (matches diagnostics/succession.py).
_FAMILY_SUCCESSION: dict[str, set[int]] = {
    "5W_TREND": {57, 59, 67},
    "5W_SIDEWAY": {57, 67, 73, 74},
    "3W": {57, 59, 64, 67, 73},
    "LINK_T": {57, 59, 64, 67},
    "LINK_S": {57, 59, 67, 73, 74},
    "LINK_SE": {57, 59, 67, 73, 74},
}


def family_fib_flow_pages(family: str) -> set[int]:
    return set(_FAMILY_FIB_FLOW.get(family, set()))


def family_confirmation_pages(family: str) -> set[int]:
    return set(_FAMILY_CONFIRMATION.get(family, set()))


def family_invalidation_pages(family: str) -> set[int]:
    return set(_FAMILY_INVALIDATION.get(family, set()))


def family_succession_pages(family: str) -> set[int]:
    return set(_FAMILY_SUCCESSION.get(family, set()))


def slot_theory_ref(slot: str, family: str) -> TheoryRef | None:
    # Always prefer this over direct SLOT_CITATIONS indexing (family-dependent slots).
    base = SLOT_CITATIONS.get(slot)
    if base is None:
        return None
    if slot in _FAMILY_DEPENDENT_SLOTS:
        return replace(base, pages=tuple(sorted(family_fib_flow_pages(family))))
    return base


def pages_for_slots(slot_names: list[str], family: str) -> set[int]:
    out: set[int] = set()
    for s in slot_names:
        ref = slot_theory_ref(s, family)
        if ref is not None:
            out.update(ref.pages)
    return out


def all_mapped_pages() -> set[int]:
    # Validation — Retriever.by_pages silently drops missing pages; tests catch drift.
    pages: set[int] = set()
    for ref in SLOT_CITATIONS.values():
        pages.update(ref.pages)
    for table in (_FAMILY_FIB_FLOW, _FAMILY_CONFIRMATION,
                  _FAMILY_INVALIDATION, _FAMILY_SUCCESSION):
        for fam_pages in table.values():
            pages.update(fam_pages)
    return pages


_TABLE_CONCEPTS: tuple[tuple[dict[str, set[int]], str], ...] = (
    (_FAMILY_FIB_FLOW, "Fibonacci Flow targets"),
    (_FAMILY_CONFIRMATION, "Confirmation rules"),
    (_FAMILY_INVALIDATION, "Invalidation rules"),
    (_FAMILY_SUCCESSION, "Link-Wave succession"),
)


def concept_for_page(page: int) -> str | None:
    # First match wins; _TABLE_CONCEPTS ordered by citation frequency.
    for ref in SLOT_CITATIONS.values():
        if page in ref.pages:
            return ref.concept
    for table, label in _TABLE_CONCEPTS:
        for fam_pages in table.values():
            if page in fam_pages:
                return label
    return None
