"""Location enum, default work-weeks, and holiday-library seed mapping.

The 8-location closed enum for v1. Work-weeks are USA-perspective: sites operating
in UTC+8 or later are modeled as Sun-Thu because their local Friday work has
completed before the USA team's Friday workday begins. See DESIGN.md for rationale.
"""

from __future__ import annotations

from typing import Final

LOCATIONS: Final[list[str]] = [
    "DAL",
    "FR-BIP",
    "MLA",
    "TIEMA",
    "CLARK",
    "TIPI",
    "TAI",
    "AIZU",
]

LOCATION_DISPLAY: Final[dict[str, str]] = {
    "DAL": "Dallas, USA",
    "FR-BIP": "Freising, Germany",
    "MLA": "Kuala Lumpur, Malaysia",
    "TIEMA": "Melaka, Malaysia",
    "CLARK": "Clark, Philippines",
    "TIPI": "Baguio, Philippines",
    "TAI": "Taiwan",
    "AIZU": "Aizu, Japan",
}

DEFAULT_WORK_WEEKS: Final[dict[str, list[str]]] = {
    "DAL":    ["MON", "TUE", "WED", "THU", "FRI"],
    "FR-BIP": ["MON", "TUE", "WED", "THU", "FRI"],
    "MLA":    ["SUN", "MON", "TUE", "WED", "THU"],
    "TIEMA":  ["SUN", "MON", "TUE", "WED", "THU"],
    "CLARK":  ["SUN", "MON", "TUE", "WED", "THU"],
    "TIPI":   ["SUN", "MON", "TUE", "WED", "THU"],
    "TAI":    ["SUN", "MON", "TUE", "WED", "THU"],
    "AIZU":   ["SUN", "MON", "TUE", "WED", "THU"],
}


def seed_holidays(location: str, year_start: int, year_end: int) -> list[dict]:
    """Seed holiday entries for a location from the Python `holidays` library.

    Returns a list of {date, name, source: "seeded"} dicts for the given year range.
    Falls back to an empty list if the holidays library is unavailable or the
    location maps to no recognized country.
    """
    try:
        import holidays as _h
    except ImportError:
        return []

    library_mapping = {
        "DAL":    lambda: _h.US(years=range(year_start, year_end + 1)),
        "FR-BIP": lambda: _h.Germany(subdiv="BY", years=range(year_start, year_end + 1)),
        "MLA":    lambda: _h.Malaysia(subdiv="KUL", years=range(year_start, year_end + 1)),
        "TIEMA":  lambda: _h.Malaysia(subdiv="MLK", years=range(year_start, year_end + 1)),
        "CLARK":  lambda: _h.Philippines(years=range(year_start, year_end + 1)),
        "TIPI":   lambda: _h.Philippines(years=range(year_start, year_end + 1)),
        "TAI":    lambda: _h.Taiwan(years=range(year_start, year_end + 1)),
        "AIZU":   lambda: _h.Japan(years=range(year_start, year_end + 1)),
    }

    factory = library_mapping.get(location)
    if factory is None:
        return []

    try:
        country_holidays = factory()
    except Exception:
        return []

    return [
        {"date": d.isoformat(), "name": str(name), "source": "seeded"}
        for d, name in sorted(country_holidays.items())
    ]


WEEKDAY_CODES: Final[list[str]] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def weekday_code(d) -> str:
    """Return the three-letter weekday code for a date (e.g., 'MON')."""
    return WEEKDAY_CODES[d.weekday()]
