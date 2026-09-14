# ABOUTME: Compares one player's casts and talent build against a top parse or a sample.
# ABOUTME: Which casts count is the caller's rule: a dungeon's boss pulls, or a whole raid fight.

from collections.abc import Callable, Sequence

from wowperf.domain.comparison.loadout import item_sourced, loadouts_of
from wowperf.domain.comparison.measures import AbilityRate, Stretch, Verdict
from wowperf.domain.comparison.reference import REPORT_URL
from wowperf.domain.comparison.sample import (
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.comparison.wording import Wording
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import (
    Confidence,
    Finding,
    FindingFact,
    quantifier_for,
    quantity,
)
from wowperf.domain.loadout import Loadout
from wowperf.domain.model import Player, Pull

MAX_SPELLS_REPORTED = 5
MIN_CASTS_TO_COMPARE = 3
"""Below this, the reference's own sample is too small to argue from."""

RATE_GAP_MULTIPLE = 1.5
"""How much more often they must cast something before it is worth reporting."""

MIN_MEMBERS_WITH_ABILITY = 3
"""An ability seen in fewer members than this is one player's build, not a pattern.

The per-run `MIN_CASTS_TO_COMPARE` still applies to each member, so a single
stray cast cannot make a member count towards this threshold either.
"""


def boss_pulls(pulls: Sequence[Pull]) -> tuple[Pull, ...]:
    """The boss pulls of a route.

    Takes the route rather than a `Run`, so that a parse reference — which
    carries its pulls and no run — reaches the same rule our own side does.
    """
    return tuple(pull for pull in pulls if pull.is_boss)


def boss_seconds(pulls: Sequence[Pull]) -> float:
    """Seconds spent on boss pulls — the only stretch where two runs fought the same thing."""
    return sum(pull.duration_seconds for pull in boss_pulls(pulls))


def in_pulls(indices: frozenset[int]) -> Callable[[CastEvent], bool]:
    """Count a cast only inside these pulls -- the Mythic+ rule.

    A `Run` has pulls and a raid `Encounter` does not, so which casts count is
    the caller's to decide rather than this module's to assume.
    """
    return lambda event: event.pull_index in indices


def whole_fight(event: CastEvent) -> bool:
    """Count every cast the stream carries -- the raid rule.

    A raid cast's `pull_index` is always `None`, so no index rule can match one.
    The stream is already scoped to one fight by the query that fetched it,
    which is what makes "everything" the right denominator here and not a
    widening.
    """
    return True


CastRule = Callable[[Sequence[Pull]], Callable[[CastEvent], bool]]
"""Which of a side's casts count, given that side's own route.

One rule, applied to our route and to each reference's, is what keeps both
sides of a rate counted the same way -- the property the whole comparison rests
on. It cannot be a single bound predicate, because a pull index means one pull
in our log and a different pull in theirs.
"""


def boss_pull_casts(pulls: Sequence[Pull]) -> Callable[[CastEvent], bool]:
    """The Mythic+ rule bound to one route: casts inside that route's boss pulls.

    Boss pulls only, because across trash an ability ratio measures the route
    rather than the player.
    """
    return in_pulls(frozenset(pull.index for pull in boss_pulls(pulls)))


def whole_fight_casts(pulls: Sequence[Pull]) -> Callable[[CastEvent], bool]:
    """The raid rule, which has no route to bind to.

    `pulls` is accepted and ignored: a raid fight carries none, and the stream
    is already scoped to the fight by the query that fetched it. Handed the
    Mythic+ rule instead, an empty route yields `in_pulls(frozenset())`, every
    ability counts zero, and nothing raises -- which is the trap this rule
    exists to close.
    """
    return whole_fight


def casts_in(
    casts: tuple[CastEvent, ...], actor_id: int, include: Callable[[CastEvent], bool]
) -> dict[int, tuple[str, int]]:
    """Each ability this actor cast, and how often, over the casts `include` admits.

    The one counting rule in this package. `boss_casts` is this scoped to the
    boss pulls; the trash comparison is this scoped to the packs two routes
    shared. Two callers counting casts two ways is how a page ends up stating
    a rate its own evidence cannot reproduce.
    """
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or not include(event):
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def boss_casts(
    pulls: Sequence[Pull], casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count).

    The casts are the whole stream and the route decides which of them count,
    so nothing else that reads the same stream — the potion count, which is a
    press wherever it happened — is narrowed by this one's rule.
    """
    return casts_in(casts, actor_id, boss_pull_casts(pulls))


def _all_cast_ability_ids(casts: tuple[CastEvent, ...], actor_id: int) -> set[int]:
    """Every ability the player cast anywhere in the run, boss pull or not."""
    return {event.ability_id for event in casts if event.actor_id == actor_id}


def their_actor_id(theirs: ParseMember, their_name: str) -> int | None:
    folded = their_name.casefold()
    for player in theirs.players:
        if player.name.casefold() == folded:
            return player.actor_id
    return None


def _one_row_per_sentence(findings: list[Finding]) -> list[Finding]:
    """One row per distinct title, at most `MAX_SPELLS_REPORTED` of each family.

    Callers build every candidate row with its family id and no rank; this
    collapses, truncates and numbers them. The rank has to be assigned after
    the collapse or the numbering would carry the holes the collapse left, and
    a pointer into a hole lands nowhere.

    **Ability names do not identify abilities, and ability ids do not identify
    buttons.** Measured 2026-09-11 against the cached responses and recorded in
    `.claude/skills/wcl-api/SKILL.md`: 475 of 1755 ability names own more than
    one game id, and 22 of the 73 report-and-actor pairs that cast anything
    cast some name under two ids. Sometimes one press emits both ids, so
    summing their casts would report two presses where the player made one;
    sometimes the two ids are two real abilities. Nothing in the log
    distinguishes the two cases — of 28 such collisions, 18 never coincide in
    time, 5 always do and 5 do only sometimes, Alter Time among the last — so
    neither merging by name nor reporting every id is right.

    What is right is narrower, and needs no such distinction. Each row's own
    rate is already correct, because one press does emit one cast of that id.
    The only defect is a sentence printed twice, so the sentence is what
    collapses, and every id that produced it is kept in the evidence. Where
    two ids of one name genuinely differ, their titles differ and both rows
    survive.
    """
    by_family: dict[str, dict[str, Finding]] = {}
    for finding in findings:
        rows = by_family.setdefault(finding.id, {})
        first = rows.get(finding.title)
        if first is None:
            rows[finding.title] = finding
            continue
        rows[finding.title] = first.model_copy(
            update={
                "evidence": first.evidence
                + tuple(line for line in finding.evidence if line not in first.evidence)
            }
        )
    return [
        row.model_copy(update={"id": f"{family}.{rank}"})
        for family, rows in by_family.items()
        for rank, row in enumerate(list(rows.values())[:MAX_SPELLS_REPORTED])
    ]


def _missing_cast_pairwise(
    their_name: str,
    our_name: str,
    ability_id: int,
    name: str,
    count: int,
    their_boss_seconds: float,
    words: Wording,
    *,
    owned: bool,
) -> Finding:
    """A cast the reference made and we did not, in whichever of two wordings is true."""
    if owned:
        detail = f"{our_name} had it equipped and never used it."
    else:
        detail = (
            f"{name} does not appear anywhere in {words.run} for {our_name}"
            f"{words.nowhere_else}. That is a talent not taken, a button "
            "not pressed, or an item not owned; the log cannot tell which."
        )
    return Finding(
        id="compare.spells.missing",
        title=(
            f"{their_name} cast {name} {count} times {words.on_stretch}; "
            f"{our_name} never cast it"
        ),
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"ability {ability_id}",
            f"{count} casts across {their_boss_seconds:.0f}s of {words.theirs_across}",
            f"zero casts in the whole of {words.our_stretch}",
        ),
        ability_id=ability_id,
        ability_name=name,
    )


def compare_spells(
    our_pulls: Sequence[Pull],
    our_boss_seconds: float,
    our_casts: tuple[CastEvent, ...],
    our_player: Player,
    our_name: str,
    theirs: ParseMember,
    their_name: str,
    *,
    counted: CastRule,
    words: Wording,
) -> list[Finding]:
    """What the reference player cast that we did not, over the counted stretch, and how often.

    `our_name` is the roster's disambiguated spelling of `our_player`, and it
    is what every title below says. `our_player.name` is not: two roster
    members can share it, and a run comparing both would then emit two
    identical titles.

    Our own side arrives as the three values this reads -- a route, the seconds
    that route was worth, and a cast stream -- rather than as a run, so that a
    raid fight, which has no run to give, reaches the same comparison. Its
    route is empty and its seconds are the fight's own, which is why the two
    are separate arguments and not one derived from the other: exactly the
    reason `ParseMember` carries `boss_seconds` beside `pulls`.
    """
    actor_id = their_actor_id(theirs, their_name)
    their_boss_seconds = theirs.boss_seconds

    if actor_id is None or their_boss_seconds <= 0 or our_boss_seconds <= 0:
        return [
            Finding(
                id="compare.spells.unavailable",
                title=f"The spell comparison could not be made for {our_name}",
                detail=(
                    f"A spell comparison needs {words.both_sides} on both sides and the "
                    "reference player present in their own report. One of those is missing, "
                    "so no ability numbers are reported rather than numbers from an unlike "
                    "sample."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our {words.stretch_time} {our_boss_seconds:.0f}s",
                    f"their {words.stretch_time} {their_boss_seconds:.0f}s",
                    f"reference player {their_name!r} "
                    f"{'found' if actor_id is not None else 'not found'}",
                ),
            )
        ]

    theirs_on_bosses = casts_in(theirs.casts, actor_id, counted(theirs.pulls))
    ours_on_bosses = casts_in(our_casts, our_player.actor_id, counted(our_pulls))
    ours_anywhere = _all_cast_ability_ids(our_casts, our_player.actor_id)

    findings: list[Finding] = []

    # 1. Abilities they cast and we never cast at all. A set difference: the
    #    highest-signal comparison the design lists, and the one with no modelling in it.
    never = sorted(
        (
            (ability_id, name, count)
            for ability_id, (name, count) in theirs_on_bosses.items()
            if ability_id not in ours_anywhere
        ),
        key=lambda row: row[2],
        reverse=True,
    )
    # Each of these abilities may resolve to an item the reference wore.
    # `their_loadouts` is a one-element sequence, because the pairwise
    # comparison has exactly one reference to ask. Whether the resolved item is
    # ours to equip is a separate question the loop below answers per
    # candidate: an id resolving to no item name, or our own loadout never
    # having been fetched, both mean the join cannot answer, and neither is
    # evidence of ownership either way.
    their_loadouts = loadouts_of([theirs])
    for ability_id, name, count in never:
        source = item_sourced(name, their_loadouts)
        if source is not None and our_player.loadout is not None:
            if our_player.loadout.has_item(source.item_id):
                findings.append(
                    _missing_cast_pairwise(
                        their_name, our_name, ability_id, name, count,
                        their_boss_seconds, words, owned=True,
                    )
                )
            # Otherwise it is an item we provably lack, and suppressed for the
            # reason the sample branch gives at length.
            continue
        findings.append(
            _missing_cast_pairwise(
                their_name, our_name, ability_id, name, count, their_boss_seconds, words,
                owned=False,
            )
        )

    # 2. Abilities both cast, where their rate over the counted stretch is
    #    materially higher.
    gaps = []
    for ability_id, (name, their_count) in theirs_on_bosses.items():
        if their_count < MIN_CASTS_TO_COMPARE or ability_id not in ours_on_bosses:
            continue
        our_count = ours_on_bosses[ability_id][1]
        their_rate = their_count / their_boss_seconds * 60
        our_rate = our_count / our_boss_seconds * 60
        if our_rate <= 0 or their_rate / our_rate < RATE_GAP_MULTIPLE:
            continue
        gaps.append((their_rate - our_rate, ability_id, name, our_rate, their_rate))
    gaps.sort(reverse=True)

    for _, ability_id, name, our_rate, their_rate in gaps:
        findings.append(
            Finding(
                id="compare.spells.rate",
                title=(
                    f"{their_name} cast {name} {their_rate:.1f} times a minute "
                    f"{words.on_stretch}, {our_name} {our_rate:.1f}"
                ),
                detail=(
                    f"Both rates are casts per minute of {words.rate_basis}, "
                    f"{words.same_stretch_pairwise} {words.rate_hedge}"
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_boss_seconds:.0f}s of {words.over}",
                    f"theirs over {their_boss_seconds:.0f}s of {words.over}",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{our_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference", value=f"{their_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    # Named rather than left implicit: this shape has no median
                    # and no range, and a panel that printed either label here
                    # would claim a sample the comparison never drew.
                    #
                    # The noun is `Wording`'s and not a literal, because this
                    # pair serves a raid fight as well as a dungeon and a raid
                    # kill is not a run. It is a field of its own rather than
                    # `run`, which is the demonstrative ("this run", "this
                    # fight") and would read "1 reference this fight" here.
                    FindingFact(label="Sample", value=f"1 reference {words.reference_noun}"),
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )

    return _one_row_per_sentence(findings)


def compare_spells_sample(
    our_pulls: Sequence[Pull],
    our_boss_seconds: float,
    our_casts: tuple[CastEvent, ...],
    our_player: Player,
    our_name: str,
    sample: ParseSample,
    *,
    counted: CastRule,
    words: Wording,
) -> list[Finding]:
    """What the sample's top parses cast that we did not, and how our own rate compares.

    `our_name` is the roster's disambiguated spelling of `our_player`, for the
    reason `compare_spells` above gives. Our own side arrives as values rather
    than a run, and `counted` decides which casts count on both sides, for the
    reasons that function's docstring gives.

    No member is named: the claim is about the sample as a population — "N of M
    top parses cast this" or "the median rate is this" — and naming one member
    to illustrate a population claim would misrepresent it while needlessly
    persisting a stranger's identity in a file kept forever. The below-floor
    fallback below is the one place a name survives, because there it is
    honestly one reference's pairwise comparison, not a population claim.
    """
    # A wholly empty sample means there was nothing to compare against at all;
    # `service.compare()` already says so once, as `compare.parse.unavailable`,
    # and `compare_parse_axis` says it once on the raid axis, so returning
    # nothing here avoids repeating that finding for a comparison that never ran.
    if not sample.members:
        return []

    if not sample.can_aggregate(sample.members):
        first = sample.members[0]
        return too_few(
            compare_spells(
                our_pulls, our_boss_seconds, our_casts, our_player, our_name,
                first, first.character_name, counted=counted, words=words,
            ),
            len(sample.members),
        )

    total = len(sample.members)
    ours_on_bosses = casts_in(our_casts, our_player.actor_id, counted(our_pulls))
    ours_anywhere = _all_cast_ability_ids(our_casts, our_player.actor_id)

    # Ability id to name, gathered from whichever member cast it first, and one
    # (boss seconds, qualifying casts) pair per member. A member whose own actor
    # cannot be found in their own report, or who fought no boss at all,
    # contributes an empty qualifying set rather than being dropped: dropping it
    # would let `total` drift from the number of members a title actually names.
    # The empty set is also the only thing keeping a zero out of `rate_measures`'
    # denominator, which divides by these seconds unguarded on purpose.
    names: dict[int, str] = {}
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in sample.members:
        actor_id = their_actor_id(member, member.character_name)
        their_boss_seconds = member.boss_seconds
        if actor_id is None or their_boss_seconds <= 0:
            per_member.append((0.0, {}))
            continue
        casts_by_ability = casts_in(member.casts, actor_id, counted(member.pulls))
        for ability_id, (name, _count) in casts_by_ability.items():
            names.setdefault(ability_id, name)
        qualifying = {
            ability_id: count
            for ability_id, (_name, count) in casts_by_ability.items()
            if count >= MIN_CASTS_TO_COMPARE
        }
        per_member.append((their_boss_seconds, qualifying))

    findings = _missing_sample(
        our_name, ours_anywhere, names, per_member, total,
        our_player.loadout, loadouts_of(sample.members), words,
    )
    if our_boss_seconds > 0:
        findings += _rate_sample(our_name, ours_on_bosses, our_boss_seconds, per_member, words)
    return findings


def _missing_sample(
    our_name: str,
    ours_anywhere: set[int],
    names: dict[int, str],
    per_member: Sequence[tuple[float, dict[int, int]]],
    total: int,
    our_loadout: Loadout | None,
    their_loadouts: Sequence[Loadout],
    words: Wording,
) -> list[Finding]:
    """Abilities enough of the sample cast, over the counted stretch, that we never cast anywhere.

    Three branches, because the log supports three explanations and the two the
    detail used to offer made a false dichotomy of it. An ability that resolves
    to an item the player does not own is a gear finding, not a cast finding:
    telling somebody to press a button they do not have is advice they cannot
    take, and it carried a `measured` badge while doing so.

    The third branch is reached whenever the join cannot answer — an ability
    matching no item name, or a player whose loadout was never fetched — and it
    widens the wording rather than claiming anything. That is what keeps the
    speed axis and every already-cached run honest without the new query.
    """
    candidates = []
    for ability_id, name in names.items():
        if ability_id in ours_anywhere:
            continue
        matching = sum(1 for _, qualifying in per_member if ability_id in qualifying)
        if matching < MIN_MEMBERS_WITH_ABILITY:
            continue
        candidates.append((matching, ability_id, name))
    candidates.sort(key=lambda row: (-row[0], row[2]))

    findings = []
    for matching, ability_id, name in candidates:
        source = item_sourced(name, their_loadouts)
        if source is not None and our_loadout is not None:
            if our_loadout.has_item(source.item_id):
                findings.append(_missing_cast(our_name, matching, total, ability_id, name,
                                               words, owned=True))
            # Otherwise the join has answered, and the answer is that the item
            # is not ours to press. Naming it at all -- as a cast we skipped or
            # as a gear gap -- puts an act the player cannot perform in front
            # of them, which is the complaint this whole path began from. Say
            # nothing. How much of the sample's gear was readable does not
            # enter it: our own loadout settles ownership by itself, and a
            # thin sample is no reason to hand back the suggestion.
            continue
        findings.append(
            _missing_cast(our_name, matching, total, ability_id, name, words, owned=False)
        )
    return _one_row_per_sentence(findings)


def _missing_cast(
    our_name: str,
    matching: int,
    total: int,
    ability_id: int,
    name: str,
    words: Wording,
    *,
    owned: bool,
) -> Finding:
    """A cast the sample made and we did not, in whichever of two wordings is true."""
    if owned:
        detail = (
            f"{our_name} had it equipped and never used it. The count is over the "
            "sample, not one parse, so no single reference needs naming to make the point."
        )
    else:
        detail = (
            f"{name} does not appear anywhere in {words.run} for {our_name}"
            f"{words.nowhere_else}. That is a talent not taken, a button not pressed, or an "
            "item not owned; the log cannot tell which. The count is over the sample, not "
            "one parse, so no single reference needs naming to make the point."
        )
    return Finding(
        id="compare.spells.missing",
        title=(
            f"{count_phrase(matching, total)} top parses cast {name} {words.on_stretch}; "
            f"{our_name} never did"
        ),
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"ability {ability_id}",
            f"{matching} of {total} top parses cast it at least "
            f"{MIN_CASTS_TO_COMPARE} times {words.on_stretch}",
            f"zero casts in the whole of {words.our_stretch}",
        ),
        quantifier=quantifier_for(matching, total),
        ability_id=ability_id,
        ability_name=name,
    )




def verdict_for(ours: float, their_median: float) -> Verdict:
    """Which of the three branches a rate falls in, at the one bar both directions use.

    Above has to stand as its own test: drop it, and an ability far enough
    above the median reads as comfortably inside the band from the other
    side, and gets filed as level instead of above. `their_median` is never
    zero here: a member only contributes a rate after clearing
    `MIN_CASTS_TO_COMPARE` over non-zero seconds.
    """
    if ours / their_median >= RATE_GAP_MULTIPLE:
        return Verdict.ABOVE
    if their_median / ours >= RATE_GAP_MULTIPLE:
        return Verdict.BELOW
    return Verdict.LEVEL


def rate_measures(
    ours_on_bosses: dict[int, tuple[str, int]],
    our_boss_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> tuple[AbilityRate, ...]:
    """Every ability compared on boss pulls, with the verdict it earned.

    The one place a boss cast rate is computed. `_rate_sample` turns these into
    findings and `comparison.tables` turns them into table rows; computing them
    twice is how a row and the table beneath it come to state different numbers
    for one player.

    A member's seconds are divided by with no guard of their own, where
    `trash_rate_measures` checks them first. The asymmetry is the contract, not
    an oversight: every caller drops a member who fought no boss on the way in,
    giving it an empty qualifying set, so an ability can never be found against
    seconds of zero. Guarding it here as well would leave those membership lines
    with no observable consequence at all -- and a line indistinguishable from
    its own absence is one the next reader deletes, taking the real protection
    with it. `compare_spells_sample` and `tables._boss` are the two callers that
    hold up this end.
    """
    measures: list[AbilityRate] = []
    for ability_id, (name, our_count) in ours_on_bosses.items():
        rates = [
            qualifying[ability_id] / their_boss_seconds * 60
            for their_boss_seconds, qualifying in per_member
            if ability_id in qualifying
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_boss_seconds * 60
        if our_rate <= 0:
            continue
        their_median = median(rates)
        measures.append(
            AbilityRate(
                ability_id=ability_id,
                name=name,
                ours=our_rate,
                their_median=their_median,
                their_rates=tuple(rates),
                stretch=Stretch.BOSS,
                verdict=verdict_for(our_rate, their_median),
            )
        )
    return tuple(measures)


def _rate_sample(
    our_name: str,
    ours_on_bosses: dict[int, tuple[str, int]],
    our_boss_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
    words: Wording,
) -> list[Finding]:
    """Abilities both sides cast, where the sample's median rate is materially higher."""
    measures = rate_measures(ours_on_bosses, our_boss_seconds, per_member)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )
    above = sorted(
        (m for m in measures if m.verdict is Verdict.ABOVE),
        key=lambda m: m.ours - m.their_median,
        reverse=True,
    )
    # Collected rather than dropped: an ability that was compared and found
    # level is not the same as one that was never compared at all, and a
    # page that dropped this list would read the two alike.
    level = [m.name for m in measures if m.verdict is Verdict.LEVEL]

    findings = [_gap_finding(our_name, m, our_boss_seconds, words) for m in gaps]
    findings += [
        _above_finding(
            our_name, m.ability_id, m.name, m.ours, m.their_median,
            list(m.their_rates), our_boss_seconds, words,
        )
        for m in above
    ]
    rows = _one_row_per_sentence(findings)
    if level:
        rows.append(_level_finding(our_name, level, words))
    return rows


def _gap_finding(
    our_name: str, measure: AbilityRate, our_boss_seconds: float, words: Wording
) -> Finding:
    """An ability the sample's median rate clears by `RATE_GAP_MULTIPLE`."""
    low, high = observed_range(measure.their_rates)
    return Finding(
        id="compare.spells.rate",
        title=(
            f"{len(measure.their_rates)} top parses cast {measure.name} a median "
            f"{measure.their_median:.1f} times a minute {words.on_stretch}; "
            f"{our_name} casts it {measure.ours:.1f}"
        ),
        detail=(
            f"Both rates are casts per minute of {words.rate_basis}, "
            f"{words.same_stretch_sample} The "
            "reference side is the median across the sample, not one parse, so a "
            "single busy or quiet run cannot carry the comparison alone."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"ability {measure.ability_id}",
            f"ours over {our_boss_seconds:.0f}s of {words.over}",
            f"range {low:.1f} to {high:.1f} casts a minute across "
            f"{len(measure.their_rates)} top parses",
        ),
        # The same four numbers the title and the evidence above already
        # state, as labels and values a panel can lay out. Ours, the
        # reference median and the range are divisions this function did, so
        # each says derived: an unset tier is what a panel draws measured
        # with. The parse count is a count, and is not.
        facts=(
            FindingFact(label="Ours", value=f"{measure.ours:.1f} casts a minute",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Reference median",
                        value=f"{measure.their_median:.1f} casts a minute",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Observed range", value=f"{low:.1f} to {high:.1f}",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Sample", value=f"{len(measure.their_rates)} top parses"),
        ),
        ability_id=measure.ability_id,
        ability_name=measure.name,
    )


def _above_finding(
    our_name: str,
    ability_id: int,
    name: str,
    our_rate: float,
    their_median: float,
    rates: Sequence[float],
    our_boss_seconds: float,
    words: Wording,
) -> Finding:
    """An ability we cast far more often than the sample's median.

    The mirror of the gap row, at the same bar, and deliberately not phrased as
    advice. The gap rows ask whether a button went unpressed, which has an
    obvious remedy; this one has none, because casting something more often is
    not a fault on its own. What it is good for is the question underneath it:
    on a class whose resources are shared, a button pressed far more than the
    sample is resources that did not go anywhere else.
    """
    low, high = observed_range(rates)
    return Finding(
        id="compare.spells.above",
        title=(
            f"{our_name} casts {name} {our_rate:.1f} times a minute {words.on_stretch}; "
            f"{len(rates)} top parses cast it a median {their_median:.1f}"
        ),
        detail=(
            f"Both rates are casts per minute of {words.rate_basis}. This row states a "
            "difference and no verdict: casting something more often than the sample is not "
            "a fault, and on a class whose resources are shared it means those resources did "
            f"not go somewhere else, which is the thing worth checking. {words.above_hedge}"
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"ability {ability_id}",
            f"ours over {our_boss_seconds:.0f}s of {words.over}",
            f"range {low:.1f} to {high:.1f} casts a minute across {len(rates)} top parses",
        ),
        facts=(
            FindingFact(
                label="Ours", value=f"{our_rate:.1f} casts a minute",
                confidence=Confidence.DERIVED,
            ),
            FindingFact(
                label="Reference median", value=f"{their_median:.1f} casts a minute",
                confidence=Confidence.DERIVED,
            ),
            FindingFact(
                label="Observed range", value=f"{low:.1f} to {high:.1f}",
                confidence=Confidence.DERIVED,
            ),
            FindingFact(label="Sample", value=f"{len(rates)} top parses"),
        ),
        ability_id=ability_id,
        ability_name=name,
    )


def _level_finding(our_name: str, names: Sequence[str], words: Wording) -> Finding:
    """The abilities compared over the stretch both sides fought that produced no gap row.

    Kept out of `_one_row_per_sentence`: that collapses and ranks a family of
    competing rows, and this is one sentence about a set, not a row that could
    have rivals.
    """
    ordered = sorted(set(names))
    return Finding(
        id="compare.spells.level",
        title=(
            f"{quantity(len(ordered), 'ability', 'abilities')} {our_name} cast "
            f"{words.on_stretch} "
            f"{'was' if len(ordered) == 1 else 'were'} compared and showed no gap"
        ),
        detail=(
            "Enough of the sample cast each of these to argue from, and our own rate was "
            "inside the band the rate rows use, in either direction: the sample's median has "
            f"to be {RATE_GAP_MULTIPLE} times ours, or ours {RATE_GAP_MULTIPLE} times theirs, "
            "before a row is written. That band is what this row states, so read it as 'no gap "
            "wide enough to report', never as 'the same rate' — a rate inside the band is "
            "reported nowhere else on this page."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(ordered),
            f"compared against at least {MIN_MEMBERS_WITH_ABILITY} top parses each",
        ),
    )


def compare_talents(
    our_player: Player, our_name: str, their_player: Player | None, theirs: ParseMember
) -> list[Finding]:
    """Whether the two builds differ, and the string needed to import theirs.

    The one row still drawn from a single reference: a build has no mean and no
    mode this project can compute. It names the top-ranked parse rather than
    the player who ran it, and links to that report, because a reader asked to
    copy a stranger's build is the one reader who must be able to trace it.

    Exactly one of the three findings below is emitted per player, so all three
    titles name whose build they are about: a run comparing the whole group
    would otherwise state the same sentence once per member with nothing in it
    to tell them apart. `our_name` is the roster's disambiguated spelling, for
    the reason `compare_spells` above gives.
    """
    our_build = our_player.talent_import_string
    their_build = their_player.talent_import_string if their_player else None
    source = REPORT_URL.format(code=theirs.report_code, fight=theirs.fight_id)

    if our_build is None or their_build is None:
        return [
            Finding(
                id="compare.talents",
                title=f"The talent builds could not be compared for {our_name}",
                detail=(
                    "One of the two reports does not carry a talent import string for its "
                    "player, so the builds are not compared. An absent string is not evidence "
                    "that the builds match."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ours {'present' if our_build else 'absent'}",
                    f"theirs {'present' if their_build else 'absent'}",
                    f"top-ranked parse: {source}",
                ),
            )
        ]

    if our_build == their_build:
        return [
            Finding(
                id="compare.talents",
                title=f"{our_name}'s talent build matches the top-ranked parse",
                detail=(
                    "Both players imported the same build, so nothing here needs changing. "
                    "This is one player's build, not the sample's: a talent string has no "
                    "median, so the row names the top-ranked parse alone."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=("identical import strings", f"top-ranked parse: {source}"),
            )
        ]

    return [
        Finding(
            id="compare.talents",
            title=f"{our_name}'s talent build differs from the top-ranked parse",
            detail=(
                "The import codes differ. They are opaque, so the difference is not spelled out "
                "here — paste the other string into the game to see it laid out on the tree. "
                "This is one player's build, not the sample's: a talent string has no median, "
                "so the row names the top-ranked parse alone, and a different build is not "
                "automatically a worse one."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"theirs: {their_build}",
                f"ours: {our_build}",
                f"top-ranked parse: {source}",
            ),
        )
    ]
