# ABOUTME: What deaths cost in seconds actually not played, and which ones caused others.
# ABOUTME: The timer penalty understates a death; this measures the real thing instead.

from collections import defaultdict
from collections.abc import Callable

from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Pull

CHAIN_WINDOW_MS = 10_000
"""Deaths closer together than this are one event, not two independent ones."""


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


def pull_offset(pulls: tuple[Pull, ...], death: Death) -> str:
    """Where a death happened, in terms a reader can act on.

    A raw report-wide millisecond offset is useless: it is milliseconds since
    the report started, and a logging session can run all evening. Time since
    the death's own pull started is meaningful instead. `pull_index` is None
    when a death falls outside every pull window; report that rather than
    inventing a pull for it.
    """
    if death.pull_index is not None:
        pull = next((p for p in pulls if p.index == death.pull_index), None)
        if pull is not None:
            seconds_in = (death.timestamp_ms - pull.start_ms) / 1000
            return f"pull {death.pull_index}, {seconds_in:.0f}s in"
    return "outside any pull"


def fight_offset(start_ms: int, death: Death) -> str:
    """Where a death happened, in seconds since the fight began.

    The raid counterpart of `pull_offset`. A boss fight is its own window, so
    there is no pull to be inside or outside of, and the reader can act on
    "60s in" against a timeline they remember.
    """
    return f"{(death.timestamp_ms - start_ms) / 1000:.0f}s in"


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


def analyse_deaths(
    deaths: tuple[Death, ...],
    locate: Callable[[Death], str],
    scope: str,
    *,
    cost_detail_suffix: str = (
        " The timer penalty is counted separately, in the time decomposition."
    ),
) -> list[Finding]:
    """Report what dying cost, grouped so a wipe reads as one event.

    `locate` turns one death into the words that say where it happened, and
    `scope` says what the count is measured across. Both are passed because a
    keystone and a boss fight answer them differently, and reading them off a
    `Run` meant a raid report evidenced "across 0 pulls".

    `cost_detail_suffix` is appended to the measured `deaths.total` detail, and
    is a caller's problem for the same reason: `decompose_time` and its timer
    penalty are a Mythic+ concept a boss fight does not have, so a raid caller
    passes the empty string rather than this module branching on what kind of
    aggregate it was given.
    """
    if not deaths:
        return []

    total_cost, unmeasured_count = _measured_cost(deaths)
    evidence = [f"{len(deaths)} deaths {scope}"]
    if unmeasured_count:
        evidence.append(_unmeasured_evidence(unmeasured_count))

    if total_cost is None:
        title = f"{len(deaths)} death{'s' if len(deaths) > 1 else ''}, cost not measured"
        detail = (
            f"None of these {len(deaths)} deaths were followed by another action, so the "
            "cost cannot be measured."
        )
    else:
        title = (
            f"{len(deaths)} death{'s' if len(deaths) > 1 else ''} cost "
            f"{total_cost:.0f}s of play"
        )
        detail = (
            "Measured from each death to that player's first cast at another actor: the "
            "time the group played without them." + cost_detail_suffix
        )

    findings = [
        Finding(
            id="deaths.total",
            title=title,
            detail=detail,
            confidence=Confidence.MEASURED,
            seconds_lost=total_cost,
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
                f"{death.player_name} at {locate(death)} to "
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
                    evidence=(locate(first),),
                    pull_index=first.pull_index,
                    ability_id=first.killing_blow_id or None,
                    ability_name=first.killing_blow,
                )
            )
            single_rank += 1

    # Two players can share a display name; group by actor id so their deaths are
    # never mixed into one finding, and disambiguate the id with the actor id only
    # when that happens, so the common case stays readable. Counted from the
    # deaths themselves rather than a roster: a name collision only matters here
    # between actors who both appear in this death list. A namesake who never
    # dies therefore never disambiguates anyone: they hold no entry in `by_actor`
    # and so are never counted, even though `analyse_consumables_never_used` and
    # `analyse_defensives`, which still count off the full roster, do count them.
    # A player can end up in this run's findings under two id shapes -- pinned in
    # `test_service.test_a_never_dying_namesake_leaves_the_death_id_unsuffixed`.
    by_actor: dict[int, list[Death]] = defaultdict(list)
    for death in deaths:
        by_actor[death.actor_id].append(death)

    name_counts: dict[str, int] = defaultdict(int)
    for theirs_list in by_actor.values():
        name_counts[theirs_list[0].player_name] += 1

    for actor_id, theirs_list in by_actor.items():
        theirs = tuple(theirs_list)
        count = len(theirs)
        if count < 2:
            continue
        name = theirs[0].player_name
        seconds_lost, unmeasured_count = _measured_cost(theirs)
        detail = f"{count} of the run's {len(deaths)} deaths were {name}."
        player_evidence = tuple(
            f"{death.killing_blow} at {locate(death)}" for death in theirs
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
