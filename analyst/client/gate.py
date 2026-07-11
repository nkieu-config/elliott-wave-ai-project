from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from analyst.flags import TEXT_FLAGS
from analyst.schemas.citation import CitationReport
from analyst.schemas.narration import NarrationDraft, render_narration

# Floor below which rendered narration is degenerate (prompts ask for 2-3 paragraphs).
_MIN_NARRATION_CHARS = 120


def gate_narration_draft(
    draft: NarrationDraft | None,
    *,
    allowed_pages: Iterable[int],
    layer1_fallback: str,
    min_chars: int = _MIN_NARRATION_CHARS,
) -> tuple[str, CitationReport, bool]:
    # min_chars override: Q&A answers a single question, so its floor is lower
    # than the 2-3 paragraph narration modes default to.
    allowed_set = frozenset(allowed_pages)

    # malformed_json ≠ too_short — long answer can fail structured-output parsing.
    if draft is None:
        return (
            layer1_fallback,
            CitationReport(allowed_pages=allowed_set, malformed_json=True),
            True,
        )

    cited: set[int] = set()
    unsourced: list[str] = []
    detected: dict[str, list[str]] = {f.field: [] for f in TEXT_FLAGS}
    for c in draft.all_claims:
        for flag in TEXT_FLAGS:
            if flag.matches(c.text):
                detected[flag.field].append(c.text)
        if c.type != "theory_claim":
            continue
        if not c.pages:
            unsourced.append(c.text)
        else:
            cited.update(c.pages)

    rendered = render_narration(draft)
    payload: dict[str, Any] = {
        name: tuple(claims) for name, claims in detected.items()
    }
    payload["cited_pages"] = frozenset(cited)
    payload["allowed_pages"] = allowed_set
    payload["unsourced_claims"] = tuple(unsourced)
    payload["too_short"] = len(rendered.strip()) < min_chars
    report = CitationReport(**payload)
    if report.ok:
        return rendered, report, False
    return layer1_fallback, report, True
