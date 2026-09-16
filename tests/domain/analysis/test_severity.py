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
    [
        "deaths",
        "progression",
        "mechanics",
        "players",
        "defensives",
        "consumables",
        "interrupts",
        "compare",
    ],
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


def test_the_progression_family_has_a_severity() -> None:
    assert "progression" in SEVERITY_BY_FAMILY


def test_every_family_the_progression_path_emits_has_a_severity() -> None:
    """Derived from the analyser rather than hand-written, unlike the raid list above.

    This is the guard the raid version admits it cannot be: it builds a real
    `LoadedProgression` -- deepened with deaths and damage taken, not a bare
    `Progression` -- runs the real analyser, and checks every id it emits.

    A bare `LoadedProgression(progression=...)` with no `loaded` would compile
    and pass here while covering none of Layer 2's four ids, since every Layer
    2 analyser returns `None` on an attempt nothing was deepened for. Deepening
    the fixture and asserting each id by name is what closes that gap: R4 says
    every `progression.*` id, Layer 1 or Layer 2, resolves through the single
    `"progression"` key, and this proves that rather than assuming it.

    `a_deepened_trio` is the same three-attempt fixture
    `test_progression_service.py` uses to prove Layer 2 fires at all --
    reused here rather than rebuilt, so the two tests cannot silently drift
    onto two different claims about what "deepened" means.
    """
    from tests.domain.analysis.test_progression_service import a_deepened_trio
    from wowperf.domain.analysis.progression_service import analyse_progression

    findings = analyse_progression(a_deepened_trio())
    found_ids = {finding.id for finding in findings}

    assert findings, "a fixture that emits nothing would make this pass vacuously"
    for layer_two_id in (
        "progression.repeat.phase",
        "progression.repeat.first_death",
        "progression.repeat.ability",
        "progression.collapse",
    ):
        assert layer_two_id in found_ids, f"{layer_two_id} never fired from the deepened fixture"
    for finding in findings:
        family = finding.id.split(".")[0]
        assert family in SEVERITY_BY_FAMILY, f"{finding.id} ranks on UNKNOWN_SEVERITY"
