from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest
from PIL import Image

from scripts.gen_rect_template_pdf import RectTemplateSpec, generate_rect_template_pdf


SRC_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"


def _build_rect_pdf(path: Path) -> RectTemplateSpec:
    spec = RectTemplateSpec(
        page_size=(400.0, 260.0),
        rows=2,
        columns=3,
        label_size=(80.0, 40.0),
        start=(36.0, 48.0),
        spacing=(100.0, 70.0),
    )
    generate_rect_template_pdf(path, spec=spec)
    return spec


def _run_cli(tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "templator.cli", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_extract_generates_percent_width_json(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    json_path = tmp_path / "grid.json"

    spec = _build_rect_pdf(pdf_path)

    result = _run_cli(
        tmp_path,
        [
            "extract",
            str(pdf_path),
            "--json",
            str(json_path),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert "Wrote JSON output" in result.stdout
    data = json.loads(json_path.read_text())
    assert data["centers_coord_space"] == "percent_width"
    assert len(data["centers"]) == spec.rows * spec.columns


def test_cli_extract_supports_csv_output(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grid.pdf"
    json_path = tmp_path / "grid.json"
    csv_path = tmp_path / "grid.csv"

    spec = _build_rect_pdf(pdf_path)

    result = _run_cli(
        tmp_path,
        [
            "extract",
            str(pdf_path),
            "--json",
            str(json_path),
            "--csv",
            str(csv_path),
            "--coord-space",
            "points",
        ],
    )

    assert result.returncode == 0, result.stderr
    assert json_path.exists()
    assert csv_path.exists()

    payload = json.loads(json_path.read_text())
    assert payload["centers_coord_space"] == "points"
    assert len(payload["centers"]) == spec.rows * spec.columns

    csv_rows = csv_path.read_text().strip().splitlines()
    assert csv_rows[0].split(",")[:3] == ["x", "y", "coord_space"]
    assert all(row.endswith(",points") for row in csv_rows[1:])


def test_cli_synthesize_circles_supports_basic_options(tmp_path: Path) -> None:
    json_path = tmp_path / "circles.json"

    result = _run_cli(
        tmp_path,
        [
            "synthesize-circles",
            "simple",
            "--page-width",
            "400",
            "--page-height",
            "400",
            "--diameter",
            "50",
            "--margin",
            "10",
            "10",
            "10",
            "10",
            "--json",
            str(json_path),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert json_path.exists()

    payload = json.loads(json_path.read_text())
    assert payload["centers_coord_space"] == "percent_width"
    assert payload["grid"]["kind"].startswith("circle_")
    assert payload["centers"], "Expected synthesised centres to be present"


def test_cli_render_generates_pdf(tmp_path: Path) -> None:
    template_payload = {
        "page": {"width_pt": 200.0, "height_pt": 120.0},
        "grid": {
            "kind": "rectangular",
            "rows": 1,
            "columns": 1,
            "delta_x_pt": 80.0,
            "delta_y_pt": 40.0,
        },
        "label": {"shape": "rectangle", "width_pt": 80.0, "height_pt": 40.0},
        "anchors": {
            "points": {"top_left": [20.0, 100.0], "bottom_left": [20.0, 20.0]},
            "percent_width": {"top_left": [10.0, 50.0], "bottom_left": [10.0, 10.0]},
        },
        "centers": [[60.0, 60.0]],
        "centers_coord_space": "points",
        "metadata": {},
    }

    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template_payload))

    symbol_path = tmp_path / "symbol.png"
    Image.new("RGBA", (12, 12), (0, 128, 255, 255)).save(symbol_path)

    job_payload = {
        "coord_space": "percent_width",
        "items": [
            {
                "text_fields": [
                    {
                        "text": "CLI",
                        "font_size": 12,
                        "offset": [0.0, 0.0],
                        "box_size": [30.0, 15.0],
                    }
                ],
                "symbols": [
                    {
                        "image_path": symbol_path.name,
                        "box_size": [10.0, 10.0],
                        "box_coord_space": "percent_width",
                    }
                ],
            }
        ],
    }

    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job_payload))

    output_pdf = tmp_path / "output.pdf"
    result = _run_cli(
        tmp_path,
        [
            "render",
            "--template",
            str(template_path),
            "--job",
            str(job_path),
            "--output",
            str(output_pdf),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert output_pdf.exists()

    doc = fitz.open(output_pdf)
    try:
        page = doc[0]
        assert page.rect.width == pytest.approx(200.0)
        assert page.rect.height == pytest.approx(120.0)
    finally:
        doc.close()


def test_cli_run_job_executes_spec(tmp_path: Path) -> None:
    template_payload = {
        "page": {"width_pt": 200.0, "height_pt": 120.0},
        "grid": {
            "kind": "rectangular",
            "rows": 1,
            "columns": 1,
            "delta_x_pt": 80.0,
            "delta_y_pt": 40.0,
        },
        "label": {"shape": "rectangle", "width_pt": 80.0, "height_pt": 40.0},
        "anchors": {
            "points": {"top_left": [20.0, 100.0], "bottom_left": [20.0, 20.0]},
            "percent_width": {"top_left": [10.0, 50.0], "bottom_left": [10.0, 10.0]},
        },
        "centers": [[60.0, 60.0]],
        "centers_coord_space": "points",
        "metadata": {},
    }

    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template_payload))

    spec_path = tmp_path / "job.json"
    spec_payload = {
        "options": {"chunk_size": 1},
        "jobs": [
            {
                "name": "cli",
                "template": "template.json",
                "output": "outputs/cli.pdf",
                "coord_space": "percent_width",
                "items": [
                    {
                        "text_fields": [
                            {
                                "text": "CLI",
                                "font_size": 12,
                                "box_size": [40.0, 20.0],
                            }
                        ]
                    }
                ],
            }
        ],
    }
    spec_path.write_text(json.dumps(spec_payload))

    result = _run_cli(tmp_path, ["run-job", str(spec_path)])

    assert result.returncode == 0, result.stderr
    output_pdf = tmp_path / "outputs" / "cli.pdf"
    assert output_pdf.exists()
    assert "1 succeeded" in result.stdout
