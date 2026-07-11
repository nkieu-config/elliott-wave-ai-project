from __future__ import annotations

from analyst.flags import FLAGS, render_repair
from analyst.schemas.citation import CitationReport


def build_repair_prompt(
    base_prompt: str, prior_answer: str, report: CitationReport,
    *, mode: str = "analysis",
) -> str:
    issues: list[str] = []
    if report.malformed_json:
        issues.append(
            "- Your previous answer was not valid JSON and could not be "
            "parsed. Return ONLY a single well-formed JSON object of the "
            'shape {"paragraphs": [[<claim>, ...], ...]} — no markdown '
            "fences, no preamble, every bracket and brace balanced."
        )
    if report.too_short:
        # QA answers may be a single sentence; narration wants 2-3 paragraphs.
        if mode == "qa":
            issues.append(
                "- Your previous answer was empty or far too short. Produce a "
                "complete answer that directly addresses the question; a single "
                "clear sentence is sufficient for a simple question."
            )
        else:
            issues.append(
                "- Your previous answer was empty or far too short. Produce a "
                "complete narration (2-3 short paragraphs) that addresses the "
                "mode's question in full."
            )
    if report.disallowed_pages:
        cited = ", ".join(f"(p.{p})" for p in sorted(report.disallowed_pages))
        allowed = (
            ", ".join(f"(p.{p})" for p in sorted(report.allowed_pages))
            or "(no pages are citeable here)"
        )
        issues.append(
            f"- You cited {cited}, which are NOT in the allowed set. "
            f"Cite only these pages: {allowed}. Remove or correct every "
            f"disallowed citation."
        )
    for flag in FLAGS:
        claims = getattr(report, flag.field)
        if claims:
            issues.append(render_repair(flag, claims))
    issues_md = "\n".join(issues) if issues else "- (no specific issue recorded)"
    return (
        f"{base_prompt}\n\n"
        "[REVISION REQUEST]\n"
        "Your previous answer needs the revisions below before it can be "
        "shown.\n\n"
        f"--- previous answer ---\n{prior_answer}\n"
        "--- end of previous answer ---\n\n"
        f"Problems to fix:\n{issues_md}\n\n"
        "Rewrite the answer as a valid JSON NarrationDraft with the same "
        "content, facts, and mode scope — change only what is needed to fix "
        "the problems above. Output the JSON object only, with no preamble."
    )
