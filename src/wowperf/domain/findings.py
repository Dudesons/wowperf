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


class Finding(Frozen):
    id: str
    title: str
    detail: str
    confidence: Confidence
    seconds_lost: float | None = None
    evidence: tuple[str, ...] = ()
    pull_index: int | None = None


def rank_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Order findings by time cost, descending. Findings with no time cost come last."""
    return sorted(
        findings,
        key=lambda finding: (finding.seconds_lost is None, -(finding.seconds_lost or 0.0)),
    )
