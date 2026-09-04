# ABOUTME: What deaths cost in seconds actually not played, and which ones caused others.
# ABOUTME: The timer penalty understates a death; this measures the real thing instead.

from collections import Counter, defaultdict

from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

CHAIN_WINDOW_MS = 10_000
"""Deaths closer together than this are one event, not two independent ones."""


def _cost(deaths: tuple[Death, ...]) -> float:
    return sum(death.seconds_until_next_action or 0.0 for death in deaths)


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
            title=f"{len(deaths)} deaths cost {_cost(deaths):.0f}s of play",
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
        if len(group) > 1:
            names = ", ".join(death.player_name for death in group[1:])
            findings.append(
                Finding(
                    id=f"deaths.chain.{chain_rank}",
                    title=f"{len(group)} deaths within {CHAIN_WINDOW_MS // 1000}s",
                    detail=(
                        f"{first.player_name} died first, to {first.killing_blow}, then "
                        f"{names}. In a chain the first death usually causes the rest."
                    ),
                    confidence=Confidence.MEASURED,
                    seconds_lost=_cost(group),
                    evidence=tuple(
                        f"{death.player_name} at {death.timestamp_ms}ms to "
                        f"{death.killing_blow}"
                        for death in group
                    ),
                    pull_index=first.pull_index,
                )
            )
            chain_rank += 1
        else:
            findings.append(
                Finding(
                    id=f"deaths.single.{single_rank}",
                    title=f"{first.player_name} died to {first.killing_blow}",
                    detail=f"Cost {_cost(group):.0f}s of play.",
                    confidence=Confidence.MEASURED,
                    seconds_lost=_cost(group),
                    evidence=(f"pull {first.pull_index}, at {first.timestamp_ms}ms",),
                    pull_index=first.pull_index,
                )
            )
            single_rank += 1

    counts = Counter(death.player_name for death in deaths)
    by_player: dict[str, list[Death]] = defaultdict(list)
    for death in deaths:
        by_player[death.player_name].append(death)
    for name, count in counts.items():
        if count < 2:
            continue
        theirs = tuple(by_player[name])
        findings.append(
            Finding(
                id=f"deaths.repeat.{name}",
                title=f"{name} died {count} times",
                detail=f"{count} of the run's {len(deaths)} deaths were {name}.",
                confidence=Confidence.MEASURED,
                seconds_lost=_cost(theirs),
                evidence=tuple(
                    f"{death.killing_blow} at {death.timestamp_ms}ms" for death in theirs
                ),
            )
        )
    return findings
