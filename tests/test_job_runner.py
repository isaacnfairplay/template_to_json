from __future__ import annotations

import json
import logging
import textwrap
from pathlib import Path

import pytest

from templator import job_runner


TEMPLATE_PAYLOAD = {
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


def _write_template(tmp_path: Path) -> Path:
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(TEMPLATE_PAYLOAD))
    return template_path


def _write_job_payload(base: Path, name: str) -> Path:
    payload = {
        "coord_space": "percent_width",
        "items": [
            {
                "text_fields": [
                    {
                        "text": name.upper(),
                        "font_size": 12,
                        "box_size": [40.0, 20.0],
                    }
                ]
            }
        ],
    }
    path = base / f"{name}.json"
    path.write_text(json.dumps(payload))
    return path


def test_job_runner_reports_success_and_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    template_path = _write_template(tmp_path)
    job_payload_path = _write_job_payload(tmp_path, "alpha")

    spec_payload = {
        "options": {"chunk_size": 2, "max_workers": 2},
        "jobs": [
            {
                "name": "alpha",
                "template": template_path.name,
                "output": "outputs/alpha.pdf",
                "job": job_payload_path.name,
                "metadata": {"batch": "A"},
            },
            {
                "name": "beta",
                "template": template_path.name,
                "output": "outputs/beta.pdf",
                "coord_space": "percent_width",
                "items": [
                    {
                        "text_fields": [
                            {
                                "text": "beta",
                                "font_size": 12,
                                "box_size": [40.0, 20.0],
                            }
                        ]
                    }
                ],
            },
        ],
    }

    spec_path = tmp_path / "job-spec.json"
    spec_path.write_text(json.dumps(spec_payload))

    calls: list[Path] = []

    def fake_render(spec: job_runner.RenderSpec, output: Path) -> Path:
        calls.append(output)
        if output.name == "beta.pdf":
            raise RuntimeError("boom")
        return output

    monkeypatch.setattr(job_runner, "render_to_pdf", fake_render)
    caplog.set_level(logging.INFO)

    spec = job_runner.load_job_spec(spec_path)
    runner = job_runner.JobRunner(spec.jobs, config=spec.config)
    report = runner.run()

    assert len(calls) == 2
    assert len(report.results) == 2
    assert len(report.succeeded) == 1
    assert len(report.failed) == 1

    failure = report.failed[0]
    assert failure.error == "boom"
    assert failure.metadata["name"] == "beta"
    assert failure.metadata["index"] == 2

    success = report.succeeded[0]
    assert success.metadata.get("batch") == "A"

    messages = {record.message for record in caplog.records}
    assert any("succeeded" in message for message in messages)
    assert any("failed" in message for message in messages)


def test_job_runner_halt_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    template_path = _write_template(tmp_path)

    spec_payload = {
        "options": {"halt_on_error": True},
        "jobs": [
            {
                "name": "first",
                "template": template_path.name,
                "output": "outputs/first.pdf",
                "items": [
                    {"text_fields": [{"text": "first", "font_size": 10, "box_size": [40.0, 20.0]}]}
                ],
            },
            {
                "name": "second",
                "template": template_path.name,
                "output": "outputs/second.pdf",
                "items": [
                    {"text_fields": [{"text": "second", "font_size": 10, "box_size": [40.0, 20.0]}]}
                ],
            },
        ],
    }

    spec_path = tmp_path / "halt-spec.json"
    spec_path.write_text(json.dumps(spec_payload))

    calls: list[Path] = []

    def fake_render(spec: job_runner.RenderSpec, output: Path) -> Path:
        calls.append(output)
        raise RuntimeError("failure")

    monkeypatch.setattr(job_runner, "render_to_pdf", fake_render)

    spec = job_runner.load_job_spec(spec_path)
    runner = job_runner.JobRunner(spec.jobs, config=spec.config)
    report = runner.run()

    assert len(calls) == 1, "Second job should not run when halt_on_error is enabled"
    assert len(report.results) == 1
    assert report.results[0].success is False
    assert report.summary()["failed"] == 1


def test_load_job_spec_supports_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")

    template_path = _write_template(tmp_path)

    spec_text = textwrap.dedent(
        """
        options:
          chunk_size: 3
        jobs:
          - template: template.json
            output: outputs/sample.pdf
            items:
              - text_fields:
                  - text: sample
                    font_size: 10
                    box_size: [40.0, 20.0]
        """
    ).strip()

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(spec_text)

    spec = job_runner.load_job_spec(spec_path)

    assert spec.config.chunk_size == 3
    assert len(spec.jobs) == 1
    job = spec.jobs[0]
    assert job.template_path == template_path
    assert job.coord_space == "percent_width"
    assert len(job.items) == 1
