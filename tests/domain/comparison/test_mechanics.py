# ABOUTME: The mechanics comparison: which references it draws, and what it states.
# ABOUTME: Size is matched, not annotated, because the rate is over a whole raid.

from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
    compare_mechanics,
    hostile_rows,
    select_reference_kills,
)
from wowperf.domain.comparison.sample import SAMPLE_SIZE


def kill(code: str, size: int) -> ReferenceKillRow:
    return ReferenceKillRow(
        report_code=code, fight_id=1, size=size,
        duration_ms=480000, deaths=0,
    )


def test_only_references_of_our_own_size_are_drawn() -> None:
    rows = (kill("a", 20), kill("b", 30), kill("c", 20), kill("d", 14))
    drawn = select_reference_kills(rows, our_size=20)
    assert [row.report_code for row in drawn] == ["a", "c"]


def test_no_more_than_the_sample_size_is_drawn() -> None:
    rows = tuple(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3))
    drawn = select_reference_kills(rows, our_size=20)
    assert len(drawn) == SAMPLE_SIZE


def ability(ability_id: int, name: str, hits: int, sources: tuple[str, ...]) -> AbilityTakenRow:
    return AbilityTakenRow(
        ability_id=ability_id, ability_name=name, hit_count=hits, source_types=sources
    )


def member(
    code: str, abilities: tuple[AbilityTakenRow, ...], seconds: float = 120.0
) -> MechanicsMember:
    # Its own row rather than `kill()`: the duration is the denominator under
    # test, so it has to be visible here and equal to ours, or a rate
    # comparison would be testing two things at once.
    return MechanicsMember(
        row=ReferenceKillRow(
            report_code=code, fight_id=1, size=20,
            duration_ms=int(seconds * 1000), deaths=0,
        ),
        abilities=abilities,
    )


def test_a_row_sourced_only_by_players_is_not_a_mechanic() -> None:
    rows = (
        ability(6940, "Blessing of Sacrifice", 2, ("Warrior",)),
        ability(400, "Ravenous Feast", 4, ("Boss",)),
    )
    assert [row.ability_id for row in hostile_rows(rows)] == [400]


def test_an_unrecognised_source_type_is_kept() -> None:
    # The filter fails toward showing a mechanic. A hostile type this code has
    # never seen must not make an ability disappear in silence.
    rows = (ability(401, "Coiling Ichor", 9, ("Leviathan",)),)
    assert [row.ability_id for row in hostile_rows(rows)] == [401]


def test_an_ability_we_took_far_more_of_than_the_sample_is_a_finding() -> None:
    # Ours: 12 landings in 120s = 6.0 a minute. The five references took
    # 1, 2, 3, 4 and 5 in 120s: a median of 3 landings, 1.5 a minute.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (1, 2, 3, 4, 5)
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "a 4x gap against five references should state something"
    assert findings[0].id.startswith("mechanics.ability.")
    # Both sides of this finding are rates this function divided out, and
    # `FindingFact`'s own rule is that a rate the report computed is derived.
    # Its own facts already badge the identical figures that way.
    assert findings[0].confidence.value == "derived"
    # Both absolute rates are pinned, not only their ratio. A ratio is
    # scale-free, so an assertion resting on it alone survives deleting the
    # per-minute conversion from both sides -- mutation shape 2. The sample
    # median (1.5) also differs from its max (2.5) and its mean (1.5 here is
    # both, so the rates are 0.5/1.0/1.5/2.0/2.5 and only the median is 1.5).
    assert any("6.0" in line for line in findings[0].evidence), "our own rate"
    assert any("1.5" in line for line in findings[0].evidence), "the sample median rate"
    # The claim is a count, never an intent. Master design 5.5 refuses the
    # latter, and names four words that would smuggle it back in. Checked
    # over every finding the call produced, and both the title and the
    # detail of each -- a single word slipping past one of the eight checks
    # is exactly how "avoidable" shipped past a check that only tried "missed".
    for finding in findings:
        for word in ("missed", "avoidable", "should have", "failed"):
            assert word not in finding.title.lower(), finding.title
            assert word not in finding.detail.lower(), finding.detail


def test_a_reference_tick_count_counts_toward_its_landings() -> None:
    # A channelled tick lands just as certainly as a hit. If a reference's rate
    # were read from hit_count alone, every fixture elsewhere in this file
    # would still pass -- none gives a reference a tick_count, so landings and
    # hit_count agree everywhere else. This is the one fixture that gives a
    # reference a nonzero tick_count, so the median actually moves if hits
    # alone were substituted for landings.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    ticking = AbilityTakenRow(
        ability_id=400, ability_name="Ravenous Feast", hit_count=1, tick_count=4,
        source_types=("Boss",),
    )
    sample = MechanicsSample(
        members=(
            member("a", (ticking,)),
            *(
                member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
                for index in (2, 3, 4, 5)
            ),
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings
    # Landings per reference: 5, 2, 3, 4, 5 in 120s -> 2.5, 1.0, 1.5, 2.0, 2.5 a
    # minute; median 2.0. Reading hit_count alone instead gives 1, 2, 3, 4, 5
    # landings -> a median of 1.5, which is a different, wrong number.
    assert any("2.0" in line for line in findings[0].evidence), "ticks must count as landings"


def test_a_reference_with_zero_duration_is_dropped_before_dividing() -> None:
    # Nothing upstream refuses a zero-duration reference: select_reference_kills
    # matches size only, and ReferenceKillRow.duration_ms is a plain int with
    # no lower bound. A member like this must be dropped before
    # the loop divides by its duration, not after, and it must not still be
    # counted in the reference total the evidence and quantifier read.
    ours = (ability(400, "Ravenous Feast", 24, ("Boss",)),)
    broken = member("broken", (ability(400, "Ravenous Feast", 50, ("Boss",)),), seconds=0.0)
    sample = MechanicsSample(
        members=(
            broken,
            member("a", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("b", (ability(400, "Ravenous Feast", 4, ("Boss",)),)),
            member("c", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "the call must not raise, and the three valid references still compare"
    # Surviving landings 2, 4, 6 in 120s -> 1.0, 2.0, 3.0 a minute; median 2.0.
    # Had the broken member instead been kept with its rate specialcased to
    # zero, the median over four values would read 1.5, not 2.0. Had it been
    # kept out of the rates but left in the denominator, the total would read
    # 4, not 3.
    assert any("2.0" in line for line in findings[0].evidence), "median over survivors only"
    assert any(
        "3 of 3" in line for line in findings[0].evidence
    ), "the broken member must not count toward the total"


def test_an_ability_in_line_with_the_sample_states_nothing() -> None:
    ours = (ability(400, "Ravenous Feast", 3, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (2, 3, 3, 4, 3)
        )
    )
    assert compare_mechanics(ours, 120.0, sample, scope="the raid") == []


def test_the_title_states_our_own_side_as_a_rate_and_not_as_a_count() -> None:
    # The title's two halves have to be the same kind of number. 24 landings
    # over 240s is 6.0 a minute, so a count and a rate are visibly different
    # here -- a fixture over 60s would make them equal and could not tell a
    # correct title from a broken one. The references took 3, 4 and 5 over
    # their own 240s: 0.75, 1.0 and 1.25 a minute, a median of 1.0 that is
    # neither the lowest nor the highest of them.
    ours = (ability(400, "Ravenous Feast", 24, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(code, (ability(400, "Ravenous Feast", landings, ("Boss",)),), seconds=240.0)
            for code, landings in (("first", 3), ("second", 4), ("third", 5))
        )
    )
    findings = compare_mechanics(ours, 240.0, sample, scope="the raid")
    assert findings, "a 6x gap against three references should state something"
    title = findings[0].title
    assert "6.0 times a minute" in title, title
    assert "a median of 1.0 a minute" in title, title
    assert "24" not in title, f"the title states a count beside a per-minute figure: {title}"
    # The count is not lost by stating a rate; it moves to where it reads as one.
    assert any(
        fact.label == "Landings" and fact.value == "24" for fact in findings[0].facts
    ), "the absolute count must survive as a fact"


def test_below_the_aggregate_floor_the_finding_says_it_is_one_reference() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("only", (ability(400, "Ravenous Feast", 1, ("Boss",)),)),)
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "one reference is still a comparison, stated as one"
    assert any("single reference" in line for line in findings[0].evidence)
    assert any("reference kill only fight 1" in line for line in findings[0].evidence)


def test_two_references_are_stated_as_one_reference_rather_than_as_a_median() -> None:
    """Below the floor, `too_few`'s note has to be true of the finding it joins.

    The note reads "a single reference, not an aggregate", so the finding it is
    appended to must state a single reference. The two members here differ on
    purpose: 2 landings in 120s is 1.0 a minute and 6 is 3.0, so a median over
    the pair would read 2.0 and a range 1.0 to 3.0 -- numbers that appear
    nowhere below, and whose appearance is exactly the contradiction this pins.
    """
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(
            member("first", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("second", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    [one] = compare_mechanics(ours, 120.0, sample, scope="the raid")

    assert "the reference took 1.0 a minute" in one.title, one.title
    assert "median" not in one.title.lower(), one.title
    assert any("single reference" in line for line in one.evidence)
    assert any("reference kill first fight 1" in line for line in one.evidence)

    stated = " ".join(one.evidence)
    assert "2.0" not in stated, f"a median over the two references reached the evidence: {stated}"
    assert "range" not in stated, stated
    assert "2 of 2" not in stated, stated
    assert one.quantifier == "", "a single reference is not an aggregate over a sample"


def test_at_the_aggregate_floor_the_finding_states_a_median_and_carries_no_note() -> None:
    # Three comparable references is the floor. 2, 4 and 6 landings in 120s
    # are 1.0, 2.0 and 3.0 a minute: the median is 2.0 and equals neither end
    # of the range the evidence states beside it.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(
            member("first", (ability(400, "Ravenous Feast", 2, ("Boss",)),)),
            member("second", (ability(400, "Ravenous Feast", 4, ("Boss",)),)),
            member("third", (ability(400, "Ravenous Feast", 6, ("Boss",)),)),
        )
    )
    [one] = compare_mechanics(ours, 120.0, sample, scope="the raid")

    assert "a median of 2.0 a minute" in one.title, one.title
    assert not any("single reference" in line for line in one.evidence), one.evidence
    assert any("range 1.0 to 3.0" in line for line in one.evidence), one.evidence
    assert any("3 of 3 references took it at all" in line for line in one.evidence), one.evidence


def test_an_empty_sample_states_nothing_rather_than_everything() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    assert compare_mechanics(ours, 120.0, MechanicsSample(), scope="the raid") == []
