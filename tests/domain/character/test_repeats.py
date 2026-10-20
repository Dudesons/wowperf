# ABOUTME: Behaviour tests for the judgements one character's runs made again and again.
# ABOUTME: Families join across runs by id shape and ability, never by a run's own slug or rank.

import re

from tests.domain.character.builders import a_finding, a_run
from wowperf.domain.character.patterns import (
    ANALYSIS_FAMILIES_NOT_COUNTED,
    family_of,
    repeated_judgements,
)
from wowperf.domain.findings import Confidence, Finding

CARESS = 195292


def caress_gap(rank: int, slug: str = "emberkin-0") -> Finding:
    return a_finding(f"compare.spells.trash.rate.{rank}.{slug}", slug=slug,
                     ability_id=CARESS, ability_name="Death's Caress")


def test_the_same_family_under_two_slugs_and_two_ranks_is_one_family() -> None:
    assert family_of(a_finding("compare.spells.trash.rate.0.emberkin-0"), "emberkin-0") == (
        "compare.spells.trash.rate")
    assert family_of(a_finding("compare.spells.trash.rate.3.emberkin-2", slug="emberkin-2"),
                     "emberkin-2") == "compare.spells.trash.rate"


def test_a_judgement_in_three_of_five_runs_is_reported_with_its_quantifier() -> None:
    runs = [a_run(0, findings=(caress_gap(0),)), a_run(1, findings=(caress_gap(3, "emberkin-2"),),
            slug="emberkin-2"), a_run(2, findings=(caress_gap(1),)), a_run(3), a_run(4)]

    [finding] = repeated_judgements(runs)

    assert finding.id == f"character.repeat.compare.spells.trash.rate.{CARESS}"
    assert finding.title == (
        "Top parses cast Death's Caress more often than you on trash, in 3 of 5 runs")
    assert finding.quantifier == "most"
    assert finding.ability_id == CARESS
    assert finding.ability_name == "Death's Caress"
    assert finding.seconds_lost is None
    assert finding.evidence[0] == "Altar of Fangs +18: A run's own title"


def test_fewer_than_three_runs_is_never_a_pattern_even_at_half() -> None:
    runs = [a_run(0, findings=(caress_gap(0),)), a_run(1, findings=(caress_gap(0),)),
            a_run(2), a_run(3)]
    assert repeated_judgements(runs) == []


def test_under_half_the_runs_is_not_a_pattern() -> None:
    runs = [a_run(i, findings=(caress_gap(0),) if i < 3 else ()) for i in range(8)]
    assert repeated_judgements(runs) == []


def test_exactly_half_is_a_pattern_about_half_the_time() -> None:
    runs = [a_run(i, findings=(caress_gap(0),) if i < 4 else ()) for i in range(8)]
    [finding] = repeated_judgements(runs)
    assert finding.quantifier == "about half"


def test_a_teammates_judgement_is_not_counted() -> None:
    teammate = a_finding("compare.spells.trash.rate.0.stonewake-1", slug="stonewake-1",
                         ability_id=CARESS, ability_name="Death's Caress")
    runs = [a_run(i, findings=(teammate,)) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_statements_that_always_appear_are_never_counted() -> None:
    always = (a_finding("compare.duration", slug=""), a_finding("compare.downtime", slug=""),
              a_finding("compare.spells.level.emberkin-0"),
              a_finding("compare.uptime.unjudged.emberkin-0"),
              a_finding("compare.uptime.debuff.unjudged.emberkin-0"))
    runs = [a_run(i, findings=always) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_a_talent_statement_is_never_counted() -> None:
    # `compare.talents` is minted under the one id whether the build could not
    # be compared, matched, or differed, so firing in every run says nothing.
    talents = a_finding("compare.talents.emberkin-0", confidence=Confidence.MEASURED)
    runs = [a_run(i, findings=(talents,)) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_two_skipped_packs_in_one_run_count_that_run_once() -> None:
    skipped = (a_finding("compare.route.skipped.0", slug=""),
               a_finding("compare.route.skipped.1", slug=""))
    runs = [a_run(i, findings=skipped) for i in range(3)] + [a_run(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == "character.repeat.compare.route.skipped"
    assert finding.title == "The group pulled a pack fast runs skipped, in 3 of 4 runs"


def test_a_prefix_family_names_what_its_id_names() -> None:
    haste = a_finding("compare.stats.rating.haste.emberkin-0")
    runs = [a_run(i, findings=(haste,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == "character.repeat.compare.stats.rating.haste"
    assert "haste" in finding.title


def test_a_bare_enchant_slot_keeps_its_slot_index_as_its_family() -> None:
    # The slot is an int folded into the id, so it reads like a rank index; it
    # names what was judged and must survive, or no enchant ever counts.
    bare = a_finding("compare.gear.enchant.7.emberkin-0", confidence=Confidence.MEASURED)
    runs = [a_run(i, findings=(bare,)) for i in range(4)]

    assert family_of(bare, "emberkin-0") == "compare.gear.enchant.7"
    [finding] = repeated_judgements(runs)
    assert finding.id == "character.repeat.compare.gear.enchant.7"
    assert finding.title == "Top parses enchanted a slot you left bare (slot 7), in 4 of 4 runs"


def test_two_bare_enchant_slots_are_two_families() -> None:
    bare = (a_finding("compare.gear.enchant.7.emberkin-0"),
            a_finding("compare.gear.enchant.15.emberkin-0"))
    runs = [a_run(i, findings=bare) for i in range(3)]

    assert [finding.id for finding in repeated_judgements(runs)] == [
        "character.repeat.compare.gear.enchant.15", "character.repeat.compare.gear.enchant.7"]


def test_fewer_tier_pieces_is_worded_as_fewer() -> None:
    tier = a_finding("compare.gear.tier.emberkin-0")
    runs = [a_run(i, findings=(tier,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.title == "You wore fewer tier pieces than top parses, in 3 of 3 runs"


def test_a_missing_consumable_buff_names_its_category_in_plain_words() -> None:
    rune = a_finding("compare.consumables.buff.augment-rune.emberkin-0",
                     confidence=Confidence.MEASURED)
    runs = [a_run(i, findings=(rune,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == "character.repeat.compare.consumables.buff.augment-rune"
    assert finding.title == (
        "Top parses carried a consumable buff you did not: augment rune, in 3 of 3 runs")


def test_an_ability_without_a_name_still_carries_its_id_on_both_sides() -> None:
    unnamed = a_finding("compare.spells.trash.rate.0.emberkin-0", ability_id=CARESS)
    runs = [a_run(i, findings=(unnamed,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.id == f"character.repeat.compare.spells.trash.rate.{CARESS}"
    assert finding.ability_id == CARESS


def test_a_buff_gap_is_worded_as_presence_never_agency() -> None:
    gap = a_finding("compare.uptime.self.0.emberkin-0", ability_id=433925,
                    ability_name="Visceral Strength")
    runs = [a_run(i, findings=(gap,)) for i in range(3)]

    [finding] = repeated_judgements(runs)

    assert finding.title == (
        "Visceral Strength was up less of the key for you than for top parses, in 3 of 3 runs")


def test_the_count_wears_the_least_certain_badge_it_counts() -> None:
    # `compare.gear.tier` is minted `derived` (comparison/loadout.py, compare_tier).
    def tier(confidence: Confidence) -> Finding:
        return a_finding("compare.gear.tier.emberkin-0", confidence=confidence)

    runs = [a_run(0, findings=(tier(Confidence.MEASURED),)),
            a_run(1, findings=(tier(Confidence.DERIVED),)),
            a_run(2, findings=(tier(Confidence.MEASURED),))]
    [finding] = repeated_judgements(runs)
    assert finding.confidence is Confidence.DERIVED


def test_the_analysis_families_are_not_counted_in_this_slice() -> None:
    analysis = (a_finding("defensives.ceiling.emberkin.48792", slug=""),
                a_finding("consumables.never.Emberkin", slug=""))
    runs = [a_run(i, findings=analysis) for i in range(4)]
    assert repeated_judgements(runs) == []


def test_the_note_on_uncounted_families_names_each_and_no_counted_one() -> None:
    """The note reaches the page and `character.json`. The combat-potion and
    consumable-buff comparisons are counted, so it may say healing consumables,
    never consumables bare."""
    for family in ("deaths", "missed interrupts", "defensives", "healing consumables",
                   "throughput cooldowns", "heavy moments of damage", "talents"):
        assert family in ANALYSIS_FAMILIES_NOT_COUNTED, family
    qualifiers = re.findall(r"(\w+)[ -]consumable", ANALYSIS_FAMILIES_NOT_COUNTED.lower())
    assert qualifiers and set(qualifiers) == {"healing"}
