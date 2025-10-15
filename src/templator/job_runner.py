"""Batch job orchestration helpers for templator rendering."""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from .models import CoordinateSpace
from .render import RenderSpec, render_to_pdf
from . import render as _render_mod

logger = logging.getLogger(__name__)

__all__ = [
    "RunnerConfig",
    "JobDefinition",
    "JobResult",
    "JobReport",
    "JobSpec",
    "load_job_spec",
    "JobRunner",
]


@dataclass(slots=True)
class RunnerConfig:
    """Configuration options controlling batch execution."""

    chunk_size: int = 1
    max_workers: int | None = None
    halt_on_error: bool = False

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            msg = f"chunk_size must be positive. Received {self.chunk_size!r}."
            raise ValueError(msg)
        if self.max_workers is not None and self.max_workers <= 0:
            msg = f"max_workers must be positive when provided. Received {self.max_workers!r}."
            raise ValueError(msg)


@dataclass(slots=True)
class JobDefinition:
    """Description of a single PDF rendering job."""

    template_path: Path
    output_path: Path
    coord_space: CoordinateSpace
    items: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    data_root: Path | None = None
    job_payload_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.template_path.exists():
            msg = f"Template path does not exist: {self.template_path}"
            raise FileNotFoundError(msg)
        if not isinstance(self.items, Sequence):
            msg = "items must be a sequence of mappings."
            raise TypeError(msg)
        for entry in self.items:
            if not isinstance(entry, Mapping):
                msg = "Each job item must be a mapping."
                raise TypeError(msg)

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        return self.output_path.stem

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the job definition."""

        return {
            "name": self.name,
            "template": str(self.template_path),
            "output": str(self.output_path),
            "coord_space": self.coord_space,
            "items_count": len(self.items),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class JobResult:
    """Result metadata for a completed job."""

    definition: JobDefinition
    success: bool
    duration_s: float
    output_path: Path | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.definition.display_name,
            "output": str(self.definition.output_path),
            "success": self.success,
            "duration_s": self.duration_s,
            "metadata": dict(self.metadata),
        }
        if self.error:
            payload["error"] = self.error
        if self.output_path is not None:
            payload["written_output"] = str(self.output_path)
        return payload


@dataclass(slots=True)
class JobReport:
    """Collection of job results with convenience helpers."""

    results: list[JobResult]

    @property
    def succeeded(self) -> list[JobResult]:
        return [result for result in self.results if result.success]

    @property
    def failed(self) -> list[JobResult]:
        return [result for result in self.results if not result.success]

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "succeeded": len(self.succeeded),
            "failed": len(self.failed),
        }


@dataclass(slots=True)
class JobSpec:
    """Structured representation of a job specification file."""

    jobs: list[JobDefinition]
    config: RunnerConfig


class JobRunner:
    """Execute templator rendering jobs sequentially or in parallel."""

    def __init__(self, jobs: Sequence[JobDefinition], *, config: RunnerConfig | None = None) -> None:
        self.jobs = list(jobs)
        self.config = config or RunnerConfig()

    @classmethod
    def from_file(cls, path: Path) -> "JobRunner":
        spec = load_job_spec(path)
        return cls(spec.jobs, config=spec.config)

    def run(self) -> JobReport:
        if not self.jobs:
            return JobReport(results=[])

        if self.config.max_workers and self.config.max_workers > 1:
            results = self._run_concurrent()
        else:
            results = self._run_serial()
        return JobReport(results=results)

    def _run_serial(self) -> list[JobResult]:
        results: list[JobResult] = []
        for index, job in enumerate(self.jobs, start=1):
            results.append(self._execute_job(job, index=index))
            if self.config.halt_on_error and not results[-1].success:
                break
        return results

    def _run_concurrent(self) -> list[JobResult]:
        results: list[JobResult] = []
        pending: list[Future[JobResult]] = []
        stop_scheduling = False
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            for idx, job in enumerate(self.jobs, start=1):
                if stop_scheduling:
                    break
                future = executor.submit(self._execute_job, job, index=idx)
                pending.append(future)
                if len(pending) >= self.config.chunk_size:
                    chunk_results = self._collect_futures(pending)
                    results.extend(chunk_results)
                    if self.config.halt_on_error and any(not res.success for res in chunk_results):
                        stop_scheduling = True
            results.extend(self._collect_futures(pending))
        return results

    @staticmethod
    def _collect_futures(futures: list[Future[JobResult]]) -> list[JobResult]:
        results = [future.result() for future in futures]
        futures.clear()
        return results

    def _execute_job(self, job: JobDefinition, *, index: int) -> JobResult:
        start = time.perf_counter()
        logger.info("Starting job %s (%s) -> %s", index, job.display_name, job.output_path)
        metadata = {
            "index": index,
            "name": job.display_name,
            "template": str(job.template_path),
            "output": str(job.output_path),
            **dict(job.metadata),
        }

        try:
            spec = _build_render_spec(job)
            output_path = render_to_pdf(spec, job.output_path)
        except Exception as exc:  # pragma: no cover - exercised in tests
            duration = time.perf_counter() - start
            message = str(exc)
            metadata["error"] = message
            logger.exception("Job %s (%s) failed: %s", index, job.display_name, message)
            return JobResult(
                definition=job,
                success=False,
                duration_s=duration,
                output_path=None,
                error=message,
                metadata=metadata,
            )

        duration = time.perf_counter() - start
        metadata["duration_s"] = duration
        logger.info(
            "Job %s (%s) succeeded in %.3fs -> %s",
            index,
            job.display_name,
            duration,
            output_path,
        )
        return JobResult(
            definition=job,
            success=True,
            duration_s=duration,
            output_path=output_path,
            metadata=metadata,
        )


def load_job_spec(path: Path) -> JobSpec:
    """Load a job specification file (JSON or YAML)."""

    payload = _load_mapping(path)
    options = payload.get("options", {})
    if options and not isinstance(options, Mapping):
        msg = "Job specification 'options' must be a mapping."
        raise ValueError(msg)

    chunk_size = int(options.get("chunk_size", 1)) if isinstance(options, Mapping) else 1
    max_workers_raw = options.get("max_workers") if isinstance(options, Mapping) else None
    if isinstance(max_workers_raw, (int, float)):
        max_workers = int(max_workers_raw)
    elif max_workers_raw is None:
        max_workers = None
    else:
        msg = "Job specification option 'max_workers' must be numeric when provided."
        raise ValueError(msg)
    halt_on_error = (
        bool(options.get("halt_on_error", False)) if isinstance(options, Mapping) else False
    )

    config = RunnerConfig(
        chunk_size=chunk_size,
        max_workers=max_workers,
        halt_on_error=halt_on_error,
    )

    jobs_payload = payload.get("jobs")
    if not isinstance(jobs_payload, list):
        msg = "Job specification must define a 'jobs' array."
        raise ValueError(msg)

    jobs = [
        _parse_job_definition(entry, base_path=path.parent)
        for entry in jobs_payload
    ]

    return JobSpec(jobs=jobs, config=config)


def _parse_job_definition(data: Mapping[str, Any], *, base_path: Path) -> JobDefinition:
    if not isinstance(data, Mapping):
        msg = "Job entries must be mappings."
        raise ValueError(msg)

    template_raw = data.get("template")
    output_raw = data.get("output")
    if not isinstance(template_raw, str) or not isinstance(output_raw, str):
        msg = "Job entries require 'template' and 'output' string fields."
        raise ValueError(msg)

    template_path = _resolve_path(base_path, template_raw)
    output_path = _resolve_path(base_path, output_raw)

    coord_space_raw = data.get("coord_space")
    coord_space: CoordinateSpace
    if coord_space_raw is None:
        coord_space = "percent_width"
    elif isinstance(coord_space_raw, str) and coord_space_raw in {
        "percent_width",
        "points",
        "inches",
        "mm",
    }:
        coord_space = coord_space_raw
    else:
        msg = f"Unsupported coord_space value: {coord_space_raw!r}"
        raise ValueError(msg)

    name = data.get("name")
    if name is not None and not isinstance(name, str):
        msg = "Job name must be a string when provided."
        raise ValueError(msg)

    metadata_raw = data.get("metadata", {})
    if not isinstance(metadata_raw, Mapping):
        msg = "Job metadata must be a mapping if provided."
        raise ValueError(msg)

    items_payload = data.get("items")
    items: list[Mapping[str, Any]] | None = None
    if items_payload is not None:
        if not isinstance(items_payload, Sequence):
            msg = "Job 'items' must be a list when provided."
            raise ValueError(msg)
        items = [_ensure_mapping(entry, "job item") for entry in items_payload]

    job_spec_raw = data.get("job")
    data_root = base_path
    job_payload_path: Path | None = None
    if job_spec_raw is not None:
        if not isinstance(job_spec_raw, str):
            msg = "Job 'job' reference must be a string path."
            raise ValueError(msg)
        job_payload_path = _resolve_path(base_path, job_spec_raw)
        job_payload = _load_mapping(job_payload_path)
        data_root = job_payload_path.parent
        job_items = job_payload.get("items")
        if items is None and job_items is not None:
            if not isinstance(job_items, Sequence):
                msg = "Referenced job payload 'items' must be a list."
                raise ValueError(msg)
            items = [_ensure_mapping(entry, "job item") for entry in job_items]
        if "coord_space" in job_payload and coord_space_raw is None:
            coord_space_value = job_payload["coord_space"]
            if isinstance(coord_space_value, str) and coord_space_value in {
                "percent_width",
                "points",
                "inches",
                "mm",
            }:
                coord_space = coord_space_value
            else:
                msg = f"Unsupported coord_space in job payload: {coord_space_value!r}"
                raise ValueError(msg)

    if items is None:
        items = []

    return JobDefinition(
        template_path=template_path,
        output_path=output_path,
        coord_space=coord_space,
        items=tuple(items),
        name=name,
        metadata=dict(metadata_raw),
        data_root=data_root,
        job_payload_path=job_payload_path,
    )


def _build_render_spec(job: JobDefinition) -> RenderSpec:
    template = _render_mod._load_template_from_json(job.template_path)
    base_path = job.data_root or job.template_path.parent
    render_items = [
        _render_mod._parse_render_item(
            dict(item),
            job.coord_space,
            base_path=base_path,
            encoder_registry=None,
        )
        for item in job.items
    ]
    return RenderSpec(
        template=template,
        items=render_items,
        coord_space=job.coord_space,
        encoder_registry=None,
    )


def _resolve_path(base_path: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base_path / candidate
    return candidate.resolve()


def _load_mapping(path: Path) -> Mapping[str, Any]:
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - requires missing dependency
            msg = (
                "PyYAML is required to read YAML job specifications. "
                "Install the 'pyyaml' package to enable this feature."
            )
            raise RuntimeError(msg) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text) if text.strip() else {}

    if data is None:
        return {}
    if not isinstance(data, Mapping):
        msg = f"Specification files must contain a mapping at the top level (got {type(data)!r})."
        raise ValueError(msg)
    return data


def _ensure_mapping(data: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        msg = f"{context.capitalize()} entries must be mappings."
        raise ValueError(msg)
    return data
