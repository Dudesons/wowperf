# ABOUTME: Command-line entry point; the driving adapter that wires ports to implementations.
# ABOUTME: Holds no analysis logic, only construction, argument handling and output.

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import typer

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.adapters.render.html import render
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.reference import ParseReference, SpeedReference
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import Player, Run
from wowperf.domain.report.build import build_report
from wowperf.urls import parse_report_url

app = typer.Typer(help="Analyse World of Warcraft logs and report what to improve.")

DEFAULT_CACHE_DIR = Path("cache")


@app.callback()
def main() -> None:
    """Analyse World of Warcraft logs and report what to improve.

    Typer collapses a single-command app into a bare invocation; this callback
    keeps `fetch` addressable as a subcommand even before later plans add more.
    """


def build_repository(cache_dir: Path) -> WclRunRepository:
    client_id = os.environ.get("WCL_CLIENT_ID")
    client_secret = os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise typer.BadParameter(
            "Set WCL_CLIENT_ID and WCL_CLIENT_SECRET. "
            "Create a client at https://www.warcraftlogs.com/api/clients/"
        )

    http = httpx.Client(timeout=60.0)
    return WclRunRepository(
        WclClient(TokenProvider(client_id, client_secret, http), http),
        DiskCache(cache_dir),
    )


@app.command()
def fetch(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
) -> None:
    """Fetch a Mythic+ run and print it as JSON."""
    # Windows gives the process a locale-dependent stdout encoding (commonly cp1252),
    # which cannot hold the non-ASCII player names and dungeon names real reports
    # contain. Reconfigure to UTF-8 so the JSON reaches stdout intact instead of
    # crashing with a UnicodeEncodeError after the API quota has already been spent.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)

        # Point cost per query is undocumented, so this reads the quota before and
        # after the fetch. The reading itself is a query too, so the difference
        # also counts the cost of these two quota reads, not only the fetch.
        before = repository.rate_limit()
        run = repository.get(code, fight if fight is not None else fight_from_url)
        after = repository.rate_limit()
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        # IngestError subclasses ValueError. Anything else keeps its traceback,
        # because an unexpected failure is a bug and should look like one.
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    spent = after.points_spent_this_hour - before.points_spent_this_hour
    remaining = after.limit_per_hour - after.points_spent_this_hour
    typer.echo(
        f"Rate limit: {spent:.2f} points spent, including the cost of these two "
        f"quota reads themselves; {remaining:.2f} of {after.limit_per_hour} remain this hour.",
        err=True,
    )
    typer.echo(run.model_dump_json(indent=2))


def _resolve_player(run: Run, requested: str | None) -> Player:
    """Whose run this is, for the individual comparison.

    The report owner is the default because it is the only name the log itself
    volunteers. Warcraft Logs lowercases it, so the match folds case.
    """
    name = requested or run.owner_name
    if name is not None:
        found = find_player(run, name)
        if found is not None:
            return found

    roster = ", ".join(sorted(player.name for player in run.players)) or "nobody"
    raise ValueError(
        f"{name!r} is not in this run's roster. Pass --player with one of: {roster}"
    )


def _references(
    rankings: WclRankingRepository,
    runs: WclRunRepository,
    run: Run,
    subject: Player,
) -> tuple[SpeedReference | None, ParseReference | None]:
    """The two reference runs, or None where the leaderboard had nothing to offer.

    A candidate row whose report fails to load — deleted, private, an
    unfinished fight, or a roster gap in its master data — is skipped rather
    than fatal: falling through to the next row (and to None once the
    leaderboard is exhausted) keeps a broken reference from discarding the
    findings already computed for the run under analysis. The leaderboard
    query itself is not guarded here: a `BracketMismatch` there means the
    bracket convention this tool relies on has changed, and that must still
    stop the command.
    """
    speed = None
    for row in rankings.fastest_runs(run.encounter_id, run.keystone_level):
        # Comparing a run against itself would report a perfect route and teach
        # the reader nothing.
        if row.report_code == run.report_code and row.fight_id == run.fight_id:
            continue
        try:
            loaded = runs.load(row.report_code, row.fight_id)
        except (IngestError, WclError):
            continue
        speed = SpeedReference(row=row, loaded=loaded)
        break

    parse = None
    for parse_row in rankings.top_parses(
        run.encounter_id, run.keystone_level, subject.class_name, subject.spec
    ):
        if parse_row.report_code == run.report_code and parse_row.fight_id == run.fight_id:
            continue
        try:
            loaded = runs.load(parse_row.report_code, parse_row.fight_id)
        except (IngestError, WclError):
            continue
        parse = ParseReference(row=parse_row, loaded=loaded)
        break

    return speed, parse


def _auras(runs: WclRunRepository, code: str, fight_id: int, actor_id: int) -> PlayerAuras | None:
    """One player's auras, or None if they cannot be had.

    A failed aura fetch must not discard the whole report: everything else has
    already been fetched and paid for, and `compare.uptime.unavailable` states
    the gap rather than hiding it. `httpx.HTTPError` covers a non-2xx aura
    response that is not itself a rate limit: `WclClient.execute` raises
    `RateLimitExceeded` (a `WclError`) for 429 before it ever calls
    `raise_for_status`, so that deliberate handling still goes through the
    `WclError` branch above and is untouched by the wider catch here.
    """
    try:
        return runs.auras(code, fight_id, actor_id)
    except (IngestError, WclError, httpx.HTTPError):
        return None


@app.command()
def analyze(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    player: str | None = typer.Option(
        None, help="Subject of the individual comparison; defaults to the report owner"
    ),
    no_compare: bool = typer.Option(
        False, "--no-compare", help="Skip both reference runs and analyse in isolation"
    ),
    narrative: Path | None = typer.Option(
        None, help="Markdown notes to render as the report's interpretation section"
    ),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings file"),
) -> None:
    """Analyse a Mythic+ run and write its findings as JSON and an HTML report."""
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        # Read this before anything is fetched: a typo in the path must cost
        # nothing, and must never quietly produce a report with no narrative.
        narrative_text = None
        if narrative:
            try:
                narrative_text = narrative.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                # UnicodeDecodeError's own message never names the file it came
                # from, so a bad-encoding narrative would otherwise print a
                # codec complaint with no way to tell which path caused it.
                raise ValueError(f"{narrative}: {error}") from error

        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        loaded = repository.load(code, fight if fight is not None else fight_from_url)
        findings = analyse(loaded, load_season_data(), load_defensives())

        subject = _resolve_player(loaded.run, player)
        speed: SpeedReference | None = None
        parse: ParseReference | None = None
        if not no_compare:
            rankings = WclRankingRepository(repository.client, repository.cache)
            speed, parse = _references(rankings, repository, loaded.run, subject)

            our_auras = None
            if parse is not None:
                # Resolve the counterpart before paying for our own aura fetch: when
                # the reference's own roster does not contain the player the
                # leaderboard row names, find_player can never resolve them, and
                # fetching our side first would pay for a query with no use once
                # that failure is discovered.
                their_player = find_player(parse.loaded.run, parse.row.character_name)
                if their_player is not None:
                    our_auras = _auras(
                        repository, loaded.run.report_code, loaded.run.fight_id, subject.actor_id
                    )
                    parse = parse.model_copy(
                        update={
                            "auras": _auras(
                                repository,
                                parse.loaded.run.report_code,
                                parse.loaded.run.fight_id,
                                their_player.actor_id,
                            )
                        }
                    )

            findings += compare(
                ours=loaded, our_player=subject, speed=speed, parse=parse, our_auras=our_auras
            )
            findings = rank_findings(findings)
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    run = loaded.run
    payload = {
        "report_code": run.report_code,
        "fight_id": run.fight_id,
        "dungeon_name": run.dungeon_name,
        "keystone_level": run.keystone_level,
        "keystone_time_seconds": run.keystone_time_seconds,
        "in_time": run.keystone_bonus >= 1,
        "player": subject.name,
        "comparison": {
            "compared": speed is not None or parse is not None,
            "speed_reference": (
                {
                    "report_code": speed.row.report_code,
                    "fight_id": speed.row.fight_id,
                    "keystone_level": speed.row.keystone_level,
                    "duration_seconds": speed.row.duration_seconds,
                    "medal": speed.row.medal,
                }
                if speed
                else None
            ),
            "parse_reference": (
                {
                    "report_code": parse.row.report_code,
                    "fight_id": parse.row.fight_id,
                    "keystone_level": parse.row.keystone_level,
                    "character_name": parse.row.character_name,
                    "class_name": parse.row.class_name,
                    "spec": parse.row.spec,
                    "medal": parse.row.medal,
                }
                if parse
                else None
            ),
        },
        "findings_are_ranked_not_additive": (
            "findings are ranked by seconds_lost, not additive: compare.duration is the "
            "total gap against the reference and already contains every other seconds_lost "
            "figure in this report; time.gap.* and compare.downtime both nest inside "
            "time.residual; deaths.single/chain/repeat.* nest inside deaths.total; and "
            "compare.route.skipped.* overlaps the waste trash.overage already reports"
        ),
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }

    out.mkdir(parents=True, exist_ok=True)
    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    # Real rosters contain non-ASCII names; write_text's default encoding is
    # locale-dependent (commonly cp1252 on Windows) and would raise on them.
    written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"{len(findings)} findings written to {written}")

    report_file = out / f"{run.report_code}-{run.fight_id}.html"
    report_file.write_text(
        render(
            build_report(
                loaded,
                findings,
                speed,
                parse,
                subject,
                narrative_text,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        ),
        encoding="utf-8",
    )
    typer.echo(f"report written to {report_file}")


if __name__ == "__main__":
    app()
