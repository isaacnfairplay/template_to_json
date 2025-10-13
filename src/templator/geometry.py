"""Geometry helpers for converting between coordinate systems and lattices."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from . import models

Point = tuple[float, float]
Margins = tuple[float, float, float, float]

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4

_EPSILON = 1e-9


def _validate_page_width(page_width_pt: float) -> None:
    if page_width_pt <= 0:
        msg = f"Page width must be positive, received {page_width_pt!r}."
        raise ValueError(msg)


def _validate_positive(value: float, name: str) -> None:
    if value <= 0:
        msg = f"{name} must be positive, received {value!r}."
        raise ValueError(msg)


def _validate_non_negative(value: float, name: str) -> None:
    if value < 0:
        msg = f"{name} must be non-negative, received {value!r}."
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


@dataclass(slots=True)
class CircleLattice:
    """Parameters describing a circular lattice arrangement."""

    pitch_x_pt: float
    pitch_y_pt: float
    row_offset_pt: float


def _circle_lattice_parameters(layout: str, diameter_pt: float, gap_pt: float) -> CircleLattice:
    layout_key = layout.lower()
    _validate_positive(diameter_pt, "Circle diameter")
    _validate_non_negative(gap_pt, "Circle gap")
    pitch_x = diameter_pt + gap_pt
    if layout_key == "simple":
        return CircleLattice(pitch_x_pt=pitch_x, pitch_y_pt=pitch_x, row_offset_pt=0.0)
    if layout_key == "close":
        pitch_y = math.sqrt(3.0) * pitch_x / 2.0
        return CircleLattice(pitch_x_pt=pitch_x, pitch_y_pt=pitch_y, row_offset_pt=pitch_x / 2.0)
    msg = f"Unsupported circle layout: {layout!r}. Expected 'simple' or 'close'."
    raise ValueError(msg)


def _validate_margins(margin_pt: Margins) -> Margins:
    if len(margin_pt) != 4:
        msg = "Margins must be a four-tuple of (top, right, bottom, left)."
        raise ValueError(msg)
    top, right, bottom, left = margin_pt
    for value, name in zip(margin_pt, ("top", "right", "bottom", "left"), strict=True):
        _validate_non_negative(value, f"Margin {name}")
    return top, right, bottom, left


def _usable_extent(page: float, margin_a: float, margin_b: float, diameter_pt: float) -> float:
    usable = page - margin_a - margin_b
    if usable < diameter_pt - _EPSILON:
        msg = (
            "Page margins leave no usable space for the requested diameter. "
            f"Usable span={usable!r}, diameter={diameter_pt!r}."
        )
        raise ValueError(msg)
    return usable


def _generate_circle_centres(
    layout: str,
    page_w_pt: float,
    page_h_pt: float,
    diameter_pt: float,
    margin_pt: Margins,
    gap_pt: float,
    max_cols: int | None,
    max_rows: int | None,
) -> tuple[list[Point], list[float], list[int]]:
    layout_key = layout.lower()
    lattice = _circle_lattice_parameters(layout_key, diameter_pt, gap_pt)
    top, right, bottom, left = _validate_margins(margin_pt)
    _validate_positive(page_w_pt, "Page width")
    _validate_positive(page_h_pt, "Page height")

    if max_cols is not None and max_cols <= 0:
        msg = f"max_cols must be positive when provided, received {max_cols!r}."
        raise ValueError(msg)
    if max_rows is not None and max_rows <= 0:
        msg = f"max_rows must be positive when provided, received {max_rows!r}."
        raise ValueError(msg)

    _usable_extent(page_w_pt, left, right, diameter_pt)
    _usable_extent(page_h_pt, top, bottom, diameter_pt)

    radius = diameter_pt / 2.0
    max_x = page_w_pt - right - radius
    start_x_base = left + radius
    max_y = page_h_pt - bottom - radius
    start_y = top + radius

    centres: list[Point] = []
    row_offsets: list[float] = []
    columns_per_row: list[int] = []

    attempted_row = 0
    added_rows = 0
    while True:
        y = start_y + attempted_row * lattice.pitch_y_pt
        if y > max_y + _EPSILON:
            break

        offset = 0.0
        if layout_key == "close" and attempted_row % 2 == 1:
            offset = lattice.row_offset_pt

        x_start = start_x_base + offset
        if x_start > max_x + _EPSILON:
            attempted_row += 1
            continue

        available_x = max_x - x_start
        if available_x < -_EPSILON:
            attempted_row += 1
            continue

        raw_columns = int(math.floor((available_x + _EPSILON) / lattice.pitch_x_pt)) + 1
        if max_cols is not None:
            raw_columns = min(raw_columns, max_cols)

        if raw_columns <= 0:
            attempted_row += 1
            continue

        row_offsets.append(offset)
        columns_per_row.append(raw_columns)

        for column in range(raw_columns):
            x = x_start + column * lattice.pitch_x_pt
            centres.append((x, y))

        added_rows += 1
        attempted_row += 1

        if max_rows is not None and added_rows >= max_rows:
            break

    if not centres:
        msg = "No circle centres could be generated with the provided configuration."
        raise ValueError(msg)

    return centres, row_offsets, columns_per_row


def _grid_metadata(
    layout: str,
    lattice: CircleLattice,
    columns_per_row: Sequence[int],
    row_offsets: Sequence[float],
) -> models.GridMetrics:
    rows = len(columns_per_row)
    columns = max(columns_per_row)
    columns_tuple = tuple(columns_per_row)
    offsets_tuple = tuple(row_offsets)
    uniform_columns = all(value == columns for value in columns_tuple)
    columns_metadata: tuple[int, ...] | None = None
    if not uniform_columns:
        columns_metadata = columns_tuple
    else:
        columns_metadata = None

    kind: models.GridKind
    layout_key = layout.lower()
    if layout_key == "simple":
        kind = "circle_simple"
    elif layout_key == "close":
        kind = "circle_close"
    else:  # pragma: no cover - guarded by caller
        kind = "rectangular"

    return models.GridMetrics(
        kind=kind,
        rows=rows,
        columns=columns,
        delta_x_pt=lattice.pitch_x_pt,
        delta_y_pt=lattice.pitch_y_pt,
        row_offsets_pt=offsets_tuple,
        columns_per_row=columns_metadata,
    )


def synthesize_circles(
    layout: str,
    page_w_pt: float,
    page_h_pt: float,
    diameter_pt: float,
    margin_pt: Margins,
    gap_pt: float = 0.0,
    max_cols: int | None = None,
    max_rows: int | None = None,
) -> models.ExtractedTemplate:
    """Generate a circular label template in the requested lattice layout."""

    layout_key = layout.lower()
    lattice = _circle_lattice_parameters(layout_key, diameter_pt, gap_pt)
    centres, row_offsets, columns_per_row = _generate_circle_centres(
        layout=layout_key,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        diameter_pt=diameter_pt,
        margin_pt=margin_pt,
        gap_pt=gap_pt,
        max_cols=max_cols,
        max_rows=max_rows,
    )

    grid = _grid_metadata(layout_key, lattice, columns_per_row, row_offsets)

    top_left = centres[0]
    bottom_left: Point
    # Identify the first centre of the final row.
    centre_index = 0
    for columns in columns_per_row[:-1]:
        centre_index += columns
    bottom_left = centres[centre_index]

    anchors = models.AnchorPoints(top_left_pt=top_left, bottom_left_pt=bottom_left)

    page = models.PageMetrics(width_pt=page_w_pt, height_pt=page_h_pt)
    label = models.LabelGeometry(shape="circle", width_pt=diameter_pt, height_pt=diameter_pt)

    template = models.ExtractedTemplate(
        page=page,
        grid=grid,
        label=label,
        anchors=anchors,
        centers_pt=centres,
        metadata={
            "layout": layout_key,
            "gap_pt": f"{gap_pt:.6f}",
        },
    )

    _validate_circle_constraints(template, margin_pt)
    return template


def _validate_circle_constraints(template: models.ExtractedTemplate, margin_pt: Margins) -> None:
    """Validate non-overlap and in-bounds constraints for circle templates."""

    diameter_pt = template.label.diameter_pt
    radius = diameter_pt / 2.0
    top, right, bottom, left = margin_pt

    page_w = template.page.width_pt
    page_h = template.page.height_pt

    min_x = left + radius - _EPSILON
    max_x = page_w - right - radius + _EPSILON
    min_y = top + radius - _EPSILON
    max_y = page_h - bottom - radius + _EPSILON

    centres = list(template.centers_pt)
    for x, y in centres:
        if not (min_x <= x <= max_x) or not (min_y <= y <= max_y):
            msg = (
                "Generated centre lies outside the allowed page bounds. "
                f"Centre=({x!r}, {y!r}), bounds=(({min_x!r}, {min_y!r}) to ({max_x!r}, {max_y!r}))."
            )
            raise ValueError(msg)

    min_distance = diameter_pt - _EPSILON
    for index, (x1, y1) in enumerate(centres):
        for x2, y2 in centres[index + 1 :]:
            distance = math.hypot(x2 - x1, y2 - y1)
            if distance < min_distance:
                msg = (
                    "Generated centres overlap based on the requested diameter and gap. "
                    f"Distance={distance!r}, required>={min_distance!r}."
                )
                raise ValueError(msg)

