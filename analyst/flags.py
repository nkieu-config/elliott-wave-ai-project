"""The grounding flags, as one table.

A flag is only real if all four consumers agree on it: the gate detects it, the
report coerces it, `ok`/`has_soft_flags` grade it, and the repair prompt tells the
model how to fix it. Hand-listing it in four places is how a flag ends up
detected, serialized, and silently ignored — so all four derive from `FLAGS`.

Adding a flag: add the field to `CitationReport` and one entry here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Severity = Literal["hard", "soft"]


@dataclass(frozen=True)
class ClaimFlag:
    """One flag. `field` names the `CitationReport` tuple it populates."""

    field: str
    severity: Severity
    # `{listed}` is replaced with the offending claims, one per bulleted line.
    repair: str
    # None → not detectable from claim text alone: supplied by the caller
    # (semantic grounding, the number check) or read off the claim's structure.
    detect: Callable[[str], bool] | None = None

    @property
    def is_hard(self) -> bool:
        return self.severity == "hard"

    def matches(self, text: str) -> bool:
        return self.detect is not None and self.detect(text)


# Rule 5 leaked identifiers: snake_case, UPPER_CASE w/ underscore (≥1 letter),
# leg codes S2/T1 (lowercase s4 allowed for chart annotations), link codes +S/+T/+SE.
_RAW_IDENTIFIER_RE = re.compile(
    r"\b(?:[a-z]+_[a-z][a-z_]*"
    r"|(?=[A-Z0-9_]*[A-Z])[A-Z0-9]+_[A-Z0-9_]+"
    r"|[ST]\d+)\b"
    r"|(?<![A-Za-z0-9_])\+[ST]E?(?![A-Za-z0-9_])"
)

# Arithmetic chain (operator + ≥2 numbers). SOFT — two-number floor avoids
# tripping on bare metric definitions ("drawdown ratio = max drawdown divided by leg length").
_ARITH_OP_RE = re.compile(
    r"[×*÷]|\b(?:times|multipl(?:y|ies|ied|ying)|divided\s+by|product\s+of)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# Prose page ref — citation belongs in `pages` field (rule 3). SOFT.
_PROSE_PAGE_RE = re.compile(r"\b(?:pages?\s+\d|p\.\s*\d)", re.IGNORECASE)

# Internal-implementation names forbidden by rule 7. SOFT.
_META_SYSTEM_RE = re.compile(
    r"\b(?:"
    r"verifier"
    r"|layer[\s\-]?1"
    r"|the\s+gate"
    r"|citation\s+gate"
    r"|bottleneck\s+diagnos"
    r"|score[\s\-]?components?\s+block"
    r"|targets?\s+block"
    r"|confirmation\s+block"
    r"|scenario[\s\-]?comparison\s+block"
    r")\b",
    re.IGNORECASE,
)

# Procedural recitation — model paraphrases a check's definition instead of
# reading chart values. Also catches hedged generalities. SOFT.
_PROCEDURAL_RECITATION_RE = re.compile(
    r"\b(?:"
    r"the\s+measurement\s+requires"
    r"|is\s+calculated\s+by"
    r"|is\s+computed\s+by"
    r"|involves?\s+(?:marking|measuring|comparing|computing)"
    r"|evaluates?\s+how\s+(?:much\s+|many\s+|deeply\s+)?"
    r"|assesses?\s+how\s+(?:much\s+|many\s+|smooth\s+|the\s+)?"
    r"|works\s+by\s+(?:marking|measuring|comparing|computing|taking)"
    r"|is\s+defined\s+as\s+(?:the\s+ratio|the\s+result)"
    r"|as\s+per\s+the\s+measurement\s+rules"
    # Hedged generalities — the model standing in for missing data
    r"|some\s+(?:retracements?\s+)?(?:may|might)\s+be\s+(?:too\s+)?(?:shallow|deep|small|large|fast|slow)"
    r"|may\s+be\s+too\s+(?:shallow|deep|small|large|fast|slow)"
    r"|may\s+not\s+(?:align|match|fit|conform|reach|hold)"
    r"|may\s+(?:differ|vary|diverge)"
    r"|might\s+(?:not\s+)?(?:align|match|fit|conform|reach|hold|differ|vary)"
    r"|do(?:es)?\s+not\s+always\s+(?:align|match|fit|reach)"
    r"|typically\s+(?:lands?|sits?|reaches?|spans?|takes?|runs?)"
    r"|generally\s+(?:one\s+(?:would|might)\s+expect|expect)"
    r"|tend\s+to\s+(?:deviate|exceed|land|fall|sit|align|differ|vary)"
    r"|deviate\s+from\s+typical"
    r"|expected\s+patterns?\b"
    # Abstract "% of pattern range" — succession block already gives dollar band.
    r"|\d+(?:\.\d+)?\s*%\s+of\s+(?:the\s+|this\s+)?(?:pattern'?s?|entire|full)\s+(?:full\s+)?(?:price\s+)?range"
    r")\b",
    re.IGNORECASE,
)

# Conjunction/adverb openers signalling a fragment. False positives acceptable — SOFT.
_FRAGMENT_OPENERS_RE = re.compile(
    r"^\s*(?:"
    r"And|But|Or|With|Meaning|Which|That"
    r"|Approximately|Roughly|About|Around"
    r")\s+(?:[a-z]|\d)",
    re.IGNORECASE,
)


def _is_arithmetic_chain(text: str) -> bool:
    return bool(_ARITH_OP_RE.search(text)) and len(_NUMBER_RE.findall(text)) >= 2


# Order is the order the repair prompt lists its issues in.
FLAGS: tuple[ClaimFlag, ...] = (
    ClaimFlag(
        field="unsourced_claims",
        severity="hard",
        repair=(
            '- These claims are typed "theory_claim" but their "pages" field '
            "is empty:\n{listed}\n"
            '  For each one: list one or more allowed pages in "pages", OR '
            'retype it as "data_observation" / "disclosure".'
        ),
    ),
    ClaimFlag(
        field="raw_identifier_claims",
        severity="hard",
        detect=lambda t: bool(_RAW_IDENTIFIER_RE.search(t)),
        repair=(
            "- These claims leak a raw code identifier (a code-style token "
            'such as "pull_depth_discipline" or "5W_SIDEWAY") instead of '
            "plain words:\n{listed}\n"
            '  Rewrite each in plain language — e.g. "the pullback-depth '
            'check", or "a five-wave sideways pattern".'
        ),
    ),
    ClaimFlag(
        field="arithmetic_chain_claims",
        severity="soft",
        detect=_is_arithmetic_chain,
        repair=(
            "- These claims narrate an arithmetic chain — a calculation "
            'such as "X times Y":\n{listed}\n'
            "  Rewrite each to state what the numbers MEAN for the wave "
            "count, not how they combine. Drop the explicit "
            "multiplication / division."
        ),
    ),
    ClaimFlag(
        field="prose_page_claims",
        severity="soft",
        detect=lambda t: bool(_PROSE_PAGE_RE.search(t)),
        repair=(
            "- These claims write a page reference inside the prose — a "
            'phrase such as "page 103" or "p.91":\n{listed}\n'
            "  Remove the page reference from the text entirely; put the "
            'page number(s) ONLY in the claim\'s "pages" field. The (p.N) '
            "citation is formatted for you — never write one in the text."
        ),
    ),
    ClaimFlag(
        field="ungrounded_citation_claims",
        severity="soft",
        repair=(
            '- These claims are typed "theory_claim" but their cited page '
            "does NOT actually state what the claim asserts:\n{listed}\n"
            "  For each one: either cite the page that genuinely contains "
            "this theory, or — if no provided page supports it — rewrite it "
            'as a "data_observation" / "disclosure". Do not state Elliott-Wave '
            "theory the cited page does not contain."
        ),
    ),
    ClaimFlag(
        field="meta_system_claims",
        severity="soft",
        detect=lambda t: bool(_META_SYSTEM_RE.search(t)),
        repair=(
            "- These claims name an internal system component (a phrase such "
            'as "the verifier", "Layer-1", "the gate", or "bottleneck '
            'diagnosis") instead of describing the underlying fact:\n'
            "{listed}\n"
            "  Rewrite each in user-facing terms — say what the fact IS, not "
            'which subsystem produced it. For example, "the verifier has '
            'not evaluated this scenario" → "the rule check waits until '
            'the pattern completes"; "the Layer-1 data shows" → "the '
            'chart shows".'
        ),
    ),
    ClaimFlag(
        field="procedural_recitation_claims",
        severity="soft",
        detect=lambda t: bool(_PROCEDURAL_RECITATION_RE.search(t)),
        repair=(
            "- These claims recite a check's GENERAL procedure (e.g. "
            '"evaluates how X by Y", "the measurement requires marking '
            'the start and end of a leg") instead of saying what THIS '
            "chart's values MEAN:\n{listed}\n"
            "  Rewrite each so it reads as an interpretation of this "
            "scenario's specific numbers: which leg / pair, what value, "
            "and what that value implies for the reader's confidence. The "
            "dashboard already shows the definitions; the model's job is "
            "the interpretation."
        ),
    ),
    ClaimFlag(
        field="fabricated_number_claims",
        severity="soft",
        repair=(
            "- These claims state a numeric figure that is NOT present in "
            "the Layer-1 data block (a rule-4 violation):\n{listed}\n"
            "  For each one: either drop the figure entirely, or replace it "
            "with the exact value as written in the Layer-1 block. Never "
            "round, recompute, or invent a number. Standard Fibonacci ratios "
            "(0.382 / 0.5 / 0.618 …) are fine without grounding; chart "
            "figures (prices, ratios, percentages) are not."
        ),
    ),
    ClaimFlag(
        field="fragment_claims",
        severity="soft",
        detect=lambda t: bool(_FRAGMENT_OPENERS_RE.match(t)),
        repair=(
            "- These claims read as SENTENCE FRAGMENTS — they open with "
            '"And ", "With ", "Meaning ", "Which ", "That " etc., '
            "or otherwise lack a self-contained subject + verb:\n{listed}\n"
            "  Rewrite each as a complete sentence (subject + verb + "
            "complete predicate), OR merge it into the prior claim so the "
            "two together form one grammatical sentence. The narration is "
            "rendered as plain prose; fragments read as broken writing."
        ),
    ),
)

# The subset the gate can find by reading claim text.
TEXT_FLAGS: tuple[ClaimFlag, ...] = tuple(f for f in FLAGS if f.detect is not None)

HARD_FLAGS: tuple[ClaimFlag, ...] = tuple(f for f in FLAGS if f.is_hard)
SOFT_FLAGS: tuple[ClaimFlag, ...] = tuple(f for f in FLAGS if not f.is_hard)


def render_repair(flag: ClaimFlag, claims: tuple[str, ...]) -> str:
    listed = "\n".join(f"    • {s}" for s in claims)
    return flag.repair.replace("{listed}", listed)
