# ABOUTME: Compares one player's boss-pull casts and talent build against a top parse or sample.
# ABOUTME: Boss pulls only: across trash an ability ratio measures the route, not the player.

from collections.abc import Sequence

from wowperf.domain.comparison.reference import REPORT_URL, ParseRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample, too_few
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import (
    Confidence,
    Finding,
    FindingFact,
    quantifier_for,
    quantity,
)
from wowperf.domain.model import LoadedRun, Player, Run

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


def boss_seconds(run: Run) -> float:
    """Seconds spent on boss pulls — the only stretch where two runs fought the same thing."""
    return sum(pull.duration_seconds for pull in run.boss_pulls)


def casts_in(
    casts: tuple[CastEvent, ...], actor_id: int, indices: frozenset[int]
) -> dict[int, tuple[str, int]]:
    """One player's casts inside `indices`, as ability id to (name, count).

    The one counting rule in this package. `boss_casts` is this scoped to the
    boss pulls; the trash comparison is this scoped to the packs two routes
    shared. Two callers counting casts two ways is how a page ends up stating
    a rate its own evidence cannot reproduce.
    """
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or event.pull_index not in indices:
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count)."""
    return casts_in(casts, actor_id, frozenset(pull.index for pull in run.boss_pulls))


def _all_cast_ability_ids(casts: tuple[CastEvent, ...], actor_id: int) -> set[int]:
    """Every ability the player cast anywhere in the run, boss pull or not."""
    return {event.ability_id for event in casts if event.actor_id == actor_id}


def their_actor_id(theirs: ParseMember, their_name: str) -> int | None:
    folded = their_name.casefold()
    for player in theirs.run.players:
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


def compare_spells(
    ours: LoadedRun,
    our_player: Player,
    our_name: str,
    theirs: ParseMember,
    their_name: str,
) -> list[Finding]:
    """What the reference player cast on bosses that we did not, and how often.

    `our_name` is the roster's disambiguated spelling of `our_player`, and it
    is what every title below says. `our_player.name` is not: two roster
    members can share it, and a run comparing both would then emit two
    identical titles.
    """
    actor_id = their_actor_id(theirs, their_name)
    their_boss_seconds = boss_seconds(theirs.run)
    our_boss_seconds = boss_seconds(ours.run)

    if actor_id is None or their_boss_seconds <= 0 or our_boss_seconds <= 0:
        return [
            Finding(
                id="compare.spells.unavailable",
                title=f"The spell comparison could not be made for {our_name}",
                detail=(
                    "A spell comparison needs boss pulls on both sides and the reference "
                    "player present in their own report. One of those is missing, so no "
                    "ability numbers are reported rather than numbers from an unlike sample."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our boss time {our_boss_seconds:.0f}s",
                    f"their boss time {their_boss_seconds:.0f}s",
                    f"reference player {their_name!r} "
                    f"{'found' if actor_id is not None else 'not found'}",
                ),
            )
        ]

    theirs_on_bosses = boss_casts(theirs.run, theirs.casts, actor_id)
    ours_on_bosses = boss_casts(ours.run, ours.casts, our_player.actor_id)
    ours_anywhere = _all_cast_ability_ids(ours.casts, our_player.actor_id)

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
    for ability_id, name, count in never:
        findings.append(
            Finding(
                id="compare.spells.missing",
                title=(
                    f"{their_name} cast {name} {count} times on bosses; "
                    f"{our_name} never cast it"
                ),
                detail=(
                    f"{name} does not appear anywhere in this run for {our_name} — not "
                    "on bosses and not on trash. That is either a talent not taken or a button "
                    "not pressed; the log cannot tell which."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"{count} casts across {their_boss_seconds:.0f}s of their boss pulls",
                    "zero casts in the whole of our run",
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )

    # 2. Abilities both cast, where their rate on bosses is materially higher.
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
                    f"{their_name} cast {name} {their_rate:.1f} times a minute on bosses, "
                    f"{our_name} {our_rate:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of boss-pull time, which is the one stretch "
                    "of a dungeon where two runs fought the same encounter. A longer fight at a "
                    "higher key changes how many cooldowns fit, so treat a small gap as noise."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_boss_seconds:.0f}s of boss pulls",
                    f"theirs over {their_boss_seconds:.0f}s of boss pulls",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{our_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference", value=f"{their_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    # Named rather than left implicit: this shape has no median
                    # and no range, and a panel that printed either label here
                    # would claim a sample the comparison never drew.
                    FindingFact(label="Sample", value="1 reference run"),
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )

    return _one_row_per_sentence(findings)


def compare_spells_sample(
    ours: LoadedRun, our_player: Player, our_name: str, sample: ParseSample
) -> list[Finding]:
    """What the sample's top parses cast that we did not, and how our own rate compares.

    `our_name` is the roster's disambiguated spelling of `our_player`, for the
    reason `compare_spells` above gives.

    No member is named: the claim is about the sample as a population — "N of M
    top parses cast this" or "the median rate is this" — and naming one member
    to illustrate a population claim would misrepresent it while needlessly
    persisting a stranger's identity in a file kept forever. The below-floor
    fallback below is the one place a name survives, because there it is
    honestly one reference's pairwise comparison, not a population claim.
    """
    # A wholly empty sample means there was nothing to compare against at all;
    # `service.compare()` already says so once, as `compare.parse.unavailable`,
    # so returning nothing here avoids repeating that finding for a comparison
    # that never ran.
    if not sample.members:
        return []

    if not sample.can_aggregate(sample.members):
        first = sample.members[0]
        return too_few(
            compare_spells(ours, our_player, our_name, first, first.row.character_name),
            len(sample.members),
        )

    total = len(sample.members)
    our_boss_seconds = boss_seconds(ours.run)
    ours_on_bosses = boss_casts(ours.run, ours.casts, our_player.actor_id)
    ours_anywhere = _all_cast_ability_ids(ours.casts, our_player.actor_id)

    # Ability id to name, gathered from whichever member cast it first, and one
    # (boss seconds, qualifying casts) pair per member. A member whose own actor
    # cannot be found in their own report, or who fought no boss at all,
    # contributes an empty qualifying set rather than being dropped: dropping it
    # would let `total` drift from the number of members a title actually names.
    names: dict[int, str] = {}
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in sample.members:
        actor_id = their_actor_id(member, member.row.character_name)
        their_boss_seconds = boss_seconds(member.run)
        if actor_id is None or their_boss_seconds <= 0:
            per_member.append((0.0, {}))
            continue
        casts_by_ability = boss_casts(member.run, member.casts, actor_id)
        for ability_id, (name, _count) in casts_by_ability.items():
            names.setdefault(ability_id, name)
        qualifying = {
            ability_id: count
            for ability_id, (_name, count) in casts_by_ability.items()
            if count >= MIN_CASTS_TO_COMPARE
        }
        per_member.append((their_boss_seconds, qualifying))

    findings = _missing_sample(our_name, ours_anywhere, names, per_member, total)
    if our_boss_seconds > 0:
        findings += _rate_sample(our_name, ours_on_bosses, our_boss_seconds, per_member)
    return findings


def _missing_sample(
    our_name: str,
    ours_anywhere: set[int],
    names: dict[int, str],
    per_member: Sequence[tuple[float, dict[int, int]]],
    total: int,
) -> list[Finding]:
    """Abilities enough of the sample cast on bosses that we never cast anywhere."""
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
        findings.append(
            Finding(
                id="compare.spells.missing",
                title=(
                    f"{count_phrase(matching, total)} top parses cast {name} on bosses; "
                    f"{our_name} never did"
                ),
                detail=(
                    f"{name} does not appear anywhere in this run for {our_name} — not "
                    "on bosses and not on trash. That is either a talent not taken or a button "
                    "not pressed; the log cannot tell which. The count is over the sample, not "
                    "one parse, so no single reference needs naming to make the point."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"{matching} of {total} top parses cast it at least "
                    f"{MIN_CASTS_TO_COMPARE} times on bosses",
                    "zero casts in the whole of our run",
                ),
                quantifier=quantifier_for(matching, total),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    return _one_row_per_sentence(findings)


def _rate_sample(
    our_name: str,
    ours_on_bosses: dict[int, tuple[str, int]],
    our_boss_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> list[Finding]:
    """Abilities both sides cast, where the sample's median rate is materially higher."""
    gaps = []
    level: list[str] = []
    for ability_id, (name, our_count) in ours_on_bosses.items():
        rates = [
            qualifying[ability_id] / their_boss_seconds * 60
            for their_boss_seconds, qualifying in per_member
            if ability_id in qualifying
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_boss_seconds * 60
        their_median = median(rates)
        if our_rate <= 0:
            continue
        if their_median / our_rate < RATE_GAP_MULTIPLE:
            # Compared against enough of the sample to argue from, and no gap
            # wide enough to report. Collected rather than dropped: silence on
            # the page read the same as never having been compared at all.
            level.append(name)
            continue
        gaps.append((their_median - our_rate, ability_id, name, our_rate, their_median, rates))
    gaps.sort(key=lambda row: row[0], reverse=True)

    findings = []
    for _, ability_id, name, our_rate, their_median, rates in gaps:
        low, high = observed_range(rates)
        findings.append(
            Finding(
                id="compare.spells.rate",
                title=(
                    f"{len(rates)} top parses cast {name} a median {their_median:.1f} times a "
                    f"minute on bosses; {our_name} casts it {our_rate:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of boss-pull time, which is the one "
                    "stretch of a dungeon where every run fought the same encounter. The "
                    "reference side is the median across the sample, not one parse, so a "
                    "single busy or quiet run cannot carry the comparison alone."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_boss_seconds:.0f}s of boss pulls",
                    f"range {low:.1f} to {high:.1f} casts a minute across "
                    f"{len(rates)} top parses",
                ),
                # The same four numbers the title and the evidence above
                # already state, as labels and values a panel can lay out.
                # Both rates and the range are divisions this module did, so
                # each says derived: an unset tier is what a panel draws
                # measured with. The parse count is a count, and is not.
                facts=(
                    FindingFact(label="Ours", value=f"{our_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{their_median:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.1f} to {high:.1f}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Sample", value=f"{len(rates)} top parses"),
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    rows = _one_row_per_sentence(findings)
    if level:
        rows.append(_level_finding(our_name, level))
    return rows


def _level_finding(our_name: str, names: Sequence[str]) -> Finding:
    """The abilities compared on bosses that produced no gap row.

    Kept out of `_one_row_per_sentence`: that collapses and ranks a family of
    competing rows, and this is one sentence about a set, not a row that could
    have rivals.
    """
    ordered = sorted(set(names))
    return Finding(
        id="compare.spells.level",
        title=(
            f"{quantity(len(ordered), 'ability', 'abilities')} {our_name} cast on bosses "
            f"{'was' if len(ordered) == 1 else 'were'} compared and showed no gap"
        ),
        detail=(
            "Enough of the sample cast each of these to argue from, and our own rate was "
            f"inside the bar the gap rows use: the sample's median has to be {RATE_GAP_MULTIPLE} "
            "times ours before one is written. That bar is what this row states, so read it as "
            "'no gap wide enough to report', never as 'the same rate' — a rate below the "
            "sample's median but inside the bar is reported nowhere else on this page."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(ordered),
            f"compared against at least {MIN_MEMBERS_WITH_ABILITY} top parses each",
        ),
    )


def compare_talents(
    our_player: Player, our_name: str, their_player: Player | None, their_row: ParseRow
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
    ours = our_player.talent_import_string
    theirs = their_player.talent_import_string if their_player else None
    source = REPORT_URL.format(code=their_row.report_code, fight=their_row.fight_id)

    if ours is None or theirs is None:
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
                    f"ours {'present' if ours else 'absent'}",
                    f"theirs {'present' if theirs else 'absent'}",
                    f"top-ranked parse: {source}",
                ),
            )
        ]

    if ours == theirs:
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
            evidence=(f"theirs: {theirs}", f"ours: {ours}", f"top-ranked parse: {source}"),
        )
    ]
