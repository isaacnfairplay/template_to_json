# agents.md — Implementation Plan & Agent Guidelines (Enterprise Label Templates & Printing)

> Serious, truthful, correct, and designed for performance. This doc is the single source of truth for building, testing, and evolving a **template extractor** & **printing pipeline** for enterprise label generation. It also lays out agent guidelines and a progress tracker.

---

## 1) Mission & Scope

**Mission:**
Build a Python library that (a) **extracts** rectangular and circular label templates from PDFs/images into a structured, machine-usable format, and (b) can **synthesize** circle layouts (simple grid & close-packing/hex). The library returns all geometry both in **original PDF points** and in a **percent-of-page-width coordinate space** (nonstandard by design: *y is also scaled by page width*).

**Future direction:**
Extend the library into a **label-printing API** capable of **bulk or serialized** label generation with **barcodes, QR, and Data Matrix**, plus text rendering, layouting, and job tracking.

**Non-Goals (for now):**

* End-user GUI.
* Vendor-specific printer drivers or spooler integrations.

---

## 2) Architecture (high-level)

```mermaid
flowchart LR
    A[Input: PDF or Image] --> B{Vector pass?\n(PyMuPDF draws)}
    B -- yes --> C[Rect/Circle extraction\n(rects, centers, radius?)]
    B -- no  --> D[Raster pass: render->edges->morphology->CC\n(medians, row/col clustering)]
    C --> E[Grid inference: rows/cols, Δx, Δy,\nTL/BL anchors, size]
    D --> E
    E --> F[Exporters: JSON, CSV\n(percent_of_width | points | inches | mm)]
    G[Synthesizers: circle simple/hex] --> F

    subgraph Future Printing API
      H[Payload: text + barcode/QR/DM + styles]
      I[Layout engine: place content on centers]
      J[PDF builder + assets]
      K[Bulk/Serialized job runner]
    end
    F --> H
    H --> I --> J --> K
```

**Key invariants**

* **Deterministic** outputs: sorting is row-major (top→bottom, left→right).
* **Minimal deps** by default; vector pass first; fast raster fallback.
* **Percent-of-width** space for drop-in printing pipelines; points/inches/mm for interoperability.

---

## 3) Modules & Responsibilities

* `templator.models`

  * `ExtractedTemplate`: dataclass modeling page size, grid, spacings, label geometry, anchors, and full center list (in points).
* `templator.geometry`

  * Unit conversions; coordinate transforms; circle lattice math (simple & close-packing).
* `templator.pdf_extract`

  * **Vector pass**: parse drawings (rectangles; optional rounded corners), cluster into rows, infer grid, spacings, anchors, and size medians.
* `templator.image_extract`

  * **Raster fallback**: render page → edge map → morphology → connected components → box filtering → clustering → medians; map back to points by DPI scale.
* `templator.exporters`

  * JSON/CSV writers in **percent_of_width** (y scaled by width) and **points/inches/mm**.
* `templator.cli`

  * `extract` (PDF→template), `synthesize-circles` (simple/hex layouts).
* **Future**: `templator.render`

  * PDF compositor for text + barcodes/QR/Data Matrix + images.
* **Future**: `templator.encoders`

  * Pluggable **encoders** for Code-128/Code-39/EAN (e.g., `python-barcode`), QR (e.g., `segno` or `qrcode`), Data Matrix (candidate encoders; select pure-Python or wheel-available libs).

---

## 4) Public API (initial)

```python
def extract_template(path: str | os.PathLike,
                     page: int = 0,
                     prefer_vector: bool = True,
                     dpi: int = 200) -> ExtractedTemplate | None: ...

def synthesize_circles(layout: Literal["simple","close"],
                       page_w_pt: float, page_h_pt: float,
                       diameter_pt: float,
                       margin_pt: tuple[float, float, float, float],
                       gap_pt: float = 0.0,
                       max_cols: int | None = None,
                       max_rows: int | None = None) -> ExtractedTemplate

def export_json(template: ExtractedTemplate,
                path: str,
                coord_space: Literal["percent_width","points","inches","mm"] = "percent_width") -> None

def export_csv(template: ExtractedTemplate,
               path: str,
               coord_space: Literal["percent_width","points","inches","mm"] = "percent_width") -> None
```

**Coordinate convention:**
`percent_width`: `(x%, y%) = (100*x/page_w, 100*y/page_w)` — **y scaled by page width** *(intentional, for downstream alignment)*.

---

## 5) Printing API (future phases)

**Goals**

* **Bulk** and **serialized** print modes.
* Text styling (font, size, kerning, wrap), per-label overrides.
* Barcode/QR/Data Matrix render plugins (choose encoders with reliable wheels across OSes).
* Page composition to PDF with precise placement, optional cropping/bleed.

**Renderer contract**

```python
@dataclass
class RenderSpec:
    template: ExtractedTemplate
    items: list[dict]  # one per label center, supports text fields and encoded symbols
    coord_space: Literal["percent_width","points","inches","mm"]  # accepted inputs
    # styling, fonts, per-field offsets, alignment, etc.

def render_to_pdf(spec: RenderSpec, out_path: str) -> None: ...
```

**Encoding plugin interface**

```python
class SymbolEncoder(Protocol):
    def render(self, payload: str) -> "PIL.Image.Image": ...
```

* **Candidates** to evaluate for *encoding*:

  * **QR**: `segno` (pure Python), `qrcode` (Pillow).
  * **1D barcodes**: `python-barcode` (Code128/39/EAN; outputs PIL/SVG).
  * **Data Matrix**: shortlist and validate pure-Python or wheel-distributed packages; add a shim and a fallback (e.g., raster font-based DM as emergency path).
    *(This doc avoids locking in a name until we verify platform wheels.)*

---

## 6) Tooling & Standards

* **Python**: 3.12
* **Package mgmt & execution**: `uv`, `uvx` (experimental), plus `mypy`
* **Style**: `ruff` (pep8/pylint rules), docstrings for public functions.
* **Tests**: `pytest` (+ `hypothesis` for property-based tests in geometry & clustering).
* **CI**: GitHub Actions (type-check, lint, test, build).
* **Security & privacy**

  * **Never log PII** (names, addresses, IDs) or **critical IP**.
  * If a user payload includes PII or secrets, **warn and require explicit confirmation** before continuing.
  * Don’t persist user data in artifacts; redact in logs.

**Commands (Windows examples)**

```powershell
# Create venv & install
uv venv .venv
. .\.venv\Scripts\activate
uv pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[opencv]"  # optional extras

# Format/lint/type-check/tests
uvx ruff check .
uvx ruff format .
uvx mypy .
uv run pytest -q
```

---

## 7) Testing & Demos (must be exhaustive)

**Principle:** Every feature ships with **unit tests**, **property tests** (where applicable), and **explicit demos** that try to break the pipeline early.

### 7.1 Synthetic PDFs (known geometry)

We **do not** rely on outside files. We generate ground-truth PDFs with known sizes, then create **rasterized PDFs** to exercise edge-detection.

* **Generator script**: creates vector PDF of a grid of rounded rectangles or circles with known page size and margins.
* **Rasterization script**: renders the vector PDF to an image and **re-embeds** it into a new PDF as a single image layer (destroys vector paths).
  This simulates “printed to PDF”.

**Acceptance:** Extractor must produce grid dims, spacings, and sizes within tolerances (e.g., ≤ 0.5 pt or ≤ 0.25% of page width).

### 7.2 Circle synthesizers

* Validate simple vs close-packing formulas (`dx`, `dy`, row offsets).
* Property tests: given `diameter` and `margins`, all centers must lie within the page and not overlap.

### 7.3 Exporters

* JSON/CSV round-trips: verify coordinate space transforms and value ranges.
* **Percent-of-width** contract: assert that `y%` uses page width.

### 7.4 Future printing

* Encode sample payloads with all symbols; composite to PDF; verify placements by re-extracting centers and comparing deltas.

---

## 8) Example Scripts (for tests & demos)

> These are deliberately complete and minimal to run under `uv run python`.

### 8.1 Generate a vector PDF of rounded rectangles

```python
# scripts/gen_rect_template_pdf.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

def main():
    pw, ph = letter  # 612x792 points
    cols, rows = 2, 9
    w, h = 3.49*inch, 0.99*inch
    dx, dy = 4.06*inch, 1.125*inch
    tlx, tly = 1.6*inch, 1.25*inch  # top-left center
    r = 0.12*inch  # corner radius

    c = canvas.Canvas("rect_template_vector.pdf", pagesize=(pw, ph))
    for r_i in range(rows):
        for c_i in range(cols):
            cx = tlx + c_i*dx
            cy = tly + r_i*dy
            x0 = cx - w/2
            y0 = cy - h/2
            c.roundRect(x0, y0, w, h, r, stroke=1, fill=0)
    c.showPage(); c.save()

if __name__ == "__main__":
    main()
```

### 8.2 Rasterize the PDF (simulate “print to PDF”)

```python
# scripts/rasterize_pdf.py
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image

def pdf_to_rasterized_pdf(src="rect_template_vector.pdf", dst="rect_template_raster.pdf", dpi=300):
    doc = fitz.open(src)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Embed rendered image back into a new PDF page
    pw, ph = letter
    c = canvas.Canvas(dst, pagesize=(pw, ph))
    # Fit the image exactly to page size
    img_path = "tmp_page.png"
    img.save(img_path, "PNG")
    c.drawImage(img_path, 0, 0, width=pw, height=ph, mask=None)
    c.showPage(); c.save()

if __name__ == "__main__":
    pdf_to_rasterized_pdf()
```

### 8.3 Demo extraction + exports

```python
# scripts/demo_extract.py
from templator.pdf_extract import extract_from_pdf
from templator.image_extract import extract_from_pdf_raster
from templator.exporters import export_json, export_csv

def main():
    # Try vector first
    t = extract_from_pdf("rect_template_vector.pdf", page_index=0)
    if t is None:
        t = extract_from_pdf_raster("rect_template_vector.pdf", page_index=0, dpi=200)
    assert t is not None, "Extraction failed (vector source)."
    export_json(t, "vector_out.json", "percent_width")
    export_csv(t,  "vector_out.csv",  "percent_width")

    # Now the rasterized version (harder path)
    r = extract_from_pdf_raster("rect_template_raster.pdf", page_index=0, dpi=200)
    assert r is not None, "Extraction failed (raster source)."
    export_json(r, "raster_out.json", "percent_width")
    export_csv(r,  "raster_out.csv",  "percent_width")

if __name__ == "__main__":
    main()
```

**Install demo deps** (adds `reportlab` for generator scripts):

```powershell
uv pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org reportlab
```

---

## 9) Type Checking, Linting, CI

* **mypy** strict: `--strict` for library code; CI blocks on errors.
* **ruff**: style + unused imports, complexity caps.
* **CI matrix**: 3.12 on Windows/Linux/macOS; optional job with OpenCV extras.

**Suggested CI steps**

1. `uvx ruff check .`
2. `uvx mypy .`
3. `uv run pytest -q`
4. Build sdist/wheel.

---

## 10) Performance & Memory

* Avoid intermediate large images when possible; prefer page-at-a-time.
* Raster DPI defaults to **200** (fast) with an option for **300/600** when precision is needed.
* Use **medians** for robustness on noisy edge maps.
* Minimize copies (operate on `numpy` views; reuse buffers).

---

## 11) Data Handling & Safety

* **Do not** include secrets, PII, or sensitive IP in templates, metadata, or logs.
* If a caller provides content that looks like PII (e.g., addresses, phone numbers, IDs) or critical IP (product drawings), **warn** and request confirmation before processing.
* Sanitization helpers redact logs and strip sensitive fields from error reports.

---

## 12) Agent Guidelines (for automated contributors)

**Absolute rules**

* Respect this document as the contract; do not invent new public APIs without updating this doc first.
* **Never** commit real PII, credentials, or proprietary data. Use synthetic fixtures only.
* Keep deps minimal; treat OpenCV as optional.
* Favor **complete scripts** in `scripts/` for demos and regression reproduction.
* Default to **percent_of_width** exports in examples and verify that **y uses page width**.

**Coding standards**

* Python 3.12; exhaustive type hints.
* No pandas; rely on PyMuPDF, Pillow, numpy. Optional OpenCV.
* Deterministic ordering (row-major). Use medians for robust aggregation.

**Review checklist**

* [ ] Public API signatures unchanged or documented.
* [ ] New code has tests (unit + demo if relevant).
* [ ] mypy clean; ruff clean.
* [ ] Benchmarks/regressions unchanged or improved.

---

## 13) Progress Tracker

**Core Extractor**

* [ ] Vector pass: rectangle detection
* [ ] Vector pass: corner-radius estimation (best-effort)
* [ ] Raster pass: edge → morphology → CC → IoU de-dup
* [ ] Row/col clustering; Δx/Δy; TL/BL anchors
* [ ] Exporters (JSON/CSV) w/ all coordinate spaces

**Circle Support**

* [ ] Simple lattice synth
* [ ] Close-packing (hex) synth + row offset
* [ ] Unit tests + property tests (non-overlap, in-bounds)

**Examples & Demos**

* [ ] Rectangle vector PDF generator script
* [ ] Rasterization script (render → embed image PDF)
* [ ] End-to-end extraction demo (vector & rasterized)

**Tooling**

* [ ] mypy strict passing
* [ ] ruff + formatting
* [ ] CI matrix (Windows/Linux/macOS)

**Printing API (Future)**

* [ ] RenderSpec & compositor
* [ ] Text layout (wrap, align, kerning where feasible)
* [ ] Encoder plugins (QR, 1D barcodes, Data Matrix) — validate pure-Python/wheel availability
* [ ] Bulk/serialized job runner
* [ ] PDF output & verification harness (placement checks)

---

## 14) Bootstrap Prompt (for agents, single-shot repo scaffold)

> Use this exact block when you spin up a new repo:

```
You are scaffolding a Python 3.12 library named “templator” as per /agents.md. Create the project with:
- src layout; modules described in Section 3
- pyproject.toml with dependencies: pymupdf>=1.23, pillow>=10.0, numpy>=1.26
- optional extras: opencv-python>=4.9
- entrypoint: templator = templator.cli:main
- add ruff + mypy configs, pytest, and GitHub Actions CI as per Sections 6 & 9
- include scripts in /scripts exactly as in Section 8
- README: quickstart with uv/uvx; examples; percent_of_width notes
- tests: cover extractors, exporters, geometry, and the demo workflow
- no sample files with real data; only synthetic generators
- Never include PII or proprietary assets; add fixtures generated at test time
Generate all files now.
```

---

## 15) Acceptance Criteria (Phase 1)

* **Rectangular** template extraction from both **vector** and **rasterized** PDFs with errors < **0.5 pt** (or < **0.25% of page width**) on:

  * grid rows/cols, Δx, Δy, TL/BL centers, width/height.
* **Circle** synthesizers produce in-bounds, non-overlapping centers for given margins and diameter.
* JSON/CSV exporters pass round-trip checks; **percent_of_width** contract verified.
* mypy, ruff, pytest passing locally and in CI.

---

If you want, I can turn this into a ready-to-commit repository structure with the code and scripts above embedded, plus basic tests wired for `uv run pytest`.

