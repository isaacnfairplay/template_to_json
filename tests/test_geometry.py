"""Tests for the :mod:`templator.geometry` helpers."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

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


@given(
    st.floats(min_value=100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    st.tuples(
        st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ),
)
@settings(max_examples=50, deadline=None)
def test_percent_of_width_inverse(page_width: float, point: tuple[float, float]) -> None:
    percent = geometry.percent_of_width(point, page_width)
    restored = geometry.percent_sequence([(percent[0] * page_width / 100.0, percent[1] * page_width / 100.0)], page_width)
    assert restored[0] == pytest.approx(percent)


@given(st.floats(min_value=0.01, max_value=500.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=None)
def test_unit_conversion_round_trip(value: float) -> None:
    inches = geometry.points_to_inches(value)
    millimetres = geometry.points_to_mm(value)
    assert geometry.inches_to_points(inches) == pytest.approx(value)
    assert geometry.mm_to_points(millimetres) == pytest.approx(value)


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


@st.composite
def circle_layouts(draw: st.DrawFn) -> tuple[str, float, float, float, tuple[float, float, float, float], float, int | None, int | None]:
    layout = draw(st.sampled_from(["simple", "close"]))
    diameter = draw(st.floats(min_value=20.0, max_value=120.0, allow_nan=False, allow_infinity=False))
    gap = draw(st.floats(min_value=0.0, max_value=diameter * 0.5, allow_nan=False, allow_infinity=False))
    margin_top = draw(st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False))
    margin_right = draw(st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False))
    margin_bottom = draw(st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False))
    margin_left = draw(st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False))
    min_width = diameter + margin_left + margin_right + 5.0
    min_height = diameter + margin_top + margin_bottom + 5.0
    page_w = draw(st.floats(min_value=min_width, max_value=min_width + 400.0, allow_nan=False, allow_infinity=False))
    page_h = draw(st.floats(min_value=min_height, max_value=min_height + 400.0, allow_nan=False, allow_infinity=False))
    max_cols = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=6)))
    max_rows = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=6)))
    return (
        layout,
        page_w,
        page_h,
        diameter,
        (margin_top, margin_right, margin_bottom, margin_left),
        gap,
        max_cols,
        max_rows,
    )


@given(circle_layouts())
@settings(max_examples=25, deadline=None)
def test_circle_synthesizer_respects_spacing(
    params: tuple[str, float, float, float, tuple[float, float, float, float], float, int | None, int | None]
) -> None:
    layout, page_w, page_h, diameter, margins, gap, max_cols, max_rows = params
    template = geometry.synthesize_circles(
        layout=layout,
        page_w_pt=page_w,
        page_h_pt=page_h,
        diameter_pt=diameter,
        margin_pt=margins,
        gap_pt=gap,
        max_cols=max_cols,
        max_rows=max_rows,
    )

    radius = diameter / 2.0
    top, right, bottom, left = margins
    min_x = left + radius - 1e-6
    max_x = page_w - right - radius + 1e-6
    min_y = top + radius - 1e-6
    max_y = page_h - bottom - radius + 1e-6

    centres = template.centers("points")
    assert centres, "Expected at least one centre from synthesizer"

    for x, y in centres:
        assert min_x <= x <= max_x
        assert min_y <= y <= max_y

    minimum_distance = _pairwise_min_distance(list(centres))
    assert minimum_distance >= diameter + gap - 1e-6
