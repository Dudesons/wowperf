# ABOUTME: Shared builders for progression tests: one attempt, one deepened attempt, one series.
# ABOUTME: Timestamps are offsets from the attempt's own start, because an_attempt offsets by id.

from tests.domain.test_progression import an_attempt
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import DamageTakenEvent, Death
from wowperf.domain.model import Player
from wowperf.domain.phases import Phase
from wowperf.domain.progression import LoadedProgression, Progression

PHASES = (
    Phase(id=1, name="The Gathering"),
    Phase(id=2, name="Intermission: Tide", is_intermission=True),
    Phase(id=3, name="The Drowning"),
)

# The roster `a_loaded_attempt` puts on an attempt whose caller names no
# roster of its own. Actor id 1 matches the default death dealer `actor_for`
# falls back to below, so an attempt built with no `players` argument still
# carries a roster its own death is a member of -- `_first_death_ms` reads
# only roster deaths, and an attempt whose encounter carries no roster at all
# would fail that filter for every death it has.
_DEFAULT_PLAYER: tuple[Player, ...] = (
    Player(actor_id=1, name="Emberkin", class_name="Paladin", spec="Holy", item_level=600),
)


def a_series(
    *attempts: Encounter,
    separates_wipes: bool = True,
    phases: tuple[Phase, ...] = PHASES,
) -> Progression:
    """A `Progression` around already-built attempts, with nothing discarded."""
    return Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        phases=phases,
        separates_wipes=separates_wipes,
        attempts=attempts,
    )


def a_loaded_attempt(
    fight_id: int,
    *,
    seconds: float = 200.0,
    remaining: float = 50.0,
    deaths_after_ms: tuple[int, ...] = (),
    damage_after_ms: tuple[tuple[int, int, int | None], ...] = (),
    players: tuple[Player, ...] = (),
    ability_names: dict[int, str] | None = None,
    **overrides: object,
) -> LoadedEncounter:
    """One deepened attempt.

    `deaths_after_ms` and `damage_after_ms` are offsets from this attempt's own
    start, because `an_attempt` places the window at `fight_id * 1_000_000`.
    Each `damage_after_ms` entry is `(offset, ability_id, source_id)`; a
    `source_id` of None means the log named no source.

    Deaths are dealt round-robin to `players` where a roster is given, so a
    test that cares which actor died first can say so by ordering the roster.
    Damage events are dealt the same way, for the same reason. Where no roster
    is given, the encounter still carries `_DEFAULT_PLAYER` -- actor id 1,
    matching the id every death and hit below falls back to -- so
    `_first_death_ms`'s roster filter has a roster to match against instead of
    discarding every death an attempt with no explicit `players` has.

    `ability_names` names each `DamageTakenEvent` by its `ability_id`, falling
    back to `"x"` for any id it does not cover. A finding reports names to a
    reader, never ids, so a test asserting on what the reader sees needs a
    real name to look for.
    """
    encounter = an_attempt(
        fight_id, remaining, seconds, players=players or _DEFAULT_PLAYER, **overrides
    )
    start_ms = encounter.start_ms

    def actor_for(index: int) -> tuple[int, str]:
        if not players:
            return 1, "Emberkin"
        dealt = players[index % len(players)]
        return dealt.actor_id, dealt.name

    deaths = tuple(
        Death(
            player_name=actor_for(index)[1],
            actor_id=actor_for(index)[0],
            timestamp_ms=start_ms + offset,
            killing_blow="x",
        )
        for index, offset in enumerate(deaths_after_ms)
    )

    damage_taken = tuple(
        DamageTakenEvent(
            actor_id=actor_for(index)[0],
            ability_id=ability_id,
            ability_name=(ability_names or {}).get(ability_id, "x"),
            amount=0,
            timestamp_ms=start_ms + offset,
            source_id=source_id,
        )
        for index, (offset, ability_id, source_id) in enumerate(damage_after_ms)
    )

    return LoadedEncounter(encounter=encounter, deaths=deaths, damage_taken=damage_taken)


def a_loaded_series(*loaded: LoadedEncounter, **series_kwargs: object) -> LoadedProgression:
    """A `LoadedProgression` whose `progression.attempts` are these attempts' encounters."""
    progression = a_series(*(one.encounter for one in loaded), **series_kwargs)  # type: ignore[arg-type]
    return LoadedProgression(progression=progression, loaded=loaded)
