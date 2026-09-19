from wowperf.domain.analysis.attempt_shape import alive_over_time, classify_attempt
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
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


def _deaths(count: int, *, first_ms: int = 0, step_ms: int = 1000) -> tuple[Death, ...]:
    """`count` deaths, one per raider, from `first_ms` and `step_ms` apart.

    The timing is a parameter because the both-verdict reads it: the default
    packs every death into the opening seconds, which is the shape every test
    written before the ordering was measured assumed.
    """
    return tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=first_ms + step_ms * index,
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(count)
    )


def _resurrections(count: int, *, at_ms: int) -> tuple[Resurrection, ...]:
    """The first `count` raiders brought back at `at_ms`, by a teammate.

    `caster_id` is another raider rather than the actor's own id: a
    self-resurrection is a different thing, and nothing here reads the caster.
    """
    return tuple(
        Resurrection(
            actor_id=index,
            caster_id=19,
            ability_id=20484,
            ability_name="Rebirth",
            timestamp_ms=at_ms,
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
    """One death, not none: the branch fires from `INTACT_SHARE`, not from silence.

    The second assertion is the point. This fixture shipped producing "Nobody
    died and it still was not enough" over a raid that had just lost somebody,
    and the test read only the title, so the sentence was never seen.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(1),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()
    assert "nobody died" not in finding.detail.lower(), finding.detail


def test_a_throughput_verdict_over_four_deaths_claims_nobody_died_nowhere() -> None:
    """The branch's far edge: `INTACT_SHARE` of 0.8 admits four of twenty dead.

    Four deaths is the most this verdict can be reached with, and every one of
    them is named on the same page by `mechanics.lethal.*`. Checked over the
    detail, the evidence and every fact, because one true sentence in the
    detail would not undo a false one in a fact a panel prints.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(4),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()
    assert "16 of 20" in finding.detail, finding.detail
    for text in (finding.title, finding.detail, *finding.evidence,
                 *(fact.value for fact in finding.facts)):
        assert "nobody died" not in text.lower(), text


def test_a_deathless_throughput_verdict_still_says_nobody_died() -> None:
    """The one shape the design's own sentence is true of, kept rather than lost.

    Design section 8.3 writes the throughput row as "nobody died and it still
    was not enough", and a fix that deleted the clause outright would drop a
    true sentence along with the false one.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        (),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()
    assert "Nobody died and it still was not enough." in finding.detail


def test_a_both_verdict_whose_deaths_fell_early_says_the_deaths_came_first() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(14),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "both" in finding.title.lower()
    assert "The deaths came first" in finding.detail, finding.detail
    assert "second half" not in finding.detail, finding.detail


def test_a_both_verdict_whose_deaths_fell_late_says_the_damage_came_up_short_first() -> None:
    """The enrage wipe: a long attempt, then the whole raid dead in ten seconds.

    This is the most common shape of a both-attempt in progression and the one
    the constant sentence had exactly backwards. Nothing but the death
    timestamps differs from the fixture above.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(14, first_ms=390_000, step_ms=500),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "both" in finding.title.lower()
    assert "The damage came up short before the raid did" in finding.detail, finding.detail
    assert "came first" not in finding.detail, finding.detail


def test_a_both_verdict_whose_deaths_straddle_the_midpoint_names_no_order() -> None:
    """Fourteen deaths spread evenly across the attempt's own midpoint.

    Their median sits inside `ORDERING_MARGIN` of it, so neither ordering is
    supported and the clause is left off entirely -- the verdict itself still
    stands, because both halves of it are still measured.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(14, first_ms=180_000, step_ms=3_000),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "both" in finding.title.lower()
    assert "came first" not in finding.detail, finding.detail
    assert "second half" not in finding.detail, finding.detail


def test_an_unlucky_wipe_near_the_kill_is_withheld() -> None:
    """Raid mostly alive, boss nearly dead, attempt shorter than the references.
    Neither reading holds, so the verdict abstains rather than guessing."""
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=2.0, seconds=250.0),
            _deaths(3),
            _sample(seconds=300.0, deaths=1),
        )
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
    # That it withholds; the reason it gives is pinned separately, below.
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(1),
            MechanicsSample(),
        )
    )


def test_an_attempt_the_report_gives_no_boss_health_for_is_withheld() -> None:
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=None, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
    )


def test_a_boss_below_the_wall_on_a_long_attempt_is_withheld() -> None:
    """Boss health under WALL_HEALTH, attempt already as long as the references, hardly
    anyone dead. Guards WALL_HEALTH's floor against being read too low: lower it and 15%
    boss health starts reading as a wall, turning this into a throughput verdict."""
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=15.0, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
    )


def test_a_raid_that_is_neither_dismantled_nor_intact_is_withheld() -> None:
    """Boss health and duration both read as stalled, but only three in four survived --
    below the intact floor without being dismantled either. Guards INTACT_SHARE's floor
    against being read too low: lower it and 75% alive starts reading as intact."""
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(5),
            _sample(seconds=300.0, deaths=1),
        )
    )


def test_players_brought_back_count_among_the_living() -> None:
    """The fixture above, with four of the five dead resurrected.

    Everything else is identical, so only the resurrection stream can move the
    verdict -- and it moves it across `INTACT_SHARE`, from withheld to
    throughput. "Alive at the end" is the design's first evidence item, and
    subtracting everyone who ever died answers a different question.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(5),
        _sample(seconds=300.0, deaths=1),
        resurrections=_resurrections(4, at_ms=10_000),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()
    assert "19 of 20 were still alive" in finding.detail, finding.detail
    assert "19 of 20 alive at the end" in finding.evidence, finding.evidence
    # Still five players who died, and the evidence says so beside the living.
    # Nobody died twice here, so the line's event count and its player count
    # are both five; what this pins is that the players are still named.
    assert any("5 of our players" in line for line in finding.evidence), finding.evidence


def test_a_player_who_died_again_after_being_brought_back_is_not_among_the_living() -> None:
    """A resurrection counts only where it is the last thing that happened to a player.

    The same five raiders and the same four resurrections as the test above,
    except that all four rezzed players were killed again afterwards. Reading
    "was ever resurrected" rather than "was resurrected after their last death"
    would put all four back on their feet and reach a throughput verdict on a
    raid that ended with five of twenty on the floor.
    """
    deaths = _deaths(5) + tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=50_000 + 1_000 * index,
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(4)
    )

    # Withheld, which is what a raid ending with five of twenty down reaches.
    # The wrong reading would reach a throughput verdict instead, and a
    # withheld notice is not one.
    _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            deaths,
            _sample(seconds=300.0, deaths=1),
            resurrections=_resurrections(4, at_ms=10_000),
        )
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


def _deaths_with_one_player_dying_twice() -> tuple[Death, ...]:
    """Twelve raiders die, one of them twice: 13 events over 12 distinct players.

    The two counts are equal on every other fixture in this file, so only a
    repeat can tell which unit a sentence is quoting.
    """
    return _deaths(12) + (
        Death(
            player_name="Raider 0",
            actor_id=0,
            timestamp_ms=60_000,
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        ),
    )


def test_the_reference_death_median_is_met_with_our_death_events() -> None:
    """`ReferenceKillRow.deaths` counts death events -- measured 2026-09-18.

    Twelve of twenty died and thirteen deaths were logged. The roster share is
    a count of players, because a raid cannot lose more members than it has;
    the figure set against the reference median has to be the event count, or
    the sentence compares players to events. Both belong in the sentence.
    """
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
        _deaths_with_one_player_dying_twice(),
        _sample(seconds=300.0, deaths=3),
    )

    assert finding is not None
    assert "execution" in finding.title.lower()
    assert "12 of 20" in finding.detail, finding.detail
    assert "13" in finding.detail, finding.detail


def test_the_death_evidence_line_names_events_beside_the_reference_median() -> None:
    """The evidence line carries the same pairing as the detail sentence."""
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
        _deaths_with_one_player_dying_twice(),
        _sample(seconds=300.0, deaths=3),
    )

    assert finding is not None
    [line] = [text for text in finding.evidence if text.endswith("deaths")]
    assert "13" in line, line


WITHHELD_ID = "wipe.cause.withheld"


def _withheld_reason(finding: Finding | None) -> str:
    """The detail of a withheld verdict, failing loudly on a verdict or on silence."""
    assert finding is not None, "the verdict was dropped instead of explained"
    assert finding.id == WITHHELD_ID, f"expected a withheld notice, got {finding.id}"
    return finding.detail


def test_a_kill_is_the_only_case_that_returns_nothing() -> None:
    """A kill has no wipe to explain, so silence is the whole answer.

    Every other way this function declines to reach a verdict is something a
    reader can be told, and after this change `None` means exactly one thing.
    """
    assert (
        classify_attempt(
            _encounter(kill=True, boss_percentage=0.0, seconds=400.0),
            _deaths(14),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_an_attempt_with_no_reference_sample_names_the_missing_sample() -> None:
    """Every `--no-compare` run takes this path, and said nothing at all before.

    Design 8.3 wants the withheld case recorded rather than dropped: a reader
    who sees no verdict cannot otherwise tell a comparison that was refused
    from one that was never asked for.
    """
    reason = _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(1),
            MechanicsSample(),
        )
    )

    assert "reference" in reason.lower(), reason


def test_an_attempt_with_no_boss_health_reading_names_that() -> None:
    reason = _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=None, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
    )

    assert "boss health" in reason.lower(), reason


def test_a_raid_matching_neither_shape_names_that() -> None:
    """The judgement was made and came out indeterminate, which is a third thing.

    Distinct from both absences above: the sample and the reading were both
    there, and the attempt simply sat between the two shapes.
    """
    reason = _withheld_reason(
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(5),
            _sample(seconds=300.0, deaths=1),
        )
    )

    assert "neither" in reason.lower(), reason


def test_the_four_withheld_reasons_are_all_different() -> None:
    """A reason that does not distinguish its case is the defect being fixed.

    Four situations reached one bare `None` before, so a test asserting each
    is explained could still pass over four identical sentences.
    """
    reasons = {
        _withheld_reason(
            classify_attempt(
                _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
                _deaths(1),
                MechanicsSample(),
            )
        ),
        _withheld_reason(
            classify_attempt(
                _encounter(kill=False, boss_percentage=None, seconds=400.0),
                _deaths(1),
                _sample(seconds=300.0, deaths=1),
            )
        ),
        _withheld_reason(
            classify_attempt(
                _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
                _deaths(5),
                _sample(seconds=300.0, deaths=1),
            )
        ),
        _withheld_reason(
            classify_attempt(
                _encounter(kill=False, boss_percentage=2.0, seconds=250.0),
                _deaths(3),
                _sample(seconds=300.0, deaths=1),
            )
        ),
    }

    assert len(reasons) == 3, reasons


def test_the_alive_series_starts_with_the_whole_raid_standing() -> None:
    [first, *_] = alive_over_time(20, (), ())

    assert first.timestamp_ms == 0
    assert first.alive == 20


def test_the_alive_series_steps_down_on_each_death() -> None:
    series = alive_over_time(20, _deaths(3), ())

    assert [point.alive for point in series] == [20, 19, 18, 17]


def test_the_alive_series_steps_back_up_on_a_resurrection() -> None:
    """A rez is a step up, and the series has to show it as one."""
    series = alive_over_time(20, _deaths(2), _resurrections(1, at_ms=5_000))

    assert [point.alive for point in series] == [20, 19, 18, 19]
    assert series[-1].timestamp_ms == 5_000


def test_a_resurrection_at_the_instant_of_a_death_leaves_the_player_down() -> None:
    """The rule `_alive_at_the_end` already applies, carried into the series.

    A rez cannot land on somebody who has not died yet, so the equal case is a
    second death landing on somebody just brought back.
    """
    deaths = (
        Death(
            player_name="Raider 0", actor_id=0, timestamp_ms=5_000,
            killing_blow="Caustic Waves", killing_blow_id=11,
        ),
    )

    series = alive_over_time(20, deaths, _resurrections(1, at_ms=5_000))

    assert series[-1].alive == 19


def test_the_series_ends_where_the_verdict_says_it_does() -> None:
    """The point of this extraction: two places on one page cannot disagree.

    The verdict's first evidence line prints "N of 20 alive at the end". A
    chart computing its own step function would eventually end on a different
    number, in two places a reader sees at once.
    """
    deaths = _deaths(5) + (
        Death(
            player_name="Raider 0", actor_id=0, timestamp_ms=60_000,
            killing_blow="Caustic Waves", killing_blow_id=11,
        ),
    )
    resurrections = _resurrections(4, at_ms=10_000)

    # boss_percentage=40.0/seconds=200.0 is the pairing the dismantled-branch
    # tests above use, but only five of twenty died here -- below
    # DISMANTLED_SHARE. seconds=400.0 is what every throughput/both fixture in
    # this file pairs with a 300.0s reference: below it the attempt reads as
    # neither shape, withheld, and a withheld finding has no "alive at the
    # end" line for this test to check.
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=400.0),
        deaths,
        _sample(seconds=300.0, deaths=3),
        resurrections=resurrections,
    )
    series = alive_over_time(20, deaths, resurrections)

    assert finding is not None
    assert f"{series[-1].alive} of 20 alive at the end" in finding.evidence
