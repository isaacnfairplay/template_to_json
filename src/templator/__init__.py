"""Top-level package for the :mod:`templator` library.

The package exposes high-level modules that implement template extraction,
geometry helpers, and data exporters. Importing the modules here keeps
``from templator import geometry`` style imports working even before the
implementation matures.
"""

from __future__ import annotations

import logging
from os import PathLike
from pathlib import Path

from . import cli, encoders, exporters, geometry, image_extract, models, pdf_extract, render

__all__ = [
    "cli",
    "encoders",
    "exporters",
    "geometry",
    "image_extract",
    "models",
    "pdf_extract",
    "render",
    "extract_template",
]

logger = logging.getLogger(__name__)


def extract_template(
    path: str | PathLike[str],
    page: int = 0,
    *,
    prefer_vector: bool = True,
    dpi: int = 200,
) -> models.ExtractedTemplate | None:
    """Extract a template using the configured vector/raster preference.

    The helper orchestrates the vector and raster extraction backends to match
    the public API described in ``/AGENTS.md``. If ``prefer_vector`` is set
    to :data:`True`, the function attempts the vector pipeline first and falls
    back to the raster pipeline only if vector extraction returns ``None`` or
    raises an exception. When ``prefer_vector`` is :data:`False`, the order of
    attempts is reversed. Fatal errors such as missing files or out-of-range
    page requests are propagated to the caller.
    """

    if dpi <= 0:
        msg = f"DPI must be a positive integer. Received {dpi!r}."
        raise ValueError(msg)

    source = Path(path)

    attempts = ("vector", "raster") if prefer_vector else ("raster", "vector")
    for mode in attempts:
        if mode == "vector":
            try:
                template = pdf_extract.extract_template(source, page=page)
            except (FileNotFoundError, IndexError):
                raise
            except Exception as exc:  # pragma: no cover - debug logging only
                logger.debug("Vector extraction failed for %s: %s", source, exc, exc_info=exc)
                continue
        else:
            try:
                template = image_extract.extract_template(source, page=page, dpi=dpi)
            except (FileNotFoundError, IndexError):
                raise
            except Exception as exc:  # pragma: no cover - debug logging only
                logger.debug("Raster extraction failed for %s: %s", source, exc, exc_info=exc)
                continue

        if template is not None:
            return template

    return None


__version__ = "0.0.1"
