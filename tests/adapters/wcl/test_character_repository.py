# ABOUTME: Behaviour tests for fetching a zone and a character's ranked runs through the cache.
# ABOUTME: Pins the variables the API receives and that a second read comes from disk.

import json
from pathlib import Path
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.character_repository import WclCharacterRepository
from wowperf.adapters.wcl.client import WclClient
from wowperf.domain.character.model import Dungeon, Zone

TOKEN = {"access_token": "t", "expires_in": 86400}
ZONE = Zone(zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,),
            dungeons=(Dungeon(encounter_id=101, name="Den of Nalorakk"),))


def repository(tmp_path: Path, bodies: list[dict[str, Any]]) -> WclCharacterRepository:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        bodies.append(body)
        if "zoneId" in body["variables"]:
            return httpx.Response(200, json={"data": {"worldData": {"zone": {
                "id": 55, "name": "Mythic+ Season 2",
                "difficulties": [{"id": 10, "name": "Dungeon"}],
                "encounters": [{"id": 101, "name": "Den of Nalorakk"}]}}}})
        return httpx.Response(200, json={"data": {"characterData": {"character": {
            "id": 1, "hidden": False, "e101": {"ranks": []}}}}})

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    return WclCharacterRepository(WclClient(TokenProvider("id", "secret", http), http),
                                  DiskCache(tmp_path))


def test_the_zone_is_asked_for_by_id(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    assert repository(tmp_path, bodies).zone(55) == ZONE
    assert bodies[0]["variables"] == {"zoneId": 55}


def test_the_character_is_asked_for_by_name_realm_and_region(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    runs = repository(tmp_path, bodies).ranked_runs("Emberkin", "argent-dawn", "eu", ZONE)

    assert runs == ()
    assert bodies[0]["variables"] == {
        "name": "Emberkin", "serverSlug": "argent-dawn", "serverRegion": "eu"
    }
    assert "e101: encounterRankings(encounterID: 101)" in bodies[0]["query"]


def test_a_second_read_is_served_from_the_cache(tmp_path: Path) -> None:
    bodies: list[dict[str, Any]] = []
    characters = repository(tmp_path, bodies)
    characters.zone(55)
    characters.zone(55)
    assert len(bodies) == 1
