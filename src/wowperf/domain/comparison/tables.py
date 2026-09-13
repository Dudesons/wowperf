# ABOUTME: Assembles everything one player's comparison measured, for the report's table.
# ABOUTME: Reads the same measurements the findings do, so the two cannot disagree.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.measures import AbilityRate, AuraUptime, PlayerMeasures
from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.comparison.service import ComparisonSubject
from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    boss_casts,
    boss_seconds,
    casts_in,
    rate_measures,
    their_actor_id,
)
from wowperf.domain.comparison.trash_spells import (
    AlignedTrash,
    aligned_trash,
    is_comparable,
    trash_rate_measures,
)
from wowperf.domain.comparison.uptime import (
    _fractions,
    boss_windows,
    uptime_measures,
)
from wowperf.domain.model import LoadedRun, Player


def comparison_measures(
    ours: LoadedRun, subjects: Sequence[ComparisonSubject]
) -> dict[str, PlayerMeasures]:
    """Everything each compared player's comparison measured, keyed by slug.

    A player whose parse sample is absent or empty gets no entry at all. An
    empty table and a missing one are different claims: the first says a
    comparison ran and measured nothing, the second that none ran.

    This repeats the arithmetic `compare()` already did. That is deliberate:
    the alternative is for `compare()` to return a tuple, changing a signature
    every test and both callers use, to save microseconds of pure arithmetic
    over data already in memory. Duplicate execution, single definition.
    """
    measures: dict[str, PlayerMeasures] = {}
    for subject in subjects:
        parse = subject.parse
        if parse is None or not parse.members:
            continue
        measures[subject.slug] = _for_one(ours, subject.player, subject.our_auras, parse)
    return measures


def _for_one(
    ours: LoadedRun, our_player: Player, our_auras: PlayerAuras | None, parse: ParseSample
) -> PlayerMeasures:
    """One player's three sets of measures, each drawn against the whole sample."""
    boss, boss_time = _boss(ours, our_player, parse)
    trash, trash_time, pack_count = _trash(ours, our_player, parse)
    return PlayerMeasures(
        boss=boss,
        trash=trash,
        auras=_auras(ours, our_auras, parse),
        boss_seconds=boss_time,
        trash_seconds=trash_time,
        pack_count=pack_count,
    )


def _boss(
    ours: LoadedRun, our_player: Player, parse: ParseSample
) -> tuple[tuple[AbilityRate, ...], float]:
    """Boss-pull cast rates against the sample, and the seconds ours were measured over.

    One (boss seconds, qualifying casts) pair per member, built the way
    `compare_spells_sample` builds it. A member whose own actor cannot be found
    in their own report, or who fought no boss at all, contributes an empty
    qualifying set rather than being dropped, so a member the finding counts and
    a member this counts are the same member — the only thing keeping a table
    row and the finding above it from stating different numbers about one
    player.
    """
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in parse.members:
        actor_id = their_actor_id(member, member.row.character_name)
        their_boss_seconds = boss_seconds(member.run)
        if actor_id is None or their_boss_seconds <= 0:
            per_member.append((0.0, {}))
            continue
        casts_by_ability = boss_casts(member.run, member.casts, actor_id)
        qualifying = {
            ability_id: count
            for ability_id, (_name, count) in casts_by_ability.items()
            if count >= MIN_CASTS_TO_COMPARE
        }
        per_member.append((their_boss_seconds, qualifying))

    our_boss_seconds = boss_seconds(ours.run)
    if our_boss_seconds <= 0:
        return (), 0.0
    ours_on_bosses = boss_casts(ours.run, ours.casts, our_player.actor_id)
    return rate_measures(ours_on_bosses, our_boss_seconds, per_member), our_boss_seconds


def _trash(
    ours: LoadedRun, our_player: Player, parse: ParseSample
) -> tuple[tuple[AbilityRate, ...], float, int]:
    """Cast rates on the packs our route shared with the sample's, and both denominators.

    The member loop is `compare_trash_spells_sample`'s, for the reason `_boss`
    above gives. A member whose actor cannot be found, or who shared too little
    trash with our route for either side's rate to be argued from, contributes
    an empty qualifying set and no packs of ours.

    When no reference shares enough of our route, the seconds come back zero
    rather than as the trash time we happened to spend: this denominator is
    aligned trash, and with nothing aligned there is none. `_boss` is not
    symmetric with it — boss seconds are ours whether or not anything compared.
    """
    ours_aligned: list[AlignedTrash] = []
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in parse.members:
        actor_id = their_actor_id(member, member.row.character_name)
        aligned = aligned_trash(ours.run, member.run)
        if actor_id is None or not is_comparable(aligned):
            per_member.append((0.0, {}))
            continue
        ours_aligned.append(aligned)
        their_casts = casts_in(member.casts, actor_id, aligned.their_pulls)
        per_member.append(
            (
                aligned.their_seconds,
                {
                    ability_id: count
                    for ability_id, (_name, count) in their_casts.items()
                    if count >= MIN_CASTS_TO_COMPARE
                },
            )
        )

    if not ours_aligned:
        return (), 0.0, 0

    # Our own denominator is the union of every pack that aligned with anybody:
    # a pack one reference skipped is still a pack we fought and were compared on.
    our_pulls = frozenset().union(*(aligned.our_pulls for aligned in ours_aligned))
    our_seconds = sum(
        pull.duration_seconds for pull in ours.run.pulls if pull.index in our_pulls
    )
    if our_seconds <= 0:
        return (), 0.0, 0
    ours_on_trash = casts_in(ours.casts, our_player.actor_id, our_pulls)
    return (
        trash_rate_measures(ours_on_trash, our_seconds, per_member),
        our_seconds,
        len(our_pulls),
    )


def _auras(
    ours: LoadedRun, our_auras: PlayerAuras | None, parse: ParseSample
) -> tuple[AuraUptime, ...]:
    """Buff uptime against the sample's median, as shares of boss time.

    Buffs only, as everywhere the uptime comparison reaches: no query argument
    narrows the enemy-debuff table to one caster, so the matching figure for
    what a player kept up on enemies does not exist to put beside these.
    """
    eligible = parse.aura_eligible
    if not eligible:
        # Not one reference returned aura data, which settles it on the
        # reference side alone: there is nothing for ours to be compared against.
        return ()

    our_seconds = boss_seconds(ours.run)
    if our_auras is None or our_seconds <= 0 or not parse.can_aggregate(eligible):
        # Below the floor, or our own side has nothing to compute a fraction
        # from either way. The comparison states a single reference here rather
        # than a statistic, and one reference has no median for a table to hold.
        return ()

    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in eligible:
        assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
        their_seconds = boss_seconds(member.run)
        fractions = (
            _fractions(member.auras.on_self, boss_windows(member.run), their_seconds)
            if their_seconds > 0
            else {}
        )
        qualifying: dict[int, float] = {}
        for ability_id, (name, fraction) in fractions.items():
            # A band that never overlaps a boss pull reads the same as never
            # having carried the aura at all, the reading `_fractions` already
            # gives the pairwise comparison.
            if fraction <= 0.0:
                continue
            names.setdefault(ability_id, name)
            qualifying[ability_id] = fraction
        per_member.append(qualifying)

    our_fractions = _fractions(our_auras.on_self, boss_windows(ours.run), our_seconds)
    return uptime_measures(our_fractions, per_member, names)
