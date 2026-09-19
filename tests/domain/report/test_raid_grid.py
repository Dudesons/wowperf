# ABOUTME: Behaviour tests for the per-player damage grid: what it shows and what it may claim.
# ABOUTME: A tint is a finding's existence, never a threshold this table recomputed.

from wowperf.domain.analysis.damage_outliers import damage_outliers
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.raid_grid import MAX_GRID_COLUMNS, build_raid_grid
from wowperf.domain.season import Roles


def _player(actor_id: int, class_name: str = "Mage", spec: str = "Frost") -> Player:
    return Player(
        actor_id=actor_id,
        name=f"Raider {actor_id}",
        class_name=class_name,
        spec=spec,
        item_level=690,
    )


def _hit(*, actor_id: int, ability_id: int, amount: int, name: str) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        amount=amount,
        timestamp_ms=1000,
    )


def _ranked(ability_id: int, ability_name: str) -> Finding:
    """A `mechanics.ability.*` finding, which is what earns a column."""
    from wowperf.domain.findings import Confidence

    return Finding(
        id=f"mechanics.ability.{ability_id}",
        title=f"{ability_name} hit the raid",
        detail="",
        confidence=Confidence.DERIVED,
        ability_id=ability_id,
        ability_name=ability_name,
    )


ROSTER = (
    _player(1), _player(2), _player(3),
    _player(4, class_name="DeathKnight", spec="Blood"),
)
HITS = (
    _hit(actor_id=1, ability_id=11, amount=100, name="Caustic Waves"),
    _hit(actor_id=2, ability_id=11, amount=100, name="Caustic Waves"),
    _hit(actor_id=3, ability_id=11, amount=400, name="Caustic Waves"),
    _hit(actor_id=4, ability_id=11, amount=9000, name="Caustic Waves"),
)
RANKED = [_ranked(11, "Caustic Waves")]


def test_a_tinted_cell_always_has_a_finding_behind_it() -> None:
    """The grid may state nothing the page does not already say outright."""
    grid = build_raid_grid(ROSTER, HITS, Roles(), RANKED)
    assert grid is not None

    outliers = {
        (one.actor_id, one.ability_id) for one in damage_outliers(ROSTER, HITS, Roles())
    }
    for row, player in zip(grid.rows, ROSTER, strict=True):
        for cell in row.cells:
            assert cell.tinted == ((player.actor_id, cell.ability_id) in outliers), (
                f"{row.player_name} / {cell.ability_id}"
            )


def test_a_tank_row_is_present_and_never_tinted() -> None:
    """A roster table missing two people reads as a bug; a tinted tank reads as blame."""
    grid = build_raid_grid(ROSTER, HITS, Roles(tanks=("DeathKnight/Blood",)), RANKED)
    assert grid is not None

    [tank] = [row for row in grid.rows if row.player_name == "Raider 4"]
    assert tank.cells[0].amount == "9,000"
    assert tank.cells[0].multiple == "", "a tank has no median to be a multiple of"
    assert tank.cells[0].tinted is False


def test_a_player_who_took_none_of_an_ability_reads_zero() -> None:
    hits = HITS + (_hit(actor_id=1, ability_id=22, amount=50, name="Purge"),)
    findings = RANKED + [_ranked(22, "Purge")]

    grid = build_raid_grid(ROSTER, hits, Roles(), findings)
    assert grid is not None

    [second] = [row for row in grid.rows if row.player_name == "Raider 2"]
    purge = [cell for cell in second.cells if cell.ability_id == 22][0]
    assert purge.amount == "0"
    assert purge.multiple == ""


def test_the_columns_are_capped() -> None:
    hits = tuple(
        _hit(actor_id=1, ability_id=identifier, amount=100, name=f"Ability {identifier}")
        for identifier in range(1, 10)
    )
    findings = [_ranked(identifier, f"Ability {identifier}") for identifier in range(1, 10)]

    grid = build_raid_grid(ROSTER, hits, Roles(), findings)
    assert grid is not None
    assert len(grid.columns) == MAX_GRID_COLUMNS


def test_no_qualifying_column_yields_no_grid() -> None:
    """Nothing to say, said as nothing -- not an empty table with headings."""
    assert build_raid_grid(ROSTER, HITS, Roles(), []) is None


def test_the_caption_refuses_to_call_a_tint_a_mistake() -> None:
    grid = build_raid_grid(ROSTER, HITS, Roles(), RANKED)
    assert grid is not None
    for word in ("mistake", "avoidable", "should have", "failed"):
        assert word not in grid.caption.lower(), grid.caption
