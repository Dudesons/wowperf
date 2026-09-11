# ABOUTME: Behaviour tests for the run structure: pull classification, durations and signatures.
# ABOUTME: These models are pure data, so the tests cover only the derived properties.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run


def a_pull(index: int, start_ms: int, end_ms: int, encounter_id: int = 0,
           game_ids: tuple[int, ...] = (100,)) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name="Pull",
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=i, game_id=g) for i, g in enumerate(game_ids)),
    )


def a_run(pulls: tuple[Pull, ...] = ()) -> Run:
    return Run(
        report_code="abc123",
        fight_id=1,
        dungeon_name="Murder Row",
        encounter_id=12825,
        keystone_level=12,
        affix_ids=(9, 10),
        keystone_time_ms=1_800_000,
        keystone_bonus=1,
        count_reached=820,
        count_required=800,
        npc_counts=((100, 5),),
        players=(Player(actor_id=1, name="Someone", class_name="Mage",
                        spec="Frost", item_level=300),),
        pulls=pulls,
    )


def test_a_pull_with_a_non_zero_encounter_id_is_a_boss() -> None:
    assert a_pull(0, 0, 1000, encounter_id=3470).is_boss is True


def test_a_pull_with_encounter_id_zero_is_trash() -> None:
    assert a_pull(0, 0, 1000).is_boss is False


def test_pull_duration_converts_milliseconds_to_seconds() -> None:
    assert a_pull(0, 10_000, 41_500).duration_seconds == 31.5


def test_a_pull_signature_is_its_sorted_enemy_game_ids() -> None:
    assert a_pull(0, 0, 1, game_ids=(300, 100, 200, 100)).signature == (100, 100, 200, 300)


def test_total_pull_seconds_sums_every_pull() -> None:
    run = a_run((a_pull(0, 0, 30_000), a_pull(1, 60_000, 90_000)))
    assert run.total_pull_seconds == 60.0


def test_boss_and_trash_pulls_partition_the_run() -> None:
    run = a_run((a_pull(0, 0, 1000), a_pull(1, 2000, 3000, encounter_id=3470)))
    assert [p.index for p in run.trash_pulls] == [0]
    assert [p.index for p in run.boss_pulls] == [1]


def test_the_model_is_frozen() -> None:
    import pytest
    from pydantic import ValidationError

    pull = a_pull(0, 0, 1000)
    with pytest.raises(ValidationError):
        pull.index = 5


def test_the_npc_count_map_reads_as_a_mapping() -> None:
    assert a_run(()).npc_count_map == {100: 5}
    assert a_run(()).npc_count_map[100] == 5


def test_the_npc_count_map_cannot_be_mutated_through() -> None:
    import pytest

    run = a_run(())
    with pytest.raises(TypeError):
        run.npc_count_map[999] = 7  # type: ignore[index]
    assert run.npc_count_map == {100: 5}


def test_a_run_is_hashable_so_later_plans_can_put_it_in_a_set() -> None:
    run = a_run((a_pull(0, 0, 1000),))
    assert hash(run) == hash(a_run((a_pull(0, 0, 1000),)))
    assert len({run, a_run((a_pull(0, 0, 1000),))}) == 1


def test_a_run_carries_the_encounter_it_can_be_compared_against() -> None:
    assert a_run(pulls=()).encounter_id == 12825


def test_a_run_without_an_owner_says_so_rather_than_guessing() -> None:
    assert a_run(pulls=()).owner_name is None


def test_a_loaded_run_defaults_every_recap_stream_to_empty() -> None:
    loaded = LoadedRun(run=a_run())
    assert (loaded.health_samples, loaded.healing, loaded.resurrections) == ((), (), ())


def test_a_loaded_run_reads_its_icon_pairs_as_a_mapping() -> None:
    loaded = LoadedRun(
        run=a_run(), ability_icons=((48792, "spell_deathknight_iceboundfortitude.jpg"),)
    )
    assert loaded.ability_icon_map[48792] == "spell_deathknight_iceboundfortitude.jpg"


def test_a_loaded_run_with_no_icon_pairs_reads_an_empty_mapping() -> None:
    assert dict(LoadedRun(run=a_run()).ability_icon_map) == {}


def test_a_loaded_run_exposes_its_auras_by_actor() -> None:
    loaded = LoadedRun(
        run=a_run(),
        auras=(
            PlayerAuras(actor_id=7, on_self=(Aura(
                ability_id=48792, name="Icebound Fortitude", total_uptime_ms=8000, uses=1,
                bands=(AuraBand(start_ms=1000, end_ms=9000),),
            ),)),
        ),
    )
    assert loaded.auras_by_actor[7].on_self[0].name == "Icebound Fortitude"
    assert 99 not in loaded.auras_by_actor


def test_a_loaded_run_with_no_auras_has_an_empty_mapping() -> None:
    # A report built with --no-compare and no aura fetch must read as "no bands
    # known", never as a KeyError at draw time.
    assert dict(LoadedRun(run=a_run()).auras_by_actor) == {}
