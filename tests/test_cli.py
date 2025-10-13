from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

import fitz


SRC_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"


def _draw_grid(
    path: Path,
    *,
    page_size: tuple[float, float],
    rows: int,
    columns: int,
    label_size: tuple[float, float],
    start: tuple[float, float],
    spacing: tuple[float, float],
) -> None:
    doc = fitz.open()
    page = doc.new_page(width=page_size[0], height=page_size[1])
    width, height = label_size
    start_x, start_y = start
    step_x, step_y = spacing
    for row in range(rows):
        for col in range(columns):
            x0 = start_x + col * step_x
            y0 = start_y + row * step_y
            rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(0, 0, 0), fill=None)
            shape.commit()
    doc.save(path)
    doc.close()


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

    _draw_grid(
        pdf_path,
        page_size=(400.0, 260.0),
        rows=2,
        columns=3,
        label_size=(80.0, 40.0),
        start=(36.0, 48.0),
        spacing=(100.0, 70.0),
    )

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
    assert len(data["centers"]) == 6


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
