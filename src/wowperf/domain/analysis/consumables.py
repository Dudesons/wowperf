# ABOUTME: Healing consumables a player could have drunk at a death, by cooldown category.
# ABOUTME: Inferred, like every availability claim: the log records only what was drunk.

from collections import defaultdict

from wowperf.domain.analysis.deaths import pull_offset
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import ConsumableCategory, Consumables


def consumables_up_at(
    casts: tuple[CastEvent, ...],
    categories: tuple[ConsumableCategory, ...],
    actor_id: int,
    death_ms: int,
    visible_from_ms: int,
) -> tuple[str, ...]:
    """Names of the categories this player had off cooldown when the killing damage began.

    A category is available when the player drank nothing from it in
    `[death - (cooldown + run-up), death]`. The window is the one the defensive
    rule uses, and for the same two reasons: something that came back halfway
    through the killing damage was never an option, and something drunk during
    that damage must not read as neglect.

    Categories are independent of one another, because the game's are: health
    potions stopped sharing a cooldown with combat potions in patch 9.0, and
    Healthstone stopped sharing with health potions in patch 8.0.1.

    Unlike a defensive, nothing here has to prove the player carried one. A
    talent they never took must never be held against them; a potion is a choice
    they control, and the log cannot separate an unused one from an empty bag in
    either direction.

    Dropping that proof costs one protection, which `visible_from_ms` restores.
    Casts are fetched per fight, so a potion drunk before the timer started is
    invisible; with no ownership rule to lean on, reporting the category as clear
    there would be a false accusation rather than the understatement every other
    rule in this project settles for. A category whose window reaches back before
    the log begins is therefore not reported at all — unknown, not available.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    return tuple(
        category.name
        for category in categories
        if death_ms - (category.cooldown_seconds + RUN_UP_SECONDS) * 1000 >= visible_from_ms
        and not any(
            cast.ability_id in category.ability_ids
            and death_ms - (category.cooldown_seconds + RUN_UP_SECONDS) * 1000
            <= cast.timestamp_ms
            <= death_ms
            for cast in ours
        )
    )


def analyse_consumables_at_death(
    run: Run,
    casts: tuple[CastEvent, ...],
    consumables: Consumables,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Players who died with a healing consumable off cooldown.

    One finding per player, with each qualifying death in the evidence, matching
    the shape of the defensive claim it sits beside.

    `inferred`, and for a reason worth stating on the page: a consumable appears
    in the log only when it is drunk, so an empty category means "nothing was on
    cooldown", never "one was in the bag".
    """
    if not consumables.categories:
        return []

    # Casts are fetched from the fight's start, so nothing before the first pull
    # is visible. `consumables_up_at` needs that boundary to refuse a claim it
    # cannot support.
    visible_from_ms = min((pull.start_ms for pull in run.pulls), default=0)

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        lines = []
        first_pull: int | None = None
        for death in sorted(
            (death for death in deaths if death.actor_id == player.actor_id),
            key=lambda death: death.timestamp_ms,
        ):
            up = consumables_up_at(
                casts,
                consumables.categories,
                player.actor_id,
                death.timestamp_ms,
                visible_from_ms=visible_from_ms,
            )
            if not up:
                continue
            if first_pull is None:
                first_pull = death.pull_index
            lines.append(
                f"{pull_offset(run, death)} to {death.killing_blow} — "
                f"{', '.join(up)} not on cooldown"
            )

        if not lines:
            continue

        base_id = (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name}.{player.actor_id}"
        )
        times = "once" if len(lines) == 1 else f"{len(lines)} times"
        findings.append(
            Finding(
                id=f"consumables.unused.{base_id}",
                title=(
                    f"{player.name} died {times} with no healing consumable on cooldown"
                ),
                detail=(
                    "A consumable reaches the log only when it is drunk, so this says "
                    "nothing was on cooldown — not that one was carried. An empty bag "
                    "and an unpressed button look identical here, and both are worth "
                    "asking about, which is why this is a question rather than a fault. "
                    "It is also close to the default state: most players drink neither "
                    "in most runs, so this says far less than a defensive left unused."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=tuple(lines),
                pull_index=first_pull,
            )
        )
    return findings
