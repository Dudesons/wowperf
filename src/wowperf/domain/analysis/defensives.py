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

The fraction carries its own floor, which is why no separate minimum sits
beside it. A press count is a positive integer, so `uses < ceiling * fraction`
cannot hold until the ceiling passes `1 / fraction` -- five, at 0.2. A ceiling
too small to argue from is therefore already silent, and a constant saying so
could only restate that arithmetic or contradict it.

The throughput ceiling borrows this fraction rather than having measured its
own. That is one of the reasons that claim is asked for rather than given.
"""

CEILING_WITHHELD_ID = "defensives.ceiling.withheld"
"""The finding that says a fight ran too short to judge some pressed defensive.

A press count is a positive integer, so `uses < ceiling * CEILING_USE_FRACTION`
cannot hold until the ceiling clears `1 / CEILING_USE_FRACTION` -- five. Below
that, the analyser is structurally unable to report on an ability regardless of
how it was used, and saying nothing reads on the page exactly like having used
it enough. This id names that silence instead of leaving it silent, so a caller
can lift it out by the id alone rather than by a prefix that would also catch
the ceiling findings it sits beside.
"""

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
    combat_seconds: float,
    deaths: tuple[Death, ...],
    actor_id: int,
    *,
    combat_end_ms: int,
) -> float:
    """Combat time this player could actually have pressed a button in.

    `combat_seconds` is the denominator the caller's aggregate defines: summed
    pull time for a keystone, fight duration for a raid boss. Taking the number
    rather than the aggregate is what lets both ask this question; taking a
    `Run` meant a raid fight silently supplied zero.

    A death's dead time is `seconds_until_next_action` where the log recorded
    one. Where it did not, the player was never seen to act on another actor
    again, and they count as dead from that death until `combat_end_ms`. On a
    wipe that is exact: the fight ended, so they provably never returned. For a
    player resurrected who then only ever casts on themselves it understates
    their alive time, which lowers their ceiling and weakens the claim -- the
    same direction every other approximation here leans, because understating
    cannot produce a false accusation.

    Approximate on purpose either way, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot.
    """
    dead = 0.0
    for death in deaths:
        if death.actor_id != actor_id:
            continue
        if death.seconds_until_next_action is None:
            # Clamped because a death can sit a millisecond past the window a
            # keystone computes for itself; see `Run.window_ms`.
            dead += max(combat_end_ms - death.timestamp_ms, 0) / 1000
        else:
            dead += death.seconds_until_next_action
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


def _ceiling_withheld(combat_seconds: float, needs: set[tuple[str, float]]) -> Finding:
    """The abilities this fight was too short to judge, said out loud.

    `measured`, on the same reasoning `attempt_shape._withheld` gives: what is
    asserted is that the analyser declined and why, and both halves are checked
    rather than read. The ceiling claim it declined to make is `inferred`; this
    is not that claim.

    One finding per report rather than per player or per ability. The
    suppression is a fact about the fight's length and an ability's own
    cooldown and charges, identical for every raider carrying the same variant
    of that ability, and twenty players against sixty-five abilities is a wall
    rather than a disclosure.

    `needs` pairs each name with the seconds *that variant* required, rather
    than a bare name, because a name alone cannot say how long an ability
    needs: charges divide that figure, so two players carrying the same-named
    ability under different specs can genuinely need different combat lengths.
    """
    count = len(needs)
    return Finding(
        id=CEILING_WITHHELD_ID,
        title=(
            f"This fight was too short to judge {count} "
            f"pressed defensive{'s' if count != 1 else ''}"
        ),
        detail=(
            "A ceiling claim needs an ability to fit more than five uses into "
            "the fight, charges included: below that, a single press already "
            "clears the threshold, so no press count could ever be low enough "
            f"to report. This fight ran {combat_seconds:.0f}s, short of what "
            f"{count} of the defensives someone pressed would need -- charges "
            "change that figure from one defensive to the next, so it is "
            "stated per ability below rather than as one number here. Nothing "
            "is being said about how those were used -- this is the analyser "
            "declining to judge them, not a clean bill of health."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=tuple(
            f"{name} would need {seconds:.0f}s of combat"
            for name, seconds in sorted(needs)
        ),
    )


def analyse_defensive_ceiling(
    players: tuple[Player, ...],
    combat_seconds: float,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
    *,
    combat_end_ms: int,
) -> list[Finding]:
    """Defensives pressed far below their cooldown ceiling (§5.7).

    `inferred`. The log emits no cooldown-reset or reduction events, so the
    claim cannot be measured, and a defensive is pressed into damage rather
    than on cooldown — the ceiling bounds what was possible, not what was
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

    # Keyed by (name, seconds needed) rather than by name alone: two specs
    # carrying a genuinely identical ability collapse to one entry, but two
    # specs whose same-named ability differs in cooldown or charges -- Barkskin
    # is 45s for a Guardian and 60s for every other druid spec -- each keep
    # their own figure instead of one overwriting the other.
    too_short: set[tuple[str, float]] = set()

    findings = []
    for player in players:
        known = defensives.for_spec(player.class_name, player.spec)
        for ability in known:
            base_id = base_ids[(player.actor_id, ability.ability_id)]
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)
            if not uses:
                continue

            # Judged against the fight, not against this player's alive time: a
            # player who died early has abilities suppressed by their short life
            # rather than by a short fight, and a line saying the fight was too
            # short would then be false.
            if cooldown_ceiling(combat_seconds, ability) <= 1 / CEILING_USE_FRACTION:
                too_short.add((
                    ability.name,
                    ability.cooldown_seconds / ability.charges / CEILING_USE_FRACTION,
                ))

            alive = alive_combat_seconds(
                combat_seconds, deaths, player.actor_id, combat_end_ms=combat_end_ms
            )
            ceiling = cooldown_ceiling(alive, ability)
            if uses >= ceiling * CEILING_USE_FRACTION:
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
    if too_short:
        findings.append(_ceiling_withheld(combat_seconds, too_short))
    return findings
