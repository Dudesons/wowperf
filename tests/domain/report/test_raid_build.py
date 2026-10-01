# ABOUTME: Behaviour tests for the raid report builder: every finding placed once, or said why.
# ABOUTME: The Damage tab is the section a wipe withholds, and it has to say so in the tool's words.

import re
from collections import Counter

import pytest

from tests.domain.analysis.test_spikes import a_heavy_moment_left_unanswered
from tests.domain.comparison.test_pace_curve import a_kill, steady
from tests.domain.comparison.test_pace_player import (
    BLOOD,
    FROST,
    NO_SELF_RESURRECTIONS,
)
from tests.domain.comparison.test_pace_player import ROLES as PLAYER_PACE_ROLES
from tests.domain.comparison.test_pace_player import a_sample as a_player_pace_sample
from tests.domain.comparison.test_pace_player import a_wipe as a_player_pace_wipe
from tests.domain.report.test_raid_frame import an_encounter
from tests.domain.report.test_raid_ledger import RAID_FAMILIES
from wowperf.domain.analysis.attempt_shape import NO_REFERENCE_SAMPLE, WITHHELD_ID, classify_attempt
from wowperf.domain.analysis.defensives import _ceiling_withheld
from wowperf.domain.analysis.spikes import SPIKES_ID, UNANSWERED_ID
from wowperf.domain.comparison.kill_time import KILL_TIME_ID, analyse_kill_time
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.comparison.pace import PACE_ID, PROJECTION_ID, PaceSample, analyse_pace
from wowperf.domain.comparison.pace_player import (
    PLAYER_PACE_PREFIX,
    PLAYER_UNAVAILABLE_PREFIX,
    SCOPE_LINE,
    analyse_player_pace,
)
from wowperf.domain.comparison.parse_axis import WITHHELD_DETAIL, ParseSubject
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.report.alive_chart import BASELINE_Y, PLOT_TOP, PLOT_X0, PLOT_X1
from wowperf.domain.report.build import ceiling_withheld_line
from wowperf.domain.report.deaths import NO_CARDS_ASKED
from wowperf.domain.report.frame import NO_COMPARISON_RAN
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.raid_build import build_raid_report
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows
from wowperf.domain.season import Consumables, Defensives, Roles, ThroughputCooldowns

FETCHED = "2026-09-15T08:00:00Z"
NO_DEFENSIVES = Defensives()
NO_CONSUMABLES = Consumables()
NO_ROLES = Roles()

EMBERKIN = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700)
STONEWAKE = Player(
    actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=690
)
EMBERKIN_SLUG = "emberkin-0"
STONEWAKE_SLUG = "stonewake-1"
"""The slugs `slugs_by_actor` mints for the roster below, in that order.

`RAID_FAMILIES` spells its comparison ids with `emberkin-0`, so Emberkin has
to sit at the roster's index 0 for those findings to reach a card at all.
"""

FIGHT_START_MS = 1_000_000
DEATH_MS = 1_150_000
FIGHT_END_MS = 1_300_000


def a_raid_fixture(
    kill: bool = True, boss_percentage: float | None = None
) -> tuple[LoadedEncounter, Player]:
    """Two raiders, one death, and a log that begins well after the report's zero.

    The start is not zero on purpose: a death's elapsed time and a fight's
    window are both measured from it, and a fixture starting at zero cannot
    tell a reading of the fight's own start apart from a raw timestamp.

    `boss_percentage` stays `None` by default, which is what every caller but
    one wants: `classify_attempt` withholds a verdict without it, and most of
    this file's fixtures are not the verdict's own tests.
    """
    loaded = LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs",
            players=(EMBERKIN, STONEWAKE),
            kill=kill,
            fight_percentage=0.0 if kill else 12.4,
            boss_percentage=boss_percentage,
            start_ms=FIGHT_START_MS,
            end_ms=FIGHT_END_MS,
        ),
        deaths=(
            Death(
                actor_id=2, player_name="Stonewake", timestamp_ms=DEATH_MS,
                killing_blow="Ravenous Feast",
            ),
        ),
    )
    return loaded, EMBERKIN


HEALER = Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=690)
ROLES_WITH_HEALER = Roles(healers=("Priest/Holy",))
"""A roster where a third raider heals, and the one who dies (Stonewake) does not."""


def a_raid_fixture_with_healer() -> tuple[LoadedEncounter, Player]:
    """`a_raid_fixture`'s own roster, plus a healer who survives the same death."""
    loaded = LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs",
            players=(EMBERKIN, STONEWAKE, HEALER),
            kill=True,
            fight_percentage=0.0,
            start_ms=FIGHT_START_MS,
            end_ms=FIGHT_END_MS,
        ),
        deaths=(
            Death(
                actor_id=2, player_name="Stonewake", timestamp_ms=DEATH_MS,
                killing_blow="Ravenous Feast",
            ),
        ),
    )
    return loaded, EMBERKIN


def a_finding(finding_id: str, seconds: float | None = None) -> Finding:
    """One finding of the given family, carrying the slug its id ends with.

    The analysis puts a `player_slug` on every raid comparison finding and
    appends the same slug to its id, so a fixture that set one without the
    other would be testing a shape the analysis does not emit.
    """
    slug = next(
        (one for one in (EMBERKIN_SLUG, STONEWAKE_SLUG) if finding_id.endswith(f".{one}")), ""
    )
    return Finding(
        id=finding_id,
        title=f"Title of {finding_id}",
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
        player_slug=slug,
    )


TIMED_FAMILIES = ("deaths.total", "deaths.single.0", "deaths.chain.0", "deaths.repeat.emberkin")
"""The raid families that carry a seconds figure, from `analyse_deaths`.

They are what puts a row in `ledger_decomposition` and in `summary_pointers`;
a fixture where everything cost nothing would leave both empty and test
neither.
"""


AN_UNPLACED_FAMILY = "compare.confound.difficulty"
"""A family no raid placement claims and no raider's card claims either.

`build_observations` is a structural catch-all, and a catch-all is only a
guarantee if something actually takes the route. Every id in `RAID_FAMILIES` is
placed by name, so without this one the call to `build_observations` could be a
literal `()` and every test in this file would stay green -- which is precisely
the guarantee it exists to give, untested.

`compare.confound.` is a real id shape rather than an invented one: the Mythic+
table places it on the route tab, and `RAID_PLACEMENTS` deliberately omits it
because a boss fight has no route. It stands here for the analyser that starts
emitting something tomorrow.
"""


def one_of_every_raid_family() -> tuple[Finding, ...]:
    """One finding per family `analyse_encounter` can emit, plus one nothing places.

    Built from `RAID_FAMILIES`, which `test_raid_ledger` holds against the
    service itself, so a family the service starts emitting reaches this test
    without anybody remembering to add it here.
    """
    return (
        *(
            a_finding(one, seconds=30.0 if one in TIMED_FAMILIES else None)
            for one in RAID_FAMILIES
        ),
        a_finding(AN_UNPLACED_FAMILY),
    )


def a_wipes_findings() -> tuple[Finding, ...]:
    """What `compare_parse_axis` emits for each raider when the attempt did not kill.

    One finding per raider, each carrying `WITHHELD_DETAIL` itself rather than
    a paraphrase: the reason the page prints has to be the comparison's own
    sentence, and a fixture that invented one could not tell whether the
    builder quoted it or wrote its own.
    """
    return tuple(
        Finding(
            id=f"compare.parse.unavailable.{slug}",
            title=f"No parse comparison is available for {name}",
            detail=WITHHELD_DETAIL,
            confidence=Confidence.MEASURED,
            player_slug=slug,
        )
        for slug, name in ((EMBERKIN_SLUG, "Emberkin"), (STONEWAKE_SLUG, "Stonewake"))
    )


def a_kills_findings() -> tuple[Finding, ...]:
    """The three families that read this report's own rankings, which a kill has."""
    return (
        a_finding(f"compare.damage.total.{EMBERKIN_SLUG}"),
        a_finding(f"compare.damage.targets.{EMBERKIN_SLUG}"),
        a_finding(f"compare.rank.{EMBERKIN_SLUG}"),
    )


PACE_DURATION = (FIGHT_END_MS - FIGHT_START_MS) / 1000
"""The fixture fight's own duration, so a sample built against it is never cut
short of what `a_raid_fixture`'s encounter actually runs."""


def a_pace_sample(per_second: int) -> PaceSample:
    """Three reference kills at a steady 100 a second, and our own steady rate.

    Three references clears `MIN_SAMPLE_FOR_AGGREGATE`, so the reading is a
    real band rather than the single-kill fallback, and every reference runs
    longer than the fixture fight so the band is never cut before its end.
    """
    kills = tuple(a_kill(100, int(PACE_DURATION) + 60) for _ in range(3))
    return PaceSample(ours=steady(per_second, int(PACE_DURATION) + 60), references=kills)


def placements(report: RaidReport) -> list[str]:
    """Every finding the page places, with each Summary pointer's second copy removed.

    A pointer is deliberately a second reference to a row that lives on another
    tab -- `RaidReport.summary_pointers` says the Summary renders a link to that
    card and never a second card -- so it is one finding drawn twice on purpose
    and not one placed twice. Removing exactly one copy per pointer leaves the
    placements.

    Read through `all_raid_ledger_rows` rather than by naming the fields again,
    so a field added to `RaidReport` is covered here the day it is added.
    """
    drawn = [row.finding_id for row in all_raid_ledger_rows(report)]
    for pointer in report.summary_pointers:
        drawn.remove(pointer.finding_id)
    return drawn


def test_the_builder_refuses_two_findings_that_share_an_id() -> None:
    """The gate every per-player comparison id has to get through, asserted
    rather than assumed.

    A duplicate id silently loses a title from `titles_by_id` and sends every
    pointer at it to the wrong row. Raising here is what turned a defect that
    shipped three times into one that cannot ship again.
    """
    loaded, subject = a_raid_fixture()
    twice = [
        a_finding(f"compare.talents.{EMBERKIN_SLUG}"),
        a_finding(f"compare.talents.{EMBERKIN_SLUG}"),
    ]

    with pytest.raises(ValueError, match=f"compare.talents.{EMBERKIN_SLUG}"):
        build_raid_report(
            loaded, twice, subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES
        )


def test_every_finding_reaches_exactly_one_field() -> None:
    """Placed, carded, or caught -- once each, never twice and never none.

    The page renders each field in turn, so a finding in two fields is drawn
    twice under two headings and a finding in none is measured and never
    shown. A per-raider parse notice the withheld Damage tab states for the
    whole fight is counted as stated there: this kill's tab is open, so none
    of this fixture's is, and its notice has to reach its card.
    """
    loaded, subject = a_raid_fixture()
    findings = one_of_every_raid_family()

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    placed = placements(report) + stated_by_the_damage_tab(report, findings)
    assert placed, "the report drew no rows at all"
    assert report.summary_pointers, "no Summary pointer, so pointers and placements read alike"
    assert sorted(placed) == sorted(finding.id for finding in findings), (
        f"placed twice: {sorted(one for one, count in Counter(placed).items() if count > 1)}; "
        f"placed nowhere: {sorted({finding.id for finding in findings} - set(placed))}"
    )
    for pointer in report.summary_pointers:
        assert pointer.finding_id in placed, (
            f"{pointer.finding_id} heads the Summary and no tab carries the card it points at"
        )


def test_a_family_nobody_placed_is_caught_rather_than_dropped() -> None:
    """The catch-all catches, which is the one thing it exists to do.

    A finding no placement claims must still reach the page. The alternative is
    an analyser that starts measuring something and a report that silently
    never shows it -- and `build_observations` is a structural catch-all rather
    than a whitelist precisely so that nobody has to remember to add a prefix.
    """
    loaded, subject = a_raid_fixture()

    report = build_raid_report(
        loaded, one_of_every_raid_family(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [row.finding_id for row in report.observations] == [AN_UNPLACED_FAMILY]


def test_the_heaviest_moments_sit_with_what_hit_the_raid_and_nowhere_else() -> None:
    loaded, subject = a_raid_fixture()
    findings = a_heavy_moment_left_unanswered(setting="fight")
    assert [finding.id for finding in findings] == [SPIKES_ID, UNANSWERED_ID]

    report = build_raid_report(
        loaded, findings, subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES
    )

    assert [row.finding_id for row in report.mechanics_rows] == [SPIKES_ID, UNANSWERED_ID]
    assert sorted(placements(report)) == sorted([SPIKES_ID, UNANSWERED_ID])


def test_the_only_raid_decomposition_heads_the_summary_and_is_not_drawn_twice() -> None:
    """`deaths.total` contains the other death figures, so it heads the ledger alone.

    A decomposition row that also sat beneath the death cards would state the
    same seconds in two places and invite a reader to add them together.
    """
    loaded, subject = a_raid_fixture()

    report = build_raid_report(
        loaded, one_of_every_raid_family(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [row.finding_id for row in report.ledger_decomposition] == ["deaths.total"]
    assert report.death_rows, "the death tab drew no rows to check the exclusion against"
    assert "deaths.total" not in [row.finding_id for row in report.death_rows]
    assert "deaths.total" not in [row.finding_id for row in report.summary_pointers]


def test_a_wipe_withholds_the_damage_tab_and_says_why() -> None:
    """Design section 13, and the risk it names: an empty section teaches nothing."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage_rows == ()
    assert report.damage.state is SectionState.WITHHELD
    assert "did not kill" in report.damage.reason
    assert report.damage.reason == WITHHELD_DETAIL


def test_a_kill_with_a_sample_opens_the_damage_tab() -> None:
    """The other half of the branch above, so neither reads as the default."""
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_kills_findings(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.state is SectionState.PRESENT
    assert report.damage.reason == ""
    assert report.damage_rows, "an open damage tab with no rows on it"


def test_a_kill_one_raider_had_no_leaderboard_for_still_opens_the_damage_tab() -> None:
    """One raider's absent sample must not hide another raider's measured figures.

    A twenty-player raid routinely has both on one page: the rows exist, and
    the unavailable finding beside them belongs to somebody else's card.
    """
    loaded, subject = a_raid_fixture(kill=True)
    findings = (
        *a_kills_findings(),
        a_finding(f"compare.parse.unavailable.{STONEWAKE_SLUG}"),
    )

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage_rows, "the compared raider's own damage rows went missing"
    assert report.damage.state is SectionState.PRESENT


def test_a_kill_whose_damage_tab_is_open_keeps_a_raiders_reason_on_their_card() -> None:
    """An open Damage tab states no reason, so it cannot stand in for a card's.

    The fight-wide reason a card may leave unsaid is the one the withheld Damage
    tab prints. On a kill where one raider's leaderboard answered, the tab is
    open on that raider's rows and says nothing; the other raider's own reason,
    which is the first `compare.parse.unavailable` finding on the page, would be
    stated nowhere if the card dropped it too.
    """
    loaded, subject = a_raid_fixture(kill=True)
    own = Finding(
        id=f"compare.parse.unavailable.{STONEWAKE_SLUG}",
        title="No ranked parse was available for Stonewake",
        detail=ONE_RAIDERS_REASON,
        confidence=Confidence.MEASURED,
        player_slug=STONEWAKE_SLUG,
    )

    report = build_raid_report(
        loaded, (*a_kills_findings(), own), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.state is SectionState.PRESENT
    cards = {card.slug: card for card in report.players}
    assert cards[STONEWAKE_SLUG].spell_and_talent.reason == ONE_RAIDERS_REASON
    assert own.id in [row.finding_id for row in cards[STONEWAKE_SLUG].spell_and_talent_rows]


def test_an_analysis_that_compared_nothing_does_not_blame_the_boss() -> None:
    """`--no-compare` withholds the same tab for a different reason, and says which.

    "This attempt did not kill the boss" is false of a kill nobody compared,
    and it is the sentence an exact-id lookup would reach for by accident.
    """
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, (a_finding("deaths.total", seconds=42.0),), subject, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.state is SectionState.WITHHELD
    assert report.damage.reason == NO_COMPARISON_RAN


def test_a_raid_read_with_no_compare_keeps_its_reason_on_every_card() -> None:
    """Only a caller that states the parse axis's absence elsewhere silences the cards.

    `raid --no-compare` hands no parse subject and states the absence nowhere
    else for a whole page, so each card still says no reference was fetched.
    """
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert len(report.players) == 2, "the fixture built no cards to check the reason on"
    assert [card.spell_and_talent.reason for card in report.players] == [
        NO_COMPARISON_RAN, NO_COMPARISON_RAN
    ]


def test_the_withheld_damage_tab_is_named_in_the_provenance() -> None:
    """A tab a reader never opens still has to be findable in one list.

    The Provenance tab is where this report states what it did not say, so a
    section withheld on a page of seven tabs is named there by the tab it
    belongs to and by the reason it was withheld for.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    withheld = report.provenance.withheld
    assert withheld, "a page with a withheld section disclosed nothing"
    assert [line for line in withheld if line.startswith("Damage against other kills: ")]
    assert all("did not kill" in line for line in withheld), withheld


def test_a_reason_the_whole_attempt_shares_is_disclosed_once_not_once_per_raider() -> None:
    """One line per distinct reason, because the reason is about the attempt.

    Every raider's comparison on a wipe is withheld for the same reason -- the
    boss lived -- so a line per raider says nothing about any of them twenty
    times. The Mythic+ sibling repeats it per card because a keystone roster is
    five and five copies read as emphasis; twenty read as a bug.

    The cards say nothing of it either: the Damage tab states the reason the
    whole attempt shares, and a card restating it is the same repetition one
    card at a time.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    withheld = report.provenance.withheld
    assert withheld, "a page with a withheld section disclosed nothing"
    assert [line for line in withheld if WITHHELD_DETAIL in line] == [
        f"Damage against other kills: {WITHHELD_DETAIL}"
    ]
    assert report.players, "the fixture built no cards to check the reason survived on"
    assert [card.spell_and_talent.reason for card in report.players] == ["", ""]


def test_a_wipe_states_the_parse_reason_on_its_damage_tab_and_on_no_card() -> None:
    """Section 5.5: on a `raid --fight N` wipe the absence is stated once, on the Damage tab.

    The reason is the attempt's -- the boss lived -- and not any raider's, so a
    card that restated it would print the Damage tab's paragraph once per
    raider: twice as the card's withheld line and its per-slug row, on every card.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.reason == WITHHELD_DETAIL
    assert len(report.players) == 2, "the fixture built no cards to check the silence on"
    for card in report.players:
        assert card.spell_and_talent.state is SectionState.WITHHELD, card.slug
        assert card.spell_and_talent.reason == "", card.slug
        assert not [
            row for row in card.spell_and_talent_rows
            if row.finding_id.startswith("compare.parse.unavailable.")
        ], card.slug
    assert [
        line for line in report.provenance.withheld
        if line.startswith("Damage against other kills: ")
    ] == [f"Damage against other kills: {WITHHELD_DETAIL}"]
    assert not [
        line for line in report.provenance.withheld
        if line.startswith("Spell and talent comparison")
    ]


def stated_by_the_damage_tab(report: RaidReport, findings: tuple[Finding, ...]) -> list[str]:
    """The per-raider parse notices the Damage tab states for everyone at once.

    A `compare.parse.unavailable.<slug>` finding whose detail is the very reason
    the withheld Damage tab prints is said there, once, and reaches no ledger
    field of its own. Read off the report's own Damage section, so a builder
    that dropped such a finding from its card while the tab stood open --
    saying nothing -- accounts for nothing here and is caught as placed nowhere.
    """
    if report.damage.state is not SectionState.WITHHELD:
        return []
    return [
        finding.id
        for finding in findings
        if finding.id.startswith("compare.parse.unavailable.")
        and finding.detail == report.damage.reason
    ]


def test_a_parse_reason_shared_by_the_fight_is_placed_once_not_per_raider() -> None:
    """The per-raider notices the Damage tab states are reached by no ledger field.

    Not on a card, and not under "Other findings" either: a notice taken off
    the cards and left to `build_observations`' catch-all would be the same
    paragraph moved, twice, to the bottom of the Summary. A timed finding and
    a family nothing places ride along so the accounting is not vacuous.
    """
    loaded, subject = a_raid_fixture(kill=False)
    findings = (
        *a_wipes_findings(),
        a_finding("deaths.total", seconds=30.0),
        a_finding(AN_UNPLACED_FAMILY),
    )

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    stated = stated_by_the_damage_tab(report, findings)
    assert sorted(stated) == sorted(one.id for one in a_wipes_findings())
    placed = placements(report)
    assert not set(placed) & set(stated), f"stated by the Damage tab and placed too: {placed}"
    assert [row.finding_id for row in report.observations] == [AN_UNPLACED_FAMILY]
    assert sorted(placed + stated) == sorted(finding.id for finding in findings)


ONE_RAIDERS_REASON = (
    "The parse leaderboard returned no reference kills for this specialisation at "
    "this difficulty, so casts a minute, talents and buff uptime are not compared. "
    "The percentile and the damage comparisons beside this one read this report's "
    "own rankings rather than a sample, and are unaffected."
)
"""A reason about one raider rather than about the attempt.

`parse_axis._no_sample`'s detail, carried whole rather than trimmed: this test
would pass against any distinct string, so the only thing a shortened copy
could do is claim a provenance it does not have.
"""


def test_a_raiders_own_reason_is_never_suppressed_with_the_attempts() -> None:
    """Only the reason the Damage section already gave is dropped from the list.

    A raider whose comparison was withheld for a reason of their own is not
    covered by the fight-wide line, and dropping theirs would lose the only
    disclosure of it. Two raiders with different reasons is the cheapest shape
    that states the rule -- the service gives everybody the same reason on a
    wipe, which is exactly why the test above cannot prove this half.
    """
    loaded, subject = a_raid_fixture(kill=False)
    shared, _ = a_wipes_findings()
    own = Finding(
        id=f"compare.parse.unavailable.{STONEWAKE_SLUG}",
        title="No ranked parse was available for Stonewake",
        detail=ONE_RAIDERS_REASON,
        confidence=Confidence.MEASURED,
        player_slug=STONEWAKE_SLUG,
    )

    report = build_raid_report(
        loaded, (shared, own), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    withheld = report.provenance.withheld
    assert withheld, "a page with a withheld section disclosed nothing"
    assert [line for line in withheld if ONE_RAIDERS_REASON in line] == [
        f"Spell and talent comparison for Stonewake: {ONE_RAIDERS_REASON}"
    ]


def test_the_report_names_the_fight_and_the_moment_it_was_fetched() -> None:
    """The header and the provenance both read the encounter, not a Run."""
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.header.boss == "The Twin Fangs"
    assert report.header.outcome == "Killed"
    assert report.provenance.report_code == "abc123"
    assert report.provenance.fight_id == 2
    assert report.provenance.fetched_at == FETCHED


def test_the_alive_chart_measures_deaths_from_the_fights_own_start() -> None:
    """`Death.timestamp_ms` sits on the report's clock, not the fight's.

    `a_raid_fixture` starts its fight well after the report's own zero for
    exactly this reason -- the same one `deaths.py::_when` subtracts
    `start_ms` for. `build_alive_chart`'s x axis expects an elapsed clock
    starting at zero, the clock its own tests are written against, so a
    builder that forwarded `Death.timestamp_ms` unconverted would push every
    death past the axis's own end and flatten it against `PLOT_X1`,
    regardless of when in the fight it actually happened.
    """
    loaded, subject = a_raid_fixture()

    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.alive_chart is not None
    elapsed_ms = DEATH_MS - FIGHT_START_MS
    duration_ms = FIGHT_END_MS - FIGHT_START_MS
    expected_x = PLOT_X0 + (elapsed_ms / duration_ms) * (PLOT_X1 - PLOT_X0)

    # One death makes three points by the step doubling: the start, then the
    # death's own pair. The pair's x is what proves the timestamp was read as
    # elapsed from the fight's start rather than passed straight through.
    assert len(report.alive_chart.points) == 3
    assert report.alive_chart.points[1].x == pytest.approx(expected_x)
    assert report.alive_chart.points[2].x == pytest.approx(expected_x)
    assert report.alive_chart.points[1].x != PLOT_X1


def test_the_alive_chart_endpoint_matches_the_verdicts_own_count() -> None:
    """The chart's last point and the verdict's "N of 20 alive at the end" must agree.

    `test_the_series_ends_where_the_verdict_says_it_does` in
    `test_attempt_shape.py` pins `alive_over_time` against `classify_attempt`
    with no shift in between the two. `build_raid_report` puts a shift between
    them -- `loaded.deaths` and `loaded.resurrections` are moved onto an
    elapsed clock before `build_alive_chart` ever sees them -- and nothing
    below that layer would notice a wiring change that broke the shift, or
    dropped one of the two tuples on the way through. Shifting every
    timestamp by the same constant cannot change who is left standing, so the
    verdict (built from the unshifted events) and the chart (built from the
    shifted ones) have to end on the same headcount if the wiring is right.
    """
    loaded, subject = a_raid_fixture(kill=False, boss_percentage=40.0)
    sample = MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ZzZzZz", fight_id=index, size=20,
                    duration_ms=200_000, deaths=1,
                ),
                abilities=(),
            )
            for index in range(5)
        )
    )
    verdict_finding = classify_attempt(
        loaded.encounter, loaded.deaths, sample, resurrections=loaded.resurrections
    )
    assert verdict_finding is not None, "fixture must reach a verdict to test its evidence line"

    report = build_raid_report(
        loaded, (verdict_finding,), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.verdict is not None
    assert report.alive_chart is not None
    alive_text, size_text = report.verdict.evidence[0].split(" of ")
    alive = int(alive_text)
    size = int(size_text.removesuffix(" alive at the end"))
    expected_y = BASELINE_Y - (alive / size) * (BASELINE_Y - PLOT_TOP)
    assert report.alive_chart.points[-1].y == pytest.approx(expected_y)


def test_the_fights_deaths_each_get_a_recap_card() -> None:
    """The recap reaches the raid page: `build_deaths` reads a fight, not a run."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [card.player for card in report.deaths] == ["Stonewake"]


def test_build_raid_report_draws_no_healers_group_without_throughput() -> None:
    loaded, subject = a_raid_fixture_with_healer()

    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, ROLES_WITH_HEALER,
    )

    assert report.deaths[0].healers is None


def test_build_raid_report_draws_a_healers_group_naming_the_healer_when_given_throughput() -> None:
    loaded, subject = a_raid_fixture_with_healer()

    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, ROLES_WITH_HEALER,
        throughput=ThroughputCooldowns(),
    )

    [card] = report.deaths
    assert card.healers is not None
    assert card.healers.lines[0].holder == "Holy Priest, Bríala"


def test_death_cards_false_skips_building_them_entirely() -> None:
    """The tier with no cards at all: `deaths` comes back empty, not built then discarded."""
    loaded, subject = a_raid_fixture(kill=False)

    without_cards = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        NO_ROLES, death_cards=False,
    )
    default = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        NO_ROLES,
    )

    assert without_cards.deaths == ()
    assert default.deaths != ()


def test_only_the_no_cards_tier_says_why_its_deaths_tab_is_empty() -> None:
    """The one tier whose empty `deaths` is not a reading of the log.

    A fight with no death has an empty tuple because nobody died, and the page
    says "No deaths." over it. This fixture's fight has one, so cards off
    empties the same tuple while the death findings stay -- and a page that
    printed the same sentence would be blaming the log for what the run
    decided. `deaths_note` is what the page reads instead, so it is set here
    and nowhere else.
    """
    loaded, subject = a_raid_fixture(kill=False)

    without_cards = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        NO_ROLES, death_cards=False,
    )
    default = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
        NO_ROLES,
    )

    assert without_cards.deaths_note == NO_CARDS_ASKED
    # The other half, and the reason the note is not simply always present: a
    # report that built its cards has nothing to explain, and an explanation
    # drawn beside a card would be false about it.
    assert default.deaths_note == ""
    assert default.deaths != ()


def test_the_subjects_card_opens_the_players_tab() -> None:
    """`--player` names one raider, and the tab that opens has to be theirs."""
    loaded, _ = a_raid_fixture()

    report = build_raid_report(
        loaded, (), STONEWAKE, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [card.name for card in report.players] == ["Stonewake", "Emberkin"]


def _a_withheld_verdict() -> Finding:
    """What `classify_attempt` now returns instead of dropping its reason."""
    return Finding(
        id=WITHHELD_ID,
        title="No verdict on why this attempt ended",
        detail=NO_REFERENCE_SAMPLE,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("no reference kills were drawn",),
    )


def test_a_withheld_attempt_verdict_is_disclosed_in_the_provenance() -> None:
    """Design 8.3: the withheld case is recorded, not dropped.

    `classify_attempt` returned a bare `None` for five situations and
    `analyse_encounter` dropped it, so a reader could not tell a verdict that
    was refused from one nobody asked for.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, (*a_wipes_findings(), _a_withheld_verdict()), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [
        line for line in report.provenance.withheld if NO_REFERENCE_SAMPLE in line
    ], report.provenance.withheld


def test_a_withheld_attempt_verdict_never_heads_the_summary() -> None:
    """`wipe` ranks 0, so a notice left among the findings leads the page.

    `severity.SEVERITY_BY_FAMILY` puts the wipe family first because a verdict
    frames everything under it. A notice saying there is no verdict inherits
    that rank, and would take the Summary's headline to say nothing.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, (*a_wipes_findings(), _a_withheld_verdict()), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    placed = [row.finding_id for row in all_raid_ledger_rows(report)]
    assert WITHHELD_ID not in placed, placed


def test_a_wipe_with_a_verdict_heads_the_summary_with_it() -> None:
    loaded, subject = a_raid_fixture(kill=False)
    verdict = Finding(
        id="wipe.cause",
        title="This attempt failed on execution: the raid was taken apart",
        detail="12 of 20 died.",
        confidence=Confidence.INFERRED,
    )

    report = build_raid_report(
        loaded, (*a_wipes_findings(), verdict), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.verdict is not None
    assert report.verdict.finding_id == "wipe.cause"


def test_a_kill_has_no_verdict_to_head_the_summary_with() -> None:
    """A kill produces no verdict at all, and the slot is absent rather than empty.

    `a_kills_findings` is this file's own kill-shaped fixture -- the brief for
    this task named a fixture `a_raids_findings`, which exists only in
    `test_raid_html_invariants.py`, and that module already imports from this
    one (`FETCHED`, `NO_CONSUMABLES`, `NO_DEFENSIVES`), so importing it back
    here would be a circular import.
    """
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_kills_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.verdict is None


def test_a_withheld_verdict_does_not_head_the_summary() -> None:
    """Its reason is already in Provenance. A landing tab whose first line says
    nothing was concluded is the complaint section 11 exists to fix."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, (*a_wipes_findings(), _a_withheld_verdict()), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.verdict is None


def _a_withheld_ceiling() -> Finding:
    """What `analyse_defensive_ceiling` returns when a fight ran too short to judge a
    defensive somebody pressed, built through the real minting function
    so this fixture's title, detail and evidence can never drift from what
    production actually emits -- a hand-written stand-in is what let the
    "stated per ability below" wording ship without anyone noticing the page
    had no such section.

    The id is checked against a literal rather than the production module's own
    `CEILING_WITHHELD_ID`: a test that constructs its expected value from the
    same constant the code under test reads proves nothing about whether the
    two agree.
    """
    finding = _ceiling_withheld(
        {("Ice Block", 1200.0)}, shape="fight",
        combat_description="This fight ran 300s",
    )
    assert finding.id == "defensives.ceiling.withheld"
    return finding


def test_a_withheld_defensive_ceiling_is_disclosed_in_the_provenance() -> None:
    """The notice reaches Provenance rather than staying silent.

    Mirrors `test_a_withheld_attempt_verdict_is_disclosed_in_the_provenance`
    above, for the withheld-ceiling notice that sits beside it.

    The disclosure is the per-ability evidence, not the detail sentence alone,
    so both must reach the page in the same Provenance entry or a reader can
    never tell which ability was withheld.
    """
    loaded, subject = a_raid_fixture()
    notice = _a_withheld_ceiling()

    report = build_raid_report(
        loaded, (notice,), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    withheld = report.provenance.withheld
    assert [line for line in withheld if "Defensive ceiling" in line] == [
        ceiling_withheld_line(notice)
    ]
    assert "Ice Block would need more than 1200s of combat" in withheld[0]


def test_a_withheld_defensive_ceiling_never_reaches_group_rows() -> None:
    """Left alone, `RAID_PLACEMENTS`' bare `defensives.` prefix would file this
    notice on the Players tab beside real per-ability ceiling judgements,
    where "I could not judge this" would read as one of them.

    A real ceiling finding rides along so the negative assertion cannot pass
    for the wrong reason -- an empty tab, or a notice that was never minted at
    all -- rather than because the builder actually pulled it out.
    """
    loaded, subject = a_raid_fixture()
    placed_ceiling = a_finding("defensives.ceiling.emberkin.0")
    notice = _a_withheld_ceiling()

    report = build_raid_report(
        loaded, (placed_ceiling, notice), subject, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    group_ids = [row.finding_id for row in report.group_rows]
    assert placed_ceiling.id in group_ids, "fixture must still place a real ceiling row"
    assert notice.id not in group_ids


def test_the_verdict_appears_once_on_the_page() -> None:
    """`build_observations`'s catch-all would place `wipe.cause` a second time,
    beneath "Other findings", if nothing excluded it: `report.verdict` is
    built from the same finding rather than from a field `all_raid_ledger_rows`
    walks, so the only way this could fail today is exactly that leak. A bound
    of `<= 1` would pass whether or not the leak was fixed, since the finding
    reaches the page at most once from `build_observations` alone; `== 0` is
    what actually pins that `all_raid_ledger_rows` -- which never walks
    `report.verdict` -- carries no second copy.
    """
    loaded, subject = a_raid_fixture(kill=False)
    verdict = Finding(
        id="wipe.cause",
        title="This attempt failed on execution: the raid was taken apart",
        detail="12 of 20 died.",
        confidence=Confidence.INFERRED,
    )

    report = build_raid_report(
        loaded, (*a_wipes_findings(), verdict), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    elsewhere = [row.finding_id for row in all_raid_ledger_rows(report)]
    assert elsewhere.count("wipe.cause") == 0, elsewhere


def test_a_behind_wipe_draws_the_pace_rows_the_chart_and_the_summary_pointer() -> None:
    """`build_raid_report` and `analyse_pace` are tested together: the findings
    below come from the real analyser rather than a hand-typed stand-in, so a
    change to either side would show up here."""
    loaded, subject = a_raid_fixture(kill=False)
    sample = a_pace_sample(per_second=80)  # behind: 80 a second against the kills' 100
    findings = analyse_pace(loaded.encounter, sample)

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES, pace=sample,
    )

    placed_ids = {row.finding_id for row in report.damage_rows}
    assert {PACE_ID, PROJECTION_ID} <= placed_ids
    assert report.damage.state is SectionState.PRESENT
    assert report.pace_chart is not None
    assert report.pace_warning is not None
    assert report.pace_warning.finding_id == PACE_ID


def test_an_on_pace_wipe_draws_the_chart_but_raises_no_warning() -> None:
    loaded, subject = a_raid_fixture(kill=False)
    sample = a_pace_sample(per_second=100)  # matches the kills' own rate: on pace
    findings = analyse_pace(loaded.encounter, sample)

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES, pace=sample,
    )

    assert report.pace_chart is not None
    assert report.pace_warning is None


def test_a_pace_comparison_that_found_nothing_is_disclosed_in_the_provenance_alone() -> None:
    loaded, subject = a_raid_fixture(kill=False)
    sample = PaceSample(unavailable="No boss actor could be found for this fight.")
    findings = analyse_pace(loaded.encounter, sample)

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES, pace=sample,
    )

    withheld = report.provenance.withheld
    assert [
        line for line in withheld
        if line.startswith("Damage pace against other kills: ")
    ]
    assert "compare.pace.unavailable" not in [
        row.finding_id for row in all_raid_ledger_rows(report)
    ]


def test_a_wipe_with_pace_rows_still_states_the_parse_reason_once() -> None:
    """Step 2.4's ruling: pace rows would otherwise make the Damage tab present
    and silently turn the fight-wide parse reason into a per-raider one.
    Guarded here on a wipe that carries both a pace comparison and the
    ordinary parse-unavailable findings `a_wipes_findings` gives every raider.
    """
    loaded, subject = a_raid_fixture(kill=False)
    sample = a_pace_sample(per_second=80)
    findings = (*analyse_pace(loaded.encounter, sample), *a_wipes_findings())

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES, pace=sample,
    )

    withheld = report.provenance.withheld
    assert [line for line in withheld if line.startswith("Damage against other kills: ")] == [
        f"Damage against other kills: {WITHHELD_DETAIL}"
    ]
    assert not [line for line in withheld if line.startswith("Spell and talent comparison for ")]


def test_a_wipe_with_pace_rows_states_the_parse_reason_on_its_open_damage_tab() -> None:
    """Design 5.5: on a raid wipe the reason stays, once, on the Damage tab.

    A pace row opens the tab, so its withheld paragraph never prints; the
    parse reason is then the tab's note beside the pace reading, and the cards
    that leave it unsaid are covered by what the tab does print.
    """
    loaded, subject = a_raid_fixture(kill=False)
    sample = a_pace_sample(per_second=80)
    findings = (*analyse_pace(loaded.encounter, sample), *a_wipes_findings())

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES, pace=sample,
    )

    assert report.damage.state is SectionState.PRESENT
    assert report.damage_note == WITHHELD_DETAIL
    assert len(report.players) == 2, "the fixture built no cards to check the silence on"
    for card in report.players:
        assert card.spell_and_talent.reason == "", card.slug
        assert not [
            row for row in card.spell_and_talent_rows
            if row.finding_id.startswith("compare.parse.unavailable.")
        ], card.slug


def test_an_open_damage_tab_with_parse_rows_carries_no_note() -> None:
    """The note is the parse comparison's withheld reason; a drawn comparison has none."""
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_kills_findings(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.state is SectionState.PRESENT
    assert report.damage_note == ""


def test_a_withheld_damage_tab_carries_its_reason_once_and_no_note() -> None:
    """A withheld tab prints its reason as the tab; a note beside it would say it twice."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.damage.reason == WITHHELD_DETAIL
    assert report.damage_note == ""


def test_a_kill_time_row_does_not_stand_in_for_the_parse_comparison() -> None:
    """A kill-time row opens the Damage tab, but it is not a parse row.

    On a page whose parse comparison left no row, the Provenance states why on
    its Damage line. Counting the kill-time row as one of the parse
    comparison's own would read that axis as present and drop the line.
    """
    loaded, subject = a_raid_fixture(kill=True)
    sample = MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code=f"ref{one}", fight_id=1, size=20, duration_ms=300_000
                ),
                abilities=(),
            )
            for one in range(3)
        )
    )
    findings = tuple(analyse_kill_time(loaded.encounter, sample))
    assert [finding.id for finding in findings] == [KILL_TIME_ID]

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert [row.finding_id for row in report.damage_rows] == [KILL_TIME_ID]
    assert report.damage.state is SectionState.PRESENT
    assert f"Damage against other kills: {NO_COMPARISON_RAN}" in report.provenance.withheld


def test_a_kill_with_no_pace_sample_draws_no_pace_fields() -> None:
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_kills_findings(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert report.pace_chart is None
    assert report.pace_warning is None
    assert report.damage_rows, "an open damage tab with no rows on it"


def _player_pace_findings() -> tuple[LoadedEncounter, tuple[Finding, ...]]:
    """Real per-player pace findings from `analyse_player_pace`, never hand-typed.

    `test_pace_player`'s own fixtures: Emberkin plays Mage/Frost and has three
    reference peers across `THREE_KILLS`, so `analyse_player_pace` reaches a
    real reading for them; Stonewake plays DeathKnight/Blood and has only two,
    which is what earns them the fewer-than-three notice instead. The two
    subjects are minted with this file's own `EMBERKIN_SLUG`/`STONEWAKE_SLUG`
    rather than `test_pace_player`'s own `p<actor_id>` convention, because
    `slugs_by_actor` mints a card's slug from the display name and the roster
    index alone -- both rosters name their players Emberkin and Stonewake in
    the same order, so the card slug and the finding's `player_slug` have to
    agree on the same two strings for the row to land on the right card.
    """
    loaded = a_player_pace_wipe()
    sample = a_player_pace_sample()
    subjects = (
        ParseSubject(player=FROST, slug=EMBERKIN_SLUG, display_name="Emberkin"),
        ParseSubject(player=BLOOD, slug=STONEWAKE_SLUG, display_name="Stonewake"),
    )
    findings = analyse_player_pace(
        loaded, sample, subjects, PLAYER_PACE_ROLES, NO_SELF_RESURRECTIONS
    )
    return loaded, tuple(findings)


def test_a_players_pace_finding_lands_on_their_own_card() -> None:
    loaded, findings = _player_pace_findings()
    pace_finding = next(f for f in findings if f.id == f"{PLAYER_PACE_PREFIX}{EMBERKIN_SLUG}")

    report = build_raid_report(
        loaded, findings, FROST, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, PLAYER_PACE_ROLES,
    )

    emberkin_card = next(card for card in report.players if card.slug == EMBERKIN_SLUG)
    other_cards = [card for card in report.players if card.slug != EMBERKIN_SLUG]
    assert [row.finding_id for row in emberkin_card.pace_rows] == [pace_finding.id]
    for card in other_cards:
        assert pace_finding.id not in [row.finding_id for row in card.pace_rows], (
            f"{pace_finding.id} landed on {card.slug}'s card as well as Emberkin's -- "
            "the slug match must be exact, not a prefix"
        )


def test_a_players_pace_notice_lands_on_their_own_card() -> None:
    loaded, findings = _player_pace_findings()
    notice = next(f for f in findings if f.id.startswith(PLAYER_UNAVAILABLE_PREFIX))
    assert notice.id == f"{PLAYER_UNAVAILABLE_PREFIX}.{STONEWAKE_SLUG}"

    report = build_raid_report(
        loaded, findings, FROST, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, PLAYER_PACE_ROLES,
    )

    stonewake_card = next(card for card in report.players if card.slug == STONEWAKE_SLUG)
    assert [row.finding_id for row in stonewake_card.pace_rows] == [notice.id]


def test_no_player_pace_row_or_notice_reaches_the_damage_tab() -> None:
    loaded, findings = _player_pace_findings()

    report = build_raid_report(
        loaded, findings, FROST, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, PLAYER_PACE_ROLES,
    )

    assert not any(
        row.finding_id.startswith(PLAYER_PACE_PREFIX) for row in report.damage_rows
    ), report.damage_rows


def test_every_player_pace_finding_is_placed_exactly_once() -> None:
    loaded, findings = _player_pace_findings()

    report = build_raid_report(
        loaded, findings, FROST, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, PLAYER_PACE_ROLES,
    )

    placed = placements(report)
    counts = Counter(placed)
    for finding in findings:
        assert counts[finding.id] == 1, (
            f"{finding.id} placed {counts[finding.id]} times, expected exactly once"
        )


def test_the_scope_line_appears_once_when_a_player_pace_finding_exists() -> None:
    loaded, findings = _player_pace_findings()

    report = build_raid_report(
        loaded, findings, FROST, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES, PLAYER_PACE_ROLES,
    )

    assert report.provenance.withheld.count(SCOPE_LINE) == 1


def test_the_scope_line_is_absent_without_a_player_pace_finding() -> None:
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )

    assert SCOPE_LINE not in report.provenance.withheld


def _every_string(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _every_string(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _every_string(item)]
    return []


def test_a_raid_page_that_compared_nothing_calls_nothing_on_it_a_run() -> None:
    # --no-compare hands no parse subject. The page says what it did not
    # compare, and a boss fight is not a run: "run" on its own names a
    # keystone, while "run-up" is the seconds before a death on any card.
    loaded, subject = a_raid_fixture()
    report = build_raid_report(
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
    )
    assert any(NO_COMPARISON_RAN in line for line in report.provenance.withheld), (
        report.provenance.withheld
    )
    for text in _every_string(report.model_dump()):
        assert not re.search(r"\brun\b(?!-)", text), text
