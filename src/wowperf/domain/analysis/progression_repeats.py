# ABOUTME: What repeated across a night's attempts: the phase, the collapse, who fell first.
# ABOUTME: Counts and presence only -- naming a mechanic as missed is the one claim forbidden here.

from collections import Counter
from statistics import median

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression, Progression


def repeat_phase(progression: Progression) -> Finding | None:
    """How many attempts ended in the same phase, or nothing.

    Gated on `separates_wipes`, which is the API's own opinion about whether
    phase is a meaningful way to group this encounter's attempts. Two of the
    eight encounters measured on 2026-09-16 report no phase table at all and
    two more report `separatesWipes: false`, so silence is the common case
    rather than the defensive one.

    `last_phase` is a `PhaseMetadata.id` -- measured across all eight, and the
    reason the name is looked up rather than derived from `phase_transitions`,
    whose last entry disagreed with `last_phase` on one of them.
    """
    if not progression.separates_wipes or not progression.phases:
        return None

    ended_in = [
        a.last_phase for a in progression.attempts if a.last_phase is not None and a.last_phase
    ]
    if len(ended_in) < 2:
        return None

    phase_id, count = Counter(ended_in).most_common(1)[0]
    names = {phase.id: phase.name for phase in progression.phases}
    name = names.get(phase_id, f"phase {phase_id}")

    return Finding(
        id="progression.repeat.phase",
        title=f"{count} of {len(ended_in)} attempts ended in {name}",
        detail=(
            f"The report groups this encounter's attempts by phase, so where an attempt "
            f"ended is a fact it states outright. {count} of the {len(ended_in)} attempts "
            f"carrying a phase ended in {name}. This counts where attempts ended and says "
            "nothing about why."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{count} of {len(ended_in)} attempts ended in {name}",
            f"phase table carries {len(progression.phases)} phases",
        ),
    )


def collapse_seconds(one: LoadedEncounter) -> float | None:
    """From the first death to the end of the attempt, or None if nobody died.

    The same window `repeat_ability` reads, so the two findings cannot disagree
    about when an attempt started falling apart.
    """
    if not one.deaths:
        return None
    first = min(death.timestamp_ms for death in one.deaths)
    return (one.encounter.end_ms - first) / 1000


def collapse(series: LoadedProgression) -> Finding | None:
    """How long each attempt took to fall apart once the first player died."""
    windows = [
        seconds
        for seconds in (collapse_seconds(one) for one in series.attempts_with_events)
        if seconds is not None
    ]
    if len(windows) < 2:
        return None

    middle = median(windows)
    return Finding(
        id="progression.collapse",
        title=f"Attempts took a median of {middle:.0f} seconds to fall apart",
        detail=(
            f"Measured across {len(windows)} attempts that had a death, from the first one "
            f"to the end of the attempt. The observed range ran {min(windows):.0f} to "
            f"{max(windows):.0f} seconds. A long window is a raid bleeding out and a short "
            "one is a raid losing the fight at once; they want different fixes, and this "
            "figure is the one that tells them apart. A median and a range, never an average."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{len(windows)} attempts with a death",
            f"range {min(windows):.0f} to {max(windows):.0f} seconds",
        ),
    )


def _earliest_death(one: LoadedEncounter) -> Death | None:
    """The attempt's first death, ties broken by the lowest actor id.

    Warcraft Logs' own event stream has no guaranteed order for two deaths
    sharing a timestamp, so breaking the tie on `actor_id` keeps the pick
    deterministic instead of depending on the order events arrived in.
    """
    if not one.deaths:
        return None
    return min(one.deaths, key=lambda death: (death.timestamp_ms, death.actor_id))


def repeat_first_death(series: LoadedProgression) -> Finding | None:
    """Which specialisation died first, counted across a night's attempts.

    Matches each attempt's earliest death against the roster by `actor_id` and
    reads `spec` and `class_name` off the matching `Player` -- never
    `Death.player_name` or `Player.name`. The report holds real people, and a
    specialisation dying first is usually a fact about where that role stands
    when a pull goes wrong, not about who was playing it. This counts and
    names no one.
    """
    specs = []
    for one in series.attempts_with_events:
        death = _earliest_death(one)
        if death is None:
            continue
        player = next((p for p in one.players if p.actor_id == death.actor_id), None)
        if player is None:
            continue
        specs.append(f"{player.spec} {player.class_name}")

    if len(specs) < 2:
        return None

    spec, count = Counter(specs).most_common(1)[0]

    return Finding(
        id="progression.repeat.first_death",
        title=f"{spec} died first in {count} of {len(specs)} attempts",
        detail=(
            f"Across the {len(specs)} attempts whose earliest death matched a roster "
            f"player, {spec} was the specialisation that died first {count} times. "
            "A specialisation dying first is usually about where that role stands when "
            "a pull comes apart, not about the player in the seat -- this counts, and "
            "assigns no blame."
        ),
        confidence=Confidence.MEASURED,
        evidence=(f"{count} of {len(specs)} attempts",),
    )
