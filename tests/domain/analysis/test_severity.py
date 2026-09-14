# ABOUTME: Raid findings rank by severity, then by what each analyser measured.
# ABOUTME: A family absent from the table ranks last rather than first: visible, not silent.

import pytest

from wowperf.domain.analysis.severity import (
    SEVERITY_BY_FAMILY,
    family_of,
    rank_raid_findings,
)
from wowperf.domain.findings import Confidence, Finding


def finding(finding_id: str, seconds: float | None = None) -> Finding:
    return Finding(
        id=finding_id, title=finding_id, detail="", confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def test_a_death_outranks_a_mechanic_even_with_no_seconds() -> None:
    ranked = rank_raid_findings([finding("mechanics.ability.0"), finding("deaths.total")])
    assert [item.id for item in ranked] == ["deaths.total", "mechanics.ability.0"]


def test_within_one_family_seconds_still_order_them() -> None:
    ranked = rank_raid_findings(
        [finding("deaths.single.0", 10.0), finding("deaths.single.1", 40.0)]
    )
    assert [item.id for item in ranked] == ["deaths.single.1", "deaths.single.0"]


def test_an_unknown_family_sorts_last_rather_than_first() -> None:
    # A new analyser that nobody added to the table must not silently outrank
    # a death. Last is the safe default: visible, and harmless.
    ranked = rank_raid_findings([finding("unheard.of.0"), finding("consumables.never.x")])
    assert [item.id for item in ranked] == ["consumables.never.x", "unheard.of.0"]


@pytest.mark.parametrize(
    "family",
    ["deaths", "mechanics", "players", "defensives", "consumables", "interrupts", "compare"],
)
def test_every_family_the_raid_path_emits_has_a_severity(family: str) -> None:
    # This catches a family dropped from the table. It cannot catch one added
    # to `analyse_encounter`: the list above is hand-written, not derived from
    # the analysers, so a new analyser's family would rank on UNKNOWN_SEVERITY
    # with this green. If you add an analyser, add its family in both places.
    assert family in SEVERITY_BY_FAMILY


def test_family_of_reads_the_first_segment() -> None:
    assert family_of("mechanics.ability.3") == "mechanics"
    assert family_of("deaths.total") == "deaths"
