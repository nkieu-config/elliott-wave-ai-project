from __future__ import annotations

import json
import logging

import numpy as np
import pytest

from analyst._fingerprint import PIPELINE_FINGERPRINT
from analyst.client.cache import build_cache_key
from analyst.orchestrator import (
    _decode_cache_payload,
    _extract_citations,
    _parse_chunks_jsonl,
    _retrieval_pages,
    build_analyst,
)
from analyst.theory.chunker import Chunk
from tests.analyst._helpers import make_scenario
from tests.analyst._helpers import make_uptrend_then_drop_bars as _make_bars


def _json_narration(*claims: tuple[str, str, list[int]]) -> str:
    para = [{"text": t, "type": typ, "pages": pgs} for t, typ, pgs in claims]
    return json.dumps({"paragraphs": [para]})


_PASS_TEXT = (
    "The scenario placement follows from its measured slot values and the "
    "way the structural dimension sets the overall ranking for this count."
)


def _passing_json(*, theory_page: int | None = None) -> str:
    claims: list[tuple[str, str, list[int]]] = [
        (_PASS_TEXT, "data_observation", [])
    ]
    if theory_page is not None:
        claims.append(
            ("This wave behaviour reflects a theory rule.", "theory_claim",
             [theory_page])
        )
    return _json_narration(*claims)


_ARITH_TEXT = (
    "The overall score of 0.374 is the product 0.467 × 0.800 of quality and "
    "commitment, which is what places this scenario at its current rank."
)


def _arithmetic_json() -> str:
    return _json_narration((_ARITH_TEXT, "data_observation", []))


_PROSE_REJECTED = "Speculative theory claim (p.999)."


class _StubLLM:
    model_id = "stub"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses) or [""]
        self.calls = 0

    def complete(self, prompt, *, format=None):
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


def test_analyze_returns_layer1_when_llm_disabled(tmp_path):
    chunks = [
        Chunk(page=34, body="Confirmation Concept ..."),
        Chunk(page=33, body="Trend-Line s2-s4 ..."),
    ]
    embeddings = np.zeros((len(chunks), 4), dtype=np.float32)
    a = build_analyst(
        chunks=chunks, embeddings=embeddings, llm_client=None, cache_dir=tmp_path,
    )
    sc = make_scenario()
    bars = _make_bars()
    out = a.analyze(sc, bars=bars, mode="explanation")
    assert out.layer1.bottleneck is not None
    assert out.layer1.confirmation is not None
    assert out.layer1.targets is not None
    assert out.layer1.succession is not None
    assert out.layer1.succession.is_terminal is True
    assert out.narration is not None
    assert out.fell_back is True


def test_retrieval_pages_scenario_outlook_is_family_aware():
    # Assert each family pulls its signature pages and excludes other families'
    # distinctive pages — an invariant that survives non-distinctive citation
    # additions, unlike pinning the full set. Signature pages per family:
    sig = {
        "3W": {48, 54, 55, 104, 112},
        "5W_SIDEWAY": {43, 74, 103, 111},
        "5W_TREND": {33, 34, 101, 110},
        "LINK_T": {105, 113},
    }
    for family, signature in sig.items():
        pages = _retrieval_pages(make_scenario(family=family, score_components={}),
                                 mode="scenario_outlook")
        assert signature <= pages, f"{family} missing its signature pages"
        others = set().union(*(s for f, s in sig.items() if f != family))
        assert pages.isdisjoint(others - signature), (
            f"{family} leaked another family's distinctive pages: "
            f"{pages & (others - signature)}"
        )


def test_retrieval_pages_slot_focus_covers_top_three_weakest():
    sc = make_scenario(family="5W_SIDEWAY", score_components={
        "speed_cluster": 0.9, "fib_push_pairs": 0.3,
        "pull_depth_discipline": 0.4, "pivot_sharpness": 0.8,
        "leg_smoothness": 0.2,
    })
    pages = _retrieval_pages(sc, mode="slot_focus")
    assert pages == {103, 111, 99, 100, 22}
    assert 91 not in pages and 96 not in pages


def test_retrieval_pages_differentiator_unions_competitor_families():
    primary = make_scenario(family="5W_SIDEWAY",
                            score_components={"fib_push_pairs": 0.5})
    competitor = make_scenario(family="5W_TREND",
                               score_components={"fib_push_pairs": 0.4})
    pages = _retrieval_pages(primary, mode="differentiator",
                             all_scenarios=[primary, competitor])
    assert {103, 111} <= pages
    assert {101, 110} <= pages


def test_extract_citations_expands_range():
    refs = _extract_citations("See the same-degree principle (p.91-96).")
    pages = sorted(r.page for r in refs)
    assert pages == [91, 92, 93, 94, 95, 96]


def test_extract_citations_handles_loose_page_forms():
    refs = _extract_citations(
        "Theory (p.96 notes the rule) and p.91's guideline both apply."
    )
    assert sorted(r.page for r in refs) == [91, 96]


def test_extract_citations_captures_surrounding_sentence():
    refs = _extract_citations(
        "First, the trendline broke (p.33). Next, retracement reached 100% (p.34)."
    )
    by_page = {r.page: r.claim_sentence for r in refs}
    assert "trendline" in by_page[33]
    assert "retracement" in by_page[34]


def test_raw_narration_preserved_when_gate_falls_back(tmp_path):
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=_StubLLM(_PROSE_REJECTED), cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert out.fell_back is True
    assert out.raw_narration is not None
    assert "(p.999)" in out.raw_narration


def test_layer1_cited_pages_are_added_to_allowed_pages(tmp_path):
    chunks: list[Chunk] = []
    embeddings = np.zeros((0, 4), dtype=np.float32)
    a = build_analyst(
        chunks=chunks, embeddings=embeddings,
        llm_client=_StubLLM(_passing_json(theory_page=34)),
        cache_dir=tmp_path,
    )
    sc = make_scenario()
    out = a.analyze(sc, bars=_make_bars(), mode="scenario_outlook")
    assert out.fell_back is False
    assert out.citation_report.ok


def test_analyze_llm_down_serves_fallback_without_caching(tmp_path):
    chunks: list[Chunk] = []
    embeddings = np.zeros((0, 4), dtype=np.float32)
    sc = make_scenario()

    class _DownLLM:
        model_id = "stub"  # match _StubLLM so the cache key is identical

        def complete(self, prompt, *, format=None):
            raise RuntimeError("ollama unreachable")

    a_down = build_analyst(
        chunks=chunks, embeddings=embeddings, llm_client=_DownLLM(), cache_dir=tmp_path,
    )
    down = a_down.analyze(sc, bars=_make_bars(), mode="scenario_outlook")
    assert down.fell_back is True
    assert down.narration  # deterministic template, not an exception

    # Same cache dir + same model_id: a recovered model must NOT serve a cached
    # fallback — the transient miss must not have been cached.
    a_up = build_analyst(
        chunks=chunks, embeddings=embeddings,
        llm_client=_StubLLM(_passing_json(theory_page=34)), cache_dir=tmp_path,
    )
    up = a_up.analyze(sc, bars=_make_bars(), mode="scenario_outlook")
    assert up.fell_back is False
    assert up.cached is False


def test_cache_key_uses_stable_model_id_across_fallover(tmp_path):
    # A client whose volatile model_id flips between calls must still hit the
    # cache: the key derives from the stable cache_model_id, not model_id. With
    # the old model_id-based key the second call re-keyed and re-hit the LLM.
    class _FlipLLM:
        cache_model_id = "stable"

        def __init__(self, *responses: str) -> None:
            self._responses = list(responses)
            self.calls = 0
            self.model_id = "A"

        def complete(self, prompt, *, format=None):
            self.calls += 1
            self.model_id = "A" if self.calls % 2 else "B"
            return self._responses[min(self.calls - 1, len(self._responses) - 1)]

    llm = _FlipLLM(_passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    sc, bars = make_scenario(), _make_bars()
    a.analyze(sc, bars=bars, mode="explanation")
    out2 = a.analyze(sc, bars=bars, mode="explanation")
    assert llm.calls == 1
    assert out2.cached is True


def test_analyze_with_stub_llm_caches_second_call(tmp_path):
    llm = _StubLLM(_passing_json())
    chunks = [Chunk(page=99, body="Fibonacci Retracement window ...")]
    embeddings = np.zeros((1, 4), dtype=np.float32)
    a = build_analyst(
        chunks=chunks, embeddings=embeddings, llm_client=llm, cache_dir=tmp_path,
    )
    sc = make_scenario()
    bars = _make_bars()
    a.analyze(sc, bars=bars, mode="explanation")
    out2 = a.analyze(sc, bars=bars, mode="explanation")
    assert llm.calls == 1
    assert out2.cached is True
    assert out2.raw_narration == _passing_json()


def test_fallback_is_mode_aware(tmp_path):
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=None, cache_dir=tmp_path,
    )
    sc, bars = make_scenario(), _make_bars()
    diff_out = a.analyze(sc, bars=bars, mode="differentiator")
    expl_out = a.analyze(sc, bars=bars, mode="explanation")
    assert diff_out.fell_back is True and expl_out.fell_back is True
    assert diff_out.narration != expl_out.narration
    assert "competitor" in diff_out.narration.lower()


def test_gate_fallback_is_cached(tmp_path):
    llm = _StubLLM(_PROSE_REJECTED)
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    sc, bars = make_scenario(), _make_bars()
    out1 = a.analyze(sc, bars=bars, mode="explanation")
    calls_after_first = llm.calls
    out2 = a.analyze(sc, bars=bars, mode="explanation")
    assert out1.fell_back is True
    assert llm.calls == calls_after_first
    assert out2.cached is True
    assert out2.fell_back is True
    assert out2.narration == out1.narration
    assert not out2.citation_report.ok
    assert out2.citation_report.disallowed_pages == out1.citation_report.disallowed_pages
    assert out2.raw_narration == out1.raw_narration
    assert out2.raw_narration is not None and "(p.999)" in out2.raw_narration


def test_decode_cache_payload_tolerates_legacy_string(tmp_path):
    narration, raw, fell_back, report = _decode_cache_payload(
        "Legacy plain narration."
    )
    assert narration == "Legacy plain narration."
    assert raw is None
    assert fell_back is False
    assert report.ok


def test_gate_repair_succeeds_on_second_attempt(tmp_path):
    llm = _StubLLM(_PROSE_REJECTED, _passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is False
    assert "slot values" in out.narration
    assert out.citation_report.ok


def test_gate_repair_failure_falls_back(tmp_path):
    llm = _StubLLM(_PROSE_REJECTED)
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is True


def test_gate_passing_answer_skips_repair(tmp_path):
    llm = _StubLLM(_passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 1
    assert out.fell_back is False


def test_empty_llm_response_falls_back_after_repair(tmp_path):
    llm = _StubLLM("")
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is True
    assert out.narration.strip()


def test_empty_first_response_repaired_to_valid(tmp_path):
    llm = _StubLLM("", _passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is False
    assert "slot values" in out.narration


def test_empty_cached_value_is_bypassed(tmp_path):
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=_StubLLM(_passing_json()), cache_dir=tmp_path,
    )
    sc, bars = make_scenario(), _make_bars()
    key = build_cache_key(sc, mode="explanation",
                          prompt_version=PIPELINE_FINGERPRINT,
                          model_id="stub", rag_enabled=True)
    a.cache.put(key, "")
    out = a.analyze(sc, bars=bars, mode="explanation")
    assert out.narration.strip()
    assert out.cached is False


def test_soft_arithmetic_flag_triggers_one_repair(tmp_path):
    llm = _StubLLM(_arithmetic_json(), _passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is False
    assert "slot values" in out.narration
    assert out.citation_report.arithmetic_chain_claims == ()


def test_soft_arithmetic_flag_repair_still_dirty_is_accepted(tmp_path):
    llm = _StubLLM(_arithmetic_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is False
    assert "0.467" in out.narration


def test_soft_repair_keeps_first_answer_when_repair_hard_regresses(tmp_path):
    llm = _StubLLM(_arithmetic_json(), "garbage — not JSON")
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    out = a.analyze(make_scenario(), bars=_make_bars(), mode="explanation")
    assert llm.calls == 2
    assert out.fell_back is False
    assert "0.467" in out.narration


def test_force_refresh_bypasses_the_cache(tmp_path):
    llm = _StubLLM(_passing_json())
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=llm, cache_dir=tmp_path,
    )
    sc, bars = make_scenario(), _make_bars()
    a.analyze(sc, bars=bars, mode="explanation")
    cached = a.analyze(sc, bars=bars, mode="explanation")
    assert cached.cached is True
    assert llm.calls == 1
    forced = a.analyze(sc, bars=bars, mode="explanation", force_refresh=True)
    assert forced.cached is False
    assert llm.calls == 2


def test_parse_chunks_jsonl_skips_malformed_lines(tmp_path, caplog):
    p = tmp_path / "chunks.jsonl"
    p.write_text(
        json.dumps({"page": 1, "body": "good chunk"}) + "\n"
        + "{this is not valid json\n"
        + "\n"
        + json.dumps({"page": 2, "body": "another good chunk"}) + "\n"
    )
    caplog.set_level(logging.WARNING, logger="analyst.orchestrator")
    out = _parse_chunks_jsonl(p)
    assert len(out) == 2
    assert out[0]["page"] == 1
    assert out[1]["page"] == 2
    assert any("malformed line 2" in r.message for r in caplog.records)


def test_parse_chunks_jsonl_raises_when_nothing_parses(tmp_path):
    p = tmp_path / "chunks.jsonl"
    p.write_text("{broken\n{also broken\n")
    with pytest.raises(RuntimeError, match="zero parsable chunks"):
        _parse_chunks_jsonl(p)


def test_compute_layer1_runs_without_llm(tmp_path):
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=None, cache_dir=tmp_path,
    )
    sc = make_scenario()
    bars = _make_bars()

    result = a.compute_layer1(sc, bars)

    assert result.scenario_id == sc.id
    assert result.bottleneck is not None
    assert result.confirmation is not None
    assert result.targets is not None
    assert result.succession is not None
    assert result.decision is not None
    assert result.alternative is None


def test_compute_layer1_alternative_brief_populated_with_multiple_scenarios(
    tmp_path,
):
    a = build_analyst(
        chunks=[], embeddings=np.zeros((0, 4), dtype=np.float32),
        llm_client=None, cache_dir=tmp_path,
    )
    sc1 = make_scenario()
    sc2 = make_scenario(scenario_id="alt", score=0.4)

    result = a.compute_layer1(sc1, _make_bars(), all_scenarios=[sc1, sc2])
    assert result.alternative is not None
