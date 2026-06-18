"""Read-only client the UI uses to talk to the fetch store.

This is the UI's only window into fetched data: it *reads* the hidden SQLite store for
instant display and *triggers* refreshes by spawning the fetch runner as a separate
process (view-driven). It never fetches in-process — Playwright and friends stay out of
the Qt process entirely.
"""

from .client import FetchClient

__all__ = ["FetchClient"]
