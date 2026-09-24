# ABOUTME: The night page's builder: every pull grouped under its boss, at the tier it was fetched.
# ABOUTME: Every tier is asserted by its exact string: a typo would pass pydantic in silence.

from collections.abc import Mapping, Sequence

from tests.domain.progression_fixtures import a_loaded_attempt
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.night import FailedPull, LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.frame import NO_COMPARISON_RAN
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import all_night_ledger_rows
from wowperf.domain.report.raid_model import all_raid_ledger_rows
from wowperf.domain.season import Consumables, Defensives, Roles

REPORT_CODE = "TESTCODE00000000"
FETCHED = "2026-09-24 09:00"
NO_FINDINGS: Mapping[int, Sequence[Finding]] = {}
NO_DEFENSIVES = Defensives()
NO_CONSUMABLES = Consumables()
NO_ROLES = Roles()

ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=690),
)

OWNER = "stonewake"
"""The report owner, spelled the way Warcraft Logs spells it: lowercased.

Index 1 of the roster on purpose. The fallback is index 0, so an owner sitting
there could not be told apart from a builder that ignores the owner entirely.
"""

BOSS_NAMES = ("Ula'tek", "Nek'zali")
HIT_ABILITY_ID = 445_566
FAILED_REASON = "the damage-taken stream would not load"


def a_pull(
    fight_id: int, boss_name: str, encounter_id: int, owner_name: str | None
) -> LoadedEncounter:
    """One deepened pull: one death, and one hit inside its run-up.

    Both are here so that a death-card assertion is able to fail. A pull with
    no death produces no card at any tier, and a card whose run-up is empty
    carries an empty timeline whether it was trimmed or not -- so a fixture
    missing either would pass against a builder that mapped every tier onto the
    same pair of keywords.
    """
    return a_loaded_attempt(
        fight_id,
        players=ROSTER,
        deaths_after_ms=(10_000,),
        damage_after_ms=((9_000, HIT_ABILITY_ID, None),),
        boss_name=boss_name,
        encounter_id=encounter_id,
        owner_name=owner_name,
    )


def a_night(
    *,
    bosses: tuple[int, ...],
    owner_name: str | None = OWNER,
    failed: tuple[int, ...] = (),
) -> LoadedNight:
    """A loaded night with one boss per entry in `bosses`, holding that many pulls.

    Fight ids are allocated ten apart per boss -- 10, 11 for the first boss and
    20, 21, 22 for the second -- so no two bosses share one and a pull grouped
    under the wrong boss is visible by its id alone.

    A fight id in `failed` stays among its boss's `attempts` and is left out of
    its `loaded`, with a `FailedPull` naming it: that is the shape
    `load_night_attempts` produces for a pull whose streams would not come
    back.
    """
    loaded: list[LoadedProgression] = []
    failures: list[FailedPull] = []
    for index, count in enumerate(bosses):
        boss_name = BOSS_NAMES[index]
        encounter_id = 3490 + index
        pulls = tuple(
            a_pull((index + 1) * 10 + which, boss_name, encounter_id, owner_name)
            for which in range(count)
        )
        failures.extend(
            FailedPull(fight_id=one.encounter.fight_id, reason=FAILED_REASON)
            for one in pulls
            if one.encounter.fight_id in failed
        )
        loaded.append(
            LoadedProgression(
                progression=Progression(
                    report_code=REPORT_CODE,
                    encounter_id=encounter_id,
                    boss_name=boss_name,
                    difficulty=5,
                    size=20,
                    attempts=tuple(one.encounter for one in pulls),
                ),
                loaded=tuple(
                    one for one in pulls if one.encounter.fight_id not in failed
                ),
            )
        )
    return LoadedNight(
        night=Night(
            report_code=REPORT_CODE,
            bosses=tuple(one.progression for one in loaded),
        ),
        loaded=tuple(loaded),
        failed_pulls=tuple(failures),
    )


def a_finding(finding_id: str) -> Finding:
    return Finding(
        id=finding_id, title="One pull's own finding", detail="d", confidence=Confidence.MEASURED
    )


def test_every_pull_is_built_and_grouped_under_its_own_boss() -> None:
    """Two bosses with DIFFERENT pull counts: two and three, not two and two.

    A builder that reported one boss's count for the whole night would pass a
    fixture where both bosses held the same number of pulls. This one cannot be
    passed that way.
    """
    report = build_night_report(
        a_night(bosses=(2, 3)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    assert tuple(len(boss.pulls) for boss in report.bosses) == (2, 3)
    assert report.total_pulls == 5
    assert [boss.boss_name for boss in report.bosses] == list(BOSS_NAMES)
    assert [pull.report.provenance.fight_id for pull in report.bosses[0].pulls] == [10, 11]
    assert [pull.report.provenance.fight_id for pull in report.bosses[1].pulls] == [20, 21, 22]
    assert report.header.report_code == REPORT_CODE
    assert report.provenance.fetched_at == FETCHED
    assert report.provenance.withheld == ()


def test_a_pull_named_by_deep_is_the_only_one_built_deep() -> None:
    """Every pull's tier is asserted, not just the named one.

    Asserting only that the named pull is deep passes against a builder that
    deepens all of them -- the whole night at the dearest tier, which is the
    most expensive regression this feature has. The timeline assertions below
    pin the same decision at the other end: the tier label and the keywords
    actually handed to `build_raid_report` have to agree.
    """
    night = a_night(bosses=(3,))
    named = night.night.bosses[0].attempts[1].fight_id

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset({named}),
        death_cards=True,
    )

    pulls = report.bosses[0].pulls
    assert tuple(pull.tier for pull in pulls) == ("trimmed", "deep", "trimmed")
    assert pulls[1].report.deaths[0].timeline != ()
    assert pulls[0].report.deaths[0].timeline == ()
    assert pulls[2].report.deaths[0].timeline == ()


def test_no_death_cards_leaves_every_pull_without_one() -> None:
    report = build_night_report(
        a_night(bosses=(2,)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=False,
    )

    assert all(pull.report.deaths == () for pull in report.bosses[0].pulls)
    assert all(pull.tier == "none" for pull in report.bosses[0].pulls)


def test_the_same_night_does_carry_cards_when_they_are_asked_for() -> None:
    """The other half of the test above: the fixture is able to produce a card.

    Without this, `deaths == ()` would pass against a fixture whose pulls hold
    no death at all, and the `--no-deaths` tier would be untested.
    """
    report = build_night_report(
        a_night(bosses=(2,)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    assert all(len(pull.report.deaths) == 1 for pull in report.bosses[0].pulls)


def test_the_page_carries_the_absent_axis_disclosure_exactly_once() -> None:
    report = build_night_report(
        a_night(bosses=(2, 3)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    ids = [row.finding_id for row in all_night_ledger_rows(report)]
    assert ids.count(NOT_DRAWN_ID) == 1


def test_a_failed_pull_is_named_in_provenance_and_left_out_of_the_count() -> None:
    """Both halves in one test: the count and the note.

    A builder that hid a failure by counting the attempts that existed rather
    than the pulls that loaded would pass a test that checked only the note,
    and one that dropped the pull without saying so would pass a test that
    checked only the count.
    """
    report = build_night_report(
        a_night(bosses=(2,), failed=(11,)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    assert report.total_pulls == 1
    assert [pull.report.provenance.fight_id for pull in report.bosses[0].pulls] == [10]
    assert report.failed_pulls == (FailedPull(fight_id=11, reason=FAILED_REASON),)
    named = [line for line in report.provenance.withheld if "11" in line]
    assert len(named) == 1
    assert FAILED_REASON in named[0]


def test_a_boss_whose_every_pull_failed_is_still_on_the_page() -> None:
    """Dropping the boss would lose the fact that the report pulled it at all.

    The same ruling `LoadedNight` makes one layer down and `BossSection`
    makes one layer up, held here where the two meet.
    """
    report = build_night_report(
        a_night(bosses=(2,), failed=(10, 11)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    assert [boss.boss_name for boss in report.bosses] == [BOSS_NAMES[0]]
    assert report.bosses[0].pulls == ()
    assert report.total_pulls == 0
    assert len(report.provenance.withheld) == 2


def test_the_report_owner_opens_every_pulls_players_tab() -> None:
    """Whose card opens the Players tab is visible on every pull, so it is pinned.

    The owner's name arrives lowercased from Warcraft Logs while the roster
    carries the character's own spelling, so an exact match would fall back on
    every real report.
    """
    report = build_night_report(
        a_night(bosses=(2, 3)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    opened = [
        pull.report.players[0].name for boss in report.bosses for pull in boss.pulls
    ]
    assert opened == ["Stonewake"] * 5


def test_a_pull_whose_owner_is_not_on_the_roster_opens_on_the_first_raider() -> None:
    for owner_name in (None, "Bríala"):
        report = build_night_report(
            a_night(bosses=(2,), owner_name=owner_name),
            NO_FINDINGS,
            FETCHED,
            NO_DEFENSIVES,
            NO_CONSUMABLES,
            NO_ROLES,
            deep_fights=frozenset(),
            death_cards=True,
        )

        opened = [pull.report.players[0].name for pull in report.bosses[0].pulls]
        assert opened == ["Emberkin", "Emberkin"], owner_name


def test_every_pull_states_that_no_comparison_was_drawn_for_it() -> None:
    """`compared_slugs=None` and not an empty set, which would be a false claim.

    An empty frozenset means a comparison ran and matched nobody, and the raid
    builder says nothing at all in that case -- so this line's absence is what
    a wrong value here looks like.
    """
    report = build_night_report(
        a_night(bosses=(2,)),
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    for pull in report.bosses[0].pulls:
        assert any(
            NO_COMPARISON_RAN in line for line in pull.report.provenance.withheld
        )


def test_each_pulls_findings_reach_that_pull_alone() -> None:
    """Findings are keyed by fight id, and a pull draws only its own.

    A builder that handed every pull the whole mapping would draw one pull's
    judgements on another's tab, under the same report code, where nothing on
    the page would say they belonged to a different attempt.
    """
    findings: Mapping[int, Sequence[Finding]] = {
        10: (a_finding("night.pull.ten"),),
        11: (a_finding("night.pull.eleven"),),
    }

    report = build_night_report(
        a_night(bosses=(2,)),
        findings,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
    )

    drawn = [
        [
            row.finding_id
            for row in all_raid_ledger_rows(pull.report)
            if row.finding_id.startswith("night.pull.")
        ]
        for pull in report.bosses[0].pulls
    ]
    assert drawn == [["night.pull.ten"], ["night.pull.eleven"]]
