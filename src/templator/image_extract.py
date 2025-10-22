"""Raster-based template extraction from rendered page images."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import fitz
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from .models import AnchorPoints, ExtractedTemplate, GridMetrics, LabelGeometry, PageMetrics

Point = tuple[float, float]

_IMAGE_SUFFIXES: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


@dataclass(slots=True)
class _RasterSource:
    """Materialised raster data for a rendered PDF page or input image."""

    gray: np.ndarray
    scale: float
    page_width_pt: float
    page_height_pt: float


@dataclass(slots=True)
class _DetectedRectangle:
    """Internal representation of a detected rectangle in point space."""

    center: Point
    width: float
    height: float


def _median(values: Iterable[float]) -> float:
    series = list(values)
    if not series:
        raise ValueError("Median requested for an empty sequence.")
    return float(np.median(series))


def _binary_dilation(image: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = image.astype(np.uint8)
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=0)
        windows = sliding_window_view(padded, (3, 3))
        result = windows.max(axis=(-2, -1)).astype(np.uint8)
    return result


def _binary_erosion(image: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = image.astype(np.uint8)
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=0)
        windows = sliding_window_view(padded, (3, 3))
        result = windows.min(axis=(-2, -1)).astype(np.uint8)
    return result


def _binary_closing(image: np.ndarray, iterations: int = 1) -> np.ndarray:
    dilated = _binary_dilation(image, iterations)
    return _binary_erosion(dilated, iterations)


def _sobel_edges(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    kernel_x = np.array([[1, 0, -1], [2, 0, -2], [1, 0, -1]], dtype=np.float32)
    kernel_y = kernel_x.T
    padded = np.pad(gray, 1, mode="edge")
    windows = sliding_window_view(padded, (3, 3))
    grad_x = np.sum(windows * kernel_x, axis=(-2, -1))
    grad_y = np.sum(windows * kernel_y, axis=(-2, -1))
    magnitude = np.hypot(grad_x, grad_y)
    return magnitude.astype(np.float32), grad_x.astype(np.float32), grad_y.astype(np.float32)


def _threshold_edges(magnitude: np.ndarray) -> np.ndarray:
    if magnitude.size == 0:
        return magnitude.astype(np.uint8)
    high_percentile = np.percentile(magnitude, 92.0)
    adaptive = magnitude.mean() + magnitude.std()
    threshold = max(high_percentile, adaptive)
    mask = magnitude >= threshold
    return mask.astype(np.uint8)


def _connected_components(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: list[tuple[int, int, int, int]] = []

    for row in range(height):
        for col in range(width):
            if visited[row, col] or mask[row, col] == 0:
                continue

            stack = [(row, col)]
            visited[row, col] = True
            min_r = max_r = row
            min_c = max_c = col
            pixel_count = 0

            while stack:
                r, c = stack.pop()
                pixel_count += 1
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)

                neighbours = (
                    (r - 1, c),
                    (r + 1, c),
                    (r, c - 1),
                    (r, c + 1),
                )
                for nr, nc in neighbours:
                    if 0 <= nr < height and 0 <= nc < width:
                        if not visited[nr, nc] and mask[nr, nc] == 1:
                            visited[nr, nc] = True
                            stack.append((nr, nc))

            if pixel_count < 16:  # Filter extremely small components.
                continue

            boxes.append((min_r, min_c, max_r, max_c))

    return boxes


def _refine_boxes(
    boxes: Sequence[tuple[int, int, int, int]],
    magnitude: np.ndarray,
    grad_x: np.ndarray,
    grad_y: np.ndarray,
) -> list[tuple[int, int, int, int]]:
    refined: list[tuple[int, int, int, int]] = []
    for min_r, min_c, max_r, max_c in boxes:
        region = magnitude[min_r : max_r + 1, min_c : max_c + 1]
        if region.size == 0:
            continue

        grad_x_region = np.abs(grad_x[min_r : max_r + 1, min_c : max_c + 1])
        grad_y_region = np.abs(grad_y[min_r : max_r + 1, min_c : max_c + 1])
        col_profile = grad_x_region.max(axis=0)
        row_profile = grad_y_region.max(axis=1)

        col_peak = float(col_profile.max())
        row_peak = float(row_profile.max())
        if col_peak <= 0 or row_peak <= 0:
            refined.append((min_r, min_c, max_r, max_c))
            continue

        col_threshold = col_peak * 0.5
        row_threshold = row_peak * 0.5

        min_c0, min_r0 = min_c, min_r
        max_c0, max_r0 = max_c, max_r

        mid_col = len(col_profile) // 2
        left_idx = int(np.argmax(col_profile[: max(1, mid_col + 1)]))
        right_idx = int(np.argmax(col_profile[mid_col:]) + mid_col)
        min_c = min_c0 + left_idx
        max_c = min_c0 + right_idx

        mid_row = len(row_profile) // 2
        top_idx = int(np.argmax(row_profile[: max(1, mid_row + 1)]))
        bottom_idx = int(np.argmax(row_profile[mid_row:]) + mid_row)
        min_r = min_r0 + top_idx
        max_r = min_r0 + bottom_idx

        refined.append((min_r, min_c, max_r, max_c))

    return refined


def _component_boxes_to_rectangles(
    boxes: Sequence[tuple[int, int, int, int]],
    scale: float,
) -> list[_DetectedRectangle]:
    rectangles: list[_DetectedRectangle] = []
    for min_r, min_c, max_r, max_c in boxes:
        width_px = max_c - min_c + 1
        height_px = max_r - min_r + 1
        if width_px <= 1 or height_px <= 1:
            continue

        width_pt = width_px * scale
        height_pt = height_px * scale

        # Reject boxes that are unreasonably thin.
        if width_pt < 4 or height_pt < 4:
            continue

        center_x_pt = (min_c + max_c + 1) / 2.0 * scale
        center_y_pt = (min_r + max_r + 1) / 2.0 * scale

        rectangles.append(
            _DetectedRectangle(center=(center_x_pt, center_y_pt), width=width_pt, height=height_pt)
        )

    return rectangles


def _cluster_rows(rectangles: Sequence[_DetectedRectangle]) -> list[list[_DetectedRectangle]]:
    if not rectangles:
        return []

    median_height = _median(rect.height for rect in rectangles)
    row_tolerance = max(median_height * 0.3, 0.75)

    sorted_rects = sorted(rectangles, key=lambda rect: rect.center[1])
    rows: list[list[_DetectedRectangle]] = []

    for rect in sorted_rects:
        placed = False
        for row in rows:
            row_y = float(np.mean([r.center[1] for r in row]))
            if abs(rect.center[1] - row_y) <= row_tolerance:
                row.append(rect)
                placed = True
                break
        if not placed:
            rows.append([rect])

    for row in rows:
        row.sort(key=lambda rect: rect.center[0])

    rows.sort(key=lambda row: float(np.mean([r.center[1] for r in row])))
    return rows


def _flatten_rows(rows: Sequence[Sequence[_DetectedRectangle]]) -> list[_DetectedRectangle]:
    ordered: list[_DetectedRectangle] = []
    for row in rows:
        ordered.extend(row)
    return ordered


def _filter_boxes(rectangles: Sequence[_DetectedRectangle]) -> list[_DetectedRectangle]:
    if not rectangles:
        return []

    widths = [rect.width for rect in rectangles]
    heights = [rect.height for rect in rectangles]

    width_median = _median(widths)
    height_median = _median(heights)

    filtered: list[_DetectedRectangle] = []
    for rect in rectangles:
        if rect.width < width_median * 0.6 or rect.width > width_median * 1.4:
            continue
        if rect.height < height_median * 0.6 or rect.height > height_median * 1.4:
            continue
        filtered.append(rect)

    return filtered if filtered else list(rectangles)


def _render_raster_source(path: Path, page: int, dpi: int) -> _RasterSource:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        if page != 0:
            msg = "Image sources support only page index 0."
            raise IndexError(msg)

        with Image.open(path) as image:
            gray_image = image.convert("L")
            gray = np.asarray(gray_image, dtype=np.float32)

        if gray.size == 0:
            raise ValueError("Input image is empty.")

        gray /= 255.0

        scale = 72.0 / float(dpi)
        if scale <= 0:
            msg = "Rendered raster produced a non-positive scale factor."
            raise ValueError(msg)

        height_px, width_px = gray.shape
        page_width_pt = float(width_px) * scale
        page_height_pt = float(height_px) * scale

        return _RasterSource(
            gray=gray,
            scale=scale,
            page_width_pt=page_width_pt,
            page_height_pt=page_height_pt,
        )

    with fitz.open(path) as document:
        if page < 0 or page >= document.page_count:
            msg = f"Requested page index {page} outside range 0..{document.page_count - 1}."
            raise IndexError(msg)

        pdf_page = document[page]
        page_rect = pdf_page.rect
        is_pdf = document.is_pdf

        zoom = dpi / 72.0
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

        samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
        channels = pixmap.n
        image = samples.reshape(pixmap.height, pixmap.width, channels)

        if channels >= 3:
            gray = (
                0.2126 * image[:, :, 0]
                + 0.7152 * image[:, :, 1]
                + 0.0722 * image[:, :, 2]
            ).astype(np.float32)
        else:
            gray = image[:, :, 0].astype(np.float32)

        gray /= 255.0

        if pixmap.width <= 0 or pixmap.height <= 0:
            raise ValueError("Rendered raster has zero dimensions.")

        scale = 72.0 / float(dpi)
        if scale <= 0:
            msg = "Rendered raster produced a non-positive scale factor."
            raise ValueError(msg)

        if is_pdf:
            page_width_pt = float(page_rect.width)
            page_height_pt = float(page_rect.height)
        else:
            page_width_pt = float(pixmap.width) * scale
            page_height_pt = float(pixmap.height) * scale

    return _RasterSource(
        gray=gray,
        scale=scale,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
    )


def _extract_rectangles_from_raster(source: _RasterSource) -> list[_DetectedRectangle]:
    magnitude, grad_x, grad_y = _sobel_edges(source.gray)
    edges = _threshold_edges(magnitude)
    closed = _binary_closing(edges, iterations=2)
    dilated = _binary_dilation(closed, iterations=1)

    boxes = _connected_components(dilated)
    boxes = _refine_boxes(boxes, magnitude, grad_x, grad_y)
    rectangles = _component_boxes_to_rectangles(boxes, source.scale)

    filtered = _filter_boxes(rectangles)

    return filtered


def extract_template(
    path: str | Path,
    page: int = 0,
    *,
    dpi: int = 200,
) -> Optional[ExtractedTemplate]:
    """Extract a label template from a rasterised PDF page or source image."""

    if dpi <= 0:
        msg = f"DPI must be a positive integer. Received {dpi!r}."
        raise ValueError(msg)

    pdf_path = Path(path)
    if not pdf_path.exists():
        msg = f"The provided path does not exist: {pdf_path}"
        raise FileNotFoundError(msg)

    raster = _render_raster_source(pdf_path, page, dpi)
    rectangles = _extract_rectangles_from_raster(raster)
    if not rectangles:
        return None

    rows = _cluster_rows(rectangles)
    if not rows:
        return None

    ordered_rectangles = _flatten_rows(rows)

    widths = [rect.width for rect in ordered_rectangles]
    heights = [rect.height for rect in ordered_rectangles]
    centers = [rect.center for rect in ordered_rectangles]

    label_width = _median(widths)
    label_height = _median(heights)

    row_centers = [float(np.mean([r.center[1] for r in row])) for row in rows]
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

    page_metrics = PageMetrics(
        width_pt=raster.page_width_pt,
        height_pt=raster.page_height_pt,
    )

    grid_metrics = GridMetrics(
        kind="rectangular",
        rows=len(rows),
        columns=max(column_counts),
        delta_x_pt=delta_x,
        delta_y_pt=delta_y,
        columns_per_row=tuple(column_counts),
    )

    label_geometry = LabelGeometry(shape="rectangle", width_pt=label_width, height_pt=label_height)

    anchors = AnchorPoints(top_left_pt=top_left_center, bottom_left_pt=bottom_left_center)

    metadata = {"extraction": "raster", "dpi": f"{dpi}"}

    return ExtractedTemplate(
        page=page_metrics,
        grid=grid_metrics,
        label=label_geometry,
        anchors=anchors,
        centers_pt=centers,
        metadata=metadata,
    )

