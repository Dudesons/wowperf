# ABOUTME: Defensive claims a combat log can support: never cast at all, or cast far
# ABOUTME: below the cooldown ceiling. Both are inferred, never measured or a target.

from collections import defaultdict

from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import DefensiveAbility, Defensives

CEILING_USE_FRACTION = 0.5
"""How far below the ceiling a player must be before it is worth saying anything."""

MIN_CEILING_USES = 3.0
"""Below this the ceiling itself is too small to argue from."""


def _alive_combat_seconds(run: Run, deaths: tuple[Death, ...], actor_id: int) -> float | None:
    """Combat time this player could actually have pressed a button in.

    Returns `None` when any of this player's deaths has `seconds_until_next_action`
    of `None` — that death's cost cannot be measured because the player's last
    recorded action in the run was dying, so nothing follows it to measure to.
    There is no honest dead-time figure to subtract in that case, so there is no
    honest alive-time figure either; the caller must report no ceiling finding
    for this player rather than treat the unmeasured death as zero seconds dead.

    Otherwise approximate on purpose, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot. Overshooting lowers the ceiling, which makes the
    claim weaker rather than louder.
    """
    theirs = [death for death in deaths if death.actor_id == actor_id]
    if any(death.seconds_until_next_action is None for death in theirs):
        return None
    dead = sum(death.seconds_until_next_action or 0.0 for death in theirs)
    return max(run.total_pull_seconds - dead, 0.0)


def _ceiling(alive_seconds: float, ability: DefensiveAbility) -> float:
    """How many times the cooldown alone would have allowed this to be pressed."""
    return alive_seconds / ability.cooldown_seconds * ability.charges


def analyse_defensives(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Defensives never pressed (§5.6), and defensives pressed far below their ceiling (§5.7).

    Both are `inferred`. The log emits no cooldown-reset or reduction events, so
    neither claim can be measured, and a defensive is pressed into damage rather
    than on cooldown — the ceiling bounds what was possible, not what was right.
    """
    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        known = defensives.for_spec(player.class_name, player.spec)
        for ability in known:
            base_id = (
                f"{player.name}.{ability.ability_id}"
                if name_counts[player.name] == 1
                else f"{player.name}.{player.actor_id}.{ability.ability_id}"
            )
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)

            if uses:
                alive = _alive_combat_seconds(run, deaths, player.actor_id)
                if alive is None:
                    continue
                ceiling = _ceiling(alive, ability)
                if ceiling < MIN_CEILING_USES or uses >= ceiling * CEILING_USE_FRACTION:
                    continue
                findings.append(
                    Finding(
                        id=f"defensives.ceiling.{base_id}",
                        title=(
                            f"{player.name} used {ability.name} {uses} "
                            f"of a possible {ceiling:.0f} times"
                        ),
                        detail=(
                            f"{ability.name} has a {ability.cooldown_seconds:.0f}s cooldown, "
                            f"which fits {ceiling:.0f} times into the {alive:.0f}s this player "
                            "spent alive and in combat. That is a ceiling, not a target: a "
                            "defensive is pressed into incoming damage, not on cooldown, so a "
                            "gap here is a question to ask rather than a mistake to fix."
                        ),
                        confidence=Confidence.INFERRED,
                        seconds_lost=None,
                        evidence=(
                            f"{player.class_name} {player.spec}",
                            f"ability {ability.ability_id}",
                            f"{uses} cast{'s' if uses != 1 else ''} in {alive:.0f}s alive",
                        ),
                    )
                )
                continue

            findings.append(
                Finding(
                    id=f"defensives.{base_id}",
                    title=f"{player.name} never cast {ability.name}",
                    detail=(
                        f"{ability.name} was not cast at any point in the run. This is "
                        "inferred, not measured: the log records no cooldown state, so it "
                        "may have been unavailable, or the talent may not be taken."
                    ),
                    confidence=Confidence.INFERRED,
                    seconds_lost=None,
                    evidence=(
                        f"{player.class_name} {player.spec}",
                        f"ability {ability.ability_id}",
                        "zero casts in the whole run",
                    ),
                )
            )
    return findings
