# ABOUTME: The Warcraft Logs adapter's error hierarchy, in its own module so auth can raise it.
# ABOUTME: Lives below client and auth to keep the import graph acyclic.


class WclError(RuntimeError):
    """The API answered, but not with data we can use."""
