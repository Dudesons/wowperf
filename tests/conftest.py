# ABOUTME: Shared pytest configuration. Currently only the golden-file update flag.
# ABOUTME: Regenerating a golden file is a deliberate act, so it needs a deliberate flag.

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--golden-update",
        action="store_true",
        default=False,
        help="Rewrite golden files from the current output. Read the diff first.",
    )
