from wowperf.domain.analysis.attempt_shape import classify_attempt
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player


def _players(count: int) -> tuple[Player, ...]:
    """Twenty raiders cannot come from a four-name allowlist, so they are indexed."""
    return tuple(
        Player(
            actor_id=index,
            name=f"Raider {index}",
            class_name="Mage",
            spec="Frost",
            item_level=690,
        )
        for index in range(count)
    )


def _encounter(*, kill: bool, boss_percentage: float | None, seconds: float) -> Encounter:
    return Encounter(
        report_code="AbCdEf",
        fight_id=1,
        encounter_id=3492,
        boss_name="The Boss",
        difficulty=5,
        partition=1,
        size=20,
        kill=kill,
        boss_percentage=boss_percentage,
        start_ms=0,
        end_ms=int(seconds * 1000),
        players=_players(20),
    )


def _deaths(count: int) -> tuple[Death, ...]:
    return tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=1000 * index,
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(count)
    )


def _sample(*, seconds: float, deaths: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ZzZzZz",
                    fight_id=index,
                    size=20,
                    duration_ms=int(seconds * 1000),
                    deaths=deaths,
                ),
                abilities=(),
            )
            for index in range(5)
        )
    )


def test_a_dismantled_raid_reads_as_execution() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
        _deaths(14),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert finding.id == "wipe.cause"
    assert finding.confidence is Confidence.INFERRED
    assert "execution" in finding.title.lower()
    assert "14" in finding.detail


def test_an_intact_raid_on_a_long_attempt_reads_as_throughput() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(1),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()


def test_a_dismantled_raid_on_a_long_attempt_reads_as_both_deaths_first() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(14),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "both" in finding.title.lower()
    assert finding.detail.lower().index("died") < finding.detail.lower().index("damage")


def test_an_unlucky_wipe_near_the_kill_is_withheld() -> None:
    """Raid mostly alive, boss nearly dead, attempt shorter than the references.
    Neither reading holds, so the verdict abstains rather than guessing."""
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=2.0, seconds=250.0),
            _deaths(3),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_a_kill_gets_no_verdict() -> None:
    assert (
        classify_attempt(
            _encounter(kill=True, boss_percentage=0.0, seconds=400.0),
            _deaths(14),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_an_attempt_with_no_reference_sample_is_withheld() -> None:
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(1),
            MechanicsSample(),
        )
        is None
    )


def test_an_attempt_the_report_gives_no_boss_health_for_is_withheld() -> None:
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=None, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_a_boss_below_the_wall_on_a_long_attempt_is_withheld() -> None:
    """Boss health under WALL_HEALTH, attempt already as long as the references, hardly
    anyone dead. Guards WALL_HEALTH's floor against being read too low: lower it and 15%
    boss health starts reading as a wall, turning this into a throughput verdict."""
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=15.0, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_a_raid_that_is_neither_dismantled_nor_intact_is_withheld() -> None:
    """Boss health and duration both read as stalled, but only three in four survived --
    below the intact floor without being dismantled either. Guards INTACT_SHARE's floor
    against being read too low: lower it and 75% alive starts reading as intact."""
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(5),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_no_verdict_from_classify_attempt_names_a_remedy() -> None:
    """Mirrors the guard on compare_lethal_abilities's own findings
    (tests/domain/comparison/test_mechanics.py). classify_attempt is the one finding in
    this plan licensed to judge -- execution or throughput -- and that license runs only
    as far as naming the attempt's shape, never the fix. Checked over all three verdict
    branches and five places wording can appear: the title, the detail, every fact's
    label and value, and every evidence line.

    The word list is wider than compare_lethal_abilities's own: "lever", "drill",
    "practice" and "should" are added because this finding's execution branch shipped a
    sentence recommending a drill before review caught it. "failed to" stands in for the
    mirrored test's bare "failed": every title here reads "This attempt failed on
    <headline>", stating that the attempt did not end in a kill -- reviewed and approved
    wording, not a claim about anyone's fault -- so a bare "failed" would flag that
    phrase itself. "failed to" is the shape an assigned-fault claim would actually take
    ("failed to interrupt") and never appears in this module's output.
    """
    findings = (
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(14),
            _sample(seconds=300.0, deaths=1),
        ),  # both
        classify_attempt(
            _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
            _deaths(14),
            _sample(seconds=300.0, deaths=1),
        ),  # execution
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        ),  # throughput
    )
    assert all(finding is not None for finding in findings), "the guard needs a finding per branch"

    for finding in findings:
        assert finding is not None
        for word in (
            "missed",
            "avoidable",
            "should have",
            "failed to",
            "lever",
            "drill",
            "practice",
            "should",
        ):
            assert word not in finding.title.lower(), finding.title
            assert word not in finding.detail.lower(), finding.detail
            for fact in finding.facts:
                assert word not in fact.label.lower(), fact.label
                assert word not in fact.value.lower(), fact.value
            for line in finding.evidence:
                assert word not in line.lower(), line
