# ABOUTME: Compares one player's buff uptime on boss pulls against a top parse or a sample.
# ABOUTME: Fractions of boss time, never seconds: two runs fight the same boss for different long.

# Buffs only, and the titles here say so. The design's other half — what a player
# kept up on enemies — is not comparable per player: no query argument narrows the
# enemy-debuff table to one caster, so every row it returns belongs to the whole
# group. See `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped
# to one caster".

from collections.abc import Sequence

from wowperf.domain.auras import Aura, PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

MAX_AURAS_REPORTED = 5

MIN_UPTIME_FRACTION = 0.10
"""Below this the reference barely carried it either, so there is nothing to argue from."""

UPTIME_GAP_FRACTION = 0.15
"""How much more of the boss fight they must have it up before it is worth reporting."""


def boss_windows(run: Run) -> tuple[tuple[int, int], ...]:
    """The millisecond spans of the boss pulls, for intersecting aura bands against."""
    return tuple((pull.start_ms, pull.end_ms) for pull in run.boss_pulls)


def _fractions(
    auras: tuple[Aura, ...], windows: tuple[tuple[int, int], ...], seconds: float
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, fraction of boss time this aura was up)."""
    return {
        aura.ability_id: (aura.name, uptime_seconds_in(aura, windows) / seconds)
        for aura in auras
    }


def _unavailable(
    our_name: str,
    our_seconds: float,
    their_seconds: float,
    our_has_auras: bool,
    their_has_auras: bool,
) -> Finding:
    return Finding(
        id="compare.uptime.unavailable",
        title=f"Buff uptime could not be compared for {our_name}",
        detail=(
            "An uptime comparison needs boss pulls on both sides and aura data for both "
            "players. One of those is missing, so no uptime numbers are reported rather "
            "than numbers from an unlike sample."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"our boss time {our_seconds:.0f}s",
            f"their boss time {their_seconds:.0f}s",
            f"our aura data {'present' if our_has_auras else 'absent'}",
            f"their aura data {'present' if their_has_auras else 'absent'}",
        ),
    )


def _no_reference_auras(our_name: str, total: int) -> Finding:
    """Not one reference came back with aura data, which decides it on its own."""
    return Finding(
        id="compare.uptime.unavailable",
        title=f"Buff uptime could not be compared for {our_name}",
        detail=(
            "An uptime comparison needs aura data from a reference to compare ours against, "
            "and no reference in the sample returned any. No uptime numbers are reported "
            "rather than numbers from one side."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(f"{count_phrase(0, total)} references returned aura data",),
    )


def _gap_findings(
    ours: dict[int, tuple[str, float]],
    theirs: dict[int, tuple[str, float]],
    our_name: str,
    their_name: str,
    our_seconds: float,
    their_seconds: float,
) -> list[Finding]:
    gaps = []
    for ability_id, (name, their_fraction) in theirs.items():
        if their_fraction < MIN_UPTIME_FRACTION:
            continue
        our_fraction = ours.get(ability_id, (name, 0.0))[1]
        if our_fraction <= 0.0:
            # `onSelf` carries no source filter, so it returns teammate-cast
            # buffs, consumables, and gear procs alongside what this player
            # actually carries. Attributing a 0% on our side to this player is
            # only trustworthy for an ability they carried at all; the case of
            # a spell they never cast is already covered by compare_spells's
            # missing-spell branch, against the caster who actually owns it.
            continue
        if their_fraction - our_fraction < UPTIME_GAP_FRACTION:
            continue
        gaps.append((their_fraction - our_fraction, ability_id, name, our_fraction,
                     their_fraction))
    gaps.sort(reverse=True)

    findings = []
    for rank, (_, ability_id, name, our_fraction, their_fraction) in enumerate(
        gaps[:MAX_AURAS_REPORTED]
    ):
        findings.append(
            Finding(
                id=f"compare.uptime.self.{rank}",
                title=(
                    f"{their_name} kept {name} up for {their_fraction:.0%} of boss time, "
                    f"{our_name} {our_fraction:.0%}"
                ),
                detail=(
                    "Both figures are the share of boss-pull time the aura was present, which "
                    "is comparable even though the two fights ran for different lengths. A "
                    "shorter fight at a different keystone level still changes what fits, so "
                    "read a narrow gap as noise. This compares by exact ability, though, so a "
                    "gap can also mean a different item of the same kind, or gear this player "
                    "does not own — not that nothing was used at all."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_seconds:.0f}s of boss pulls",
                    f"theirs over {their_seconds:.0f}s of boss pulls",
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    return findings


def compare_uptime(
    ours: Run,
    our_auras: PlayerAuras | None,
    our_name: str,
    theirs: Run,
    their_auras: PlayerAuras | None,
    their_name: str,
) -> list[Finding]:
    """Where the reference kept an aura up markedly more of the boss fight than we did.

    `our_name` is the roster's disambiguated spelling of the player being
    compared — never `Player.name`, which two roster members can share, and
    which would then title two players' findings identically.
    """
    our_seconds = boss_seconds(ours)
    their_seconds = boss_seconds(theirs)

    if our_auras is None or their_auras is None or our_seconds <= 0 or their_seconds <= 0:
        return [
            _unavailable(
                our_name,
                our_seconds,
                their_seconds,
                our_auras is not None,
                their_auras is not None,
            )
        ]

    our_windows = boss_windows(ours)
    their_windows = boss_windows(theirs)

    # Named at the call site: the four arguments below are two pairs of
    # same-typed values, and a swap inside either pair would put one player's
    # figure under the other's name without failing a type check.
    return _gap_findings(
        _fractions(our_auras.on_self, our_windows, our_seconds),
        _fractions(their_auras.on_self, their_windows, their_seconds),
        our_name=our_name,
        their_name=their_name,
        our_seconds=our_seconds,
        their_seconds=their_seconds,
    )


def compare_uptime_sample(
    ours: Run,
    our_auras: PlayerAuras | None,
    our_name: str,
    sample: ParseSample,
) -> list[Finding]:
    """Where the sample's top parses kept an aura up markedly more of the boss fight than we did.

    `our_name` is the roster's disambiguated spelling, for the reason
    `compare_uptime` above gives.

    No member is named: the claim is about the sample as a population, the same way
    `compare_spells_sample` reports a count or a median rather than one parse's number.
    Requiring at least `MIN_SAMPLE_FOR_AGGREGATE` parses to have carried a given ability before
    its gap is reported is what lets the sample retire this finding's old hedge about a single
    player's gear: a one-off proc or a teammate's buff bleeding through `onSelf`'s missing
    source filter cannot reach that many parses, so a surviving gap is the aura itself, not the
    noise around it. The below-floor fallback delegates to `compare_uptime`, the one place a
    reference name still appears, because there it is honestly one reference's pairwise
    comparison, not a population claim.
    """
    # A wholly empty sample means there was nothing to compare against at all;
    # `service.compare()` already says so once, as `compare.parse.unavailable`, so
    # returning nothing here avoids repeating that finding for a comparison that
    # never ran. This is distinct from every member lacking aura data, which the
    # below-floor fallback below reports as `compare.uptime.unavailable` because
    # the reference it falls back to has none.
    if not sample.members:
        return []

    eligible = sample.aura_eligible
    aggregable = sample.can_aggregate(eligible)

    if not eligible:
        # The reference side alone settles it, and saying so is the only honest
        # answer available: `cli._fetch_parse_auras` fetches our own aura data
        # once any member's counterpart resolves, so when not one member has
        # aura data our own may never have been asked for. Delegating to
        # `compare_uptime` here would report "our aura data absent" for a query
        # that was never issued.
        return [_no_reference_auras(our_name, len(sample.members))]

    if our_auras is None or boss_seconds(ours) <= 0 or not aggregable:
        # Below the floor, or our own side has nothing to compute a fraction from
        # either way: one reference is all that can honestly be reported, and
        # `compare_uptime`'s own availability check already decides whether that
        # comes back as a real gap or as `compare.uptime.unavailable`. `too_few`
        # is only wrapped on when the sample itself was the reason — wrapping it
        # around a failure caused by our own missing data would blame the sample
        # for a gap that was never the sample's fault.
        first = eligible[0] if eligible else sample.members[0]
        fallback = compare_uptime(
            ours, our_auras, our_name, first.run, first.auras, first.row.character_name
        )
        return fallback if aggregable else too_few(fallback, len(eligible))

    our_windows = boss_windows(ours)
    our_seconds = boss_seconds(ours)
    total = len(sample.members)
    missing_aura_data = total - len(eligible)

    our_fractions = _fractions(our_auras.on_self, our_windows, our_seconds)
    return _gap_findings_sample(
        our_fractions, eligible, our_name, our_seconds, missing_aura_data, total
    )


def _gap_findings_sample(
    our_fractions: dict[int, tuple[str, float]],
    eligible: Sequence[ParseMember],
    our_name: str,
    our_seconds: float,
    missing_aura_data: int,
    total: int,
) -> list[Finding]:
    """Abilities the sample's top parses kept up markedly more than we did, by median.

    A member's fraction for an ability only counts as "carried" when it is above zero: a
    band that never overlaps a boss pull reads the same as never having the aura at all, the
    same reading `_fractions` already gives the pairwise comparison.
    """
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
            if fraction <= 0.0:
                continue
            names.setdefault(ability_id, name)
            qualifying[ability_id] = fraction
        per_member.append(qualifying)

    gaps = []
    for ability_id, name in names.items():
        carried = [q[ability_id] for q in per_member if ability_id in q]
        if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
            # A one-off proc or a teammate's buff bleeding through `onSelf`'s
            # missing source filter cannot reach this many parses; requiring it
            # here is what lets the detail below retire the old hedge about a
            # single player's gear.
            continue
        their_median = median(carried)
        if their_median < MIN_UPTIME_FRACTION:
            continue
        our_fraction = our_fractions.get(ability_id, (name, 0.0))[1]
        if our_fraction <= 0.0:
            continue
        if their_median - our_fraction < UPTIME_GAP_FRACTION:
            continue
        gaps.append(
            (their_median - our_fraction, ability_id, name, our_fraction, their_median, carried)
        )
    gaps.sort(key=lambda row: row[0], reverse=True)

    findings = []
    for rank, (_, ability_id, name, our_fraction, their_median, carried) in enumerate(
        gaps[:MAX_AURAS_REPORTED]
    ):
        low, high = observed_range(carried)
        findings.append(
            Finding(
                id=f"compare.uptime.self.{rank}",
                title=(
                    f"{len(carried)} top parses kept {name} up a median {their_median:.0%} "
                    f"of boss time; {our_name} {our_fraction:.0%}"
                ),
                detail=(
                    "Both figures are the share of boss-pull time the aura was present, which "
                    "is comparable even though the fights ran for different lengths. A shorter "
                    "fight at a different keystone level still changes what fits, so read a "
                    "narrow gap as noise. This compares by exact ability, so a gap can still "
                    "mean a different item of the same kind — but the gap is stated over "
                    "several top parses, not one player's build, so a single trinket this "
                    "player happens not to own no longer explains it away."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_seconds:.0f}s of boss pulls",
                    f"range {low:.0%} to {high:.0%} across {len(carried)} top parses",
                    f"{count_phrase(missing_aura_data, total)} references had no aura data",
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    return findings
