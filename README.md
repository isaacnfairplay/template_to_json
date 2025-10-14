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
   The CLI exposes `extract` and `synthesize-circles` subcommands. `extract`
   performs vector extraction with an automatic raster fallback and writes
   exporter-backed outputs (defaulting to `percent_width` JSON). The
   `synthesize-circles` helper generates circular layouts via the geometry
   synthesiser with the same exporter defaults.

## Library Goals

- **Extract** rectangular and circular label layouts from PDFs and raster images using deterministic geometry inference.
- **Represent** geometry in multiple coordinate systems, including the percent-of-page-width convention described below, for seamless printing pipelines.
- **Export** templates to machine-usable formats (JSON, CSV) and support future synthesis of circle layouts and printable payloads.

## Percent-of-Page-Width Convention

Templator expresses template coordinates in a custom `percent_of_width` space where both the x and y coordinates are scaled by the page width. For a point `(x_pt, y_pt)` on a page with width `page_w_pt`, the scaled coordinates are `(x_pct, y_pct) = (100 * x_pt / page_w_pt, 100 * y_pt / page_w_pt)`. This ensures consistent downstream alignment with printing systems that normalize everything to page width.

## Exporting Templates

Templator exposes helpers for writing extracted or synthesised templates to disk:

```python
from templator.exporters import export_csv, export_json

export_json(template, "labels.json")
export_csv(template, "labels.csv", coord_space="mm")
```

Both functions default to the `percent_width` coordinate space, preserving the contract that *both* x and y values are scaled by the page width. When alternative spaces are required, pass `coord_space="points"`, `"inches"`, or `"mm"`. Outputs are deterministic and sorted row-major (top-to-bottom, left-to-right) so repeated exports of the same template produce identical files—critical for regression testing and downstream diffing.

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

## Utility Scripts

Templator ships with helper scripts for generating demo assets and exercising the
extractors. They are invoked with `python` (or `uv run python`) and emit files in
the working directory unless paths are provided.

### `scripts/gen_rect_template_pdf.py`

Generate a synthetic rectangular grid as a vector PDF and immediately run the
vector extractor against the result. By default, it uses PyMuPDF for drawing,
but the optional `reportlab` dependency enables a ReportLab backend:

```bash
uv run python scripts/gen_rect_template_pdf.py output.pdf --json output.json
uv pip install reportlab  # optional backend
uv run python scripts/gen_rect_template_pdf.py output.pdf --backend reportlab
```

### `scripts/rasterize_pdf.py`

Render a PDF page to an image and optionally re-embed it into a rasterised PDF.
If no output paths are supplied, a PNG is created next to the source PDF. Both
the PNG and raster PDF work with the raster extractor:

```bash
uv run python scripts/rasterize_pdf.py template.pdf --pdf raster.pdf --json raster.json
```

### `scripts/demo_extract.py`

Run an end-to-end demo that generates a synthetic PDF, exports the vector
extraction to JSON, rasterises the document, and exports the raster extraction.
The demo writes all artefacts to `./demo_output` by default:

```bash
uv run python scripts/demo_extract.py --output-dir demo_output
```

### Optional dependencies

* `reportlab` – enables the `--backend reportlab` mode in
  `gen_rect_template_pdf.py` for high-quality PDF generation:
  ```bash
  uv pip install reportlab
  ```
