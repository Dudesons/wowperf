# ABOUTME: Healing consumables a player could have drunk at a death, by cooldown category.
# ABOUTME: Inferred, like every availability claim: the log records only what was drunk.

from collections import defaultdict

from wowperf.domain.analysis.deaths import pull_offset
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import ConsumableCategory, Consumables


def consumable_window_start(category: ConsumableCategory, death_ms: int) -> float:
    """When a press would have to fall for this category still to be on cooldown at the death.

    A death earlier in the run than this cannot be judged at all: the log begins
    after the window opens, so silence about the category proves nothing.
    """
    return death_ms - (category.cooldown_seconds + RUN_UP_SECONDS) * 1000


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

    Only categories the player drank from somewhere in the run are considered.
    That rule was absent at first, on the reasoning that carrying a potion is a
    choice the player controls, so silence about it was worth reporting. A real
    run settled it: nobody used a healthstone in nine thousand casts, so every
    death of every player carried a line saying the healthstone was off cooldown
    — true, unarguable and worth nothing. What the log supports about a category
    nobody touched is a fact about the run, which `analyse_consumables_never_used`
    states once, rather than a fact about each death.

    Dropping that proof costs one protection, which `visible_from_ms` restores.
    Casts are fetched per fight, so a potion drunk before the timer started is
    invisible; with no ownership rule to lean on, reporting the category as clear
    there would be a false accusation rather than the understatement every other
    rule in this project settles for. A category whose window reaches back before
    the log begins is therefore not reported at all — unknown, not available.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    drank = {cast.ability_id for cast in ours}
    return tuple(
        category.name
        for category in categories
        if any(ability_id in drank for ability_id in category.ability_ids)
        and consumable_window_start(category, death_ms) >= visible_from_ms
        and not any(
            cast.ability_id in category.ability_ids
            and consumable_window_start(category, death_ms) <= cast.timestamp_ms <= death_ms
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
    survival_categories = consumables.for_survival()
    if not survival_categories:
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
                survival_categories,
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


def analyse_consumables_never_used(
    run: Run,
    casts: tuple[CastEvent, ...],
    consumables: Consumables,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Players who died and drank from a whole category at no point in the run.

    The stronger of the two consumable claims, and the cheaper to act on. Its
    sibling asks whether a category happened to be off cooldown at a death, which
    is a coincidence of timing; this asks whether one was used at all, which is a
    habit.

    Still `inferred`, and for the same reason: a consumable reaches the log only
    when it is drunk, so this says none was used, never that none was carried.
    But unlike the per-death claim it is said once, and a reader can act on it
    without knowing what was in anyone's bags.
    """
    survival_categories = consumables.for_survival()
    if not survival_categories:
        return []

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        theirs = [death for death in deaths if death.actor_id == player.actor_id]
        if not theirs:
            continue
        drank = {cast.ability_id for cast in casts if cast.actor_id == player.actor_id}
        untouched = [
            category.name
            for category in survival_categories
            if not any(ability_id in drank for ability_id in category.ability_ids)
        ]
        if not untouched:
            continue

        base_id = (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name}.{player.actor_id}"
        )
        times = "once" if len(theirs) == 1 else f"{len(theirs)} times"
        findings.append(
            Finding(
                id=f"consumables.never.{base_id}",
                title=(
                    f"{player.name} died {times} and used no "
                    f"{' or '.join(untouched)} at any point in the run"
                ),
                detail=(
                    "A consumable reaches the log only when it is drunk, so this says "
                    "none was used — not that none was carried. Those want the same "
                    "answer and the tool cannot tell them apart, which is why it reports "
                    "the run rather than pinning it on a particular death."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=(
                    f"{player.class_name} {player.spec}",
                    f"died {times}",
                    *(f"no {name} used in the run" for name in untouched),
                ),
                pull_index=theirs[0].pull_index,
            )
        )
    return findings
