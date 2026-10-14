# ABOUTME: The buff uptime comparison reads one row per cause when it is handed the aura groups.
# ABOUTME: Pinned on our side and the references' alike, in the findings, the table and a raid.

from tests.domain.comparison.test_parse_axis import KILL_ARGS
from tests.domain.comparison.test_service import OUR_SLUG, OURS, THEIRS, a_loaded
from tests.domain.comparison.test_tables import a_parse_member, a_pull_of
from wowperf.domain.aura_groups import AuraGroups
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.measures import StretchCell, Verdict
from wowperf.domain.comparison.parse_axis import compare_parse_axis
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.comparison.uptime import (
    compare_uptime_sample,
    fight_seconds_of,
    key_clock_uptime,
)
from wowperf.domain.comparison.wording import KEY
from wowperf.domain.findings import Finding
from wowperf.domain.model import LoadedRun

DND = 188290
SANGUINE_GROUND = 391459
BLOOD_SOAKED_GROUND = 434034
BONE_SHIELD = 195181
CRIMSON_SCOURGE = 81141
OSSUARY = 219788
RECENTLY_USED_DEATH_STRIKE = 180612

TRIO_NAME = "Death and Decay, with Sanguine Ground and Blood-Soaked Ground"

GROUPS = AuraGroups(groups=((DND, SANGUINE_GROUND, BLOOD_SOAKED_GROUND),))

NAMES = {
    DND: "Death and Decay",
    SANGUINE_GROUND: "Sanguine Ground",
    BLOOD_SOAKED_GROUND: "Blood-Soaked Ground",
    BONE_SHIELD: "Bone Shield",
    CRIMSON_SCOURGE: "Crimson Scourge",
    OSSUARY: "Ossuary",
    RECENTLY_USED_DEATH_STRIKE: "Recently Used Death Strike",
}

KEY_MS = 100_000
"""Our key and every reference's: one boss pull of a hundred seconds, which is its whole clock."""


def an_aura(ability_id: int, *bands: tuple[int, int]) -> Aura:
    return Aura(
        ability_id=ability_id,
        name=NAMES[ability_id],
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=len(bands),
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def carrying(actor_id: int, *auras: Aura) -> PlayerAuras:
    return PlayerAuras(actor_id=actor_id, on_self=auras)


def a_key() -> LoadedRun:
    return a_loaded((OURS,), (a_pull_of(0, (9,), KEY_MS / 1000, boss=True),))


def a_reference(code: str, auras: PlayerAuras) -> ParseMember:
    theirs = a_loaded((THEIRS,), (a_pull_of(0, (9,), KEY_MS / 1000, boss=True),))
    return a_parse_member(code, theirs, auras=auras)


def five_references(*auras: Aura) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_reference(f"REF{one}", carrying(THEIRS.actor_id, *auras)) for one in range(5)
        )
    )


def subject(
    sample: ParseSample, our_auras: PlayerAuras, groups: AuraGroups = AuraGroups()
) -> tuple[ComparisonSubject, ...]:
    return (
        ComparisonSubject(
            player=OURS,
            slug=OUR_SLUG,
            display_name=OURS.name,
            parse=sample,
            our_auras=our_auras,
            aura_groups=groups,
        ),
    )


def uptime_gaps(findings: list[Finding]) -> list[Finding]:
    """The buff gap findings in the order they were ranked, whatever order the list is in."""
    gaps = [one for one in findings if one.id.startswith("compare.uptime.self.")]
    return sorted(gaps, key=lambda one: int(one.id.split(".")[3]))


def fact(finding: Finding, label: str) -> str:
    return next(one.value for one in finding.facts if one.label == label)


# Death and Decay carried under three ids by both sides, each for the same stretch, and four
# other causes the references carried longer than we did. The gaps run 0.60, 0.55, 0.50 for the
# trio, 0.45 and 0.40, so five slots take five causes where they used to take three rows of one.
OUR_CAUSES = carrying(
    OURS.actor_id,
    an_aura(DND, (0, 20_000)),
    an_aura(SANGUINE_GROUND, (0, 20_000)),
    an_aura(BLOOD_SOAKED_GROUND, (0, 20_000)),
    an_aura(BONE_SHIELD, (0, 10_000)),
    an_aura(CRIMSON_SCOURGE, (0, 10_000)),
    an_aura(OSSUARY, (0, 10_000)),
    an_aura(RECENTLY_USED_DEATH_STRIKE, (0, 10_000)),
)
THEIR_CAUSES = (
    an_aura(DND, (0, 70_000)),
    an_aura(SANGUINE_GROUND, (0, 70_000)),
    an_aura(BLOOD_SOAKED_GROUND, (0, 70_000)),
    an_aura(BONE_SHIELD, (0, 70_000)),
    an_aura(CRIMSON_SCOURGE, (0, 65_000)),
    an_aura(OSSUARY, (0, 55_000)),
    an_aura(RECENTLY_USED_DEATH_STRIKE, (0, 50_000)),
)


def test_one_cause_under_three_ids_is_one_finding_and_frees_the_slots_it_took() -> None:
    findings = compare(
        a_key(), None, subject(five_references(*THEIR_CAUSES), OUR_CAUSES, GROUPS)
    )

    gaps = uptime_gaps(findings)

    assert [(one.ability_id, one.ability_name) for one in gaps] == [
        (BONE_SHIELD, "Bone Shield"),
        (CRIMSON_SCOURGE, "Crimson Scourge"),
        (DND, TRIO_NAME),
        (OSSUARY, "Ossuary"),
        (RECENTLY_USED_DEATH_STRIKE, "Recently Used Death Strike"),
    ]
    assert fact(gaps[2], "Ours") == "20% of key time"
    assert fact(gaps[2], "Reference median") == "70% of key time"


def test_without_the_groups_the_same_three_rows_push_two_causes_out() -> None:
    """The control for the test above: the inputs are the same, the groups are not given."""
    findings = compare(a_key(), None, subject(five_references(*THEIR_CAUSES), OUR_CAUSES))

    assert [one.ability_name for one in uptime_gaps(findings)] == [
        "Bone Shield",
        "Crimson Scourge",
        "Death and Decay",
        "Sanguine Ground",
        "Blood-Soaked Ground",
    ]


def test_the_union_of_the_members_is_measured_on_our_side_and_on_every_reference() -> None:
    """Each member alone reads low and the stretches overlap, so only the union gives 20% and 70%.

    Ours: 0-10s, 5-20s and 10-20s of a hundred. Theirs: 0-20s, 10-70s and 60-70s. Read as
    the main id alone, ours is 10% and theirs 20%, which is no gap at all.
    """
    ours = carrying(
        OURS.actor_id,
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (5_000, 20_000)),
        an_aura(BLOOD_SOAKED_GROUND, (10_000, 20_000)),
    )
    theirs = (
        an_aura(DND, (0, 20_000)),
        an_aura(SANGUINE_GROUND, (10_000, 70_000)),
        an_aura(BLOOD_SOAKED_GROUND, (60_000, 70_000)),
    )

    findings = compare(a_key(), None, subject(five_references(*theirs), ours, GROUPS))

    [gap] = uptime_gaps(findings)
    assert gap.ability_name == TRIO_NAME
    assert fact(gap, "Ours") == "20% of key time"
    assert fact(gap, "Reference median") == "70% of key time"


def test_a_side_that_carried_only_another_member_is_compared_on_the_mains_row() -> None:
    """We carried Sanguine Ground alone and every reference Death and Decay alone.

    Unmerged, ours has no row for the main id and the comparison names the aura as one it
    cannot judge. Merged, both sides key the main id and the gap is stated.
    """
    ours = carrying(OURS.actor_id, an_aura(SANGUINE_GROUND, (0, 20_000)))
    theirs = (an_aura(DND, (0, 70_000)),)

    findings = compare(a_key(), None, subject(five_references(*theirs), ours, GROUPS))

    [gap] = uptime_gaps(findings)
    assert gap.ability_id == DND
    # Named as the references spell it: the sample is what names a row.
    assert gap.ability_name == "Death and Decay"
    assert fact(gap, "Ours") == "20% of key time"
    assert not [one for one in findings if one.id.startswith("compare.uptime.unjudged")]


def test_below_the_floor_the_single_reference_is_folded_too() -> None:
    sample = ParseSample(
        members=(a_reference("REF1", carrying(THEIRS.actor_id, *THEIR_CAUSES[:3])),)
    )
    ours = carrying(OURS.actor_id, *OUR_CAUSES.on_self[:3])

    findings = compare_uptime_sample(
        a_key().run.pulls, KEY_MS / 1000, ours, "Emberkin", sample,
        measured=key_clock_uptime, words=KEY, our_fight_ms=(0, KEY_MS), over=fight_seconds_of,
        groups=GROUPS,
    )

    [gap] = uptime_gaps(findings)
    assert gap.ability_name == TRIO_NAME


def test_the_table_carries_one_row_for_the_cause_and_describes_it_over_the_union() -> None:
    ours = carrying(
        OURS.actor_id,
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (5_000, 20_000)),
        an_aura(BLOOD_SOAKED_GROUND, (10_000, 20_000)),
    )
    theirs = (
        an_aura(DND, (0, 20_000)),
        an_aura(SANGUINE_GROUND, (10_000, 70_000)),
        an_aura(BLOOD_SOAKED_GROUND, (60_000, 70_000)),
    )
    subjects = subject(five_references(*theirs), ours, GROUPS)

    measures = comparison_measures(a_key(), subjects)[OUR_SLUG]

    [row] = measures.auras
    assert (row.uptime.ability_id, row.uptime.name) == (DND, TRIO_NAME)
    assert (row.uptime.ours, row.uptime.their_median) == (0.2, 0.7)
    assert row.uptime.verdict is Verdict.BELOW
    # The whole key is one boss pull, so the Bosses figure reads the same union.
    assert row.bosses == StretchCell(ours=0.2, their_median=0.7)


def test_every_finding_still_has_a_table_row_stating_the_same_figures_once_folded() -> None:
    subjects = subject(five_references(*THEIR_CAUSES), OUR_CAUSES, GROUPS)

    findings = compare(a_key(), None, subjects)
    measures = comparison_measures(a_key(), subjects)[OUR_SLUG]

    by_aura = {row.uptime.ability_id: row.uptime for row in measures.auras}
    gaps = uptime_gaps(findings)
    assert len(gaps) == 5
    for finding in gaps:
        assert finding.ability_id is not None
        measured = by_aura[finding.ability_id]
        assert finding.ability_name == measured.name
        assert fact(finding, "Ours") == f"{measured.ours:.0%} of key time"
        assert fact(finding, "Reference median") == f"{measured.their_median:.0%} of key time"


def a_raid_reference(code: str, *auras: Aura) -> ParseMember:
    return ParseMember(
        character_name="Stonewake",
        report_code=code,
        fight_id=1,
        boss_seconds=100.0,
        auras=carrying(THEIRS.actor_id, *auras),
    )


def test_a_raid_reads_one_row_per_cause_on_our_side_and_on_every_reference() -> None:
    ours = carrying(
        OURS.actor_id,
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (5_000, 20_000)),
        an_aura(BLOOD_SOAKED_GROUND, (10_000, 20_000)),
    )
    sample = ParseSample(
        members=tuple(
            a_raid_reference(
                f"REF{one}",
                an_aura(DND, (0, 20_000)),
                an_aura(SANGUINE_GROUND, (10_000, 70_000)),
                an_aura(BLOOD_SOAKED_GROUND, (60_000, 70_000)),
            )
            for one in range(5)
        )
    )
    args = {**KILL_ARGS, "our_seconds": 100.0, "our_auras": ours, "sample": sample}

    findings = compare_parse_axis(**args, aura_groups=GROUPS)  # type: ignore[arg-type]

    [gap] = uptime_gaps(findings)
    assert (gap.ability_id, gap.ability_name) == (DND, TRIO_NAME)
    assert fact(gap, "Ours") == "20% of fight time"
    assert fact(gap, "Reference median") == "70% of fight time"
