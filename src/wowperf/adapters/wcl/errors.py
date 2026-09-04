# ABOUTME: The Warcraft Logs adapter's error hierarchy, in its own module so auth can raise it.
# ABOUTME: Lives below client and auth to keep the import graph acyclic.


class WclError(RuntimeError):
    """The API answered, but not with data we can use."""


class BracketMismatch(WclError):
    """The leaderboard bracket did not mean what the tool assumed it means.

    `bracket = keystoneLevel - 1` is a community convention that appears in no
    documentation. If it ever changes, every reference run silently becomes the
    wrong one, so the tool stops instead.
    """
