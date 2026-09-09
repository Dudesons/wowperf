# ABOUTME: Behaviour tests for the individual comparison: which spells and which build.
# ABOUTME: Everything here is restricted to boss pulls, where the encounter is the same fight.

from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    MIN_MEMBERS_WITH_ABILITY,
    boss_casts,
    boss_seconds,
    compare_spells,
    compare_spells_sample,
    compare_talents,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Player, Pull, Run

OURS = Player(actor_id=693, name="Emberkin", class_name="Mage", spec="Arcane", item_level=318)
THEIRS = Player(
    actor_id=11,
    name="Bríala",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)


def boss_pull(index: int, seconds: float) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk",
        encounter_id=2607,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def trash_pull(index: int, seconds: float) -> Pull:
    pull = boss_pull(index, seconds)
    return pull.model_copy(update={"encounter_id": 0, "name": "Pack"})


def a_loaded(player: Player, pulls: tuple[Pull, ...], casts: tuple[CastEvent, ...]) -> LoadedRun:
    run = Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(player,),
        pulls=pulls,
    )
    return LoadedRun(run=run, casts=casts)


def a_member(
    player: Player,
    pulls: tuple[Pull, ...],
    casts: tuple[CastEvent, ...],
    *,
    report_code: str = "REF1",
    level: int = 16,
) -> ParseMember:
    """A parse reference wrapping `a_loaded`, for the tests that need a `ParseMember`."""
    loaded = a_loaded(player, pulls, casts)
    return ParseMember(
        row=ParseRow(
            report_code=report_code,
            fight_id=1,
            keystone_level=level,
            duration_ms=1_909_000,
            character_name=player.name,
            class_name=player.class_name,
            spec=player.spec,
        ),
        run=loaded.run,
        casts=loaded.casts,
    )


def cast(actor_id: int, ability_id: int, name: str, at_ms: int, pull: int | None) -> CastEvent:
    return CastEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        timestamp_ms=at_ms,
        pull_index=pull,
    )


def test_boss_seconds_counts_only_boss_pulls() -> None:
    run = a_loaded(OURS, (boss_pull(0, 120.0), trash_pull(1, 60.0), boss_pull(2, 60.0)), ()).run

    assert boss_seconds(run) == 180.0


def test_boss_casts_ignore_trash_and_other_players() -> None:
    pulls = (boss_pull(0, 120.0), trash_pull(1, 60.0))
    casts = (
        cast(693, 30451, "Arcane Blast", 1_000, 0),
        cast(693, 30451, "Arcane Blast", 2_000, 0),
        cast(693, 30451, "Arcane Blast", 3_000, 1),
        cast(693, 30451, "Arcane Blast", 4_000, None),
        cast(7, 30451, "Arcane Blast", 5_000, 0),
    )
    run = a_loaded(OURS, pulls, casts).run

    counted = boss_casts(run, casts, actor_id=693)

    assert counted == {30451: ("Arcane Blast", 2)}


def test_an_ability_they_cast_and_we_never_did_is_reported() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 120.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 120.0),),
        (
            cast(11, 30451, "Arcane Blast", 1_000, 0),
            cast(11, 153626, "Arcane Orb", 2_000, 0),
            cast(11, 153626, "Arcane Orb", 3_000, 0),
        ),
    )

    findings = compare_spells(ours, OURS, theirs, "Bríala")
    missing = [f for f in findings if f.id.startswith("compare.spells.missing.")]

    assert len(missing) == 1
    assert "Arcane Orb" in missing[0].title
    assert missing[0].confidence is Confidence.MEASURED
    assert missing[0].seconds_lost is None


def test_an_ability_we_cast_only_on_trash_still_counts_as_cast() -> None:
    ours = a_loaded(
        OURS,
        (boss_pull(0, 120.0), trash_pull(1, 60.0)),
        (cast(693, 153626, "Arcane Orb", 200_000, 1),),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 120.0),),
        tuple(cast(11, 153626, "Arcane Orb", n * 1_000, 0) for n in range(4)),
    )

    missing = [
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.missing.")
    ]

    assert missing == []


def test_a_rate_gap_on_a_shared_ability_is_derived() -> None:
    ours = a_loaded(
        OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),)
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(6)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 1
    assert rates[0].confidence is Confidence.DERIVED
    assert "Arcane Blast" in rates[0].title


def test_a_reference_cast_too_few_times_is_not_a_rate_finding() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(
            cast(11, 30451, "Arcane Blast", n * 1_000, 0)
            for n in range(MIN_CASTS_TO_COMPARE - 1)
        ),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert rates == []


def test_a_reference_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(THEIRS, (trash_pull(0, 60.0),), ())

    findings = compare_spells(ours, OURS, theirs, "Bríala")

    assert any(f.id == "compare.spells.unavailable" for f in findings)


TOP_PARSE_ROW = ParseRow(
    report_code="TOPREF",
    fight_id=7,
    keystone_level=16,
    duration_ms=1_909_000,
    character_name=THEIRS.name,
    class_name=THEIRS.class_name,
    spec=THEIRS.spec,
)
TOP_PARSE_URL = "https://www.warcraftlogs.com/reports/TOPREF?fight=7"


def test_a_different_build_is_reported_with_their_string() -> None:
    finding = compare_talents(OURS.model_copy(update={"talent_import_string": "C4DAAAAA"}),
                              THEIRS, TOP_PARSE_ROW)[0]

    assert finding.id == "compare.talents"
    assert finding.confidence is Confidence.MEASURED
    assert any("CoPAAAAA" in line for line in finding.evidence)


def test_an_identical_build_reports_that_it_matches() -> None:
    same = OURS.model_copy(update={"talent_import_string": "CoPAAAAA"})

    finding = compare_talents(same, THEIRS, TOP_PARSE_ROW)[0]

    assert "matches" in finding.title.lower()


def test_a_missing_build_says_the_comparison_could_not_be_made() -> None:
    finding = compare_talents(OURS, THEIRS, TOP_PARSE_ROW)[0]

    assert "not" in finding.detail.lower()
    assert finding.seconds_lost is None


def test_the_talent_row_links_the_top_parse_and_names_no_player() -> None:
    """The one row that asks a reader to copy a stranger's build. It stays
    single-reference — a build has no median — so it must be traceable, and the
    trace is a link: a name written into a file is greppable and poolable."""
    builds = (
        (OURS.model_copy(update={"talent_import_string": "C4DAAAAA"}), THEIRS),
        (OURS.model_copy(update={"talent_import_string": "CoPAAAAA"}), THEIRS),
        (OURS, THEIRS),
    )

    for ours, theirs in builds:
        finding = compare_talents(ours, theirs, TOP_PARSE_ROW)[0]

        assert f"top-ranked parse: {TOP_PARSE_URL}" in finding.evidence
        assert THEIRS.name not in finding.title
        assert THEIRS.name not in finding.detail
        assert not any(THEIRS.name in line for line in finding.evidence)
        assert "the reference" not in finding.title.lower()


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 100 + n, f"Spell {n}", n * 1_000, 0) for n in range(8) for _ in range(4)),
    )

    ids = [f.id for f in compare_spells(ours, OURS, theirs, "Bríala")]

    assert len(ids) == len(set(ids))


# --- compare_spells_sample --------------------------------------------------

SHIFTING_POWER = 314791
"""Cast by 4 of the 5 members below, never by OURS: the set-difference case."""

RUNE_OF_POWER = 116011
"""Cast by only 2 of the 5 members below: below MIN_MEMBERS_WITH_ABILITY, reported nowhere."""

METEOR = 153561
"""Cast by both sides, at a rate gap wide enough to report: the median-rate case."""


def a_parse_member(
    name: str, actor_id: int, casts_by_ability: dict[int, int], *, boss_seconds_: float = 60.0
) -> ParseMember:
    """A sample member who casts each ability in `casts_by_ability` that many times,
    on the one boss pull that grounds their `boss_seconds`."""
    player = Player(actor_id=actor_id, name=name, class_name="Mage", spec="Arcane",
                     item_level=320)
    casts = tuple(
        cast(actor_id, ability_id, f"Ability {ability_id}", n * 1_000, 0)
        for ability_id, count in casts_by_ability.items()
        for n in range(count)
    )
    return a_member(player, (boss_pull(0, boss_seconds_),), casts)


# Five top parses. Four cast Shifting Power (3 times each) and Meteor (varying
# rates); only two cast Rune of Power. The fifth member casts none of the three.
SAMPLE_OF_FIVE = ParseSample(
    members=(
        a_parse_member("Bríala", 11, {SHIFTING_POWER: 3, METEOR: 6, RUNE_OF_POWER: 3}),
        a_parse_member("Dawnseeker", 12, {SHIFTING_POWER: 3, METEOR: 8, RUNE_OF_POWER: 3}),
        a_parse_member("Emberfall", 13, {SHIFTING_POWER: 3, METEOR: 4}),
        a_parse_member("Frostwhisper", 14, {SHIFTING_POWER: 3, METEOR: 10}),
        a_parse_member("Glimmerose", 15, {}),
    )
)

OURS_LOADED = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, METEOR, "Meteor", 1_000, 0),) * 2)


def test_a_spell_most_top_parses_cast_and_we_never_did_is_counted() -> None:
    findings = compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)

    missing = next(f for f in findings if f.id == "compare.spells.missing.0")
    assert missing.title == (
        "4 of 5 top parses cast Ability 314791 on bosses; Emberkin never did"
    )
    assert missing.quantifier == "most"
    assert missing.confidence is Confidence.MEASURED


def test_no_reference_player_is_named_in_a_sampled_spell_finding() -> None:
    findings = compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)

    for name in ("Bríala", "Dawnseeker", "Emberfall", "Frostwhisper", "Glimmerose"):
        assert all(name not in finding.title for finding in findings)
        assert all(name not in line for finding in findings for line in finding.evidence)


def test_an_ability_seen_in_too_few_members_is_not_reported() -> None:
    # Rune of Power is cast by 2 of the 5 members, one short of the threshold.
    assert 2 < MIN_MEMBERS_WITH_ABILITY

    findings = compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)

    assert not any(str(RUNE_OF_POWER) in f.title for f in findings)


def test_a_rate_gap_seen_in_too_few_members_is_not_reported() -> None:
    """The mirror of the missing-ability threshold, on the rate branch. Two
    parses casting something ten times a minute is two players' build, not a
    pattern, and a median of two is a mean of two."""
    two_of_five = ParseSample(
        members=(
            a_parse_member("Bríala", 11, {METEOR: 12}),
            a_parse_member("Dawnseeker", 12, {METEOR: 12}),
            a_parse_member("Emberfall", 13, {}),
            a_parse_member("Frostwhisper", 14, {}),
            a_parse_member("Glimmerose", 15, {}),
        )
    )
    # The fixture's own premise: one short of the threshold, at a gap that would
    # otherwise be reported (12 casts over 60s against our own 2).
    assert 2 < MIN_MEMBERS_WITH_ABILITY

    findings = compare_spells_sample(OURS_LOADED, OURS, two_of_five)

    assert not any(f.id.startswith("compare.spells.rate.") for f in findings)


def test_the_rate_finding_uses_the_median_of_per_run_rates() -> None:
    findings = compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)

    rate = next(f for f in findings if f.id == "compare.spells.rate.0")
    assert "4 top parses cast" in rate.title and "a median" in rate.title
    assert rate.confidence is Confidence.DERIVED
    assert any("range" in line for line in rate.evidence)


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.parse.unavailable`; this must not crash, and must not repeat it.
    findings = compare_spells_sample(OURS_LOADED, OURS, ParseSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    below_floor = ParseSample(members=SAMPLE_OF_FIVE.members[: MIN_SAMPLE_FOR_AGGREGATE - 1])

    findings = compare_spells_sample(OURS_LOADED, OURS, below_floor)

    missing = next(f for f in findings if f.id == "compare.spells.missing.0")
    assert "Bríala" in missing.title
    assert any("below the floor of" in line for line in missing.evidence)


def test_every_finding_id_is_unique_over_the_sample() -> None:
    ids = [f.id for f in compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)]

    assert len(ids) == len(set(ids))


def test_a_missing_spell_finding_names_the_ability_against_one_reference() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 120.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 120.0),),
        (
            cast(11, 30451, "Arcane Blast", 1_000, 0),
            cast(11, 153626, "Arcane Orb", 2_000, 0),
            cast(11, 153626, "Arcane Orb", 3_000, 0),
        ),
    )
    missing = next(
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.missing.")
    )
    assert missing.ability_id == 153626
    assert missing.ability_name == "Arcane Orb"
    assert missing.ability_name in missing.title


def test_a_rate_spell_finding_names_the_ability_against_one_reference() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(6)),
    )
    rate = next(
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == 30451
    assert rate.ability_name == "Arcane Blast"
    assert rate.ability_name in rate.title


def test_a_missing_spell_finding_names_the_ability_across_the_sample() -> None:
    missing = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.missing.")
    )
    assert missing.ability_id == SHIFTING_POWER
    # a_parse_member names every ability f"Ability {ability_id}"; this is that
    # synthetic name, not a real spell name.
    assert missing.ability_name == f"Ability {SHIFTING_POWER}"
    assert missing.ability_name in missing.title


def test_a_rate_spell_finding_names_the_ability_across_the_sample() -> None:
    rate = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == METEOR
    # The rate branch names the ability from our own side's cast (OURS_LOADED),
    # not the sample's synthetic "Ability {id}" naming.
    assert rate.ability_name == "Meteor"
    assert rate.ability_name in rate.title
