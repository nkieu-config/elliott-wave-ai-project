import json
from pathlib import Path

import analyst.theory
from analyst.theory.citation_map import (
    SLOT_CITATIONS,
    all_mapped_pages,
    family_confirmation_pages,
    family_fib_flow_pages,
    family_invalidation_pages,
    family_succession_pages,
    pages_for_slots,
    slot_theory_ref,
)


def test_slot_citations_cover_all_known_slots():
    expected = {
        "speed_cluster",
        "fib_push_pairs",
        "pull_depth_discipline",
        "pivot_sharpness",
        "leg_smoothness",
    }
    assert set(SLOT_CITATIONS) == expected


def test_binding_kinds_are_correct():
    assert SLOT_CITATIONS["speed_cluster"].binding == "concept_operationalization"
    assert SLOT_CITATIONS["fib_push_pairs"].binding == "concept_operationalization"
    assert SLOT_CITATIONS["pull_depth_discipline"].binding == "concept_operationalization"
    assert SLOT_CITATIONS["pivot_sharpness"].binding == "heuristic"
    assert SLOT_CITATIONS["leg_smoothness"].binding == "heuristic"


def test_heuristic_slots_have_empty_pages():
    assert SLOT_CITATIONS["pivot_sharpness"].pages == ()
    assert SLOT_CITATIONS["leg_smoothness"].pages == ()


def test_pages_for_slots_unions_pages_across_active_slots():
    out = pages_for_slots(["speed_cluster", "leg_smoothness"], "5W_TREND")
    assert out == {91, 96}


def test_fib_push_pairs_pages_are_resolved_per_family():
    trend = slot_theory_ref("fib_push_pairs", "5W_TREND")
    sideway = slot_theory_ref("fib_push_pairs", "5W_SIDEWAY")
    assert set(trend.pages) == {101, 110}
    assert set(sideway.pages) == {103, 111}
    assert 110 not in sideway.pages
    assert pages_for_slots(["fib_push_pairs"], "5W_SIDEWAY") == {103, 111}
    assert pages_for_slots(["fib_push_pairs"], "3W") == {104, 112}


def test_family_neutral_slot_ignores_family():
    a = slot_theory_ref("speed_cluster", "5W_TREND")
    b = slot_theory_ref("speed_cluster", "5W_SIDEWAY")
    assert a.pages == b.pages == (91, 96)
    assert slot_theory_ref("unknown_slot", "5W_TREND") is None


def test_family_fib_flow_pages():
    assert family_fib_flow_pages("5W_TREND") == {101, 110}
    assert family_fib_flow_pages("3W") == {104, 112}
    assert family_fib_flow_pages("LINK_S") == {106, 114}


def test_family_confirmation_pages():
    assert family_confirmation_pages("5W_TREND") == {33, 34}
    assert family_confirmation_pages("5W_SIDEWAY") == {43}
    assert family_confirmation_pages("3W") == {54, 55}
    assert family_confirmation_pages("LINK_T") == set()
    assert family_confirmation_pages("LINK_S") == set()
    assert family_confirmation_pages("UNKNOWN") == set()


def test_family_invalidation_pages():
    assert family_invalidation_pages("5W_TREND") == {22}
    assert family_invalidation_pages("5W_SIDEWAY") == {22}
    assert family_invalidation_pages("3W") == {48}
    assert family_invalidation_pages("LINK_T") == set()


def test_family_succession_pages():
    assert family_succession_pages("3W") == {57, 59, 64, 67, 73}
    assert family_succession_pages("5W_SIDEWAY") == {57, 67, 73, 74}
    assert family_succession_pages("5W_TREND") == {57, 59, 67}
    assert family_succession_pages("LINK_T") == {57, 59, 64, 67}
    assert family_succession_pages("LINK_S") == {57, 59, 67, 73, 74}
    assert family_succession_pages("UNKNOWN") == set()


def _corpus_pages() -> set[int]:
    chunks_path = Path(analyst.theory.__file__).parent / "data" / "chunks.jsonl"
    return {
        json.loads(line)["page"]
        for line in chunks_path.read_text().splitlines() if line.strip()
    }


def test_every_mapped_page_exists_in_the_theory_corpus():
    missing = all_mapped_pages() - _corpus_pages()
    assert not missing, (
        f"citation map references pages absent from chunks.jsonl: {sorted(missing)}"
    )


def test_all_mapped_pages_aggregates_slot_and_family_tables():
    pages = all_mapped_pages()
    assert {91, 96} <= pages
    assert {33, 34} <= pages
    assert {22, 48} <= pages
    assert {57, 59, 64, 67, 73, 74} <= pages
