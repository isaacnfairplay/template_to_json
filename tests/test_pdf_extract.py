"""Tests for the vector PDF template extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf

from templator.pdf_extract import extract_template


def _generate_duplicate_rect_pdf(path: Path, spec: RectTemplateSpec) -> None:
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=spec.page_size[0], height=spec.page_size[1])
        for x0, y0, width, height in spec.iter_rectangles():
            rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
            for _ in range(2):  # Draw stroke/fill style duplicates.
                shape = page.new_shape()
                shape.draw_rect(rect)
                shape.finish(color=(0, 0, 0), fill=None)
                shape.commit()
        doc.save(path)
    finally:
        doc.close()


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


def test_extracts_basic_vector_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    page_size = (500.0, 320.0)
    rows, columns = 3, 4
    label_size = (80.0, 40.0)
    spacing = (label_size[0] + 12.0, label_size[1] + 18.0)
    start = (50.0, 70.0)

    spec = RectTemplateSpec(
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
    )
    generate_rect_template_pdf(pdf_path, spec=spec)

    template = extract_template(pdf_path)
    assert template is not None

    assert template.page.width_pt == pytest.approx(page_size[0])
    assert template.page.height_pt == pytest.approx(page_size[1])

    assert template.grid.rows == rows
    assert template.grid.columns == columns
    assert template.grid.columns_per_row == (columns,) * rows
    assert template.grid.delta_x_pt == pytest.approx(spacing[0])
    assert template.grid.delta_y_pt == pytest.approx(spacing[1])

    assert template.label.width_pt == pytest.approx(label_size[0])
    assert template.label.height_pt == pytest.approx(label_size[1])

    assert template.metadata.get("extraction") == "vector"

    expected_top_left = (start[0] + label_size[0] / 2.0, start[1] + label_size[1] / 2.0)
    assert template.anchors.top_left_pt == pytest.approx(expected_top_left)

    expected_bottom_left = (
        start[0] + label_size[0] / 2.0,
        start[1] + (rows - 1) * spacing[1] + label_size[1] / 2.0,
    )
    assert template.anchors.bottom_left_pt == pytest.approx(expected_bottom_left)

    centers = list(template.iter_centers())
    assert len(centers) == rows * columns
    assert centers == sorted(centers, key=lambda pt: (pt[1], pt[0]))

    expected_centers = _centers_from_spec(spec)
    for actual, expected in zip(centers, expected_centers, strict=True):
        assert actual[0] == pytest.approx(expected[0], abs=1e-6)
        assert actual[1] == pytest.approx(expected[1], abs=1e-6)

    assert float(template.metadata.get("corner_radius_pt", "0")) == pytest.approx(0.0)


def test_extracts_rounded_rectangles(tmp_path: Path) -> None:
    pdf_path = tmp_path / "rounded.pdf"
    page_size = (400.0, 260.0)
    rows, columns = 2, 3
    label_size = (90.0, 60.0)
    spacing = (label_size[0] + 20.0, label_size[1] + 16.0)
    start = (36.0, 48.0)
    corner_radius = 0.15 * min(label_size)

    spec = RectTemplateSpec(
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
        corner_radius=corner_radius,
    )
    generate_rect_template_pdf(pdf_path, spec=spec)

    template = extract_template(pdf_path)
    assert template is not None

    expected_radius = corner_radius
    assert float(template.metadata.get("corner_radius_pt", "0")) == pytest.approx(expected_radius, abs=0.1)

    assert template.grid.rows == rows
    assert template.grid.columns == columns
    assert template.grid.columns_per_row == (columns,) * rows
    assert template.grid.delta_x_pt == pytest.approx(spacing[0])
    assert template.grid.delta_y_pt == pytest.approx(spacing[1])

    assert template.label.width_pt == pytest.approx(label_size[0])
    assert template.label.height_pt == pytest.approx(label_size[1])

    assert template.metadata.get("extraction") == "vector"

    expected_centers = _centers_from_spec(spec)
    for actual, expected in zip(template.iter_centers(), expected_centers, strict=True):
        assert actual[0] == pytest.approx(expected[0], abs=1e-6)
        assert actual[1] == pytest.approx(expected[1], abs=1e-6)


def test_extracts_grid_with_duplicate_drawings(tmp_path: Path) -> None:
    pdf_path = tmp_path / "duplicated.pdf"
    spec = RectTemplateSpec(
        page_size=(420.0, 300.0),
        rows=3,
        columns=2,
        label_size=(92.0, 54.0),
        start=(44.0, 62.0),
        spacing=(112.0, 96.0),
    )
    _generate_duplicate_rect_pdf(pdf_path, spec)

    template = extract_template(pdf_path)
    assert template is not None

    assert template.grid.rows == spec.rows
    assert template.grid.columns == spec.columns
    assert template.grid.columns_per_row == (spec.columns,) * spec.rows
    assert template.centers_count() == spec.rows * spec.columns
