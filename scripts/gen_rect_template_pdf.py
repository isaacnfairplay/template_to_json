"""Generate a synthetic rectangular label template PDF."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import fitz

from templator import exporters, pdf_extract

CoordSpace = tuple[float, float]


@dataclass(slots=True)
class RectTemplateSpec:
    """Configuration describing a rectangular grid layout."""

    page_size: CoordSpace
    rows: int
    columns: int
    label_size: CoordSpace
    start: CoordSpace
    spacing: CoordSpace
    corner_radius: float = 0.0

    def iter_rectangles(self) -> Iterable[tuple[float, float, float, float]]:
        width, height = self.label_size
        start_x, start_y = self.start
        step_x, step_y = self.spacing
        for row in range(self.rows):
            for col in range(self.columns):
                x0 = start_x + col * step_x
                y0 = start_y + row * step_y
                yield (x0, y0, width, height)


class MissingDependencyError(RuntimeError):
    """Raised when an optional dependency is not available."""


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _draw_with_fitz(path: Path, spec: RectTemplateSpec) -> None:
    doc = fitz.open()
    page = doc.new_page(width=spec.page_size[0], height=spec.page_size[1])
    for x0, y0, width, height in spec.iter_rectangles():
        rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
        shape = page.new_shape()
        if spec.corner_radius:
            min_side = min(width, height)
            if min_side <= 0:
                radius_fraction = 0.0
            else:
                radius_fraction = min(spec.corner_radius / min_side, 0.5)
            shape.draw_rect(rect, radius=radius_fraction)
        else:
            shape.draw_rect(rect)
        shape.finish(color=(0, 0, 0), fill=None)
        shape.commit()
    doc.save(path)
    doc.close()


def _draw_with_reportlab(path: Path, spec: RectTemplateSpec) -> None:
    try:
        from reportlab.lib.colors import black
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise MissingDependencyError(
            "The reportlab package is required for the reportlab backend."
        ) from exc

    _ensure_parent(path)
    canv = canvas.Canvas(str(path), pagesize=spec.page_size)
    canv.setStrokeColor(black)
    canv.setLineWidth(1)
    page_height = spec.page_size[1]
    for x0, y0, width, height in spec.iter_rectangles():
        # ReportLab's origin is bottom-left; mirror the Y coordinate.
        canv.roundRect(
            x0,
            page_height - (y0 + height),
            width,
            height,
            radius=spec.corner_radius,
            stroke=1,
            fill=0,
        )
    canv.showPage()
    canv.save()


def generate_rect_template_pdf(
    path: Path,
    *,
    spec: RectTemplateSpec,
    backend: str = "fitz",
) -> Path:
    """Generate a PDF for the provided rectangular layout specification."""

    path = Path(path)
    _ensure_parent(path)
    if backend == "fitz":
        _draw_with_fitz(path, spec)
    elif backend == "reportlab":
        _draw_with_reportlab(path, spec)
    else:  # pragma: no cover - defensive guard
        msg = f"Unsupported backend: {backend}"
        raise ValueError(msg)
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination PDF path.")
    parser.add_argument("--rows", type=int, default=3, help="Number of grid rows (default: 3).")
    parser.add_argument(
        "--columns", type=int, default=4, help="Number of grid columns (default: 4)."
    )
    parser.add_argument(
        "--page-width",
        type=float,
        default=612.0,
        help="Page width in points (default: 612 pt = 8.5 inches).",
    )
    parser.add_argument(
        "--page-height",
        type=float,
        default=792.0,
        help="Page height in points (default: 792 pt = 11 inches).",
    )
    parser.add_argument(
        "--label-width", type=float, default=144.0, help="Label width in points (default: 144)."
    )
    parser.add_argument(
        "--label-height",
        type=float,
        default=72.0,
        help="Label height in points (default: 72).",
    )
    parser.add_argument(
        "--start-x",
        type=float,
        default=36.0,
        help="X coordinate of the first label's top-left corner (default: 36).",
    )
    parser.add_argument(
        "--start-y",
        type=float,
        default=72.0,
        help="Y coordinate of the first label's top-left corner (default: 72).",
    )
    parser.add_argument(
        "--gap-x",
        type=float,
        default=18.0,
        help="Horizontal gap between labels in points (default: 18).",
    )
    parser.add_argument(
        "--gap-y",
        type=float,
        default=24.0,
        help="Vertical gap between labels in points (default: 24).",
    )
    parser.add_argument(
        "--corner-radius",
        type=float,
        default=6.0,
        help="Rounded corner radius in points (default: 6).",
    )
    parser.add_argument(
        "--backend",
        choices=("fitz", "reportlab"),
        default="fitz",
        help="Drawing backend to use (default: fitz).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write JSON output using templator.pdf_extract.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional path to write CSV output using templator.pdf_extract.",
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

    spec = RectTemplateSpec(
        page_size=(args.page_width, args.page_height),
        rows=args.rows,
        columns=args.columns,
        label_size=(args.label_width, args.label_height),
        start=(args.start_x, args.start_y),
        spacing=(args.label_width + args.gap_x, args.label_height + args.gap_y),
        corner_radius=args.corner_radius,
    )

    pdf_path = generate_rect_template_pdf(args.output, spec=spec, backend=args.backend)

    template = pdf_extract.extract_template(pdf_path)
    if template is None:
        parser.error("Generated PDF did not yield a detectable template.")

    if args.json is not None:
        exporters.export_json(template, args.json, coord_space=args.coord_space)
    if args.csv is not None:
        exporters.export_csv(template, args.csv, coord_space=args.coord_space)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
