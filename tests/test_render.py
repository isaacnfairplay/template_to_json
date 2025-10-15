from __future__ import annotations

import json
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest
from PIL import Image

from templator import exporters, render
from templator.models import AnchorPoints, ExtractedTemplate, GridMetrics, LabelGeometry, PageMetrics


def _build_template() -> ExtractedTemplate:
    page = PageMetrics(width_pt=200.0, height_pt=120.0)
    grid = GridMetrics(
        kind="rectangular",
        rows=1,
        columns=2,
        delta_x_pt=80.0,
        delta_y_pt=40.0,
    )
    label = LabelGeometry(shape="rectangle", width_pt=80.0, height_pt=40.0)
    anchors = AnchorPoints(top_left_pt=(20.0, 100.0), bottom_left_pt=(20.0, 20.0))
    centres = [(60.0, 60.0), (140.0, 60.0)]
    return ExtractedTemplate(
        page=page,
        grid=grid,
        label=label,
        anchors=anchors,
        centers_pt=centres,
    )


def test_render_to_pdf_places_elements(tmp_path: Path) -> None:
    template = _build_template()
    red_symbol = Image.new("RGBA", (20, 20), (255, 0, 0, 255))

    items = [
        render.RenderItem(
            text_fields=[
                render.TextFieldSpec(
                    text="Alpha",
                    font_size=12.0,
                    align_x="center",
                    align_y="center",
                    offset=(5.0, 0.0),
                    coord_space="percent_width",
                    box_size=(40.0, 20.0),
                    box_coord_space="points",
                )
            ]
        ),
        render.RenderItem(
            text_fields=[
                render.TextFieldSpec(
                    text="Beta",
                    font_size=12.0,
                    align_x="center",
                    align_y="center",
                    offset=(0.0, -5.0),
                    coord_space="percent_width",
                    box_size=(40.0, 20.0),
                    box_coord_space="points",
                )
            ],
            symbols=[
                render.SymbolSpec(
                    image=red_symbol,
                    align_x="center",
                    align_y="center",
                    offset=(0.0, 5.0),
                    coord_space="percent_width",
                    box_size=(10.0, 10.0),
                    box_coord_space="percent_width",
                )
            ],
        ),
    ]

    spec = render.RenderSpec(template=template, items=items, coord_space="percent_width")
    output = tmp_path / "job.pdf"
    render.render_to_pdf(spec, output)

    doc = fitz.open(output)
    try:
        page = doc[0]
        assert page.rect.width == pytest.approx(template.page.width_pt)
        assert page.rect.height == pytest.approx(template.page.height_pt)

        alpha_rects = page.search_for("Alpha")
        beta_rects = page.search_for("Beta")
        assert alpha_rects, "Expected Alpha text to be present"
        assert beta_rects, "Expected Beta text to be present"

        alpha_rect = alpha_rects[0]
        beta_rect = beta_rects[0]

        alpha_center = ((alpha_rect.x0 + alpha_rect.x1) / 2.0, (alpha_rect.y0 + alpha_rect.y1) / 2.0)
        beta_center = ((beta_rect.x0 + beta_rect.x1) / 2.0, (beta_rect.y0 + beta_rect.y1) / 2.0)

        assert alpha_center[0] == pytest.approx(70.0, abs=1.0)
        assert alpha_center[1] == pytest.approx(60.0, abs=1.0)
        assert beta_center[0] == pytest.approx(140.0, abs=1.0)
        assert beta_center[1] == pytest.approx(50.0, abs=1.5)

        clip_rect = fitz.Rect(132.0, 62.0, 148.0, 78.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=clip_rect)
        red_channel = pix.samples[0::pix.n]
        blue_channel = pix.samples[2::pix.n]
        assert max(red_channel) > max(blue_channel)
    finally:
        doc.close()


def test_render_spec_from_json(tmp_path: Path) -> None:
    template = _build_template()
    template_path = tmp_path / "template.json"
    exporters.export_json(template, template_path, coord_space="percent_width")

    symbol_path = tmp_path / "symbol.png"
    Image.new("RGBA", (10, 10), (0, 0, 255, 255)).save(symbol_path)

    job_data = {
        "coord_space": "percent_width",
        "items": [
            {
                "text_fields": [
                    {
                        "text": "Gamma",
                        "font_size": 10,
                        "offset": [2.0, 0.0],
                    }
                ]
            },
            {
                "text_fields": [
                    {
                        "text": "Delta",
                        "font_size": 10,
                        "offset": [0.0, 0.0],
                        "box_size": [30.0, 15.0],
                    }
                ],
                "symbols": [
                    {
                        "image_path": symbol_path.name,
                        "box_size": [8.0, 8.0],
                        "box_coord_space": "percent_width",
                    }
                ],
            },
        ],
    }

    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job_data))

    spec = render.RenderSpec.from_json(template_path, job_path)
    assert spec.coord_space == "percent_width"
    assert len(spec.items) == 2
    assert spec.items[0].text_fields[0].text == "Gamma"
    assert spec.items[1].symbols, "Expected symbol entry to be parsed"

    output_path = tmp_path / "job.pdf"
    render.render_to_pdf(spec, output_path)
    assert output_path.exists()
