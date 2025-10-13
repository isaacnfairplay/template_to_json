"""Geometry helpers for converting between coordinate systems."""

from __future__ import annotations

from typing import Iterable, Sequence

Point = tuple[float, float]

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4


def _validate_page_width(page_width_pt: float) -> None:
    if page_width_pt <= 0:
        msg = f"Page width must be positive, received {page_width_pt!r}."
        raise ValueError(msg)


def percent_of_width(point: Point, page_width_pt: float) -> Point:
    """Scale a point from PDF points into percent-of-page-width space."""

    _validate_page_width(page_width_pt)
    x_pt, y_pt = point
    scale = 100.0 / page_width_pt
    return x_pt * scale, y_pt * scale


def percent_sequence(points: Iterable[Point], page_width_pt: float) -> list[Point]:
    """Convert a sequence of points to percent-of-page-width space."""

    return [percent_of_width(point, page_width_pt) for point in points]


def points_to_inches(value: float | Point) -> float | Point:
    """Convert PDF points to inches."""

    if isinstance(value, tuple):
        return tuple(component / POINTS_PER_INCH for component in value)
    return value / POINTS_PER_INCH


def points_to_mm(value: float | Point) -> float | Point:
    """Convert PDF points to millimetres."""

    inches = points_to_inches(value)
    if isinstance(inches, tuple):
        return tuple(component * MM_PER_INCH for component in inches)
    return inches * MM_PER_INCH


def inches_to_points(value: float | Point) -> float | Point:
    """Convert inches to PDF points."""

    if isinstance(value, tuple):
        return tuple(component * POINTS_PER_INCH for component in value)
    return value * POINTS_PER_INCH


def mm_to_points(value: float | Point) -> float | Point:
    """Convert millimetres to PDF points."""

    if isinstance(value, tuple):
        return tuple(component * POINTS_PER_INCH / MM_PER_INCH for component in value)
    return value * POINTS_PER_INCH / MM_PER_INCH


def ensure_row_major(points: Sequence[Point]) -> list[Point]:
    """Return a row-major ordered list of points."""

    return sorted(points, key=lambda point: (point[1], point[0]))

