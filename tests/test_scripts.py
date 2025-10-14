from __future__ import annotations

import json
from pathlib import Path

from scripts import demo_extract


def test_demo_extract_pipeline(tmp_path: Path) -> None:
    output_dir = tmp_path / "demo"
    exit_code = demo_extract.main(["--output-dir", str(output_dir), "--dpi", "200"])
    assert exit_code == 0

    pdf_path = output_dir / "demo_grid.pdf"
    raster_pdf_path = output_dir / "demo_grid_raster.pdf"
    vector_json = output_dir / "demo_grid_vector.json"
    raster_json = output_dir / "demo_grid_raster.json"

    assert pdf_path.exists()
    assert raster_pdf_path.exists()
    assert vector_json.exists()
    assert raster_json.exists()

    with vector_json.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["grid"]["kind"] == "rectangular"
    assert payload["label"]["shape"] == "rectangle"
