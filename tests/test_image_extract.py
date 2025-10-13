"""Tests for the raster PDF template extractor."""

from __future__ import annotations

from pathlib import Path
import pathlib
import random
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from templator.image_extract import extract_template


def _draw_grid(
    path: Path,
    *,
    page_size: tuple[float, float],
    rows: int,
    columns: int,
    label_size: tuple[float, float],
    start: tuple[float, float],
    spacing: tuple[float, float],
) -> None:
    doc = fitz.open()
    page = doc.new_page(width=page_size[0], height=page_size[1])
    width, height = label_size
    start_x, start_y = start
    step_x, step_y = spacing
    for row in range(rows):
        for col in range(columns):
            x0 = start_x + col * step_x
            y0 = start_y + row * step_y
            rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(0, 0, 0), fill=None)
            shape.commit()
    doc.save(path)
    doc.close()


def _rasterize_pdf(source: Path, destination: Path, dpi: int = 200) -> None:
    with fitz.open(source) as doc:
        page = doc[0]
        zoom = dpi / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        image_bytes = pixmap.tobytes("png")
        page_rect = page.rect

    new_doc = fitz.open()
    new_page = new_doc.new_page(width=page_rect.width, height=page_rect.height)
    new_page.insert_image(new_page.rect, stream=image_bytes)
    new_doc.save(destination)
    new_doc.close()


def _abs_error(value: float, expected: float) -> float:
    return abs(value - expected)


def _assert_template_matches(
    template_path: Path,
    *,
    rows: int,
    columns: int,
    label_size: tuple[float, float],
    start: tuple[float, float],
    spacing: tuple[float, float],
    dpi: int,
) -> None:
    template = extract_template(template_path, dpi=dpi)
    assert template is not None

    width, height = label_size
    spacing_x, spacing_y = spacing

    assert template.grid.rows == rows
    assert template.grid.columns == columns
    assert _abs_error(template.grid.delta_x_pt, spacing_x) <= 0.75
    assert _abs_error(template.grid.delta_y_pt, spacing_y) <= 0.75

    assert _abs_error(template.label.width_pt, width) <= 0.75
    assert _abs_error(template.label.height_pt, height) <= 0.75

    expected_top_left = (start[0] + width / 2.0, start[1] + height / 2.0)
    expected_bottom_left = (
        start[0] + width / 2.0,
        start[1] + (rows - 1) * spacing_y + height / 2.0,
    )

    assert _abs_error(template.anchors.top_left_pt[0], expected_top_left[0]) <= 1.0
    assert _abs_error(template.anchors.top_left_pt[1], expected_top_left[1]) <= 1.0
    assert _abs_error(template.anchors.bottom_left_pt[0], expected_bottom_left[0]) <= 1.0
    assert _abs_error(template.anchors.bottom_left_pt[1], expected_bottom_left[1]) <= 1.0

    centers = list(template.iter_centers())
    assert len(centers) == rows * columns
    assert centers == sorted(centers, key=lambda pt: (pt[1], pt[0]))


def test_extracts_basic_raster_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    raster_path = tmp_path / "grid_raster.pdf"

    page_size = (510.0, 330.0)
    rows, columns = 3, 4
    label_size = (82.0, 44.0)
    spacing = (label_size[0] + 12.0, label_size[1] + 20.0)
    start = (54.0, 68.0)

    _draw_grid(
        pdf_path,
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
    )
    _rasterize_pdf(pdf_path, raster_path, dpi=220)

    _assert_template_matches(
        raster_path,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
        dpi=220,
    )


@pytest.mark.parametrize("rows,columns", [(2, 3), (3, 5), (4, 4)])
def test_raster_property_variations(tmp_path: Path, rows: int, columns: int) -> None:
    rng = random.Random(1234 + rows * 10 + columns)
    pdf_path = tmp_path / f"grid_{rows}x{columns}.pdf"
    raster_path = tmp_path / f"grid_{rows}x{columns}_raster.pdf"

    page_width = 500.0 + rng.uniform(-20.0, 20.0)
    page_height = 320.0 + rng.uniform(-30.0, 30.0)
    label_width = 70.0 + rng.uniform(-10.0, 10.0)
    label_height = 38.0 + rng.uniform(-6.0, 6.0)
    spacing_x = label_width + rng.uniform(10.0, 16.0)
    spacing_y = label_height + rng.uniform(14.0, 22.0)

    margin_x = rng.uniform(30.0, 60.0)
    margin_y = rng.uniform(40.0, 70.0)

    _draw_grid(
        pdf_path,
        page_size=(page_width, page_height),
        rows=rows,
        columns=columns,
        label_size=(label_width, label_height),
        start=(margin_x, margin_y),
        spacing=(spacing_x, spacing_y),
    )

    dpi = rng.choice([180, 200, 240])
    _rasterize_pdf(pdf_path, raster_path, dpi=dpi)

    _assert_template_matches(
        raster_path,
        rows=rows,
        columns=columns,
        label_size=(label_width, label_height),
        start=(margin_x, margin_y),
        spacing=(spacing_x, spacing_y),
        dpi=dpi,
    )
