"""Vector-based template extraction from PDF files."""

from __future__ import annotations

from dataclasses import dataclass
import statistics
from pathlib import Path
from typing import Iterable, Optional, Sequence

import fitz

from .models import AnchorPoints, ExtractedTemplate, GridMetrics, LabelGeometry, PageMetrics

Point = tuple[float, float]


@dataclass(slots=True)
class _DetectedRectangle:
    """Internal representation of a detected rectangle."""

    center: Point
    width: float
    height: float
    radius: float


def _median(values: Iterable[float]) -> float:
    series = list(values)
    if not series:
        raise ValueError("Median requested for an empty sequence.")
    return float(statistics.median(series))


def _estimate_corner_radius(items: Sequence[tuple], rect: fitz.Rect) -> float:
    """Best-effort radius estimation for rounded rectangles."""

    width = float(rect.width)
    height = float(rect.height)
    if width <= 0 or height <= 0:
        return 0.0

    limit_x = width / 2.0 + 1e-6
    limit_y = height / 2.0 + 1e-6

    left = float(rect.x0)
    right = float(rect.x1)
    top = float(rect.y0)
    bottom = float(rect.y1)

    x_candidates: list[float] = []
    y_candidates: list[float] = []

    for item in items:
        if not item:
            continue
        op = item[0]
        if op not in {"l", "L"}:  # Only consider straight segments.
            continue
        # Remaining tuple entries are points.
        for point in item[1:]:
            if isinstance(point, fitz.Point):
                px, py = float(point.x), float(point.y)
            else:
                # Skip non-point entries (e.g., rectangles).
                continue
            dx_left = px - left
            dx_right = right - px
            dy_top = py - top
            dy_bottom = bottom - py
            if 1e-6 < dx_left < limit_x:
                x_candidates.append(dx_left)
            if 1e-6 < dx_right < limit_x:
                x_candidates.append(dx_right)
            if 1e-6 < dy_top < limit_y:
                y_candidates.append(dy_top)
            if 1e-6 < dy_bottom < limit_y:
                y_candidates.append(dy_bottom)

    if not x_candidates and not y_candidates:
        return 0.0

    if x_candidates and y_candidates:
        return (_median(x_candidates) + _median(y_candidates)) / 2.0
    if x_candidates:
        return _median(x_candidates)
    return _median(y_candidates)


def _rectangle_from_drawing(drawing: dict) -> _DetectedRectangle | None:
    rect = drawing.get("rect")
    items: Sequence[tuple] = drawing.get("items", [])
    if rect is None or not items:
        return None

    first_item = items[0]
    if first_item and first_item[0] == "re":
        radius = 0.0
    else:
        radius = _estimate_corner_radius(items, rect)

    width = float(rect.width)
    height = float(rect.height)
    if width <= 0 or height <= 0:
        return None

    center = (float(rect.x0 + rect.x1) / 2.0, float(rect.y0 + rect.y1) / 2.0)
    return _DetectedRectangle(center=center, width=width, height=height, radius=radius)


def _cluster_rows(rectangles: Sequence[_DetectedRectangle]) -> list[list[_DetectedRectangle]]:
    if not rectangles:
        return []

    median_height = _median(rect.height for rect in rectangles)
    row_tolerance = max(median_height * 0.25, 0.5)

    sorted_rects = sorted(rectangles, key=lambda rect: rect.center[1])
    rows: list[list[_DetectedRectangle]] = []

    for rect in sorted_rects:
        placed = False
        for row in rows:
            row_y = statistics.mean(r.center[1] for r in row)
            if abs(rect.center[1] - row_y) <= row_tolerance:
                row.append(rect)
                placed = True
                break
        if not placed:
            rows.append([rect])

    for row in rows:
        row.sort(key=lambda rect: rect.center[0])

    rows.sort(key=lambda row: statistics.mean(r.center[1] for r in row))
    return rows


def _flatten_rows(rows: Sequence[Sequence[_DetectedRectangle]]) -> list[_DetectedRectangle]:
    ordered: list[_DetectedRectangle] = []
    for row in rows:
        ordered.extend(row)
    return ordered


def extract_template(
    path: str | Path,
    page: int = 0,
    *,
    prefer_vector: bool = True,
    dpi: int = 200,
) -> Optional[ExtractedTemplate]:
    """Extract a label template from the provided PDF file."""

    del prefer_vector, dpi  # Vector extraction only for now.

    pdf_path = Path(path)
    if not pdf_path.exists():
        msg = f"The provided PDF path does not exist: {pdf_path}"
        raise FileNotFoundError(msg)

    with fitz.open(pdf_path) as document:
        if page < 0 or page >= document.page_count:
            msg = f"Requested page index {page} outside range 0..{document.page_count - 1}."
            raise IndexError(msg)
        pdf_page = document[page]
        page_rect = pdf_page.rect
        drawings = pdf_page.get_drawings()

        rectangles: list[_DetectedRectangle] = []
        for drawing in drawings:
            detected = _rectangle_from_drawing(drawing)
            if detected is not None:
                rectangles.append(detected)

        if not rectangles:
            return None

        rows = _cluster_rows(rectangles)
        if not rows:
            return None

        ordered_rectangles = _flatten_rows(rows)

        widths = [rect.width for rect in ordered_rectangles]
        heights = [rect.height for rect in ordered_rectangles]
        radii = [rect.radius for rect in ordered_rectangles]
        centers = [rect.center for rect in ordered_rectangles]

        label_width = _median(widths)
        label_height = _median(heights)
        corner_radius = _median(radii)

        row_centers = [statistics.mean(r.center[1] for r in row) for row in rows]
        column_counts = [len(row) for row in rows]

        delta_y_values: list[float] = []
        for idx in range(1, len(row_centers)):
            delta_y_values.append(row_centers[idx] - row_centers[idx - 1])
        delta_y = _median(delta_y_values) if delta_y_values else label_height

        delta_x_values: list[float] = []
        for row in rows:
            if len(row) < 2:
                continue
            xs = [rect.center[0] for rect in row]
            for idx in range(1, len(xs)):
                delta_x_values.append(xs[idx] - xs[idx - 1])
        delta_x = _median(delta_x_values) if delta_x_values else label_width

        top_left_center = rows[0][0].center
        bottom_left_center = rows[-1][0].center

        page_metrics = PageMetrics(width_pt=float(page_rect.width), height_pt=float(page_rect.height))

        grid_metrics = GridMetrics(
            kind="rectangular",
            rows=len(rows),
            columns=max(column_counts),
            delta_x_pt=delta_x,
            delta_y_pt=delta_y,
        )

        label_geometry = LabelGeometry(shape="rectangle", width_pt=label_width, height_pt=label_height)

        anchors = AnchorPoints(top_left_pt=top_left_center, bottom_left_pt=bottom_left_center)

        metadata = {"corner_radius_pt": f"{corner_radius:.6f}"}

        return ExtractedTemplate(
            page=page_metrics,
            grid=grid_metrics,
            label=label_geometry,
            anchors=anchors,
            centers_pt=centers,
            metadata=metadata,
        )

