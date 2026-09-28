# ABOUTME: Each wiped player's boss damage against the kills' players of the same class and spec.
# ABOUTME: One finding or one notice per compared damage dealer or tank, read from pace_curve.

import re
from collections.abc import Sequence

from wowperf.domain.analysis.recap import RESURRECTED, SELF_RESURRECTED, return_of
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace import PaceSample, clock_text, share_of, withheld_reason
from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReading,
    PaceReference,
    PaceState,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    lag_against,
    read_pace,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import Roles, SelfResurrections

PLAYER_PACE_PREFIX = "compare.pace.player."
PLAYER_UNAVAILABLE_PREFIX = "compare.pace.player.unavailable"

COMPARED_ROLES = frozenset({"damage", "tank"})

PLAYER_DETAIL = (
    "Cumulative damage to the boss, second by second from the pull, against the reference "
    "kills' players of the same class and specialisation over the same seconds, both sides "
    "read from the same boss-only damage graph. Damage to the boss only: a player assigned "
    "to adds, or a tank who held adds, reads behind for that assignment, not for their play."
)
FEWER_THAN_THREE_DETAIL = (
    "Damage pace per player needs three or more players of the same class and specialisation "
    "across the reference kills: against fewer, it would mostly measure what those raids "
    "assigned them."
)
NO_SPEC_TITLE = "This report does not name their specialisation"
NO_SPEC_DETAIL = (
    "Damage pace per player compares players of the same class and specialisation, and this "
    "report leaves this player's specialisation unnamed."
)
NOTHING_TO_COMPARE_DETAIL = (
    "The reference players of this class and specialisation had dealt the boss no damage by "
    "the last second compared."
)
SCOPE_LINE = "Damage pace per player compares damage dealers and tanks only."


def pair_label(class_name: str, spec: str, *, plural: bool = True) -> str:
    """ "Frost Mages", "Blood Death Knights": the spec, then the class split at its capitals."""
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    return f"{spec} {words}{'s' if plural else ''}"


class Window(Frozen):
    """Where one player's comparison ends, and every stretch they spent dead before it.

    `end_seconds` counts from the pull. `by_death` says a death no resurrection
    answered ended it, rather than the wipe. `dead` holds (died, back) pairs,
    in seconds from the pull, for every death that was answered.
    """

    end_seconds: float
    by_death: bool
    dead: tuple[tuple[float, float], ...] = ()


def window_of(
    loaded: LoadedEncounter, actor_id: int, self_resurrections: SelfResurrections
) -> Window:
    """From the pull to the first death no resurrection answered, or to the wipe.

    `return_of` decides, as it does for the death recaps, so "brought back"
    means one thing on the whole page. A release ends the window: on a wipe
    it is the end of the attempt for that player.
    """
    start_ms = loaded.encounter.start_ms
    dead: list[tuple[float, float]] = []
    deaths = sorted(
        (death for death in loaded.deaths if death.actor_id == actor_id),
        key=lambda death: death.timestamp_ms,
    )
    for death in deaths:
        died_at = (death.timestamp_ms - start_ms) / 1000
        came_back = return_of(loaded.resurrections, loaded.casts, death, self_resurrections)
        if came_back.kind in (RESURRECTED, SELF_RESURRECTED):
            if came_back.seconds_after is not None:
                dead.append((died_at, died_at + came_back.seconds_after))
            continue
        return Window(end_seconds=died_at, by_death=True, dead=tuple(dead))
    return Window(
        end_seconds=loaded.encounter.duration_seconds, by_death=False, dead=tuple(dead)
    )


def analyse_player_pace(
    loaded: LoadedEncounter,
    sample: PaceSample,
    subjects: Sequence[ParseSubject],
    roles: Roles,
    self_resurrections: SelfResurrections,
) -> list[Finding]:
    """`compare.pace.player.<slug>` or its notice, for each damage dealer and tank asked for.

    Nothing on a kill, and nothing when the raid-wide comparison was itself
    withheld: its notice in Provenance already says why, for everyone. A
    healer is not compared. A player dead before the first second has no
    reading and no line.
    """
    if loaded.encounter.kill or withheld_reason(loaded.encounter, sample):
        return []
    ours_by_actor = {one.actor_id: one.damage for one in sample.our_players}

    findings: list[Finding] = []
    for subject in subjects:
        player = subject.player
        if roles.role_of(player.class_name, player.spec) not in COMPARED_ROLES:
            continue
        if not player.spec:
            findings.append(_notice(subject.slug, NO_SPEC_TITLE, NO_SPEC_DETAIL))
            continue
        window = window_of(loaded, player.actor_id, self_resurrections)
        if window.end_seconds < 1:
            continue
        peers, kills = _peers(sample, player)
        if len(peers) < MIN_SAMPLE_FOR_AGGREGATE:
            findings.append(
                _notice(subject.slug, _too_few_title(len(peers), player), FEWER_THAN_THREE_DETAIL)
            )
            continue
        ours = ours_by_actor.get(player.actor_id, BossDamage(interval_ms=1000.0))
        reading = read_pace(ours, peers, window.end_seconds)
        if reading is None or not reading.seconds or reading.seconds[-1].median <= 0:
            label = pair_label(player.class_name, player.spec)
            findings.append(
                _notice(
                    subject.slug,
                    f"No second of this attempt could be compared against the kills' {label}",
                    NOTHING_TO_COMPARE_DETAIL,
                )
            )
            continue
        findings.append(_finding(subject.slug, player, reading, ours, peers, kills, window))
    return findings


def _peers(sample: PaceSample, player: Player) -> tuple[tuple[PaceReference, ...], int]:
    """Every reference player of the same class and spec, each over their own part of the kill."""
    peers: list[PaceReference] = []
    kills = 0
    for kill in sample.references:
        matching = [
            one
            for one in kill.players
            if (one.class_name, one.spec) == (player.class_name, player.spec)
        ]
        if matching:
            kills += 1
        for one in matching:
            until = kill.duration_seconds
            if one.until_seconds is not None:
                until = min(until, one.until_seconds)
            peers.append(PaceReference(duration_seconds=until, damage=one.damage))
    return tuple(peers), kills


def _too_few_title(count: int, player: Player) -> str:
    one = pair_label(player.class_name, player.spec, plural=False)
    many = pair_label(player.class_name, player.spec)
    if count == 0:
        return f"No {one} in the reference kills: fewer than three to compare against"
    return (
        f"Only {count} {one if count == 1 else many} in the reference kills: "
        "fewer than three to compare against"
    )


def _notice(slug: str, title: str, detail: str) -> Finding:
    return Finding(
        id=f"{PLAYER_UNAVAILABLE_PREFIX}.{slug}",
        title=title,
        detail=detail,
        confidence=Confidence.MEASURED,
        player_slug=slug,
    )


def _lag_line(
    label: str, one: str, second: int, amount: float, peers: tuple[PaceReference, ...]
) -> str:
    """The lag names the median: the state reads the whole band, so "on pace" and
    seconds behind can both be true, and the line must say which it measured."""
    lag = lag_against(amount, peers)
    if lag.reached_at is None:
        return (
            f"More than the kills' median had dealt by {clock_text(lag.band_end)}, where fewer "
            f"than three {label} were still fighting"
        )
    gap = round(second - lag.reached_at)
    if gap == 0:
        return (
            f"By {clock_text(second)} they had dealt what the kills' median {one} had dealt "
            "by then"
        )
    seconds = f"{abs(gap)} second{'s' if abs(gap) != 1 else ''}"
    return (
        f"By {clock_text(second)} they had dealt what the kills' median {one} had dealt by "
        f"{clock_text(lag.reached_at)}: {seconds} {'behind' if gap > 0 else 'ahead'}"
    )


def _finding(
    slug: str,
    player: Player,
    reading: PaceReading,
    ours: BossDamage,
    peers: tuple[PaceReference, ...],
    kills: int,
    window: Window,
) -> Finding:
    label = pair_label(player.class_name, player.spec)
    last = reading.seconds[-1]
    clock = clock_text(last.second)
    lead = {
        PaceState.BEHIND: f"Behind the kills' {label}",
        PaceState.ON_PACE: f"On the kills' {label}' pace",
        PaceState.AHEAD: f"Ahead of the kills' {label}",
    }[last.state]

    evidence = [
        f"Against {len(peers)} {label} across {kills} reference kill{'s' if kills != 1 else ''} "
        "of this raid size",
        f"Their range at {clock}: {share_of(last.low, last.median)}% to "
        f"{share_of(last.high, last.median)}% of their median",
    ]
    dealt = cumulative_at(ours, last.second)
    if dealt > 0:
        one = pair_label(player.class_name, player.spec, plural=False)
        evidence.append(_lag_line(label, one, last.second, dealt, peers))
    if reading.band_cut:
        evidence.append(
            f"Compared through {clock}, after which fewer than three {label} were still fighting"
        )
    elif window.by_death:
        evidence.append(f"Compared through their death at {clock}")
    else:
        evidence.append(f"Compared through the wipe at {clock}")
    compared_through = last.second
    evidence.extend(
        f"Dead from {clock_text(died)} to {clock_text(min(back, compared_through))}, "
        "then resurrected"
        for died, back in window.dead
        if died < compared_through
    )
    start = final_behind_start(reading)
    if start is not None:
        evidence.append(f"Behind from {clock_text(start)} to {clock}")
        evidence.extend(
            f"Also behind between {clock_text(first)} and {clock_text(end)}"
            for first, end in earlier_behind(reading)
        )

    return Finding(
        id=f"{PLAYER_PACE_PREFIX}{slug}",
        title=f"{lead}: {share_of(last.ours, last.median)}% of their median boss damage by {clock}",
        detail=PLAYER_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(evidence),
        player_slug=slug,
    )
