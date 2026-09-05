# ABOUTME: Compares one player's buff and debuff uptime on boss pulls against a top parse.
# ABOUTME: Fractions of boss time, never seconds: two runs fight the same boss for different long.

# The debuff half never fires in practice: `on_targets` is always empty against
# the live API, confirmed 2026-09-05 (design §2.2) — no query argument narrows
# the enemy-debuff table to one caster.

from wowperf.domain.auras import Aura, PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player, Run

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
    our_seconds: float, their_seconds: float, our_has_auras: bool, their_has_auras: bool
) -> Finding:
    return Finding(
        id="compare.uptime.unavailable",
        title="Buff and debuff uptime could not be compared",
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


def _gap_findings(
    kind: str,
    ours: dict[int, tuple[str, float]],
    theirs: dict[int, tuple[str, float]],
    our_player: Player,
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

    where = "on themselves" if kind == "self" else "on the enemy"
    findings = []
    for rank, (_, ability_id, name, our_fraction, their_fraction) in enumerate(
        gaps[:MAX_AURAS_REPORTED]
    ):
        findings.append(
            Finding(
                id=f"compare.uptime.{kind}.{rank}",
                title=(
                    f"{their_name} kept {name} up for {their_fraction:.0%} of boss time "
                    f"{where}, {our_player.name} {our_fraction:.0%}"
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
            )
        )
    return findings


def compare_uptime(
    ours: Run,
    our_auras: PlayerAuras | None,
    our_player: Player,
    theirs: Run,
    their_auras: PlayerAuras | None,
    their_name: str,
) -> list[Finding]:
    """Where the reference kept an aura up markedly more of the boss fight than we did."""
    our_seconds = boss_seconds(ours)
    their_seconds = boss_seconds(theirs)

    if our_auras is None or their_auras is None or our_seconds <= 0 or their_seconds <= 0:
        return [
            _unavailable(
                our_seconds, their_seconds, our_auras is not None, their_auras is not None
            )
        ]

    our_windows = boss_windows(ours)
    their_windows = boss_windows(theirs)

    findings: list[Finding] = []
    for kind, ours_side, theirs_side in (
        ("self", our_auras.on_self, their_auras.on_self),
        ("target", our_auras.on_targets, their_auras.on_targets),
    ):
        findings += _gap_findings(
            kind,
            _fractions(ours_side, our_windows, our_seconds),
            _fractions(theirs_side, their_windows, their_seconds),
            our_player,
            their_name,
            our_seconds,
            their_seconds,
        )
    return findings
