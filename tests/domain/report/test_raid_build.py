# ABOUTME: Behaviour tests for the raid report builder: every finding placed once, or said why.
# ABOUTME: The Damage tab is the section a wipe withholds, and it has to say so in the tool's words.

from collections import Counter

import pytest

from tests.domain.report.test_raid_frame import an_encounter
from tests.domain.report.test_raid_ledger import RAID_FAMILIES
from wowperf.domain.analysis.attempt_shape import NO_REFERENCE_SAMPLE, WITHHELD_ID
from wowperf.domain.comparison.parse_axis import WITHHELD_DETAIL
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.report.alive_chart import PLOT_X0, PLOT_X1
from wowperf.domain.report.frame import NO_COMPARISON_RAN
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.raid_build import build_raid_report
from wowperf.domain.report.raid_model import RaidReport, all_raid_ledger_rows
from wowperf.domain.season import Consumables, Defensives

FETCHED = "2026-09-15T08:00:00Z"
NO_DEFENSIVES = Defensives()
NO_CONSUMABLES = Consumables()

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


def a_raid_fixture(kill: bool = True) -> tuple[LoadedEncounter, Player]:
    """Two raiders, one death, and a log that begins well after the report's zero.

    The start is not zero on purpose: a death's elapsed time and a fight's
    window are both measured from it, and a fixture starting at zero cannot
    tell a reading of the fight's own start apart from a raw timestamp.
    """
    loaded = LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs",
            players=(EMBERKIN, STONEWAKE),
            kill=kill,
            fight_percentage=0.0 if kill else 12.4,
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

    Task 2 puts a `player_slug` on every raid comparison finding and appends
    the same slug to its id, so a fixture that set one without the other would
    be testing a shape the analysis does not emit.
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
            title=f"No comparison against other kills is available for {name}",
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
    """The gate Task 2 exists to get through, asserted rather than assumed.

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
        build_raid_report(loaded, twice, subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES)


def test_every_finding_reaches_exactly_one_field() -> None:
    """Placed, carded, or caught -- once each, never twice and never none.

    The page renders each field in turn, so a finding in two fields is drawn
    twice under two headings and a finding in none is measured and never
    shown.
    """
    loaded, subject = a_raid_fixture()
    findings = one_of_every_raid_family()

    report = build_raid_report(
        loaded, findings, subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    placed = placements(report)
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
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert [row.finding_id for row in report.observations] == [AN_UNPLACED_FAMILY]


def test_the_only_raid_decomposition_heads_the_summary_and_is_not_drawn_twice() -> None:
    """`deaths.total` contains the other death figures, so it heads the ledger alone.

    A decomposition row that also sat beneath the death cards would state the
    same seconds in two places and invite a reader to add them together.
    """
    loaded, subject = a_raid_fixture()

    report = build_raid_report(
        loaded, one_of_every_raid_family(), subject, frozenset({EMBERKIN_SLUG}), FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        NO_DEFENSIVES, NO_CONSUMABLES,
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
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.damage_rows, "the compared raider's own damage rows went missing"
    assert report.damage.state is SectionState.PRESENT


def test_an_analysis_that_compared_nothing_does_not_blame_the_boss() -> None:
    """`--no-compare` withholds the same tab for a different reason, and says which.

    "This attempt did not kill the boss" is false of a kill nobody compared,
    and it is the sentence an exact-id lookup would reach for by accident.
    """
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, (a_finding("deaths.total", seconds=42.0),), subject, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.damage.state is SectionState.WITHHELD
    assert report.damage.reason == NO_COMPARISON_RAN


def test_the_withheld_damage_tab_is_named_in_the_provenance() -> None:
    """A tab a reader never opens still has to be findable in one list.

    The Provenance tab is where this report states what it did not say, so a
    section withheld on a page of seven tabs is named there by the tab it
    belongs to and by the reason it was withheld for.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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

    The suppression is on this list alone. Each card still carries its own
    reason, which is the half a reader looking at one raider needs without
    scrolling to Provenance, and the second assertion is what keeps the fix
    from being made in the wrong place.
    """
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    withheld = report.provenance.withheld
    assert withheld, "a page with a withheld section disclosed nothing"
    assert [line for line in withheld if WITHHELD_DETAIL in line] == [
        f"Damage against other kills: {WITHHELD_DETAIL}"
    ]
    assert report.players, "the fixture built no cards to check the reason survived on"
    assert [card.spell_and_talent.reason for card in report.players] == [
        WITHHELD_DETAIL, WITHHELD_DETAIL
    ]


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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        loaded, (), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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


def test_the_fights_deaths_each_get_a_recap_card() -> None:
    """The recap reaches the raid page: `build_deaths` reads a fight, not a run."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, a_wipes_findings(), subject, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert [card.player for card in report.deaths] == ["Stonewake"]


def test_the_subjects_card_opens_the_players_tab() -> None:
    """`--player` names one raider, and the tab that opens has to be theirs."""
    loaded, _ = a_raid_fixture()

    report = build_raid_report(
        loaded, (), STONEWAKE, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.verdict is None


def test_a_withheld_verdict_does_not_head_the_summary() -> None:
    """Its reason is already in Provenance. A landing tab whose first line says
    nothing was concluded is the complaint section 11 exists to fix."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, (*a_wipes_findings(), _a_withheld_verdict()), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.verdict is None


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
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    elsewhere = [row.finding_id for row in all_raid_ledger_rows(report)]
    assert elsewhere.count("wipe.cause") == 0, elsewhere
