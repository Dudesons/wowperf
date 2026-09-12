# ABOUTME: The output type of every analyser, and the ranking that orders a report.
# ABOUTME: Confidence is mandatory so a reader always knows how much to trust a claim.

from collections.abc import Iterable
from enum import StrEnum

from wowperf.domain.base import Frozen


class Confidence(StrEnum):
    """How much the log actually supports a claim.

    MEASURED  read from the log, or plain arithmetic over logged facts and dated
              constants, needing no assumption that could be wrong
    DERIVED   reconstructed by a documented rule, or computed with a modelling
              choice that could be wrong
    INFERRED  requires an assumption the log cannot confirm
    """

    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"


class FindingFact(Frozen):
    """One labelled figure a finding carries, for a panel to render.

    A finding states its figures twice already: in a title a person reads and
    in evidence strings a person scans. A hover panel wants them a third way,
    as labels and values, and the only alternative was for the report to parse
    back strings the analysis had just formatted -- "range 0.7 to 2.1 casts a
    minute across 5 top parses" taken apart into four numbers again.

    `confidence` is None for a figure read straight from the log, matching
    `report.model.TooltipLine.tier`, where None is the panel's default tier and
    means measured. Set it on anything that is not: a rate the report computed
    is `derived`, a cooldown assumed from a data file is `inferred`. Leaving
    one of those unset does not abstain -- it badges the figure measured.
    """

    label: str
    value: str
    confidence: Confidence | None = None


class Finding(Frozen):
    id: str
    title: str
    detail: str
    confidence: Confidence
    seconds_lost: float | None = None
    evidence: tuple[str, ...] = ()
    # The same figures the evidence states in prose, as labels and values a
    # hover panel can lay out. Empty on a finding with nothing a panel would
    # add to what its card already prints.
    facts: tuple[FindingFact, ...] = ()
    pull_index: int | None = None
    # The ability this finding is about, for the icon the page draws at its name.
    # `ability_id` is None on a finding that names no single ability; `ability_name`
    # is the same spelling the title uses, so locating it there is never a guess
    # about which words are the spell.
    ability_id: int | None = None
    ability_name: str = ""
    # The word a digit-free narrative may use in place of this finding's count.
    # Empty on any finding that is not an aggregate over a sample.
    quantifier: str = ""
    # The fragment id of the player this finding is about, from `slugs_by_actor`.
    # Empty on any finding that is a statement about the run rather than about
    # one player: a route, a tempo or a confound belongs to nobody.
    player_slug: str = ""


def quantifier_for(matching: int, total: int) -> str:
    """The word a digit-free narrative may use for `matching of total`.

    The narrative file is refused if it contains a digit, so a count cannot
    reach the reader through it. Computing the word here keeps the reading of
    the ratio in tested Python: the narrative echoes, it does not calculate.

    "none" is a real aggregate and gets its own word, parallel to "every":
    `compare.confound.affixes` fires precisely when no reference shared our
    affix set. Only a sample with no members at all yields nothing to say.
    """
    if total <= 0:
        return ""
    if matching <= 0:
        return "none"
    if matching == total:
        return "every"
    if matching * 2 > total:
        return "most"
    if matching * 2 == total:
        return "about half"
    return "some"


def quantity(n: int, singular: str, plural: str) -> str:
    """`n` and its noun, in whichever number `n` calls for.

    Titles that state a count over a set read it back to a reader, and "1
    abilities" is the kind of slip that gets noticed before the finding does.
    Both forms are passed in rather than derived: English pluralisation is not
    a rule worth implementing for the two nouns this has to spell.
    """
    return f"{n} {singular}" if n == 1 else f"{n} {plural}"


def rank_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Order findings by time cost, descending. Findings with no time cost come last."""
    return sorted(
        findings,
        key=lambda finding: (finding.seconds_lost is None, -(finding.seconds_lost or 0.0)),
    )
