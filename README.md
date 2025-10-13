# Templator

Templator is a Python 3.12 library focused on extracting label templates from PDF and image sources and preparing them for high-volume printing workflows. The project follows the mission outlined in `/AGENTS.md`: deterministic template extraction, optional raster fallback, and geometry exports expressed in both page points and a custom percent-of-page-width space.

## Quickstart (with `uv`)

1. Install [uv](https://github.com/astral-sh/uv) if you do not already have it.
2. Create and activate a virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
3. Install Templator and its core dependencies:
   ```bash
   uv pip install -e .
   ```
4. (Optional) Install the OpenCV extras for advanced raster extraction support:
   ```bash
   uv pip install -e .[opencv]
   ```
5. Run the command-line interface to confirm the entry point is available:
   ```bash
   uv run templator --help
   ```
   The CLI exposes `extract` and `synthesise-circles` subcommands that document
   the planned workflow. Both commands currently report that their
   implementations are forthcoming.

## Library Goals

- **Extract** rectangular and circular label layouts from PDFs and raster images using deterministic geometry inference.
- **Represent** geometry in multiple coordinate systems, including the percent-of-page-width convention described below, for seamless printing pipelines.
- **Export** templates to machine-usable formats (JSON, CSV) and support future synthesis of circle layouts and printable payloads.

## Percent-of-Page-Width Convention

Templator expresses template coordinates in a custom `percent_of_width` space where both the x and y coordinates are scaled by the page width. For a point `(x_pt, y_pt)` on a page with width `page_w_pt`, the scaled coordinates are `(x_pct, y_pct) = (100 * x_pt / page_w_pt, 100 * y_pt / page_w_pt)`. This ensures consistent downstream alignment with printing systems that normalize everything to page width.

## Repository Layout

```
.
├── pyproject.toml
├── src/templator/
│   ├── __init__.py
│   ├── cli.py
│   ├── exporters.py
│   ├── geometry.py
│   ├── image_extract.py
│   ├── models.py
│   └── pdf_extract.py
├── scripts/
└── tests/
```

Scripts in `scripts/` are reserved for demos and reproducible experiments, while `tests/` will collect unit and integration tests as the extractor and exporter implementations grow.
