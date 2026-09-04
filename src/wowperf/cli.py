# ABOUTME: Command-line entry point; the driving adapter that wires ports to implementations.
# ABOUTME: Holds no analysis logic, only construction, argument handling and output.

import json
import os
import sys
from pathlib import Path

import httpx
import typer

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.analysis.service import analyse
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
    except (ValueError, WclError, httpx.HTTPError) as error:
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


@app.command()
def analyze(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings file"),
) -> None:
    """Analyse a Mythic+ run and write its findings as JSON."""
    # See the matching comment on `fetch`: Windows gives the process a
    # locale-dependent stdout encoding that cannot hold non-ASCII names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        loaded = repository.load(code, fight if fight is not None else fight_from_url)
        findings = analyse(loaded, load_season_data(), load_defensives())
    except (ValueError, WclError, httpx.HTTPError) as error:
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
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }

    out.mkdir(parents=True, exist_ok=True)
    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    # Real rosters contain non-ASCII names; write_text's default encoding is
    # locale-dependent (commonly cp1252 on Windows) and would raise on them.
    written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"{len(findings)} findings written to {written}")


if __name__ == "__main__":
    app()
