# ABOUTME: Behaviour tests for comparing what a player drank against what the sample drank.
# ABOUTME: Absent auras are a real state; a player with no aura table is not a player with none.

from wowperf.domain.auras import Aura, PlayerAuras
from wowperf.domain.comparison.consumables import compare_consumable_buffs
from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player, Run
from wowperf.domain.season import ConsumableBuffs

BUFFS = ConsumableBuffs(
    entries=(("flask", (1235057, 1235110)), ("food", (451920, 1219182)))
)
OUR_NAME = "Emberkin (actor 693)"

# Sample members are synthetic references, never the player under comparison, so
# their names are drawn from the sanctioned set too — cycled rather than reusing
# one name five times only because a run's roster of one name each is easier to
# read while debugging a failure.
SAMPLE_NAMES = ("Stonewake", "Bríala", "Кириллица")


def auras_with(*ability_ids: int) -> PlayerAuras:
    return PlayerAuras(
        actor_id=693,
        on_self=tuple(
            Aura(ability_id=i, name=f"aura {i}", total_uptime_ms=600_000, uses=1)
            for i in ability_ids
        ),
    )


def _reference_run(player: Player) -> Run:
    return Run(
        report_code="REF",
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
        players=(player,),
        pulls=(),
    )


def a_sample_with(*per_member: tuple[int, ...] | None) -> ParseSample:
    """One member per tuple, each carrying the auras that tuple names.

    `None` in a member's place means that member's aura table was never
    fetched — the state `ParseSample.aura_eligible` excludes, and which this
    module must not read as "carried nothing".
    """
    members = []
    for index, ability_ids in enumerate(per_member):
        actor_id = 100 + index
        name = SAMPLE_NAMES[index % len(SAMPLE_NAMES)]
        player = Player(
            actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=300
        )
        auras = (
            PlayerAuras(
                actor_id=actor_id,
                on_self=tuple(
                    Aura(ability_id=i, name=f"aura {i}", total_uptime_ms=600_000, uses=1)
                    for i in ability_ids
                ),
            )
            if ability_ids is not None
            else None
        )
        members.append(
            ParseMember(
                row=ParseRow(
                    report_code=f"REF{actor_id}",
                    fight_id=1,
                    keystone_level=16,
                    duration_ms=1_000_000,
                    character_name=name,
                    class_name="DeathKnight",
                    spec="Blood",
                ),
                run=_reference_run(player),
                auras=auras,
            )
        )
    return ParseSample(members=tuple(members))


def test_a_category_the_whole_sample_had_and_we_did_not_is_a_finding() -> None:
    sample = a_sample_with((1235057,), (1235110,), (1235057,), (1235057,), (1235110,))
    findings = compare_consumable_buffs(auras_with(451920), OUR_NAME, sample, BUFFS)
    # The category is folded into the id: two categories missing at once must
    # not mint the same id and collide into one page element id.
    assert [f.id for f in findings] == ["compare.consumables.buff.flask"]
    assert "flask" in findings[0].title
    assert findings[0].confidence is Confidence.MEASURED


def test_any_id_in_the_category_counts_as_having_it() -> None:
    # Well Fed spans six ids. Which one a player drank is not the question.
    sample = a_sample_with(*[(451920,)] * 5)
    assert compare_consumable_buffs(auras_with(1219182), OUR_NAME, sample, BUFFS) == []


def test_a_category_only_some_of_the_sample_had_is_not_a_finding() -> None:
    sample = a_sample_with((1235057,), (1235057,), (), (), ())
    assert compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS) == []


def test_nothing_is_compared_when_our_aura_table_is_absent() -> None:
    # Absent auras are a real state and not an empty one: a player whose table
    # was never fetched must not be reported as having drunk nothing.
    sample = a_sample_with(*[(1235057,)] * 5)
    assert compare_consumable_buffs(None, OUR_NAME, sample, BUFFS) == []


def test_a_member_with_no_aura_table_is_not_counted_as_lacking_it() -> None:
    sample = a_sample_with((1235057,), (1235057,), (1235057,), None, None)
    findings = compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS)
    assert "3 of 3" in " ".join(findings[0].evidence)


def test_nothing_is_compared_below_the_sample_floor() -> None:
    sample = a_sample_with((1235057,), (1235057,))
    assert compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS) == []


def test_a_category_most_but_not_all_of_the_sample_had_is_not_a_finding() -> None:
    """Four of five is a majority, not unanimity — the same distinction
    `compare_enchants` draws. Relaxing the rule to "most of the sample carried
    it" would report this category; unanimity must not."""
    sample = a_sample_with((1235057,), (1235057,), (1235057,), (1235057,), ())
    assert compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS) == []


def test_two_missing_categories_are_each_reported_with_their_own_name() -> None:
    """A bug that pairs one category's name with another's id list, or that
    reports every finding under the first category iterated, would still
    produce two findings here — only checking each one's own name and count
    against its own evidence line catches it."""
    sample = a_sample_with(
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
    )
    findings = compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS)

    assert len(findings) == 2
    by_category = {
        category: finding
        for finding in findings
        for category in ("flask", "food")
        if category in finding.title
    }
    assert set(by_category) == {"flask", "food"}
    assert "category flask" in by_category["flask"].evidence[0]
    assert "category food" in by_category["food"].evidence[0]
    assert "food" not in by_category["flask"].title
    assert "flask" not in by_category["food"].title


def test_two_missing_categories_produce_distinct_finding_ids() -> None:
    # `_for_player` appends `.{slug}` uniformly with no dedup, so two rows
    # sharing one id before that suffix would mint the identical element id
    # twice -- invalid HTML, and `report.js` resolves `location.hash` through
    # `getElementById`, so the collision is live, not cosmetic. Asserted on
    # `finding.id` directly: the title/evidence check above cannot see this.
    sample = a_sample_with(
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
        (1235057, 451920),
    )
    findings = compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS)
    ids = [f.id for f in findings]
    assert len(ids) == 2
    assert len(set(ids)) == len(ids)
    assert set(ids) == {"compare.consumables.buff.flask", "compare.consumables.buff.food"}


def test_the_finding_carries_a_quantifier_for_the_narrative() -> None:
    # `quantifier` is what a digit-free narrative echoes in place of a count;
    # empty here would silently strand the narrative with nothing to say.
    sample = a_sample_with(*[(1235057,)] * 5)
    findings = compare_consumable_buffs(auras_with(), OUR_NAME, sample, BUFFS)
    assert findings[0].quantifier == "every"


def test_sample_floor_constant_is_used_rather_than_a_literal() -> None:
    # Pins the fixture's own assumption: the floor test above relies on 2
    # being below MIN_SAMPLE_FOR_AGGREGATE. If that constant ever moved down
    # to 2 or below, the floor test would start reporting where it must not.
    assert MIN_SAMPLE_FOR_AGGREGATE > 2
