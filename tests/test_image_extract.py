"""Tests for the raster PDF template extractor."""

from __future__ import annotations

from pathlib import Path
import random

import pytest

from scripts.gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf
from scripts.rasterize_pdf import rasterize_page

from templator.image_extract import extract_template


def _centers_from_spec(spec: RectTemplateSpec) -> list[tuple[float, float]]:
    width, height = spec.label_size
    start_x, start_y = spec.start
    step_x, step_y = spec.spacing
    centers: list[tuple[float, float]] = []
    for row in range(spec.rows):
        for col in range(spec.columns):
            x = start_x + col * step_x + width / 2.0
            y = start_y + row * step_y + height / 2.0
            centers.append((x, y))
    return centers


def _abs_error(value: float, expected: float) -> float:
    return abs(value - expected)


def _assert_template_matches(
    template_path: Path,
    *,
    spec: RectTemplateSpec,
    dpi: int,
) -> None:
    template = extract_template(template_path, dpi=dpi)
    assert template is not None

    width, height = spec.label_size
    spacing_x, spacing_y = spec.spacing

    assert template.grid.rows == spec.rows
    assert template.grid.columns == spec.columns
    assert _abs_error(template.grid.delta_x_pt, spacing_x) <= 0.75
    assert _abs_error(template.grid.delta_y_pt, spacing_y) <= 0.75

    assert _abs_error(template.label.width_pt, width) <= 0.75
    assert _abs_error(template.label.height_pt, height) <= 0.75

    expected_top_left = (spec.start[0] + width / 2.0, spec.start[1] + height / 2.0)
    expected_bottom_left = (
        spec.start[0] + width / 2.0,
        spec.start[1] + (spec.rows - 1) * spacing_y + height / 2.0,
    )

    assert _abs_error(template.anchors.top_left_pt[0], expected_top_left[0]) <= 1.0
    assert _abs_error(template.anchors.top_left_pt[1], expected_top_left[1]) <= 1.0
    assert _abs_error(template.anchors.bottom_left_pt[0], expected_bottom_left[0]) <= 1.0
    assert _abs_error(template.anchors.bottom_left_pt[1], expected_bottom_left[1]) <= 1.0

    centers = list(template.iter_centers())
    assert len(centers) == spec.rows * spec.columns
    assert centers == sorted(centers, key=lambda pt: (pt[1], pt[0]))

    expected_centers = _centers_from_spec(spec)
    for actual, expected in zip(centers, expected_centers, strict=True):
        assert _abs_error(actual[0], expected[0]) <= 1.5
        assert _abs_error(actual[1], expected[1]) <= 1.5


def test_extracts_basic_raster_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    raster_path = tmp_path / "grid_raster.pdf"

    page_size = (510.0, 330.0)
    rows, columns = 3, 4
    label_size = (82.0, 44.0)
    spacing = (label_size[0] + 12.0, label_size[1] + 20.0)
    start = (54.0, 68.0)

    spec = RectTemplateSpec(
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
    )
    generate_rect_template_pdf(pdf_path, spec=spec)
    rasterize_page(pdf_path, dpi=220, pdf_path=raster_path)

    _assert_template_matches(
        raster_path,
        spec=spec,
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

    spec = RectTemplateSpec(
        page_size=(page_width, page_height),
        rows=rows,
        columns=columns,
        label_size=(label_width, label_height),
        start=(margin_x, margin_y),
        spacing=(spacing_x, spacing_y),
    )
    generate_rect_template_pdf(pdf_path, spec=spec)

    dpi = rng.choice([180, 200, 240])
    rasterize_page(pdf_path, dpi=dpi, pdf_path=raster_path)

    _assert_template_matches(
        raster_path,
        spec=spec,
        dpi=dpi,
    )
