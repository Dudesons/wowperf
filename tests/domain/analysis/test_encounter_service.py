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
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
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


def test_a_fight_with_nothing_in_it_produces_only_never_cast_defensives() -> None:
    """An empty fight invents nothing it lacks data for -- but that is not `[]`.

    `analyse_defensives` states, once, that Prismatic Barrier was never cast --
    a real claim this fixture's zero casts support (`analyse_defensives`' never-
    cast branch emits it for every ability in a player's spec the player never
    pressed). What must stay absent is anything needing data an empty fight has
    none of: a death, a landed or kicked enemy cast, a consumable, or a
    ceiling computed from an actual cast.
    """
    findings = analyse_encounter(a_loaded_encounter(), DEFENSIVES, Consumables())

    assert findings, "an uncast defensive is a real, reportable claim, not silence"
    assert all(f.id.startswith("defensives.never.") for f in findings)
    forbidden = ("deaths.", "interrupts.", "consumables.", "defensives.ceiling.")
    leaked = [f.id for f in findings if f.id.startswith(forbidden)]
    assert leaked == [], f"needs data an empty fight does not have: {leaked}"


def test_a_death_is_reported_and_located_against_the_fight() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())

    assert findings, "a death must produce a finding"
    # deaths.total and defensives.never.* both reach rank_findings; deaths.total
    # carries a seconds_lost and defensives.never.* does not, so rank_findings'
    # (None-last) key puts it first deterministically, not by insertion luck.
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
    """
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
        a_loaded_encounter(encounter=a_raid_encounter()),
        DEFENSIVES, Consumables(), roles=ROLES,
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


def a_ranked_player(amount: float, rank_percent: int) -> RankedPlayer:
    return RankedPlayer(
        character_name="Emberkin", class_name="Mage", spec="Arcane", role="dps",
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
            amount=amount, size=20,
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

    assert "compare.damage.total" in ids
    assert "compare.damage.targets" in ids
    assert "compare.rank" in ids
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

    assert "deaths.total" in ids, "the internal frame went with the external one"
    assert "compare.parse.unavailable" in ids
    assert [one for one in ids if one.startswith("compare.")] == ["compare.parse.unavailable"]


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
        a_parse_subject(player=RAID[1], display_name="Stonewake"),
    )
    findings = analyse_encounter(
        loaded, DEFENSIVES, Consumables(), parse_subjects=subjects
    )

    ranks = [one for one in findings if one.id == "compare.rank"]
    assert len(ranks) == 1, "only one roster member is in this fixture's rankings row"
    unavailable = [
        one for one in findings
        if one.id == "compare.rank.unavailable" and "Stonewake" in one.title
    ]
    assert unavailable, "the second subject was never compared at all"
