# ABOUTME: Behaviour tests for turning a route alignment into findings a reader can act on.
# ABOUTME: The headline is what a faster group skipped, priced with our own clock.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.route import MAX_PACKS_REPORTED, compare_route
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(
    index: int, game_ids: tuple[int, ...], seconds: float = 60.0, boss: bool = False
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Boss" if boss else "Pack",
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=100 + index,
        y=200 + index,
        enemies=tuple(
            EnemyNpc(actor_id=100 + n, game_id=game_id) for n, game_id in enumerate(game_ids)
        ),
    )


def a_run(pulls: tuple[Pull, ...], counts: tuple[tuple[int, int], ...] = ()) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=counts,
        players=(),
        pulls=pulls,
    )


def findings_by_prefix(findings: list[Finding], prefix: str) -> list[Finding]:
    return [finding for finding in findings if finding.id.startswith(prefix)]


def test_a_pack_they_skipped_is_priced_with_our_own_clock() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))),
                 counts=((2, 12),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert len(skipped) == 1
    assert skipped[0].seconds_lost == 45.0
    assert skipped[0].confidence is Confidence.MEASURED
    assert skipped[0].pull_index == 1
    assert any("12" in line for line in skipped[0].evidence)


def test_a_boss_is_never_reported_as_a_skipped_pack() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))
    theirs = a_run((a_pull(0, (1,)),))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))

    assert findings_by_prefix(findings, "compare.route.skipped.") == []


def test_a_boss_is_never_reported_as_an_extra_pack() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))

    assert findings_by_prefix(findings, "compare.route.extra.") == []


def test_a_pack_only_they_killed_carries_no_seconds() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert len(extra) == 1
    assert extra[0].seconds_lost is None


def test_the_summary_counts_both_routes() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (1,)),))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.summary")[0]

    assert "2" in summary.title
    assert "1" in summary.title
    assert summary.seconds_lost is None


def test_only_the_worst_packs_are_reported() -> None:
    # Eight packs they skipped, each one second shorter than the last.
    skipped_pulls = tuple(
        a_pull(index, (index + 10,), seconds=float(60 - index)) for index in range(1, 9)
    )
    ours = a_run((a_pull(0, (1,)), *skipped_pulls))
    theirs = a_run((a_pull(0, (1,)),))

    skipped = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.skipped.")

    assert len(skipped) == MAX_PACKS_REPORTED
    seconds = [finding.seconds_lost for finding in skipped]

    def as_sortable(value: float | None) -> float:
        return value if value is not None else float("-inf")

    assert seconds == sorted(seconds, key=as_sortable, reverse=True)


def test_a_reordered_route_is_reported_once() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                               "compare.route.order")

    assert len(order) <= 1


def test_identical_routes_report_only_the_summary() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, ours, align_pulls(ours, ours))

    assert [finding.id for finding in findings] == ["compare.route.summary"]


def test_every_finding_id_is_unique() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    ids = [finding.id for finding in compare_route(ours, theirs, align_pulls(ours, theirs))]

    assert len(ids) == len(set(ids))
