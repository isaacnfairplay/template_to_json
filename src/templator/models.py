"""Domain models used by the :mod:`templator` library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

CoordinateSpace = Literal["percent_width", "points", "inches", "mm"]


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
    """Grid configuration for a rectangular template."""

    rows: int
    columns: int
    spacing_x_pt: float
    spacing_y_pt: float

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.rows <= 0 or self.columns <= 0:
            msg = (
                "Grid rows and columns must be positive integers. "
                f"Received rows={self.rows!r}, columns={self.columns!r}."
            )
            raise ValueError(msg)
        if self.spacing_x_pt < 0 or self.spacing_y_pt < 0:
            msg = (
                "Grid spacing must be non-negative. "
                f"Received spacing_x={self.spacing_x_pt!r}, spacing_y={self.spacing_y_pt!r}."
            )
            raise ValueError(msg)


@dataclass(slots=True)
class LabelGeometry:
    """Geometric description for an individual label in PDF points."""

    width_pt: float
    height_pt: float

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.width_pt <= 0 or self.height_pt <= 0:
            msg = (
                "Label dimensions must be positive. "
                f"Received width={self.width_pt!r}, height={self.height_pt!r}."
            )
            raise ValueError(msg)


@dataclass(slots=True)
class ExtractedTemplate:
    """Structured representation of an extracted template.

    Attributes
    ----------
    page : PageMetrics
        Physical size of the page in PDF points.
    grid : GridMetrics
        Inferred grid characteristics for rectangular templates.
    label : LabelGeometry
        Size of the label region in PDF points.
    top_left_pt : tuple[float, float]
        The top-left anchor of the grid in PDF points.
    centers_pt : Sequence[tuple[float, float]]
        Row-major ordered list of label centers expressed in PDF points.
    metadata : dict[str, str]
        Optional metadata captured during extraction (e.g., source path).
    """

    page: PageMetrics
    grid: GridMetrics
    label: LabelGeometry
    top_left_pt: tuple[float, float]
    centers_pt: Sequence[tuple[float, float]]
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from . import geometry

        self.centers_pt = tuple(geometry.ensure_row_major(self.centers_pt))

    def centers(self, coord_space: CoordinateSpace) -> list[tuple[float, float]]:
        """Return centers converted into the requested coordinate space."""

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

    def to_dict(self, coord_space: CoordinateSpace) -> dict[str, object]:
        """Create a JSON-serialisable dictionary of the template."""

        from . import geometry

        return {
            "page": {
                "width_pt": self.page.width_pt,
                "height_pt": self.page.height_pt,
            },
            "grid": {
                "rows": self.grid.rows,
                "columns": self.grid.columns,
                "spacing_x_pt": self.grid.spacing_x_pt,
                "spacing_y_pt": self.grid.spacing_y_pt,
            },
            "label": {
                "width_pt": self.label.width_pt,
                "height_pt": self.label.height_pt,
            },
            "top_left": {
                "points": list(self.top_left_pt),
                "percent_width": geometry.percent_of_width(
                    self.top_left_pt, self.page.width_pt
                ),
            },
            "centers": self.centers(coord_space),
            "centers_coord_space": coord_space,
            "metadata": self.metadata,
        }

