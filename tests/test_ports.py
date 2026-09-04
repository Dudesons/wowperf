# ABOUTME: Proves the fake repository satisfies the port that adapters must also satisfy.
# ABOUTME: Keeps later plans honest: if the port changes, the fake breaks here first.

import pytest

from tests.domain.test_model import a_run
from tests.fakes import InMemoryRunRepository
from wowperf.domain.ports import RunRepository


def test_the_in_memory_repository_satisfies_the_run_repository_port() -> None:
    run = a_run(())
    repository: RunRepository = InMemoryRunRepository({("abc123", 1): run})
    assert repository.get("abc123", 1) is run


def test_an_unknown_report_raises_a_key_error_naming_the_code() -> None:
    repository = InMemoryRunRepository({})
    with pytest.raises(KeyError, match="missing"):
        repository.get("missing", 1)
