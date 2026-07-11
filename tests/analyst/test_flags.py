"""The table is the invariant: a flag that is detected but graded by nobody is
the failure mode this suite exists to make impossible.
"""

from dataclasses import fields

import pytest

from analyst.flags import FLAGS, HARD_FLAGS, SOFT_FLAGS, TEXT_FLAGS, render_repair
from analyst.prompts.repair import build_repair_prompt
from analyst.schemas.citation import CitationReport

_CLAIM = "A claim that trips this flag."


def _report_with(field: str) -> CitationReport:
    return CitationReport(**{field: (_CLAIM,)})


def test_every_claims_field_has_a_flag_entry() -> None:
    declared = {f.name for f in fields(CitationReport) if f.name.endswith("_claims")}
    tabled = {f.field for f in FLAGS}
    assert declared == tabled, (
        f"untabled fields={declared - tabled}, table entries with no field={tabled - declared}"
    )


def test_severities_partition_the_table() -> None:
    assert set(HARD_FLAGS) | set(SOFT_FLAGS) == set(FLAGS)
    assert not set(HARD_FLAGS) & set(SOFT_FLAGS)


@pytest.mark.parametrize("flag", FLAGS, ids=lambda f: f.field)
def test_every_flag_is_graded(flag) -> None:
    # The bug this prevents: a flag detected, serialized, and acted on by nobody.
    report = _report_with(flag.field)
    if flag.is_hard:
        assert not report.ok, f"{flag.field} is HARD but does not fail the gate"
    else:
        assert report.ok, f"{flag.field} is SOFT but fails the gate"
        assert report.has_soft_flags, f"{flag.field} is SOFT but earns no repair pass"


@pytest.mark.parametrize("flag", FLAGS, ids=lambda f: f.field)
def test_every_flag_reaches_the_repair_prompt(flag) -> None:
    out = build_repair_prompt("BASE", "prior", _report_with(flag.field))
    assert _CLAIM in out
    assert render_repair(flag, (_CLAIM,)) in out


@pytest.mark.parametrize("flag", FLAGS, ids=lambda f: f.field)
def test_every_flag_serializes_and_round_trips(flag) -> None:
    report = _report_with(flag.field)
    assert report.to_dict()[flag.field] == [_CLAIM]
    assert getattr(CitationReport.from_dict(report.to_dict()), flag.field) == (_CLAIM,)


@pytest.mark.parametrize("flag", TEXT_FLAGS, ids=lambda f: f.field)
def test_text_detectors_are_callable_predicates(flag) -> None:
    assert isinstance(flag.matches("plain words with nothing wrong"), bool)


def test_flags_without_a_detector_never_self_match() -> None:
    # These are supplied by the caller (grounding, number check) or read off the
    # claim's structure — the gate's text loop must not invent them.
    for flag in set(FLAGS) - set(TEXT_FLAGS):
        assert not flag.matches(_CLAIM)


def test_repair_placeholder_is_substituted_for_every_flag() -> None:
    for flag in FLAGS:
        rendered = render_repair(flag, (_CLAIM,))
        assert "{listed}" not in rendered, f"{flag.field} left its placeholder unsubstituted"
        assert _CLAIM in rendered


def test_clean_report_is_ok_and_has_no_soft_flags() -> None:
    report = CitationReport()
    assert report.ok
    assert not report.has_soft_flags
