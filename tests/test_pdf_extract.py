"""Tests for the vector PDF template extractor."""

from __future__ import annotations

from pathlib import Path
import pathlib
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from templator.pdf_extract import extract_template


def _draw_grid(
    path: Path,
    *,
    page_size: tuple[float, float],
    rows: int,
    columns: int,
    label_size: tuple[float, float],
    start: tuple[float, float],
    spacing: tuple[float, float],
    radius: float = 0.0,
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
            if radius:
                shape.draw_rect(rect, radius=radius)
            else:
                shape.draw_rect(rect)
            shape.finish(color=(0, 0, 0), fill=None)
            shape.commit()
    doc.save(path)
    doc.close()


def test_extracts_basic_vector_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    page_size = (500.0, 320.0)
    rows, columns = 3, 4
    label_size = (80.0, 40.0)
    spacing = (label_size[0] + 12.0, label_size[1] + 18.0)
    start = (50.0, 70.0)

    _draw_grid(
        pdf_path,
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
    )

    template = extract_template(pdf_path)
    assert template is not None

    assert template.page.width_pt == pytest.approx(page_size[0])
    assert template.page.height_pt == pytest.approx(page_size[1])

    assert template.grid.rows == rows
    assert template.grid.columns == columns
    assert template.grid.delta_x_pt == pytest.approx(spacing[0])
    assert template.grid.delta_y_pt == pytest.approx(spacing[1])

    assert template.label.width_pt == pytest.approx(label_size[0])
    assert template.label.height_pt == pytest.approx(label_size[1])

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

    assert float(template.metadata.get("corner_radius_pt", "0")) == pytest.approx(0.0)


def test_extracts_rounded_rectangles(tmp_path: Path) -> None:
    pdf_path = tmp_path / "rounded.pdf"
    page_size = (400.0, 260.0)
    rows, columns = 2, 3
    label_size = (90.0, 60.0)
    spacing = (label_size[0] + 20.0, label_size[1] + 16.0)
    start = (36.0, 48.0)
    radius_fraction = 0.15

    _draw_grid(
        pdf_path,
        page_size=page_size,
        rows=rows,
        columns=columns,
        label_size=label_size,
        start=start,
        spacing=spacing,
        radius=radius_fraction,
    )

    template = extract_template(pdf_path)
    assert template is not None

    expected_radius = radius_fraction * min(label_size)
    assert float(template.metadata.get("corner_radius_pt", "0")) == pytest.approx(expected_radius, abs=0.1)

    assert template.grid.rows == rows
    assert template.grid.columns == columns
    assert template.grid.delta_x_pt == pytest.approx(spacing[0])
    assert template.grid.delta_y_pt == pytest.approx(spacing[1])

    assert template.label.width_pt == pytest.approx(label_size[0])
    assert template.label.height_pt == pytest.approx(label_size[1])
