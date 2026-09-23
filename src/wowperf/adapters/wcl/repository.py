# ABOUTME: Assembles a Run from Warcraft Logs, caching every response it fetches.
# ABOUTME: Satisfies the RunRepository port so services never learn where a run came from.

from collections.abc import Sequence
from typing import Any, Literal, NamedTuple, cast

import httpx

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.config.toml import load_raid_partition
from wowperf.adapters.wcl.client import RateLimit, RateLimitExceeded, WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_casts,
    build_damage_done,
    build_damage_taken,
    build_deaths,
    build_encounter,
    build_enemy_cast_rows,
    build_enemy_deaths,
    build_healing,
    build_health_samples,
    build_interrupts,
    build_phases,
    build_player_auras,
    build_raid_roster,
    build_resurrections,
    build_run,
    select_keystone_fight,
    select_raid_fight,
)
from wowperf.adapters.wcl.loadouts import build_loadouts
from wowperf.adapters.wcl.pagination import Execute, fetch_all_events
from wowperf.adapters.wcl.queries import (
    ABILITIES_QUERY,
    ACTORS_QUERY,
    AFFIXES_QUERY,
    AURA_TABLE_QUERY,
    CASTS_QUERY,
    DAMAGE_DONE_GRAPH_QUERY,
    DAMAGE_TAKEN_QUERY,
    DEATHS_QUERY,
    ENEMY_CASTS_QUERY,
    ENEMY_DEATHS_QUERY,
    FIGHTS_QUERY,
    HEALING_QUERY,
    INTERRUPTS_QUERY,
    PLAYER_DETAILS_QUERY,
    REPORT_RANKINGS_QUERY,
    RESURRECTS_QUERY,
    talents_query,
)
from wowperf.adapters.wcl.report_rankings import build_report_rankings
from wowperf.domain.analysis.defensives import RUN_UP_SECONDS
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.raid_reference import ReportRankings
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, Death, HealingEvent
from wowperf.domain.loadout import Loadout
from wowperf.domain.model import LoadedRun, Player, Pull, Run
from wowperf.domain.night import FailedPull, LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression, build_progression

# `full` loads everything our own run needs. `speed` and `parse` are the two
# trimmed reference profiles, each fetching only the streams its own axis reads.
_Profile = Literal["full", "speed", "parse"]


class RaidReference(NamedTuple):
    """One raid boss fight fetched to stand beside ours, as the three values a
    `ParseMember` is built from.

    Not a `LoadedEncounter`. An `Encounter` carries a `partition`, which a
    reference's report never states and `build_encounter` therefore refuses to
    guess -- inventing one here to satisfy a constructor would put a number this
    project made up into a field every later reader would take for a measurement.
    The reference's fight length is not here either: the leaderboard row that
    named this fight already carries `duration`, and reading it twice is two
    places for one fact to be got from.
    """

    players: tuple[Player, ...]
    casts: tuple[CastEvent, ...]
    ability_icons: tuple[tuple[int, str], ...]


def healing_windows(deaths: Sequence[Death]) -> list[tuple[int, int, int]]:
    """One `(actor, start, end)` window per stretch of a player's run-ups.

    Two deaths of the same player less than the run-up apart share the seconds
    before the later one. Asking for a window per death would fetch those
    seconds twice, and every heal in them would then reach both cards twice
    over, health column included. Merged windows are still cut back to one
    run-up per death by the timeline that reads them.
    """
    run_up_ms = int(RUN_UP_SECONDS * 1000)
    windows: list[tuple[int, int, int]] = []
    for death in sorted(deaths, key=lambda death: (death.actor_id, death.timestamp_ms)):
        start, end = death.timestamp_ms - run_up_ms, death.timestamp_ms
        if windows and windows[-1][0] == death.actor_id and start <= windows[-1][2]:
            actor, opened, _ = windows[-1]
            windows[-1] = (actor, opened, end)
        else:
            windows.append((death.actor_id, start, end))
    return windows


def _pick_boss(
    fights: list[dict[str, Any]],
    encounter_id: int | None,
    difficulty: int | None,
) -> tuple[int, int]:
    """The boss and difficulty a night's fights are read against.

    `fights` is a report's boss fights, never empty -- the caller raises before
    reaching here. With no `encounter_id`, this stands in for the CLI flag a
    keystone run never needs: `select_raid_fight` refuses the same way with one
    fight already picked, and this refuses one step earlier, before any fight
    is built. The only boss present is chosen without asking; several bosses
    raise, naming every one of them and the flag that resolves the question.

    An explicit `encounter_id` with no `difficulty` takes the difficulty of
    that boss's first fight, on the same reasoning `Progression` itself uses:
    a raid night is fought at one difficulty, so the fight list settles it
    rather than making the caller repeat what the report already states.

    The existence check runs whether or not `difficulty` was supplied. An
    explicit `--boss` naming a fight absent from the report, or naming one
    present only at a different difficulty, is a routine user error and must
    be refused with a message -- not answered with an unchecked pair that
    `build_progression` then turns into an empty, nameless series.
    """
    if encounter_id is None:
        boss_ids = sorted({int(fight["encounterID"]) for fight in fights})
        if len(boss_ids) != 1:
            named = ", ".join(str(boss_id) for boss_id in boss_ids)
            raise ValueError(f"This report holds several bosses ({named}); pass --boss")
        encounter_id = boss_ids[0]

    matching = [fight for fight in fights if fight["encounterID"] == encounter_id]
    if not matching:
        raise ValueError(f"This report holds no fight for boss {encounter_id}")

    if difficulty is None:
        difficulty = int(matching[0]["difficulty"])
    elif not any(int(fight["difficulty"]) == difficulty for fight in matching):
        raise ValueError(
            f"This report holds no difficulty {difficulty} fight for boss {encounter_id}"
        )

    return encounter_id, difficulty


class WclRunRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    @property
    def client(self) -> WclClient:
        return self._client

    @property
    def cache(self) -> DiskCache:
        return self._cache

    def _query(
        self, query: str, variables: dict[str, Any], hits: list[bool] | None = None
    ) -> dict[str, Any]:
        """Run one query through the cache, recording a hit or a miss when `hits` is given.

        `hits` is a list local to one `_load` call, not adapter state: two
        concurrent loads must not race a shared "was that a hit" flag, so the
        aggregate is threaded through explicitly instead of stored on `self`.
        """
        payload, hit = self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._fetch(query, variables),
        )
        if hits is not None:
            hits.append(hit)
        # Also checked on the way out of the cache, so an entry written by an
        # older build still reports the problem instead of subscripting None.
        self._require_report(payload, variables)
        return payload

    def _fetch(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Fetch and validate a payload, so that only a usable one reaches the cache."""
        payload = self._client.execute(query, variables)
        self._require_report(payload, variables)
        return payload

    @staticmethod
    def _require_report(payload: dict[str, Any] | None, variables: dict[str, Any]) -> None:
        """Reject a null report.

        An unlisted or unknown report usually answers HTTP 200 with
        `reportData.report` null and no GraphQL errors. Since
        `WclClient.execute` now raises on a null `data` block, only a stale
        cache entry from an older build can deliver None here. Raising before
        the payload is cached matters: an entry lives for a day or forever, so
        caching one would poison the key for that whole span.
        """
        if payload is None:
            raise IngestError(
                f"Report {variables.get('code')} was not found, or is not accessible "
                "with these credentials. Private reports need a personal login, which "
                "this tool does not support."
            )
        report_data = payload.get("reportData")
        if isinstance(report_data, dict) and report_data.get("report") is None:
            raise IngestError(
                f"Report {variables.get('code')} was not found, or is not accessible "
                "with these credentials. Private reports need a personal login, which "
                "this tool does not support."
            )

    def rate_limit(self) -> RateLimit:
        """Read the quota straight from the API; a cached reading would be worthless."""
        return self._client.rate_limit()

    def _report(self, report_code: str, hits: list[bool] | None = None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._query(FIGHTS_QUERY, {"code": report_code}, hits)["reportData"]["report"],
        )

    def _fetch_affixes(self) -> dict[str, Any]:
        """Fetch and validate the affix table, so only a usable payload reaches the cache."""
        payload = self._client.execute(AFFIXES_QUERY, {})
        game_data = payload.get("gameData")
        if not isinstance(game_data, dict) or not game_data.get("affixes"):
            raise WclError("The affixes response did not carry gameData.affixes as expected")
        return payload

    def _affix_names(
        self, affix_ids: Sequence[int], hits: list[bool] | None = None
    ) -> tuple[str, ...]:
        """Affix names from game data, with the bare id for anything unlisted.

        Goes to the cache and the client directly rather than through `_query`:
        the affix table needs its own validation before it may be cached
        (`_fetch_affixes` does that), and unlike every other query this
        repository issues, its absence must degrade the run rather than fail
        it — an affix id the report already carries is still usable on its
        own, so a header of bare ids is preferable to no report at all. A
        spent rate limit is the one failure still allowed through: it must
        stop the run rather than be swallowed into a silent degrade.

        Cached indefinitely: the affix table is game-wide and changes only when
        Blizzard adds one, at which point the new id simply resolves to itself
        until the cache is cleared.
        """
        if not affix_ids:
            return ()
        try:
            payload, hit = self._cache.get_or_fetch(
                cache_key(AFFIXES_QUERY, {}), self._fetch_affixes
            )
        except WclError as error:
            if isinstance(error, RateLimitExceeded):
                raise
            # A degrade is not a reuse: a real attempt was made and it failed.
            if hits is not None:
                hits.append(False)
            return tuple(str(affix_id) for affix_id in affix_ids)
        if hits is not None:
            hits.append(hit)
        rows = payload["gameData"]["affixes"]
        names = {int(row["id"]): str(row["name"]) for row in rows}
        return tuple(names.get(affix_id, str(affix_id)) for affix_id in affix_ids)

    def get(self, report_code: str, fight_id: int | None) -> Run:
        """Build the run alone, without paying for the event streams `load` fetches."""
        report = self._report(report_code)
        run = build_run(report, select_keystone_fight(report["fights"], fight_id))
        return run.model_copy(update={"affix_names": self._affix_names(run.affix_ids)})

    def _actor_game_ids(
        self, report_code: str, hits: list[bool] | None = None
    ) -> dict[int, int]:
        """Map every actor in the report to its game id, so an enemy death always resolves.

        A death can target a Pet actor as well as an NPC one: a dungeon mechanic
        that encases a player is modelled as a hostile pet owned by that player.
        Fetching every actor, not only type "NPC", is what makes that resolve.
        """
        payload = self._query(ACTORS_QUERY, {"code": report_code}, hits)
        report = payload["reportData"]["report"]
        master = report.get("masterData") or {}
        actors = master.get("actors")
        if actors is None:
            raise WclError(f"Report {report_code} returned no masterData.actors block")
        return {actor["id"]: actor["gameID"] for actor in actors}

    def _talents(
        self, report_code: str, fight: dict[str, Any], hits: list[bool] | None = None
    ) -> dict[int, str]:
        """The talent import string per player, keyed by actor id.

        A player with no recorded build is left out rather than given an empty
        string: absent and "took no talents" are different claims.
        """
        actor_ids = [int(actor_id) for actor_id in fight.get("friendlyPlayers") or []]
        if not actor_ids:
            return {}

        payload = self._query(
            talents_query(actor_ids), {"code": report_code, "fightId": fight["id"]}, hits
        )
        fights = payload["reportData"]["report"]["fights"] or [{}]
        codes = fights[0]
        return {
            actor_id: codes[f"a{actor_id}"]
            for actor_id in actor_ids
            if codes.get(f"a{actor_id}")
        }

    def _ability_dictionary(
        self, report_code: str, hits: list[bool] | None = None
    ) -> tuple[dict[int, str], tuple[tuple[int, str], ...]]:
        """The report's ability names by game id, and the icon file names beside them.

        One query for the whole report rather than one per fight, which is why
        it is keyed by report code alone. An ability with no icon is left out of
        the second half rather than carried with an empty name: an empty string
        is not a file name, and a page addressing one draws a broken image where
        a clean gap belongs.
        """
        payload = self._query(ABILITIES_QUERY, {"code": report_code}, hits)
        try:
            rows = payload["reportData"]["report"]["masterData"]["abilities"]
            names = {ability["gameID"]: ability["name"] for ability in rows}
            icons = tuple(
                (ability["gameID"], ability["icon"])
                for ability in rows
                if ability.get("icon")
            )
        except (KeyError, TypeError) as error:
            raise WclError(
                "The abilities response did not carry masterData.abilities as expected"
            ) from error
        return names, icons

    def _loadouts(
        self, report_code: str, fight: dict[str, Any], hits: list[bool] | None = None
    ) -> dict[int, Loadout]:
        """Gear and stat ratings per player, keyed by actor id.

        Costs 2.00 points, measured 2026-09-14. A report that returns nothing
        usable yields an empty map, and every consumer reads that as unknown.
        """
        payload = self._query(
            PLAYER_DETAILS_QUERY, {"code": report_code, "fightId": fight["id"]}, hits
        )
        return build_loadouts(payload)

    def load(self, report_code: str, fight_id: int | None) -> LoadedRun:
        """Every stream the analysers and the death cards read."""
        loaded, _ = self._load(report_code, fight_id, profile="full")
        return loaded

    def _report_rankings(
        self,
        report_code: str,
        fight_id: int,
        metric: str,
        hits: list[bool] | None = None,
    ) -> ReportRankings | None:
        """One `Report.rankings` row for one `playerMetric`, or `None` off a wipe.

        Called once for `dps` and once for `bossdps`: Tasks 7 and 8 each read
        one of the two rows, and fetching either again later would pay its
        2.00 points twice. A wipe's row list is empty, with no field
        distinguishing it from a kill -- design section 14 item 7, measured
        2026-09-14.
        """
        payload = self._query(
            REPORT_RANKINGS_QUERY,
            {"code": report_code, "fightId": fight_id, "metric": metric},
            hits,
        )
        return build_report_rankings(payload, fight_id)

    def load_encounter(self, report_code: str, fight_id: int | None) -> LoadedEncounter:
        """Every stream the raid analysers and the death cards read, for one boss fight.

        Reuses the same query fan-out and cache as `load`'s full profile, with
        `select_raid_fight` and `build_encounter` standing in for their keystone
        counterparts. Two Mythic+-only steps are skipped rather than adapted:
        `_affix_names`, because an `Encounter` carries no affix vocabulary to
        resolve at all, and the enemy-deaths forces splice (`_actor_game_ids` and
        `ENEMY_DEATHS_QUERY`), because `LoadedEncounter` deliberately carries no
        `enemy_deaths` field -- that stream exists to price a keystone's
        enemy-forces requirement, which a boss fight has none of.
        """
        hits: list[bool] = []
        report = self._report(report_code, hits)
        fight = select_raid_fight(report["fights"], fight_id)
        talents = self._talents(report_code, fight, hits)
        standing = self._report_rankings(report_code, fight["id"], "dps", hits)
        boss_standing = self._report_rankings(report_code, fight["id"], "bossdps", hits)
        # ReportFight carries no partition field at all. Design 2.2 prescribes
        # reading it from the report's own `Report.rankings` row, and this is
        # that read. `boss_standing` is fetched and kept for Tasks 7 and 8 but
        # takes no part here: only the `dps` row (`standing`) has been
        # measured against a wipe, so it is the only one this fallback trusts.
        # A wipe returns no row at all -- measured, design section 14 item 7
        # -- so `data/season.toml` stays as the fallback for exactly that case
        # rather than as the source for every case.
        partition = standing.partition if standing else load_raid_partition()
        partition_source = "report rankings" if standing else "data/season.toml"
        encounter = build_encounter(report, fight, partition=partition, talents=talents)

        ability_names, ability_icons = self._ability_dictionary(report_code, hits)

        event_variables = {
            "code": report_code,
            "fightId": encounter.fight_id,
            "startTime": float(fight["startTime"]),
            "endTime": float(fight["endTime"]),
        }

        def query(one_query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return self._query(one_query, variables, hits)

        cast_events = fetch_all_events(query, CASTS_QUERY, event_variables)
        death_events = fetch_all_events(query, DEATHS_QUERY, event_variables)
        enemy_cast_events = fetch_all_events(query, ENEMY_CASTS_QUERY, event_variables)
        interrupt_events = fetch_all_events(query, INTERRUPTS_QUERY, event_variables)
        damage_taken_events = fetch_all_events(query, DAMAGE_TAKEN_QUERY, event_variables)

        # A boss fight carries no pulls at all, so every builder below gets an
        # empty tuple where the Mythic+ path passes `run.pulls`: pull_index_at
        # returns None unconditionally over an empty sequence, which is the
        # correct answer for an event that is never "inside" or "outside" a pull.
        no_pulls: tuple[Pull, ...] = ()
        casts = build_casts(cast_events, no_pulls, ability_names)
        player_names = {player.actor_id: player.name for player in encounter.players}
        deaths = build_deaths(death_events, no_pulls, casts, player_names, ability_names)
        enemy_cast_rows = build_enemy_cast_rows(enemy_cast_events, no_pulls, ability_names)
        interrupts = build_interrupts(interrupt_events, no_pulls, player_names)
        damage_taken = build_damage_taken(damage_taken_events, no_pulls, ability_names)
        # Pre-aggregated by the API, so one call rather than a paginated stream,
        # exactly as `load` fetches it.
        damage_done = build_damage_done(query(DAMAGE_DONE_GRAPH_QUERY, event_variables))
        resurrections = build_resurrections(
            fetch_all_events(query, RESURRECTS_QUERY, event_variables), ability_names
        )

        # One healing window per stretch of run-ups, scoped to the dying player,
        # exactly as `load` fetches it.
        healing: list[HealingEvent] = []
        for actor_id, start, end in healing_windows(deaths):
            scoped = {
                "code": report_code,
                "fightId": encounter.fight_id,
                "actorId": actor_id,
                "startTime": float(start),
                "endTime": float(end),
            }
            healing.extend(
                build_healing(fetch_all_events(query, HEALING_QUERY, scoped), ability_names)
            )

        return LoadedEncounter(
            encounter=encounter,
            casts=casts,
            deaths=deaths,
            enemy_cast_rows=enemy_cast_rows,
            interrupts=interrupts,
            damage_taken=damage_taken,
            damage_done=damage_done,
            health_samples=build_health_samples(cast_events),
            healing=tuple(healing),
            resurrections=resurrections,
            ability_icons=ability_icons,
            standing=standing,
            boss_standing=boss_standing,
            partition_source=partition_source,
        )

    def load_progression(
        self,
        report_code: str,
        encounter_id: int | None,
        difficulty: int | None,
    ) -> Progression:
        """Every attempt at one boss, from one report, in one query.

        Layer 1 of the progression design needs fight metadata and nothing else,
        and `FIGHTS_QUERY` already returns every fight in the report. So a whole
        night costs one query, which is the design's central cost claim.

        No rankings query is sent. The series compares attempts to each other and
        draws no external reference, so the partition comes from the season file
        and is carried only because `Encounter` requires one.
        """
        report = self._report(report_code)
        boss_fights = [f for f in report.get("fights") or () if f.get("encounterID")]
        if not boss_fights:
            raise ValueError(f"Report {report_code} holds no boss fight")

        encounter_id, difficulty = _pick_boss(boss_fights, encounter_id, difficulty)
        partition = load_raid_partition()
        phases, separates_wipes = build_phases(report, encounter_id)
        encounters = [
            build_encounter(report, fight, partition=partition) for fight in boss_fights
        ]
        return build_progression(
            encounters,
            encounter_id=encounter_id,
            difficulty=difficulty,
            phases=phases,
            separates_wipes=separates_wipes,
        )

    def load_night(self, report_code: str, difficulty: int | None) -> Night:
        """Every boss in one report, each as a Progression, from one fight list.

        `load_progression` reads this same list and then narrows it to one boss,
        refusing when nothing picks one out. This reads it and keeps all of
        them: the report is the subject here, so several bosses is what the
        command is for rather than an ambiguity to refuse.

        One `Fights` query answers the whole report, exactly as it does for
        `load_progression` -- the cost of reading a night's shape does not scale
        with how many bosses it holds. What scales is the deepening, which is
        `load_night_attempts`' business and priced there.

        An explicit `difficulty` narrows the report rather than one boss: a
        boss fought only at a different difficulty is skipped, never raised
        on the way `_pick_boss` raises for a single `--boss`/`--difficulty`
        mismatch. A real raid night routinely clears some bosses at one
        difficulty and pushes others at another, and skipping never invents a
        difficulty for the boss it keeps -- mixing difficulties on one page
        would make the page's own difficulty label meaningless. Only when
        every boss is skipped this way does it raise, naming the difficulty
        asked for and the ones the report actually holds: a report with boss
        fights that simply are not at that difficulty is a different failure,
        with a different cause, than a report with no boss fights at all.
        """
        report = self._report(report_code)
        boss_fights = [f for f in report.get("fights") or () if f.get("encounterID")]
        if not boss_fights:
            return Night(report_code=report_code, bosses=())

        boss_ids: list[int] = []
        for fight in boss_fights:
            boss_id = int(fight["encounterID"])
            if boss_id not in boss_ids:
                boss_ids.append(boss_id)

        if difficulty is not None:
            boss_ids = [
                boss_id
                for boss_id in boss_ids
                if any(
                    fight["encounterID"] == boss_id and int(fight["difficulty"]) == difficulty
                    for fight in boss_fights
                )
            ]
            if not boss_ids:
                present = sorted({int(fight["difficulty"]) for fight in boss_fights})
                named = ", ".join(str(one) for one in present)
                raise ValueError(
                    f"This report holds no boss fight at difficulty {difficulty}; "
                    f"it holds difficulty {named}"
                )

        partition = load_raid_partition()
        encounters = [
            build_encounter(report, fight, partition=partition) for fight in boss_fights
        ]

        bosses: list[Progression] = []
        for boss_id in boss_ids:
            resolved_id, resolved_difficulty = _pick_boss(boss_fights, boss_id, difficulty)
            phases, separates_wipes = build_phases(report, resolved_id)
            bosses.append(
                build_progression(
                    encounters,
                    encounter_id=resolved_id,
                    difficulty=resolved_difficulty,
                    phases=phases,
                    separates_wipes=separates_wipes,
                )
            )
        return Night(report_code=report_code, bosses=tuple(bosses))

    def load_progression_attempts(self, progression: Progression) -> LoadedProgression:
        """Deepen every qualifying attempt: deaths and damage taken, nothing else.

        Two streams an attempt, against the nine `load_encounter` fetches for one
        fight. Measured 2026-09-16: an event stream costs about 1.00 points a
        fight whatever its size.

        Projected, not measured: two streams over an eight-attempt night lands
        near 20 points of 3600, well under the design's 40-to-60 estimate for
        three streams -- lower only because that estimate priced a debuff
        stream this command never sends. Nobody has clocked a cold run of this
        command end to end; the one figure actually measured for it is a
        warm-cache re-run at 8.00 points -- 7 `Deaths` calls for 7.00 and 2
        `RateLimit` calls for 1.00, with `Fights`, `Abilities` and `DamageTaken`
        all served from cache -- so it prices a re-run, not a cold one.

        No casts stream. `build_deaths` uses casts only to time how long a dead
        player stayed out of the fight, which is a Mythic+ recap's figure and
        which nothing in Layer 2 reads; fetching one per attempt would double
        the command's cost for a field nobody looks at.

        Returns before fetching anything when `progression.attempts` is empty:
        a night where every attempt fell under `MIN_ATTEMPT_SECONDS` has
        nothing to deepen, and an ability dictionary nothing would read is a
        point spent for no reason.
        """
        if not progression.attempts:
            return LoadedProgression(progression=progression)

        hits: list[bool] = []
        ability_names, _icons = self._ability_dictionary(progression.report_code, hits)

        def query(one_query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return self._query(one_query, variables, hits)

        no_pulls: tuple[Pull, ...] = ()
        loaded: list[LoadedEncounter] = []
        for attempt in progression.attempts:
            event_variables = {
                "code": attempt.report_code,
                "fightId": attempt.fight_id,
                "startTime": float(attempt.start_ms),
                "endTime": float(attempt.end_ms),
            }
            player_names = {player.actor_id: player.name for player in attempt.players}
            deaths = build_deaths(
                fetch_all_events(query, DEATHS_QUERY, event_variables),
                no_pulls,
                (),
                player_names,
                ability_names,
            )
            damage_taken = build_damage_taken(
                fetch_all_events(query, DAMAGE_TAKEN_QUERY, event_variables),
                no_pulls,
                ability_names,
            )
            loaded.append(
                LoadedEncounter(encounter=attempt, deaths=deaths, damage_taken=damage_taken)
            )

        return LoadedProgression(progression=progression, loaded=tuple(loaded))

    def load_night_attempts(
        self, night: Night, *, deep_fights: frozenset[int], death_cards: bool
    ) -> LoadedNight:
        """Deepen every attempt of every boss, each at the cheapest tier that serves it.

        A night pull renders a whole pull page, so it needs more than the two
        streams `load_progression_attempts` fetches -- that page draws no death
        card at all. It needs less than `load_encounter` fetches, though: no
        parse axis, and no stream a trimmed card leaves undrawn. What it needs
        is a ladder, consulted per attempt:

        * Every tier fetches deaths, damage taken, enemy casts and interrupts.
          Nothing below the mechanics and interrupts tabs is optional.
        * `death_cards` adds the aura tables, one call a roster player. This is
          what refines a defensive press into `held` or `faded`; without it all
          six availability states collapse back to `pressed`, the explicit
          unknown, and a card drawing six states would only ever reach one.
        * `deep_fights` adds the casts stream -- which is also the health
          column, since `build_health_samples` reads it -- and one healing
          window a death, for the named fights alone.

        The two dear halves, measured on one 65.19-point wipe: the aura tables
        were 20.00 of it and the healing windows 22.00. A night holds many more
        pulls than a raid command's one, so paying either on every pull is the
        difference between a night that fits the hourly budget and one that
        does not.

        `deep_fights` is read once per attempt rather than once for the night:
        a `--deep` that leaked would put every pull at the dearest tier, which
        is the whole night at the price the flag exists to charge for one.

        Returns before fetching anything when no boss has a qualifying attempt:
        an ability dictionary nothing would read is a point spent for no
        reason. The bosses still come back, each with an empty
        `LoadedProgression`, because a boss that was only ever reset is still a
        boss this report holds.
        """
        if not any(boss.attempts for boss in night.bosses):
            return LoadedNight(
                night=night,
                loaded=tuple(LoadedProgression(progression=boss) for boss in night.bosses),
            )

        hits: list[bool] = []
        # Both halves, where `load_progression_attempts` keeps only the names:
        # a night's death cards and ledger rows draw ability icons, and one
        # query answers the whole report however many pulls read it.
        ability_names, ability_icons = self._ability_dictionary(night.report_code, hits)

        def query(one_query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return self._query(one_query, variables, hits)

        loaded: list[LoadedProgression] = []
        failures: list[FailedPull] = []
        for boss in night.bosses:
            deepened: list[LoadedEncounter] = []
            for attempt in boss.attempts:
                try:
                    deepened.append(
                        self._deepen_attempt(
                            attempt,
                            query,
                            ability_names,
                            ability_icons,
                            deep=attempt.fight_id in deep_fights,
                            death_cards=death_cards,
                        )
                    )
                except RateLimitExceeded:
                    # Not this pull's failure but every remaining pull's, so it
                    # stops the night instead of being recorded once per pull
                    # under a cause that would be true of none of them.
                    # `_affix_names` lets it through for the same reason.
                    raise
                except (ValueError, WclError, httpx.HTTPError, OSError) as error:
                    # The tuple the `progression` command treats as a load
                    # failure, caught per attempt rather than per night: one
                    # pull that cannot be read shrinks the night, and the
                    # record below is what keeps the shrinking from being
                    # silent.
                    failures.append(FailedPull(fight_id=attempt.fight_id, reason=str(error)))
            loaded.append(LoadedProgression(progression=boss, loaded=tuple(deepened)))

        return LoadedNight(night=night, loaded=tuple(loaded), failed_pulls=tuple(failures))

    def _deepen_attempt(
        self,
        attempt: Encounter,
        query: Execute,
        ability_names: dict[int, str],
        ability_icons: tuple[tuple[int, str], ...],
        *,
        deep: bool,
        death_cards: bool,
    ) -> LoadedEncounter:
        """One pull's streams, at the tier `deep` and `death_cards` place it on.

        Every stream this skips leaves an empty tuple behind, which reads the
        same as "this pull had none" -- the shape `load_speed_reference` and
        `load_parse_reference` leave behind for the streams their own axes do
        not read. Nothing may report absence off a trimmed tier without
        knowing which tier it was fetched at, or it would state as a finding
        what is only a stream nobody paid for.
        """
        # The tiers are a ladder, so the deep one reaches everything the
        # trimmed one does. A fight named deep is a request for that pull's
        # whole anatomy, which outranks a night-wide "no cards".
        cards = death_cards or deep

        event_variables = {
            "code": attempt.report_code,
            "fightId": attempt.fight_id,
            "startTime": float(attempt.start_ms),
            "endTime": float(attempt.end_ms),
        }
        # A boss fight carries no pulls at all, so every builder below indexes
        # its events against an empty route -- `pull_index_at` answers None
        # over one, which is the right answer for an event that is never
        # inside or outside a pull.
        no_pulls: tuple[Pull, ...] = ()

        # One stream, two readings: the casts themselves and the health column
        # `build_health_samples` reads out of them. Below the deep tier
        # `build_deaths` gets an empty one, which costs only its reading of how
        # long a death kept the player out.
        cast_events = fetch_all_events(query, CASTS_QUERY, event_variables) if deep else []
        casts = build_casts(cast_events, no_pulls, ability_names)

        player_names = {player.actor_id: player.name for player in attempt.players}
        deaths = build_deaths(
            fetch_all_events(query, DEATHS_QUERY, event_variables),
            no_pulls,
            casts,
            player_names,
            ability_names,
        )
        damage_taken = build_damage_taken(
            fetch_all_events(query, DAMAGE_TAKEN_QUERY, event_variables),
            no_pulls,
            ability_names,
        )
        enemy_cast_rows = build_enemy_cast_rows(
            fetch_all_events(query, ENEMY_CASTS_QUERY, event_variables),
            no_pulls,
            ability_names,
        )
        interrupts = build_interrupts(
            fetch_all_events(query, INTERRUPTS_QUERY, event_variables),
            no_pulls,
            player_names,
        )

        auras: tuple[PlayerAuras, ...] = ()
        if cards:
            auras = tuple(
                build_player_auras(
                    query(
                        AURA_TABLE_QUERY,
                        {
                            "code": attempt.report_code,
                            "fightId": attempt.fight_id,
                            "actorId": player.actor_id,
                        },
                    ),
                    player.actor_id,
                )
                for player in attempt.players
            )

        # One healing window per stretch of run-ups, scoped to the dying
        # player, exactly as `load_encounter` fetches it.
        healing: list[HealingEvent] = []
        if deep:
            for actor_id, start, end in healing_windows(deaths):
                scoped = {
                    "code": attempt.report_code,
                    "fightId": attempt.fight_id,
                    "actorId": actor_id,
                    "startTime": float(start),
                    "endTime": float(end),
                }
                healing.extend(
                    build_healing(fetch_all_events(query, HEALING_QUERY, scoped), ability_names)
                )

        return LoadedEncounter(
            encounter=attempt,
            casts=casts,
            deaths=deaths,
            enemy_cast_rows=enemy_cast_rows,
            interrupts=interrupts,
            damage_taken=damage_taken,
            health_samples=build_health_samples(cast_events),
            healing=tuple(healing),
            auras=auras,
            ability_icons=ability_icons,
        )

    def load_speed_reference(
        self, report_code: str, fight_id: int | None
    ) -> tuple[LoadedRun, bool]:
        """Only the streams a speed comparison reads off a reference run: run, deaths,
        enemy casts and interrupts.

        Casts are not fetched. `build_deaths` still takes a cast stream to time
        how long a death kept the player out of the fight, but an empty one only
        costs that one reading (`Death.seconds_until_next_action`), which no
        speed comparison reads — route, tempo and confounds count
        `len(member.deaths)`, nothing finer. Talents are not fetched either:
        none of those three read a player's build.

        The fields left behind are empty tuples, which read the same as "this
        run had none". Nothing consults them today; a comparison that started
        to would be reading absence as fact, and must call `load` instead.
        `SpeedMember` carries no field for them at all, so that mistake cannot
        be made.

        The second element is true only when every query this reference took
        was served from the cache, so a caller can tell a reused reference from
        one that was actually fetched.
        """
        return self._load(report_code, fight_id, profile="speed")

    def load_parse_reference(
        self, report_code: str, fight_id: int | None
    ) -> tuple[LoadedRun, bool]:
        """Only the streams a parse comparison reads off a reference run: run and casts.

        Talents are fetched even though neither `LoadedRun` nor `ParseMember`
        names a field for them: they ride inside `run.players[].talent_import_string`,
        and that roster is carried onto the member as `players`, where
        `compare_talents` finds the top parse's own player and names the build a
        reader should copy. Skipping the query would not remove a field nothing
        reads — it would make the one thing that does read it silently report
        every build as absent.

        Deaths, enemy casts and interrupts are not fetched. The fields left
        behind are empty tuples, which read the same as "this run had none".
        Nothing consults them today; a comparison that started to would be
        reading absence as fact, and must call `load` instead. `ParseMember`
        carries no field for them at all, so that mistake cannot be made.

        The second element is true only when every query this reference took
        was served from the cache, so a caller can tell a reused reference from
        one that was actually fetched.
        """
        return self._load(report_code, fight_id, profile="parse")

    def load_raid_parse_reference(
        self, report_code: str, fight_id: int
    ) -> tuple[RaidReference, bool]:
        """Only the streams a raid parse comparison reads off a reference kill.

        A sibling of `load_parse_reference`, not a profile of it: that path
        selects a keystone fight and would refuse a boss fight outright, and the
        `Run` it assembles has no raid meaning. This selects the boss fight the
        leaderboard row named, and returns the three values a `ParseMember`
        carries -- nothing else is fetched, so nothing else can be read as fact.

        Talents are fetched for the reason `load_parse_reference` gives: they
        ride inside `players[].talent_import_string`, and `compare_talents` names
        the build a reader is invited to copy. `fight_id` is required rather than
        optional, because a leaderboard row always names one and a raid report
        holding several boss fights has no default to fall back on.

        The second element is true only when every query this reference took was
        served from the cache, so a caller can tell a reused reference from one
        that was actually fetched.
        """
        hits: list[bool] = []
        report = self._report(report_code, hits)
        fight = select_raid_fight(report["fights"], fight_id)
        talents = self._talents(report_code, fight, hits)
        # No loadouts: `playerDetails` costs 2.00 points a fight and the only
        # thing that reads it off a reference is the gear half of the spell
        # comparison, which widens its own wording when a loadout is absent.
        players = build_raid_roster(report, fight, talents)

        ability_names, ability_icons = self._ability_dictionary(report_code, hits)

        cast_events = fetch_all_events(
            lambda one_query, variables: self._query(one_query, variables, hits),
            CASTS_QUERY,
            {
                "code": report_code,
                "fightId": fight["id"],
                "startTime": float(fight["startTime"]),
                "endTime": float(fight["endTime"]),
            },
        )
        # A boss fight carries no pulls, so every cast is indexed against an
        # empty route -- which `whole_fight_casts` is the rule for.
        no_pulls: tuple[Pull, ...] = ()
        return (
            RaidReference(
                players=players,
                casts=build_casts(cast_events, no_pulls, ability_names),
                ability_icons=ability_icons,
            ),
            all(hits),
        )

    def _load(
        self, report_code: str, fight_id: int | None, *, profile: _Profile
    ) -> tuple[LoadedRun, bool]:
        hits: list[bool] = []
        report = self._report(report_code, hits)
        fight = select_keystone_fight(report["fights"], fight_id)
        # Route, tempo and confounds never read a player's talent build, so a
        # speed reference leaves the aliased per-player talentImportCode query
        # unfetched; build_run accepts no talents just as readily as some.
        talents = {} if profile == "speed" else self._talents(report_code, fight, hits)
        loadouts = {} if profile == "speed" else self._loadouts(report_code, fight, hits)
        run = build_run(report, fight, talents, loadouts)
        run = run.model_copy(update={"affix_names": self._affix_names(run.affix_ids, hits)})

        ability_names, ability_icons = self._ability_dictionary(report_code, hits)

        event_variables = {
            "code": report_code,
            "fightId": run.fight_id,
            "startTime": float(fight["startTime"]),
            "endTime": float(fight["endTime"]),
        }

        def query(one_query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return self._query(one_query, variables, hits)

        if profile == "parse":
            cast_events = fetch_all_events(query, CASTS_QUERY, event_variables)
            loaded = LoadedRun(
                run=run,
                casts=build_casts(cast_events, run.pulls, ability_names),
                ability_icons=ability_icons,
            )
            return loaded, all(hits)

        death_events = fetch_all_events(query, DEATHS_QUERY, event_variables)
        enemy_cast_events = fetch_all_events(query, ENEMY_CASTS_QUERY, event_variables)
        interrupt_events = fetch_all_events(query, INTERRUPTS_QUERY, event_variables)
        # A speed reference never fetches its own cast stream either, even
        # though build_deaths below takes one: it only uses it to time how long
        # a death kept the player out (seconds_until_next_action), a reading no
        # speed comparison reads. An empty tuple costs that one reading and
        # nothing else.
        cast_events = (
            fetch_all_events(query, CASTS_QUERY, event_variables) if profile == "full" else []
        )
        casts = build_casts(cast_events, run.pulls, ability_names)
        player_names = {player.actor_id: player.name for player in run.players}
        deaths = build_deaths(death_events, run.pulls, casts, player_names, ability_names)
        enemy_cast_rows = build_enemy_cast_rows(enemy_cast_events, run.pulls, ability_names)
        interrupts = build_interrupts(interrupt_events, run.pulls, player_names)

        if profile == "speed":
            loaded = LoadedRun(
                run=run,
                deaths=deaths,
                enemy_cast_rows=enemy_cast_rows,
                interrupts=interrupts,
                ability_icons=ability_icons,
            )
            return loaded, all(hits)

        enemy_death_events = fetch_all_events(query, ENEMY_DEATHS_QUERY, event_variables)
        damage_taken_events = fetch_all_events(query, DAMAGE_TAKEN_QUERY, event_variables)
        # Pre-aggregated by the API, so one call rather than a paginated stream.
        # One response carries a series for every player, which is why widening
        # to the whole roster costs nothing more here.
        damage_done = build_damage_done(query(DAMAGE_DONE_GRAPH_QUERY, event_variables))
        resurrections = build_resurrections(
            fetch_all_events(query, RESURRECTS_QUERY, event_variables), ability_names
        )
        actor_game_ids = self._actor_game_ids(report_code, hits)
        enemy_deaths = build_enemy_deaths(
            enemy_death_events, run, actor_game_ids, dict(run.npc_count_map)
        )
        damage_taken = build_damage_taken(damage_taken_events, run.pulls, ability_names)

        # One healing window per stretch of run-ups, scoped to the dying player.
        # Resurrections are fetched once above, fight-wide, because the All
        # stream ignores `targetID` while a server-side filter on
        # `type = 'resurrect'` costs one point for the whole fight rather than
        # one point per death.
        healing: list[HealingEvent] = []
        for actor_id, start, end in healing_windows(deaths):
            scoped = {
                "code": report_code,
                "fightId": run.fight_id,
                "actorId": actor_id,
                "startTime": float(start),
                "endTime": float(end),
            }
            healing.extend(
                build_healing(fetch_all_events(query, HEALING_QUERY, scoped), ability_names)
            )

        loaded = LoadedRun(
            run=run,
            casts=casts,
            deaths=deaths,
            enemy_cast_rows=enemy_cast_rows,
            interrupts=interrupts,
            enemy_deaths=enemy_deaths,
            damage_taken=damage_taken,
            damage_done=damage_done,
            health_samples=build_health_samples(cast_events),
            healing=tuple(healing),
            resurrections=resurrections,
            ability_icons=ability_icons,
        )
        return loaded, all(hits)

    def auras(self, report_code: str, fight_id: int, actor_id: int) -> PlayerAuras:
        """Buff uptime for one player of one fight.

        Scoped rather than folded into `load`: an aura table is per-actor, so
        loading them for a whole roster would pay for ten tables to answer a
        question about two players. Only what the player carried is asked for:
        no query argument narrows the enemy-debuff table to one caster, so the
        matching figure for enemies does not exist — the measured table is in
        `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to
        one caster".
        """
        payload = self._query(
            AURA_TABLE_QUERY,
            {"code": report_code, "fightId": fight_id, "actorId": actor_id},
        )
        return build_player_auras(payload, actor_id)
