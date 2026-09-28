# ABOUTME: The night page's builder: every pull grouped under its boss, at the tier it was fetched.
# ABOUTME: Every tier is asserted by its exact string: a typo would pass pydantic in silence.

from collections.abc import Mapping, Sequence

from tests.domain.comparison.test_pace_night import a_sample
from tests.domain.progression_fixtures import a_loaded_attempt
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.comparison.pace import NO_SINGLE_BOSS, PACE_ID, PaceSample, analyse_pace
from wowperf.domain.comparison.pace_night import NIGHT_PACE_ID, analyse_night_pace
from wowperf.domain.comparison.parse_axis import WITHHELD_DETAIL
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.night import FailedPull, LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.frame import NO_COMPARISON_RAN
from wowperf.domain.report.model import ReferenceRecord, SectionState
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import NightReport, all_night_ledger_rows
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows
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


def test_a_night_handed_a_pace_sample_says_it_draws_pace_and_no_parses() -> None:
    """Handed any sample, the night asked a leaderboard for reference kills --
    even when every wipe then withheld -- so the disclosure may no longer say
    that no comparison against other kills is drawn. A night handed none, a
    `--no-compare` or all-kills night, keeps the sentence it always had.
    """
    night = a_night(bosses=(1,))
    fight_id = night.night.bosses[0].attempts[0].fight_id

    def disclosure(pace_by_fight: Mapping[int, PaceSample] | None) -> str:
        report = build_night_report(
            night,
            NO_FINDINGS,
            FETCHED,
            NO_DEFENSIVES,
            NO_CONSUMABLES,
            NO_ROLES,
            deep_fights=frozenset(),
            death_cards=True,
            findings_by_boss=NO_FINDINGS,
            pace_by_fight=pace_by_fight,
        )
        (row,) = (one for one in report.observations if one.finding_id == NOT_DRAWN_ID)
        return row.title

    withheld = disclosure({fight_id: PaceSample(unavailable=NO_SINGLE_BOSS)})
    assert withheld == "No parse comparison is drawn on this page"
    assert disclosure(None) == "No comparison against other kills is drawn on this page"
    assert disclosure({}) == "No comparison against other kills is drawn on this page"


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


PACE_REFERENCE_CODE = "REFCODE0000000A"
"""A reference kill's report code, fabricated for the fixture below.

Never the code of a real, fetched reference kill -- constraints.md forbids
printing one of those. This one names nothing that was ever fetched.
"""


def a_reference_record(index: int, *, from_cache: bool = False) -> ReferenceRecord:
    """One fabricated reference kill, distinguished from its siblings by `index`.

    `url` is what dedup keys on, so two records built with the same `index`
    but different `from_cache` share a `url` -- the shape two pulls handed the
    same reference kill actually have, one reading it fresh and the next
    reading the cached copy back.
    """
    return ReferenceRecord(
        report_code=PACE_REFERENCE_CODE,
        fight_id=index,
        keystone_level=0,
        url=f"https://www.warcraftlogs.com/reports/{PACE_REFERENCE_CODE}#fight={index}",
        axis="pace",
        from_cache=from_cache,
    )


def test_a_pull_given_a_pace_sample_draws_its_chart_row_and_pointer() -> None:
    """The three things one sample buys, built through `analyse_pace` and never hand-typed.

    A hand-typed finding would agree with a builder that stopped reading
    `pace` at all for the chart, since nothing else here would notice it was
    gone -- `analyse_pace` is what ties the chart to the same reading its
    finding states.
    """
    night = a_night(bosses=(1,))
    encounter = night.night.bosses[0].attempts[0]
    fight_id = encounter.fight_id
    # The pull's own duration, read off its own encounter -- a hardcoded
    # figure would happen to match `a_loaded_attempt`'s default and would
    # stop matching the moment the fixture's own duration changed.
    sample = a_sample(80, int(encounter.duration_seconds))
    findings = analyse_pace(encounter, sample)

    report = build_night_report(
        night,
        {fight_id: findings},
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
        pace_by_fight={fight_id: sample},
    )

    pull = report.bosses[0].pulls[0].report
    assert pull.pace_chart is not None
    assert any(row.finding_id == PACE_ID for row in pull.damage_rows)
    assert pull.pace_warning is not None


def test_a_pull_with_no_sample_draws_none_of_the_three() -> None:
    """A pull nobody asked about draws no chart, no row and no warning.

    The lone pull below has neither a finding nor a `pace_by_fight` entry --
    the simplest shape, and one a builder that stopped threading `pace`
    altogether would still pass, since "nothing" is what both a working and
    a broken builder draw for it. The second pull below closes that gap:
    both fights carry their own real `compare.pace.boss` finding, so a
    chart *can* render for either, and `pace_by_fight` names only the first.
    A builder that read any available sample instead of that fight's own --
    the first entry `pace_by_fight` happens to hold, say -- would draw the
    second pull's chart from the first pull's sample, and this is where
    that would show.
    """
    night = a_night(bosses=(1,))

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
    )

    pull = report.bosses[0].pulls[0].report
    assert pull.pace_chart is None
    assert not any(row.finding_id == PACE_ID for row in pull.damage_rows)
    assert pull.pace_warning is None

    two_pulls = a_night(bosses=(2,))
    fight_a, fight_b = (attempt.fight_id for attempt in two_pulls.night.bosses[0].attempts)
    encounter_a, encounter_b = (
        next(one for one in two_pulls.night.bosses[0].attempts if one.fight_id == fight)
        for fight in (fight_a, fight_b)
    )
    sample_a = a_sample(80, int(encounter_a.duration_seconds))
    findings_by_fight = {
        fight_a: analyse_pace(encounter_a, sample_a),
        # Its own reading, from its own sample -- so this pull carries a real
        # finding of its own and a leaked chart would not be the only finding
        # on the page to explain.
        fight_b: analyse_pace(encounter_b, sample_a),
    }

    report_two = build_night_report(
        two_pulls,
        findings_by_fight,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
        pace_by_fight={fight_a: sample_a},
    )

    pull_b = next(
        one.report
        for one in report_two.bosses[0].pulls
        if one.report.provenance.fight_id == fight_b
    )
    assert pull_b.pace_chart is None
    assert pull_b.pace_warning is None


def test_a_pulls_own_provenance_carries_the_records_handed_for_it() -> None:
    night = a_night(bosses=(1,))
    fight_id = night.night.bosses[0].attempts[0].fight_id
    records = (a_reference_record(1), a_reference_record(2))

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
        records_by_fight={fight_id: records},
    )

    assert report.bosses[0].pulls[0].report.provenance.references == records


def test_two_pulls_sharing_reference_records_are_named_once_each() -> None:
    """Three records handed to two pulls give three, not six -- the first copies.

    The second pull's records are the same three kills, `from_cache=True`: the
    shape `load_pace_sample` produces when the first pull already paid for
    them. Deduped by `url`, so the night's own list carries the first pull's
    copies and not the cached repeats.
    """
    night = a_night(bosses=(2,))
    fight_a, fight_b = (attempt.fight_id for attempt in night.night.bosses[0].attempts)
    first = tuple(a_reference_record(i) for i in (1, 2, 3))
    second = tuple(a_reference_record(i, from_cache=True) for i in (1, 2, 3))

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
        records_by_fight={fight_a: first, fight_b: second},
    )

    assert report.provenance.references == first


def test_a_withheld_pace_notice_becomes_one_provenance_line() -> None:
    night = a_night(bosses=(1,))
    encounter = night.night.bosses[0].attempts[0]
    fight_id = encounter.fight_id
    sample = PaceSample(unavailable=NO_SINGLE_BOSS)
    findings = analyse_pace(encounter, sample)

    report = build_night_report(
        night,
        {fight_id: findings},
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
    )

    named = [line for line in report.provenance.withheld if line.startswith(f"Fight {fight_id}:")]
    assert named == [
        f"Fight {fight_id}: damage pace against the kills was not compared. {NO_SINGLE_BOSS}"
    ]


def three_wipes_one_handed_no_sample() -> dict[str, RaidReport]:
    """Three wipes at one boss: one compared, one handed a sample that withheld, one handed none.

    The switch under test is on being handed a sample, not on that sample
    succeeding: `load_pace_sample` ran for both of the first two, and only the
    third is a pull `pace_by_fight` never names -- the shape a kill or a
    `--no-compare` night has. Returned by role, so each test below reads the
    pull it is about by name rather than by position.
    """
    night = a_night(bosses=(3,))
    compared, unavailable, untouched = night.night.bosses[0].attempts
    sample = a_sample(80, int(compared.duration_seconds))

    report = build_night_report(
        night,
        {compared.fight_id: analyse_pace(compared, sample)},
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss=NO_FINDINGS,
        pace_by_fight={
            compared.fight_id: sample,
            unavailable.fight_id: PaceSample(unavailable=NO_SINGLE_BOSS),
        },
    )
    by_fight = {pull.report.provenance.fight_id: pull.report for pull in report.bosses[0].pulls}
    return {
        "compared": by_fight[compared.fight_id],
        "unavailable": by_fight[unavailable.fight_id],
        "untouched": by_fight[untouched.fight_id],
    }


def test_a_pull_handed_a_pace_sample_states_the_wipes_own_reason_on_every_card() -> None:
    """Design 14.3: the pull's page is the page `raid --fight N` draws for that wipe.

    `raid` on a wipe says `WITHHELD_DETAIL` on the card of every raider it
    compared -- the attempt did not kill, so no parse leaderboard sample stands
    beside it. `NO_COMPARISON_RAN` says no reference run was fetched at all,
    which is false of a pull `load_pace_sample` ran for.
    """
    pulls = three_wipes_one_handed_no_sample()

    for role in ("compared", "unavailable"):
        cards = pulls[role].players
        assert len(cards) == len(ROSTER), role
        assert [card.spell_and_talent.reason for card in cards] == [WITHHELD_DETAIL] * 2, role


def test_a_pull_handed_a_pace_sample_withholds_its_damage_tab_as_raid_does_on_that_wipe() -> None:
    """The Damage tab's own fallback: `raid`'s wipe withholds it with `WITHHELD_DETAIL`.

    The compared pull's tab opens on its pace row, so the fallback shows only
    on the pull whose sample withheld -- the one place a reader meets it.
    """
    pulls = three_wipes_one_handed_no_sample()

    assert pulls["compared"].damage.state is SectionState.PRESENT
    unavailable = pulls["unavailable"].damage
    assert unavailable.state is SectionState.WITHHELD
    assert unavailable.reason == WITHHELD_DETAIL


def test_a_pull_handed_a_pace_sample_states_the_wipes_reason_once_in_its_provenance() -> None:
    """`raid`'s wipe states `WITHHELD_DETAIL` once, as the Damage line, and never again.

    Its per-card spell-and-talent lines are suppressed there as repeats of the
    reason the whole attempt shares, so the night pull carries no "Spell and
    talent comparison" line either -- and nothing saying no reference was fetched.
    """
    pulls = three_wipes_one_handed_no_sample()

    for role in ("compared", "unavailable"):
        withheld = pulls[role].provenance.withheld
        assert [line for line in withheld if WITHHELD_DETAIL in line] == [
            f"Damage against other kills: {WITHHELD_DETAIL}"
        ], role
        assert not any(line.startswith("Spell and talent comparison") for line in withheld), role
        assert not any(NO_COMPARISON_RAN in line for line in withheld), role


def test_a_pull_handed_no_pace_sample_keeps_no_comparison_ran_at_every_site() -> None:
    """A kill, or a `--no-compare` night: nothing was fetched for it, and the page says so."""
    pulls = three_wipes_one_handed_no_sample()
    untouched = pulls["untouched"]

    assert [card.spell_and_talent.reason for card in untouched.players] == [
        NO_COMPARISON_RAN
    ] * 2
    assert untouched.damage.state is SectionState.WITHHELD
    assert untouched.damage.reason == NO_COMPARISON_RAN
    assert [line for line in untouched.provenance.withheld if NO_COMPARISON_RAN in line] == [
        f"Damage against other kills: {NO_COMPARISON_RAN}",
        f"Spell and talent comparison: {NO_COMPARISON_RAN}",
    ]
    assert not any(WITHHELD_DETAIL in line for line in untouched.provenance.withheld)


def test_the_boss_pace_line_lands_on_the_summary_and_nowhere_on_a_pull() -> None:
    """Task 1's line, handed through `findings_by_boss` as the command will hand it.

    Placed by the existing `progression.attempts.` prefix rule, so this pins
    that the wiring reaches the summary's own Attempts tab and never leaks
    onto a pull's own tabs -- not a new placement rule of its own. Read off
    `summary.attempt_rows` directly, the one field the brief names, rather
    than a union across every progression field: a builder that placed the
    line on `repeat_rows` or `best_rows` instead would still pass a check
    that only asked whether the line landed somewhere on the summary.
    """
    night = a_night(bosses=(2,))
    boss = night.loaded[0]
    encounter_id = boss.progression.encounter_id
    attempts = boss.attempts_with_events
    samples = {
        attempt.encounter.fight_id: a_sample(80, int(attempt.encounter.duration_seconds))
        for attempt in attempts
    }
    boss_line = analyse_night_pace(attempts, samples)
    assert boss_line, "the fixture must actually earn the line, or this pins nothing"

    report = build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=True,
        findings_by_boss={encounter_id: tuple(boss_line)},
    )

    summary = report.bosses[0].summary
    assert summary is not None
    attempt_row_ids = [row.finding_id for row in summary.attempt_rows]
    assert attempt_row_ids.count(NIGHT_PACE_ID) == 1
    for pull in report.bosses[0].pulls:
        pull_ids = [row.finding_id for row in all_raid_ledger_rows(pull.report)]
        assert NIGHT_PACE_ID not in pull_ids
