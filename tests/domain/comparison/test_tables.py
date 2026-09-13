# ABOUTME: The per-player measures the report's comparison table is built from.
# ABOUTME: One entry per compared player, keyed by the slug the page matches cards on.

from tests.domain.comparison.test_service import (
    ARCANE_BLAST,
    OUR_SLUG,
    OURS,
    THEIRS,
    a_loaded,
    a_run_sharing_a_pack,
    a_shared_pack_member,
    only_ours,
)
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.comparison.trash_spells import (
    MIN_ALIGNED_TRASH_SECONDS,
    aligned_trash,
    is_comparable,
)
from wowperf.domain.comparison.uptime import boss_windows
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import EnemyNpc, LoadedRun, Pull

METEOR = 153561
ARCANE_POWER = 12042


def a_pull_of(index: int, game_ids: tuple[int, ...], seconds: float, boss: bool = False) -> Pull:
    """`test_service.a_pull`, with a duration of our own choosing.

    Every pull that fixture builds runs sixty seconds, and a rate over sixty
    seconds is indistinguishable from the cast count behind it: `count / 60 *
    60` is `count`. A denominator that is not a minute is what lets an asserted
    rate fail when the division it claims to check is deleted.
    """
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk" if boss else "Pack",
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=index,
        y=index,
        enemies=tuple(EnemyNpc(actor_id=100 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def casts_on(
    actor_id: int, ability_id: int, name: str, pull_index: int, count: int
) -> tuple[CastEvent, ...]:
    """`count` presses of one ability inside one pull."""
    return tuple(
        CastEvent(
            actor_id=actor_id,
            ability_id=ability_id,
            ability_name=name,
            timestamp_ms=pull_index * 200_000 + 1_000 * n,
            pull_index=pull_index,
        )
        for n in range(count)
    )


def a_parse_row(code: str) -> ParseRow:
    return ParseRow(
        report_code=code,
        fight_id=16,
        keystone_level=16,
        duration_ms=1_399_143,
        character_name="Bríala",
        class_name="Mage",
        spec="Arcane",
    )


def test_every_compared_player_gets_one_entry_keyed_by_slug() -> None:
    sample = ParseSample(
        members=tuple(a_shared_pack_member(code) for code in ("REF1", "REF2", "REF3"))
    )
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=sample
    )

    measures = comparison_measures(a_run_sharing_a_pack(), (subject,))

    assert set(measures) == {OUR_SLUG}
    trash = {m.name: m for m in measures[OUR_SLUG].trash}
    assert trash["Arcane Blast"].verdict is Verdict.BELOW
    assert trash["Arcane Blast"].stretch is Stretch.TRASH
    assert measures[OUR_SLUG].pack_count == 1
    # The id, not only the name: the page draws an icon from it, and a name
    # can belong to more than one game id.
    assert trash["Arcane Blast"].ability_id == ARCANE_BLAST


def test_a_player_with_no_parse_sample_gets_no_entry() -> None:
    """A slug with an empty table and a slug that is absent read differently: the
    first says a comparison ran and found nothing, the second that none ran."""
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=None
    )

    assert comparison_measures(a_run_sharing_a_pack(), (subject,)) == {}


def test_a_player_whose_sample_came_back_empty_gets_no_entry() -> None:
    """The other half of the same guard. A sample object holding no members is
    what a leaderboard that answered with nothing leaves behind, and it says the
    same thing about the player as no sample at all: nothing was compared."""
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=ParseSample()
    )

    assert comparison_measures(a_run_sharing_a_pack(), (subject,)) == {}


def a_boss_parse_member(
    code: str, seconds: float, boss_casts: int, trash_casts: int = 0
) -> ParseMember:
    """A reference whose boss pull runs `seconds` and carries `boss_casts` Meteors.

    `trash_casts` puts the same ability on a pack of enemy types our route never
    fought. A boss rate that counted those would be counting presses from a
    stretch the boss comparison does not measure, and the pack matches nothing
    of ours, so it cannot reach the trash half either.
    """
    theirs = a_loaded(
        (THEIRS,),
        (a_pull_of(0, (9,), seconds, boss=True), a_pull_of(1, (7,), 60.0)),
        casts=(
            casts_on(THEIRS.actor_id, METEOR, "Meteor", 0, boss_casts)
            + casts_on(THEIRS.actor_id, METEOR, "Meteor", 1, trash_casts)
        ),
    )
    return ParseMember(row=a_parse_row(code), run=theirs.run, casts=theirs.casts)


def a_run_with_a_long_boss_pull() -> LoadedRun:
    """Our run: four Meteors over a two-minute boss pull, and two more off it."""
    return a_loaded(
        (OURS,),
        (a_pull_of(0, (1,), 60.0), a_pull_of(1, (9,), 120.0, boss=True)),
        casts=(
            casts_on(OURS.actor_id, METEOR, "Meteor", 0, 2)
            + casts_on(OURS.actor_id, METEOR, "Meteor", 1, 4)
        ),
    )


def test_a_boss_rate_is_the_sample_median_against_our_own_per_minute_figure() -> None:
    """Four Meteors over 120s is 2.0 a minute, not the 4 we pressed; the sample's
    three qualifying references sit at 2.0, 6.0 and 16.0, a median of 6.0 rather
    than their counts' median of 8. Neither figure is reachable without dividing."""
    sample = ParseSample(
        members=(
            a_boss_parse_member("REF1", 90.0, 3),
            a_boss_parse_member("REF2", 90.0, 9, trash_casts=5),
            a_boss_parse_member("REF3", 30.0, 8),
            # Two presses is below MIN_CASTS_TO_COMPARE, so this reference's own
            # sample is too small to argue from. Counted, its 2.0 a minute would
            # drag the median to 4.0.
            a_boss_parse_member("REF4", 60.0, 2),
        )
    )

    measures = comparison_measures(a_run_with_a_long_boss_pull(), only_ours(sample))[OUR_SLUG]

    boss = {m.name: m for m in measures.boss}
    assert boss["Meteor"].ours == 2.0
    assert boss["Meteor"].their_median == 6.0
    assert boss["Meteor"].their_rates == (2.0, 6.0, 16.0)
    assert boss["Meteor"].stretch is Stretch.BOSS
    assert boss["Meteor"].verdict is Verdict.BELOW
    assert measures.boss_seconds == 120.0
    # Our route and the sample's share no pack, so the trash half of the same
    # player's table is empty rather than restating the boss figures.
    assert measures.trash == ()
    assert measures.trash_seconds == 0.0


def test_a_sample_too_small_to_aggregate_names_no_boss_denominator() -> None:
    """Two references are below MIN_SAMPLE_FOR_AGGREGATE, so no boss comparison
    was drawn against this sample as a population at all.

    The empty table cannot say that on its own — a sample that was compared and
    matched nothing is empty too — so the denominator is what carries it: zero
    seconds, rather than naming the two minutes of boss pulls no comparison was
    drawn over. That is the only thing the aggregate gate decides while the
    sample floor and the per-ability floor are the same number, and it is the
    whole of what this test can hold it to.
    """
    sample = ParseSample(
        members=(a_boss_parse_member("REF1", 90.0, 3), a_boss_parse_member("REF2", 90.0, 9))
    )

    measures = comparison_measures(a_run_with_a_long_boss_pull(), only_ours(sample))[OUR_SLUG]

    assert measures.boss == ()
    assert measures.boss_seconds == 0.0


def a_trash_parse_member(
    code: str, game_ids: tuple[int, ...], seconds: float, casts: int
) -> ParseMember:
    """A reference whose route holds one pack of `game_ids`, fought for `seconds`."""
    theirs = a_loaded(
        (THEIRS,),
        (a_pull_of(0, game_ids, seconds), a_pull_of(1, (9,), 60.0, boss=True)),
        casts=casts_on(THEIRS.actor_id, ARCANE_BLAST, "Arcane Blast", 0, casts),
    )
    return ParseMember(row=a_parse_row(code), run=theirs.run, casts=theirs.casts)


def a_run_with_three_packs() -> LoadedRun:
    """Our run: two packs the sample shares between them, one it never fought, one boss."""
    return a_loaded(
        (OURS,),
        (
            a_pull_of(0, (1,), 90.0),
            a_pull_of(1, (2,), 70.0),
            a_pull_of(2, (5,), 80.0),
            a_pull_of(3, (9,), 60.0, boss=True),
        ),
        casts=(
            casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 0, 4)
            + casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 1, 4)
            + casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 2, 10)
            + casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 3, 10)
        ),
    )


def test_trash_denominators_are_every_pack_that_aligned_with_anybody() -> None:
    """No reference shares both of our packs, so our own denominator is the union
    of the two: 160 seconds, over which eight presses are 3.0 a minute rather than
    the 28 we pressed across the whole run. The sample's qualifying references sit
    at 3.0, 6.0 and 12.0, a median of 6.0 their raw counts cannot reach."""
    sample = ParseSample(
        members=(
            a_trash_parse_member("REF1", (1,), 120.0, 6),
            a_trash_parse_member("REF2", (2,), 150.0, 15),
            a_trash_parse_member("REF3", (1,), 60.0, 12),
            # Thirty seconds of shared trash is under MIN_ALIGNED_TRASH_SECONDS,
            # so this reference is not comparable on this stretch at all.
            # Counted, its 60.0 a minute would drag the median to 9.0.
            a_trash_parse_member("REF4", (1,), 30.0, 30),
            # Comparable, but two presses are below MIN_CASTS_TO_COMPARE.
            # Counted, its 2.0 a minute would drag the median to 4.5.
            a_trash_parse_member("REF5", (1,), 60.0, 2),
        )
    )

    measures = comparison_measures(a_run_with_three_packs(), only_ours(sample))[OUR_SLUG]

    trash = {m.name: m for m in measures.trash}
    assert trash["Arcane Blast"].ours == 3.0
    assert trash["Arcane Blast"].their_median == 6.0
    assert trash["Arcane Blast"].their_rates == (3.0, 6.0, 12.0)
    assert trash["Arcane Blast"].stretch is Stretch.TRASH
    assert trash["Arcane Blast"].verdict is Verdict.BELOW
    assert measures.trash_seconds == 160.0
    assert measures.pack_count == 2


def an_aura(band_ms: int, start_ms: int = 0) -> Aura:
    return Aura(
        ability_id=ARCANE_POWER,
        name="Arcane Power",
        total_uptime_ms=band_ms,
        uses=1,
        bands=(AuraBand(start_ms=start_ms, end_ms=start_ms + band_ms),),
    )


def an_aura_parse_member(
    code: str,
    seconds: float,
    band_ms: int,
    fought_a_boss: bool = True,
    band_start_ms: int = 0,
) -> ParseMember:
    """A reference carrying Arcane Power for `band_ms` of a boss pull `seconds` long.

    A boss pull built here always starts at zero, so a `band_start_ms` past the
    end of one is an aura the reference carried outside every boss pull.
    """
    pulls = (
        (a_pull_of(0, (9,), seconds, boss=True),)
        if fought_a_boss
        else (a_pull_of(0, (7,), seconds),)
    )
    theirs = a_loaded((THEIRS,), pulls)
    return ParseMember(
        row=a_parse_row(code),
        run=theirs.run,
        auras=PlayerAuras(
            actor_id=THEIRS.actor_id, on_self=(an_aura(band_ms, band_start_ms),)
        ),
    )


def a_parse_member_without_auras(code: str) -> ParseMember:
    """A reference whose aura query never came back, which is a real state."""
    theirs = a_loaded((THEIRS,), (a_pull_of(0, (9,), 60.0, boss=True),))
    return ParseMember(row=a_parse_row(code), run=theirs.run)


def a_run_with_a_two_minute_boss() -> LoadedRun:
    return a_loaded((OURS,), (a_pull_of(0, (9,), 120.0, boss=True),))


OUR_UPTIME = PlayerAuras(actor_id=OURS.actor_id, on_self=(an_aura(30_000),))


def test_an_aura_row_is_a_share_of_boss_time_on_both_sides() -> None:
    """Thirty seconds of a two-minute boss pull is a quarter of it, and the
    sample's three boss-fighting references carried it over 0.75, 0.6 and 0.95 of
    theirs. Every one of those is a division by a different denominator, so none
    of them is the band length that produced it."""
    sample = ParseSample(
        members=(
            an_aura_parse_member("REF1", 60.0, 45_000),
            an_aura_parse_member("REF2", 90.0, 54_000),
            an_aura_parse_member("REF3", 60.0, 57_000),
            # Aura data but no boss pull: there is no boss time to take a share
            # of, so this reference carries nothing rather than dividing by zero.
            an_aura_parse_member("REF4", 60.0, 45_000, fought_a_boss=False),
            # No aura data at all, so not an eligible member of the sample.
            a_parse_member_without_auras("REF5"),
            # The aura was up, but never while this reference was on a boss,
            # which reads the same as never having carried it. Counted as a
            # zero, it would pull the median down to 0.675.
            an_aura_parse_member("REF6", 60.0, 30_000, band_start_ms=100_000),
        )
    )

    measures = comparison_measures(
        a_run_with_a_two_minute_boss(), only_ours(sample, our_auras=OUR_UPTIME)
    )[OUR_SLUG]

    auras = {m.name: m for m in measures.auras}
    assert auras["Arcane Power"].ours == 0.25
    assert auras["Arcane Power"].their_median == 0.75
    assert auras["Arcane Power"].their_fractions == (0.75, 0.6, 0.95)
    assert auras["Arcane Power"].verdict is Verdict.BELOW


def test_no_aura_row_when_our_own_side_returned_none() -> None:
    """Our own aura query may never have been issued, and a comparison with one
    side missing states a single reference rather than a statistic. One reference
    has no median, so there is nothing for an aura row to hold."""
    sample = ParseSample(
        members=tuple(an_aura_parse_member(c, 60.0, 45_000) for c in ("REF1", "REF2", "REF3"))
    )

    measures = comparison_measures(a_run_with_a_two_minute_boss(), only_ours(sample))[OUR_SLUG]

    assert measures.auras == ()


RATE_FAMILIES = (
    "compare.spells.rate.",
    "compare.spells.above.",
    "compare.spells.trash.rate.",
    "compare.spells.trash.above.",
)
"""The sample rate families: both directions of both stretches.

Matching one of these prefixes is not on its own a promise that the row states
a median. `compare_spells_sample` falls back to a pairwise comparison below
`MIN_SAMPLE_FOR_AGGREGATE`, and `too_few` leaves the id untouched, so a
below-floor row is still `compare.spells.rate.<rank>` while its facts read
`Reference` rather than `Reference median` and no median was ever drawn. No
prefix can separate the two. `tables._boss` returns nothing for that same
sample, both sides behaving exactly as designed, so a caller that pairs rows
with table entries would meet a missing entry rather than a drift.

A caller that may be handed a below-floor sample must therefore check
`can_aggregate` itself; the tests here use samples large enough to aggregate,
and the end-to-end test asserts it.
"""


def stretch_of(finding: Finding) -> Stretch:
    """Which denominator a rate row was drawn over, from the family it belongs to.

    The finding does not carry a `Stretch`, and one ability id is routinely
    measured on both — a button pressed on the boss and on the packs owns a
    row in each table. Without this, a boss row could be checked against the
    trash figure for the same button, with neither of them wrong.
    """
    return Stretch.TRASH if finding.id.startswith("compare.spells.trash.") else Stretch.BOSS


def family_of(finding: Finding) -> str:
    """The `RATE_FAMILIES` prefix a rate row belongs to.

    The four prefixes are disjoint — none is a prefix of another — so the first
    match is the only match.
    """
    return next(family for family in RATE_FAMILIES if finding.id.startswith(family))


def below_the_aligned_trash_floor(ours: LoadedRun, sample: ParseSample) -> tuple[str, ...]:
    """Codes that shared trash with our route, but too little of it to be compared.

    Deliberately not `is_comparable`'s complement: a reference that shared no
    trash at all fails that too, and is a different kind of member. This names
    only the shape that makes the floor itself decide something.
    """
    codes = []
    for member in sample.members:
        aligned = aligned_trash(ours.run, member.run)
        if aligned.their_seconds > 0 and not is_comparable(aligned):
            codes.append(member.row.report_code)
    return tuple(codes)


def without_boss_seconds(sample: ParseSample) -> tuple[str, ...]:
    """Codes whose boss pulls add up to no time at all to measure a rate over."""
    return tuple(
        member.row.report_code for member in sample.members if boss_seconds(member.run) <= 0
    )


def carried_only_outside_boss_pulls(sample: ParseSample) -> tuple[str, ...]:
    """Codes carrying an aura whose bands never overlap one of their own boss pulls."""
    codes = []
    for member in sample.members:
        if member.auras is None or not member.auras.on_self:
            continue
        windows = boss_windows(member.run)
        if all(uptime_seconds_in(aura, windows) <= 0 for aura in member.auras.on_self):
            codes.append(member.row.report_code)
    return tuple(codes)


def fact_value(finding: Finding, label: str) -> str:
    """The value of one labelled fact, which is where a row states a figure unambiguously.

    A title states both figures in one sentence, so a bare substring found
    there could be either of them — and a row that had swapped the two would
    still contain both. The label says which figure is which.
    """
    return next(fact.value for fact in finding.facts if fact.label == label)


def a_boss_and_trash_member(
    code: str,
    *,
    trash_seconds: float,
    boss_seconds: float,
    trash_blasts: int,
    trash_meteors: int,
    boss_meteors: int,
    boss_blasts: int,
) -> ParseMember:
    """A reference our route shares a pack with, who also fought the boss.

    Both stretches on one member, so a single sample reaches the boss builder
    and the trash builder together. Both abilities are cast on both stretches,
    which is what a real run does: a button pressed on the packs and on the
    boss owns a row in each table under one id, and a figure asserted about one
    stretch must not be reachable from the other's row.
    """
    theirs = a_loaded(
        (THEIRS,),
        (a_pull_of(0, (1,), trash_seconds), a_pull_of(1, (9,), boss_seconds, boss=True)),
        casts=(
            casts_on(THEIRS.actor_id, ARCANE_BLAST, "Arcane Blast", 0, trash_blasts)
            + casts_on(THEIRS.actor_id, METEOR, "Meteor", 0, trash_meteors)
            + casts_on(THEIRS.actor_id, METEOR, "Meteor", 1, boss_meteors)
            + casts_on(THEIRS.actor_id, ARCANE_BLAST, "Arcane Blast", 1, boss_blasts)
        ),
    )
    return ParseMember(row=a_parse_row(code), run=theirs.run, casts=theirs.casts)


def a_member_whose_boss_pull_has_no_duration(code: str) -> ParseMember:
    """A reference whose boss pull was recorded with no duration, and holds casts in it.

    The shape that makes `_boss`'s `their_boss_seconds <= 0` guard decide
    something. A reference that simply fought no boss does not: `boss_casts`
    scopes to the boss pull indices, so with none it counts nothing and the
    guarded and unguarded paths reach the same empty result by different
    roads. Here the pull exists, so its casts are counted, and only the guard
    stops them becoming a rate over zero seconds.
    """
    theirs = a_loaded(
        (THEIRS,),
        (a_pull_of(0, (9,), 0.0, boss=True),),
        casts=casts_on(THEIRS.actor_id, METEOR, "Meteor", 0, 5),
    )
    return ParseMember(row=a_parse_row(code), run=theirs.run, casts=theirs.casts)


def a_run_with_a_boss_and_a_shared_pack() -> LoadedRun:
    """Our run: a 90s pack and a 120s boss, both abilities pressed on each.

    Our four rates are 2.0 and 6.0 a minute on the pack, 1.5 and 9.0 on the
    boss. Neither denominator is a minute, so none of them is the cast count
    that produced it and no assertion below survives deleting the division.
    """
    return a_loaded(
        (OURS,),
        (a_pull_of(0, (1,), 90.0), a_pull_of(1, (9,), 120.0, boss=True)),
        casts=(
            casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 0, 3)
            + casts_on(OURS.actor_id, METEOR, "Meteor", 0, 9)
            + casts_on(OURS.actor_id, METEOR, "Meteor", 1, 3)
            + casts_on(OURS.actor_id, ARCANE_BLAST, "Arcane Blast", 1, 18)
        ),
    )


def a_sample_reaching_every_rate_family() -> ParseSample:
    """A sample that puts one row in each of the four rate families.

    Against `a_run_with_a_boss_and_a_shared_pack`, the medians are Arcane Blast
    6.0 a minute on trash and 3.0 on bosses, Meteor 2.0 on trash and 9.0 on
    bosses. Set against our own 2.0, 9.0, 6.0 and 1.5 that is one row below and
    one above on each stretch, which is what reaches both directions of both
    families.

    The last two members are the awkward ones, and they are what make a change
    to *which* members the table counts visible rather than only a change to
    how it divides. One shares half the aligned-trash floor, so `is_comparable`
    drops it from the trash stretch while it stays an ordinary member of the
    boss stretch; counted, its 30.0 a minute would carry the trash Arcane Blast
    median to 9.0 and the Meteor median to 7.0. Its boss rates deliberately sit
    on both boss medians, so admitting it changes nothing there and a trash
    failure cannot be mistaken for a boss one. The other has a boss pull of no
    duration holding casts, which is the one shape the boss stretch's own
    membership guard decides anything about.

    Both are tied to the thing that makes them awkward rather than described
    beside it: `test_the_awkward_members_stay_awkward` holds each to its own
    guard, so neither can quietly become an ordinary member if a floor moves.
    """
    return ParseSample(
        members=(
            # Trash 3.0 and 2.0 a minute; boss 2.0 and 2.0.
            a_boss_and_trash_member(
                "REF1", trash_seconds=120.0, boss_seconds=90.0,
                trash_blasts=6, trash_meteors=4, boss_meteors=3, boss_blasts=3,
            ),
            # Trash 6.0 and 2.0; boss 9.0 and 3.0 — on the median of both.
            a_boss_and_trash_member(
                "REF2", trash_seconds=150.0, boss_seconds=60.0,
                trash_blasts=15, trash_meteors=5, boss_meteors=9, boss_blasts=3,
            ),
            # Trash 12.0 and 12.0; boss 16.0 and 6.0.
            a_boss_and_trash_member(
                "REF3", trash_seconds=65.0, boss_seconds=30.0,
                trash_blasts=13, trash_meteors=13, boss_meteors=8, boss_blasts=3,
            ),
            # Below the aligned-trash floor: compared on the boss, not on trash.
            a_boss_and_trash_member(
                "REF4",
                trash_seconds=MIN_ALIGNED_TRASH_SECONDS / 2,
                boss_seconds=60.0,
                trash_blasts=15, trash_meteors=15, boss_meteors=9, boss_blasts=3,
            ),
            # The second awkward member, for the boss stretch's own membership
            # guard. It contributes no rate either way; what it decides is
            # whether its casts are divided by its zero seconds.
            a_member_whose_boss_pull_has_no_duration("REF5"),
        )
    )


def test_every_rate_finding_has_a_table_row_stating_the_same_figures() -> None:
    """The property the table's honesty rests on, on both stretches.

    A rate row and a table row are two projections of one `AbilityRate`, so
    this cannot fail while that holds. What it is worth pinning against is the
    case that breaks it: `tables` builds its own per-member input for each
    stretch, mirroring the finding builder rather than sharing it, and a drift
    between either pair would move a median under a row that never stated it.
    Nothing else in the suite puts the two side by side.
    """
    ours = a_run_with_a_boss_and_a_shared_pack()
    subjects = only_ours(a_sample_reaching_every_rate_family())

    findings = compare(ours, None, subjects)
    measures = comparison_measures(ours, subjects)[OUR_SLUG]

    by_row = {(m.stretch, m.ability_id): m for m in measures.boss + measures.trash}
    rate_rows = [f for f in findings if f.id.startswith(RATE_FAMILIES)]
    # All four families, or the fixture has stopped reaching one of them and
    # the loop below would pass on whichever survived. Both stretches, because
    # each has a mirrored builder of its own; both directions, because the
    # above rows are built separately from the gap rows and nothing else
    # offline holds their fact labels to anything.
    assert {family_of(f) for f in rate_rows} == set(RATE_FAMILIES)

    for finding in rate_rows:
        # By id, never by name: a name can belong to more than one game id, and
        # a run's aura table really does carry several such pairs with figures
        # of their own.
        assert finding.ability_id is not None
        measured = by_row[(stretch_of(finding), finding.ability_id)]
        assert finding.ability_name == measured.name
        assert fact_value(finding, "Ours") == f"{measured.ours:.1f} casts a minute"
        assert fact_value(finding, "Reference median") == (
            f"{measured.their_median:.1f} casts a minute"
        )
        # The sentence a reader actually reads, not only the panel beside it.
        assert f"{measured.ours:.1f}" in finding.title
        assert f"{measured.their_median:.1f}" in finding.title


A_SHORT_REFERENCE_BOSS = 60.0
"""How long the boss pull runs for a reference built at this length.

`an_aura_parse_member` starts every boss pull at zero, so a band beginning
after this has ended never overlaps one. Named rather than written twice, so
the band below cannot drift back inside the window it is meant to sit outside.
"""


def a_sample_carrying_an_aura_unevenly() -> ParseSample:
    """Three references carrying an aura across their boss time, and one that did not.

    The three sit at 0.75, 0.6 and 0.95 of their own boss pulls, each a
    division by a different denominator, so no fraction is the band length that
    produced it. Their median is 0.75 against our own 0.25.

    The fourth is the awkward one, and what makes a change to which members the
    aura table counts visible rather than only a change to how it divides. It
    carried the aura, but never while it was on a boss, which reads the same as
    never having carried it at all. Counted as a zero it would drag the median
    to 0.675.
    """
    return ParseSample(
        members=(
            an_aura_parse_member("REF1", A_SHORT_REFERENCE_BOSS, 45_000),
            an_aura_parse_member("REF2", 90.0, 54_000),
            an_aura_parse_member("REF3", A_SHORT_REFERENCE_BOSS, 57_000),
            an_aura_parse_member(
                "REF4",
                A_SHORT_REFERENCE_BOSS,
                30_000,
                band_start_ms=int(A_SHORT_REFERENCE_BOSS * 1000) + 1_000,
            ),
        )
    )


def test_the_awkward_members_stay_awkward() -> None:
    """The membership coverage the two samples add, pinned so it cannot evaporate.

    Each sample carries members that exist only to make a membership guard
    decide something, and each is awkward by a hair. A floor moving, a literal
    drifting, or an aura band sliding back inside a boss pull would make them
    ordinary again — and then the membership mutations would pass unnoticed,
    the net would be back to catching arithmetic alone, and nothing would fail
    to say so. This is what fails instead.
    """
    rates = a_sample_reaching_every_rate_family()
    ours = a_run_with_a_boss_and_a_shared_pack()

    # Equality, not membership: it pins that the others are ordinary just as
    # much as that these two are not.
    assert below_the_aligned_trash_floor(ours, rates) == ("REF4",)
    assert without_boss_seconds(rates) == ("REF5",)
    assert carried_only_outside_boss_pulls(a_sample_carrying_an_aura_unevenly()) == ("REF4",)


def test_every_uptime_finding_has_a_table_row_stating_the_same_figures() -> None:
    """The same property for the third measure, which is built the same way.

    An aura table is `tables._auras` mirroring `uptime._gap_findings_sample`'s
    own member loop, so it can drift from the rows exactly as the two rate
    builders can. Uptimes are shares rather than rates, and a row spells them
    as whole percents, which is the figure a reader would have to reconcile.
    """
    ours = a_run_with_a_two_minute_boss()
    subjects = only_ours(a_sample_carrying_an_aura_unevenly(), our_auras=OUR_UPTIME)

    findings = compare(ours, None, subjects)
    measures = comparison_measures(ours, subjects)[OUR_SLUG]

    by_aura = {m.ability_id: m for m in measures.auras}
    gaps = [f for f in findings if f.id.startswith("compare.uptime.self.")]
    assert gaps, "no uptime finding to check against"

    for finding in gaps:
        assert finding.ability_id is not None
        measured = by_aura[finding.ability_id]
        assert finding.ability_name == measured.name
        assert fact_value(finding, "Ours") == f"{measured.ours:.0%} of boss time"
        assert fact_value(finding, "Reference median") == (
            f"{measured.their_median:.0%} of boss time"
        )
        assert f"{measured.ours:.0%}" in finding.title
        assert f"{measured.their_median:.0%}" in finding.title
