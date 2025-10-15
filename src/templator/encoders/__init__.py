"""Symbol encoder registry and adapters for the rendering pipeline."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol, runtime_checkable

from PIL import Image

_RESAMPLING = getattr(Image, "Resampling", Image)

__all__ = [
    "SymbolEncoder",
    "EncoderError",
    "EncoderLookupError",
    "EncoderDependencyError",
    "EncoderRegistry",
    "create_default_registry",
    "get_default_registry",
]


@runtime_checkable
class SymbolEncoder(Protocol):
    """Protocol for objects that can encode payloads into raster symbols."""

    def encode(
        self,
        payload: str,
        *,
        size: tuple[int, int] | None = None,
        options: Mapping[str, object] | None = None,
    ) -> Image.Image:
        """Return a PIL image representing ``payload``.

        Parameters
        ----------
        payload:
            Text to encode.
        size:
            Optional pixel dimensions.  Encoders should honour the requested
            size when possible while maintaining aspect ratio fidelity for the
            symbology.
        options:
            Optional encoder-specific overrides.
        """


class EncoderError(RuntimeError):
    """Base error raised for encoder registry operations."""


class EncoderLookupError(EncoderError):
    """Raised when a symbol type does not have an associated encoder."""


@dataclass(slots=True)
class EncoderDependencyError(EncoderError):
    """Raised when an encoder cannot be initialised due to missing deps."""

    dependency: str

    def __str__(self) -> str:  # pragma: no cover - string formatting helper
        return f"Optional dependency '{self.dependency}' is not available"


@dataclass(slots=True)
class _EncoderRegistration:
    factory: Callable[[], SymbolEncoder]
    dependency: str | None = None


class EncoderRegistry:
    """Mapping from symbolic names to concrete encoder factories."""

    def __init__(self) -> None:
        self._registry: dict[str, _EncoderRegistration] = {}

    def register(
        self,
        symbol_type: str,
        factory: Callable[[], SymbolEncoder],
        *,
        dependency: str | None = None,
        override: bool = False,
    ) -> None:
        """Register ``factory`` for ``symbol_type``.

        Parameters
        ----------
        symbol_type:
            Canonical identifier for the symbology (case-insensitive).
        factory:
            Callable that returns a :class:`SymbolEncoder` instance.  The
            callable may lazily import optional dependencies.
        dependency:
            Name of the optional dependency required by this encoder.  Used to
            produce helpful error messages when imports fail.
        override:
            Allow re-registering an existing symbol type when ``True``.
        """

        key = symbol_type.lower()
        if not override and key in self._registry:
            msg = f"Encoder for symbol type {symbol_type!r} is already registered"
            raise ValueError(msg)
        self._registry[key] = _EncoderRegistration(factory=factory, dependency=dependency)

    def get(self, symbol_type: str) -> SymbolEncoder:
        """Return the encoder associated with ``symbol_type``."""

        registration = self._registry.get(symbol_type.lower())
        if registration is None:
            msg = f"No encoder is registered for symbol type {symbol_type!r}"
            raise EncoderLookupError(msg)
        try:
            return registration.factory()
        except ModuleNotFoundError as exc:  # pragma: no cover - defensive guard
            dependency = registration.dependency or exc.name or "unknown"
            raise EncoderDependencyError(dependency) from exc
        except ImportError as exc:
            dependency = registration.dependency or getattr(exc, "name", None) or "unknown"
            raise EncoderDependencyError(dependency) from exc

    def available_types(self) -> tuple[str, ...]:
        """Return registered symbol type identifiers."""

        return tuple(sorted(self._registry.keys()))


_DEFAULT_REGISTRY: EncoderRegistry | None = None


def get_default_registry() -> EncoderRegistry:
    """Return the process-wide default encoder registry."""

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = create_default_registry()
    return _DEFAULT_REGISTRY


def create_default_registry() -> EncoderRegistry:
    """Construct a registry populated with the built-in adapters."""

    registry = EncoderRegistry()
    registry.register("code128", _python_barcode_factory("code128"), dependency="python-barcode")
    registry.register("code39", _python_barcode_factory("code39"), dependency="python-barcode")
    registry.register("ean13", _python_barcode_factory("ean13"), dependency="python-barcode")
    registry.register("qr", _qr_factory(), dependency="segno or qrcode")
    registry.register("qrcode", _qrcode_factory(), dependency="qrcode")
    registry.register("datamatrix", _pystrich_factory(), dependency="pystrich")
    return registry


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _normalise_size(size: tuple[int, int] | None) -> tuple[int, int] | None:
    if size is None:
        return None
    width, height = size
    if width <= 0 or height <= 0:
        msg = "Requested pixel size must be positive"
        raise ValueError(msg)
    return int(width), int(height)


def _prepare_image(image: Image.Image, size: tuple[int, int] | None) -> Image.Image:
    converted = image.convert("RGBA") if image.mode != "RGBA" else image.copy()
    normalised = _normalise_size(size)
    if normalised is None:
        return converted
    return converted.resize(normalised, _RESAMPLING.LANCZOS)


# ---------------------------------------------------------------------------
# python-barcode adapter
# ---------------------------------------------------------------------------


def _python_barcode_factory(barcode_name: str) -> Callable[[], SymbolEncoder]:
    def factory() -> SymbolEncoder:
        try:
            import barcode  # type: ignore[import-untyped]
            from barcode.writer import ImageWriter  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise ImportError(barcode_name) from exc

        class PythonBarcodeEncoder:
            def __init__(self) -> None:
                self._barcode = barcode
                self._name = barcode_name
                self._writer_cls = ImageWriter

            def encode(
                self,
                payload: str,
                *,
                size: tuple[int, int] | None = None,
                options: Mapping[str, object] | None = None,
            ) -> Image.Image:
                writer_options: dict[str, object] = {
                    "module_height": 15.0,
                    "module_width": 0.2,
                    "quiet_zone": 2.0,
                    "font_size": 0,
                    "text_distance": 1.0,
                }
                if options:
                    writer_options.update(dict(options))
                barcode_class = self._barcode.get_barcode_class(self._name)
                instance = barcode_class(payload, writer=self._writer_cls())
                image = instance.render(writer_options)
                return _prepare_image(image, size)

        return PythonBarcodeEncoder()

    return factory


# ---------------------------------------------------------------------------
# QR adapters
# ---------------------------------------------------------------------------


def _qr_factory() -> Callable[[], SymbolEncoder]:
    def factory() -> SymbolEncoder:
        try:
            return _segno_factory()()
        except ModuleNotFoundError:
            return _qrcode_factory()()

    return factory


def _segno_factory() -> Callable[[], SymbolEncoder]:
    def factory() -> SymbolEncoder:
        import segno  # type: ignore[import-untyped]

        class SegnoEncoder:
            def encode(
                self,
                payload: str,
                *,
                size: tuple[int, int] | None = None,
                options: Mapping[str, object] | None = None,
            ) -> Image.Image:
                opts = dict(options or {})
                error = opts.pop("error", None)
                border = int(opts.pop("border", 4))
                scale = int(opts.pop("scale", 10))
                dark = opts.pop("dark", "#000000")
                light = opts.pop("light", "#ffffff")
                if opts:
                    msg = f"Unsupported segno options: {', '.join(sorted(opts))}"
                    raise ValueError(msg)
                matrix = segno.make(payload, error=error) if error else segno.make(payload)
                buffer = BytesIO()
                matrix.save(buffer, kind="png", scale=scale, border=border, dark=dark, light=light)
                buffer.seek(0)
                image = Image.open(buffer)
                return _prepare_image(image, size)

        return SegnoEncoder()

    return factory


def _qrcode_factory() -> Callable[[], SymbolEncoder]:
    def factory() -> SymbolEncoder:
        import qrcode  # type: ignore[import-untyped]
        from qrcode.constants import ERROR_CORRECT_M  # type: ignore[import-untyped]

        class QrcodeEncoder:
            def encode(
                self,
                payload: str,
                *,
                size: tuple[int, int] | None = None,
                options: Mapping[str, object] | None = None,
            ) -> Image.Image:
                opts = dict(options or {})
                version = opts.pop("version", None)
                error_correction = opts.pop("error_correction", ERROR_CORRECT_M)
                box_size = int(opts.pop("box_size", 10))
                border = int(opts.pop("border", 4))
                fill_color = opts.pop("fill_color", "black")
                back_color = opts.pop("back_color", "white")
                if opts:
                    msg = f"Unsupported qrcode options: {', '.join(sorted(opts))}"
                    raise ValueError(msg)
                builder = qrcode.QRCode(
                    version=version,
                    error_correction=error_correction,
                    box_size=box_size,
                    border=border,
                )
                builder.add_data(payload)
                builder.make(fit=True)
                image = builder.make_image(fill_color=fill_color, back_color=back_color)
                return _prepare_image(image, size)

        return QrcodeEncoder()

    return factory


# ---------------------------------------------------------------------------
# Data Matrix adapter (pystrich)
# ---------------------------------------------------------------------------


def _pystrich_factory() -> Callable[[], SymbolEncoder]:
    def factory() -> SymbolEncoder:
        from pystrich.datamatrix import DataMatrixEncoder  # type: ignore[import-untyped]

        class PystrichDataMatrixEncoder:
            def encode(
                self,
                payload: str,
                *,
                size: tuple[int, int] | None = None,
                options: Mapping[str, object] | None = None,
            ) -> Image.Image:
                kwargs = dict(options or {})
                encoder = DataMatrixEncoder(payload, **kwargs)
                raw = encoder.get_imagedata()
                if isinstance(raw, (bytes, bytearray)):
                    stream = BytesIO(raw)
                else:
                    stream = raw
                stream.seek(0)
                image = Image.open(stream)
                return _prepare_image(image, size)

        return PystrichDataMatrixEncoder()

    return factory

