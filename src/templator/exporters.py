"""Export utilities for :mod:`templator` templates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import CoordinateSpace, ExtractedTemplate


def _normalise_path(path: str | Path) -> Path:
    result = Path(path)
    if not result.parent.exists():
        result.parent.mkdir(parents=True, exist_ok=True)
    return result


def export_json(
    template: ExtractedTemplate,
    path: str | Path,
    *,
    coord_space: CoordinateSpace = "percent_width",
    indent: int = 2,
) -> Path:
    """Serialise the template to JSON."""

    target = _normalise_path(path)
    payload = template.to_dict(coord_space)
    target.write_text(json.dumps(payload, indent=indent, sort_keys=True))
    return target


def export_csv(
    template: ExtractedTemplate,
    path: str | Path,
    *,
    coord_space: CoordinateSpace = "percent_width",
) -> Path:
    """Serialise template centres to CSV."""

    target = _normalise_path(path)
    centers = template.centers(coord_space)
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

