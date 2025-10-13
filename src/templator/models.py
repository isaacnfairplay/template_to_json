"""Domain models used by the :mod:`templator` library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

Point = tuple[float, float]
CoordinateSpace = Literal["percent_width", "points", "inches", "mm"]
GridKind = Literal["rectangular", "circle_simple", "circle_close"]
LabelShape = Literal["rectangle", "circle"]


@dataclass(slots=True)
class PageMetrics:
    """Physical page description in PDF points."""

    width_pt: float
    height_pt: float

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.width_pt <= 0 or self.height_pt <= 0:
            msg = (
                "Page dimensions must be positive. "
                f"Received width={self.width_pt!r}, height={self.height_pt!r}."
            )
            raise ValueError(msg)


@dataclass(slots=True)
class GridMetrics:
    """Grid configuration for a template."""

    kind: GridKind
    rows: int
    columns: int
    delta_x_pt: float
    delta_y_pt: float
    row_offsets_pt: tuple[float, ...] = ()
    columns_per_row: tuple[int, ...] | None = None

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.rows <= 0 or self.columns <= 0:
            msg = (
                "Grid rows and columns must be positive integers. "
                f"Received rows={self.rows!r}, columns={self.columns!r}."
            )
            raise ValueError(msg)
        if self.delta_x_pt <= 0 or self.delta_y_pt <= 0:
            msg = (
                "Grid spacing must be positive. "
                f"Received delta_x={self.delta_x_pt!r}, delta_y={self.delta_y_pt!r}."
            )
            raise ValueError(msg)
        if self.row_offsets_pt and len(self.row_offsets_pt) != self.rows:
            msg = (
                "Row offsets must match the number of rows. "
                f"Received {len(self.row_offsets_pt)} offsets for {self.rows} rows."
            )
            raise ValueError(msg)
        if self.columns_per_row is not None:
            if len(self.columns_per_row) != self.rows:
                msg = (
                    "Columns-per-row metadata must match row count. "
                    f"Received {len(self.columns_per_row)} entries for {self.rows} rows."
                )
                raise ValueError(msg)
            if any(columns <= 0 for columns in self.columns_per_row):
                msg = "Columns-per-row values must be positive integers."
                raise ValueError(msg)


@dataclass(slots=True)
class LabelGeometry:
    """Geometric description for an individual label in PDF points."""

    shape: LabelShape
    width_pt: float
    height_pt: float

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.width_pt <= 0 or self.height_pt <= 0:
            msg = (
                "Label dimensions must be positive. "
                f"Received width={self.width_pt!r}, height={self.height_pt!r}."
            )
            raise ValueError(msg)
        if self.shape == "circle" and abs(self.width_pt - self.height_pt) > 1e-6:
            msg = (
                "Circle geometry requires equal width and height. "
                f"Received width={self.width_pt!r}, height={self.height_pt!r}."
            )
            raise ValueError(msg)

    @property
    def diameter_pt(self) -> float:
        """Return the diameter in PDF points for circular labels."""

        if self.shape != "circle":
            msg = "Diameter is only defined for circular labels."
            raise AttributeError(msg)
        return self.width_pt

    @property
    def radius_pt(self) -> float:
        """Return the radius in PDF points for circular labels."""

        return self.diameter_pt / 2.0


@dataclass(slots=True)
class AnchorPoints:
    """Representative anchor points for the grid."""

    top_left_pt: Point
    bottom_left_pt: Point

    def as_percent_of_width(self, page_width_pt: float) -> dict[str, Point]:
        """Return anchor points scaled into percent-of-width space."""

        from . import geometry

        return {
            "top_left": geometry.percent_of_width(self.top_left_pt, page_width_pt),
            "bottom_left": geometry.percent_of_width(
                self.bottom_left_pt, page_width_pt
            ),
        }


@dataclass(slots=True)
class ExtractedTemplate:
    """Structured representation of an extracted or synthesised template."""

    page: PageMetrics
    grid: GridMetrics
    label: LabelGeometry
    anchors: AnchorPoints
    centers_pt: Sequence[Point]
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from . import geometry

        original = tuple(self.centers_pt)
        if not original:
            msg = "Templates must contain at least one centre point."
            raise ValueError(msg)
        ordered = tuple(geometry.ensure_row_major(original))
        self.centers_pt = ordered

    def centers(self, coord_space: CoordinateSpace) -> list[Point]:
        """Return centres converted into the requested coordinate space."""

        from . import geometry  # Local import to avoid circular dependency.

        match coord_space:
            case "percent_width":
                return [
                    geometry.percent_of_width(point, self.page.width_pt)
                    for point in self.centers_pt
                ]
            case "points":
                return list(self.centers_pt)
            case "inches":
                return [geometry.points_to_inches(point) for point in self.centers_pt]
            case "mm":
                return [geometry.points_to_mm(point) for point in self.centers_pt]
            case _:
                msg = f"Unknown coordinate space: {coord_space!r}"
                raise ValueError(msg)

    def centers_count(self) -> int:
        """Return the total number of centres in the template."""

        return len(self.centers_pt)

    def iter_centers(self) -> Iterable[Point]:
        """Iterate over centre points in row-major order."""

        yield from self.centers_pt

    def to_dict(self, coord_space: CoordinateSpace) -> dict[str, object]:
        """Create a JSON-serialisable dictionary of the template."""

        from . import geometry

        centers = self.centers(coord_space)
        row_offsets = list(self.grid.row_offsets_pt)
        grid_dict: dict[str, object] = {
            "kind": self.grid.kind,
            "rows": self.grid.rows,
            "columns": self.grid.columns,
            "delta_x_pt": self.grid.delta_x_pt,
            "delta_y_pt": self.grid.delta_y_pt,
        }
        if row_offsets:
            grid_dict["row_offsets_pt"] = row_offsets
        if self.grid.columns_per_row is not None:
            grid_dict["columns_per_row"] = list(self.grid.columns_per_row)

        anchors_percent = self.anchors.as_percent_of_width(self.page.width_pt)

        return {
            "page": {
                "width_pt": self.page.width_pt,
                "height_pt": self.page.height_pt,
            },
            "grid": grid_dict,
            "label": {
                "shape": self.label.shape,
                "width_pt": self.label.width_pt,
                "height_pt": self.label.height_pt,
            },
            "anchors": {
                "points": {
                    "top_left": list(self.anchors.top_left_pt),
                    "bottom_left": list(self.anchors.bottom_left_pt),
                },
                "percent_width": {
                    "top_left": list(anchors_percent["top_left"]),
                    "bottom_left": list(anchors_percent["bottom_left"]),
                },
            },
            "centers": centers,
            "centers_coord_space": coord_space,
            "metadata": self.metadata,
            "top_left_percent_width": geometry.percent_of_width(
                self.anchors.top_left_pt, self.page.width_pt
            ),
        }

