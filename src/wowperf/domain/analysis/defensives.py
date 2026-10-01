# ABOUTME: Defensive claims a combat log can support: cast far below the cooldown ceiling,
# ABOUTME: or off cooldown at a death, one pull at a time or pooled across a boss. All inferred.

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable

from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding, quantity
from wowperf.domain.model import Player
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.season import CooldownAbility, DefensiveAbility, Defensives
from wowperf.domain.slug import player_slug

CEILING_USE_FRACTION = 0.2
"""How far below the ceiling a player must be before it is worth saying anything.

Measured, not chosen by taste: run against a realistic 28-minute dungeon run
with realistic press counts, a 0.5 fraction fired on seven of eight pressed
defensives, including "used Prismatic Barrier 12 of a possible 67 times" —
escaping that finding would take 34 presses in one dungeon. Using a defensive
at close to half its theoretical maximum is ordinary play, not neglect; 0.2
fires only on genuine near-neglect instead of on almost everything pressed.

The fraction carries its own floor, which is why no separate minimum sits
beside it. A press count is a positive integer, so `uses < ceiling * fraction`
cannot hold until the ceiling passes `1 / fraction` -- five, at 0.2. A ceiling
too small to argue from is therefore already silent, and a constant saying so
could only restate that arithmetic or contradict it.

The throughput ceiling borrows this fraction rather than having measured its
own. That is one of the reasons that claim is asked for rather than given.
"""

CEILING_WITHHELD_ID = "defensives.ceiling.withheld"
"""The finding that says a fight ran too short to judge some pressed defensive.

A press count is a positive integer, so `uses < ceiling * CEILING_USE_FRACTION`
cannot hold until the ceiling clears `1 / CEILING_USE_FRACTION` -- five. Below
that, the analyser is structurally unable to report on an ability regardless of
how it was used, and saying nothing reads on the page exactly like having used
it enough. This id names that silence instead of leaving it silent, so a caller
can lift it out by the id alone rather than by a prefix that would also catch
the ceiling findings it sits beside.
"""

RUN_UP_SECONDS = 10.0
"""How much of the run-up to a death counts as the damage that killed the player.

An ability that came off cooldown halfway through that run-up was never an
option anyone had, so availability is judged from when the damage began rather
than from the instant of death. The report's death card shows this same window,
so a reader sees the damage a defensive could have answered — long enough to
read the sequence, short enough that the card stays a card.
"""


def window_inside_log(moment_ms: int, seconds: float, visible_from_ms: int) -> bool:
    """Whether the `seconds` before `moment_ms` lie wholly inside the log.

    The log may not hold a press before `visible_from_ms`: a raid fight's
    casts start at the pull, and a cooldown carries over from the pull before.
    So a window reaching back past it cannot show that an ability was unspent.
    `defensives_up_at`, the pooled finding and the card's `state_of` ask this
    -- `state_of` only once COOLDOWN has been ruled out, since presses inside
    the log prove that state however early. `ready_at` (which `read_cooldown`
    reads through) and the consumable filters apply the same inequality
    inline. A window that cannot pass it is "not judged" rather than guessed
    in the one direction this project never guesses in.
    """
    return moment_ms - seconds * 1000 >= visible_from_ms


def defensives_up_at(
    casts: tuple[CastEvent, ...],
    abilities: tuple[DefensiveAbility, ...],
    actor_id: int,
    death_ms: int,
    *,
    visible_from_ms: int,
) -> tuple[str, ...]:
    """Names of `abilities` this player had off cooldown when the killing damage began.

    Two conditions, and the first is the one that keeps this honest.

    **The player must have cast the ability somewhere in the run.** Several
    entries in the data file are talent-gated, and a player who did not take the
    talent casts it nowhere — which looks exactly like having it and never
    pressing it. Reporting silence as availability would accuse someone of not
    pressing a button they do not own. An ability never cast at all is the death
    card's subject, where it reads as `unseen` beside the other states a
    reader needs to weigh it against.

    **And they must have cast it at no point in `[death - (cooldown + run-up),
    death]`.** That one window does two jobs: it excludes an ability still on
    cooldown, and it excludes one they pressed during the run-up and died anyway.

    **And that window must lie inside the log** (`window_inside_log`). The log
    may not hold a press before `visible_from_ms` -- a raid fight's casts start
    at the pull, and a cooldown carries over from the pull before -- so a
    window reaching back past the log's first second could hide the press that
    spent the ability. It is not judged, and the ability is not named.

    What remains resolves toward saying nothing. Base cooldowns are longer than
    talented ones; charges are ignored, so a spare charge reads as unavailable;
    and the log emits no cooldown reset or reduction events, so a reset reads as
    unavailable. Each understates what was up, and understating cannot produce
    a false accusation.

    Returned in the order the abilities were given, so a caller controls the
    reading order rather than inheriting a set's.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    return tuple(
        ability.name
        for ability in abilities
        if any(cast.ability_id == ability.ability_id for cast in ours)
        and window_inside_log(
            death_ms, ability.cooldown_seconds + RUN_UP_SECONDS, visible_from_ms
        )
        and not any(
            cast.ability_id == ability.ability_id
            and death_ms - (ability.cooldown_seconds + RUN_UP_SECONDS) * 1000
            <= cast.timestamp_ms
            <= death_ms
            for cast in ours
        )
    )


def _base_ids(players: Iterable[Player]) -> dict[int, str]:
    """Each player's id stem: the slug, or `slug.actor_id` when two players share it.

    Counted on the slug rather than the name, because the slug is what the id
    carries: `Bríala` and `Briala` are two players and one slug, and only the
    actor id then tells their findings apart. One helper, so the per-pull
    finding and the one pooling it across pulls apply the same disambiguation
    rule -- each against its own roster: the per-pull finding counts slugs on
    that one pull's roster, the pooled finding on the whole boss's roster
    across every pull. The two rosters can disagree, so the same player can
    take `briala` on a pull where they are the only `Bríala`/`Briala` present
    and `briala.<actor_id>` in the pooled finding, where both are.
    """
    unique = {player.actor_id: player for player in players}
    slugs = {actor_id: player_slug(player.name) for actor_id, player in unique.items()}
    counts = Counter(slugs.values())
    return {
        actor_id: slug if counts[slug] == 1 else f"{slug}.{actor_id}"
        for actor_id, slug in slugs.items()
    }


def analyse_defensives_at_death(
    players: tuple[Player, ...],
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
    *,
    locate: Callable[[Death], str],
    visible_from_ms: int,
    shape: str,
) -> list[Finding]:
    """Players who died while a personal defensive was off cooldown.

    One finding per player rather than per death, because the question a reader
    asks is about the player, and the evidence carries each death separately.

    `inferred`, like every other claim in this module: availability is
    reconstructed from cast timestamps and a base cooldown, and the log records
    no cooldown state to check it against. A defensive is also pressed into
    incoming damage rather than on cooldown, so an unpressed one that was up is
    a question worth asking, never a verdict.

    Only abilities the player cast somewhere in the run are considered, so a
    talent they never took cannot be held against them. That leaves the never-cast
    case entirely to the death card, which shows it as `unseen` alongside the
    other states an ability can be in at a death.

    A spec absent from the data file produces nothing, which is not the same
    claim as a spec that had nothing available. The caller must keep those apart.

    `locate` renders where a death happened for the evidence line — a pull
    offset for a keystone, something else for a fight with no pulls to offset
    against. `visible_from_ms` is the log's first second as the card reads it
    -- a keystone's first pull, a boss fight's own start -- and `shape` names
    that setting, "run" or "fight", for the sentence saying what is not judged.
    """
    base_ids = _base_ids(players)

    findings = []
    for player in players:
        abilities = defensives.for_spec(player.class_name, player.spec)
        if not abilities:
            continue

        lines = []
        first_pull: int | None = None
        for death in sorted(
            (death for death in deaths if death.actor_id == player.actor_id),
            key=lambda death: death.timestamp_ms,
        ):
            up = defensives_up_at(
                casts, abilities, player.actor_id, death.timestamp_ms,
                visible_from_ms=visible_from_ms,
            )
            if not up:
                continue
            if first_pull is None:
                first_pull = death.pull_index
            lines.append(
                f"{locate(death)} to {death.killing_blow}, with "
                f"{', '.join(up)} off cooldown"
            )

        if not lines:
            continue

        base_id = base_ids[player.actor_id]
        times = "once" if len(lines) == 1 else f"{len(lines)} times"
        findings.append(
            Finding(
                id=f"defensives.unused.{base_id}",
                title=f"{player.name} died {times} with a defensive available",
                detail=(
                    "Availability is read from this player's own casts against the "
                    "ability's base cooldown, judged from when the damage that killed "
                    f"them began. Only abilities they cast somewhere in the {shape} count, "
                    "so a talent they never took is never held against them, and spare "
                    "charges and cooldown resets are ignored because the log does not "
                    "record them. An ability whose base cooldown reaches back before the "
                    f"{shape}'s first second is not judged, since a press before it may "
                    "not be in the log. A defensive is pressed into damage rather than on "
                    "cooldown, so this is a question to ask, not a mistake to fix."
                ),
                confidence=Confidence.INFERRED,
                seconds_lost=None,
                evidence=(f"{player.class_name} {player.spec}", *lines),
                pull_index=first_pull,
            )
        )
    return findings


REPEAT_READY_PREFIX = "progression.repeat.ready."
"""Pooled across a boss's pulls, so it sits on the summary's Repeats tab.

The `progression.repeat.` placement puts it there with no table change; the
player's id stem follows, exactly as it does on the per-pull finding.
"""


def repeat_defensives_up(series: LoadedProgression, defensives: Defensives) -> list[Finding]:
    """Players whose own defensives were up at their deaths on more than one pull.

    `analyse_defensives_at_death`'s rule, pooled: each pull is judged by
    `defensives_up_at` on that pull's own casts, and the judgements are added
    up, so the pooled count is exactly the sum of the pull rows beneath it and
    stays right when a raider swaps a talent between pulls. Ownership is never
    judged across the night -- a talent dropped after one pull would otherwise
    read as available and unpressed on the next.

    Per player and ability, the count is the deaths at which it was up, and the
    denominator is the deaths on pulls where the player cast it at least once:
    on any other pull the rule cannot say whether they owned it, so those
    deaths are unknown rather than "not up". A death whose window reaches back
    before its own pull's first second is unknown the same way
    (`window_inside_log`): a cooldown carries over between pulls, so it is
    left out of both counts rather than read as down. A player is named when some
    ability was up at two or more deaths on two or more pulls -- two deaths
    inside one pull are a claim that pull's own row already makes.

    Every death counts, late wipe deaths included: measured on a real night,
    the share of defensives still ready at death does not rise in the pile-up
    (`docs/plans/2026-09-26-night-defensives-pooled-design.md` section 2).

    `inferred`, like every claim in this module. Players are matched across
    pulls by actor id, stable within one report, and each pull reads the spec
    that pull's roster gives. A spec absent from the data file names nobody.
    """
    roster: dict[int, Player] = {}
    for one in series.attempts_with_events:
        for player in one.players:
            roster.setdefault(player.actor_id, player)
    base_ids = _base_ids(roster.values())

    names: dict[tuple[int, int], str] = {}
    up: Counter[tuple[int, int]] = Counter()
    judged: Counter[tuple[int, int]] = Counter()
    pulls_up: dict[tuple[int, int], set[int]] = defaultdict(set)
    for one in series.attempts_with_events:
        pull_start_ms = one.window_ms[0]
        for player in one.players:
            abilities = defensives.for_spec(player.class_name, player.spec)
            cast_ids = {
                cast.ability_id for cast in one.casts if cast.actor_id == player.actor_id
            }
            for death in one.deaths:
                if death.actor_id != player.actor_id:
                    continue
                up_now = defensives_up_at(
                    one.casts, abilities, player.actor_id, death.timestamp_ms,
                    visible_from_ms=pull_start_ms,
                )
                for ability in abilities:
                    if ability.ability_id not in cast_ids:
                        continue
                    if not window_inside_log(
                        death.timestamp_ms, ability.cooldown_seconds + RUN_UP_SECONDS,
                        pull_start_ms,
                    ):
                        continue
                    key = (player.actor_id, ability.ability_id)
                    names.setdefault(key, ability.name)
                    judged[key] += 1
                    if ability.name in up_now:
                        up[key] += 1
                        pulls_up[key].add(one.encounter.fight_id)

    findings = []
    for actor_id, player in roster.items():
        # Two pulls is the whole rule: each pull in `pulls_up` holds at least
        # one death at which the ability was up, so two pulls imply two deaths.
        named = sorted(
            (key for key in up if key[0] == actor_id and len(pulls_up[key]) >= 2),
            key=lambda key: (-up[key], names[key]),
        )
        if not named:
            continue
        lines = tuple(
            f"{names[key]} up at {up[key]} of {judged[key]} deaths" for key in named
        )
        single = named[0] if len(named) == 1 else None
        findings.append(
            Finding(
                id=f"{REPEAT_READY_PREFIX}{base_ids[actor_id]}",
                title=(
                    f"{player.name}: {lines[0]}"
                    if single is not None
                    else f"{player.name}: {len(named)} defensives up at more than one death"
                ),
                detail=(
                    "Judged pull by pull from this player's own casts against each "
                    "ability's base cooldown, counting only abilities they cast somewhere "
                    "in that pull, then added up across the boss's pulls. A death at which "
                    "an ability's base cooldown reaches back before that pull's first "
                    "second is not judged or counted for it, since a press before the pull "
                    "is invisible. Every other death counts, late wipe deaths included: "
                    "the share of defensives still up at death was measured not to rise "
                    "once a wipe comes apart. A defensive is pressed into damage rather "
                    "than on cooldown, so this is a question to ask, not a mistake to fix."
                ),
                confidence=Confidence.INFERRED,
                evidence=(f"{player.class_name} {player.spec}", *lines),
                ability_id=single[1] if single is not None else None,
                ability_name=names[single] if single is not None else "",
            )
        )
    return findings


def alive_combat_seconds(
    combat_seconds: float,
    deaths: tuple[Death, ...],
    actor_id: int,
    *,
    combat_end_ms: int,
) -> float:
    """Combat time this player could actually have pressed a button in.

    `combat_seconds` is the denominator the caller's aggregate defines: summed
    pull time for a keystone, fight duration for a raid boss. Taking the number
    rather than the aggregate is what lets both ask this question; taking a
    `Run` meant a raid fight silently supplied zero.

    A death's dead time is `seconds_until_next_action` where the log recorded
    one. Where it did not, the player was never seen to act on another actor
    again, and they count as dead from that death until `combat_end_ms`. On a
    raid wipe that is exact: the fight ended, so they provably never returned,
    and `combat_end_ms` and `combat_seconds` share the same wall clock. On a
    keystone it is not: `combat_end_ms` is `run.window_ms[1]`, wall-clock time,
    while `combat_seconds` sums pull time only, so a death near the run's end
    still charges the player for whatever between-pull downtime followed it --
    another understatement rather than an exact one, leaning the same safe
    direction as every other approximation here. For a player resurrected who
    then only ever casts on themselves it understates their alive time the
    same way, which lowers their ceiling and weakens the claim -- because
    understating cannot produce a false accusation.

    Approximate on purpose either way, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot.
    """
    dead = 0.0
    for death in deaths:
        if death.actor_id != actor_id:
            continue
        if death.seconds_until_next_action is None:
            # Clamped because a death can sit a millisecond past the window a
            # keystone computes for itself; see `Run.window_ms`.
            dead += max(combat_end_ms - death.timestamp_ms, 0) / 1000
        else:
            dead += death.seconds_until_next_action
    return max(combat_seconds - dead, 0.0)


def cooldown_ceiling(alive_seconds: float, ability: CooldownAbility) -> float:
    """How many times the cooldown alone would have allowed this to be pressed."""
    return alive_seconds / ability.cooldown_seconds * ability.charges


def defensive_base_ids(
    players: tuple[Player, ...], defensives: Defensives
) -> dict[tuple[int, int], str]:
    """The id fragment every `defensives.*` finding carries, by (actor, ability).

    Minted here rather than inside `analyse_defensive_ceiling` so that anything
    needing to find a defensives finding again can generate the same id
    instead of taking one apart. These findings carry no `player_slug`: the
    owner lives only in this fragment, and a reader parsing it back would be
    parsing a string this module had just formatted.

    Counted on the slug rather than the name, because the slug is what the id
    carries: `Bríala` and `Briala` are two players and one slug, and only the
    actor id then tells their findings apart.
    """
    slug_counts: dict[str, int] = defaultdict(int)
    for player in players:
        slug_counts[player_slug(player.name)] += 1

    ids: dict[tuple[int, int], str] = {}
    for player in players:
        slug = player_slug(player.name)
        for ability in defensives.for_spec(player.class_name, player.spec):
            ids[(player.actor_id, ability.ability_id)] = (
                f"{slug}.{ability.ability_id}"
                if slug_counts[slug] == 1
                else f"{slug}.{player.actor_id}.{ability.ability_id}"
            )
    return ids


def _ceiling_withheld(
    needs: set[tuple[str, float]], *, shape: str, combat_description: str
) -> Finding:
    """The abilities this fight was too short to judge, said out loud.

    `measured`, on the same reasoning `attempt_shape._withheld` gives: what is
    asserted is that the analyser declined and why, and both halves are checked
    rather than read. The ceiling claim it declined to make is `inferred`; this
    is not that claim.

    One finding per report rather than per player or per ability. The
    suppression is a fact about the fight's length and an ability's own
    cooldown and charges, identical for every raider carrying the same variant
    of that ability, and twenty players against sixty-five abilities is a wall
    rather than a disclosure.

    `needs` pairs each name with the seconds *that variant* required, rather
    than a bare name, because a name alone cannot say how long an ability
    needs: charges divide that figure, so two players carrying the same-named
    ability under different specs can genuinely need different combat lengths.

    The title and detail still count distinct ability *names*, not `needs`'
    pairs: a raid holding two specs of the same ability is one defensive a
    reader would recognise by name, not two, even though its two variants
    need different combat lengths. Only the evidence -- where the two figures
    belong -- carries one line per variant.

    `shape` and `combat_description` are the caller's words, not this
    module's: a keystone report says "run" throughout and a raid page says
    "fight", and what `combat_seconds` honestly measures differs the same
    way -- summed pull time on a keystone, wall-clock duration on a raid.
    Hard-coding either here would put raid wording on a dungeon page, or
    state a keystone's summed pull time as if it were elapsed time.

    The detail names no ability itself: it ends on the sentence that
    introduces the evidence lines rather than restating them, because the
    two are printed as one paragraph -- `report/build.py` and
    `report/raid_build.py` both append this finding's `evidence` straight
    onto its `detail` for the single Provenance entry a reader sees, so the
    detail's closing colon must lead into lines that immediately follow it
    rather than into a section that does not exist on the page.
    """
    count = len({name for name, _ in needs})
    return Finding(
        id=CEILING_WITHHELD_ID,
        title=(
            f"This {shape} was too short to judge "
            f"{quantity(count, 'pressed defensive', 'pressed defensives')}"
        ),
        detail=(
            "A ceiling claim needs an ability to fit more than five uses into "
            f"the {shape}, charges included: below that, a single press "
            "already clears the threshold, so no press count could ever be "
            "low enough to report. Nothing is being said about how those "
            "were used -- this is the analyser declining to judge them, not "
            f"a clean bill of health. {combat_description}, short of what "
            f"{count} of the defensives someone pressed would need -- "
            "charges change that figure from one defensive to the next, so "
            "each is named here:"
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=tuple(
            f"{name} would need more than {seconds:.0f}s of combat"
            for name, seconds in sorted(needs)
        ),
    )


def analyse_defensive_ceiling(
    players: tuple[Player, ...],
    combat_seconds: float,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
    *,
    combat_end_ms: int,
    shape: str,
    combat_description: str,
) -> list[Finding]:
    """Defensives pressed far below their cooldown ceiling (§5.7).

    `inferred`. The log emits no cooldown-reset or reduction events, so the
    claim cannot be measured, and a defensive is pressed into damage rather
    than on cooldown — the ceiling bounds what was possible, not what was
    right.

    An ability the player never pressed produces nothing here. It has no
    ceiling to be judged against, and the claim that they never pressed it is
    the death card's, where it sits beside the other states a reader needs to
    weigh it.

    `shape` and `combat_description` feed only the withheld notice's own
    wording -- see `_ceiling_withheld` -- and are required rather than
    defaulted for the same reason `combat_end_ms` is: a caller who forgets
    one should fail loudly rather than ship raid words on a keystone page, or
    a keystone's summed pull time stated as if it had elapsed.
    """
    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1

    base_ids = defensive_base_ids(players, defensives)

    # Keyed by (name, seconds needed) rather than by name alone: two specs
    # carrying a genuinely identical ability collapse to one entry, but two
    # specs whose same-named ability differs in cooldown or charges -- Barkskin
    # is 45s for a Guardian and 60s for every other druid spec -- each keep
    # their own figure instead of one overwriting the other.
    too_short: set[tuple[str, float]] = set()

    findings = []
    for player in players:
        known = defensives.for_spec(player.class_name, player.spec)
        alive = alive_combat_seconds(
            combat_seconds, deaths, player.actor_id, combat_end_ms=combat_end_ms
        )
        for ability in known:
            base_id = base_ids[(player.actor_id, ability.ability_id)]
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)
            if not uses:
                continue

            # Judged against the fight, not against this player's alive time: a
            # player who died early has abilities suppressed by their short life
            # rather than by a short fight, and a line saying the fight was too
            # short would then be false.
            if cooldown_ceiling(combat_seconds, ability) <= 1 / CEILING_USE_FRACTION:
                too_short.add((
                    ability.name,
                    ability.cooldown_seconds / ability.charges / CEILING_USE_FRACTION,
                ))

            ceiling = cooldown_ceiling(alive, ability)
            if uses >= ceiling * CEILING_USE_FRACTION:
                continue
            findings.append(
                Finding(
                    id=f"defensives.ceiling.{base_id}",
                    title=(
                        f"{player.name} used {ability.name} {uses} "
                        f"of a possible {ceiling:.0f} times"
                    ),
                    detail=(
                        f"{ability.name} has a {ability.cooldown_seconds:.0f}s cooldown, "
                        f"which fits {ceiling:.0f} times into the {alive:.0f}s this player "
                        "spent alive and in combat. That is a ceiling, not a target: a "
                        "defensive is pressed into incoming damage, not on cooldown, so a "
                        "gap here is a question to ask rather than a mistake to fix."
                    ),
                    confidence=Confidence.INFERRED,
                    seconds_lost=None,
                    evidence=(
                        f"{player.class_name} {player.spec}",
                        f"ability {ability.ability_id}",
                        f"{quantity(uses, 'cast', 'casts')} in {alive:.0f}s alive",
                    ),
                    ability_id=ability.ability_id,
                    ability_name=ability.name,
                )
            )
    # `combat_seconds` is zero for a keystone with no pulls at all --
    # `Run.window_ms` and `total_pull_seconds` both collapse to zero, so
    # `cooldown_ceiling(0, ability) == 0` clears the `<= 5` test for any
    # ability pressed outside every pull window. Minting the notice there
    # would blame the fight's length for a silence that is actually the log
    # carrying no pulls to time it by, which is a different and false claim.
    if too_short and combat_seconds > 0:
        findings.append(
            _ceiling_withheld(too_short, shape=shape, combat_description=combat_description)
        )
    return findings
