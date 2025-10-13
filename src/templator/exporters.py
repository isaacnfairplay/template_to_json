"""Export utilities for :mod:`templator` templates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from . import geometry

from .models import CoordinateSpace, ExtractedTemplate


_COORDINATE_SPACES: tuple[CoordinateSpace, ...] = (
    "percent_width",
    "points",
    "inches",
    "mm",
)


def _normalise_path(path: str | Path) -> Path:
    result = Path(path)
    if not result.parent.exists():
        result.parent.mkdir(parents=True, exist_ok=True)
    return result


def _validate_coord_space(coord_space: CoordinateSpace) -> CoordinateSpace:
    if coord_space not in _COORDINATE_SPACES:
        msg = (
            "Unsupported coordinate space. "
            f"Expected one of {_COORDINATE_SPACES!r}, received {coord_space!r}."
        )
        raise ValueError(msg)
    return coord_space


def export_json(
    template: ExtractedTemplate,
    path: str | Path,
    *,
    coord_space: CoordinateSpace = "percent_width",
    indent: int = 2,
) -> Path:
    """Serialise the template to JSON."""

    coord_space = _validate_coord_space(coord_space)
    target = _normalise_path(path)
    centers = geometry.ensure_row_major(template.centers(coord_space))
    payload = template.to_dict(coord_space)
    payload["centers"] = centers
    target.write_text(json.dumps(payload, indent=indent, sort_keys=True))
    return target


def export_csv(
    template: ExtractedTemplate,
    path: str | Path,
    *,
    coord_space: CoordinateSpace = "percent_width",
) -> Path:
    """Serialise template centres to CSV."""

    coord_space = _validate_coord_space(coord_space)
    target = _normalise_path(path)
    centers = geometry.ensure_row_major(template.centers(coord_space))
    with target.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "coord_space"])
        for x, y in centers:
            writer.writerow([f"{x:.6f}", f"{y:.6f}", coord_space])
    return target


def export_centers(centers: Iterable[tuple[float, float]], path: str | Path) -> Path:
    """Write bare centres to a CSV file.

    This helper exists for lightweight debugging scripts that do not need the
    full :class:`~templator.models.ExtractedTemplate` dataclass.
    """

    target = _normalise_path(path)
    with target.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y"])
        for x, y in centers:
            writer.writerow([f"{x:.6f}", f"{y:.6f}"])
    return target

