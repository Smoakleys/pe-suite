"""Project-timezone helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Project


def project_now(project: Project) -> datetime:
    """Return the current time in the project's configured timezone.

    Falls back to the host local timezone if the configured IANA timezone is
    unavailable. Validation/UI can surface invalid timezone values later; this
    helper keeps save/export paths resilient.
    """
    try:
        return datetime.now(ZoneInfo(project.project.timezone))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()
