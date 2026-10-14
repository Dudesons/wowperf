# ABOUTME: Assembles everything one player's comparison measured, for the report's table.
# ABOUTME: Reads the same measurements the findings do, so the two cannot disagree.

from collections.abc import Sequence

from wowperf.domain.aura_groups import AuraGroups
from wowperf.domain.auras import PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import Span, Withheld, length_ms, merged_spans
from wowperf.domain.comparison.debuff_uptime import debuff_table
from wowperf.domain.comparison.key_debuffs import KeyDebuffs
from wowperf.domain.comparison.loadout import loadouts_of, stat_measures
from wowperf.domain.comparison.measures import AbilityRate, AuraRow, PlayerMeasures
from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.comparison.service import ComparisonSubject
from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    boss_casts,
    boss_seconds,
    casts_in,
    in_pulls,
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
    aura_fractions,
    boss_windows,
    fight_seconds,
    grouped_auras,
    grouped_members,
    measured_or,
    stretch_cell,
    uptime_measures,
    without_boss_pulls,
)
from wowperf.domain.model import LoadedRun, Player, Pull


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
        measures[subject.slug] = _for_one(
            ours, subject.player, subject.our_auras, subject.our_debuffs, parse,
            subject.aura_groups,
        )
    return measures


def _for_one(
    ours: LoadedRun,
    our_player: Player,
    our_auras: PlayerAuras | None,
    our_debuffs: KeyDebuffs | None,
    parse: ParseSample,
    aura_groups: AuraGroups,
) -> PlayerMeasures:
    """One player's sets of measures, each drawn against the whole sample."""
    boss, boss_time = _boss(ours, our_player, parse)
    trash, trash_time, pack_count = _trash(ours, our_player, parse)
    auras, key_seconds = _auras(ours, our_auras, parse, aura_groups)
    return PlayerMeasures(
        boss=boss,
        trash=trash,
        auras=auras,
        # Read straight off the loadouts, with no run in it: a stat share is a
        # fact about gear, not about a stretch of the dungeon, so unlike the
        # three above it needs no denominator and no pull alignment.
        stats=stat_measures(our_player.loadout, loadouts_of(parse.members)),
        debuffs=debuff_table(our_debuffs, parse),
        boss_seconds=boss_time,
        trash_seconds=trash_time,
        pack_count=pack_count,
        key_seconds=key_seconds,
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
    if not parse.can_aggregate(parse.members):
        # The gate `compare_spells_sample` opens on, asked of the sample itself
        # so that both read one definition of when a sample may be argued from
        # as a population, rather than each enforcing a floor of its own.
        #
        # While `MIN_SAMPLE_FOR_AGGREGATE` and `MIN_MEMBERS_WITH_ABILITY` are
        # both 3 this changes no rate: no ability can gather more rates than
        # the sample has members, so `rate_measures` finds nothing below the
        # floor whether it is asked or not. All it settles at those values is
        # that the denominator reads zero instead of naming boss seconds no
        # comparison was ever drawn over. Raise the first above the second and
        # it decides the rates as well, which is what keeps a median off the
        # page beside a finding that withheld one.
        return (), 0.0

    per_member: list[tuple[float, dict[int, int]]] = []
    for member in parse.members:
        actor_id = their_actor_id(member, member.character_name)
        their_boss_seconds = member.boss_seconds
        if actor_id is None or their_boss_seconds <= 0:
            # The seconds half of this is what keeps a zero out of
            # `rate_measures`' denominator: it divides by a member's seconds
            # with no guard of its own, and says why in its own docstring.
            per_member.append((0.0, {}))
            continue
        casts_by_ability = boss_casts(member.pulls, member.casts, actor_id)
        qualifying = {
            ability_id: count
            for ability_id, (_name, count) in casts_by_ability.items()
            if count >= MIN_CASTS_TO_COMPARE
        }
        per_member.append((their_boss_seconds, qualifying))

    our_boss_seconds = boss_seconds(ours.run.pulls)
    if our_boss_seconds <= 0:
        return (), 0.0
    ours_on_bosses = boss_casts(ours.run.pulls, ours.casts, our_player.actor_id)
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
    symmetric with it — boss seconds are ours whenever a comparison was drawn
    over them, whether or not it found anything worth a row.

    There is no aggregate gate here to match `_boss`'s, because
    `compare_trash_spells_sample` has none: a trash rate is already floored on
    seconds of aligned trash per side, and a sample too small to aggregate
    reaches `trash_rate_measures`, which needs `MIN_MEMBERS_WITH_ABILITY` rates
    for a median of its own.
    """
    ours_aligned: list[AlignedTrash] = []
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in parse.members:
        actor_id = their_actor_id(member, member.character_name)
        aligned = aligned_trash(ours.run, member.pulls)
        if actor_id is None or not is_comparable(aligned):
            per_member.append((0.0, {}))
            continue
        ours_aligned.append(aligned)
        their_casts = casts_in(member.casts, actor_id, in_pulls(aligned.their_pulls))
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
    ours_on_trash = casts_in(ours.casts, our_player.actor_id, in_pulls(our_pulls))
    return (
        trash_rate_measures(ours_on_trash, our_seconds, per_member),
        our_seconds,
        len(our_pulls),
    )


def _auras(
    ours: LoadedRun, our_auras: PlayerAuras | None, parse: ParseSample, aura_groups: AuraGroups
) -> tuple[tuple[AuraRow, ...], float]:
    """Buff uptime against the sample's median: judged over the key clock, described beside it.

    Buffs only, from this table: no query argument narrows the enemy-debuff
    table to one caster, so what a player kept up on enemies cannot come from
    it. That figure is rebuilt from the event stream instead, and sits beside
    these in `debuffs` (see `comparison/key_debuffs.py` and
    `.claude/skills/wcl-api/SKILL.md`, "The debuff event stream does name the
    caster").

    The verdict reads each side's whole key clock, from its fight's start to its
    end, as `compare_uptime_sample` does for the findings. Without bosses and
    Bosses describe and never judge. The seconds returned are our own key
    clock's, and zero beside no rows.
    """
    # Folded by the groups on both sides, as `compare_uptime_sample` folds them for the
    # findings, so a row and the finding above it name one cause the same way.
    our_auras = grouped_auras(our_auras, aura_groups)
    eligible = grouped_members(parse.aura_eligible, aura_groups)
    if not eligible:
        # Not one reference returned aura data, which settles it on the
        # reference side alone: there is nothing for ours to be compared against.
        return (), 0.0

    our_fight = ours.run.fight_ms
    our_seconds = fight_seconds(our_fight)
    if (
        our_auras is None
        or our_fight is None
        or our_seconds <= 0
        or not parse.can_aggregate(eligible)
    ):
        # Below the floor, or our own side has nothing to compute a fraction
        # from either way. The comparison states a single reference here rather
        # than a statistic, and one reference has no median for a table to hold.
        return (), 0.0

    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in eligible:
        assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
        fight = member.fight_ms
        their_seconds = fight_seconds(fight)
        fractions = (
            aura_fractions(member.auras.on_self, (fight,), their_seconds)
            if fight is not None and their_seconds > 0
            else {}
        )
        qualifying: dict[int, float] = {}
        for ability_id, (name, fraction) in fractions.items():
            # A band that never overlaps the key clock reads the same as never
            # having carried the aura at all, the reading `aura_fractions` already
            # gives the pairwise comparison.
            if fraction <= 0.0:
                continue
            names.setdefault(ability_id, name)
            qualifying[ability_id] = fraction
        per_member.append(qualifying)

    our_fractions = aura_fractions(our_auras.on_self, (our_fight,), our_seconds)
    our_away, our_bosses = _beside(our_fight, ours.run.pulls)
    rows: list[AuraRow] = []
    for m in uptime_measures(our_fractions, per_member, names):
        away: list[float | None] = []
        on_bosses: list[float | None] = []
        for member in eligible:
            assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
            their_away, their_bosses = _beside(member.fight_ms, member.pulls)
            away.append(_share_in(member.auras, m.ability_id, their_away))
            on_bosses.append(_share_in(member.auras, m.ability_id, their_bosses))
        our_away_share = _share_in(our_auras, m.ability_id, our_away)
        our_boss_share = _share_in(our_auras, m.ability_id, our_bosses)
        rows.append(
            AuraRow(
                uptime=m,
                without_bosses=stretch_cell(
                    measured_or(our_away_share, Withheld.NOTHING_OUTSIDE_BOSSES), away
                ),
                bosses=stretch_cell(measured_or(our_boss_share, Withheld.NO_BOSS), on_bosses),
            )
        )
    return tuple(rows), our_seconds


def _beside(
    fight_ms: Span | None, pulls: Sequence[Pull]
) -> tuple[tuple[Span, ...], tuple[Span, ...]]:
    """A side's two described stretches: the key clock less its boss pulls, and its boss pulls."""
    away = without_boss_pulls(fight_ms, pulls) if fight_ms is not None else ()
    return away, boss_windows(pulls)


def _share_in(auras: PlayerAuras, ability_id: int, windows: tuple[Span, ...]) -> float | None:
    """This aura's share of these windows, or None when they hold no time at all.

    The denominator is the time the windows cover, an overlap counted once, as
    `uptime_seconds_in` counts it in the numerator. `boss_windows` lists a boss
    pull Warcraft Logs lists twice once, but two distinct boss pulls may still
    overlap, and summing them as given would count their overlap twice.
    """
    seconds = length_ms(merged_spans(windows)) / 1000
    if seconds <= 0:
        return None
    aura = next((one for one in auras.on_self if one.ability_id == ability_id), None)
    return 0.0 if aura is None else uptime_seconds_in(aura, windows) / seconds
