# ABOUTME: Behaviour tests for confounds a comparison declares instead of correcting.
# ABOUTME: Each is read straight off a roster, so fact is measured where risk is not.

from wowperf.domain.comparison.confounds import ITEM_LEVEL_GAP, declare_confounds
from wowperf.domain.comparison.reference import Comparability
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


ROSTER = (
    player("Dudesons", "DeathKnight", "Blood"),
    player("Uglymage", "Mage", "Arcane"),
)


def ids(findings: list[Finding]) -> set[str]:
    return {finding.id for finding in findings}


def test_an_augmentation_evoker_on_either_side_is_declared() -> None:
    theirs = a_loaded((*ROSTER, player("Augbot", "Evoker", "Augmentation")))

    findings = declare_confounds(a_loaded(ROSTER), theirs, SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.augmentation")

    assert banner.confidence is Confidence.MEASURED
    assert "attribution" in banner.detail.lower()
    assert banner.seconds_lost is None


def test_no_augmentation_evoker_means_no_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), a_loaded(ROSTER), SAME_LEVEL)

    assert "compare.confound.augmentation" not in ids(findings)


def test_a_keystone_level_gap_is_declared() -> None:
    findings = declare_confounds(
        a_loaded(ROSTER), a_loaded(ROSTER, level=17), Comparability(our_level=16, their_level=17)
    )

    assert "compare.confound.keystone_level" in ids(findings)


def test_matching_levels_need_no_keystone_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), a_loaded(ROSTER), SAME_LEVEL)

    assert "compare.confound.keystone_level" not in ids(findings)


def test_a_material_item_level_gap_is_declared() -> None:
    richer = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP + 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(richer), SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.item_level")

    assert "Catalyst" in banner.detail or "secondary" in banner.detail.lower()


def test_an_item_level_gap_at_the_exact_threshold_is_declared() -> None:
    """Pins the boundary as inclusive: flipping `>=` to `>` must fail this test."""
    at_threshold = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(at_threshold), SAME_LEVEL)

    assert "compare.confound.item_level" in ids(findings)


def test_a_small_item_level_gap_is_not_worth_a_banner() -> None:
    close = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP - 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(close), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)


def test_a_different_group_composition_is_declared() -> None:
    theirs = (player("Dudesons", "Warrior", "Protection"), player("Uglymage", "Mage", "Arcane"))

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(theirs), SAME_LEVEL)

    assert "compare.confound.composition" in ids(findings)


def test_the_same_composition_needs_no_banner() -> None:
    shuffled = tuple(reversed(ROSTER))

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(shuffled), SAME_LEVEL)

    assert "compare.confound.composition" not in ids(findings)


def test_an_empty_roster_declares_nothing_and_does_not_divide_by_zero() -> None:
    findings = declare_confounds(a_loaded(()), a_loaded(()), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)


def test_differing_affixes_are_declared_by_name() -> None:
    ours = a_loaded(affix_ids=(9, 147), affix_names=("Tyrannical", "Xal'atath's Guile"))
    theirs = a_loaded(affix_ids=(10, 147), affix_names=("Fortified", "Xal'atath's Guile"))

    findings = declare_confounds(ours, theirs, SAME_LEVEL)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert affixes.confidence is Confidence.MEASURED
    assert affixes.seconds_lost is None
    assert "only ours: Tyrannical" in affixes.evidence
    assert "only theirs: Fortified" in affixes.evidence


def test_an_affix_with_no_resolved_name_is_declared_by_id() -> None:
    ours = a_loaded(affix_ids=(9, 147))
    theirs = a_loaded(affix_ids=(10, 147))

    findings = declare_confounds(ours, theirs, SAME_LEVEL)
    affixes = next(f for f in findings if f.id == "compare.confound.affixes")

    assert "only ours: 9" in affixes.evidence
    assert "only theirs: 10" in affixes.evidence


def test_identical_affixes_raise_no_confound() -> None:
    ours = a_loaded(affix_ids=(9, 147))

    findings = declare_confounds(ours, ours, SAME_LEVEL)

    assert "compare.confound.affixes" not in ids(findings)
