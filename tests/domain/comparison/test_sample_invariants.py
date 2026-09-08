# ABOUTME: Cross-module invariants a sample-based finding must never violate: a stated count
# ABOUTME: states its denominator, a stated median states its range, and neither badge is swapped.

import re

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.alignment import Alignment, align_pulls
from wowperf.domain.comparison.confounds import declare_confounds_sample
from wowperf.domain.comparison.reference import Comparability, ParseRow, SpeedRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample, SpeedMember, SpeedSample
from wowperf.domain.comparison.service import compare
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run

# The five call sites that state a ratio (grep `quantifier_for(` under
# src/wowperf/domain/comparison/) all live behind one of these prefixes. The prefix
# alone is too blunt, though (Ruling R5): below MIN_SAMPLE_FOR_AGGREGATE every sample
# function delegates to its pairwise counterpart, and `compare.confound.composition`
# falls back to today's title when no spec is absent from our roster -- both produce
# the same id with an empty `quantifier` and correctly no denominator. A finding is
# only held to the rule below when it also carries a non-empty quantifier; the two
# carve-out tests near the bottom of this file exercise both exemptions directly.
AGGREGATE_PREFIXES = (
    "compare.route.skipped.",
    "compare.spells.missing.",
    "compare.confound.composition",
    "compare.confound.affixes",
    "compare.confound.keystone_level",
)

# Every id whose sample function calls `statistics.median` and must state the
# observed range beside it. Ranked ids (spells.rate, uptime.self, uptime.target)
# need a prefix; the rest are single findings, so an exact id behaves the same
# under `startswith`.
MEDIAN_ID_PREFIXES = (
    "compare.downtime",
    "compare.deaths",
    "compare.interrupts",
    "compare.duration",
    "compare.confound.item_level",
    "compare.spells.rate.",
    "compare.uptime.self.",
    "compare.uptime.target.",
)

DUNGEON_ENCOUNTER_ID = 12825
BOSS_ENCOUNTER_ID = 2607
RATE_ABILITY_ID = 90002
RATE_ABILITY_NAME = "Frostbolt"
MISSING_ABILITY_ID = 90001
MISSING_ABILITY_NAME = "Meteor"
UPTIME_SELF_ABILITY_ID = 90003
UPTIME_SELF_ABILITY_NAME = "Ice Barrier"
UPTIME_TARGET_ABILITY_ID = 90004
UPTIME_TARGET_ABILITY_NAME = "Winter's Chill"


def _pull(index: int, game_id: int, seconds: float = 60.0, boss: bool = False) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Boss" if boss else "Pack",
        encounter_id=BOSS_ENCOUNTER_ID if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=index,
        y=index,
        enemies=(EnemyNpc(actor_id=1000 + index, game_id=game_id),),
    )


# Six trash pulls, one per enemy type (game id = index + 1), and one boss pull.
# Every speed reference below is built by aligning a subset of this route against
# itself, so `only_ours` / `only_theirs` land on exactly the pulls a reference
# fixture omits or keeps.
OUR_TRASH = tuple(_pull(i, i + 1) for i in range(6))
OUR_BOSS = _pull(6, 99, seconds=120.0, boss=True)
OUR_PULLS = (*OUR_TRASH, OUR_BOSS)

SUBJECT = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=300)

# Four casts of the ability both sides use, on our own boss pull, at 4 casts over
# 120s of boss time = 2 a minute -- the rate every parse reference below beats by
# more than spells.RATE_GAP_MULTIPLE.
OUR_CASTS = tuple(
    CastEvent(
        actor_id=SUBJECT.actor_id,
        ability_id=RATE_ABILITY_ID,
        ability_name=RATE_ABILITY_NAME,
        timestamp_ms=1_200_000 + n * 1_000,
        pull_index=6,
    )
    for n in range(4)
)

OUR_RUN = Run(
    report_code="ours",
    fight_id=1,
    dungeon_name="Den of Nalorakk",
    encounter_id=DUNGEON_ENCOUNTER_ID,
    keystone_level=16,
    affix_ids=(9, 10, 147),
    keystone_time_ms=1_400_000,
    keystone_bonus=1,
    count_reached=744,
    count_required=729,
    npc_counts=(),
    players=(SUBJECT,),
    pulls=OUR_PULLS,
    owner_name="emberkin",
)
OURS = LoadedRun(run=OUR_RUN, casts=OUR_CASTS)

# Our own boss pull (OUR_BOSS) spans 1_200_000ms to 1_320_000ms, 120s. 6s of each
# aura kept up is a 5% fraction -- low enough for every top parse below (80%) to
# clear UPTIME_GAP_FRACTION against it, and still above zero so the "we never had
# it at all" carve-out does not swallow the gap.
OUR_AURAS = PlayerAuras(
    actor_id=SUBJECT.actor_id,
    on_self=(
        Aura(
            ability_id=UPTIME_SELF_ABILITY_ID,
            name=UPTIME_SELF_ABILITY_NAME,
            total_uptime_ms=6_000,
            uses=1,
            bands=(AuraBand(start_ms=1_200_000, end_ms=1_206_000),),
        ),
    ),
    on_targets=(
        Aura(
            ability_id=UPTIME_TARGET_ABILITY_ID,
            name=UPTIME_TARGET_ABILITY_NAME,
            total_uptime_ms=6_000,
            uses=1,
            bands=(AuraBand(start_ms=1_200_000, end_ms=1_206_000),),
        ),
    ),
)


def _speed_member(
    tag: str, *, skip_pack: bool, level: int, affix_ids: tuple[int, ...]
) -> SpeedMember:
    """One fast run: our own route, minus the sixth trash pull when `skip_pack` is
    set, fielding a Priest Holy our own one-player roster never brings."""
    trash = OUR_TRASH[:5] if skip_pack else OUR_TRASH
    theirs = Run(
        report_code=f"fast{tag}",
        fight_id=1,
        dungeon_name="Den of Nalorakk",
        encounter_id=DUNGEON_ENCOUNTER_ID,
        keystone_level=level,
        affix_ids=affix_ids,
        keystone_time_ms=1_300_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(
            Player(
                actor_id=2000 + ord(tag), name=f"Fast{tag}Mage", class_name="Mage",
                spec="Arcane", item_level=400,
            ),
            Player(
                actor_id=3000 + ord(tag), name=f"Fast{tag}Priest", class_name="Priest",
                spec="Holy", item_level=400,
            ),
        ),
        pulls=(*trash, OUR_BOSS),
    )
    return SpeedMember(
        row=SpeedRow(
            report_code=f"fast{tag}", fight_id=1, keystone_level=level,
            duration_ms=1_300_000, deaths=0,
        ),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=level),
        alignment=align_pulls(OUR_RUN, theirs),
    )


# Five fast runs. Three skip our sixth pack (compare.route.skipped: "3 of 5", most);
# three sit at our keystone level and two one level higher
# (compare.confound.keystone_level: "2 of 5", some); two share our affix set and
# three run a different one (compare.confound.affixes: "2 of 5", some); every one
# fields a Priest Holy we never do (compare.confound.composition: "5 of 5", every);
# every one averages far above our item level (compare.confound.item_level, a
# median with a stated, if degenerate, range).
SAMPLE = SpeedSample(
    members=(
        _speed_member("A", skip_pack=True, level=16, affix_ids=(9, 10, 147)),
        _speed_member("B", skip_pack=True, level=16, affix_ids=(9, 10, 147)),
        _speed_member("C", skip_pack=True, level=17, affix_ids=(9, 10, 999)),
        _speed_member("D", skip_pack=False, level=16, affix_ids=(9, 10, 999)),
        _speed_member("E", skip_pack=False, level=17, affix_ids=(9, 10, 999)),
    )
)


def _parse_member(tag: str, *, casts_missing: bool) -> ParseMember:
    """One top parse: a boss pull, the rate ability cast enough to beat our own
    rate, the missing ability too unless `casts_missing` says otherwise, and both
    an on-self and an on-target aura kept up for 80% of that boss pull -- far
    above OUR_AURAS's 5%."""
    name = f"Rival{tag}"
    actor_id = 5000 + ord(tag)
    rate_casts = tuple(
        CastEvent(
            actor_id=actor_id, ability_id=RATE_ABILITY_ID, ability_name=RATE_ABILITY_NAME,
            timestamp_ms=1_200_000 + n * 1_000, pull_index=0,
        )
        for n in range(12)
    )
    missing_count = 3 if casts_missing else 0
    missing_casts = tuple(
        CastEvent(
            actor_id=actor_id, ability_id=MISSING_ABILITY_ID, ability_name=MISSING_ABILITY_NAME,
            timestamp_ms=1_250_000 + n * 1_000, pull_index=0,
        )
        for n in range(missing_count)
    )
    theirs = Run(
        report_code=f"top{tag}",
        fight_id=2,
        dungeon_name="Den of Nalorakk",
        encounter_id=DUNGEON_ENCOUNTER_ID,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_300_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(Player(actor_id=actor_id, name=name, class_name="Mage", spec="Arcane",
                         item_level=400),),
        pulls=(_pull(0, 99, seconds=120.0, boss=True),),
    )
    # This run's boss pull spans 0ms to 120_000ms; 96s of each aura is 80% of it.
    auras = PlayerAuras(
        actor_id=actor_id,
        on_self=(
            Aura(
                ability_id=UPTIME_SELF_ABILITY_ID,
                name=UPTIME_SELF_ABILITY_NAME,
                total_uptime_ms=96_000,
                uses=1,
                bands=(AuraBand(start_ms=0, end_ms=96_000),),
            ),
        ),
        on_targets=(
            Aura(
                ability_id=UPTIME_TARGET_ABILITY_ID,
                name=UPTIME_TARGET_ABILITY_NAME,
                total_uptime_ms=96_000,
                uses=1,
                bands=(AuraBand(start_ms=0, end_ms=96_000),),
            ),
        ),
    )
    return ParseMember(
        row=ParseRow(
            report_code=f"top{tag}", fight_id=2, keystone_level=16, duration_ms=1_300_000,
            character_name=name, class_name="Mage", spec="Arcane",
        ),
        run=theirs,
        casts=rate_casts + missing_casts,
        auras=auras,
    )


# Five top parses. All five cast the rate ability far more often than we do
# (compare.spells.rate: a DERIVED median with its range). Four of five also cast
# an ability we never cast anywhere (compare.spells.missing: "4 of 5", most). All
# five also keep an on-self buff and an on-target debuff up for 80% of their boss
# pull against our own 5% (compare.uptime.self / compare.uptime.target: a DERIVED
# median with its range).
PARSE_SAMPLE = ParseSample(
    members=(
        _parse_member("A", casts_missing=True),
        _parse_member("B", casts_missing=True),
        _parse_member("C", casts_missing=True),
        _parse_member("D", casts_missing=True),
        _parse_member("E", casts_missing=False),
    )
)


def test_the_fixture_exercises_every_aggregate_prefix_family() -> None:
    """A family that emits nothing is how the denominator guard would rot without
    anyone noticing (Ruling R5), so pin down that every prefix actually fires."""
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    for prefix in AGGREGATE_PREFIXES:
        matching = [f for f in findings if f.id.startswith(prefix) and f.quantifier]
        assert matching, f"no quantifier-carrying finding for prefix {prefix!r}"


def test_the_fixture_exercises_every_median_prefix_family() -> None:
    """The same guard as above, for the other tuple: `assert medians` in the tests
    below only proves the merged list is non-empty, so one family going silent
    could hide behind the others still firing. Enumerate them individually, the
    same way the aggregate families are."""
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    for prefix in MEDIAN_ID_PREFIXES:
        matching = [f for f in findings if f.id.startswith(prefix)]
        assert matching, f"no finding for median prefix {prefix!r}"


def test_every_count_finding_states_its_denominator_in_its_title() -> None:
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    counted = [f for f in findings if f.id.startswith(AGGREGATE_PREFIXES) and f.quantifier]
    assert counted, "the fixture must produce at least one aggregate finding"
    for finding in counted:
        assert re.search(r"\b\d+ of \d+\b", finding.title), finding.id


def test_no_count_finding_renders_its_share_of_the_sample_as_a_percentage() -> None:
    """At five references "80%" invents precision the sample does not have, and a
    reader cannot tell it apart from a percentage measured inside a run.

    Scoped to the count families deliberately. A rate or an uptime measured
    within one run — `compare.interrupts`, `compare.uptime.*` — is a real
    percentage of that run's own time and states one on purpose; only a share
    *of the sample* is banned from wearing one.
    """
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    counted = [f for f in findings if f.id.startswith(AGGREGATE_PREFIXES) and f.quantifier]
    assert counted, "the fixture must produce at least one aggregate finding"
    for finding in counted:
        assert "%" not in finding.title, finding.id
        assert not any("%" in line for line in finding.evidence), finding.id


def test_every_median_finding_states_its_range_in_its_evidence() -> None:
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    medians = [f for f in findings if f.id.startswith(MEDIAN_ID_PREFIXES)]
    assert medians, "the fixture must produce at least one median finding"
    for finding in medians:
        assert any("range" in line for line in finding.evidence), finding.id


def test_a_count_finding_is_measured_and_a_median_finding_is_derived() -> None:
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE, our_auras=OUR_AURAS
    )

    counted = [f for f in findings if f.id.startswith(AGGREGATE_PREFIXES) and f.quantifier]
    assert counted, "the fixture must produce at least one aggregate finding"
    for finding in counted:
        assert finding.confidence is Confidence.MEASURED, finding.id

    medians = [f for f in findings if f.id.startswith(MEDIAN_ID_PREFIXES)]
    assert medians, "the fixture must produce at least one median finding"
    for finding in medians:
        assert finding.confidence is Confidence.DERIVED, finding.id


# --- Ruling R5's two carve-outs, exercised directly -------------------------
#
# The tests above key the denominator rule on `quantifier`, not on id prefix
# alone, precisely so that these two shapes are exempt. Both are proven here to
# actually fire, and to actually carry no denominator and an empty quantifier --
# otherwise the exemption in the tests above would be untested and could silently
# start covering for a real defect.


def test_a_below_floor_sample_carries_no_denominator_and_is_exempt_from_the_rule() -> None:
    """Below MIN_SAMPLE_FOR_AGGREGATE, every sample function delegates to its
    pairwise counterpart, whose title correctly states no denominator -- there is
    no sample size to state one of."""
    below_floor = SpeedSample(members=(SAMPLE.members[0],))

    findings = compare(ours=OURS, our_player=SUBJECT, speed=below_floor, parse=None)

    matching = [f for f in findings if f.id.startswith(AGGREGATE_PREFIXES)]
    assert matching, "the one-member sample should still produce a route or confound finding"
    for finding in matching:
        assert finding.quantifier == "", finding.id
        assert not re.search(r"\b\d+ of \d+\b", finding.title), finding.id


def test_a_composition_confound_with_no_absent_spec_states_no_denominator_either() -> None:
    """`_confound_composition` falls back to today's title when no spec is absent
    from our own roster -- the two rosters here differ only in headcount, not in
    which specs appear, so the fallback (not the counted) branch fires."""
    our_two_mages = LoadedRun(
        run=OUR_RUN.model_copy(
            update={
                "players": (
                    SUBJECT,
                    Player(actor_id=2, name="Emberally", class_name="Mage", spec="Arcane",
                           item_level=300),
                )
            }
        )
    )

    def one_mage_pair(tag: str) -> SpeedMember:
        theirs = Run(
            report_code=f"fast{tag}",
            fight_id=1,
            dungeon_name="Den of Nalorakk",
            encounter_id=DUNGEON_ENCOUNTER_ID,
            keystone_level=16,
            affix_ids=(9, 10, 147),
            keystone_time_ms=1_300_000,
            keystone_bonus=1,
            count_reached=744,
            count_required=729,
            npc_counts=(),
            players=(
                Player(actor_id=4000 + ord(tag), name=f"Fast{tag}A", class_name="Mage",
                       spec="Arcane", item_level=300),
            ),
            pulls=(),
        )
        return SpeedMember(
            row=SpeedRow(report_code=f"fast{tag}", fight_id=1, keystone_level=16,
                         duration_ms=1_300_000, deaths=0),
            run=theirs,
            comparability=Comparability(our_level=16, their_level=16),
            alignment=Alignment(),
        )

    sample = SpeedSample(members=tuple(one_mage_pair(tag) for tag in "ABC"))
    findings = declare_confounds_sample(our_two_mages, sample)
    composition = next(f for f in findings if f.id == "compare.confound.composition")

    assert composition.quantifier == ""
    assert not re.search(r"\b\d+ of \d+\b", composition.title)
