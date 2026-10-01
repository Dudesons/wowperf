# ABOUTME: Behaviour tests for the boss-level rollups: kill speed, verdicts and over-landing.
# ABOUTME: Each counts findings its pulls already carry, so the pull findings here are real ones.

from collections.abc import Sequence

from tests.domain.analysis.test_attempt_shape import _deaths, _encounter, _sample
from tests.domain.analysis.test_defensives_at_death import BLOOD
from tests.domain.comparison.test_pace_night import a_sample
from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series
from wowperf.domain.analysis.attempt_shape import classify_attempt
from wowperf.domain.analysis.night_rollups import analyse_night_rollups
from wowperf.domain.analysis.night_service import analyse_night_boss
from wowperf.domain.analysis.progression_repeats import MAX_REPEAT_ABILITIES
from wowperf.domain.analysis.severity import rank_raid_findings
from wowperf.domain.comparison.kill_time import analyse_kill_time
from wowperf.domain.comparison.pace import analyse_pace
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.findings import Confidence, Finding

KILL_SPEED = "progression.lead.kill_speed"
VERDICTS = "progression.lead.verdicts"
OVERLANDING = "progression.lead.overlanding"

_SHAPES = {
    "execution": (40.0, 200.0, 14),
    "throughput": (45.0, 400.0, 1),
    "both": (45.0, 400.0, 14),
    "neither": (2.0, 250.0, 3),
    "no boss health": (None, 400.0, 1),
}
"""Boss health, seconds and deaths that put `classify_attempt` on each shape or notice."""


def a_verdict(shape: str) -> Finding:
    """The verdict `classify_attempt` itself writes for one shape, never a hand copy."""
    boss_percentage, seconds, deaths = _SHAPES[shape]
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=boss_percentage, seconds=seconds),
        _deaths(deaths),
        _sample(seconds=300.0, deaths=1),
    )
    assert finding is not None
    return finding


def a_wipe(fight_id: int) -> Encounter:
    return a_loaded_attempt(fight_id).encounter


def a_kill(fight_id: int) -> Encounter:
    return a_loaded_attempt(fight_id, remaining=0.0, kill=True).encounter


def the_kill_readings(kill: Encounter) -> tuple[Finding, Finding]:
    """The kill's own `compare.kill.time` and `compare.pace.boss`, from their analysers."""
    [kill_time] = analyse_kill_time(kill, _sample(seconds=300.0, deaths=1))
    [pace] = analyse_pace(kill, a_sample(80))
    return kill_time, pace


def over_landing(rank: int, ability_id: int, name: str) -> Finding:
    """A `mechanics.ability.*` finding in the shape `compare_mechanics` writes it."""
    return Finding(
        id=f"mechanics.ability.{rank}",
        title=(
            f"This raid took {name} 3.0 times a minute where the references took a "
            "median of 1.0 a minute"
        ),
        detail="3.0 landings a minute against a reference median of 1.0.",
        confidence=Confidence.DERIVED,
        ability_id=ability_id,
        ability_name=name,
    )


def the_rollup(found: Sequence[Finding], finding_id: str) -> Finding:
    [one] = [finding for finding in found if finding.id == finding_id]
    return one


def test_the_verdict_rollup_counts_each_kind_and_names_withheld_ones() -> None:
    attempts = [a_wipe(20), a_wipe(21), a_wipe(22), a_wipe(24)]
    pull_findings = {
        20: [a_verdict("execution")],
        21: [a_verdict("execution")],
        22: [a_verdict("execution")],
        24: [a_verdict("neither")],
    }

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "3 of 4 wipes ended on execution"
    assert rollup.quantifier == "most"
    assert rollup.confidence is Confidence.INFERRED
    assert rollup.evidence == (
        "execution: 3 of 4 wipes (Fights 20–22)",
        "withheld, neither shape fit this attempt: 1 of 4 wipes (Fight 24)",
    )


def test_the_both_verdict_is_named_in_full_in_the_title_and_bare_in_the_evidence() -> None:
    attempts = [a_wipe(3), a_wipe(4), a_wipe(6)]
    pull_findings = {
        3: [a_verdict("both")],
        4: [a_verdict("throughput")],
        6: [a_verdict("both")],
    }

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "2 of 3 wipes ended on both execution and throughput"
    assert rollup.evidence == (
        "both: 2 of 3 wipes (Fights 3 and 6)",
        "throughput: 1 of 3 wipes (Fight 4)",
    )


def test_a_boss_whose_every_verdict_was_withheld_says_so_as_measured() -> None:
    attempts = [a_wipe(5), a_wipe(6)]
    pull_findings = {5: [a_verdict("neither")], 6: [a_verdict("no boss health")]}

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "No wipe's verdict could be read, of 2 wipes"
    assert rollup.confidence is Confidence.MEASURED
    assert rollup.quantifier == "none"
    assert rollup.evidence == (
        "withheld, neither shape fit this attempt: 1 of 2 wipes (Fight 5)",
        "withheld, the report carried no boss health: 1 of 2 wipes (Fight 6)",
    )


def test_a_boss_with_one_wipe_counts_it_in_the_singular() -> None:
    """A boss killed on its second pull has one wipe, and "1 of 1 wipes" misreads it."""
    kill = a_kill(9)
    attempts = [a_wipe(8), kill]
    pull_findings = {8: [a_verdict("execution")], 9: list(the_kill_readings(kill))}

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "1 of 1 wipe ended on execution"
    assert rollup.evidence == ("execution: 1 of 1 wipe (Fight 8)",)


def test_a_lone_wipe_whose_verdict_was_withheld_is_counted_in_the_singular() -> None:
    rollup = the_rollup(
        analyse_night_rollups([a_wipe(8)], {8: [a_verdict("no boss health")]}, frozenset()),
        VERDICTS,
    )

    assert rollup.title == "No wipe's verdict could be read, of 1 wipe"
    assert rollup.evidence == (
        "withheld, the report carried no boss health: 1 of 1 wipe (Fight 8)",
    )


def test_kills_are_not_counted_among_the_wipes() -> None:
    """A kill is not a wipe, whatever its findings hold.

    `classify_attempt` writes nothing on a kill, so the kill here carries a
    verdict-shaped finding on purpose: were it counted, the denominator would
    read three, and the rollup would claim a wipe the boss never had.
    """
    kill = a_kill(9)
    attempts = [a_wipe(7), a_wipe(8), kill]
    pull_findings = {
        7: [a_verdict("execution")],
        8: [a_verdict("execution")],
        9: [*the_kill_readings(kill), a_verdict("execution")],
    }

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "2 of 2 wipes ended on execution"
    assert rollup.evidence == ("execution: 2 of 2 wipes (Fights 7–8)",)


def test_a_wipe_whose_pull_did_not_load_is_counted_as_withheld() -> None:
    """Spec section 5.2: a withheld verdict is counted and named, not dropped.

    Fight 23 is one of the boss's attempts, and its pull never loaded, so no
    findings were ever written for it. Leaving it out would put "of 3 wipes"
    under a headline counting four.
    """
    attempts = [a_wipe(20), a_wipe(21), a_wipe(22), a_wipe(23)]
    pull_findings = {
        20: [a_verdict("execution")],
        21: [a_verdict("execution")],
        22: [a_verdict("execution")],
    }

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "3 of 4 wipes ended on execution"
    assert rollup.confidence is Confidence.INFERRED
    assert rollup.evidence == (
        "execution: 3 of 4 wipes (Fights 20–22)",
        "withheld, its pull did not load: "
        "1 of 4 wipes (Fight 23)",
    )


def test_a_boss_whose_every_wipe_failed_to_load_says_so_as_measured() -> None:
    attempts = [a_wipe(5), a_wipe(6), a_wipe(7)]

    rollup = the_rollup(analyse_night_rollups(attempts, {}, frozenset()), VERDICTS)

    assert rollup.title == "No wipe's verdict could be read, of 3 wipes"
    assert rollup.confidence is Confidence.MEASURED
    assert rollup.quantifier == "none"
    assert rollup.evidence == (
        "withheld, its pull did not load: "
        "3 of 3 wipes (Fights 5–7)",
    )


def test_a_drawn_wipe_carrying_no_verdict_is_not_counted() -> None:
    """Drawn, so not a pull that failed to load; with no verdict, nothing to count.

    `wowperf night` never hands such a wipe -- every drawn wipe carries a
    verdict or its withheld notice -- so this pins what the rollup does for a
    caller that does, rather than a state a live night reaches.
    """
    attempts = [a_wipe(7), a_wipe(8)]
    pull_findings: dict[int, list[Finding]] = {7: [a_verdict("execution")], 8: []}

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), VERDICTS)

    assert rollup.title == "1 of 1 wipe ended on execution"


def test_a_kill_whose_pull_did_not_load_is_neither_a_wipe_nor_a_kill_speed() -> None:
    """An undrawn kill has nothing to read, so the drawn kill after it is the one read.

    A report holding two kills of one boss is rare, but the rule is the
    rollup's: kill speed reads a drawn kill's findings, never a kill that
    carries none.
    """
    kill = a_kill(10)
    attempts = [a_wipe(8), a_kill(9), kill]
    pull_findings = {8: [a_verdict("execution")], 10: list(the_kill_readings(kill))}

    found = analyse_night_rollups(attempts, pull_findings, frozenset())

    assert the_rollup(found, VERDICTS).title == "1 of 1 wipe ended on execution"
    assert the_rollup(found, KILL_SPEED).evidence[0] == "On the kill, fight 10"


def test_a_boss_killed_on_its_first_pull_has_no_verdict_rollup() -> None:
    kill = a_kill(9)
    found = analyse_night_rollups([kill], {9: list(the_kill_readings(kill))}, frozenset())
    assert VERDICTS not in [finding.id for finding in found]


def test_an_ability_over_landing_in_two_compared_pulls_is_named_once() -> None:
    attempts = [a_wipe(3), a_wipe(4), a_wipe(5)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash")],
        4: [],
        5: [over_landing(1, 9001, "Brinecoil Lash")],
    }

    rollup = the_rollup(
        analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5})), OVERLANDING
    )

    assert rollup.title == "Brinecoil Lash over-landed in 2 of 3 compared attempts"
    assert rollup.quantifier == "most"
    assert rollup.confidence is Confidence.DERIVED
    assert rollup.ability_id == 9001
    assert rollup.ability_name == "Brinecoil Lash"
    assert rollup.evidence == (
        "Brinecoil Lash over-landed in 2 of 3 compared attempts (Fights 3 and 5)",
    )


def test_an_ability_reported_in_one_pull_does_not_repeat() -> None:
    """Once per pull, never per finding: one pull naming it twice is still one pull."""
    attempts = [a_wipe(3), a_wipe(4)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash"), over_landing(1, 9001, "Brinecoil Lash")],
        4: [over_landing(0, 9002, "Marrow Squall")],
    }

    found = analyse_night_rollups(attempts, pull_findings, frozenset({3, 4}))

    assert OVERLANDING not in [finding.id for finding in found]


def test_a_pull_not_compared_is_not_in_the_denominator() -> None:
    """Nor among the pulls counted: fight 4 names the ability, and its sample drew no member."""
    attempts = [a_wipe(3), a_wipe(4), a_wipe(5)]
    pull_findings = {
        3: [over_landing(0, 9001, "Brinecoil Lash")],
        4: [over_landing(0, 9001, "Brinecoil Lash")],
        5: [over_landing(0, 9001, "Brinecoil Lash")],
    }

    rollup = the_rollup(
        analyse_night_rollups(attempts, pull_findings, frozenset({3, 5})), OVERLANDING
    )

    assert rollup.title == "Brinecoil Lash over-landed in 2 of 2 compared attempts"
    assert rollup.quantifier == "every"


def test_several_abilities_are_all_counted_and_the_most_repeated_listed_first() -> None:
    """The title counts every ability that repeated; only the evidence is capped, and says so.

    Seven abilities repeat, two more than `MAX_REPEAT_ABILITIES`: a title that
    counted the listed lines would claim five, and miss the two the cap left out.
    """
    names = [f"Ability {letter}" for letter in "ABCDEFG"]
    attempts = [a_wipe(fight) for fight in (3, 4, 5)]
    # Ability G lands in all three pulls; A to F in two each.
    pull_findings: dict[int, list[Finding]] = {3: [], 4: [], 5: []}
    for index, name in enumerate(names):
        for fight in ((3, 4, 5) if name == "Ability G" else (3, 4)):
            pull_findings[fight].append(over_landing(index, 100 + index, name))

    rollup = the_rollup(
        analyse_night_rollups(attempts, pull_findings, frozenset({3, 4, 5})), OVERLANDING
    )

    assert MAX_REPEAT_ABILITIES == 5, "the evidence below lists five lines"
    assert rollup.title == "7 abilities over-landed in more than one compared attempt"
    assert rollup.ability_id is None
    assert rollup.ability_name == ""
    assert rollup.quantifier == "every"
    assert rollup.evidence == (
        "Ability G over-landed in 3 of 3 compared attempts (Fights 3–5)",
        "Ability A over-landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability B over-landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability C over-landed in 2 of 3 compared attempts (Fights 3–4)",
        "Ability D over-landed in 2 of 3 compared attempts (Fights 3–4)",
        "The evidence lists the 5 abilities most reported",
    )


def test_abilities_the_cap_does_not_cut_carry_no_line_about_the_cap() -> None:
    """Exactly `MAX_REPEAT_ABILITIES` repeating abilities are all listed, so nothing is cut."""
    names = [f"Ability {letter}" for letter in "ABCDE"]
    attempts = [a_wipe(fight) for fight in (3, 4)]
    pull_findings: dict[int, list[Finding]] = {3: [], 4: []}
    for index, name in enumerate(names):
        for fight in (3, 4):
            pull_findings[fight].append(over_landing(index, 100 + index, name))

    rollup = the_rollup(
        analyse_night_rollups(attempts, pull_findings, frozenset({3, 4})), OVERLANDING
    )

    assert rollup.title == "5 abilities over-landed in more than one compared attempt"
    assert len(rollup.evidence) == MAX_REPEAT_ABILITIES
    assert not any("most reported" in line for line in rollup.evidence)


def test_kill_speed_reads_the_kill_pulls_time_and_pace() -> None:
    kill = a_kill(9)
    kill_time, pace = the_kill_readings(kill)
    attempts = [a_wipe(7), a_wipe(8), kill]
    pull_findings = {7: [a_verdict("execution")], 8: [], 9: [kill_time, pace]}

    rollup = the_rollup(analyse_night_rollups(attempts, pull_findings, frozenset()), KILL_SPEED)

    assert rollup.title == kill_time.title
    assert rollup.evidence == (
        "On the kill, fight 9",
        *kill_time.evidence,
        f"Damage pace: {pace.title}",
    )
    assert rollup.confidence is Confidence.DERIVED
    assert rollup.quantifier == ""


def test_kill_speed_without_a_pace_reading_takes_the_kill_times_confidence() -> None:
    kill = a_kill(9)
    kill_time, _ = the_kill_readings(kill)

    rollup = the_rollup(analyse_night_rollups([kill], {9: [kill_time]}, frozenset()), KILL_SPEED)

    assert rollup.confidence is Confidence.MEASURED
    assert rollup.evidence == ("On the kill, fight 9", *kill_time.evidence)


def test_kill_speed_with_only_a_pace_reading_takes_its_title() -> None:
    """No kill time is a kill whose sample drew no member; the pace may still have read."""
    kill = a_kill(9)
    _, pace = the_kill_readings(kill)

    rollup = the_rollup(analyse_night_rollups([kill], {9: [pace]}, frozenset()), KILL_SPEED)

    assert rollup.title == pace.title
    assert rollup.evidence == ("On the kill, fight 9", *pace.evidence)
    assert pace.evidence, "a pace reading with no evidence pins nothing"
    assert rollup.confidence is Confidence.DERIVED


def test_kill_speed_is_absent_when_the_kill_carries_neither_reading() -> None:
    kill = a_kill(9)
    found = analyse_night_rollups([a_wipe(8), kill], {8: [], 9: []}, frozenset())
    assert KILL_SPEED not in [finding.id for finding in found]


def test_kill_speed_is_absent_on_a_boss_that_never_died() -> None:
    """A wipe's pace reading is not a kill's speed, though it carries the same id."""
    wipe = a_wipe(8)
    [pace, *_] = analyse_pace(wipe, a_sample(80))
    found = analyse_night_rollups([wipe], {8: [pace]}, frozenset())
    assert KILL_SPEED not in [finding.id for finding in found]


def test_the_rollups_come_in_their_fixed_order() -> None:
    """Fixed by the rollup itself, and kept by the ranking the night writes them through.

    `rank_raid_findings` sorts the `progression` family on severity and seconds
    alone, and none of the three costs a second, so only a stable sort keeps
    the order `analyse_night_rollups` set.
    """
    kill = a_kill(9)
    attempts = [a_wipe(7), a_wipe(8), kill]
    pull_findings = {
        7: [a_verdict("execution"), over_landing(0, 9001, "Brinecoil Lash")],
        8: [a_verdict("execution"), over_landing(0, 9001, "Brinecoil Lash")],
        9: [*the_kill_readings(kill)],
    }
    compared = frozenset({7, 8, 9})
    order = [KILL_SPEED, VERDICTS, OVERLANDING]

    found = analyse_night_rollups(attempts, pull_findings, compared)
    assert [finding.id for finding in found] == order

    ranked = rank_raid_findings(
        analyse_night_boss(
            a_loaded_series(*(LoadedEncounter(encounter=one) for one in attempts)),
            BLOOD,
            death_cards=False,
            pull_findings=pull_findings,
            mechanics_compared=compared,
        )
    )
    assert [finding.id for finding in ranked if finding.id.startswith("progression.lead.")] == (
        order
    )
