# ABOUTME: Compares one player's boss-pull casts and talent build against a top parse or sample.
# ABOUTME: Boss pulls only: across trash an ability ratio measures the route, not the player.

from collections.abc import Sequence

from wowperf.domain.comparison.reference import REPORT_URL, ParseRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample, too_few
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding, quantifier_for
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


def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count)."""
    boss_indices = {pull.index for pull in run.boss_pulls}
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or event.pull_index not in boss_indices:
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def _all_cast_ability_ids(casts: tuple[CastEvent, ...], actor_id: int) -> set[int]:
    """Every ability the player cast anywhere in the run, boss pull or not."""
    return {event.ability_id for event in casts if event.actor_id == actor_id}


def _their_actor_id(theirs: ParseMember, their_name: str) -> int | None:
    folded = their_name.casefold()
    for player in theirs.run.players:
        if player.name.casefold() == folded:
            return player.actor_id
    return None


def compare_spells(
    ours: LoadedRun, our_player: Player, theirs: ParseMember, their_name: str
) -> list[Finding]:
    """What the reference player cast on bosses that we did not, and how often."""
    their_actor_id = _their_actor_id(theirs, their_name)
    their_boss_seconds = boss_seconds(theirs.run)
    our_boss_seconds = boss_seconds(ours.run)

    if their_actor_id is None or their_boss_seconds <= 0 or our_boss_seconds <= 0:
        return [
            Finding(
                id="compare.spells.unavailable",
                title="The spell comparison could not be made",
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
                    f"{'found' if their_actor_id is not None else 'not found'}",
                ),
            )
        ]

    theirs_on_bosses = boss_casts(theirs.run, theirs.casts, their_actor_id)
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
    for rank, (ability_id, name, count) in enumerate(never[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.missing.{rank}",
                title=(
                    f"{their_name} cast {name} {count} times on bosses; "
                    f"{our_player.name} never cast it"
                ),
                detail=(
                    f"{name} does not appear anywhere in this run for {our_player.name} — not "
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

    for rank, (_, ability_id, name, our_rate, their_rate) in enumerate(gaps[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.rate.{rank}",
                title=(
                    f"{their_name} cast {name} {their_rate:.1f} times a minute on bosses, "
                    f"{our_player.name} {our_rate:.1f}"
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
            )
        )

    return findings


def compare_spells_sample(
    ours: LoadedRun, our_player: Player, sample: ParseSample
) -> list[Finding]:
    """What the sample's top parses cast that we did not, and how our own rate compares.

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
            compare_spells(ours, our_player, first, first.row.character_name),
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
        their_actor_id = _their_actor_id(member, member.row.character_name)
        their_boss_seconds = boss_seconds(member.run)
        if their_actor_id is None or their_boss_seconds <= 0:
            per_member.append((0.0, {}))
            continue
        casts_by_ability = boss_casts(member.run, member.casts, their_actor_id)
        for ability_id, (name, _count) in casts_by_ability.items():
            names.setdefault(ability_id, name)
        qualifying = {
            ability_id: count
            for ability_id, (_name, count) in casts_by_ability.items()
            if count >= MIN_CASTS_TO_COMPARE
        }
        per_member.append((their_boss_seconds, qualifying))

    findings = _missing_sample(our_player, ours_anywhere, names, per_member, total)
    if our_boss_seconds > 0:
        findings += _rate_sample(our_player, ours_on_bosses, our_boss_seconds, per_member)
    return findings


def _missing_sample(
    our_player: Player,
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
    for rank, (matching, ability_id, name) in enumerate(candidates[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.missing.{rank}",
                title=(
                    f"{count_phrase(matching, total)} top parses cast {name} on bosses; "
                    f"{our_player.name} never did"
                ),
                detail=(
                    f"{name} does not appear anywhere in this run for {our_player.name} — not "
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
            )
        )
    return findings


def _rate_sample(
    our_player: Player,
    ours_on_bosses: dict[int, tuple[str, int]],
    our_boss_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> list[Finding]:
    """Abilities both sides cast, where the sample's median rate is materially higher."""
    gaps = []
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
        if our_rate <= 0 or their_median / our_rate < RATE_GAP_MULTIPLE:
            continue
        gaps.append((their_median - our_rate, ability_id, name, our_rate, their_median, rates))
    gaps.sort(key=lambda row: row[0], reverse=True)

    findings = []
    for rank, (_, ability_id, name, our_rate, their_median, rates) in enumerate(
        gaps[:MAX_SPELLS_REPORTED]
    ):
        low, high = observed_range(rates)
        findings.append(
            Finding(
                id=f"compare.spells.rate.{rank}",
                title=(
                    f"{len(rates)} top parses cast {name} a median {their_median:.1f} times a "
                    f"minute on bosses; {our_player.name} casts it {our_rate:.1f}"
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
            )
        )
    return findings


def compare_talents(
    our_player: Player, their_player: Player | None, their_row: ParseRow
) -> list[Finding]:
    """Whether the two builds differ, and the string needed to import theirs.

    The one row still drawn from a single reference: a build has no mean and no
    mode this project can compute. It names the top-ranked parse rather than
    the player who ran it, and links to that report, because a reader asked to
    copy a stranger's build is the one reader who must be able to trace it.
    """
    ours = our_player.talent_import_string
    theirs = their_player.talent_import_string if their_player else None
    source = REPORT_URL.format(code=their_row.report_code, fight=their_row.fight_id)

    if ours is None or theirs is None:
        return [
            Finding(
                id="compare.talents",
                title="The talent builds could not be compared",
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
                title="The talent build matches the top-ranked parse",
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
            title="The talent build differs from the top-ranked parse",
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
