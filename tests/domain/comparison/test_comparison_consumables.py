# ABOUTME: Behaviour tests for comparing what a player drank against what the sample drank.
# ABOUTME: Absent auras are a real state; a player with no aura table is not a player with none.

from wowperf.domain.auras import Aura, PlayerAuras
from wowperf.domain.comparison.consumables import compare_consumable_buffs, compare_potions
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, ParseMember, ParseSample
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Player, Run
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
        run = _reference_run(player)
        members.append(
            ParseMember(
                character_name=name,
                report_code=f"REF{actor_id}",
                fight_id=1,
                boss_seconds=boss_seconds(run.pulls),
                players=run.players,
                auras=auras,
                pulls=run.pulls,
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


LABELLED = ConsumableBuffs(
    entries=(("flask", (1235057, 1235110)), ("food", (451920, 1219182))),
    labels=(("flask", "a flask"), ("food", "food")),
)


def test_a_mass_noun_category_is_not_given_an_article() -> None:
    """Found by forcing this family to fire on a real log: the title read
    "3 of 5 top parses carried a food". "a flask" and "an augment rune" take an
    article and "food" does not, and no rule derived from the spelling can tell
    those apart, so the phrasing is data.
    """
    sample = a_sample_with(*[(451920,)] * 5)
    findings = compare_consumable_buffs(auras_with(1235057), OUR_NAME, sample, LABELLED)
    assert findings[0].title == f"5 of 5 top parses carried food; {OUR_NAME} did not"


def test_a_countable_category_keeps_its_article() -> None:
    # The other half of the pair: the fix must not strip the article from the
    # categories that need one.
    sample = a_sample_with(*[(1235057,)] * 5)
    findings = compare_consumable_buffs(auras_with(451920), OUR_NAME, sample, LABELLED)
    assert findings[0].title == f"5 of 5 top parses carried a flask; {OUR_NAME} did not"


def test_a_category_with_no_label_falls_back_to_its_bare_name() -> None:
    # Every caller that has not loaded the data file gets an unlabelled
    # `ConsumableBuffs`, and a title without an article still reads.
    sample = a_sample_with(*[(1235057,)] * 5)
    findings = compare_consumable_buffs(auras_with(451920), OUR_NAME, sample, BUFFS)
    assert findings[0].title == f"5 of 5 top parses carried flask; {OUR_NAME} did not"


def test_the_detail_makes_no_claim_about_the_sample_the_title_could_contradict() -> None:
    """The detail used to spell "every comparable reference carried one" in
    prose while the count beside it was computed. That is true only while the
    gate demands unanimity, and it is spelled under a `measured` badge -- so
    loosening the gate would have made the page lie without touching the
    sentence. The count belongs in one place, and the title already has it.
    """
    sample = a_sample_with(*[(1235057,)] * 5)
    detail = compare_consumable_buffs(auras_with(451920), OUR_NAME, sample, LABELLED)[0].detail
    assert "every comparable reference" not in detail
    assert "5" not in detail


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


# --- compare_potions: cast counts, not aura uptime -----------------------------

OURS = Player(actor_id=693, name="Emberkin", class_name="DeathKnight", spec="Blood", item_level=318)

POTION = 1236994
# A different consumable entirely (a health potion's id from consumables.toml),
# used only to prove a count that ignored ability id would read too high.
DECOY = 1234768


def _cast(actor_id: int, ability_id: int, at_ms: int) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name=f"ability {ability_id}",
        timestamp_ms=at_ms,
    )


def ours_casting(
    ability_id: int, times: int, *, other_ability: int | None = None, other_times: int = 0
) -> LoadedRun:
    """Our own run, pressing `ability_id` that many times.

    `other_ability`/`other_times` add casts of a second ability, for the one
    test that must prove only the requested id is counted.
    """
    casts = tuple(_cast(OURS.actor_id, ability_id, n * 1_000) for n in range(times))
    if other_ability is not None:
        casts += tuple(
            _cast(OURS.actor_id, other_ability, 500_000 + n * 1_000) for n in range(other_times)
        )
    return LoadedRun(run=_reference_run(OURS), casts=casts)


def a_member_pressing(
    actor_id: int, name: str, counts: dict[int, int], *, row_name: str | None = None
) -> ParseMember:
    """A reference over their own run, pressing each ability in `counts` that many times.

    `row_name`, left default, matches the roster so `their_actor_id` resolves
    normally. Set it to a name absent from the roster (another sanctioned name,
    never a fabricated one) to simulate a resolution failure -- the state that
    must drop a member from a statistic entirely rather than counting them as
    having drunk nothing.
    """
    player = Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=300
    )
    casts = tuple(
        _cast(actor_id, ability_id, n * 1_000)
        for ability_id, count in counts.items()
        for n in range(count)
    )
    run = _reference_run(player)
    return ParseMember(
        character_name=row_name if row_name is not None else name,
        report_code=f"REF{actor_id}",
        fight_id=1,
        boss_seconds=boss_seconds(run.pulls),
        players=run.players,
        casts=casts,
        pulls=run.pulls,
    )


def a_sample_casting_potion(count: int, members: int = 5) -> ParseSample:
    """A sample of `members` references whose potion-cast counts have a real median of `count`.

    Spread asymmetrically rather than uniformly: roughly half the members
    press it noticeably less than `count` and half noticeably more, so a mean
    would land far from `count` while the median still sits on it exactly. A
    fixture where every member drank the same amount could not tell a
    median-reading implementation from a mean-reading one apart -- this one can.
    """
    below_n = members // 2
    above_n = members // 2
    below = [max(count - (below_n - i), 0) for i in range(below_n)]
    above = [count + 10 * (i + 1) for i in range(above_n)]
    if members % 2 == 1:
        counts = below + [count] + above
    else:
        if below:
            below[-1] = max(count - 1, 0)
        if above:
            above[0] = count + 1
        counts = below + above

    return ParseSample(
        members=tuple(
            a_member_pressing(100 + i, SAMPLE_NAMES[i % len(SAMPLE_NAMES)], {POTION: c})
            for i, c in enumerate(counts)
        )
    )


def test_fewer_potions_than_the_sample_median_is_a_finding() -> None:
    findings = compare_potions(
        ours_casting(POTION, times=0), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
    )
    assert [f.id for f in findings] == ["compare.consumables.potion"]
    assert findings[0].confidence is Confidence.MEASURED


def test_matching_the_sample_median_is_not_a_finding() -> None:
    # Pins the boundary: our count equals the median exactly, and "at least as
    # much as the sample" must not be reported as a shortfall.
    assert (
        compare_potions(
            ours_casting(POTION, times=2), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
        )
        == []
    )


def test_more_potions_than_the_sample_is_not_a_finding() -> None:
    assert (
        compare_potions(
            ours_casting(POTION, times=4), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
        )
        == []
    )


def test_the_finding_states_the_median_and_the_range() -> None:
    findings = compare_potions(
        ours_casting(POTION, times=0), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
    )
    # Asserted as exact strings rather than "2 in ..." -- the sample's own
    # spread (0, 1, 2, 12, 22) contains other digits that a loose substring
    # check could not tell apart from the real median.
    assert findings[0].title == (
        "Emberkin (actor 693) drank 0 combat potions; the sample's median is 2"
    )
    assert findings[0].evidence == (
        "0 combat potions cast in this run",
        "sample median 2, range 0 to 22 across 5 references",
    )


def test_potions_are_not_compared_below_the_sample_floor() -> None:
    # Named distinctly from the buff family's own floor test above: two test
    # functions sharing a name in this file would silently delete the first,
    # with pytest reporting no error at all.
    sample = a_sample_casting_potion(2, members=2)
    assert compare_potions(ours_casting(POTION, times=0), OURS, OUR_NAME, sample, (POTION,)) == []


def test_no_potion_ids_means_no_comparison() -> None:
    # Cannot discriminate the `if not wanted` guard from its absence: with no
    # ids to look for, `_potion_casts` would count zero casts on every side
    # regardless, both `ours_count` and the sample's median would be 0, and
    # `ours_count >= their_median` would already return [] downstream. This
    # only proves the empty-ids case does not raise or otherwise misbehave.
    sample = a_sample_casting_potion(2)
    assert compare_potions(ours_casting(POTION, 0), OURS, OUR_NAME, sample, ()) == []


def test_a_different_ability_is_not_counted_towards_the_sample_median() -> None:
    """A count that summed every cast regardless of ability id would put this
    sample's median at 10, not 1: each reference presses a different
    consumable nine times and the potion only once."""
    sample = ParseSample(
        members=(
            a_member_pressing(101, "Stonewake", {POTION: 1, DECOY: 9}),
            a_member_pressing(102, "Bríala", {POTION: 1, DECOY: 9}),
            a_member_pressing(103, "Кириллица", {POTION: 1, DECOY: 9}),
        )
    )
    findings = compare_potions(ours_casting(POTION, 0), OURS, OUR_NAME, sample, (POTION,))
    assert findings[0].title.endswith("the sample's median is 1")


def test_only_the_requested_ability_is_counted_for_us() -> None:
    """A count that summed every cast regardless of ability id would read 5
    presses here, not 1."""
    ours = ours_casting(POTION, 1, other_ability=DECOY, other_times=4)
    findings = compare_potions(ours, OURS, OUR_NAME, a_sample_casting_potion(3), (POTION,))
    assert findings[0].evidence[0] == "1 combat potion cast in this run"


def test_an_unresolved_member_is_not_counted_as_having_drunk_nothing() -> None:
    """A bug that fell back to zero for an unresolved actor would compute a
    median of 2.5, not 3: three real references drink 2, 3 and 10, and a
    fourth whose row name matches nobody on their own roster must be dropped
    entirely rather than counted as zero."""
    sample = ParseSample(
        members=(
            a_member_pressing(101, "Stonewake", {POTION: 2}),
            a_member_pressing(102, "Bríala", {POTION: 3}),
            a_member_pressing(103, "Кириллица", {POTION: 10}),
            a_member_pressing(104, "Bríala", {POTION: 3}, row_name="Stonewake"),
        )
    )
    findings = compare_potions(ours_casting(POTION, 0), OURS, OUR_NAME, sample, (POTION,))
    assert findings[0].title.endswith("the sample's median is 3")


def test_an_unresolved_member_dropping_below_the_floor_is_not_compared() -> None:
    """Three members, but only two resolve to an actor in their own report --
    the effective sample is 2, below the floor, and must be treated exactly
    like any other sample that never reached it."""
    sample = ParseSample(
        members=(
            a_member_pressing(101, "Stonewake", {POTION: 3}),
            a_member_pressing(102, "Bríala", {POTION: 3}),
            a_member_pressing(103, "Кириллица", {POTION: 3}, row_name="Stonewake"),
        )
    )
    assert compare_potions(ours_casting(POTION, 0), OURS, OUR_NAME, sample, (POTION,)) == []


def test_the_finding_never_needs_a_player_discriminator() -> None:
    """`compare_potions` returns at most one row per call -- one player, one
    verdict -- unlike the buff family above, which folds a category into its
    id because it can emit several rows for one player. Pinned here so a
    future change that starts emitting more than one row is forced to add a
    discriminator rather than silently colliding two rows into one page
    element id."""
    findings = compare_potions(
        ours_casting(POTION, times=0), OURS, OUR_NAME, a_sample_casting_potion(2), (POTION,)
    )
    assert len(findings) == 1
    assert findings[0].id == "compare.consumables.potion"
