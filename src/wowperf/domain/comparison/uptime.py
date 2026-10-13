# ABOUTME: Compares one player's buff uptime against a top parse or a sample, by one caller's rule.
# ABOUTME: Fractions of the stretch a rule names, never seconds: two runs last different lengths.

# Buffs only, and the titles here say so. The design's other half — what a player
# kept up on enemies — cannot come from the aura table: no query argument narrows the
# enemy-debuff table to one caster, so every row it returns belongs to the whole
# group (`.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one
# caster"). It is rebuilt from the event stream instead, for every enemy of a key, in
# `debuff_uptime.py` and `key_debuffs.py` (same skill, "The debuff event stream does
# name the caster").

from collections.abc import Callable, Collection, Sequence

from wowperf.domain.auras import Aura, PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import Span, Withheld, boss_pulls_listed_once
from wowperf.domain.comparison.measures import AuraUptime, StretchCell, Verdict
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.comparison.wording import Wording
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity
from wowperf.domain.model import Pull

MAX_AURAS_REPORTED = 5

MIN_UPTIME_FRACTION = 0.10
"""Below this the reference barely carried it either, so there is nothing to argue from."""

UPTIME_GAP_FRACTION = 0.15
"""How much more of the measured stretch they must have it up before it is worth reporting."""


def boss_windows(pulls: Sequence[Pull]) -> tuple[tuple[int, int], ...]:
    """The millisecond spans of the boss pulls, for intersecting aura bands against.

    Takes the route rather than a `Run`, so that a parse reference — which
    carries its pulls and no run — reaches the same rule our own side does.

    A boss pull Warcraft Logs lists twice is one span, by the rule the debuff
    figure's `boss_windows_of` reads, so a sum over these spans counts its
    seconds once, as the merge in `auras.uptime_seconds_in` counts the aura's.
    """
    return tuple((pull.start_ms, pull.end_ms) for _, pull in boss_pulls_listed_once(pulls))


UptimeRule = Callable[[Sequence[Pull], Span | None], Callable[[Aura], float]]
"""How long a side's auras count as up, given that side's own route and its fight's clock.

The counterpart of `spells.CastRule`, and one rule for both sides for the same
reason: a fraction is only comparable when the two numerators were measured the
same way. The clock is the fight's own start and end, None where a side has none
to give; a rule that does not read it ignores it.
"""


def seconds_up_in(windows: tuple[tuple[int, int], ...]) -> Callable[[Aura], float]:
    """Seconds an aura was up inside these windows, as a rule one side can be read by."""
    return lambda aura: uptime_seconds_in(aura, windows)


def fight_seconds(fight_ms: Span | None) -> float:
    """Seconds of a fight's own clock, zero for a side that carries none."""
    return 0.0 if fight_ms is None else (fight_ms[1] - fight_ms[0]) / 1000


def key_clock_uptime(pulls: Sequence[Pull], fight_ms: Span | None) -> Callable[[Aura], float]:
    """The Mythic+ rule: uptime over the whole key clock, from the fight's start to its end.

    The walking between pulls is inside it, so a buff only up in combat reads
    lower the more of the key was spent between pulls, on either side. `pulls`
    is accepted and ignored. A side with no clock measures nothing, and its
    seconds read zero, which the comparison states as unavailable.
    """
    return seconds_up_in(() if fight_ms is None else (fight_ms,))


def without_boss_pulls(fight_ms: Span, pulls: Sequence[Pull]) -> tuple[Span, ...]:
    """The key clock less its boss pulls: the trash pulls and the walking between them."""
    windows: list[Span] = []
    cursor = fight_ms[0]
    for start, end in sorted(boss_windows(pulls)):
        if start > cursor:
            windows.append((cursor, min(start, fight_ms[1])))
        cursor = max(cursor, end)
    if cursor < fight_ms[1]:
        windows.append((cursor, fight_ms[1]))
    return tuple((start, end) for start, end in windows if end > start)


def seconds_up_over_the_fight(aura: Aura) -> float:
    """Seconds an aura was up over a stream already scoped to one fight -- the raid rule.

    Clipped to the aura's own extent, which clips nothing: what it does is
    reuse `uptime_seconds_in`'s merge, so two bands that overlap contribute
    once here exactly as they do on the Mythic+ side. Read off the bands rather
    than off `total_uptime_ms` because the bands are what the other rule reads,
    and one aura measured two ways is how a fraction and its own evidence come
    to disagree.

    Nothing bounds this against the denominator it will be divided by. What
    stands in for a bound is that the aura table returns bands already clipped
    to the fight it was queried for: measured 2026-09-14 over every cached
    response that joins to its own fight -- 22 tables, 49,514 bands, none
    outside -- every one of them a Mythic+ fight; and again 2026-09-15 over
    five raid tables, 2326 bands, where each table's earliest band start and
    latest band end equal its fight's own start and end exactly. Recorded in
    `.claude/skills/wcl-api/SKILL.md` under "In every table measured", and
    re-checked on every live run by `tests/e2e/test_raid_e2e.py`.
    """
    if not aura.bands:
        return 0.0
    span = (
        min(band.start_ms for band in aura.bands),
        max(band.end_ms for band in aura.bands),
    )
    return uptime_seconds_in(aura, (span,))


def whole_fight_uptime(
    pulls: Sequence[Pull], fight_ms: Span | None
) -> Callable[[Aura], float]:
    """The raid rule, which has no route to bind to.

    `pulls` and `fight_ms` are accepted and ignored, exactly as `spells.whole_fight_casts`
    ignores it, and for the same reason: a raid fight carries no pulls, and the
    Mythic+ rule over an empty route would clip every band to nothing and
    report every aura as never present.
    """
    return seconds_up_over_the_fight


def boss_seconds_of(member: ParseMember) -> float:
    """A reference's boss seconds: its denominator under every rule but the key clock."""
    return member.boss_seconds


def fight_seconds_of(member: ParseMember) -> float:
    """A reference's key clock in seconds: its denominator under the key clock rule."""
    return fight_seconds(member.fight_ms)


def fractions_of(
    auras: tuple[Aura, ...], measured: Callable[[Aura], float], seconds: float
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, fraction of `seconds` this aura was up), by one rule."""
    return {aura.ability_id: (aura.name, measured(aura) / seconds) for aura in auras}


def aura_fractions(
    auras: tuple[Aura, ...], windows: tuple[tuple[int, int], ...], seconds: float
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, fraction of the measured stretch this aura was up)."""
    return fractions_of(auras, seconds_up_in(windows), seconds)


def _unavailable(
    our_name: str,
    our_seconds: float,
    their_seconds: float,
    our_has_auras: bool,
    their_has_auras: bool,
    words: Wording,
) -> Finding:
    return Finding(
        id="compare.uptime.unavailable",
        title=f"Buff uptime could not be compared for {our_name}",
        detail=(
            f"An uptime comparison needs {words.both_sides} on both sides and aura data for "
            "both players. One of those is missing, so no uptime numbers are reported rather "
            "than numbers from an unlike sample."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"our {words.stretch_time} {our_seconds:.0f}s",
            f"their {words.stretch_time} {their_seconds:.0f}s",
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


def pairwise_gaps(
    ours: dict[int, tuple[str, float]], theirs: dict[int, tuple[str, float]]
) -> list[tuple[float, int, str, float, float]]:
    """Where one reference had an aura up markedly more than ours did, widest gap first.

    Each row is (gap, ability id, name, our fraction, their fraction). An aura
    is a candidate when the reference carried it for at least
    `MIN_UPTIME_FRACTION`, ours is above zero, and the reference leads by at
    least `UPTIME_GAP_FRACTION`. A zero on our side is passed over rather than
    reported: below the aggregate floor there is no sample to say the aura is
    one this player is meant to carry, so why that is trustworthy to skip is
    each caller's to state.
    """
    gaps = []
    for ability_id, (name, their_fraction) in theirs.items():
        if their_fraction < MIN_UPTIME_FRACTION:
            continue
        our_fraction = ours.get(ability_id, (name, 0.0))[1]
        if our_fraction <= 0.0:
            continue
        if their_fraction - our_fraction < UPTIME_GAP_FRACTION:
            continue
        gaps.append((their_fraction - our_fraction, ability_id, name, our_fraction,
                     their_fraction))
    gaps.sort(reverse=True)
    return gaps


def carried_fractions(
    fractions: dict[int, tuple[str, float]], names: dict[int, str]
) -> dict[int, float]:
    """The fractions above zero, by ability id, recording each name in `names`.

    A fraction only counts as carried when it is above zero: a band that never
    overlaps the measured stretch reads the same as never having the aura at
    all. `names` is shared across a sample's members and keeps the first
    spelling seen for each ability.
    """
    carried: dict[int, float] = {}
    for ability_id, (name, fraction) in fractions.items():
        if fraction <= 0.0:
            continue
        names.setdefault(ability_id, name)
        carried[ability_id] = fraction
    return carried


def _gap_findings(
    ours: dict[int, tuple[str, float]],
    theirs: dict[int, tuple[str, float]],
    our_name: str,
    their_name: str,
    our_seconds: float,
    their_seconds: float,
    words: Wording,
) -> list[Finding]:
    # `pairwise_gaps` passes over an aura at zero on our side. `onSelf` carries
    # no source filter, so it returns teammate-cast buffs, consumables, and gear
    # procs alongside what this player actually carries. Attributing a 0% on
    # our side to this player is only trustworthy for an ability they carried
    # at all; the case of a spell they never cast is already covered by
    # compare_spells's missing-spell branch, against the caster who actually
    # owns it.
    gaps = pairwise_gaps(ours, theirs)

    findings = []
    for rank, (_, ability_id, name, our_fraction, their_fraction) in enumerate(
        gaps[:MAX_AURAS_REPORTED]
    ):
        findings.append(
            Finding(
                id=f"compare.uptime.self.{rank}",
                # Presence, never agency. A proc is not something a player
                # keeps up, and this family cannot tell a proc from a button:
                # the aura table reports that a buff was present, not who or
                # what put it there. So the aura is the subject and the two
                # players are only whose stretch it is measured over -- the
                # key clock in a dungeon, the fight itself in a raid, which is
                # what `words.stretch_time` spells out below.
                title=(
                    f"{name} was up for {their_fraction:.0%} of {their_name}'s "
                    f"{words.stretch_time}, {our_fraction:.0%} of {our_name}'s"
                ),
                detail=(
                    f"Both figures are the share of {words.rate_basis} the aura was present, "
                    "which is comparable even though the two fights ran for different "
                    f"lengths. {words.uptime_hedge} This compares by exact ability, though, "
                    "so a gap can also mean a different item of the same kind, or gear this "
                    "player does not own — not that nothing was used at all."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_seconds:.0f}s of {words.over}",
                    f"theirs over {their_seconds:.0f}s of {words.over}",
                ),
                facts=(
                    FindingFact(label="Ours",
                                value=f"{our_fraction:.0%} of {words.stretch_time}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference",
                                value=f"{their_fraction:.0%} of {words.stretch_time}",
                                confidence=Confidence.DERIVED),
                    # No median and no range in this shape: one reference, and
                    # a label claiming otherwise would claim a sample. The noun
                    # comes from `Wording` for the reason its twin in
                    # `spells.py` gives -- a raid kill is not a run, and this
                    # pair serves both.
                    FindingFact(label="Sample", value=f"1 reference {words.reference_noun}"),
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    return findings


def compare_uptime(
    our_pulls: Sequence[Pull],
    our_seconds: float,
    our_auras: PlayerAuras | None,
    our_name: str,
    theirs: ParseMember,
    *,
    measured: UptimeRule,
    words: Wording,
    our_fight_ms: Span | None = None,
    over: Callable[[ParseMember], float] = boss_seconds_of,
) -> list[Finding]:
    """Where an aura was up markedly more of the reference's measured stretch than of ours.

    `our_name` is the roster's disambiguated spelling of the player being
    compared — never `Player.name`, which two roster members can share, and
    which would then title two players' findings identically.

    The reference side is the member itself rather than a run and a pair of
    loose values: it already carries its own seconds, its own auras and its own
    route, and passing those three separately is how one player's figure ends
    up under another player's name. Its name is read off it for the same
    reason, rather than taken as an argument beside it: two channels for one
    identity is the hazard the sentence above names, and the only way they can
    disagree is to be two.

    Our own side arrives as the two values this reads — a route and the seconds
    that route was worth — rather than as a run, so that a raid fight, which has
    no run to give, reaches the same comparison through `whole_fight_uptime`.

    `our_fight_ms` is our fight's own clock and `over` reads a reference's
    denominator, for a rule that reads the clock. Their defaults read boss
    seconds, as the raid and every rule before the key clock did.
    """
    their_auras = theirs.auras
    their_seconds = over(theirs)

    if our_auras is None or their_auras is None or our_seconds <= 0 or their_seconds <= 0:
        return [
            _unavailable(
                our_name,
                our_seconds,
                their_seconds,
                our_auras is not None,
                their_auras is not None,
                words,
            )
        ]

    # Named at the call site: the four arguments below are two pairs of
    # same-typed values, and a swap inside either pair would put one player's
    # figure under the other's name without failing a type check.
    return _gap_findings(
        fractions_of(our_auras.on_self, measured(our_pulls, our_fight_ms), our_seconds),
        fractions_of(their_auras.on_self, measured(theirs.pulls, theirs.fight_ms), their_seconds),
        our_name=our_name,
        their_name=theirs.character_name,
        our_seconds=our_seconds,
        their_seconds=their_seconds,
        words=words,
    )


def compare_uptime_sample(
    our_pulls: Sequence[Pull],
    our_seconds: float,
    our_auras: PlayerAuras | None,
    our_name: str,
    sample: ParseSample,
    *,
    measured: UptimeRule,
    words: Wording,
    our_fight_ms: Span | None = None,
    over: Callable[[ParseMember], float] = boss_seconds_of,
) -> list[Finding]:
    """Where an aura was up over markedly more of the sample's measured stretches than of ours.

    `our_name` is the roster's disambiguated spelling, for the reason
    `compare_uptime` above gives, and our own side arrives as values rather
    than a run for the reason it gives too.

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
    # `service.compare()` already says so once, as `compare.parse.unavailable`,
    # and `compare_parse_axis` says it once on the raid axis, so returning
    # nothing here avoids repeating that finding for a comparison that never
    # ran. This is distinct from every member lacking aura data, which the
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

    if our_auras is None or our_seconds <= 0 or not aggregable:
        # Below the floor, or our own side has nothing to compute a fraction from
        # either way: one reference is all that can honestly be reported, and
        # `compare_uptime`'s own availability check already decides whether that
        # comes back as a real gap or as `compare.uptime.unavailable`. `too_few`
        # is only wrapped on when the sample itself was the reason — wrapping it
        # around a failure caused by our own missing data would blame the sample
        # for a gap that was never the sample's fault.
        first = eligible[0] if eligible else sample.members[0]
        fallback = compare_uptime(
            our_pulls, our_seconds, our_auras, our_name, first,
            measured=measured, words=words, our_fight_ms=our_fight_ms, over=over,
        )
        return fallback if aggregable else too_few(fallback, len(eligible))

    total = len(sample.members)
    missing_aura_data = total - len(eligible)

    our_fractions = fractions_of(our_auras.on_self, measured(our_pulls, our_fight_ms), our_seconds)
    return _gap_findings_sample(
        our_fractions, eligible, our_name, our_seconds, missing_aura_data, total,
        measured=measured, words=words, over=over,
    )


def uptime_measures(
    our_fractions: dict[int, tuple[str, float]],
    per_member: Sequence[dict[int, float]],
    names: dict[int, str],
    *,
    kept: Collection[int] = (),
) -> tuple[AuraUptime, ...]:
    """Every aura the sample carried often enough to judge, with its verdict.

    The one place an uptime fraction is compared. An aura below
    `MIN_SAMPLE_FOR_AGGREGATE` carriers or below `MIN_UPTIME_FRACTION` is
    absent entirely rather than carrying a verdict: neither was compared, and
    a table that showed them would claim a judgement nobody made.

    `kept` names abilities another stretch's own admission already vouched for.
    One of them that falls under `MIN_UPTIME_FRACTION` here is returned after
    the judged ones with `Verdict.BOSSES_ONLY` instead of being dropped: its
    figures are stated and none of them is compared. It still needs
    `MIN_SAMPLE_FOR_AGGREGATE` carriers here, which a stretch it is a part of
    has already shown.
    """
    judged: list[AuraUptime] = []
    set_aside: list[AuraUptime] = []
    for ability_id, name in names.items():
        carried = [q[ability_id] for q in per_member if ability_id in q]
        if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
            # A one-off proc or a teammate's buff bleeding through `onSelf`'s
            # missing source filter cannot reach this many parses; requiring
            # it here is what retires the old hedge about a single player's
            # gear.
            continue
        their_median = median(carried)
        our_fraction = our_fractions.get(ability_id, (name, 0.0))[1]
        if their_median < MIN_UPTIME_FRACTION:
            if ability_id in kept:
                set_aside.append(
                    AuraUptime(
                        ability_id=ability_id,
                        name=name,
                        ours=our_fraction,
                        their_median=their_median,
                        their_fractions=tuple(carried),
                        verdict=Verdict.BOSSES_ONLY,
                    )
                )
            continue
        if our_fraction <= 0.0:
            verdict = Verdict.UNJUDGED
        elif their_median - our_fraction >= UPTIME_GAP_FRACTION:
            verdict = Verdict.BELOW
        else:
            verdict = Verdict.LEVEL
        judged.append(
            AuraUptime(
                ability_id=ability_id,
                name=name,
                ours=our_fraction,
                their_median=their_median,
                their_fractions=tuple(carried),
                verdict=verdict,
            )
        )
    return (*judged, *set_aside)


def measured_or(value: float | None, reason: Withheld) -> float | Withheld:
    """Our own figure over a stretch, or why our side measured nothing over it."""
    return reason if value is None else value


def carried_shares(theirs: Sequence[float | None]) -> tuple[float, ...]:
    """The references' shares over one stretch that carried it there: measured, above zero.

    These give a stretch cell's median, and the reach table states their range
    and count beside Overall reach.
    """
    return tuple(share for share in theirs if share is not None and share > 0.0)


def stretch_cell(ours: float | Withheld, theirs: Sequence[float | None]) -> StretchCell:
    """One stretch's cell: ours against the median of the references that carried it there.

    Descriptive only: the verdict is the row's. `ours` is a reason when our own
    side measured nothing over the stretch. A reference that measured nothing
    there (None) is not counted for it, and a reference at zero there did not
    carry it; the rest give the median, at the floor the row's own median keeps.
    """
    if isinstance(ours, Withheld):
        return StretchCell(withheld=ours)
    if all(share is None for share in theirs):
        return StretchCell(ours=ours, withheld=Withheld.NOT_REACHED)
    carried = carried_shares(theirs)
    if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
        return StretchCell(ours=ours, withheld=Withheld.TOO_FEW)
    return StretchCell(ours=ours, their_median=median(carried))


def _gap_findings_sample(
    our_fractions: dict[int, tuple[str, float]],
    eligible: Sequence[ParseMember],
    our_name: str,
    our_seconds: float,
    missing_aura_data: int,
    total: int,
    *,
    measured: UptimeRule,
    words: Wording,
    over: Callable[[ParseMember], float],
) -> list[Finding]:
    """Auras up over markedly more of the sample's measured stretches than of ours, by median.

    A member's fraction for an ability only counts as "carried" when it is above zero: a
    band that never overlaps the stretch its rule measures reads the same as never having the
    aura at all, the same reading `aura_fractions` already gives the pairwise comparison.
    """
    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in eligible:
        assert member.auras is not None  # aura_eligible guarantees a PlayerAuras
        their_seconds = over(member)
        fractions = (
            fractions_of(
                member.auras.on_self, measured(member.pulls, member.fight_ms), their_seconds
            )
            if their_seconds > 0
            else {}
        )
        per_member.append(carried_fractions(fractions, names))

    measures = uptime_measures(our_fractions, per_member, names)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )
    # Named rather than dropped: an unjudged aura is one the sample plainly
    # carried, and dropping it silently would read like having nothing to
    # say about it.
    unjudged = [m.name for m in measures if m.verdict is Verdict.UNJUDGED]

    findings = []
    for rank, m in enumerate(gaps[:MAX_AURAS_REPORTED]):
        low, high = observed_range(m.their_fractions)
        findings.append(
            Finding(
                id=f"compare.uptime.self.{rank}",
                # Presence, never agency — see the pairwise branch above.
                title=(
                    f"{m.name} was up a median {m.their_median:.0%} of {words.stretch_time} "
                    f"across {len(m.their_fractions)} top parses; {m.ours:.0%} for {our_name}"
                ),
                detail=(
                    f"Both figures are the share of {words.rate_basis} the aura was present, "
                    "which is comparable even though the fights ran for different lengths. "
                    f"{words.uptime_hedge} This compares by exact ability, so a gap can still "
                    "mean a different item of the same kind — but the gap is stated over "
                    "several top parses, not one player's build, so a single trinket this "
                    "player happens not to own no longer explains it away."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our_seconds:.0f}s of {words.over}",
                    f"range {low:.0%} to {high:.0%} across {len(m.their_fractions)} top parses",
                    f"{count_phrase(missing_aura_data, total)} references had no aura data",
                ),
                # The same figures the title and the evidence already state.
                # Each share is a division this module did, so each says
                # derived: an unset tier is what a panel draws measured with.
                # The parse count is a count, and is not.
                facts=(
                    FindingFact(label="Ours", value=f"{m.ours:.0%} of {words.stretch_time}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{m.their_median:.0%} of {words.stretch_time}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.0%} to {high:.0%}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Sample", value=f"{len(m.their_fractions)} top parses"),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )
    if unjudged:
        findings.append(_unjudged_finding(our_name, unjudged, words))
    return findings


def _unjudged_finding(our_name: str, names: Sequence[str], words: Wording) -> Finding:
    """Auras the sample carried that our own side of the comparison shows none of.

    Deliberately not a gap row. `onSelf` has no source filter, so it returns
    teammate-cast buffs, consumables and gear procs alongside the player's own,
    and a zero cannot be told apart from a buff nobody gave them — reporting it
    as a shortfall would blame a player for a button that is not theirs. What
    this row adds is that the aura is named instead of disappearing, so silence
    on the page stops meaning both "nothing to say" and "set aside".
    """
    ordered = sorted(set(names))
    return Finding(
        id="compare.uptime.unjudged",
        title=(
            f"{quantity(len(ordered), 'aura', 'auras')} the sample carried "
            f"{'is' if len(ordered) == 1 else 'are'} not judged for {our_name}"
        ),
        detail=(
            f"Each of these was present over enough of the sample's {words.stretch_time} to "
            "compare, and absent from ours. It is named rather than measured: the aura table "
            "cannot say "
            "whose buff a row was, so a zero here may be a button this player never pressed "
            "or one a teammate never gave them, and the log does not separate the two. Check "
            "whether the build produces it before reading anything into it."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(ordered),
            f"carried by at least {MIN_SAMPLE_FOR_AGGREGATE} top parses each",
            f"absent from {words.absent_from}",
        ),
    )
