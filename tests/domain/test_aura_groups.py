# ABOUTME: Behaviour tests for folding the auras of one cause into one aura per hand-kept group.
# ABOUTME: The cases are the union of bands, partial groups, the main id, naming, and order.

import pytest

from wowperf.domain.aura_groups import AuraGroups, merge_aura_groups
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras

DND = 188290
SANGUINE_GROUND = 391459
BLOOD_SOAKED_GROUND = 434034
DANCING_RUNE_WEAPON = 81256
DANCE_OF_MIDNIGHT = 1264407

GROUPS = AuraGroups(
    groups=(
        (DND, SANGUINE_GROUND, BLOOD_SOAKED_GROUND),
        (DANCING_RUNE_WEAPON, DANCE_OF_MIDNIGHT),
    )
)

NAMES = {
    DND: "Death and Decay",
    SANGUINE_GROUND: "Sanguine Ground",
    BLOOD_SOAKED_GROUND: "Blood-Soaked Ground",
    DANCING_RUNE_WEAPON: "Dancing Rune Weapon",
    DANCE_OF_MIDNIGHT: "Dance of Midnight",
}


def an_aura(
    ability_id: int,
    *bands: tuple[int, int],
    name: str | None = None,
    icon: str = "",
    uses: int = 1,
) -> Aura:
    return Aura(
        ability_id=ability_id,
        name=name if name is not None else NAMES[ability_id],
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=uses,
        icon=icon,
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def carrying(*auras: Aura) -> PlayerAuras:
    return PlayerAuras(actor_id=7, on_self=auras)


def merged(*auras: Aura) -> tuple[Aura, ...]:
    return merge_aura_groups(carrying(*auras), GROUPS).on_self


def bands_of(aura: Aura) -> tuple[tuple[int, int], ...]:
    return tuple((band.start_ms, band.end_ms) for band in aura.bands)


def test_overlapping_bands_of_two_members_become_one_band() -> None:
    [one] = merged(
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (5_000, 15_000)),
    )

    assert bands_of(one) == ((0, 15_000),)


def test_disjoint_bands_of_two_members_stay_two_bands_oldest_first() -> None:
    [one] = merged(
        an_aura(DND, (20_000, 30_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
    )

    assert bands_of(one) == ((0, 10_000), (20_000, 30_000))


def test_the_total_uptime_is_the_length_of_the_union_and_not_the_sum_of_the_members() -> None:
    [one] = merged(
        an_aura(DND, (0, 10_000), (20_000, 30_000)),
        an_aura(SANGUINE_GROUND, (5_000, 15_000)),
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000)),
    )

    # Summed the members would read 40_000; the union is (0, 15_000) and (20_000, 30_000).
    assert one.total_uptime_ms == 25_000


def test_a_side_carrying_some_members_merges_what_it_has() -> None:
    [one] = merged(
        an_aura(SANGUINE_GROUND, (0, 10_000)),
        an_aura(BLOOD_SOAKED_GROUND, (5_000, 20_000)),
    )

    assert bands_of(one) == ((0, 20_000),)
    assert one.total_uptime_ms == 20_000


def test_the_merged_aura_takes_the_main_id_even_when_the_main_is_absent() -> None:
    [one] = merged(an_aura(SANGUINE_GROUND, (0, 10_000)))

    assert one.ability_id == DND


def test_a_lone_member_keeps_its_own_name() -> None:
    [one] = merged(an_aura(BLOOD_SOAKED_GROUND, (0, 10_000)))

    assert one.name == "Blood-Soaked Ground"


def test_two_members_read_main_with_the_other() -> None:
    [one] = merged(
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
    )

    assert one.name == "Death and Decay, with Sanguine Ground"


def test_three_members_read_main_with_the_others_joined_by_and() -> None:
    [one] = merged(
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000)),
    )

    assert one.name == "Death and Decay, with Sanguine Ground and Blood-Soaked Ground"


def test_four_members_comma_every_name_but_the_last() -> None:
    four = AuraGroups(groups=((1, 2, 3, 4),))
    auras = carrying(*(an_aura(n, (0, 10_000), name=f"Member {n}") for n in (1, 2, 3, 4)))

    [one] = merge_aura_groups(auras, four).on_self

    assert one.name == "Member 1, with Member 2, Member 3 and Member 4"


def test_the_names_follow_the_groups_order_and_not_the_order_the_table_listed_them_in() -> None:
    [one] = merged(
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000)),
        an_aura(DND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
    )

    assert one.name == "Death and Decay, with Sanguine Ground and Blood-Soaked Ground"


def test_without_the_main_the_first_present_member_leads_the_name() -> None:
    [one] = merged(
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
    )

    assert one.name == "Sanguine Ground, with Blood-Soaked Ground"


def test_the_icon_is_the_mains_when_the_main_is_present() -> None:
    [one] = merged(
        an_aura(SANGUINE_GROUND, (0, 10_000), icon="sanguine"),
        an_aura(DND, (0, 10_000), icon="deathanddecay"),
    )

    assert one.icon == "deathanddecay"


def test_the_icon_is_the_first_present_members_when_the_main_is_absent() -> None:
    [one] = merged(
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000), icon="blood-soaked"),
        an_aura(SANGUINE_GROUND, (0, 10_000), icon="sanguine"),
    )

    assert one.icon == "sanguine"


def test_the_uses_are_the_mains_when_the_main_is_present_and_the_first_members_otherwise() -> None:
    with_main = merged(
        an_aura(SANGUINE_GROUND, (0, 10_000), uses=9),
        an_aura(DND, (0, 10_000), uses=4),
    )
    without_main = merged(
        an_aura(BLOOD_SOAKED_GROUND, (0, 10_000), uses=2),
        an_aura(SANGUINE_GROUND, (0, 10_000), uses=9),
    )

    assert with_main[0].uses == 4
    assert without_main[0].uses == 9


def test_a_side_carrying_no_member_gets_no_merged_aura() -> None:
    unrelated = an_aura(55233, (0, 10_000), name="Vampiric Blood")

    assert merged(unrelated) == (unrelated,)


def test_auras_in_no_group_pass_through_unchanged_and_in_order() -> None:
    first = an_aura(100, (0, 5_000), name="First")
    second = an_aura(200, (0, 6_000), name="Second")
    third = an_aura(300, (0, 7_000), name="Third")

    result = merged(first, an_aura(DND, (0, 10_000)), second, third)

    assert result[0] == first
    assert result[2:] == (second, third)


def test_the_merged_aura_sits_where_the_first_present_member_was() -> None:
    before = an_aura(100, (0, 5_000), name="Before")
    between = an_aura(200, (0, 6_000), name="Between")
    after = an_aura(300, (0, 7_000), name="After")

    result = merged(
        before,
        an_aura(SANGUINE_GROUND, (0, 10_000)),
        between,
        an_aura(DND, (0, 10_000)),
        after,
    )

    assert [one.ability_id for one in result] == [100, DND, 200, 300]


def test_two_groups_on_one_side_each_fold_into_their_own_aura() -> None:
    result = merged(
        an_aura(DND, (0, 10_000)),
        an_aura(DANCE_OF_MIDNIGHT, (0, 8_000)),
        an_aura(SANGUINE_GROUND, (0, 10_000)),
        an_aura(DANCING_RUNE_WEAPON, (4_000, 12_000)),
    )

    assert [(one.ability_id, bands_of(one)) for one in result] == [
        (DND, ((0, 10_000),)),
        (DANCING_RUNE_WEAPON, ((0, 12_000),)),
    ]


def test_the_actor_is_kept() -> None:
    assert merge_aura_groups(carrying(an_aura(DND, (0, 10_000))), GROUPS).actor_id == 7


def test_no_groups_leave_the_auras_as_they_were() -> None:
    auras = carrying(an_aura(DND, (0, 10_000)), an_aura(SANGUINE_GROUND, (0, 10_000)))

    assert merge_aura_groups(auras, AuraGroups()) == auras


def test_a_group_of_one_id_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two"):
        AuraGroups(groups=((DND,),))


def test_an_id_in_two_groups_is_refused() -> None:
    with pytest.raises(ValueError, match="188290"):
        AuraGroups(groups=((DND, SANGUINE_GROUND), (BLOOD_SOAKED_GROUND, DND)))
