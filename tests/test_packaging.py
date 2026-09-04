# ABOUTME: Proves the package is installed and importable before any real code depends on it.
# ABOUTME: A failure here means the uv environment is wrong, not that a feature is broken.

import wowperf


def test_package_exposes_a_version() -> None:
    assert wowperf.__version__ == "0.1.0"
