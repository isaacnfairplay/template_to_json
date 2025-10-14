"""End-to-end demo for generating and extracting a template."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from templator import exporters, image_extract, pdf_extract

from .gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf
from .rasterize_pdf import rasterize_page


def _default_spec() -> RectTemplateSpec:
    return RectTemplateSpec(
        page_size=(612.0, 792.0),
        rows=3,
        columns=4,
        label_size=(144.0, 72.0),
        start=(48.0, 96.0),
        spacing=(162.0, 100.0),
        corner_radius=6.0,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("demo_output"),
        help="Directory to write demo artifacts (default: ./demo_output).",
    )
    parser.add_argument(
        "--backend",
        choices=("fitz", "reportlab"),
        default="fitz",
        help="Rendering backend for the generator script (default: fitz).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=220,
        help="DPI used for rasterisation and raster extraction (default: 220).",
    )
    parser.add_argument(
        "--coord-space",
        choices=("percent_width", "points", "inches", "mm"),
        default="percent_width",
        help="Coordinate space for exported files (default: percent_width).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / "demo_grid.pdf"
    json_vector_path = output_dir / "demo_grid_vector.json"
    raster_pdf_path = output_dir / "demo_grid_raster.pdf"
    json_raster_path = output_dir / "demo_grid_raster.json"

    spec = _default_spec()
    generate_rect_template_pdf(pdf_path, spec=spec, backend=args.backend)

    template_vector = pdf_extract.extract_template(pdf_path)
    if template_vector is None:
        parser.error("Vector extraction failed for the generated demo PDF.")
    exporters.export_json(template_vector, json_vector_path, coord_space=args.coord_space)

    rasterize_page(pdf_path, dpi=args.dpi, pdf_path=raster_pdf_path)
    template_raster = image_extract.extract_template(raster_pdf_path, dpi=args.dpi)
    if template_raster is None:
        parser.error("Raster extraction failed for the rasterised demo PDF.")
    exporters.export_json(template_raster, json_raster_path, coord_space=args.coord_space)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
