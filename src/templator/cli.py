"""Command line interface for :mod:`templator`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="templator",
        description="Extract label templates or synthesise layouts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    extract_parser = subparsers.add_parser(
        "extract", help="Extract a template from a PDF or image file."
    )
    extract_parser.add_argument("source", type=Path, help="Path to the source file")
    extract_parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="Zero-based page index to analyse (default: 0)",
    )
    extract_parser.add_argument(
        "--raster",
        action="store_true",
        help="Force raster extraction even if vector data is available.",
    )
    extract_parser.set_defaults(handler=_handle_extract)

    synth_parser = subparsers.add_parser(
        "synthesise-circles",
        help="Generate a circular layout (simple or close packing).",
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
    synth_parser.set_defaults(handler=_handle_synth)

    return parser


def _handle_extract(args: argparse.Namespace) -> int:
    del args  # placeholder until the extractor is implemented
    print("templator.extract is not implemented yet", file=sys.stderr)
    return 1


def _handle_synth(args: argparse.Namespace) -> int:
    del args  # placeholder until synthesiser is implemented
    print("templator.synthesise-circles is not implemented yet", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``python -m templator`` and the console script."""

    parser = _build_parser()
    parsed = parser.parse_args(argv)
    if parsed.command is None:
        parser.print_help()
        return 0
    handler = getattr(parsed, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(parsed))


if __name__ == "__main__":  # pragma: no cover - manual execution guard
    raise SystemExit(main())

