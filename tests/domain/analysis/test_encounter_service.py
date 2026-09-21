# ABOUTME: The raid analyser list, and which claims a boss fight can support.
# ABOUTME: What is absent here matters as much as what is present.

from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.comparison.raid_reference import (
    RaidParseRow,
    RankedPlayer,
    ReportRankings,
)
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.targets import TargetRow
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, Resurrection
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
from wowperf.domain.phases import Phase, PhaseTransition
from wowperf.domain.report.players import slugs_by_actor
from wowperf.domain.season import Consumables, DefensiveAbility, Defensives, Roles

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=235450, name="Prismatic Barrier", cooldown_seconds=30.0
                ),
            ),
        ),
    )
)

NO_DEFENSIVES = Defensives(entries=())
NO_CONSUMABLES = Consumables()


def a_loaded_encounter(**overrides: object) -> LoadedEncounter:
    encounter = Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=375_000,
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=700),
        ),
    )
    fields: dict[str, object] = {"encounter": encounter}
    fields.update(overrides)
    return LoadedEncounter(**fields)  # type: ignore[arg-type]


def test_a_fight_with_nothing_in_it_produces_nothing() -> None:
    """An empty fight invents nothing it lacks data for.

    Every claim this service can make needs evidence an empty fight has none
    of: a death, a landed or kicked enemy cast, a consumable, or a ceiling
    computed from an actual cast. With no casts there is no ceiling to judge
    and nothing else to report, so the honest answer is silence.
    """
    findings = analyse_encounter(a_loaded_encounter(), DEFENSIVES, Consumables())

    assert findings == [], f"an empty fight has no evidence for: {[f.id for f in findings]}"


def test_a_death_is_reported_and_located_against_the_fight() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())

    assert findings, "a death must produce a finding"
    # This fixture presses nothing and both defensives analysers gate on a cast,
    # so the only findings here are deaths.total and deaths.single.0 -- one
    # family, both carrying the same 3.0s, which rank_raid_findings scores
    # identically. Nothing in the ranking separates them; the order is the one
    # analyse_deaths emitted, held by a stable sort, and it builds the total
    # before appending the singles.
    assert findings[0].id == "deaths.total"
    assert any("The Twin Fangs" in line for line in findings[0].evidence)
    assert not any("pull" in line for f in findings for line in f.evidence)
    # A boss fight has no timer penalty and no time decomposition to point a
    # reader at -- decompose_time is deliberately absent from analyse_encounter.
    assert "timer penalty" not in findings[0].detail
    assert "time decomposition" not in findings[0].detail


def test_the_defensive_ceiling_uses_fight_duration_and_therefore_fires() -> None:
    """The regression this whole slice guards against.

    Under the rejected design -- a Run holding one degenerate pull -- the
    ceiling denominator was zero and this finding disappeared in silence.

    Prismatic Barrier (235450, 30s cooldown -- data/defensives.toml:139) is used
    rather than Ice Block: in a 374s fight Ice Block's 240s cooldown yields a
    ceiling of 1.56, below `MIN_CEILING_USES = 3.0`, so the finding would be
    suppressed regardless of fight duration and prove nothing about this
    regression. Prismatic Barrier's ceiling is 374 / 30 = 12.5.
    """
    casts = (
        CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000, pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(casts=casts), DEFENSIVES,
                                 Consumables())

    ceiling = [f for f in findings if f.id.startswith("defensives.ceiling")]
    assert ceiling, "one Prismatic Barrier cast in a 374s fight is below its ceiling"
    assert ceiling[0].confidence is Confidence.INFERRED


def test_no_keystone_shaped_finding_reaches_a_raid_report() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())
    assert findings, "the guard below proves nothing against an empty list"
    forbidden = ("time.residual", "time.gap", "trash.", "compare.route")
    leaked = [f.id for f in findings if f.id.startswith(forbidden)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"


ROLES = Roles(tanks=("Warrior/Protection",))

RAID = (
    Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=12, name="Stonewake", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=13, name="Bríala", class_name="Mage", spec="Arcane", item_level=700),
)

RAID_SLUGS = slugs_by_actor(RAID)
"""Every `RAID` member's fragment id, minted the one way `cli.py` mints one."""


def a_raid_encounter() -> Encounter:
    """Three players and a 120-second fight, so a median has three takers."""
    return Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=121_000,
        players=RAID,
    )


def took(actor_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=400, ability_name="Ravenous Feast",
        amount=amount, timestamp_ms=2_000,
    )


def test_the_outlier_finding_now_reaches_a_raid_report() -> None:
    # `roles` stopped being inert with this plan: the outlier half of
    # `analyse_players` is the one piece of it a boss fight supports.
    loaded = a_loaded_encounter(
        encounter=a_raid_encounter(),
        damage_taken=(took(11, 400), took(12, 100), took(13, 100)),
    )
    findings = analyse_encounter(loaded, DEFENSIVES, Consumables(), roles=ROLES)
    assert any(finding.id.startswith("players.damage.") for finding in findings)


def test_a_mechanic_outranks_a_defensive_though_neither_costs_seconds() -> None:
    """Severity, and only severity, can produce this order.

    Both families carry `seconds_lost=None`, and `analyse_encounter` appends
    defensives long before mechanics, so under `rank_findings` the sort is
    stable and defensives come first. Deaths would have been the wrong pair to
    test with: a raid death does carry seconds, so `rank_findings` already
    sorts it above a mechanic and the assertion could not have failed.

    The defensive half brings its own `Defensives` rather than the module's.
    A ceiling finding fires only below `CEILING_USE_FRACTION` of what the
    cooldown allowed, and this 120s fight fits the module's 30s cooldown four
    times: one press against a ceiling of 4 reads as ordinary play, and no
    press count clears the fraction at a ceiling that small. At 20s the
    ceiling is 6, and the single press below is 1 of 6.
    """
    defensives = Defensives(
        entries=(
            (
                "Mage/Arcane",
                (DefensiveAbility(ability_id=235450, name="Prismatic Barrier",
                                  cooldown_seconds=20.0),),
            ),
        )
    )
    casts = (
        CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000),
    )
    sample = MechanicsSample(
        members=(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ref", fight_id=1, size=20,
                    duration_ms=120_000, deaths=0,
                ),
                abilities=(),
            ),
        )
    )
    ours = (
        AbilityTakenRow(
            ability_id=400, ability_name="Ravenous Feast", hit_count=12,
            source_types=("Boss",),
        ),
    )
    findings = analyse_encounter(
        a_loaded_encounter(encounter=a_raid_encounter(), casts=casts),
        defensives, Consumables(), roles=ROLES,
        mechanics=sample, our_abilities=ours,
    )
    families = [finding.id.split(".", 1)[0] for finding in findings]
    assert "mechanics" in families, "the fixture must produce a mechanics finding"
    assert "defensives" in families, "the fixture must produce a defensives finding"
    assert families.index("mechanics") < families.index("defensives")

    # `scope` names who took the landings, not the encounter: "the raid", never
    # the boss. `compare_mechanics`'s title opens "{scope} took {ability} ...",
    # so a `scope` of the boss name would have this read as the boss taking its
    # own damage -- exactly the slip this pins against returning silently.
    [mechanics_finding] = [finding for finding in findings if finding.id.startswith("mechanics")]
    assert mechanics_finding.title.startswith("the raid")
    assert "Twin Fangs" not in mechanics_finding.title


ARCANE_BLAST = 30451

OUR_CASTS = tuple(
    CastEvent(actor_id=11, ability_id=ARCANE_BLAST, ability_name="Arcane Blast",
              timestamp_ms=2_000 + one * 1_000)
    for one in range(10)
)
"""Ten casts for the subject, and none for anybody else on the roster.

Over the fixture encounter's own 374 seconds that is 1.6 a minute. Over any
other denominator a wiring mistake could reach for -- 300, 120, a pull's length,
zero -- it is a different figure or no finding at all, which is what makes the
rate row below an assertion about what `analyse_encounter` passed."""


def a_ranked_player(amount: float, rank_percent: int, name: str = "Emberkin") -> RankedPlayer:
    return RankedPlayer(
        character_name=name, class_name="Mage", spec="Arcane", role="dps",
        amount=amount, rank="~1200", best="~900", rank_percent=rank_percent,
        bracket_percent=rank_percent, total_parses=4_100,
    )


def a_standing(amount: float, rank_percent: int) -> ReportRankings:
    return ReportRankings(
        fight_id=22, difficulty=4, partition=1, size=20, kill=True,
        players=(a_ranked_player(amount, rank_percent),),
    )


def a_board(amounts: tuple[float, ...]) -> tuple[RaidParseRow, ...]:
    return tuple(
        RaidParseRow(
            report_code=f"BOARD{one}", fight_id=one + 1, duration_ms=240_000,
            character_name="Stonewake", class_name="Mage", spec="Arcane",
            amount=amount,
        )
        for one, amount in enumerate(amounts)
    )


def a_parse_member(report_code: str, blasts: int) -> ParseMember:
    return ParseMember(
        character_name="Stonewake",
        report_code=report_code,
        fight_id=1,
        boss_seconds=240.0,
        players=(
            Player(actor_id=90, name="Stonewake", class_name="Mage", spec="Arcane",
                   item_level=710),
        ),
        casts=tuple(
            CastEvent(actor_id=90, ability_id=ARCANE_BLAST, ability_name="Arcane Blast",
                      timestamp_ms=one * 1_000)
            for one in range(blasts)
        ),
    )


def a_parse_subject(**overrides: object) -> ParseSubject:
    """The subject as the adapter layer hands it over, with a full sample by default."""
    fields: dict[str, object] = {
        "player": RAID[0],
        "slug": RAID_SLUGS[RAID[0].actor_id],
        "display_name": "Emberkin",
        "sample": ParseSample(
            members=tuple(a_parse_member(f"REF{one}", 14) for one in range(5))
        ),
        "board": a_board((1_600_000.0, 1_720_000.0, 1_540_000.0, 1_880_000.0, 1_490_000.0)),
        "boss_board": a_board((1_310_000.0, 1_402_000.0, 1_255_000.0, 1_520_000.0, 1_190_000.0)),
        "our_targets": (
            TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=880_000_000),
            TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=120_000_000),
        ),
        "their_targets": tuple(
            (
                TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=470_000_000),
                TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=30_000_000),
            )
            for _ in range(5)
        ),
    }
    fields.update(overrides)
    return ParseSubject(**fields)  # type: ignore[arg-type]


def test_the_external_frame_joins_the_internal_one_over_this_fights_own_seconds() -> None:
    """The wiring this task exists for, asserted through a figure only it produces.

    The rate row is stated over the fight's own duration and the subject's own
    cast stream, both of which reach `compare_parse_axis` from `analyse_encounter`
    and from nowhere else -- so a call handing it an empty stream, a zero
    denominator or another player's casts changes this number or removes the row.
    """
    loaded = a_loaded_encounter(casts=OUR_CASTS, standing=a_standing(1_450_000.0, 62),
                                boss_standing=a_standing(1_180_000.0, 48))
    findings = analyse_encounter(
        loaded, DEFENSIVES, Consumables(), parse_subjects=(a_parse_subject(),)
    )
    ids = [finding.id for finding in findings]
    slug = RAID_SLUGS[RAID[0].actor_id]

    assert f"compare.damage.total.{slug}" in ids
    assert f"compare.damage.targets.{slug}" in ids
    assert f"compare.rank.{slug}" in ids
    [rate] = [one for one in findings if one.id.startswith("compare.spells.rate")]
    # 10 casts over the encounter's own 374 seconds, against the sample's 3.5.
    assert "1.6" in rate.title, rate.title
    assert "ours over 374s of the fight" in rate.evidence


def test_the_frame_is_withheld_on_a_wipe_without_the_internal_frame_going_with_it() -> None:
    """Design 15's reason for building the internal frame first."""
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    loaded = a_loaded_encounter(casts=OUR_CASTS, deaths=deaths, standing=None,
                                boss_standing=None)
    findings = analyse_encounter(
        loaded, DEFENSIVES, Consumables(), parse_subjects=(a_parse_subject(),)
    )
    ids = [finding.id for finding in findings]
    unavailable_id = f"compare.parse.unavailable.{RAID_SLUGS[RAID[0].actor_id]}"

    assert "deaths.total" in ids, "the internal frame went with the external one"
    assert unavailable_id in ids
    assert [one for one in ids if one.startswith("compare.")] == [unavailable_id]


def test_a_fight_with_no_subjects_named_emits_no_comparison_at_all() -> None:
    """`--no-compare` reaches here as an empty sequence, and must stay silent.

    Not an absence to fill in: a subject nobody asked to compare has no sample,
    no board and no target table, and every sentence this axis writes would be
    about a query that was never issued.
    """
    loaded = a_loaded_encounter(casts=OUR_CASTS, standing=a_standing(1_450_000.0, 62))
    findings = analyse_encounter(loaded, DEFENSIVES, Consumables())

    assert not [one for one in findings if one.id.startswith("compare.")]


def test_every_named_subject_gets_their_own_row_of_each_family() -> None:
    """`--all-players` reaches here as several subjects, and each is measured.

    A loop that compared only the first would pass every assertion above.
    """
    loaded = a_loaded_encounter(casts=OUR_CASTS, standing=a_standing(1_450_000.0, 62))
    subjects = (
        a_parse_subject(),
        a_parse_subject(
            player=RAID[1], display_name="Stonewake", slug=RAID_SLUGS[RAID[1].actor_id]
        ),
    )
    findings = analyse_encounter(
        loaded, DEFENSIVES, Consumables(), parse_subjects=subjects
    )

    ranks = [
        one for one in findings if one.id == f"compare.rank.{RAID_SLUGS[RAID[0].actor_id]}"
    ]
    assert len(ranks) == 1, "only one roster member is in this fixture's rankings row"
    unavailable = [
        one for one in findings
        if one.id == f"compare.rank.unavailable.{RAID_SLUGS[RAID[1].actor_id]}"
        and "Stonewake" in one.title
    ]
    assert unavailable, "the second subject was never compared at all"


def a_two_raider_encounter(
    names: tuple[str, str] = ("Emberkin", "Stonewake"),
) -> tuple[Encounter, LoadedEncounter]:
    """Two roster members, both specced and both ranked.

    Neither subject's comparison may short-circuit into an unavailable finding:
    both carry a spec, the fight killed the boss, and both names are in the
    rankings row `compare_rank` and `compare_damage_total` join against.
    """
    players = (
        Player(actor_id=11, name=names[0], class_name="Mage", spec="Arcane", item_level=700),
        Player(actor_id=12, name=names[1], class_name="Mage", spec="Arcane", item_level=700),
    )
    encounter = Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=121_000,
        players=players,
    )
    standing = ReportRankings(
        fight_id=22, difficulty=4, partition=1, size=20, kill=True,
        players=tuple(a_ranked_player(1_450_000.0, 62, name=name) for name in names),
    )
    casts = tuple(
        CastEvent(actor_id=player.actor_id, ability_id=ARCANE_BLAST,
                  ability_name="Arcane Blast", timestamp_ms=2_000 + one * 1_000)
        for player in players
        for one in range(10)
    )
    loaded = a_loaded_encounter(
        encounter=encounter, casts=casts, standing=standing, boss_standing=standing,
    )
    return encounter, loaded


def two_comparable_subjects(encounter: Encounter) -> tuple[ParseSubject, ...]:
    """Both roster members, each with a parse sample thick enough to compare for real.

    Slugs come from `slugs_by_actor`, exactly as `cli.py`'s `_parse_samples`
    mints them -- never from the display name, which is the whole point of
    the third test this helper feeds.
    """
    sample = ParseSample(members=tuple(a_parse_member(f"REF{one}", 14) for one in range(5)))
    assert sample.members, "the fixture produced no parse sample to compare against"
    slugs = slugs_by_actor(encounter.players)
    return tuple(
        ParseSubject(
            player=player,
            slug=slugs[player.actor_id],
            display_name=player.name,
            sample=sample,
        )
        for player in encounter.players
    )


def test_two_raiders_compared_at_once_never_share_a_finding_id() -> None:
    """Under `--all-players` each subject's comparison is its own row.

    Two subjects reach `compare_parse_axis` through the same loop, and the
    comparison modules know nothing about who else is in the raid -- they mint
    `compare.talents` and the loop appends the player. Without that the two
    calls return the identical id twice, `build_raid_report` refuses the list,
    and the page could not key an element id on one anyway.
    """
    encounter, loaded = a_two_raider_encounter()
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    ids = [f.id for f in compared]
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)


def test_every_compared_finding_names_the_raider_it_is_about() -> None:
    """The slug is a field as well as a suffix, because two consumers read it.

    `RAID_COMPARISON_PREFIXES` routes a row to a card by `player_slug`, and the
    page anchors `#finding-...` on the id. A suffix with no field leaves the
    first consumer matching nothing, and a field with no suffix leaves the
    second with duplicate element ids.
    """
    encounter, loaded = a_two_raider_encounter()
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    slugs = {subject.slug for subject in subjects}
    for finding in compared:
        assert finding.player_slug in slugs, finding.id
        assert finding.id.endswith(f".{finding.player_slug}"), finding.id


def test_two_raiders_whose_names_reduce_to_one_slug_stay_apart() -> None:
    """The defect the last whole-branch review found, at the layer above it.

    Plan 3a joined a rankings row on a disambiguated display name and told a
    duplicate-named raider their kill was not a kill. The same two raiders
    reach this loop, and here the failure would be quieter: both cards would
    draw the same rows under two names.
    """
    encounter, loaded = a_two_raider_encounter(names=("Bríala", "Briala"))
    subjects = two_comparable_subjects(encounter)

    findings = analyse_encounter(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, parse_subjects=subjects
    )

    compared = [f for f in findings if f.id.startswith("compare.")]
    assert compared, "the fixture produced no comparison findings to distinguish"
    ids = [f.id for f in compared]
    assert len(ids) == len(set(ids))
    assert len({f.player_slug for f in compared}) == 2


def _mechanics_sample() -> MechanicsSample:
    """One reference kill, below `MIN_SAMPLE_FOR_AGGREGATE`, matching the shape
    `test_a_mechanic_outranks_a_defensive_though_neither_costs_seconds` above
    already builds inline -- named here because the two tests below need it
    twice. `deaths=1` is what `classify_attempt` reads back as the reference
    median death count.
    """
    return MechanicsSample(
        members=(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ref", fight_id=1, size=20,
                    duration_ms=120_000, deaths=1,
                ),
                abilities=(),
            ),
        )
    )


def _loaded_wipe_with(deaths: int, resurrected: int = 0) -> LoadedEncounter:
    """A wipe with `deaths` of a 20-player raid dead, `resurrected` of them back up.

    At 14, that clears `classify_attempt`'s own `DISMANTLED_SHARE` of one
    half, so a verdict fires. `boss_percentage` is set outright rather than
    left at its `None` default: `classify_attempt` withholds a verdict
    whenever it reads `None`, and a wipe fixture must not do that by omission.

    Every resurrection lands after every death this builds, so `resurrected`
    raiders are standing when the attempt ends.
    """
    death_events = tuple(
        Death(
            actor_id=index,
            player_name=RAID[index % len(RAID)].name,
            timestamp_ms=60_000 + (index - 1) * 30_000,
            killing_blow="Ravenous Feast",
            killing_blow_id=400,
        )
        for index in range(1, deaths + 1)
    )
    back_up = tuple(
        Resurrection(
            actor_id=index,
            caster_id=19,
            ability_id=20484,
            ability_name="Rebirth",
            timestamp_ms=60_000 + deaths * 30_000,
        )
        for index in range(1, resurrected + 1)
    )
    encounter = Encounter(
        report_code="wipe1", fight_id=5, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=False, boss_percentage=60.0, start_ms=1_000, end_ms=500_000,
        players=(),
    )
    return LoadedEncounter(encounter=encounter, deaths=death_events, resurrections=back_up)


PHASED_ABILITY = 400

PHASED_ABILITIES_TAKEN = (
    AbilityTakenRow(
        ability_id=PHASED_ABILITY, ability_name="Ravenous Feast", hit_count=4,
        source_types=("Boss",),
    ),
)
"""Our own `viewBy: Ability` row for the ability the fixture's events carry.

The id is the join the phase label depends on, and the two sides of it come
from two different API surfaces: this table has no timestamps, the event stream
has no landing count. Spelled from one constant so the fixture cannot pass by
comparing an ability against itself under two different ids -- and `hit_count`
matches the number of events below, so the landings the comparison states and
the landings the phase share is drawn from are the same four.
"""


def _loaded_wipe_with_phases() -> LoadedEncounter:
    """A fight whose encounter carries named phases and a transition list.

    Gates `compare_phase_cost` on `Encounter.phases` rather than on
    `separatesWipes` -- the global constraint measured 2026-09-18 across 8
    encounters, 3 of which read `separatesWipes` false while still naming
    phases.

    Its damage events fall in both phases, three of four in Stage Two, so the
    dominant phase is a choice a wrong join could get wrong rather than the
    only phase on offer.
    """
    phases = (
        Phase(id=1, name="Stage One: Something"),
        Phase(id=2, name="Stage Two: Something Else"),
    )
    transitions = (
        PhaseTransition(id=1, start_ms=1_000),
        PhaseTransition(id=2, start_ms=61_000),
    )
    encounter = Encounter(
        report_code="wipe2", fight_id=6, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=False, boss_percentage=60.0, start_ms=1_000, end_ms=121_000,
        phases=phases, phase_transitions=transitions,
        players=(),
    )
    damage_taken = tuple(
        DamageTakenEvent(actor_id=1, ability_id=PHASED_ABILITY, ability_name="Ravenous Feast",
                         amount=500, timestamp_ms=when)
        for when in (30_000, 70_000, 80_000, 90_000)
    )
    return LoadedEncounter(encounter=encounter, damage_taken=damage_taken)


def test_a_wipe_reaches_a_lethal_finding_and_a_verdict() -> None:
    loaded = _loaded_wipe_with(deaths=14)

    ids = {finding.id for finding in analyse_encounter(loaded, DEFENSIVES, Consumables(),
                                                       mechanics=_mechanics_sample())}

    assert any(one.startswith("mechanics.lethal.") for one in ids)
    assert "wipe.cause" in ids


def test_the_resurrection_stream_reaches_the_verdict() -> None:
    """Two runs of one fixture, differing only in who came back.

    Five of twenty died. With four of them rezzed, nineteen were standing when
    the attempt ended, which is over `INTACT_SHARE` where fifteen is under it,
    so the verdict fires here and is withheld there. A call site that dropped
    `resurrections` would leave both runs silent, and silence is also what a
    fight with no verdict to give produces -- so only the pair can see it.
    """
    without = analyse_encounter(
        _loaded_wipe_with(deaths=5), DEFENSIVES, Consumables(), mechanics=_mechanics_sample()
    )
    with_rezzes = analyse_encounter(
        _loaded_wipe_with(deaths=5, resurrected=4), DEFENSIVES, Consumables(),
        mechanics=_mechanics_sample(),
    )

    assert "wipe.cause" not in {finding.id for finding in without}
    [verdict] = [finding for finding in with_rezzes if finding.id == "wipe.cause"]
    assert "19 of 20 were still alive" in verdict.detail, verdict.detail


def test_a_fight_with_phases_reaches_a_phase_finding() -> None:
    loaded = _loaded_wipe_with_phases()

    ids = {finding.id for finding in analyse_encounter(loaded, DEFENSIVES, Consumables(),
                                                       mechanics=_mechanics_sample())}

    assert any(one.startswith("mechanics.phase.") for one in ids)


def test_a_compared_ability_carries_the_phase_its_landings_fell_in() -> None:
    """The half of the phase work no fixture used to reach: the label on a comparison.

    Every fixture passing `our_abilities` carried no phases, and the one fixture
    with phases passed no `our_abilities`, so the two halves never met and
    `dominant_phase_by_ability` could be stubbed out of the service with the
    whole suite green. This is the only test that joins them, and the join it
    covers is a real one: the landing count comes from a `viewBy: Ability`
    table with no timestamps, the phase from an event stream with no landing
    count, and the ability id is all that holds them together.
    """
    loaded = _loaded_wipe_with_phases()

    findings = analyse_encounter(
        loaded, DEFENSIVES, Consumables(),
        mechanics=_mechanics_sample(), our_abilities=PHASED_ABILITIES_TAKEN,
    )

    [compared] = [one for one in findings if one.id.startswith("mechanics.ability.")]
    [label] = [fact for fact in compared.facts if fact.label == "Mostly in"]
    assert label.value == "Stage Two: Something Else", label.value
    assert label.confidence is Confidence.DERIVED
    assert "3 of 4 landings fell in Stage Two: Something Else" in compared.evidence, (
        compared.evidence
    )
