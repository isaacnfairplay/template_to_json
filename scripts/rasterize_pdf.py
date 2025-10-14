"""Rasterise a PDF page and optionally embed it into a new PDF."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import fitz

from templator import exporters, image_extract


@dataclass(slots=True)
class RasterizationPaths:
    """Container for generated raster outputs."""

    png_path: Path | None
    pdf_path: Path | None


def _ensure_parent(path: Path) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


def rasterize_page(
    source: Path,
    *,
    page: int = 0,
    dpi: int = 200,
    png_path: Path | None = None,
    pdf_path: Path | None = None,
) -> RasterizationPaths:
    """Rasterise a single page of the PDF and write outputs."""

    source = Path(source)
    if not source.exists():
        msg = f"The provided PDF path does not exist: {source}"
        raise FileNotFoundError(msg)

    if png_path is None and pdf_path is None:
        msg = "At least one of png_path or pdf_path must be provided."
        raise ValueError(msg)

    png_path = Path(png_path) if png_path is not None else None
    pdf_path = Path(pdf_path) if pdf_path is not None else None

    for target in (png_path, pdf_path):
        if target is not None:
            _ensure_parent(target)

    with fitz.open(source) as document:
        if page < 0 or page >= document.page_count:
            msg = f"Requested page index {page} outside range 0..{document.page_count - 1}."
            raise IndexError(msg)
        pdf_page = document[page]
        zoom = dpi / 72.0
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        image_bytes = pixmap.tobytes("png")
        page_rect = pdf_page.rect

    if png_path is not None:
        png_path.write_bytes(image_bytes)

    if pdf_path is not None:
        new_doc = fitz.open()
        new_page = new_doc.new_page(width=page_rect.width, height=page_rect.height)
        new_page.insert_image(new_page.rect, stream=image_bytes)
        new_doc.save(pdf_path)
        new_doc.close()

    return RasterizationPaths(png_path=png_path, pdf_path=pdf_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Input PDF file to rasterise.")
    parser.add_argument("--page", type=int, default=0, help="Zero-based page index (default: 0).")
    parser.add_argument("--dpi", type=int, default=220, help="Rendering DPI (default: 220).")
    parser.add_argument("--png", type=Path, help="Optional path to write the PNG raster.")
    parser.add_argument(
        "--pdf",
        type=Path,
        help="Optional path to write a PDF with the rasterised image embedded.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write JSON output using templator.image_extract.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional path to write CSV output using templator.image_extract.",
    )
    parser.add_argument(
        "--coord-space",
        choices=("percent_width", "points", "inches", "mm"),
        default="percent_width",
        help="Coordinate space for exports (default: percent_width).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    png_target = args.png
    pdf_target = args.pdf
    if png_target is None and pdf_target is None:
        png_target = args.source.with_suffix(".png")

    outputs = rasterize_page(
        args.source,
        page=args.page,
        dpi=args.dpi,
        png_path=png_target,
        pdf_path=pdf_target,
    )

    target_pdf = outputs.pdf_path or args.source
    if args.json is not None or args.csv is not None:
        template = image_extract.extract_template(target_pdf, page=args.page, dpi=args.dpi)
        if template is None:
            parser.error("Raster extraction yielded no template to export.")
        if args.json is not None:
            exporters.export_json(template, args.json, coord_space=args.coord_space)
        if args.csv is not None:
            exporters.export_csv(template, args.csv, coord_space=args.coord_space)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
