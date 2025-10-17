from __future__ import annotations

from pathlib import Path

import pytest

from scripts.gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf
from scripts.rasterize_pdf import rasterize_page

from templator import extract_template


def _basic_spec() -> RectTemplateSpec:
    return RectTemplateSpec(
        page_size=(480.0, 320.0),
        rows=3,
        columns=4,
        label_size=(72.0, 48.0),
        start=(36.0, 64.0),
        spacing=(96.0, 84.0),
    )


def _assert_core_metrics(template, spec: RectTemplateSpec) -> None:
    assert template is not None
    assert template.grid.rows == spec.rows
    assert template.grid.columns == spec.columns
    assert template.centers_count() == spec.rows * spec.columns


def test_highlevel_extract_prefers_vector(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(pdf_path, spec=spec)

    template = extract_template(pdf_path, prefer_vector=True)

    _assert_core_metrics(template, spec)
    assert template.metadata.get("extraction") == "vector"


def test_highlevel_extract_falls_back_to_raster(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    raster_pdf_path = tmp_path / "vector_raster.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(pdf_path, spec=spec)
    rasterize_page(pdf_path, dpi=210, pdf_path=raster_pdf_path)

    template = extract_template(raster_pdf_path, prefer_vector=True, dpi=210)

    _assert_core_metrics(template, spec)
    assert template.metadata.get("extraction") == "raster"


def test_highlevel_extract_raster_first(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(pdf_path, spec=spec)

    template = extract_template(pdf_path, prefer_vector=False, dpi=190)

    _assert_core_metrics(template, spec)
    assert template.metadata.get("extraction") == "raster"


def test_highlevel_extract_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError):
        extract_template(missing)


def test_highlevel_extract_invalid_dpi(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    spec = _basic_spec()
    generate_rect_template_pdf(pdf_path, spec=spec)

    with pytest.raises(ValueError):
        extract_template(pdf_path, dpi=0)
