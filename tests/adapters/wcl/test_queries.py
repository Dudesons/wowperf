# ABOUTME: Tests the quota block spliced into every operation, so each query reports its own cost.
# ABOUTME: A query the splice cannot parse must go out untouched rather than corrupted.

from wowperf.adapters.wcl import queries
from wowperf.adapters.wcl.queries import (
    AFFIXES_QUERY,
    FIGHTS_QUERY,
    PLAYER_DETAILS_QUERY,
    RATE_LIMIT_QUERY,
    operation_name,
    with_rate_limit,
)

BLOCK = "rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }"


def test_the_block_becomes_the_first_selection_of_a_query_taking_variables() -> None:
    spliced = with_rate_limit(FIGHTS_QUERY).strip().splitlines()

    assert spliced[0] == "query Fights($code: String!) {"
    assert spliced[1].strip() == BLOCK
    assert spliced[2].strip() == "reportData {"


def test_the_block_becomes_the_first_selection_of_a_query_taking_none() -> None:
    spliced = with_rate_limit(AFFIXES_QUERY).strip().splitlines()

    assert spliced[0] == "query Affixes {"
    assert spliced[1].strip() == BLOCK


def test_a_query_already_selecting_the_quota_is_left_alone() -> None:
    """Splicing a second copy in would be harmless but dishonest about the query."""
    assert with_rate_limit(RATE_LIMIT_QUERY) == RATE_LIMIT_QUERY


def test_an_operation_the_splice_cannot_recognise_goes_out_untouched() -> None:
    """Instrumentation must never be the reason a query stops working."""
    anonymous = "query { hello }"

    assert with_rate_limit(anonymous) == anonymous


def _every_query() -> dict[str, str]:
    """Every operation this module can send, the generated one included."""
    named = {
        name: value
        for name, value in vars(queries).items()
        if name.endswith("_QUERY") and isinstance(value, str)
    }
    named["talents_query"] = queries.talents_query([12, 7])
    return named


def test_every_query_in_the_module_carries_the_block_as_its_first_selection() -> None:
    """A query the splice misses is a query whose cost stays invisible.

    Three of these wrap their variable list over several lines, so "first
    selection" is read as "nothing but the operation's own opening brace comes
    before the block", not as a line number.
    """
    unspliced = {}
    for name, query in _every_query().items():
        if name == "RATE_LIMIT_QUERY":
            continue
        before, block, _ = with_rate_limit(query).partition(BLOCK)
        if not block or before.count("{") != 1 or not before.rstrip().endswith("{"):
            unspliced[name] = query.strip().splitlines()[0]

    assert unspliced == {}


def test_a_comment_that_looks_like_a_header_is_not_mistaken_for_the_operation() -> None:
    """Splicing at the comment would put the block outside any operation and
    break a query that was perfectly valid before we touched it."""
    query = "# query Bar {\nquery Foo { hello }"

    assert queries.operation_name(query) == "Foo"
    assert with_rate_limit(query) == f"# query Bar {{\nquery Foo {{\n  {BLOCK} hello }}"


def test_an_operation_with_no_recognisable_header_has_no_name() -> None:
    assert queries.operation_name("query { hello }") is None


def test_the_player_details_query_asks_for_combatant_info() -> None:
    # The flag defaults off, and without it combatantInfo comes back as an
    # empty list rather than an error, so a query missing it fails silently.
    # Measured 2026-09-14; see the wcl-api skill.
    assert "includeCombatantInfo: true" in PLAYER_DETAILS_QUERY


def test_the_player_details_query_is_named_for_its_operation() -> None:
    assert operation_name(PLAYER_DETAILS_QUERY) == "PlayerDetails"


def test_the_player_details_query_allows_an_unlisted_report() -> None:
    assert "allowUnlisted: true" in PLAYER_DETAILS_QUERY


def test_the_player_details_query_structure_is_correct() -> None:
    # Catches field-name typos like playerDetials, and variable-name mismatches
    # like $fightID instead of $fightId. Task 5 will call this with the exact
    # variable names declared here, so both are runtime failures against a
    # quota-limited API if they slip past tests.
    assert "playerDetails(fightIDs: [$fightId], includeCombatantInfo: true)" in PLAYER_DETAILS_QUERY
