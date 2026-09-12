# ABOUTME: Behaviour tests for the individual comparison: which spells and which build.
# ABOUTME: Everything here is restricted to boss pulls, where the encounter is the same fight.

from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.spells import (
    MAX_SPELLS_REPORTED,
    MIN_CASTS_TO_COMPARE,
    MIN_MEMBERS_WITH_ABILITY,
    boss_casts,
    boss_seconds,
    casts_in,
    compare_spells,
    compare_spells_sample,
    compare_talents,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
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

OUR_NAME = "Emberkin (actor 693)"
"""The spelling `display_names` gives a name two roster members share.

Deliberately not `OURS.name`: every title below is built from the name the
caller passes in, and a fixture that passed `OURS.name` would keep passing if
these modules went back to reading the name off the roster — which is the bug
that put one player's name on another player's finding.
"""


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


def test_casts_in_counts_only_the_given_pulls_for_the_given_actor() -> None:
    """The counting rule boss_casts uses, taken out so a trash-scoped caller
    shares it rather than writing a second one that can drift."""
    casts = (
        cast(693, 100, "Kept", 1_000, 0),
        cast(693, 100, "Kept", 2_000, 0),
        cast(693, 100, "Kept", 3_000, 5),
        cast(693, 200, "Other pull", 4_000, 9),
        cast(11, 100, "Other actor", 5_000, 0),
        cast(693, 300, "No pull", 6_000, None),
    )

    counted = casts_in(casts, 693, frozenset({0, 5}))

    assert counted == {100: ("Kept", 3)}


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

    findings = compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
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
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
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
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
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
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert rates == []


def test_a_reference_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(THEIRS, (trash_pull(0, 60.0),), ())

    findings = compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")

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
                              OUR_NAME, THEIRS, TOP_PARSE_ROW)[0]

    assert finding.id == "compare.talents"
    assert finding.confidence is Confidence.MEASURED
    assert any("CoPAAAAA" in line for line in finding.evidence)


def test_an_identical_build_reports_that_it_matches() -> None:
    same = OURS.model_copy(update={"talent_import_string": "CoPAAAAA"})

    finding = compare_talents(same, OUR_NAME, THEIRS, TOP_PARSE_ROW)[0]

    assert "matches" in finding.title.lower()


def test_a_missing_build_says_the_comparison_could_not_be_made() -> None:
    finding = compare_talents(OURS, OUR_NAME, THEIRS, TOP_PARSE_ROW)[0]

    assert "not" in finding.detail.lower()
    assert finding.seconds_lost is None


TALENT_BUILDS = (
    (OURS.model_copy(update={"talent_import_string": "C4DAAAAA"}), THEIRS),
    (OURS.model_copy(update={"talent_import_string": "CoPAAAAA"}), THEIRS),
    (OURS, THEIRS),
)
"""One pair per branch of `compare_talents`: differs, matches, and no string at all."""


def test_the_talent_row_links_the_top_parse_and_names_no_reference_player() -> None:
    """The one row that asks a reader to copy a stranger's build. It stays
    single-reference — a build has no median — so it must be traceable, and the
    trace is a link: a name written into a file is greppable and poolable."""
    for ours, theirs in TALENT_BUILDS:
        finding = compare_talents(ours, OUR_NAME, theirs, TOP_PARSE_ROW)[0]

        assert f"top-ranked parse: {TOP_PARSE_URL}" in finding.evidence
        assert THEIRS.name not in finding.title
        assert THEIRS.name not in finding.detail
        assert not any(THEIRS.name in line for line in finding.evidence)
        assert "the reference" not in finding.title.lower()


def test_every_talent_outcome_names_the_player_whose_build_it_is() -> None:
    """`compare_talents` emits exactly one of its three findings per player, so
    a title naming nobody reads identically under every card of a whole-group
    run — and in the findings file, which is what the narrative is written
    from, there would be no way to say whose build differed."""
    titles = [
        compare_talents(ours, OUR_NAME, theirs, TOP_PARSE_ROW)[0].title
        for ours, theirs in TALENT_BUILDS
    ]

    assert len(titles) == len(TALENT_BUILDS)
    for title in titles:
        assert OUR_NAME in title


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 100 + n, f"Spell {n}", n * 1_000, 0) for n in range(8) for _ in range(4)),
    )

    ids = [f.id for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")]

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
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)

    missing = next(f for f in findings if f.id == "compare.spells.missing.0")
    assert missing.title == (
        f"4 of 5 top parses cast Ability 314791 on bosses; {OUR_NAME} never did"
    )
    assert missing.quantifier == "most"
    assert missing.confidence is Confidence.MEASURED


def test_no_reference_player_is_named_in_a_sampled_spell_finding() -> None:
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)

    for name in ("Bríala", "Dawnseeker", "Emberfall", "Frostwhisper", "Glimmerose"):
        assert all(name not in finding.title for finding in findings)
        assert all(name not in line for finding in findings for line in finding.evidence)


def test_an_ability_seen_in_too_few_members_is_not_reported() -> None:
    # Rune of Power is cast by 2 of the 5 members, one short of the threshold.
    assert 2 < MIN_MEMBERS_WITH_ABILITY

    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)

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

    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, two_of_five)

    assert not any(f.id.startswith("compare.spells.rate.") for f in findings)


def test_the_rate_finding_uses_the_median_of_per_run_rates() -> None:
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)

    rate = next(f for f in findings if f.id == "compare.spells.rate.0")
    assert "4 top parses cast" in rate.title and "a median" in rate.title
    assert rate.confidence is Confidence.DERIVED
    assert any("range" in line for line in rate.evidence)


LEVEL_SAMPLE = ParseSample(
    members=(
        a_parse_member("Bríala", 11, {METEOR: 10}),
        a_parse_member("Dawnseeker", 12, {METEOR: 11}),
        a_parse_member("Emberfall", 13, {METEOR: 12}),
        a_parse_member("Frostwhisper", 14, {}),
        a_parse_member("Glimmerose", 15, {}),
    )
)
"""Three parses cast Meteor a touch more often than the run below: compared, no gap."""

LEVEL_LOADED = a_loaded(
    OURS, (boss_pull(0, 60.0),), (cast(693, METEOR, "Meteor", 1_000, 0),) * 10
)


def test_an_ability_compared_and_found_inside_the_band_is_named() -> None:
    """Silence meant three different things — never compared, compared and level, or
    dropped below a threshold — and the page gave a reader no way to tell them apart.
    A player asking "am I fine on this button" needs the second said out loud."""
    findings = compare_spells_sample(LEVEL_LOADED, OURS, OUR_NAME, LEVEL_SAMPLE)

    level = next(f for f in findings if f.id == "compare.spells.level")
    assert "Meteor" in " ".join(level.evidence)


def test_a_single_level_ability_is_counted_in_the_singular() -> None:
    """A title states its count back to the reader, and "1 abilities" gets noticed
    before the finding does."""
    findings = compare_spells_sample(LEVEL_LOADED, OURS, OUR_NAME, LEVEL_SAMPLE)

    level = next(f for f in findings if f.id == "compare.spells.level")
    assert level.title.startswith("1 ability ")
    assert "was compared" in level.title


def test_no_level_row_is_written_when_every_ability_showed_a_gap() -> None:
    """An empty row would say "nothing was level" in a voice indistinguishable from
    "nothing was compared", which is the confusion this family exists to end."""
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)

    assert not any(f.id.startswith("compare.spells.level") for f in findings)


def test_an_ability_too_few_parses_cast_is_not_called_level() -> None:
    """Level means compared and no gap found. An ability the sample barely cast was
    never compared at all, and claiming it as level would invent a reassurance."""
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        (cast(693, METEOR, "Meteor", 1_000, 0),) * 10
        + (cast(693, RUNE_OF_POWER, "Rune of Power", 2_000, 0),) * 10,
    )

    findings = compare_spells_sample(ours, OURS, OUR_NAME, LEVEL_SAMPLE)

    level = next(f for f in findings if f.id == "compare.spells.level")
    assert "Meteor" in " ".join(level.evidence)
    assert "Rune of Power" not in " ".join(level.evidence)


def test_the_level_row_is_one_sentence_rather_than_a_ranked_family() -> None:
    """The gap rows compete with each other and are collapsed and numbered. This one
    states a set, so a rank suffix would promise rivals it does not have."""
    findings = compare_spells_sample(LEVEL_LOADED, OURS, OUR_NAME, LEVEL_SAMPLE)

    assert [f.id for f in findings if f.id.startswith("compare.spells.level")] == [
        "compare.spells.level"
    ]


def a_sampled_rate_finding() -> Finding:
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)
    return next(f for f in findings if f.id == "compare.spells.rate.0")


def test_a_spell_rate_finding_carries_both_sides_as_facts() -> None:
    # The same numbers the title and the evidence already state, taken a third
    # way. Nothing here is a second measurement, and nothing is parsed back out
    # of a string the analyser had just formatted.
    rate = a_sampled_rate_finding()
    assert [fact.label for fact in rate.facts] == [
        "Ours", "Reference median", "Observed range", "Sample",
    ]
    values = {fact.label: fact.value for fact in rate.facts}
    assert values["Ours"].endswith(" casts a minute")
    assert values["Reference median"].endswith(" casts a minute")
    assert values["Sample"] == "4 top parses"
    assert values["Ours"].split()[0] in rate.title
    assert values["Reference median"].split()[0] in rate.title


def test_the_reference_side_is_a_median_and_a_range_and_never_a_mean() -> None:
    # This project reports a median and an observed range, never a mean, and a
    # panel is one more surface that has to keep saying so.
    labels = [fact.label for fact in a_sampled_rate_finding().facts]
    assert "Reference median" in labels and "Observed range" in labels
    assert not any("mean" in label.lower() for label in labels)


def test_a_rate_fact_is_derived_because_a_rate_is_computed() -> None:
    # An unset tier is what a panel draws measured with, so a rate this report
    # divided out has to say derived rather than leave the line bare.
    rate = a_sampled_rate_finding()
    assert all(fact.confidence is Confidence.DERIVED for fact in rate.facts[:3])
    assert rate.facts[3].confidence is None  # a count of parses, read not computed


def test_a_pairwise_rate_finding_names_one_reference_rather_than_a_median() -> None:
    # The fallback shape, drawn when the sample has too few comparable members.
    # It has no median and no range, and must not print labels claiming either.
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, METEOR, "Meteor", 1_000, 0),))
    theirs = a_member(
        THEIRS, (boss_pull(0, 60.0),),
        tuple(cast(11, METEOR, "Meteor", n * 1_000, 0) for n in range(8)),
    )
    findings = compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
    rate = next(f for f in findings if f.id.startswith("compare.spells.rate."))
    assert [fact.label for fact in rate.facts] == ["Ours", "Reference", "Sample"]
    assert {fact.value for fact in rate.facts} >= {"1 reference run"}


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.parse.unavailable`; this must not crash, and must not repeat it.
    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, ParseSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    below_floor = ParseSample(members=SAMPLE_OF_FIVE.members[: MIN_SAMPLE_FOR_AGGREGATE - 1])

    findings = compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, below_floor)

    missing = next(f for f in findings if f.id == "compare.spells.missing.0")
    assert "Bríala" in missing.title
    assert any("below the floor of" in line for line in missing.evidence)


def test_every_finding_id_is_unique_over_the_sample() -> None:
    ids = [f.id for f in compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)]

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
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
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
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == 30451
    assert rate.ability_name == "Arcane Blast"
    assert rate.ability_name in rate.title


def test_a_missing_spell_finding_names_the_ability_across_the_sample() -> None:
    missing = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.missing.")
    )
    assert missing.ability_id == SHIFTING_POWER
    # a_parse_member names every ability f"Ability {ability_id}"; this is that
    # synthetic name, not a real spell name.
    assert missing.ability_name == f"Ability {SHIFTING_POWER}"
    assert missing.ability_name in missing.title


def test_a_rate_spell_finding_names_the_ability_across_the_sample() -> None:
    rate = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, OUR_NAME, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == METEOR
    # The rate branch names the ability from our own side's cast (OURS_LOADED),
    # not the sample's synthetic "Ability {id}" naming.
    assert rate.ability_name == "Meteor"
    assert rate.ability_name in rate.title


# Measured 2026-09-11 against the cached responses: 475 of 1755 ability names
# own more than one game id, and 22 of the 73 report-and-actor pairs that cast
# anything cast some name under two ids. Both figures are recorded in
# `.claude/skills/wcl-api/SKILL.md`. That is why the tests below exist and why
# none of them merges casts: for some of those pairs one press emits both ids,
# so summing the counts would report two presses where there was one, and
# nothing in the log says which pairs those are.


def test_one_sentence_is_printed_once_however_many_ids_produced_it() -> None:
    """Alter Time casts as 342245 and as 342247, and both are named Alter Time.

    Each row's own rate is correct -- one press does emit one cast of that id
    -- so the ids must not be merged into a doubled count. What must not
    happen is the same true sentence printed twice with nothing in it to tell
    the two apart.
    """
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        (cast(693, 342245, "Alter Time", 1_000, 0), cast(693, 342247, "Alter Time", 1_100, 0)),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 342245, "Alter Time", n * 1_000, 0) for n in range(6))
        + tuple(cast(11, 342247, "Alter Time", n * 1_000 + 100, 0) for n in range(6)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 1, [f.title for f in rates]
    assert "ability 342245" in rates[0].evidence
    assert "ability 342247" in rates[0].evidence


def test_two_ids_of_one_name_that_say_different_things_keep_both_rows() -> None:
    """Collapsing is on the sentence, not on the name.

    Some same-named pairs are genuinely two abilities -- measured on the same
    cache, Demonic Gateway's two ids never pair up within a second of each
    other. Where their rates differ the two titles differ too, and both rows
    carry information the other does not.
    """
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        (cast(693, 342245, "Alter Time", 1_000, 0), cast(693, 342247, "Alter Time", 1_100, 0)),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 342245, "Alter Time", n * 1_000, 0) for n in range(6))
        + tuple(cast(11, 342247, "Alter Time", n * 1_000 + 100, 0) for n in range(12)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 2, [f.title for f in rates]
    assert rates[0].title != rates[1].title


def test_collapsing_leaves_the_rank_numbering_without_a_hole_in_it() -> None:
    """The rank is part of the id, and the id is an element id on the page.

    A row dropped after its neighbours were numbered would leave
    `compare.spells.rate.0` beside `compare.spells.rate.2`, and a reader
    following a pointer to the missing one would land nowhere.
    """
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        (
            cast(693, 342245, "Alter Time", 1_000, 0),
            cast(693, 342247, "Alter Time", 1_100, 0),
            cast(693, 30451, "Arcane Blast", 1_200, 0),
        ),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 342245, "Alter Time", n * 1_000, 0) for n in range(6))
        + tuple(cast(11, 342247, "Alter Time", n * 1_000 + 100, 0) for n in range(6))
        + tuple(cast(11, 30451, "Arcane Blast", n * 1_000 + 200, 0) for n in range(9)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 2, [f.title for f in rates]
    assert [f.id for f in rates] == ["compare.spells.rate.0", "compare.spells.rate.1"]


def three_rate_gaps() -> tuple[LoadedRun, ParseMember]:
    """One run and one reference differing on three abilities by three margins.

    Arcane Blast has the widest gap, then Fire Blast, then Frostbolt, so the
    ranking is decided by the numbers and not by the order the abilities were
    inserted into any dictionary.
    """
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        (
            cast(693, 30451, "Arcane Blast", 1_000, 0),
            cast(693, 108853, "Fire Blast", 1_100, 0),
            cast(693, 116, "Frostbolt", 1_200, 0),
        ),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(20))
        + tuple(cast(11, 108853, "Fire Blast", n * 1_000 + 100, 0) for n in range(12))
        + tuple(cast(11, 116, "Frostbolt", n * 1_000 + 200, 0) for n in range(6)),
    )
    return ours, theirs


def test_the_widest_rate_gap_is_ranked_first() -> None:
    """The rank is assigned after the collapse, so the sort has to survive it.

    Pinned on which ability each rank names, not merely on the ranks being
    contiguous: a collapse that reversed or reshuffled its input would still
    number 0, 1, 2 and would still put the least useful row at the top of the
    card.
    """
    ours, theirs = three_rate_gaps()

    rates = [
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert [f.ability_name for f in rates] == ["Arcane Blast", "Fire Blast", "Frostbolt"]


def test_no_more_of_one_spell_family_is_reported_than_the_cap_allows() -> None:
    """`MAX_SPELLS_REPORTED` now caps distinct sentences rather than candidates.

    Nothing else in the suite observes the cap, and the collapse routed all
    four spell families through one truncation, so one edit there would uncap
    every one of them.
    """
    ours = a_loaded(
        OURS,
        (boss_pull(0, 60.0),),
        tuple(
            cast(693, 500 + n, f"Spell {n}", 1_000 + n, 0)
            for n in range(MAX_SPELLS_REPORTED + 3)
        ),
    )
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(
            cast(11, 500 + n, f"Spell {n}", m * 1_000 + n, 0)
            for n in range(MAX_SPELLS_REPORTED + 3)
            for m in range(6)
        ),
    )

    rates = [
        f for f in compare_spells(ours, OURS, OUR_NAME, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    ]

    # Every one of the eight is a real gap, so the cap is the only thing that
    # can be holding the count down.
    assert len(rates) == MAX_SPELLS_REPORTED
