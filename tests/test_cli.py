from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

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
