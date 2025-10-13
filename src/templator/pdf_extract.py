"""Vector-based template extraction from PDF files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import ExtractedTemplate


def extract_template(
    path: str | Path,
    page: int = 0,
    *,
    prefer_vector: bool = True,
    dpi: int = 200,
) -> Optional[ExtractedTemplate]:
    """Extract a label template from the provided PDF file.

    The function is currently a placeholder; it documents the intended API and
    raises :class:`NotImplementedError` until the vector extraction
    implementation lands.
    """

    raise NotImplementedError(
        "PDF vector extraction is not yet implemented. "
        "This placeholder documents the intended interface."
    )

