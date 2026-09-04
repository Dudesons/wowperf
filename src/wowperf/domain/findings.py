# ABOUTME: The output type of every analyser, and the ranking that orders a report.
# ABOUTME: Confidence is mandatory so a reader always knows how much to trust a claim.

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Confidence(StrEnum):
    """How much the log actually supports a claim.

    MEASURED  read straight from the log
    DERIVED   computed by a documented formula over logged facts
    INFERRED  requires an assumption the log cannot confirm
    """

    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

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
