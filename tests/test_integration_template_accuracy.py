from __future__ import annotations

from pathlib import Path

from scripts.gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf
from scripts.rasterize_pdf import rasterize_page
from templator import extract_template

TOLERANCE_PT = 0.5


def _basic_spec() -> RectTemplateSpec:
    return RectTemplateSpec(
        page_size=(480.0, 320.0),
        rows=3,
        columns=4,
        label_size=(72.0, 48.0),
        start=(36.0, 64.0),
        spacing=(96.0, 84.0),
    )


def _expected_centers(spec: RectTemplateSpec) -> list[tuple[float, float]]:
    width, height = spec.label_size
    start_x, start_y = spec.start
    step_x, step_y = spec.spacing

    centers: list[tuple[float, float]] = []
    for row in range(spec.rows):
        for col in range(spec.columns):
            center_x = start_x + col * step_x + width / 2.0
            center_y = start_y + row * step_y + height / 2.0
            centers.append((center_x, center_y))
    return centers


def _assert_close(actual: float, expected: float) -> None:
    diff = abs(actual - expected)
    assert (
        diff < TOLERANCE_PT
    ), f"Difference {diff} exceeds tolerance {TOLERANCE_PT} pt for value {expected}"


def _assert_template_matches(template, spec: RectTemplateSpec, *, mode: str) -> None:
    assert template is not None
    assert template.metadata.get("extraction") == mode

    expected_centers = _expected_centers(spec)
    actual_centers = list(template.iter_centers())

    assert template.grid.rows == spec.rows
    assert template.grid.columns == spec.columns
    assert template.centers_count() == len(expected_centers)
    for actual, expected in zip(actual_centers, expected_centers):
        _assert_close(actual[0], expected[0])
        _assert_close(actual[1], expected[1])

    _assert_close(template.page.width_pt, spec.page_size[0])
    _assert_close(template.page.height_pt, spec.page_size[1])

    _assert_close(template.grid.delta_x_pt, spec.spacing[0])
    _assert_close(template.grid.delta_y_pt, spec.spacing[1])

    _assert_close(template.label.width_pt, spec.label_size[0])
    _assert_close(template.label.height_pt, spec.label_size[1])

    expected_top_left = expected_centers[0]
    expected_bottom_left = expected_centers[(spec.rows - 1) * spec.columns]
    _assert_close(template.anchors.top_left_pt[0], expected_top_left[0])
    _assert_close(template.anchors.top_left_pt[1], expected_top_left[1])
    _assert_close(template.anchors.bottom_left_pt[0], expected_bottom_left[0])
    _assert_close(template.anchors.bottom_left_pt[1], expected_bottom_left[1])

    expected_columns_per_row = tuple(spec.columns for _ in range(spec.rows))
    assert template.grid.columns_per_row == expected_columns_per_row


def test_integration_vector_accuracy(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(pdf_path, spec=spec)

    template = extract_template(pdf_path, prefer_vector=True)

    _assert_template_matches(template, spec, mode="vector")


def test_integration_raster_accuracy(tmp_path: Path) -> None:
    vector_pdf = tmp_path / "source.pdf"
    raster_pdf = tmp_path / "rasterized.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(vector_pdf, spec=spec)
    rasterize_page(vector_pdf, dpi=420, pdf_path=raster_pdf)

    template = extract_template(raster_pdf, prefer_vector=True, dpi=420)

    _assert_template_matches(template, spec, mode="raster")
