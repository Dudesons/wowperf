# ABOUTME: The one defensive claim a combat log can support: never cast at all.
# ABOUTME: Labelled inferred, because no event says whether a cooldown was available.

from collections import defaultdict

from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import Defensives


def analyse_defensives(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
) -> list[Finding]:
    """Name defensives a player never pressed at any point in the run.

    Deliberately narrow. "Should have used it there" needs to know the cooldown
    was up, and the log emits no cooldown-reset or reduction events, so that
    claim is not available at any confidence level.
    """
    cast_ids: dict[int, set[int]] = defaultdict(set)
    for cast in casts:
        cast_ids[cast.actor_id].add(cast.ability_id)

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        known = defensives.for_spec(player.class_name, player.spec)
        pressed = cast_ids.get(player.actor_id, set())
        for ability in known:
            if ability.ability_id in pressed:
                continue
            # Two players can share a display name; disambiguate the id with the
            # actor id only when that happens, so the common case stays readable.
            finding_id = (
                f"defensives.{player.name}.{ability.ability_id}"
                if name_counts[player.name] == 1
                else f"defensives.{player.name}.{player.actor_id}.{ability.ability_id}"
            )
            findings.append(
                Finding(
                    id=finding_id,
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
