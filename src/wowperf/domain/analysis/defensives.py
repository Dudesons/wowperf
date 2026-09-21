# ABOUTME: Defensive claims a combat log can support: cast far below the cooldown ceiling,
# ABOUTME: or off cooldown at a death. Both are inferred.

from collections import defaultdict
from collections.abc import Callable

from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, DefensiveAbility, Defensives
from wowperf.domain.slug import player_slug

CEILING_USE_FRACTION = 0.2
"""How far below the ceiling a player must be before it is worth saying anything.

Measured, not chosen by taste: run against a realistic 28-minute dungeon run
with realistic press counts, a 0.5 fraction fired on seven of eight pressed
defensives, including "used Prismatic Barrier 12 of a possible 67 times" —
escaping that finding would take 34 presses in one dungeon. Using a defensive
at close to half its theoretical maximum is ordinary play, not neglect; 0.2
fires only on genuine near-neglect instead of on almost everything pressed.

The throughput ceiling borrows this fraction rather than having measured its
own. That is one of the reasons that claim is asked for rather than given.
"""

MIN_CEILING_USES = 3.0
"""Below this the ceiling itself is too small to argue from."""

RUN_UP_SECONDS = 10.0
"""How much of the run-up to a death counts as the damage that killed the player.

An ability that came off cooldown halfway through that run-up was never an
option anyone had, so availability is judged from when the damage began rather
than from the instant of death. The report's death card shows this same window,
so a reader sees the damage a defensive could have answered — long enough to
read the sequence, short enough that the card stays a card.
"""


def defensives_up_at(
    casts: tuple[CastEvent, ...],
    abilities: tuple[DefensiveAbility, ...],
    actor_id: int,
    death_ms: int,
) -> tuple[str, ...]:
    """Names of `abilities` this player had off cooldown when the killing damage began.

    Two conditions, and the first is the one that keeps this honest.

    **The player must have cast the ability somewhere in the run.** Several
    entries in the data file are talent-gated, and a player who did not take the
    talent casts it nowhere — which looks exactly like having it and never
    pressing it. Reporting silence as availability would accuse someone of not
    pressing a button they do not own. An ability never cast at all is the death
    card's subject, where it reads as `unseen` beside the three other states a
    reader needs to weigh it against.

    **And they must have cast it at no point in `[death - (cooldown + run-up),
    death]`.** That one window does two jobs: it excludes an ability still on
    cooldown, and it excludes one they pressed during the run-up and died anyway.

    What remains resolves toward saying nothing. Base cooldowns are longer than
    talented ones; charges are ignored, so a spare charge reads as unavailable;
    the log emits no cooldown reset or reduction events, so a reset reads as
    unavailable; and casts are fetched for the fight, so one pressed before the
    timer started is invisible. Each understates what was up, and understating
    cannot produce a false accusation.

    Returned in the order the abilities were given, so a caller controls the
    reading order rather than inheriting a set's.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    return tuple(
        ability.name
        for ability in abilities
        if any(cast.ability_id == ability.ability_id for cast in ours)
        and not any(
            cast.ability_id == ability.ability_id
            and death_ms - (ability.cooldown_seconds + RUN_UP_SECONDS) * 1000
            <= cast.timestamp_ms
            <= death_ms
            for cast in ours
        )
    )


def analyse_defensives_at_death(
    players: tuple[Player, ...],
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
    *,
    locate: Callable[[Death], str],
) -> list[Finding]:
    """Players who died while a personal defensive was off cooldown.

    One finding per player rather than per death, because the question a reader
    asks is about the player, and the evidence carries each death separately.

    `inferred`, like every other claim in this module: availability is
    reconstructed from cast timestamps and a base cooldown, and the log records
    no cooldown state to check it against. A defensive is also pressed into
    incoming damage rather than on cooldown, so an unpressed one that was up is
    a question worth asking, never a verdict.

    Only abilities the player cast somewhere in the run are considered, so a
    talent they never took cannot be held against them. That leaves the never-cast
    case entirely to the death card, which shows it as `unseen` alongside the
    other states an ability can be in at a death.

    A spec absent from the data file produces nothing, which is not the same
    claim as a spec that had nothing available. The caller must keep those apart.

    `locate` renders where a death happened for the evidence line — a pull
    offset for a keystone, something else for a fight with no pulls to offset
    against.
    """
    # Counted on the slug rather than the name, because the slug is what the id
    # carries: `Bríala` and `Briala` are two players and one slug, and only the
    # actor id then tells their findings apart.
    slug_counts: dict[str, int] = defaultdict(int)
    for player in players:
        slug_counts[player_slug(player.name)] += 1

    findings = []
    for player in players:
        abilities = defensives.for_spec(player.class_name, player.spec)
        if not abilities:
            continue

        lines = []
        first_pull: int | None = None
        for death in sorted(
            (death for death in deaths if death.actor_id == player.actor_id),
            key=lambda death: death.timestamp_ms,
        ):
            up = defensives_up_at(casts, abilities, player.actor_id, death.timestamp_ms)
            if not up:
                continue
            if first_pull is None:
                first_pull = death.pull_index
            lines.append(
                f"{locate(death)} to {death.killing_blow}, with "
                f"{', '.join(up)} off cooldown"
            )

        if not lines:
            continue

        slug = player_slug(player.name)
        base_id = slug if slug_counts[slug] == 1 else f"{slug}.{player.actor_id}"
        times = "once" if len(lines) == 1 else f"{len(lines)} times"
        findings.append(
            Finding(
                id=f"defensives.unused.{base_id}",
                title=f"{player.name} died {times} with a defensive available",
                detail=(
                    "Availability is read from this player's own casts against the "
                    "ability's base cooldown, judged from when the damage that killed "
                    "them began. Only abilities they cast somewhere in the run count, so "
                    "a talent they never took is never held against them, and spare "
                    "charges and cooldown resets are ignored because the log does not "
                    "record them. A defensive is pressed into damage rather than on "
                    "cooldown, so this is a question to ask, not a mistake to fix."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=(f"{player.class_name} {player.spec}", *lines),
                pull_index=first_pull,
            )
        )
    return findings


def alive_combat_seconds(
    combat_seconds: float, deaths: tuple[Death, ...], actor_id: int
) -> float | None:
    """Combat time this player could actually have pressed a button in.

    `combat_seconds` is the denominator the caller's aggregate defines: summed
    pull time for a keystone, fight duration for a raid boss. Taking the number
    rather than the aggregate is what lets both ask this question; taking a
    `Run` meant a raid fight silently supplied zero.

    Returns `None` when any of this player's deaths has `seconds_until_next_action`
    of `None` -- that death's cost cannot be measured because the player's last
    recorded action was dying, so nothing follows it to measure to. There is no
    honest dead-time figure to subtract, so there is no honest alive-time figure
    either; the caller must report no ceiling finding for this player rather
    than treat the unmeasured death as zero seconds dead.

    Otherwise approximate on purpose, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot. Overshooting lowers the ceiling, which makes the
    claim weaker rather than louder.
    """
    theirs = [death for death in deaths if death.actor_id == actor_id]
    if any(death.seconds_until_next_action is None for death in theirs):
        return None
    dead = sum(death.seconds_until_next_action or 0.0 for death in theirs)
    return max(combat_seconds - dead, 0.0)


def cooldown_ceiling(alive_seconds: float, ability: CooldownAbility) -> float:
    """How many times the cooldown alone would have allowed this to be pressed."""
    return alive_seconds / ability.cooldown_seconds * ability.charges


def defensive_base_ids(
    players: tuple[Player, ...], defensives: Defensives
) -> dict[tuple[int, int], str]:
    """The id fragment every `defensives.*` finding carries, by (actor, ability).

    Minted here rather than inside `analyse_defensive_ceiling` so that anything
    needing to find a defensives finding again can generate the same id
    instead of taking one apart. These findings carry no `player_slug`: the
    owner lives only in this fragment, and a reader parsing it back would be
    parsing a string this module had just formatted.

    Counted on the slug rather than the name, because the slug is what the id
    carries: `Bríala` and `Briala` are two players and one slug, and only the
    actor id then tells their findings apart.
    """
    slug_counts: dict[str, int] = defaultdict(int)
    for player in players:
        slug_counts[player_slug(player.name)] += 1

    ids: dict[tuple[int, int], str] = {}
    for player in players:
        slug = player_slug(player.name)
        for ability in defensives.for_spec(player.class_name, player.spec):
            ids[(player.actor_id, ability.ability_id)] = (
                f"{slug}.{ability.ability_id}"
                if slug_counts[slug] == 1
                else f"{slug}.{player.actor_id}.{ability.ability_id}"
            )
    return ids


def analyse_defensive_ceiling(
    players: tuple[Player, ...],
    combat_seconds: float,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Defensives pressed far below their cooldown ceiling (§5.7).

    `inferred`. The log emits no cooldown-reset or reduction events, so the
    claim cannot be measured, and a defensive is pressed into damage rather
    than on cooldown -- the ceiling bounds what was possible, not what was
    right.

    An ability the player never pressed produces nothing here. It has no
    ceiling to be judged against, and the claim that they never pressed it is
    the death card's, where it sits beside the three other states a reader
    needs to weigh it.
    """
    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1

    base_ids = defensive_base_ids(players, defensives)

    findings = []
    for player in players:
        known = defensives.for_spec(player.class_name, player.spec)
        for ability in known:
            base_id = base_ids[(player.actor_id, ability.ability_id)]
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)
            if not uses:
                continue

            alive = alive_combat_seconds(combat_seconds, deaths, player.actor_id)
            if alive is None:
                continue
            ceiling = cooldown_ceiling(alive, ability)
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
                    ability_id=ability.ability_id,
                    ability_name=ability.name,
                )
            )
    return findings
