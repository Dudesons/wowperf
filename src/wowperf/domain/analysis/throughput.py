# ABOUTME: Whether burst cooldowns landed on the pulls that were worth spending them on.
# ABOUTME: Inferred: the log records presses, never the plan behind holding one back.

from collections import defaultdict

from wowperf.domain.analysis.defensives import (
    CEILING_USE_FRACTION,
    MIN_CEILING_USES,
    alive_combat_seconds,
    cooldown_ceiling,
)
from wowperf.domain.events import CastEvent, Death, EnemyDeath
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Pull, Run
from wowperf.domain.season import CooldownAbility, ThroughputCooldowns

MOST_PULLS_CONSIDERED = 3
"""How many of the largest trash pulls to ask about.

Asking about every pull would be asking about nothing: a cooldown held through
four small packs and spent on the fifth is correct play, and the whole reason
this analyser looks at the big pulls only.
"""


def ready_at(
    casts: tuple[CastEvent, ...],
    abilities: tuple[CooldownAbility, ...],
    actor_id: int,
    at_ms: int,
    visible_from_ms: int,
) -> tuple[CooldownAbility, ...]:
    """Which of `abilities` this player owned and had off cooldown at `at_ms`.

    Owned means cast at least once somewhere in the run. Throughput cooldowns are
    talent-gated like defensive ones, and a player who never took the talent
    casts it nowhere — indistinguishable from holding it back, so silence must
    not be read as either.

    Off cooldown means cast at no point in `[at_ms - cooldown, at_ms]`. There is
    no run-up widening here, unlike the rule at a death: a pull has a start, and
    what matters is whether the button was pressable when the pack was engaged.

    A window reaching back before `visible_from_ms` is not judged. Casts are
    fetched per fight, so a cooldown pressed before the timer began is invisible,
    and calling it ready would be the one direction this project never guesses in.
    One consequence worth expecting rather than filing as a bug: the run's first
    pull begins at `visible_from_ms`, so no ability is ever ready on it.

    Charges are ignored, so a second charge reads as unavailable. That is the
    same understatement the sibling rules make, and the same safe direction.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    owned = {cast.ability_id for cast in ours}
    return tuple(
        ability
        for ability in abilities
        if ability.ability_id in owned
        and at_ms - ability.cooldown_seconds * 1000 >= visible_from_ms
        and not any(
            cast.ability_id == ability.ability_id
            and at_ms - ability.cooldown_seconds * 1000 <= cast.timestamp_ms <= at_ms
            for cast in ours
        )
    )


def pulls_worth_a_cooldown(
    run: Run, enemy_deaths: tuple[EnemyDeath, ...], most: int = MOST_PULLS_CONSIDERED
) -> tuple[Pull, ...]:
    """Every boss pull, and the `most` trash pulls that gave up the most forces.

    Bosses are included whatever their forces, which are usually none at all:
    ranking by forces alone would drop the one pull nobody would argue is worth
    a cooldown.

    Returned in pull order rather than in size order, so a reader walks the run
    forwards.
    """
    forces_by_pull: dict[int | None, int] = defaultdict(int)
    for death in enemy_deaths:
        forces_by_pull[death.pull_index] += death.forces

    # A pull that gave up no forces is not one of the largest, whatever a stable
    # sort would hand back when every pull ties at zero — which is what an empty
    # `enemy_deaths` produces. Saying nothing beats calling the first three pulls
    # the biggest.
    trash = sorted(
        (
            pull
            for pull in run.pulls
            if pull.encounter_id == 0 and forces_by_pull[pull.index] > 0
        ),
        key=lambda pull: forces_by_pull[pull.index],
        reverse=True,
    )
    chosen = {pull.index for pull in trash[:most]}
    chosen |= {pull.index for pull in run.pulls if pull.encounter_id != 0}
    return tuple(pull for pull in run.pulls if pull.index in chosen)


def analyse_cooldown_alignment(
    run: Run,
    casts: tuple[CastEvent, ...],
    cooldowns: ThroughputCooldowns,
    enemy_deaths: tuple[EnemyDeath, ...],
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Cooldowns a player owned, had ready, and did not press on a pull worth it.

    `inferred`, and the reason is not the arithmetic. The log records presses; it
    does not record the plan. A cooldown held through a big pack because a bigger
    one was thirty seconds away is good play and reads here as a gap, which is
    why this is a question to ask rather than a fault to correct.

    Only the run's boss pulls and its largest trash pulls are asked about, since
    that is the difference between this and a claim that a cooldown should be
    pressed on cooldown — which in a keystone it should not.

    A pull the player spent dead is skipped: a corpse presses nothing, and those
    are the pulls where dying is likeliest. Where a death's cost cannot be
    measured at all the player is not judged, following the same refusal
    `alive_combat_seconds` makes for the same reason.
    """
    if not cooldowns.entries:
        return []

    worth = pulls_worth_a_cooldown(run, enemy_deaths)
    if not worth:
        return []

    visible_from_ms = min((pull.start_ms for pull in run.pulls), default=0)
    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        abilities = cooldowns.for_spec(player.class_name, player.spec)
        if not abilities:
            continue

        theirs = [death for death in deaths if death.actor_id == player.actor_id]
        if any(death.seconds_until_next_action is None for death in theirs):
            continue
        dead_spans = [
            (death.timestamp_ms, death.timestamp_ms + (death.seconds_until_next_action or 0) * 1000)
            for death in theirs
        ]

        lines = []
        for pull in worth:
            if any(start < pull.end_ms and pull.start_ms < end for start, end in dead_spans):
                continue
            ready = ready_at(
                casts, abilities, player.actor_id, pull.start_ms, visible_from_ms
            )
            if not ready:
                continue
            pressed = {
                cast.ability_id
                for cast in casts
                if cast.actor_id == player.actor_id
                and pull.start_ms <= cast.timestamp_ms <= pull.end_ms
            }
            held = [ability.name for ability in ready if ability.ability_id not in pressed]
            if not held:
                continue
            where = pull.name
            lines.append(f"{where}: {', '.join(held)} ready and not pressed")

        if not lines:
            continue

        base_id = (
            player.name
            if name_counts[player.name] == 1
            else f"{player.name}.{player.actor_id}"
        )
        pulls_word = "pull" if len(lines) == 1 else "pulls"
        findings.append(
            Finding(
                id=f"throughput.alignment.{base_id}",
                title=(
                    f"{player.name} had a cooldown ready and unpressed on "
                    f"{len(lines)} big {pulls_word}"
                ),
                detail=(
                    "Read against the run's boss pulls and its largest trash packs, "
                    "because a cooldown held through a small pack is correct play and "
                    "only the big ones make holding it a question. Only abilities this "
                    "player cast somewhere in the run are considered, so a talent they "
                    "never took is never counted against them. The log records presses "
                    "and not plans: a cooldown saved for a bigger pack moments later "
                    "reads here as a gap."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=(f"{player.class_name} {player.spec}", *lines),
            )
        )
    return findings


def analyse_cooldown_ceiling(
    run: Run,
    casts: tuple[CastEvent, ...],
    cooldowns: ThroughputCooldowns,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Throughput cooldowns pressed far below what their cooldown allowed.

    Off by default, and the reason is in the claim itself. For a defensive the
    ceiling is explicitly not a target, because a defensive answers incoming
    damage. For a burst cooldown in a keystone the ceiling is closer to a target
    but still is not one: a route decides how many packs are worth spending on,
    and a player who spends four times on four big pulls has done nothing wrong
    against a ceiling of fifteen.

    That is why `analyse_cooldown_alignment` is the claim this project makes by
    default and this one is asked for. It fires only at the same near-neglect
    fraction the defensive ceiling uses, and only for abilities the player cast
    at least once — never casting one is the talent-gated case, which belongs to
    no analyser here.
    """
    if not cooldowns.entries:
        return []

    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1

    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    findings = []
    for player in run.players:
        for ability in cooldowns.for_spec(player.class_name, player.spec):
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)
            if not uses:
                continue
            alive = alive_combat_seconds(run.total_pull_seconds, deaths, player.actor_id)
            if alive is None:
                continue
            ceiling = cooldown_ceiling(alive, ability)
            if ceiling < MIN_CEILING_USES or uses >= ceiling * CEILING_USE_FRACTION:
                continue
            base_id = (
                f"{player.name}.{ability.ability_id}"
                if name_counts[player.name] == 1
                else f"{player.name}.{player.actor_id}.{ability.ability_id}"
            )
            findings.append(
                Finding(
                    id=f"throughput.ceiling.{base_id}",
                    title=(
                        f"{player.name} used {ability.name} {uses} "
                        f"of a possible {ceiling:.0f} times"
                    ),
                    detail=(
                        f"{ability.name} has a {ability.cooldown_seconds:.0f}s cooldown, "
                        f"which fits {ceiling:.0f} times into the {alive:.0f}s this player "
                        "spent alive and in combat. A keystone gives no reason to press a "
                        "burst cooldown on every one of those: the route decides how many "
                        "packs are worth it, so this is a ceiling and not a target."
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
