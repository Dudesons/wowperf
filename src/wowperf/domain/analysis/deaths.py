# ABOUTME: What deaths cost in seconds actually not played, and which ones caused others.
# ABOUTME: The timer penalty understates a death; this measures the real thing instead.

from collections import defaultdict

from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

CHAIN_WINDOW_MS = 10_000
"""Deaths closer together than this are one event, not two independent ones."""


def _cost(deaths: tuple[Death, ...]) -> float:
    """Sum of measured cost, treating an unmeasured death as contributing nothing.

    Used only for deaths.total, whose own evidence already discloses how many of
    the summed deaths were unmeasured. Every other finding family uses
    `_measured_cost` instead, which refuses to paper over an unmeasured death with
    a fabricated zero.
    """
    return sum(death.seconds_until_next_action or 0.0 for death in deaths)


def _measured_cost(deaths: tuple[Death, ...]) -> tuple[float | None, int]:
    """The measured cost of a group of deaths, and how many members were unmeasured.

    Returns `(None, len(deaths))` when every death in the group is unmeasured —
    the player or players involved never acted again, so no honest number
    exists. Returns `(sum, 0)` when every death is measured. Returns `(sum, n)`
    when some but not all are measured, in which case the sum is a floor on the
    true cost rather than the whole of it.
    """
    measured = [
        death.seconds_until_next_action for death in deaths
        if death.seconds_until_next_action is not None
    ]
    unmeasured_count = len(deaths) - len(measured)
    if not measured:
        return None, unmeasured_count
    return sum(measured), unmeasured_count


def _unmeasured_evidence(unmeasured_count: int) -> str:
    """The disclosure line for a partially-unmeasured group, matching deaths.total."""
    return (
        f"{unmeasured_count} death{'s' if unmeasured_count > 1 else ''} not measured: "
        "the player never acted again"
    )


def _chains(deaths: tuple[Death, ...]) -> list[tuple[Death, ...]]:
    """Group deaths into runs of deaths separated by less than the chain window."""
    ordered = sorted(deaths, key=lambda death: death.timestamp_ms)
    groups: list[list[Death]] = []
    for death in ordered:
        if groups and death.timestamp_ms - groups[-1][-1].timestamp_ms <= CHAIN_WINDOW_MS:
            groups[-1].append(death)
        else:
            groups.append([death])
    return [tuple(group) for group in groups]


def analyse_deaths(run: Run, deaths: tuple[Death, ...]) -> list[Finding]:
    """Report what dying cost, grouped so a wipe reads as one event."""
    if not deaths:
        return []

    unmeasured = [death for death in deaths if death.seconds_until_next_action is None]
    evidence = [f"{len(deaths)} deaths across {len(run.pulls)} pulls"]
    if unmeasured:
        evidence.append(
            f"{len(unmeasured)} death{'s' if len(unmeasured) > 1 else ''} not measured: "
            "the player never acted again"
        )

    findings = [
        Finding(
            id="deaths.total",
            title=(
                f"{len(deaths)} death{'s' if len(deaths) > 1 else ''} cost "
                f"{_cost(deaths):.0f}s of play"
            ),
            detail=(
                "Measured from each death to that player's next cast, which is longer than "
                "the timer penalty and is the time the group actually lost."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=_cost(deaths),
            evidence=tuple(evidence),
        )
    ]

    chain_rank = single_rank = 0
    for group in _chains(deaths):
        first = group[0]
        seconds_lost, unmeasured_count = _measured_cost(group)
        if len(group) > 1:
            names = ", ".join(death.player_name for death in group[1:])
            detail = (
                f"{first.player_name} died first, to {first.killing_blow}, then "
                f"{names}. In a chain the first death usually causes the rest."
            )
            group_evidence = tuple(
                f"{death.player_name} at {death.timestamp_ms}ms to "
                f"{death.killing_blow}"
                for death in group
            )
            if seconds_lost is None:
                detail += (
                    f" None of these {len(group)} deaths were followed by another "
                    "action, so the cost cannot be measured."
                )
            elif unmeasured_count:
                group_evidence = group_evidence + (_unmeasured_evidence(unmeasured_count),)
            findings.append(
                Finding(
                    id=f"deaths.chain.{chain_rank}",
                    title=f"{len(group)} deaths within {CHAIN_WINDOW_MS // 1000}s",
                    detail=detail,
                    confidence=Confidence.MEASURED,
                    seconds_lost=seconds_lost,
                    evidence=group_evidence,
                    pull_index=first.pull_index,
                )
            )
            chain_rank += 1
        else:
            if seconds_lost is None:
                detail = (
                    f"{first.player_name} never acted again after dying, so the "
                    "cost cannot be measured."
                )
            else:
                detail = f"Cost {seconds_lost:.0f}s of play."
            findings.append(
                Finding(
                    id=f"deaths.single.{single_rank}",
                    title=f"{first.player_name} died to {first.killing_blow}",
                    detail=detail,
                    confidence=Confidence.MEASURED,
                    seconds_lost=seconds_lost,
                    evidence=(f"pull {first.pull_index}, at {first.timestamp_ms}ms",),
                    pull_index=first.pull_index,
                )
            )
            single_rank += 1

    # Two players can share a display name; group by actor id so their deaths are
    # never mixed into one finding, and disambiguate the id with the actor id only
    # when that happens, so the common case stays readable.
    name_counts: dict[str, int] = defaultdict(int)
    for player in run.players:
        name_counts[player.name] += 1

    by_actor: dict[int, list[Death]] = defaultdict(list)
    for death in deaths:
        by_actor[death.actor_id].append(death)

    for actor_id, theirs_list in by_actor.items():
        theirs = tuple(theirs_list)
        count = len(theirs)
        if count < 2:
            continue
        name = theirs[0].player_name
        seconds_lost, unmeasured_count = _measured_cost(theirs)
        detail = f"{count} of the run's {len(deaths)} deaths were {name}."
        player_evidence = tuple(
            f"{death.killing_blow} at {death.timestamp_ms}ms" for death in theirs
        )
        if seconds_lost is None:
            detail += (
                f" None of {name}'s deaths were followed by another action, so the "
                "cost cannot be measured."
            )
        elif unmeasured_count:
            player_evidence = player_evidence + (_unmeasured_evidence(unmeasured_count),)
        finding_id = (
            f"deaths.repeat.{name}"
            if name_counts[name] == 1
            else f"deaths.repeat.{name}.{actor_id}"
        )
        findings.append(
            Finding(
                id=finding_id,
                title=f"{name} died {count} times",
                detail=detail,
                confidence=Confidence.MEASURED,
                seconds_lost=seconds_lost,
                evidence=player_evidence,
            )
        )
    return findings
