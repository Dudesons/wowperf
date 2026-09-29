# ABOUTME: The group's heaviest moments of damage taken, and whether a cooldown answered each.
# ABOUTME: Judged for the group, never per healer: the log records presses, not rotation plans.

from collections.abc import Sequence
from enum import StrEnum
from math import ceil
from statistics import median

from wowperf.domain.analysis.throughput import ready_at
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.pace_player import pair_label
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Externals, Roles, ThroughputCooldowns

SPIKES_ID = "healing.spikes"
UNANSWERED_ID = "healing.spikes.unanswered"
UNAVAILABLE_ID = "healing.spikes.unavailable"

SPIKE_WINDOW_SECONDS = 5
"""A heavy moment is a rolling window this long, so a burst straddling a boundary is not halved."""

SECONDS_PER_SPIKE = 180
"""One moment is ranked per started stretch this long: the cooldown of almost every answer."""

SPIKE_FLOOR = 2.0
"""A window ranks only at this multiple of the median window or above. Chosen, not measured."""

ANSWER_LEAD_SECONDS = 10
"""A press this long before a window opens still answers it: casting ahead is correct play."""

NOT_JUDGED_TITLE = "Healing cooldowns at the heaviest moments were not judged"


class Answer(Frozen):
    """One cooldown one player holds that answers a heavy moment for the whole group."""

    actor_id: int
    holder: str
    ability: CooldownAbility


class Moment(Frozen):
    """One ranked window. `rank` 1 is the heaviest; `weight` is None when the median window
    took no damage, so there is nothing to weigh it against."""

    start_ms: int
    end_ms: int
    rank: int
    weight: float | None


class State(StrEnum):
    ANSWERED = "answered"
    READY = "unanswered, cooldowns ready"
    NONE_READY = "unanswered, no answer shown ready"


class Verdict(Frozen):
    moment: Moment
    state: State
    pressed: tuple[str, ...] = ()
    ready: tuple[str, ...] = ()
    unready: tuple[str, ...] = ()


def answers_for(
    players: Sequence[Player],
    throughput: ThroughputCooldowns,
    externals: Externals,
    roles: Roles,
) -> tuple[Answer, ...]:
    """Every group answer each player holds: a healer's marked cooldowns, anyone's marked externals.

    Only entries marked `group` count. Both files also hold abilities that
    answer nobody but their target -- Power Infusion, Ironbark -- and a
    heavy moment is the whole group's.
    """
    found: list[Answer] = []
    for player in players:
        abilities: list[CooldownAbility] = [
            one for one in externals.for_spec(player.class_name, player.spec) if one.group
        ]
        if roles.role_of(player.class_name, player.spec) == "healer":
            abilities = [
                one for one in throughput.for_spec(player.class_name, player.spec) if one.group
            ] + abilities
        holder = f"{pair_label(player.class_name, player.spec, plural=False)}, {player.name}"
        found.extend(
            Answer(actor_id=player.actor_id, holder=holder, ability=one) for one in abilities
        )
    return tuple(found)


def _window_totals(
    damage_taken: Sequence[DamageTakenEvent],
    player_ids: frozenset[int],
    span: tuple[int, int],
    combat: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Every whole window inside one `combat` stretch, as (total, first second of the span).

    Each hit counts what reached health plus what a shield absorbed, less any
    damage past death: what healers had to answer. Only roster players count.
    """
    start, end = span
    seconds = max(0, ceil((end - start) / 1000))
    buckets = [0] * seconds
    for hit in damage_taken:
        if hit.actor_id not in player_ids:
            continue
        index = (hit.timestamp_ms - start) // 1000
        if 0 <= index < seconds:
            buckets[index] += max(0, hit.health_damage + hit.absorbed - hit.overkill)

    width = SPIKE_WINDOW_SECONDS
    windows: list[tuple[int, int]] = []
    for first in range(seconds - width + 1):
        opens = start + first * 1000
        closes = opens + width * 1000
        if any(low <= opens and closes <= high for low, high in combat):
            windows.append((sum(buckets[first : first + width]), first))
    return windows


def heaviest_moments(
    damage_taken: Sequence[DamageTakenEvent],
    player_ids: frozenset[int],
    span: tuple[int, int],
    combat: Sequence[tuple[int, int]],
) -> tuple[Moment, ...]:
    """The heaviest non-overlapping windows of the group's damage taken, in clock order.

    Each hit counts what reached health plus what a shield absorbed, less any
    damage past death: what healers had to answer. Only roster players count.
    A window must sit wholly inside one `combat` stretch -- the fight, or one
    pull of a key -- so the quiet between pulls neither ranks nor drags the
    median down.
    """
    windows = _window_totals(damage_taken, player_ids, span, combat)
    if not windows:
        return ()

    start, end = span
    width = SPIKE_WINDOW_SECONDS
    seconds = max(0, ceil((end - start) / 1000))
    wanted = ceil(seconds / SECONDS_PER_SPIKE)
    typical = median(total for total, _ in windows)
    picked: list[tuple[int, int]] = []
    for total, first in sorted(windows, key=lambda one: (-one[0], one[1])):
        if len(picked) >= wanted or total <= 0 or total < SPIKE_FLOOR * typical:
            break
        if any(abs(first - other) < width for _, other in picked):
            continue
        picked.append((total, first))

    moments = [
        Moment(
            start_ms=start + first * 1000,
            end_ms=start + (first + width) * 1000,
            rank=rank,
            weight=total / typical if typical > 0 else None,
        )
        for rank, (total, first) in enumerate(picked, start=1)
    ]
    return tuple(sorted(moments, key=lambda one: one.start_ms))


def _dead_at(
    actor_id: int,
    at_ms: int,
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
) -> bool:
    """Dead when the moment opened: died before it, with no resurrection and no cast since.

    A cast is a sign of life as good as a resurrection record, and the only
    one a player who released and ran back leaves: the log records no return.
    """
    before = [death.timestamp_ms for death in deaths if death.actor_id == actor_id]
    before = [when for when in before if when < at_ms]
    if not before:
        return False
    died = max(before)
    revived = any(
        one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in resurrections
    )
    acted = any(one.actor_id == actor_id and died < one.timestamp_ms <= at_ms for one in casts)
    return not (revived or acted)


def judge(
    moment: Moment,
    answers: Sequence[Answer],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    visible_from_ms: int,
    setting: str,
) -> Verdict:
    """Which answers were pressed for one moment, which sat ready, and why the rest did not.

    A cooldown never pressed anywhere in the fight is left out altogether:
    whether it was talented cannot be told. Nothing here says a cooldown was
    "on cooldown" -- talents shorten some, so the page states the press it saw.
    """
    lead_ms = ANSWER_LEAD_SECONDS * 1000
    pressed: list[str] = []
    ready: list[str] = []
    unready: list[str] = []
    for answer in answers:
        name = f"{answer.ability.name} ({answer.holder})"
        own = [
            cast.timestamp_ms
            for cast in casts
            if cast.actor_id == answer.actor_id and cast.ability_id == answer.ability.ability_id
        ]
        if not own:
            continue
        if any(moment.start_ms - lead_ms <= when <= moment.end_ms for when in own):
            pressed.append(name)
            continue
        if _dead_at(answer.actor_id, moment.start_ms, casts, deaths, resurrections):
            unready.append(f"{name}: its holder was dead")
            continue
        if ready_at(
            tuple(casts), (answer.ability,), answer.actor_id, moment.start_ms, visible_from_ms
        ):
            ready.append(name)
            continue
        cooldown_ms = answer.ability.cooldown_seconds * 1000
        recent = [when for when in own if moment.start_ms - cooldown_ms <= when <= moment.start_ms]
        # A key's casts are read from the fight's start, but its clock starts at
        # the first pull: a press between the two has no clock to print.
        if recent and max(recent) < visible_from_ms:
            unready.append(
                f"{name}: pressed before the {setting}'s first second, within its base "
                f"cooldown of {clock_text(answer.ability.cooldown_seconds)}"
            )
        elif recent:
            unready.append(
                f"{name}: pressed at {clock_text((max(recent) - visible_from_ms) / 1000)}, within "
                f"its base cooldown of {clock_text(answer.ability.cooldown_seconds)}"
            )
        else:
            unready.append(
                f"{name}: not judged, its base cooldown reaches before the {setting}'s first second"
            )

    if pressed:
        state = State.ANSWERED
    elif ready:
        state = State.READY
    else:
        state = State.NONE_READY
    return Verdict(
        moment=moment,
        state=state,
        pressed=tuple(pressed),
        ready=tuple(ready),
        unready=tuple(unready),
    )


def analyse_spikes(
    *,
    damage_taken: Sequence[DamageTakenEvent],
    casts: Sequence[CastEvent],
    deaths: Sequence[Death],
    resurrections: Sequence[Resurrection],
    players: Sequence[Player],
    answers: Sequence[Answer],
    span: tuple[int, int],
    combat: Sequence[tuple[int, int]],
    setting: str,
) -> list[Finding]:
    """`healing.spikes`, and `healing.spikes.unanswered` when it applies, or one notice.

    `span` is the fight's, or the whole run's on a key; `combat` the stretches
    a window may sit in; `setting` names the span on the page ("fight", "run").
    """
    if not casts:
        return [_notice(NOT_JUDGED_TITLE, NO_CASTS_DETAIL.format(setting=setting))]
    if not answers:
        return [_notice(NOT_JUDGED_TITLE, NO_ANSWER_DETAIL)]
    player_ids = frozenset(player.actor_id for player in players)
    moments = heaviest_moments(damage_taken, player_ids, span, combat)
    if not moments:
        # Two different reasons, and only one of them has a median to name:
        # when every window totals zero, each sits at twice a median of zero,
        # and when no whole window fits inside combat there is no median at all.
        felt = any(total > 0 for total, _ in _window_totals(damage_taken, player_ids, span, combat))
        return [
            _notice(
                f"No moment of this {setting} was heavy enough to rank",
                (NO_MOMENT_DETAIL if felt else NO_DAMAGE_DETAIL).format(setting=setting),
            )
        ]

    verdicts = [
        judge(moment, answers, casts, deaths, resurrections, span[0], setting)
        for moment in moments
    ]
    count = len(verdicts)
    plural = "s" if count != 1 else ""
    tally = {state: sum(one.state is state for one in verdicts) for state in State}
    parts = [
        f"{tally[state]} {label}"
        for state, label in (
            (State.ANSWERED, "answered"),
            (State.READY, "unanswered while cooldowns were ready"),
            (State.NONE_READY, "unanswered with no answer shown ready"),
        )
        if tally[state]
    ]
    findings = [
        Finding(
            id=SPIKES_ID,
            title=f"{count} heaviest moment{plural}: {', '.join(parts)}",
            detail=SPIKES_DETAIL.format(setting=setting),
            confidence=Confidence.DERIVED,
            evidence=tuple(_line(one, span[0], setting) for one in verdicts),
        )
    ]
    unanswered = [one for one in verdicts if one.state is State.READY]
    if unanswered:
        findings.append(
            Finding(
                id=UNANSWERED_ID,
                title=(
                    f"{len(unanswered)} of {count} heaviest moment{plural} went unanswered "
                    "while group cooldowns were ready"
                ),
                detail=UNANSWERED_DETAIL.format(setting=setting),
                confidence=Confidence.INFERRED,
                evidence=tuple(_line(one, span[0], setting) for one in unanswered),
            )
        )
    return findings


ORDINALS = ("", "second ", "third ", "fourth ", "fifth ", "sixth ", "seventh ", "eighth ",
            "ninth ", "tenth ")


def _ordinal(rank: int) -> str:
    """Return the ordinal prefix for a rank (e.g., '', 'second ', '11th ', '21st ')."""
    if 1 <= rank <= len(ORDINALS):
        return ORDINALS[rank - 1]
    suffix = "th"
    if rank % 100 not in (11, 12, 13):
        ones = rank % 10
        if ones == 1:
            suffix = "st"
        elif ones == 2:
            suffix = "nd"
        elif ones == 3:
            suffix = "rd"
    return f"{rank}{suffix} "


def _line(verdict: Verdict, origin_ms: int, setting: str) -> str:
    moment = verdict.moment
    opens = clock_text((moment.start_ms - origin_ms) / 1000)
    closes = clock_text((moment.end_ms - origin_ms) / 1000)
    rank = _ordinal(moment.rank)
    weight = (
        f"{moment.weight:.1f} times the median"
        if moment.weight is not None
        else (
            f"most of this {setting}'s {SPIKE_WINDOW_SECONDS}-second windows in combat took no "
            "damage"
        )
    )
    if verdict.state is State.ANSWERED:
        body = f"answered by {_joined(verdict.pressed)}"
    elif verdict.state is State.READY:
        body = f"nothing pressed; ready: {_joined(verdict.ready)}"
    else:
        body = "nothing pressed, and no answer was shown ready"
        if verdict.unready:
            body += "; " + "; ".join(verdict.unready)
    return f"{opens} to {closes}, the {rank}heaviest ({weight}): {body}"


def _joined(names: Sequence[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _notice(title: str, detail: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID, title=title, detail=detail, confidence=Confidence.MEASURED
    )


SPIKES_DETAIL = (
    "The damage the group's players took, each hit counted as what reached health plus what a "
    f"shield absorbed, less any damage past death, summed over rolling {SPIKE_WINDOW_SECONDS}-"
    f"second windows. One moment is ranked per started {SECONDS_PER_SPIKE // 60} minutes of the "
    "{setting}, heaviest first and never overlapping, and a window counts only at "
    f"{SPIKE_FLOOR:g} times the median {SPIKE_WINDOW_SECONDS}-second window or above, the median "
    "taken over the {setting}'s windows spent in combat. A healing or group-wide defensive "
    "cooldown answers a moment when it was pressed from "
    f"{ANSWER_LEAD_SECONDS} seconds before the window opened to its close. A cooldown never "
    "pressed in the {setting} is not seen, so it is not listed."
)
UNANSWERED_DETAIL = (
    "Judged for the group, never for one healer: the group may have planned this moment for a "
    "cooldown that came later. A cooldown reads as ready when its holder pressed it somewhere "
    "in this {setting}, had not pressed it within its base cooldown before the window opened, "
    "was alive, and that base cooldown reached back no further than the {setting}'s first "
    "second. Talents that shorten a cooldown are not modelled, a second charge reads as not "
    "ready, and a cooldown never pressed in the {setting} is not seen at all, so ready is "
    f"understated, never invented. The {ANSWER_LEAD_SECONDS}-second lead and the floor of "
    f"{SPIKE_FLOOR:g} times the median are chosen numbers, not measured ones."
)
NO_CASTS_DETAIL = (
    "This {setting} was read without its casts, so no press of any cooldown can be seen."
)
NO_ANSWER_DETAIL = (
    "Nobody in this group plays a specialisation holding a healing or group-wide defensive "
    "cooldown that this tool lists as answering the whole group's damage."
)
NO_MOMENT_DETAIL = (
    f"No {SPIKE_WINDOW_SECONDS}-second window of this {{setting}} spent in combat reached "
    f"{SPIKE_FLOOR:g} times the median of those windows, so none is presented as a heavy moment."
)
NO_DAMAGE_DETAIL = (
    f"No {SPIKE_WINDOW_SECONDS}-second window of this {{setting}} spent in combat took any damage "
    "that reached health or a shield, so no moment is ranked."
)
