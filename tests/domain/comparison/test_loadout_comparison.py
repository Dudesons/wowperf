# ABOUTME: Behaviour tests for the gear and stat comparison families.
# ABOUTME: item_sourced is asymmetric on purpose: a match is evidence, a miss is not.

import re

from wowperf.domain.comparison.loadout import (
    compare_enchants,
    compare_stats,
    compare_tier,
    item_sourced,
    loadouts_of,
)
from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import ParseMember
from wowperf.domain.findings import Confidence
from wowperf.domain.loadout import TIER_SLOTS, EquippedItem, Loadout, StatBlock
from wowperf.domain.model import Player, Run
from wowperf.domain.season import SlotNames

OUR_NAME = "Stonewake (actor 7)"


def an_item(**changes: object) -> EquippedItem:
    fields: dict[str, object] = {
        "item_id": 250225,
        "slot": 12,
        "name": "Tablet of the Stonewake",
        "item_level": 331,
        "enchant_id": None,
        "enchant_name": None,
        "set_id": None,
    }
    fields.update(changes)
    return EquippedItem(**fields)  # type: ignore[arg-type]


def a_loadout(*items: EquippedItem) -> Loadout:
    return Loadout(items=items or (an_item(),))


def test_an_ability_named_after_an_equipped_item_resolves_to_it() -> None:
    # Measured 2026-09-14: Warcraft Logs names an on-use trinket's spell after
    # the item. Four of ten equipped trinkets matched the ability dictionary.
    found = item_sourced("Tablet of the Stonewake", [a_loadout()])
    assert found is not None
    assert found.item_id == 250225


def test_an_ability_matching_no_equipped_item_resolves_to_nothing() -> None:
    # A miss means unknown, never "this is a class spell". The measurement
    # shows a match indicates an item source; it does not show every
    # item-sourced ability matches by name.
    assert item_sourced("Arcane Blast", [a_loadout()]) is None


def test_any_loadout_in_the_sample_can_supply_the_match() -> None:
    others = [a_loadout(an_item(name="Bríala's Ember")), a_loadout(an_item(name="Ashen Coil"))]
    found = item_sourced("Ashen Coil", others)
    assert found is not None
    assert found.name == "Ashen Coil"


def test_no_loadouts_at_all_resolve_to_nothing() -> None:
    assert item_sourced("Ashen Coil", []) is None


def test_the_match_is_exact_rather_than_loose() -> None:
    # A substring rule would fold "Rune of Sanguination" into a rune consumable
    # and a "Tablet" into every tablet; the join is worth having only if it is
    # precise.
    assert item_sourced("Tablet", [a_loadout()]) is None
    assert item_sourced("tablet of the stonewake", [a_loadout()]) is None


# --- loadouts_of -------------------------------------------------------------


def a_reference_run(*players: Player) -> Run:
    return Run(
        report_code="REF1",
        fight_id=1,
        dungeon_name="Den of Stonewake",
        encounter_id=1,
        keystone_level=16,
        affix_ids=(),
        keystone_time_ms=1_000_000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=players,
        pulls=(),
    )


def a_reference_member(player: Player, *roster: Player) -> ParseMember:
    """A parse reference whose own report rosters `player` alongside `roster`."""
    return ParseMember(
        row=ParseRow(
            report_code="REF1",
            fight_id=1,
            keystone_level=16,
            duration_ms=1_000_000,
            character_name=player.name,
            class_name=player.class_name,
            spec=player.spec,
        ),
        run=a_reference_run(player, *roster),
    )


def test_loadouts_of_collects_each_members_own_players_loadout() -> None:
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout(an_item(name="Ashen Coil")))
    stonewake = Player(actor_id=12, name="Stonewake", class_name="Priest", spec="Shadow",
                        item_level=328, loadout=a_loadout(an_item(name="Bríala's Ember")))

    found = loadouts_of([a_reference_member(briala), a_reference_member(stonewake)])

    assert len(found) == 2
    assert {loadout.items[0].name for loadout in found} == {"Ashen Coil", "Bríala's Ember"}


def test_loadouts_of_skips_a_member_whose_loadout_was_never_fetched() -> None:
    # The speed axis, and every already-cached run, never fetch a loadout at
    # all -- `Player.loadout` stays None rather than an empty `Loadout`, and
    # that must not be mistaken for "equipped nothing".
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout())
    kirillica = Player(actor_id=13, name="Кириллица", class_name="Warrior", spec="Fury",
                        item_level=325)

    found = loadouts_of([a_reference_member(briala), a_reference_member(kirillica)])

    assert len(found) == 1
    assert found[0] is briala.loadout


def test_loadouts_of_skips_a_member_whose_player_cannot_be_found() -> None:
    # A row naming a character the report's own roster does not contain -- the
    # same gap `find_player` already has to handle -- contributes nothing
    # rather than raising.
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout())
    ghost = ParseMember(
        row=ParseRow(
            report_code="REF2", fight_id=2, keystone_level=16, duration_ms=1_000_000,
            character_name="Nobody", class_name="Mage", spec="Arcane",
        ),
        run=a_reference_run(briala),
    )

    found = loadouts_of([ghost])

    assert found == ()


# --- compare_enchants --------------------------------------------------------


def test_a_slot_everyone_enchanted_and_we_did_not_is_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME)
    assert len(findings) == 1
    # The slot is folded in: two missing slots must not mint the same id and
    # collide into one page element id once `_for_player` appends the player.
    assert findings[0].id == "compare.gear.enchant.7"
    assert findings[0].confidence is Confidence.MEASURED
    assert "slot 7" in findings[0].evidence[0]


def test_with_no_slot_names_loaded_the_title_falls_back_to_the_raw_index() -> None:
    # `slot_names` defaults to an empty `SlotNames`, which every caller that
    # has not loaded the data file gets -- the whole test module above this
    # one, in particular.
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME)
    assert findings[0].title == f"5 of 5 top parses enchanted slot 7; {OUR_NAME} did not"


def test_a_known_slot_is_named_in_the_title() -> None:
    # A reader must know that slot 7 is feet to act on this finding -- the one
    # family whose whole job is "go do this specific thing".
    slot_names = SlotNames(entries=((7, "feet"),))
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME, slot_names)
    assert findings[0].title == f"5 of 5 top parses enchanted the feet; {OUR_NAME} did not"
    # The slot index is kept in the evidence even once the title names it.
    assert "slot 7" in findings[0].evidence[0]


def test_an_unidentified_slot_falls_back_to_its_raw_index_rather_than_a_guess() -> None:
    # Slots 3 and 17 were never identified. A `SlotNames` naming every other
    # slot must still fall back for these two rather than inventing a name.
    slot_names = SlotNames(entries=((7, "feet"), (12, "trinket")))
    theirs = [a_loadout(an_item(slot=3, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=3, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME, slot_names)
    assert findings[0].title == f"5 of 5 top parses enchanted slot 3; {OUR_NAME} did not"


def test_two_missing_enchant_slots_produce_distinct_finding_ids() -> None:
    # `_for_player` appends `.{slug}` uniformly with no dedup, so two rows
    # sharing one id before that suffix would mint the identical element id
    # twice -- invalid HTML, and `report.js` resolves `location.hash` through
    # `getElementById`, so the collision is live, not cosmetic.
    theirs = [
        a_loadout(an_item(slot=7, enchant_id=8017), an_item(slot=8, enchant_id=8020))
        for _ in range(5)
    ]
    ours = a_loadout(an_item(slot=7, enchant_id=None), an_item(slot=8, enchant_id=None))
    findings = compare_enchants(ours, theirs, OUR_NAME)
    ids = [f.id for f in findings]
    assert len(ids) == 2
    assert len(set(ids)) == len(ids)
    assert set(ids) == {"compare.gear.enchant.7", "compare.gear.enchant.8"}


def test_a_slot_the_sample_left_bare_is_not_a_finding() -> None:
    # Measured 2026-09-14: the off hand was enchanted by 1 of 10 players. A
    # hardcoded enchantable-slot list would flag nine of them; letting the
    # sample define the rule flags none.
    theirs = [a_loadout(an_item(slot=16, enchant_id=None)) for _ in range(5)]
    ours = a_loadout(an_item(slot=16, enchant_id=None))
    assert compare_enchants(ours, theirs, OUR_NAME) == []


def test_a_slot_only_some_of_the_sample_enchanted_is_not_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=16, enchant_id=8017))] + [
        a_loadout(an_item(slot=16, enchant_id=None)) for _ in range(4)
    ]
    assert compare_enchants(a_loadout(an_item(slot=16, enchant_id=None)), theirs, OUR_NAME) == []


def test_a_slot_most_but_not_all_of_the_sample_enchanted_is_not_a_finding() -> None:
    # Four of five is a majority, not unanimity. Relaxing the rule to "most of
    # the sample enchanted it" would report this slot; unanimity must not.
    theirs = [a_loadout(an_item(slot=16, enchant_id=8017)) for _ in range(4)] + [
        a_loadout(an_item(slot=16, enchant_id=None))
    ]
    assert compare_enchants(a_loadout(an_item(slot=16, enchant_id=None)), theirs, OUR_NAME) == []


def test_a_slot_we_enchanted_too_is_not_a_finding() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    ours = a_loadout(an_item(slot=7, enchant_id=9000))
    assert compare_enchants(ours, theirs, OUR_NAME) == []


def test_a_slot_we_have_no_item_in_is_not_a_finding() -> None:
    # An empty slot is a different claim from an unenchanted one, and the tool
    # has no opinion about a player choosing to wear nothing there.
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    assert compare_enchants(a_loadout(an_item(slot=0)), theirs, OUR_NAME) == []


def test_nothing_is_compared_without_our_loadout() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(5)]
    assert compare_enchants(None, theirs, OUR_NAME) == []


def test_nothing_is_compared_below_the_sample_floor() -> None:
    theirs = [a_loadout(an_item(slot=7, enchant_id=8017)) for _ in range(2)]
    assert compare_enchants(a_loadout(an_item(slot=7, enchant_id=None)), theirs, OUR_NAME) == []


# --- compare_tier -------------------------------------------------------------


def a_tier_loadout(pieces: int) -> Loadout:
    slots = sorted(TIER_SLOTS)[:pieces]
    return Loadout(items=tuple(an_item(slot=slot, set_id=2062) for slot in slots))


def test_fewer_tier_pieces_than_the_sample_median_is_a_finding() -> None:
    findings = compare_tier(a_tier_loadout(2), [a_tier_loadout(4) for _ in range(5)], OUR_NAME)
    assert len(findings) == 1
    assert findings[0].id == "compare.gear.tier"
    assert findings[0].confidence is Confidence.DERIVED


def test_the_tier_finding_is_derived_because_the_slot_rule_is_inferred() -> None:
    # The API states no tier flag. The rule is read off seven observed sets,
    # so the badge must not claim the log said it.
    findings = compare_tier(a_tier_loadout(2), [a_tier_loadout(4) for _ in range(5)], OUR_NAME)
    assert findings[0].confidence is Confidence.DERIVED


def test_matching_the_sample_median_is_not_a_finding() -> None:
    assert compare_tier(a_tier_loadout(4), [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []


def test_more_tier_pieces_than_the_sample_is_not_a_finding() -> None:
    assert compare_tier(a_tier_loadout(5), [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []


def test_the_finding_states_the_median_and_the_range() -> None:
    # Asserted as the literal rendered phrases, not bare digits: "2", "4" and
    # "5" each also appear in evidence[0]'s slot list or in the reference
    # count, so a bare-digit check passes even if the median and range are
    # wrong (swapped, or replaced outright) -- only the exact phrase ties the
    # assertion to the values this test claims to verify.
    theirs = [a_tier_loadout(2), a_tier_loadout(4), a_tier_loadout(4), a_tier_loadout(5),
              a_tier_loadout(5)]
    findings = compare_tier(a_tier_loadout(0), theirs, OUR_NAME)
    stats = findings[0].evidence[1]
    assert "sample median 4" in stats
    assert "range 2 to 5" in stats


def test_nothing_is_compared_below_the_sample_floor_for_tier() -> None:
    assert compare_tier(a_tier_loadout(0), [a_tier_loadout(4) for _ in range(2)], OUR_NAME) == []


def test_nothing_is_compared_without_our_loadout_for_tier() -> None:
    assert compare_tier(None, [a_tier_loadout(4) for _ in range(5)], OUR_NAME) == []


def test_the_median_is_not_a_mean() -> None:
    # [0, 0, 4, 4, 4] has median 4 but mean 2.4. Wearing 3 pieces sits below the
    # median and above the mean: a mean-based comparison would let this pass,
    # and only a median-based one reports it. This is the case
    # test_the_finding_states_the_median_and_the_range cannot rule out, because
    # its sample's mean and median both land on 4.
    theirs = [a_tier_loadout(0), a_tier_loadout(0), a_tier_loadout(4), a_tier_loadout(4),
              a_tier_loadout(4)]
    findings = compare_tier(a_tier_loadout(3), theirs, OUR_NAME)
    assert len(findings) == 1
    # The literal phrase, not a bare "4": a bare digit also matches the slot
    # list in evidence[0], so it would not prove the median (rather than the
    # mean, 2.4) is what got reported.
    assert "sample median 4" in findings[0].evidence[1]


# --- compare_stats -------------------------------------------------------------


def a_stat_loadout(**ratings: int) -> Loadout:
    return Loadout(items=(an_item(),), stats=StatBlock(**ratings))


def test_each_secondary_that_differs_gets_a_row() -> None:
    ours = a_stat_loadout(crit=900, haste=900, mastery=400, versatility=0)
    theirs = [a_stat_loadout(crit=900, haste=900, mastery=1400, versatility=0) for _ in range(5)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    assert [f.id for f in findings] == ["compare.stats.rating.mastery"]
    assert "mastery" in findings[0].title


def test_two_secondaries_moving_at_once_produce_two_distinct_ids() -> None:
    # A real gear difference routinely moves more than one secondary's share
    # past STAT_GAP_SHARE at once. `_for_player` appends an identical player
    # slug to every row this function returns, so two rows sharing one id here
    # would collide into one page element id -- exactly the failure
    # `compare_enchants` folds in the slot to avoid and `compare_consumable_buffs`
    # folds in the category to avoid. Checking titles or evidence, as every
    # other test in this section does, cannot see this: only the ids collide.
    ours = a_stat_loadout(crit=500, haste=500, mastery=200, versatility=0)
    theirs = [
        a_stat_loadout(crit=1000, haste=200, mastery=1400, versatility=100) for _ in range(5)
    ]
    findings = compare_stats(ours, theirs, OUR_NAME)
    ids = [f.id for f in findings]
    assert len(ids) == 2
    assert len(set(ids)) == len(ids)
    assert set(ids) == {"compare.stats.rating.haste", "compare.stats.rating.mastery"}


def test_the_row_states_our_rating_the_median_and_the_range() -> None:
    # crit is held equal on both sides so only mastery's rating differs. A
    # StatBlock with mastery as its only nonzero stat would make
    # total_secondary() equal to that one rating, collapsing every share to
    # 100% regardless of its size -- STAT_GAP_SHARE could never clear and the
    # row would never print.
    ours = a_stat_loadout(crit=1000, mastery=400)
    theirs = [a_stat_loadout(crit=1000, mastery=r) for r in (1290, 1400, 1480, 1500, 1602)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    joined = " ".join(findings[0].evidence)
    assert "400" in joined
    assert "1480" in joined
    assert "1290" in joined and "1602" in joined


def test_the_row_also_states_the_share_of_the_secondary_budget() -> None:
    # The raw gap between a top parse and this player largely restates item
    # level. The share is the part a decision can change.
    ours = a_stat_loadout(crit=800, mastery=200)
    theirs = [a_stat_loadout(crit=200, mastery=800) for _ in range(5)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    joined = " ".join(f.detail for f in findings)
    assert "%" in joined


def test_the_share_values_are_correct_not_swapped() -> None:
    # The test above only checks that some percentage sign appears somewhere
    # -- a detail with the two shares reversed, or entirely made up, would
    # still contain a "%". crit is held equal on both sides so exactly one row
    # (mastery) exists, and its exact, directional phrasing is asserted: ours
    # first, then the sample's.
    ours = a_stat_loadout(crit=1000, mastery=200)
    theirs = [a_stat_loadout(crit=1000, mastery=800) for _ in range(5)]
    findings = compare_stats(ours, theirs, OUR_NAME)
    assert len(findings) == 1
    assert (
        "17% of this player's secondary rating against 44% of the sample's"
        in findings[0].detail
    )


def test_a_stat_nobody_has_produces_no_row() -> None:
    ours = a_stat_loadout(crit=900)
    theirs = [a_stat_loadout(crit=900) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME) == []


def test_a_small_share_difference_produces_no_row_despite_a_rating_gap() -> None:
    # The raw mastery rating differs (400 vs 430) but both loadouts spend
    # nearly the same share of their own budget on it -- under STAT_GAP_SHARE,
    # so nothing is worth printing. This is the case a flipped comparison
    # (printing when the gap is small rather than skipping it) would get
    # backwards, and that test_each_secondary_that_differs_gets_a_row's large
    # gap cannot rule out on its own.
    ours = a_stat_loadout(crit=900, mastery=400)
    theirs = [a_stat_loadout(crit=900, mastery=430) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME) == []


def test_rows_are_badged_derived() -> None:
    ours = a_stat_loadout(crit=1000, mastery=400)
    theirs = [a_stat_loadout(crit=1000, mastery=1400) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME)[0].confidence is Confidence.DERIVED


def test_no_row_states_a_percentage_of_the_rating_itself() -> None:
    # Converting a rating to a percentage needs a per-level coefficient with no
    # source in this API. The only percentage permitted is the share of budget.
    #
    # Asserted as an allowlist over every "%" token in the whole finding
    # (title, detail and evidence), not a blocklist of specific strings like
    # "400%": a blocklist only catches a percentage spelled out in that exact
    # form. The fixture's numbers keep every rating-derived ratio distinct
    # from the two legitimate shares: this player's own rating over the
    # sample's median rating (400 / 1500 = 27%) matches neither share (29%,
    # 60%), so a stray percentage computed from a rating rather than a share
    # cannot slip past this check unnoticed.
    ours = a_stat_loadout(crit=1000, mastery=400)
    theirs = [a_stat_loadout(crit=1000, mastery=1500) for _ in range(5)]
    finding = compare_stats(ours, theirs, OUR_NAME)[0]
    rendered = finding.title + " " + finding.detail + " " + " ".join(finding.evidence)
    our_share_pct = f"{400 / 1400:.0%}"
    their_share_pct = f"{1500 / 2500:.0%}"
    assert {our_share_pct, their_share_pct} == {"29%", "60%"}  # sanity-check the fixture math
    assert set(re.findall(r"\d+%", rendered)) == {our_share_pct, their_share_pct}


def test_nothing_is_compared_without_our_loadout_for_stats() -> None:
    theirs = [a_stat_loadout(mastery=1400) for _ in range(5)]
    assert compare_stats(None, theirs, OUR_NAME) == []


def test_nothing_is_compared_when_our_stats_were_withheld() -> None:
    ours = Loadout(items=(an_item(),), stats=None)
    theirs = [a_stat_loadout(mastery=1400) for _ in range(5)]
    assert compare_stats(ours, theirs, OUR_NAME) == []


def test_a_reference_whose_stats_were_withheld_is_not_counted() -> None:
    ours = a_stat_loadout(crit=1000, mastery=400)
    theirs = [a_stat_loadout(crit=1000, mastery=1400) for _ in range(3)] + [
        Loadout(items=(an_item(),), stats=None) for _ in range(2)
    ]
    findings = compare_stats(ours, theirs, OUR_NAME)
    assert "3 references" in " ".join(findings[0].evidence)


def test_nothing_is_compared_below_the_sample_floor_for_stats() -> None:
    # Named "..._for_stats": test_nothing_is_compared_below_the_sample_floor
    # already exists above for compare_enchants. Pasted verbatim, Python would
    # silently rebind that name and pytest would run only the last definition.
    #
    # Both sides carry an equal crit baseline, the same way
    # test_the_row_states_our_rating_the_median_and_the_range does above: a
    # loadout with mastery as its only nonzero stat makes total_secondary()
    # equal to that one rating, collapsing every share to 100% regardless of
    # the floor guard -- STAT_GAP_SHARE would suppress the row on its own, and
    # the floor below the sample size would never get a chance to.
    ours = a_stat_loadout(crit=1000, mastery=400)
    theirs = [a_stat_loadout(crit=1000, mastery=1400) for _ in range(2)]
    assert compare_stats(ours, theirs, OUR_NAME) == []
