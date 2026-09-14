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


def kill(code: str, size: int, difficulty: int = 4) -> ReferenceKillRow:
    return ReferenceKillRow(
        report_code=code, fight_id=1, difficulty=difficulty, size=size,
        duration_ms=480000, deaths=0,
    )


def test_only_references_of_our_own_size_are_drawn() -> None:
    rows = (kill("a", 20), kill("b", 30), kill("c", 20), kill("d", 14))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["a", "c"]


def test_a_reference_at_another_difficulty_is_refused() -> None:
    # Difficulty is matched exactly, never approximated: a Heroic pull against
    # Mythic references is meaningless, and design 13 refuses it rather than
    # annotating it.
    rows = (kill("a", 20, difficulty=5), kill("b", 20, difficulty=4))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["b"]


def test_no_more_than_the_sample_size_is_drawn() -> None:
    rows = tuple(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
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
            report_code=code, fight_id=1, difficulty=4, size=20,
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
    assert findings[0].confidence.value == "measured"
    # Both absolute rates are pinned, not only their ratio. A ratio is
    # scale-free, so an assertion resting on it alone survives deleting the
    # per-minute conversion from both sides -- mutation shape 2. The sample
    # median (1.5) also differs from its max (2.5) and its mean (1.5 here is
    # both, so the rates are 0.5/1.0/1.5/2.0/2.5 and only the median is 1.5).
    assert any("6.0" in line for line in findings[0].evidence), "our own rate"
    assert any("1.5" in line for line in findings[0].evidence), "the sample median rate"
    # The claim is a count, never an intent. Master design 5.5 refuses the latter.
    assert "missed" not in findings[0].title.lower()
    assert "missed" not in findings[0].detail.lower()


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


def test_an_ability_in_line_with_the_sample_states_nothing() -> None:
    ours = (ability(400, "Ravenous Feast", 3, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (2, 3, 3, 4, 3)
        )
    )
    assert compare_mechanics(ours, 120.0, sample, scope="the raid") == []


def test_below_the_aggregate_floor_the_finding_says_it_is_one_reference() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("a", (ability(400, "Ravenous Feast", 1, ("Boss",)),)),)
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "one reference is still a comparison, stated as one"
    assert any("single reference" in line for line in findings[0].evidence)


def test_an_empty_sample_states_nothing_rather_than_everything() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    assert compare_mechanics(ours, 120.0, MechanicsSample(), scope="the raid") == []
