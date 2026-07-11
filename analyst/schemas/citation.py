from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Literal

from analyst.flags import FLAGS, HARD_FLAGS, SOFT_FLAGS

BindingType = Literal["rule_implementation", "concept_operationalization", "heuristic"]


@dataclass(frozen=True)
class TheoryRef:
    # pages=() + binding="heuristic" → no theory binding.
    pages: tuple[int, ...]
    concept: str
    binding: BindingType
    note: str


@dataclass(frozen=True)
class CitationRef:
    page: int
    claim_sentence: str


@dataclass(frozen=True)
class CitationReport:
    cited_pages: frozenset[int] = field(default_factory=frozenset)
    allowed_pages: frozenset[int] = field(default_factory=frozenset)
    # Severity, detection and repair text for every *_claims field below live in
    # analyst/flags.py — this is only their wire shape.
    unsourced_claims: tuple[str, ...] = ()
    raw_identifier_claims: tuple[str, ...] = ()
    arithmetic_chain_claims: tuple[str, ...] = ()
    ungrounded_citation_claims: tuple[str, ...] = ()
    prose_page_claims: tuple[str, ...] = ()
    meta_system_claims: tuple[str, ...] = ()
    procedural_recitation_claims: tuple[str, ...] = ()
    fabricated_number_claims: tuple[str, ...] = ()
    fragment_claims: tuple[str, ...] = ()
    too_short: bool = False
    # Distinct from too_short — parse failure ≠ genuinely-short answer.
    malformed_json: bool = False

    def __post_init__(self) -> None:
        for attr in ("cited_pages", "allowed_pages"):
            object.__setattr__(self, attr, frozenset(getattr(self, attr)))
        for flag in FLAGS:
            object.__setattr__(self, flag.field, tuple(getattr(self, flag.field)))

    def to_dict(self) -> dict[str, Any]:
        # Iterates fields() so a new flag serializes automatically — no hand-listing.
        # Sets are sorted for deterministic JSON; tuples become lists.
        out: dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, (frozenset, set)):
                out[f.name] = sorted(val)
            elif isinstance(val, tuple):
                out[f.name] = list(val)
            else:
                out[f.name] = val
        return out

    @classmethod
    def from_dict(cls, data: Any) -> CitationReport:
        # Missing keys fall back to field defaults; __post_init__ re-coerces
        # lists back to frozenset/tuple, so legacy/partial payloads stay valid.
        if not isinstance(data, dict):
            return cls()
        names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in names}
        return cls(**kwargs)

    @property
    def disallowed_pages(self) -> frozenset[int]:
        return self.cited_pages - self.allowed_pages

    @property
    def ok(self) -> bool:
        # Soft flags omitted — they trigger repair, not failure.
        if self.disallowed_pages or self.too_short or self.malformed_json:
            return False
        return not any(getattr(self, f.field) for f in HARD_FLAGS)

    @property
    def has_soft_flags(self) -> bool:
        # Each soft flag earns one repair pass but never fails the gate.
        return any(getattr(self, f.field) for f in SOFT_FLAGS)
