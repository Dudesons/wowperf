# ABOUTME: Cumulative boss damage per second and where one raid's curve sits in the kills' band.
# ABOUTME: Pure arithmetic the pace findings and the pace chart both read, cannot disagree.

from collections.abc import Sequence
from enum import StrEnum
from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE


class BossDamage(Frozen):
    """Damage to one boss per bucket, as the boss-only damage graph cut it.

    `amounts` holds damage, never a rate: the adapter converts the graph's
    per-second figures at the boundary, as it does for `DamageDoneSeries`.
    Bucket `i` covers `lead_ms + i * interval_ms` onward from the fight's start.
    `lead_ms` was measured 0 on every graph read (2026-09-27); it is carried so
    a grid that ever starts late is honoured rather than assumed away.
    """

    interval_ms: float
    amounts: tuple[int, ...] = ()
    lead_ms: int = 0


def sum_boss_damage(parts: Sequence[BossDamage]) -> BossDamage | None:
    """Several bosses' damage as one series, bucket by bucket, or None.

    A council's bosses are each read through their own graph. Measured
    2026-10-01, two such graphs of one fight came back on one grid, so their
    buckets add directly; parts on different grids are refused rather than
    resampled, since no fight measured has needed it. A shorter part adds
    nothing past its end.
    """
    if not parts:
        return None
    first = parts[0]
    if any(
        part.interval_ms != first.interval_ms or part.lead_ms != first.lead_ms
        for part in parts[1:]
    ):
        return None
    length = max(len(part.amounts) for part in parts)
    return BossDamage(
        interval_ms=first.interval_ms,
        amounts=tuple(
            sum(part.amounts[index] for part in parts if index < len(part.amounts))
            for index in range(length)
        ),
        lead_ms=first.lead_ms,
    )


class PlayerSeries(Frozen):
    """One player's damage to the boss in one fight, and which class and spec they played.

    `until_seconds` is where a reference player's own death ended their part
    in the kill, counted from the pull; None when they lived to the end.
    Carries an actor id and no name.
    """

    actor_id: int
    class_name: str
    spec: str
    damage: BossDamage
    until_seconds: float | None = None


class PaceReference(Frozen):
    """One reference kill: how long it ran and what it dealt the boss.

    `players` splits `damage` by player, for the per-player comparison; it is
    empty when the kill's roster could not be read. Carries no report code and
    no name. It lives for one comparison in memory and is never written
    anywhere.
    """

    duration_seconds: float
    damage: BossDamage
    players: tuple[PlayerSeries, ...] = ()


class PaceState(StrEnum):
    BEHIND = "behind"
    ON_PACE = "on pace"
    AHEAD = "ahead"


class PaceSecond(Frozen):
    """Our cumulative boss damage at one second, and the kills' band at it."""

    second: int
    ours: float
    low: float
    median: float
    high: float

    @property
    def state(self) -> PaceState:
        if self.ours < self.low:
            return PaceState.BEHIND
        if self.ours > self.high:
            return PaceState.AHEAD
        return PaceState.ON_PACE


class PaceReading(Frozen):
    """Every compared second of one wipe against its reference kills.

    `single` is the fallback below three references: the band is the slowest
    kill alone. `band_cut` says the comparison stopped before the wipe because
    too few kills were still fighting. `target` is the kills' median total boss
    damage at their own ends -- the slowest kill's alone under the fallback.
    """

    seconds: tuple[PaceSecond, ...]
    references: int
    single: bool
    band_cut: bool
    widest_bucket_seconds: float
    target: float
    reference_durations: tuple[float, ...]


def cumulative_at(series: BossDamage, second: float) -> float:
    """Damage dealt by `second` from the pull: whole buckets, plus the covered part of one."""
    elapsed_ms = second * 1000 - series.lead_ms
    if elapsed_ms <= 0 or series.interval_ms <= 0:
        return 0.0
    whole, fraction = divmod(elapsed_ms / series.interval_ms, 1)
    index = int(whole)
    done = float(sum(series.amounts[:index]))
    if index >= len(series.amounts):
        return done
    return done + series.amounts[index] * fraction


def read_pace(
    ours: BossDamage, references: tuple[PaceReference, ...], duration_seconds: float
) -> PaceReading | None:
    """Our curve against the kills', every whole second from 1 to the wipe.

    With three or more references, each second's band is built from the kills
    still fighting at it, and the reading stops at the last second that had
    three. Below three references the slowest kill stands alone: it dealt least
    per second, so "behind" against it can only understate. None without any
    reference.
    """
    if not references:
        return None
    single = len(references) < MIN_SAMPLE_FOR_AGGREGATE
    band = (max(references, key=lambda one: one.duration_seconds),) if single else references
    needed = 1 if single else MIN_SAMPLE_FOR_AGGREGATE

    seconds: list[PaceSecond] = []
    cut = False
    for second in range(1, int(duration_seconds) + 1):
        fighting = [one for one in band if second <= one.duration_seconds]
        if len(fighting) < needed:
            cut = True
            break
        values = [cumulative_at(one.damage, second) for one in fighting]
        seconds.append(
            PaceSecond(
                second=second,
                ours=cumulative_at(ours, second),
                low=min(values),
                median=median(values),
                high=max(values),
            )
        )

    return PaceReading(
        seconds=tuple(seconds),
        references=len(references),
        single=single,
        band_cut=cut,
        widest_bucket_seconds=max(one.damage.interval_ms for one in band) / 1000,
        target=median(cumulative_at(one.damage, one.duration_seconds) for one in band),
        reference_durations=tuple(sorted(one.duration_seconds for one in band)),
    )


def behind_stretches(reading: PaceReading) -> tuple[tuple[int, int], ...]:
    """Every unbroken run of behind seconds, as inclusive (first, last) pairs."""
    stretches: list[tuple[int, int]] = []
    start: int | None = None
    previous = 0
    for one in reading.seconds:
        if one.state is PaceState.BEHIND:
            if start is None:
                start = one.second
        elif start is not None:
            stretches.append((start, previous))
            start = None
        previous = one.second
    if start is not None:
        stretches.append((start, previous))
    return tuple(stretches)


def final_behind_start(reading: PaceReading) -> int | None:
    """T: where the last stretch began, when it runs to the last compared second."""
    stretches = behind_stretches(reading)
    if not stretches or not reading.seconds:
        return None
    start, end = stretches[-1]
    return start if end == reading.seconds[-1].second else None


def earlier_behind(reading: PaceReading) -> tuple[tuple[int, int], ...]:
    """Stretches before the final one that outlasted the widest reference bucket.

    A shorter dip cannot be told from interpolating across one coarse bucket:
    measured 2026-09-27, every wipe's first ten seconds flickered this way.
    Empty unless the reading ends behind.
    """
    if final_behind_start(reading) is None:
        return ()
    return tuple(
        (start, end)
        for start, end in behind_stretches(reading)[:-1]
        if end - start + 1 > reading.widest_bucket_seconds
    )


class PaceLag(Frozen):
    """When the references' median had dealt a given amount of boss damage.

    `reached_at` is in seconds from the pull, interpolated within the second;
    None when the median never reached the amount before fewer than three
    references were still fighting. `band_end` is the last second that still
    held three.
    """

    reached_at: float | None
    band_end: int


def lag_against(amount: float, references: tuple[PaceReference, ...]) -> PaceLag:
    """The first time the references' median reached `amount`, over every second the band holds.

    The median is taken over the references still fighting at each second, as
    `read_pace` takes it, so the time lag and the share read one curve. An
    amount of zero or less is reached at the pull.
    """
    reached_at: float | None = 0.0 if amount <= 0 else None
    previous = 0.0
    band_end = 0
    second = 1
    while True:
        fighting = [one for one in references if second <= one.duration_seconds]
        if len(fighting) < MIN_SAMPLE_FOR_AGGREGATE:
            break
        current = median(cumulative_at(one.damage, second) for one in fighting)
        if reached_at is None and current >= amount:
            reached_at = second - 1 + (amount - previous) / (current - previous)
        previous = current
        band_end = second
        second += 1
    return PaceLag(reached_at=reached_at, band_end=band_end)
