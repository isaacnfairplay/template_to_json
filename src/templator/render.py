"""PDF composition utilities for the templator rendering pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import Path
from typing import Iterable, Literal, Sequence

import fitz  # type: ignore[import-untyped]
from PIL import Image

from . import geometry
from .models import (
    AnchorPoints,
    CoordinateSpace,
    ExtractedTemplate,
    GridMetrics,
    LabelGeometry,
    PageMetrics,
)

HorizontalAlignment = Literal["left", "center", "right"]
VerticalAlignment = Literal["top", "center", "bottom"]

__all__ = [
    "TextFieldSpec",
    "SymbolSpec",
    "RenderItem",
    "RenderSpec",
    "render_to_pdf",
]


@dataclass(slots=True)
class TextFieldSpec:
    """Description of a single text element to render on a label."""

    text: str
    font_name: str = "Helvetica"
    font_size: float = 10.0
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    align_x: HorizontalAlignment = "center"
    align_y: VerticalAlignment = "center"
    offset: tuple[float, float] = (0.0, 0.0)
    coord_space: CoordinateSpace | None = None
    box_size: tuple[float, float] | None = None
    box_coord_space: CoordinateSpace | None = None


@dataclass(slots=True)
class SymbolSpec:
    """Description of a pre-rendered image to place on a label."""

    image: Image.Image
    align_x: HorizontalAlignment = "center"
    align_y: VerticalAlignment = "center"
    offset: tuple[float, float] = (0.0, 0.0)
    coord_space: CoordinateSpace | None = None
    box_size: tuple[float, float] | None = None
    box_coord_space: CoordinateSpace | None = None

    @property
    def aspect_ratio(self) -> float:
        width, height = self.image.size
        if height == 0:
            msg = "Symbol image height must be non-zero."
            raise ValueError(msg)
        return width / height


@dataclass(slots=True)
class RenderItem:
    """Collection of renderable elements for a single label centre."""

    text_fields: list[TextFieldSpec] = field(default_factory=list)
    symbols: list[SymbolSpec] = field(default_factory=list)


@dataclass(slots=True)
class RenderSpec:
    """Complete specification describing how to render a template."""

    template: ExtractedTemplate
    items: Sequence[RenderItem]
    coord_space: CoordinateSpace = "percent_width"

    @classmethod
    def from_json(cls, template_path: Path, job_path: Path) -> "RenderSpec":
        """Load a :class:`RenderSpec` from JSON descriptors.

        Parameters
        ----------
        template_path:
            Path to a JSON file produced by :func:`templator.exporters.export_json`.
        job_path:
            Path to a JSON file describing the render job.  The job document must
            contain a ``coord_space`` field and an ``items`` array.  Each item may
            define ``text_fields`` and ``symbols`` collections.  Symbol entries are
            expected to reference raster image files using ``image_path``.
        """

        template = _load_template_from_json(template_path)
        job_data = json.loads(job_path.read_text())
        coord_space = _normalise_coord_space(job_data.get("coord_space"))
        items = [
            _parse_render_item(entry, coord_space, base_path=job_path.parent)
            for entry in job_data.get("items", [])
        ]
        return cls(template=template, items=items, coord_space=coord_space)


def render_to_pdf(spec: RenderSpec, out_path: str | Path) -> Path:
    """Render a template-driven job into a PDF document."""

    output_path = Path(out_path)
    if output_path.parent and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)

    document = fitz.open()
    page = document.new_page(
        width=spec.template.page.width_pt, height=spec.template.page.height_pt
    )

    centres = spec.template.centers("points")
    item_iter = _zip_items_with_centres(centres, spec.items)
    for centre, item in item_iter:
        _render_text_fields(page, spec, centre, item.text_fields)
        _render_symbols(page, spec, centre, item.symbols)

    document.save(output_path)
    document.close()
    return output_path


def _zip_items_with_centres(
    centres: Sequence[tuple[float, float]], items: Sequence[RenderItem]
) -> Iterable[tuple[tuple[float, float], RenderItem]]:
    default_item = RenderItem()
    for index, centre in enumerate(centres):
        item = items[index] if index < len(items) else default_item
        yield centre, item


def _render_text_fields(
    page: fitz.Page, spec: RenderSpec, centre: tuple[float, float], fields: Iterable[TextFieldSpec]
) -> None:
    for field in fields:
        if not field.text:
            continue
        offset_space = field.coord_space or spec.coord_space
        box_space = field.box_coord_space or offset_space
        offset_pt = _convert_point(field.offset, offset_space, spec.template.page.width_pt)
        width_pt, height_pt = _resolve_box_size(
            spec.template, field.box_size, box_space
        )
        anchor_x = centre[0] + offset_pt[0]
        anchor_y = centre[1] + offset_pt[1]
        rect = _alignment_rect(
            anchor_x, anchor_y, width_pt, height_pt, field.align_x, field.align_y
        )
        font = fitz.Font(fontname=field.font_name)
        text_width = fitz.get_text_length(
            field.text, fontname=field.font_name, fontsize=field.font_size
        )
        ascender = font.ascender * field.font_size
        descender = font.descender * field.font_size

        if field.align_x == "left":
            baseline_x = rect.x0
        elif field.align_x == "right":
            baseline_x = rect.x1 - text_width
        else:
            baseline_x = (rect.x0 + rect.x1 - text_width) / 2.0

        if field.align_y == "top":
            baseline_y = rect.y0 + ascender
        elif field.align_y == "bottom":
            baseline_y = rect.y1 + descender
        else:
            baseline_y = (rect.y0 + rect.y1) / 2.0 + (ascender + descender) / 2.0

        page.insert_text(
            fitz.Point(baseline_x, baseline_y),
            field.text,
            fontsize=field.font_size,
            fontname=field.font_name,
            color=field.color,
        )


def _render_symbols(
    page: fitz.Page, spec: RenderSpec, centre: tuple[float, float], symbols: Iterable[SymbolSpec]
) -> None:
    for symbol in symbols:
        offset_space = symbol.coord_space or spec.coord_space
        box_space = symbol.box_coord_space or offset_space
        offset_pt = _convert_point(symbol.offset, offset_space, spec.template.page.width_pt)
        width_pt, height_pt = _resolve_symbol_size(spec.template, symbol, box_space)
        anchor_x = centre[0] + offset_pt[0]
        anchor_y = centre[1] + offset_pt[1]
        rect = _alignment_rect(
            anchor_x, anchor_y, width_pt, height_pt, symbol.align_x, symbol.align_y
        )
        stream = _image_to_png_stream(symbol.image)
        page.insert_image(rect, stream=stream, keep_proportion=False, overlay=True)


def _alignment_rect(
    anchor_x: float,
    anchor_y: float,
    width_pt: float,
    height_pt: float,
    align_x: HorizontalAlignment,
    align_y: VerticalAlignment,
) -> fitz.Rect:
    if width_pt <= 0 or height_pt <= 0:
        msg = "Box dimensions must be positive."
        raise ValueError(msg)

    if align_x == "left":
        x0 = anchor_x
        x1 = anchor_x + width_pt
    elif align_x == "right":
        x0 = anchor_x - width_pt
        x1 = anchor_x
    else:
        x0 = anchor_x - width_pt / 2.0
        x1 = anchor_x + width_pt / 2.0

    if align_y == "top":
        y0 = anchor_y
        y1 = anchor_y + height_pt
    elif align_y == "bottom":
        y0 = anchor_y - height_pt
        y1 = anchor_y
    else:
        y0 = anchor_y - height_pt / 2.0
        y1 = anchor_y + height_pt / 2.0

    return fitz.Rect(x0, y0, x1, y1)


def _resolve_box_size(
    template: ExtractedTemplate,
    box_size: tuple[float, float] | None,
    coord_space: CoordinateSpace,
) -> tuple[float, float]:
    if box_size is None:
        return template.label.width_pt, template.label.height_pt
    width_raw, height_raw = box_size
    width_pt = _convert_length(width_raw, coord_space, template.page.width_pt)
    height_pt = _convert_length(height_raw, coord_space, template.page.width_pt)
    return width_pt, height_pt


def _resolve_symbol_size(
    template: ExtractedTemplate, symbol: SymbolSpec, coord_space: CoordinateSpace
) -> tuple[float, float]:
    if symbol.box_size is None:
        return template.label.width_pt, template.label.height_pt

    width_raw, height_raw = symbol.box_size
    width_pt = _convert_length(width_raw, coord_space, template.page.width_pt)
    height_pt = _convert_length(height_raw, coord_space, template.page.width_pt)

    has_width = width_pt > 0
    has_height = height_pt > 0

    if has_width and has_height:
        return width_pt, height_pt
    if has_width:
        return width_pt, width_pt / symbol.aspect_ratio
    if has_height:
        return height_pt * symbol.aspect_ratio, height_pt

    msg = "Symbol sizing must specify at least one positive dimension."
    raise ValueError(msg)


def _convert_length(value: float, coord_space: CoordinateSpace, page_width_pt: float) -> float:
    if coord_space == "points":
        return value
    if coord_space == "percent_width":
        return value * page_width_pt / 100.0
    if coord_space == "inches":
        return float(geometry.inches_to_points(value))
    if coord_space == "mm":
        return float(geometry.mm_to_points(value))
    msg = f"Unsupported coordinate space {coord_space!r}."
    raise ValueError(msg)


def _convert_point(
    value: tuple[float, float], coord_space: CoordinateSpace, page_width_pt: float
) -> tuple[float, float]:
    x, y = value
    return (
        _convert_length(x, coord_space, page_width_pt),
        _convert_length(y, coord_space, page_width_pt),
    )


def _image_to_png_stream(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _normalise_coord_space(value: object) -> CoordinateSpace:
    if isinstance(value, str) and value in {"percent_width", "points", "inches", "mm"}:
        return value
    msg = "Job specification must declare a supported coord_space."
    raise ValueError(msg)


def _load_template_from_json(path: Path) -> ExtractedTemplate:
    payload = json.loads(path.read_text())
    page = payload["page"]
    grid = payload["grid"]
    label = payload["label"]
    anchors = payload["anchors"]["points"]
    centers = payload["centers"]
    coord_space = payload.get("centers_coord_space", "points")

    page_metrics = PageMetrics(width_pt=page["width_pt"], height_pt=page["height_pt"])
    grid_metrics = GridMetrics(
        kind=grid["kind"],
        rows=grid["rows"],
        columns=grid["columns"],
        delta_x_pt=grid["delta_x_pt"],
        delta_y_pt=grid["delta_y_pt"],
        row_offsets_pt=tuple(grid.get("row_offsets_pt", [])),
        columns_per_row=(
            tuple(grid["columns_per_row"]) if "columns_per_row" in grid else None
        ),
    )
    label_geometry = LabelGeometry(
        shape=label["shape"],
        width_pt=label["width_pt"],
        height_pt=label["height_pt"],
    )
    anchor_points = AnchorPoints(
        top_left_pt=tuple(anchors["top_left"]),  # type: ignore[arg-type]
        bottom_left_pt=tuple(anchors["bottom_left"]),  # type: ignore[arg-type]
    )
    centres_pt = [
        _convert_point(tuple(point), coord_space, page_metrics.width_pt)  # type: ignore[arg-type]
        if coord_space != "points"
        else tuple(point)  # type: ignore[arg-type]
        for point in centers
    ]

    metadata = payload.get("metadata", {})
    return ExtractedTemplate(
        page=page_metrics,
        grid=grid_metrics,
        label=label_geometry,
        anchors=anchor_points,
        centers_pt=centres_pt,
        metadata=metadata,
    )


def _parse_render_item(
    data: dict[str, object],
    default_coord_space: CoordinateSpace,
    *,
    base_path: Path,
) -> RenderItem:
    if not isinstance(data, dict):  # pragma: no cover - defensive guard
        msg = "Render item entries must be JSON objects."
        raise ValueError(msg)
    text_entries = data.get("text_fields", [])
    symbol_entries = data.get("symbols", [])
    texts = [
        _parse_text_field(entry, default_coord_space)
        for entry in text_entries  # type: ignore[list-item]
        if isinstance(entry, dict)
    ]
    symbols = [
        _parse_symbol(entry, default_coord_space, base_path=base_path)
        for entry in symbol_entries  # type: ignore[list-item]
        if isinstance(entry, dict)
    ]
    return RenderItem(text_fields=texts, symbols=symbols)


def _parse_text_field(
    entry: dict[str, object], default_coord_space: CoordinateSpace
) -> TextFieldSpec:
    text = str(entry.get("text", ""))
    font_name = str(entry.get("font_name", "Helvetica"))
    font_size = float(entry.get("font_size", 10.0))
    color_raw = entry.get("color", (0.0, 0.0, 0.0))
    color_values = (
        tuple(float(component) for component in color_raw)  # type: ignore[arg-type]
        if isinstance(color_raw, (list, tuple)) and len(color_raw) == 3
        else (0.0, 0.0, 0.0)
    )
    align_x = str(entry.get("align_x", "center"))
    align_y = str(entry.get("align_y", "center"))
    offset = tuple(float(value) for value in entry.get("offset", (0.0, 0.0)))
    coord_space = entry.get("coord_space") or default_coord_space
    box_size_raw = entry.get("box_size")
    box_size = None
    if isinstance(box_size_raw, (list, tuple)) and len(box_size_raw) == 2:
        box_size = tuple(float(value) for value in box_size_raw)
    box_coord_space = entry.get("box_coord_space") or coord_space
    return TextFieldSpec(
        text=text,
        font_name=font_name,
        font_size=font_size,
        color=color_values,
        align_x=align_x,  # type: ignore[arg-type]
        align_y=align_y,  # type: ignore[arg-type]
        offset=offset,  # type: ignore[arg-type]
        coord_space=coord_space,  # type: ignore[arg-type]
        box_size=box_size,
        box_coord_space=box_coord_space,  # type: ignore[arg-type]
    )


def _parse_symbol(
    entry: dict[str, object],
    default_coord_space: CoordinateSpace,
    *,
    base_path: Path,
) -> SymbolSpec:
    image_path_raw = entry.get("image_path")
    if not isinstance(image_path_raw, str):
        msg = "Symbol specification must include an image_path."
        raise ValueError(msg)
    image_path = (base_path / image_path_raw).resolve()
    with Image.open(image_path) as handle:
        image = handle.convert("RGBA")
    align_x = str(entry.get("align_x", "center"))
    align_y = str(entry.get("align_y", "center"))
    offset = tuple(float(value) for value in entry.get("offset", (0.0, 0.0)))
    coord_space = entry.get("coord_space") or default_coord_space
    box_size_raw = entry.get("box_size")
    box_size = None
    if isinstance(box_size_raw, (list, tuple)) and len(box_size_raw) == 2:
        box_size = tuple(float(value) for value in box_size_raw)
    box_coord_space = entry.get("box_coord_space") or coord_space
    return SymbolSpec(
        image=image,
        align_x=align_x,  # type: ignore[arg-type]
        align_y=align_y,  # type: ignore[arg-type]
        offset=offset,  # type: ignore[arg-type]
        coord_space=coord_space,  # type: ignore[arg-type]
        box_size=box_size,
        box_coord_space=box_coord_space,  # type: ignore[arg-type]
    )

