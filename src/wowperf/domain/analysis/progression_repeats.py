# ABOUTME: What repeated across a night's attempts -- the phase, collapse, who fell first, to what.
# ABOUTME: Counts and presence only -- naming a mechanic as missed is the one claim forbidden here.

from collections import Counter
from statistics import median
from typing import TypeVar

from wowperf.domain.analysis.recap import lethal_hit
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding, quantity
from wowperf.domain.progression import LoadedProgression, Progression

# Bound to the two concrete key types this module counts: a `PhaseMetadata.id`
# in `repeat_phase`, a "spec class" label in `repeat_first_death`. Both order
# comparably, which an unbound TypeVar would not let `sorted()` assume.
_K = TypeVar("_K", int, str)


def _tied_for_first(counts: "Counter[_K]") -> tuple[int, list[_K]]:
    """The winning count and every key that reaches it, sorted for determinism.

    `Counter.most_common(1)` breaks a tie by first-seen order and reports one
    winner as if it had no rivals, hiding that a tie happened at all. This
    returns every key sharing the top count instead, so a caller can name them
    all rather than picking one arbitrarily.
    """
    top = max(counts.values())
    winners = sorted(key for key, count in counts.items() if count == top)
    return top, winners


def _join_or(items: list[str]) -> str:
    """Join tied names as prose: one alone, or a comma list ending in "or".

    Never an "and": these are alternatives that tied for the same count, not a
    set that all held true together.
    """
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} or {items[-1]}"


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

    Withheld when the winning count is 1: with every attempt ending somewhere
    different, nothing repeated, and reporting "1 of N attempts ended in X"
    would dress that noise as a pattern. When more than one phase ties for the
    top count, every tied phase is named -- `Counter.most_common(1)` would
    otherwise report whichever tied phase happened to appear first, silently
    hiding the tie.
    """
    if not progression.separates_wipes or not progression.phases:
        return None

    ended_in = [
        a.last_phase for a in progression.attempts if a.last_phase is not None and a.last_phase
    ]
    if len(ended_in) < 2:
        return None

    count, winners = _tied_for_first(Counter(ended_in))
    if count < 2:
        return None

    names = {phase.id: phase.name for phase in progression.phases}
    name = _join_or([names.get(phase_id, f"phase {phase_id}") for phase_id in winners])

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


def _first_death_ms(one: LoadedEncounter) -> int | None:
    """The timestamp of an attempt's first roster death, or None if no roster
    player died.

    The one figure `collapse_seconds` and `repeat_ability` both build their
    window from, so the two findings cannot disagree about when an attempt
    started falling apart. Filtered to `one.players` for the same reason
    `repeat_first_death` matches its own earliest death against the roster: a
    pet or an unidentified actor dying first is not a roster player's death,
    and letting one anchor this window would let the three analysers disagree
    about which death started an attempt's collapse.
    """
    roster_ids = {player.actor_id for player in one.players}
    deaths = [death for death in one.deaths if death.actor_id in roster_ids]
    if not deaths:
        return None
    return min(death.timestamp_ms for death in deaths)


def collapse_seconds(one: LoadedEncounter) -> float | None:
    """From the first death to the end of the attempt, or None if nobody died.

    The same window `repeat_ability` reads, so the two findings cannot disagree
    about when an attempt started falling apart.
    """
    first = _first_death_ms(one)
    if first is None:
        return None
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

    Withheld when the winning count is 1: two or more attempts identified is
    not the same claim as one specialisation recurring, and "died first in 1
    of N attempts" would report a mode of one as if it were a pattern. When
    more than one specialisation ties for the top count, both are named
    rather than one picked arbitrarily.
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

    count, winners = _tied_for_first(Counter(specs))
    if count < 2:
        return None
    name = _join_or(winners)

    return Finding(
        id="progression.repeat.first_death",
        title=f"{name} died first in {count} of {len(specs)} attempts",
        detail=(
            f"Across the {len(specs)} attempts whose earliest death matched a roster "
            f"player, {name} died first {count} times. "
            "A specialisation dying first is usually about where that role stands when "
            "a pull comes apart, not about the player in the seat -- this counts, and "
            "assigns no blame."
        ),
        confidence=Confidence.MEASURED,
        evidence=(f"{count} of {len(specs)} attempts",),
    )


MAX_REPEAT_ABILITIES = 5


def repeat_killing_blow(series: LoadedProgression) -> Finding | None:
    """Which abilities dealt each attempt's first death, counted across the night.

    Reads the death `_earliest_death` picks -- the one `repeat_first_death`
    reads -- so the two findings always speak of the same death on every pull.
    Only the first: on a wipe most deaths come after the raid has come apart,
    and counting them would measure what finishes a lost pull rather than what
    started it going wrong.

    An attempt drops out when its first death matches no roster player, names
    no ability (`killing_blow_id` zero), or was dealt by a roster player -- the
    rule `repeat.ability` applies to every hit, since a teammate's hit says
    nothing about the encounter. Where the stream holds no lethal hit, or the
    hit names no source, the attempt stays: the log still named the ability.

    Withheld below two qualifying attempts, or when no ability reaches two: a
    mode of one is not a pattern. No control subtraction against the deepest
    attempt, unlike `repeat_ability` -- a best attempt that also opened with
    this death is more reason to name it, not less. Measured: the log names the
    death and its blow, and the rest is counting. Names no player and no
    specialisation; who died first is `repeat_first_death`'s claim.
    """
    names: dict[int, str] = {}
    counts: Counter[int] = Counter()
    qualifying = 0
    for one in series.attempts_with_events:
        death = _earliest_death(one)
        if death is None or not death.killing_blow_id:
            continue
        roster = {player.actor_id for player in one.players}
        if death.actor_id not in roster:
            continue
        hit = lethal_hit(one.damage_taken, death)
        if hit is not None and hit.source_id is not None and hit.source_id in roster:
            continue
        qualifying += 1
        names.setdefault(death.killing_blow_id, death.killing_blow)
        counts[death.killing_blow_id] += 1

    if qualifying < 2:
        return None
    named = sorted(
        (ability_id for ability_id, count in counts.items() if count >= 2),
        key=lambda ability_id: (-counts[ability_id], names[ability_id]),
    )[:MAX_REPEAT_ABILITIES]
    if not named:
        return None

    lines = tuple(
        f"{names[ability_id]} dealt the first death in {counts[ability_id]} of "
        f"{qualifying} attempts"
        for ability_id in named
    )
    single = named[0] if len(named) == 1 else None
    return Finding(
        id="progression.repeat.killing_blow",
        title=(
            lines[0]
            if single is not None
            else f"{len(named)} abilities dealt the first death in more than one attempt"
        ),
        detail=(
            f"Across the {qualifying} attempts whose first death was a roster player "
            "killed by an ability the log named: "
            + "; ".join(lines)
            + ". Only each attempt's first death is read -- the one the rest of a wipe "
            "cannot swamp -- and an attempt whose first death a raider dealt is left out. "
            "This counts what the log names; it does not say the death could have been "
            "avoided."
        ),
        confidence=Confidence.MEASURED,
        evidence=lines,
        ability_id=single,
        ability_name=names[single] if single is not None else "",
    )


def _abilities_in_window(one: LoadedEncounter) -> dict[int, str] | None:
    """Enemy-sourced abilities landing from an attempt's first death to its
    end, named by id. None when the attempt had no death, so it carries no
    window at all.

    A hit whose `source_id` is a roster player -- including the victim's own
    id, which is self-damage -- is excluded outright rather than counted.
    Measured 2026-09-16 across 19 fights and 8 encounters: outside one
    anomalous encounter, that population is 99 hits across 17 fights, and even
    inside it, it is entirely teammates' own class abilities landing on a raid
    member the encounter turned hostile -- never a bearing on what the enemy
    did. An ability like Blessing of Sacrifice, a cooldown that redirects
    damage away from an ally, would otherwise show up here as something that
    repeatedly ends attempts, which is not what it does.
    """
    first = _first_death_ms(one)
    if first is None:
        return None

    friendly_ids = {player.actor_id for player in one.players}
    names: dict[int, str] = {}
    for hit in one.damage_taken:
        if hit.timestamp_ms < first:
            continue
        # A hit with no source_id is kept rather than excluded: the log naming
        # nobody is not evidence of a teammate, and dropping it would silently
        # discard a real enemy hit. Measured 2026-09-16: all 15,798 damage rows
        # on the probed fight carried a source_id, so this branch is
        # near-unreachable in practice, but it is a live and deliberate default.
        if hit.source_id is not None and hit.source_id in friendly_ids:
            continue
        names.setdefault(hit.ability_id, hit.ability_name)
    return names


def repeat_ability(series: LoadedProgression) -> Finding | None:
    """Which abilities kept landing while attempts fell apart, named and counted.

    The window is the one `_first_death_ms` gives `collapse_seconds`: from an
    attempt's first death to its end. An attempt with no death contributes
    nothing.

    The deepest attempt in the series -- `LoadedProgression.deepest_loaded` --
    is the control. An ability landing inside its own window is the encounter
    working as designed: a soak, a link, a controlled detonation that the best
    attempt took too, not something that kept a shallower attempt from
    surviving (design section 5.2). Such an ability is dropped regardless of
    how many other attempts it appeared in. The finding is withheld entirely
    when the deepest attempt carries no window of its own: no death there
    means no control to compare against, and treating every ability as "absent
    from the control" in that case would invert the rule into naming
    everything rather than staying quiet.

    Counts attempts an ability appeared in, never hits, and reports only
    abilities present in more than half the attempts with a window, capped at
    five. Confidence is derived rather than measured: which hits fall inside
    the window is a modelling choice, not a fact the log states outright.
    """
    deepest = series.deepest_loaded
    if deepest is None:
        return None
    control = _abilities_in_window(deepest)
    if control is None:
        return None
    control_ids = set(control)

    attempts_with_window = 0
    ability_names: dict[int, str] = {}
    attempts_by_ability: Counter[int] = Counter()

    for one in series.attempts_with_events:
        seen = _abilities_in_window(one)
        if seen is None:
            continue
        attempts_with_window += 1
        for ability_id, name in seen.items():
            ability_names.setdefault(ability_id, name)
            attempts_by_ability[ability_id] += 1

    if attempts_with_window < 2:
        return None

    qualifying = [
        (ability_id, count)
        for ability_id, count in attempts_by_ability.items()
        if count > attempts_with_window / 2 and ability_id not in control_ids
    ]
    if not qualifying:
        return None

    qualifying.sort(key=lambda pair: (-pair[1], ability_names[pair[0]]))
    top = qualifying[:MAX_REPEAT_ABILITIES]

    lines = tuple(
        f"{ability_names[ability_id]} landed in {count} of {attempts_with_window} attempts"
        for ability_id, count in top
    )

    return Finding(
        id="progression.repeat.ability",
        title=f"{quantity(len(top), 'ability', 'abilities')} kept landing as attempts fell apart",
        detail=(
            f"Across the {attempts_with_window} attempts carrying a window from the first "
            "death to the end, these abilities kept landing on someone after the raid "
            "started coming apart: "
            + "; ".join(lines)
            + ". This counts the attempts each ability appeared in, not hits, and excludes "
            "any hit a roster player dealt, self-damage included, along with any ability "
            "that also landed inside the deepest attempt's own window -- the deepest attempt "
            "is the control, so an ability it saw too reads as the encounter working as "
            "designed, not as something worth naming. Which hits fall inside a window is a "
            "modelling choice, so this reads as derived rather than measured, and states "
            "only what kept landing, nothing about why an attempt ended."
        ),
        confidence=Confidence.DERIVED,
        evidence=lines,
    )
