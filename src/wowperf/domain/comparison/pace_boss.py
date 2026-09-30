# ABOUTME: Picks the boss, or a council's bosses, out of one fight's own enemy actors.
# ABOUTME: Boss flag, the fight's enemy list and the fight's name; no hand-written boss list.

from wowperf.domain.base import Frozen

BOSS_SUB_TYPE = "Boss"


class NpcActor(Frozen):
    """One enemy actor of a report, as `masterData.actors(type: "NPC")` lists it."""

    actor_id: int
    game_id: int
    name: str
    sub_type: str


def _named_after(name: str, fight_name: str) -> bool:
    """The fight's name, or its opening words: "Grimtooth" names "Grimtooth the Vile"."""
    return bool(name) and (name == fight_name or fight_name.startswith(f"{name} "))


def find_bosses(
    actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], fight_name: str
) -> tuple[NpcActor, ...]:
    """The fight's boss, a council's bosses, or none, read from its own enemies.

    Measured 2026-10-01: a boss-flagged actor's name can differ from the
    fight's ("Vashnik" in "Vashnik the Malignant"), a single-boss fight can
    list boss-flagged adds beside its boss, and a council lists its bosses
    with none named after the fight. So the candidates are the boss-flagged
    actors this fight lists; one named after the fight is the boss alone;
    otherwise every candidate is, one being a boss under another name and
    several a council. Two named after the fight is a shape never measured,
    and is no boss rather than a guess.
    """
    candidates = tuple(
        one for one in actors if one.sub_type == BOSS_SUB_TYPE and one.actor_id in enemy_ids
    )
    named = [one for one in candidates if _named_after(one.name, fight_name)]
    if len(named) == 1:
        return (named[0],)
    if named:
        return ()
    return candidates
