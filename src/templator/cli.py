"""Command line interface for :mod:`templator`."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import exporters, geometry, image_extract, job_runner, pdf_extract, render
from .models import ExtractedTemplate


_COORD_SPACE_CHOICES: tuple[str, ...] = ("percent_width", "points", "inches", "mm")


@dataclass(slots=True)
class _ExtractionResult:
    template: ExtractedTemplate | None
    message: str | None


def _export_outputs(
    template: ExtractedTemplate,
    *,
    json_path: Path | None,
    csv_path: Path | None,
    coord_space: str,
    default_json: Path | None,
) -> list[tuple[str, Path]]:
    outputs: list[tuple[str, Path]] = []

    use_default_json = json_path is None and csv_path is None and default_json is not None
    if json_path is not None or use_default_json:
        target = json_path or default_json
        if target is None:  # pragma: no cover - defensive guard
            raise ValueError("JSON output target could not be determined.")
        outputs.append(("json", exporters.export_json(template, target, coord_space=coord_space)))

    if csv_path is not None:
        outputs.append(("csv", exporters.export_csv(template, csv_path, coord_space=coord_space)))

    if not outputs and default_json is not None:
        outputs.append(("json", exporters.export_json(template, default_json, coord_space=coord_space)))

    return outputs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="templator",
        description=(
            "Extract label templates, synthesise circle layouts, or render jobs to PDF."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="Extract a template from a PDF or rasterised page."
    )
    extract_parser.add_argument("source", type=Path, help="Path to the source PDF or image")
    extract_parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="Zero-based page index to analyse (default: 0)",
    )
    extract_parser.add_argument(
        "--mode",
        choices=("auto", "vector", "raster"),
        default="auto",
        help="Extraction strategy: vector first with raster fallback (auto), vector-only, or raster-only.",
    )
    extract_parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI used for raster extraction (default: 200).",
    )
    extract_parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write JSON output (percent_width by default).",
    )
    extract_parser.add_argument(
        "--csv",
        type=Path,
        help="Optional path to write CSV output (percent_width by default).",
    )
    extract_parser.add_argument(
        "--coord-space",
        choices=_COORD_SPACE_CHOICES,
        default="percent_width",
        help="Coordinate space for outputs (default: percent_width).",
    )
    extract_parser.set_defaults(handler=_handle_extract)

    synth_parser = subparsers.add_parser(
        "synthesize-circles",
        help="Generate a circular layout using the simple or close-packed lattice.",
    )
    synth_parser.add_argument(
        "layout",
        choices=("simple", "close"),
        help="Desired circle lattice pattern.",
    )
    synth_parser.add_argument(
        "--page-width",
        type=float,
        required=True,
        help="Page width in points.",
    )
    synth_parser.add_argument(
        "--page-height",
        type=float,
        required=True,
        help="Page height in points.",
    )
    synth_parser.add_argument(
        "--diameter",
        type=float,
        required=True,
        help="Circle diameter in points.",
    )
    synth_parser.add_argument(
        "--margin",
        type=float,
        nargs=4,
        metavar=("TOP", "RIGHT", "BOTTOM", "LEFT"),
        default=(0.0, 0.0, 0.0, 0.0),
        help="Page margins in points (top right bottom left).",
    )
    synth_parser.add_argument(
        "--gap",
        type=float,
        default=0.0,
        help="Gap between circles in points (default: 0).",
    )
    synth_parser.add_argument(
        "--max-cols",
        type=int,
        help="Optional limit on the number of columns to generate.",
    )
    synth_parser.add_argument(
        "--max-rows",
        type=int,
        help="Optional limit on the number of rows to generate.",
    )
    synth_parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write JSON output (percent_width by default).",
    )
    synth_parser.add_argument(
        "--csv",
        type=Path,
        help="Optional path to write CSV output (percent_width by default).",
    )
    synth_parser.add_argument(
        "--coord-space",
        choices=_COORD_SPACE_CHOICES,
        default="percent_width",
        help="Coordinate space for outputs (default: percent_width).",
    )
    synth_parser.set_defaults(handler=_handle_synth)

    render_parser = subparsers.add_parser(
        "render", help="Render a template-driven job specification to PDF."
    )
    render_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to a template JSON file produced by templator export tools.",
    )
    render_parser.add_argument(
        "--job",
        type=Path,
        required=True,
        help="Path to a job specification JSON file containing render instructions.",
    )
    render_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination PDF path for the rendered output.",
    )
    render_parser.set_defaults(handler=_handle_render)

    run_job_parser = subparsers.add_parser(
        "run-job",
        help="Execute a batch rendering job described by a JSON or YAML specification.",
    )
    run_job_parser.add_argument(
        "spec",
        type=Path,
        help="Path to the job specification file (JSON or YAML).",
    )
    run_job_parser.set_defaults(handler=_handle_run_job)

    return parser


def _try_vector_extraction(path: Path, page: int) -> _ExtractionResult:
    try:
        template = pdf_extract.extract_template(path, page=page)
    except Exception as exc:  # pragma: no cover - exercised via smoke tests
        return _ExtractionResult(template=None, message=f"Vector extraction failed: {exc}")
    if template is None:
        return _ExtractionResult(template=None, message="Vector extraction yielded no template.")
    return _ExtractionResult(template=template, message=None)


def _try_raster_extraction(path: Path, page: int, dpi: int) -> _ExtractionResult:
    try:
        template = image_extract.extract_template(path, page=page, dpi=dpi)
    except Exception as exc:  # pragma: no cover - exercised via smoke tests
        return _ExtractionResult(template=None, message=f"Raster extraction failed: {exc}")
    if template is None:
        return _ExtractionResult(template=None, message="Raster extraction yielded no template.")
    return _ExtractionResult(template=template, message=None)


def _handle_extract(args: argparse.Namespace) -> int:
    source: Path = args.source
    mode: str = args.mode
    page: int = args.page
    dpi: int = args.dpi

    template = None
    vector_result: _ExtractionResult | None = None
    raster_result: _ExtractionResult | None = None

    if mode in {"auto", "vector"}:
        vector_result = _try_vector_extraction(source, page)
        template = vector_result.template
        if template is None and mode == "vector":
            if vector_result.message:
                print(vector_result.message, file=sys.stderr)
            return 1

    if template is None and mode in {"auto", "raster"}:
        raster_result = _try_raster_extraction(source, page, dpi)
        template = raster_result.template
        if template is None and mode == "raster":
            if raster_result.message:
                print(raster_result.message, file=sys.stderr)
            return 1

    if template is None:
        messages = [
            result.message
            for result in (vector_result, raster_result)
            if result is not None and result.message
        ]
        for message in messages:
            print(message, file=sys.stderr)
        print("No template could be extracted from the provided source.", file=sys.stderr)
        return 1

    default_json = source.with_suffix(".json")
    outputs = _export_outputs(
        template,
        json_path=args.json,
        csv_path=args.csv,
        coord_space=args.coord_space,
        default_json=default_json,
    )

    for kind, path in outputs:
        print(f"Wrote {kind.upper()} output to {path}")

    return 0


def _handle_synth(args: argparse.Namespace) -> int:
    layout: str = args.layout
    page_w: float = args.page_width
    page_h: float = args.page_height
    diameter: float = args.diameter
    margin_values = tuple(float(value) for value in args.margin)
    margin: tuple[float, float, float, float] = (
        margin_values[0],
        margin_values[1],
        margin_values[2],
        margin_values[3],
    )

    template = geometry.synthesize_circles(
        layout,
        page_w_pt=page_w,
        page_h_pt=page_h,
        diameter_pt=diameter,
        margin_pt=margin,
        gap_pt=args.gap,
        max_cols=args.max_cols,
        max_rows=args.max_rows,
    )

    default_json = Path.cwd() / f"templator-circles-{layout}.json"
    outputs = _export_outputs(
        template,
        json_path=args.json,
        csv_path=args.csv,
        coord_space=args.coord_space,
        default_json=default_json,
    )

    for kind, path in outputs:
        print(f"Wrote {kind.upper()} output to {path}")

    return 0


def _handle_render(args: argparse.Namespace) -> int:
    template_path: Path = args.template
    job_path: Path = args.job
    output_path: Path = args.output

    spec = render.RenderSpec.from_json(template_path, job_path)
    result_path = render.render_to_pdf(spec, output_path)
    print(f"Wrote PDF output to {result_path}")

    return 0


def _handle_run_job(args: argparse.Namespace) -> int:
    spec_path: Path = args.spec

    try:
        spec = job_runner.load_job_spec(spec_path)
    except Exception as exc:  # pragma: no cover - exercised in CLI tests
        print(f"Failed to load job specification: {exc}", file=sys.stderr)
        return 1

    runner = job_runner.JobRunner(spec.jobs, config=spec.config)
    report = runner.run()

    for result in report.results:
        status = "SUCCESS" if result.success else "FAILED"
        destination = result.output_path or result.definition.output_path
        print(f"[{status}] {result.definition.display_name} -> {destination}")
        if not result.success and result.error:
            print(f"    error: {result.error}", file=sys.stderr)

    summary = report.summary()
    print(
        "Completed {total} job(s): {succeeded} succeeded, {failed} failed.".format(
            **summary
        )
    )

    return 0 if not report.failed else 1


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``python -m templator`` and the console script."""

    parser = _build_parser()
    parsed = parser.parse_args(argv)
    handler = getattr(parsed, "handler")
    return int(handler(parsed))


if __name__ == "__main__":  # pragma: no cover - manual execution guard
    raise SystemExit(main())

