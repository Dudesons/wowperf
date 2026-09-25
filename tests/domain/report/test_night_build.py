# ABOUTME: The night page's builder: every pull grouped under its boss, at the tier it was fetched.
# ABOUTME: Every tier is asserted by its exact string: a typo would pass pydantic in silence.

from collections.abc import Mapping, Sequence

from tests.domain.progression_fixtures import a_loaded_attempt
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.night import FailedPull, LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.frame import NO_COMPARISON_RAN
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import NightReport, all_night_ledger_rows
from wowperf.domain.report.progression_build import build_progression_report
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
                # Newest first, the reverse of pull order. The streams come back
                # in whatever order they come back in, and the page's order has
                # to be the report's: a fixture already sorted the way the page
                # prints cannot tell `attempts_with_events` apart from a plain
                # walk of `loaded`, so the fight-id assertions below would pass
                # against a builder that silently reordered the night.
                loaded=tuple(
                    reversed(
                        [one for one in pulls if one.encounter.fight_id not in failed]
                    )
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


def tier_line(report: NightReport) -> str:
    """The one Provenance line stating what depth the run asked for.

    A reader who did not type the command cannot otherwise tell a Deaths tab
    that was suppressed from one that failed, and these pages get shared.
    """
    assert len(report.provenance.methods) == 1
    return report.provenance.methods[0]


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
        findings_by_boss=NO_FINDINGS,
    )

    assert tuple(len(boss.pulls) for boss in report.bosses) == (2, 3)
    assert report.total_pulls == 5
    assert [boss.boss_name for boss in report.bosses] == list(BOSS_NAMES)
    assert [pull.report.provenance.fight_id for pull in report.bosses[0].pulls] == [10, 11]
    assert [pull.report.provenance.fight_id for pull in report.bosses[1].pulls] == [20, 21, 22]
    assert report.header.report_code == REPORT_CODE
    assert report.provenance.fetched_at == FETCHED
    assert report.provenance.withheld == ()
    assert "trimmed" in tier_line(report)
    assert "except" not in tier_line(report)


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
        findings_by_boss=NO_FINDINGS,
    )

    pulls = report.bosses[0].pulls
    assert tuple(pull.tier for pull in pulls) == ("trimmed", "deep", "trimmed")
    # The claim, not the mention. A line whose opening clause says every card
    # on the page is trimmed has told a reader something false of this very
    # pull -- the one whose timeline the assertion above just found -- and
    # naming the exception in a later sentence does not retract it. So the
    # qualification has to land before the opening sentence ends.
    lead = tier_line(report).split(". ")[0]
    assert "except" in lead
    assert str(named) in lead
    assert pulls[1].report.deaths[0].timeline != ()
    assert pulls[0].report.deaths[0].timeline == ()
    assert pulls[2].report.deaths[0].timeline == ()


def test_two_named_pulls_are_both_named_where_the_claim_is_qualified() -> None:
    """The plural branch of the same sentence, and both ids inside the exception.

    One named fight exercises neither the pluralised noun nor the join, and a
    line that qualified its claim for one pull while silently swallowing the
    other would be false of the pull it dropped.
    """
    night = a_night(bosses=(3,))
    named = tuple(attempt.fight_id for attempt in night.night.bosses[0].attempts[:2])

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(named),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
    )

    lead = tier_line(report).split(". ")[0]
    assert "fights" in lead
    assert all(str(one) in lead for one in named)


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
        findings_by_boss=NO_FINDINGS,
    )

    assert all(pull.report.deaths == () for pull in report.bosses[0].pulls)
    assert all(pull.tier == "none" for pull in report.bosses[0].pulls)
    assert "No death card was drawn" in tier_line(report)


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
        findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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
            findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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
        findings_by_boss=NO_FINDINGS,
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


def boss_findings(night: LoadedNight) -> dict[int, tuple[Finding, ...]]:
    """What the command computes per boss: the progression analyser, run for real."""
    return {
        boss.progression.encounter_id: tuple(analyse_progression(boss))
        for boss in night.loaded
    }


def a_report(night: LoadedNight, *, death_cards: bool = True) -> NightReport:
    return build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=death_cards,
        findings_by_boss=boss_findings(night),
    )


def test_a_boss_pulled_once_has_no_summary_and_a_boss_pulled_twice_has_one() -> None:
    """One and two, side by side, so the threshold is pinned from both sides at once."""
    report = a_report(a_night(bosses=(1, 2)))

    assert report.bosses[0].summary is None
    assert report.bosses[1].summary is not None


def test_a_boss_with_no_drawn_pull_has_no_summary() -> None:
    report = a_report(a_night(bosses=(2,), failed=(10, 11)))

    assert report.bosses[0].pulls == ()
    assert report.bosses[0].summary is None


def test_the_threshold_counts_drawn_pulls_not_attempts() -> None:
    """Three attempts, two failed: one drawn pull, so no summary -- though three were pulled."""
    report = a_report(a_night(bosses=(3,), failed=(11, 12)))

    assert len(report.bosses[0].pulls) == 1
    assert report.bosses[0].summary is None


def test_a_summary_is_the_progression_page_for_that_boss_and_nothing_else() -> None:
    """Equal to a direct call on the same boss: the reuse is whole, not an imitation."""
    night = a_night(bosses=(1, 3))
    findings = boss_findings(night)
    report = a_report(night)

    boss = night.loaded[1]
    assert report.bosses[1].summary == build_progression_report(
        boss, findings[boss.progression.encounter_id], FETCHED
    )


def test_a_summary_with_a_failed_pull_says_how_many_were_counted_and_how_many_deepened() -> None:
    report = a_report(a_night(bosses=(3,), failed=(12,)))

    summary = report.bosses[0].summary
    assert summary is not None
    assert summary.provenance.attempts_counted == 3
    assert summary.provenance.attempts_deepened == 2


def test_a_summary_does_not_depend_on_the_death_card_tier() -> None:
    """Progression reads deaths and damage taken, which every tier fetches."""
    night = a_night(bosses=(3,))

    assert a_report(night, death_cards=True).bosses[0].summary == a_report(
        night, death_cards=False
    ).bosses[0].summary
