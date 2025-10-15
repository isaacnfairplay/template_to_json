"""Top-level package for the :mod:`templator` library.

The package exposes high-level modules that implement template extraction,
geometry helpers, and data exporters.  Importing the modules here keeps
``from templator import geometry`` style imports working even before the
implementation matures.
"""

from . import cli, exporters, geometry, image_extract, models, pdf_extract, render

__all__ = [
    "cli",
    "exporters",
    "geometry",
    "image_extract",
    "models",
    "pdf_extract",
    "render",
]


__version__ = "0.0.1"
