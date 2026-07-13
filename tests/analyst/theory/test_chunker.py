from pathlib import Path

import pytest

from analyst.theory.chunker import Chunk, chunk_theory_file, enrich_aliases


def test_chunk_extracts_page_number_and_body(tmp_path: Path):
    f = tmp_path / "theory.md"
    f.write_text(
        "# Title\n\n"
        "## Page 6\n\nIntro text.\n\n---\n\n"
        "## Page 7\n\nMore text.\n\n",
        encoding="utf-8",
    )
    chunks = chunk_theory_file(f)
    assert [c.page for c in chunks] == [6, 7]
    assert "Intro text" in chunks[0].body
    assert "More text" in chunks[1].body


def test_chunk_against_real_theory_file():
    real = Path("analyst/theory/corpus/elliott_wave_theory_en.md")
    if not real.exists():
        pytest.skip(f"{real} not present — running outside repo")
    chunks = chunk_theory_file(real)
    pages = [c.page for c in chunks]
    assert len(chunks) >= 50
    assert pages == sorted(pages), "pages must come in ascending order"
    for p in (34, 55, 99, 100, 110):
        assert p in pages, f"missing page {p}"


def test_enrich_aliases_appends_linkwave_names():
    chunks = [
        Chunk(page=1, body="A +T extends the trend; a +S goes sideways."),
        Chunk(page=2, body="When +S exceeds 161.8% it becomes +SE."),
        Chunk(page=3, body="Wave s3 must be longer than s2."),  # leg codes only
    ]
    out = enrich_aliases(chunks)
    assert "Trend linkage" in out[0].body and "Sideway linkage" in out[0].body
    # +SE must resolve distinctly from +S.
    assert "Sideway-Expand linkage" in out[1].body
    # Leg-only page untouched — no false enrichment.
    assert out[2] is chunks[2]
    # Enrichment is additive, original text preserved.
    assert out[0].body.startswith("A +T extends the trend")
