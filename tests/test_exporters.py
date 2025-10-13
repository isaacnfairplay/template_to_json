"""Tests for the :mod:`templator.exporters` module."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from templator import geometry
from templator.exporters import export_csv, export_json
from templator.models import AnchorPoints, ExtractedTemplate, GridMetrics, LabelGeometry, PageMetrics


def _build_template() -> ExtractedTemplate:
    page = PageMetrics(width_pt=200.0, height_pt=300.0)
    grid = GridMetrics(
        kind="rectangular",
        rows=2,
        columns=2,
        delta_x_pt=100.0,
        delta_y_pt=100.0,
    )
    label = LabelGeometry(shape="rectangle", width_pt=90.0, height_pt=80.0)
    anchors = AnchorPoints(top_left_pt=(10.0, 20.0), bottom_left_pt=(10.0, 220.0))
    centers = (
        (10.0, 20.0),
        (110.0, 20.0),
        (10.0, 120.0),
        (110.0, 120.0),
    )
    return ExtractedTemplate(
        page=page,
        grid=grid,
        label=label,
        anchors=anchors,
        centers_pt=centers,
    )


def _centers_as_points(
    exported: list[tuple[float, float]], coord_space: str, page_width_pt: float
) -> list[tuple[float, float]]:
    if coord_space == "percent_width":
        scale = page_width_pt / 100.0
        return [(x * scale, y * scale) for x, y in exported]
    if coord_space == "points":
        return exported
    if coord_space == "inches":
        return [geometry.inches_to_points(point) for point in exported]
    if coord_space == "mm":
        return [geometry.mm_to_points(point) for point in exported]
    msg = f"Unexpected coordinate space in test: {coord_space!r}"
    raise AssertionError(msg)


@pytest.mark.parametrize(
    "coord_space",
    ["percent_width", "points", "inches", "mm"],
)
def test_export_json_round_trip(tmp_path: Path, coord_space: str) -> None:
    template = _build_template()
    target = tmp_path / f"template_{coord_space}.json"

    export_json(template, target, coord_space=coord_space)

    data = json.loads(target.read_text())
    assert data["centers_coord_space"] == coord_space

    exported = [tuple(point) for point in data["centers"]]
    converted = _centers_as_points(exported, coord_space, template.page.width_pt)
    for (x_conv, y_conv), (x_ref, y_ref) in zip(
        converted, template.centers("points"), strict=True
    ):
        assert x_conv == pytest.approx(x_ref, rel=1e-6, abs=1e-6)
        assert y_conv == pytest.approx(y_ref, rel=1e-6, abs=1e-6)

    if coord_space == "percent_width":
        expected_percent = [
            (x * 100.0 / template.page.width_pt, y * 100.0 / template.page.width_pt)
            for x, y in template.centers("points")
        ]
        for (x_export, y_export), (x_expected, y_expected) in zip(
            exported, expected_percent, strict=True
        ):
            assert x_export == pytest.approx(x_expected, rel=1e-6, abs=1e-6)
            assert y_export == pytest.approx(y_expected, rel=1e-6, abs=1e-6)


@pytest.mark.parametrize(
    "coord_space",
    ["percent_width", "points", "inches", "mm"],
)
def test_export_csv_round_trip(tmp_path: Path, coord_space: str) -> None:
    template = _build_template()
    target = tmp_path / f"template_{coord_space}.csv"

    export_csv(template, target, coord_space=coord_space)

    with target.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert {row["coord_space"] for row in rows} == {coord_space}

    exported = [(float(row["x"]), float(row["y"])) for row in rows]
    converted = _centers_as_points(exported, coord_space, template.page.width_pt)
    for (x_conv, y_conv), (x_ref, y_ref) in zip(
        converted, template.centers("points"), strict=True
    ):
        assert x_conv == pytest.approx(x_ref, rel=1e-6, abs=1e-4)
        assert y_conv == pytest.approx(y_ref, rel=1e-6, abs=1e-4)

    if coord_space == "percent_width":
        expected_percent = [
            (x * 100.0 / template.page.width_pt, y * 100.0 / template.page.width_pt)
            for x, y in template.centers("points")
        ]
        for (x_export, y_export), (x_expected, y_expected) in zip(
            exported, expected_percent, strict=True
        ):
            assert x_export == pytest.approx(x_expected, rel=1e-6, abs=1e-6)
            assert y_export == pytest.approx(y_expected, rel=1e-6, abs=1e-6)


def test_exporters_reject_unknown_coordinate_spaces(tmp_path: Path) -> None:
    template = _build_template()
    with pytest.raises(ValueError):
        export_json(template, tmp_path / "bad.json", coord_space="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        export_csv(template, tmp_path / "bad.csv", coord_space="invalid")  # type: ignore[arg-type]

