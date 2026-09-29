# ABOUTME: What the other healers were doing in a dying player's last seconds, read off the casts.
# ABOUTME: Where their casts were aimed and where their group cooldowns stood: facts, no verdict.

from collections.abc import Sequence

from wowperf.domain.analysis.cooldown_reading import (
    CooldownReading,
    Reading,
    dead_at,
    read_cooldown,
)
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns


class TargetCounts(Frozen):
    """A healer's casts in the run-up, by where each was aimed.

    A target is a player when its id is on the roster; anything else -- an
    enemy, a pet -- is a non-player. `None` is an untargeted cast.
    """

    at_player: int = 0
    at_self: int = 0
    at_other_players: int = 0
    at_non_players: int = 0
    untargeted: int = 0

    @property
    def total(self) -> int:
        return (
            self.at_player + self.at_self + self.at_other_players + self.at_non_players
            + self.untargeted
        )


class HealerCooldown(Frozen):
    """One group healing cooldown a healer holds, and where it stood as the run-up opened."""

    ability: CooldownAbility
    reading: CooldownReading


class HealerSide(Frozen):
    """One other healer at one death.

    `cooldowns` leaves out every cooldown never pressed in the log read, and
    is empty for a dead healer: a dead player presses nothing. `listed` is how
    many group healing cooldowns the healer's specialisation lists at all, so
    a caller can tell "none listed" from "none pressed".
    """

    healer: Player
    dead: bool
    casts: TargetCounts
    last_at_player_ms: int | None
    cooldowns: tuple[HealerCooldown, ...] = ()
    listed: int = 0


def healer_side(
    death: Death,
    players: Sequence[Player],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    roles: Roles,
    throughput: ThroughputCooldowns,
    visible_from_ms: int,
) -> tuple[HealerSide, ...]:
    """Every other healer's side of one death, in roster order.

    The window is the card's run-up, `RUN_UP_SECONDS` before the death. Each
    group healing cooldown -- an entry marked `group` under the healer's
    specialisation -- is read as the run-up opens, the card's rule that
    availability is judged from when the damage began, by the same rule the
    heavy-moment finding reads it (`read_cooldown`).
    """
    death_ms = death.timestamp_ms
    opens_ms = int(death_ms - RUN_UP_SECONDS * 1000)
    roster = {player.actor_id for player in players}
    sides: list[HealerSide] = []
    for healer in players:
        if healer.actor_id == death.actor_id:
            continue
        if roles.role_of(healer.class_name, healer.spec) != "healer":
            continue
        own = [
            cast
            for cast in casts
            if cast.actor_id == healer.actor_id and opens_ms <= cast.timestamp_ms <= death_ms
        ]
        counts = TargetCounts(
            at_player=sum(cast.target_id == death.actor_id for cast in own),
            at_self=sum(cast.target_id == healer.actor_id for cast in own),
            at_other_players=sum(
                cast.target_id is not None
                and cast.target_id in roster
                and cast.target_id not in (death.actor_id, healer.actor_id)
                for cast in own
            ),
            at_non_players=sum(
                cast.target_id is not None
                and cast.target_id not in roster
                and cast.target_id != death.actor_id
                for cast in own
            ),
            untargeted=sum(cast.target_id is None for cast in own),
        )
        at_player = [cast.timestamp_ms for cast in own if cast.target_id == death.actor_id]
        dead = dead_at(healer.actor_id, death_ms, casts, deaths, resurrections)
        marked = [
            one for one in throughput.for_spec(healer.class_name, healer.spec) if one.group
        ]
        readings = (
            ()
            if dead
            else tuple(
                HealerCooldown(ability=ability, reading=reading)
                for ability in marked
                if (reading := read_cooldown(
                    ability, healer.actor_id, casts, deaths, resurrections,
                    pressed_from_ms=opens_ms,
                    judged_at_ms=opens_ms,
                    pressed_until_ms=death_ms,
                    visible_from_ms=visible_from_ms,
                )).reading is not Reading.UNSEEN
            )
        )
        sides.append(
            HealerSide(
                healer=healer,
                dead=dead,
                casts=counts,
                last_at_player_ms=max(at_player) if at_player else None,
                cooldowns=readings,
                listed=len(marked),
            )
        )
    return tuple(sides)
