# ABOUTME: Picks the boss out of a report's enemy actors, by its boss flag and the fight's name.
# ABOUTME: Anything but exactly one match is no boss, which is what a council encounter reads as.

from wowperf.domain.base import Frozen

BOSS_SUB_TYPE = "Boss"


class NpcActor(Frozen):
    """One enemy actor of a report, as `masterData.actors(type: "NPC")` lists it."""

    actor_id: int
    game_id: int
    name: str
    sub_type: str


def find_boss_actor(actors: tuple[NpcActor, ...], fight_name: str) -> NpcActor | None:
    """The one actor flagged a boss and named after the fight, or None.

    Both halves are needed, measured 2026-09-27: the flag alone also marks adds
    that carry a boss frame, and the name alone also matches a same-named actor
    flagged `NPC` that took no damage.
    """
    matches = [
        one for one in actors if one.sub_type == BOSS_SUB_TYPE and one.name == fight_name
    ]
    return matches[0] if len(matches) == 1 else None
