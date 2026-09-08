# ABOUTME: Behaviour tests for confounds a comparison declares instead of correcting, alone
# ABOUTME: and over a sample. Each is read off a roster, so fact is measured where risk is not.

import pytest

from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.comparison.confounds import (
    ITEM_LEVEL_GAP,
    declare_confounds,
    declare_confounds_sample,
)
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player, Run

SAME_LEVEL = Comparability(our_level=16, their_level=16)


def player(name: str, class_name: str, spec: str, item_level: int = 318) -> Player:
    return Player(
        actor_id=abs(hash(name)) % 1000,
        name=name,
        class_name=class_name,
        spec=spec,
        item_level=item_level,
    )


def a_loaded(
    players: tuple[Player, ...] = (),
    level: int = 16,
    affix_ids: tuple[int, ...] = (9, 10, 147),
    affix_names: tuple[str, ...] = (),
) -> LoadedRun:
    return LoadedRun(
        run=Run(
            report_code="abc123",
            fight_id=36,
            dungeon_name="Den of Nalorakk",
            encounter_id=12825,
            keystone_level=level,
            affix_ids=affix_ids,
            affix_names=affix_names,
            keystone_time_ms=1_909_000,
            keystone_bonus=1,
            count_reached=744,
            count_required=729,
            npc_counts=(),
            players=players,
            pulls=(),
        )
    )


def member(loaded: LoadedRun) -> SpeedMember:
    """Wrap a `LoadedRun` fixture as the `SpeedMember` `declare_confounds` now takes.

    `declare_confounds` reads only `.run` off its second argument, so the row,
    comparability and alignment carried here are placeholders it never inspects.
    """
    return SpeedMember(
        row=SpeedRow(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            keystone_level=loaded.run.keystone_level,
            duration_ms=loaded.run.keystone_time_ms,
            deaths=0,
        ),
        run=loaded.run,
        comparability=Comparability(
            our_level=loaded.run.keystone_level, their_level=loaded.run.keystone_level
        ),
        alignment=Alignment(),
    )


ROSTER = (
    player("Stonewake", "DeathKnight", "Blood"),
    player("Emberkin", "Mage", "Arcane"),
)


def ids(findings: list[Finding]) -> set[str]:
    return {finding.id for finding in findings}


# --- declare_confounds (pairwise) -------------------------------------------


def test_an_augmentation_evoker_on_either_side_is_declared() -> None:
    theirs = a_loaded((*ROSTER, player("Augbot", "Evoker", "Augmentation")))

    findings = declare_confounds(a_loaded(ROSTER), member(theirs), SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.augmentation")

    assert banner.confidence is Confidence.MEASURED
    assert "attribution" in banner.detail.lower()
    assert banner.seconds_lost is None


def test_no_augmentation_evoker_means_no_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(ROSTER)), SAME_LEVEL)

    assert "compare.confound.augmentation" not in ids(findings)


def test_a_keystone_level_gap_is_declared() -> None:
    findings = declare_confounds(
        a_loaded(ROSTER),
        member(a_loaded(ROSTER, level=17)),
        Comparability(our_level=16, their_level=17),
    )

    assert "compare.confound.keystone_level" in ids(findings)


def test_matching_levels_need_no_keystone_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(ROSTER)), SAME_LEVEL)

    assert "compare.confound.keystone_level" not in ids(findings)


def test_a_material_item_level_gap_is_declared() -> None:
    richer = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP + 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(richer)), SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.item_level")

    assert "Catalyst" in banner.detail or "secondary" in banner.detail.lower()


def test_an_item_level_gap_at_the_exact_threshold_is_declared() -> None:
    """Pins the boundary as inclusive: flipping `>=` to `>` must fail this test."""
    at_threshold = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(at_threshold)), SAME_LEVEL)

    assert "compare.confound.item_level" in ids(findings)


def test_a_small_item_level_gap_is_not_worth_a_banner() -> None:
    close = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP - 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(close)), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)


def test_a_different_group_composition_is_declared() -> None:
    theirs = (player("Stonewake", "Warrior", "Protection"), player("Emberkin", "Mage", "Arcane"))

    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(theirs)), SAME_LEVEL)

    assert "compare.confound.composition" in ids(findings)


def test_the_same_composition_needs_no_banner() -> None:
    shuffled = tuple(reversed(ROSTER))

    findings = declare_confounds(a_loaded(ROSTER), member(a_loaded(shuffled)), SAME_LEVEL)

    assert "compare.confound.composition" not in ids(findings)


def test_an_empty_roster_declares_nothing_and_does_not_divide_by_zero() -> None:
    findings = declare_confounds(a_loaded(()), member(a_loaded(())), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)


def test_differing_affixes_are_declared_by_name() -> None:
    ours = a_loaded(affix_ids=(9, 147), affix_names=("Tyrannical", "Xal'atath's Guile"))
    theirs = a_loaded(affix_ids=(10, 147), affix_names=("Fortified", "Xal'atath's Guile"))

    findings = declare_confounds(ours, member(theirs), SAME_LEVEL)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert affixes.confidence is Confidence.MEASURED
    assert affixes.seconds_lost is None
    assert "only ours: Tyrannical" in affixes.evidence
    assert "only theirs: Fortified" in affixes.evidence


def test_an_affix_with_no_resolved_name_is_declared_by_id() -> None:
    ours = a_loaded(affix_ids=(9, 147))
    theirs = a_loaded(affix_ids=(10, 147))

    findings = declare_confounds(ours, member(theirs), SAME_LEVEL)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert "only ours: 9" in affixes.evidence
    assert "only theirs: 10" in affixes.evidence


def test_a_partial_affix_name_mismatch_raises() -> None:
    """affix_names must be empty or index-aligned with affix_ids; a partial table
    violates that invariant rather than being a legitimate shape to degrade from."""
    ours = a_loaded(affix_ids=(9, 10), affix_names=("Tyrannical",))
    theirs = a_loaded(affix_ids=(10, 147))

    with pytest.raises(ValueError):
        declare_confounds(ours, member(theirs), SAME_LEVEL)


def test_identical_affixes_raise_no_confound() -> None:
    ours = a_loaded(affix_ids=(9, 147))

    findings = declare_confounds(ours, member(ours), SAME_LEVEL)

    assert "compare.confound.affixes" not in ids(findings)


# --- declare_confounds_sample -----------------------------------------------


def a_sample_member(
    players: tuple[Player, ...],
    level: int = 16,
    our_level: int = 16,
    report_code: str = "fast",
    affix_ids: tuple[int, ...] = (9, 10, 147),
) -> SpeedMember:
    run = a_loaded(players, level=level, affix_ids=affix_ids).run
    return SpeedMember(
        row=SpeedRow(
            report_code=report_code,
            fight_id=1,
            keystone_level=level,
            duration_ms=run.keystone_time_ms,
            deaths=0,
        ),
        run=run,
        comparability=Comparability(our_level=our_level, their_level=level),
        alignment=Alignment(),
    )


def _augmented_pair(tag: str, item_level: int) -> tuple[Player, Player]:
    return (
        player(f"{tag}Evoker", "Evoker", "Augmentation", item_level),
        player(f"{tag}Mage", "Mage", "Arcane", item_level),
    )


def _unaugmented_pair(tag: str, item_level: int) -> tuple[Player, Player]:
    return (
        player(f"{tag}Mage", "Mage", "Arcane", item_level),
        player(f"{tag}Priest", "Priest", "Holy", item_level),
    )


OURS = a_loaded(ROSTER)
"""Our side of every `declare_confounds_sample` test: the plain two-player ROSTER."""

# Four of five rosters bring an Augmentation Evoker we never have; two of five sit a
# keystone level above ours; group item levels of 630-634 sit far above our roster's 318.
SAMPLE_OF_FIVE_WITH_AUGMENTATION = SpeedSample(
    members=(
        a_sample_member(_augmented_pair("A", 630), level=16, report_code="fastA"),
        a_sample_member(_augmented_pair("B", 631), level=16, report_code="fastB"),
        a_sample_member(_augmented_pair("C", 632), level=16, report_code="fastC"),
        a_sample_member(_augmented_pair("D", 633), level=17, report_code="fastD"),
        a_sample_member(_unaugmented_pair("E", 634), level=17, report_code="fastE"),
    )
)


def test_a_spec_every_fast_run_brought_and_we_did_not_is_counted() -> None:
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)

    composition = next(f for f in confounds if f.id == "compare.confound.composition")
    assert (
        composition.title == "4 of 5 fast runs brought an Augmentation Evoker; your group did not"
    )
    assert composition.quantifier == "most"
    assert composition.seconds_lost is None


def test_the_augmentation_confound_counts_rosters_and_states_no_ratio_in_the_title() -> None:
    # 4 of the 5 SAMPLE_OF_FIVE_WITH_AUGMENTATION rosters carry an Augmentation Evoker
    # (A, B, C, D); OURS carries none. The title names no ratio (Ruling R5: one
    # Augmentation Evoker anywhere is enough to establish the claim), so the count lives
    # only in the evidence line.
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)
    augmentation = next(f for f in confounds if f.id == "compare.confound.augmentation")

    assert (
        augmentation.title
        == "An Augmentation Evoker makes per-player damage attribution unreliable"
    )
    assert "4 of 5 fast run rosters contained an Augmentation Evoker" in augmentation.evidence
    assert augmentation.quantifier == ""
    assert augmentation.confidence is Confidence.MEASURED
    assert augmentation.seconds_lost is None


def test_the_composition_finding_gives_no_advice() -> None:
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)
    composition = next(f for f in confounds if f.id == "compare.confound.composition")

    assert "bring" not in composition.detail.lower()
    assert "recruit" not in composition.detail.lower()


def test_item_level_is_compared_against_the_median_of_the_group_means() -> None:
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)
    item_level = next(f for f in confounds if f.id == "compare.confound.item_level")

    assert "the median of 5 fast runs is 632" in item_level.title
    assert item_level.confidence is Confidence.DERIVED
    assert any("630" in line and "634" in line for line in item_level.evidence)


def test_the_keystone_confound_counts_the_members_at_a_different_level() -> None:
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)
    keystone = next(f for f in confounds if f.id == "compare.confound.keystone_level")

    assert keystone.title == "2 of 5 fast runs were at a different keystone level"
    assert keystone.quantifier == "some"


def test_the_affixes_confound_counts_rosters_that_matched_our_set() -> None:
    # OURS runs (9, 10, 147) affixes (a_loaded's default). Two of three members share
    # that set; the third ran a different one, so k=2 < total=3 and the finding fires.
    # count_phrase(2, 3) == "2 of 3"; quantifier_for(2, 3): 2*2=4 > 3, so "most".
    sample = SpeedSample(
        members=(
            a_sample_member(ROSTER, level=16, report_code="fastA", affix_ids=(9, 10, 147)),
            a_sample_member(ROSTER, level=16, report_code="fastB", affix_ids=(9, 10, 147)),
            a_sample_member(ROSTER, level=16, report_code="fastC", affix_ids=(9, 10, 999)),
        )
    )

    findings = declare_confounds_sample(OURS, sample)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert affixes.title == "2 of 3 fast runs ran your affix set"
    assert affixes.quantifier == "most"
    assert "2 of 3 fast runs shared our affix set" in affixes.evidence


def test_an_affix_set_no_fast_run_shared_is_quantified_as_none() -> None:
    """The one aggregate that really does reach zero. "none" is the word parallel
    to "every", and a narrative that may write no digits needs one to use."""
    sample = SpeedSample(
        members=tuple(
            a_sample_member(ROSTER, level=16, report_code=f"fast{tag}", affix_ids=(9, 10, 999))
            for tag in "ABC"
        )
    )

    findings = declare_confounds_sample(OURS, sample)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert affixes.title == "0 of 3 fast runs ran your affix set"
    assert affixes.quantifier == "none"


def test_a_wholly_empty_sample_declares_nothing() -> None:
    # `service.compare()` already says "nothing to compare against" once, as
    # `compare.speed.unavailable`; this must not crash, and must not repeat it.
    findings = declare_confounds_sample(OURS, SpeedSample())

    assert findings == []


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    sample = SpeedSample(
        members=(
            a_sample_member(ROSTER, level=17, report_code="fastA"),
            a_sample_member(ROSTER, level=17, report_code="fastB"),
        )
    )

    findings = declare_confounds_sample(OURS, sample)

    keystone = next(f for f in findings if f.id == "compare.confound.keystone_level")
    assert "+17" in keystone.title
    assert any("below the floor of" in line for line in keystone.evidence)


def test_when_no_spec_is_absent_from_ours_the_old_composition_title_is_kept() -> None:
    # Every member brings only "DeathKnight Blood", a spec we already have, but two
    # copies of it against our one, so the two rosters still differ in composition.
    sample = SpeedSample(
        members=tuple(
            a_sample_member(
                (
                    player(f"{tag}One", "DeathKnight", "Blood"),
                    player(f"{tag}Two", "DeathKnight", "Blood"),
                ),
                level=16,
                report_code=f"fast{tag}",
            )
            for tag in "ABC"
        )
    )

    findings = declare_confounds_sample(OURS, sample)

    composition = next(f for f in findings if f.id == "compare.confound.composition")
    assert composition.title == "The two groups were not the same composition"
    assert composition.quantifier == ""


def test_the_same_composition_across_the_sample_needs_no_banner() -> None:
    sample = SpeedSample(
        members=tuple(a_sample_member(ROSTER, level=16, report_code=f"fast{tag}") for tag in "ABC")
    )

    findings = declare_confounds_sample(OURS, sample)

    assert "compare.confound.composition" not in ids(findings)
