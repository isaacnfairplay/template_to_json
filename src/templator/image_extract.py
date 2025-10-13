"""Raster-based template extraction from rendered page images."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import ExtractedTemplate


def extract_template(
    path: str | Path,
    page: int = 0,
    *,
    dpi: int = 200,
) -> Optional[ExtractedTemplate]:
    """Extract a label template from a rasterised PDF page or source image."""

    raise NotImplementedError(
        "Raster extraction is not yet implemented. "
        "The function exists to document the public interface."
    )

