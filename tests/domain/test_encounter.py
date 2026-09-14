# ABOUTME: Behaviour tests for the raid encounter aggregate.
# ABOUTME: A boss fight is not a keystone, and this model is where that is enforced.

import pytest
from pydantic import ValidationError

from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.model import Player


def an_encounter(**overrides: object) -> Encounter:
    fields: dict[str, object] = dict(
        report_code="abc123",
        fight_id=22,
        encounter_id=3421,
        boss_name="The Twin Fangs",
        difficulty=4,
        partition=1,
        size=20,
        kill=True,
        fight_percentage=0.01,
        start_ms=1_000,
        end_ms=375_000,
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=700),
        ),
    )
    fields.update(overrides)
    return Encounter(**fields)  # type: ignore[arg-type]


def test_duration_is_the_span_of_the_fight_in_seconds() -> None:
    assert an_encounter(start_ms=1_000, end_ms=375_000).duration_seconds == 374.0


def test_a_kill_and_a_wipe_describe_themselves_differently() -> None:
    assert an_encounter(kill=True).outcome == "killed"
    assert an_encounter(kill=False, fight_percentage=16.49).outcome == "wiped at 16.5%"


def test_a_wipe_with_no_percentage_says_so_rather_than_printing_a_number() -> None:
    # fightPercentage is null on some fights. Defaulting it to zero would read
    # as "wiped at 0%", which is a kill.
    assert an_encounter(kill=False, fight_percentage=None).outcome == "wiped"


def test_an_encounter_is_frozen() -> None:
    with pytest.raises(ValidationError):
        an_encounter().boss_name = "something else"


def test_an_encounter_carries_no_keystone_vocabulary() -> None:
    # The whole point of a sibling aggregate. If these ever appear, the model has
    # drifted back towards Run and the analysers will start reading nulls.
    forbidden = {
        "keystone_level", "affix_ids", "affix_names", "keystone_time_ms",
        "keystone_bonus", "count_reached", "count_required", "npc_counts", "pulls",
    }
    present = forbidden & set(Encounter.model_fields)
    assert present == set(), f"Mythic+ fields leaked into Encounter: {sorted(present)}"


def test_a_loaded_encounter_defaults_every_stream_to_empty() -> None:
    loaded = LoadedEncounter(encounter=an_encounter())
    assert loaded.casts == ()
    assert loaded.deaths == ()
    assert loaded.damage_taken == ()
    assert loaded.auras == ()


def test_a_loaded_encounter_reads_its_icons_and_auras_as_mappings() -> None:
    loaded = LoadedEncounter(encounter=an_encounter(), ability_icons=((11, "icon.jpg"),))
    assert loaded.ability_icon_map[11] == "icon.jpg"
    assert loaded.auras_by_actor == {}
