# ABOUTME: The findings one boss earns on the night summary: progression's, plus the night's own.
# ABOUTME: Pins that the pooled defensives finding runs with death cards and never without.

from tests.domain.analysis.test_defensives_at_death import BLOOD, IBF, owned_and_died
from tests.domain.comparison.test_pace_night import a_sample
from tests.domain.progression_fixtures import a_loaded_series
from wowperf.domain.analysis.attempt_shape import classify_attempt
from wowperf.domain.analysis.defensives import REPEAT_READY_PREFIX
from wowperf.domain.analysis.night_service import analyse_night_boss
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.analysis.severity import SEVERITY_BY_FAMILY
from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.pace_night import NIGHT_PACE_ID
from wowperf.domain.progression import LoadedProgression


def a_firing_boss() -> LoadedProgression:
    """Emberkin dies on two pulls with Icebound Fortitude up: the pooled finding fires."""
    return a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF))


def test_with_death_cards_the_pooled_finding_follows_the_progression_findings() -> None:
    series = a_firing_boss()
    found = analyse_night_boss(series, BLOOD, death_cards=True)
    progression = analyse_progression(series)

    assert found[: len(progression)] == progression
    pooled = found[len(progression):]
    assert [f.id for f in pooled] == [f"{REPEAT_READY_PREFIX}emberkin"]
    for finding in found:
        assert finding.id.split(".")[0] in SEVERITY_BY_FAMILY


def test_without_death_cards_it_is_never_asked() -> None:
    """At --no-deaths there is no casts stream; asking would imply a check that never ran."""
    series = a_firing_boss()
    assert analyse_night_boss(series, BLOOD, death_cards=False) == analyse_progression(series)


def test_the_pace_line_follows_when_pace_samples_are_given() -> None:
    """Both of the firing boss's pulls (fight ids 1 and 2) are wipes with samples."""
    series = a_firing_boss()
    pace = {1: a_sample(80), 2: a_sample(80)}
    found = analyse_night_boss(series, BLOOD, death_cards=True, pace=pace)
    assert [f.id for f in found].count(NIGHT_PACE_ID) == 1


def test_no_pace_argument_carries_no_pace_line() -> None:
    series = a_firing_boss()
    found = analyse_night_boss(series, BLOOD, death_cards=True)
    assert NIGHT_PACE_ID not in [f.id for f in found]


def test_the_boss_rollups_follow_when_pull_findings_are_given() -> None:
    """Both of the firing boss's pulls are wipes; each verdict is withheld for want of a sample."""
    series = a_firing_boss()
    withheld = classify_attempt(
        series.attempts_with_events[0].encounter, (), MechanicsSample()
    )
    assert withheld is not None
    pull_findings = {1: [withheld], 2: [withheld]}

    found = analyse_night_boss(series, BLOOD, death_cards=True, pull_findings=pull_findings)

    assert found[:-1] == analyse_night_boss(series, BLOOD, death_cards=True)
    assert found[-1].id == "progression.lead.verdicts"
    assert found[-1].title == "No wipe's verdict could be read, of 2 wipes"


def test_no_pull_findings_carry_no_boss_rollup() -> None:
    series = a_firing_boss()
    found = analyse_night_boss(series, BLOOD, death_cards=True)
    assert not [f.id for f in found if f.id.startswith("progression.lead.")]


def test_the_pace_line_does_not_depend_on_death_cards() -> None:
    series = a_firing_boss()
    pace = {1: a_sample(80), 2: a_sample(80)}
    found = analyse_night_boss(series, BLOOD, death_cards=False, pace=pace)
    assert NIGHT_PACE_ID in [f.id for f in found]
