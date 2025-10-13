"""Tests for the :mod:`templator.geometry` helpers."""

from __future__ import annotations

import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from templator import geometry


def _pairwise_min_distance(points: list[tuple[float, float]]) -> float:
    minimum = float("inf")
    for index, (x1, y1) in enumerate(points):
        for x2, y2 in points[index + 1 :]:
            distance = math.hypot(x2 - x1, y2 - y1)
            minimum = min(minimum, distance)
    return minimum


def test_percent_of_width_round_trip() -> None:
    page_width = 600.0
    point = (300.0, 150.0)
    percent = geometry.percent_of_width(point, page_width)
    assert percent == pytest.approx((50.0, 25.0))

    restored = geometry.percent_sequence([point], page_width)[0]
    assert restored == pytest.approx(percent)


def test_synthesize_circles_simple_grid() -> None:
    page_w = 8.5 * geometry.POINTS_PER_INCH
    page_h = 11.0 * geometry.POINTS_PER_INCH
    diameter = 36.0
    gap = 12.0
    margin = (36.0, 36.0, 36.0, 36.0)

    template = geometry.synthesize_circles(
        layout="simple",
        page_w_pt=page_w,
        page_h_pt=page_h,
        diameter_pt=diameter,
        margin_pt=margin,
        gap_pt=gap,
    )

    assert template.grid.kind == "circle_simple"
    assert template.label.shape == "circle"

    pitch = diameter + gap
    assert template.grid.delta_x_pt == pytest.approx(pitch)
    assert template.grid.delta_y_pt == pytest.approx(pitch)

    usable_w = page_w - margin[1] - margin[3]
    usable_h = page_h - margin[0] - margin[2]
    expected_cols = math.floor((usable_w - diameter) / pitch) + 1
    expected_rows = math.floor((usable_h - diameter) / pitch) + 1

    assert template.grid.columns == expected_cols
    assert template.grid.rows == expected_rows
    assert template.centers_count() == expected_cols * expected_rows

    centers = template.centers("points")
    first = centers[0]
    radius = diameter / 2.0
    assert first == pytest.approx((margin[3] + radius, margin[0] + radius))
    assert template.anchors.top_left_pt == pytest.approx(first)

    last = centers[-1]
    assert last[0] <= page_w - margin[1] - radius + 1e-6
    assert last[1] <= page_h - margin[2] - radius + 1e-6

    minimum_distance = _pairwise_min_distance(centers)
    assert minimum_distance >= pitch - 1e-6

    for x, y in centers:
        assert margin[3] + radius - 1e-6 <= x <= page_w - margin[1] - radius + 1e-6
        assert margin[0] + radius - 1e-6 <= y <= page_h - margin[2] - radius + 1e-6


def test_synthesize_circles_close_packing() -> None:
    page_w = 600.0
    page_h = 720.0
    diameter = 40.0
    gap = 4.0
    margin = (20.0, 20.0, 20.0, 20.0)

    template = geometry.synthesize_circles(
        layout="close",
        page_w_pt=page_w,
        page_h_pt=page_h,
        diameter_pt=diameter,
        margin_pt=margin,
        gap_pt=gap,
    )

    assert template.grid.kind == "circle_close"
    pitch_x = diameter + gap
    pitch_y = math.sqrt(3.0) * pitch_x / 2.0
    assert template.grid.delta_x_pt == pytest.approx(pitch_x)
    assert template.grid.delta_y_pt == pytest.approx(pitch_y)

    row_offsets = template.grid.row_offsets_pt
    assert len(row_offsets) == template.grid.rows
    if template.grid.rows > 1:
        assert row_offsets[1] == pytest.approx(pitch_x / 2.0)

    columns_per_row = template.grid.columns_per_row or (
        (template.grid.columns,) * template.grid.rows
    )
    centers = template.centers("points")
    expected_count = sum(columns_per_row)
    assert template.centers_count() == expected_count == len(centers)

    radius = diameter / 2.0
    for idx, (x, y) in enumerate(centers):
        assert margin[3] + radius - 1e-6 <= x <= page_w - margin[1] - radius + 1e-6
        assert margin[0] + radius - 1e-6 <= y <= page_h - margin[2] - radius + 1e-6

    minimum_distance = _pairwise_min_distance(centers)
    assert minimum_distance >= diameter + gap - 1e-6


def test_synthesize_circles_respects_limits() -> None:
    template = geometry.synthesize_circles(
        layout="simple",
        page_w_pt=400.0,
        page_h_pt=400.0,
        diameter_pt=50.0,
        margin_pt=(20.0, 20.0, 20.0, 20.0),
        gap_pt=0.0,
        max_cols=2,
        max_rows=3,
    )

    assert template.grid.columns == 2
    assert template.grid.rows == 3
    assert template.centers_count() == 6


def test_synthesize_circles_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        geometry.synthesize_circles(
            layout="simple",
            page_w_pt=200.0,
            page_h_pt=200.0,
            diameter_pt=300.0,
            margin_pt=(10.0, 10.0, 10.0, 10.0),
        )
