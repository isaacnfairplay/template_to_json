from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from templator import encoders


@pytest.fixture
def qr_decoder():
    cv2 = pytest.importorskip("cv2")
    detector = cv2.QRCodeDetector()

    def decode(image: Image.Image) -> str:
        array = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        data, _, _ = detector.detectAndDecode(array)
        return data

    return decode


def test_python_barcode_encoder_dimensions() -> None:
    pytest.importorskip("barcode")
    registry = encoders.create_default_registry()
    encoder = registry.get("code128")
    image = encoder.encode("ABC-123", size=(240, 80))
    assert image.size == (240, 80)
    assert image.mode == "RGBA"


def test_qr_encoder_dimensions() -> None:
    pytest.importorskip("segno", reason="segno preferred for QR encoder")
    registry = encoders.create_default_registry()
    encoder = registry.get("qr")
    image = encoder.encode("templator", size=(160, 160))
    assert image.size == (160, 160)
    assert image.mode == "RGBA"


def test_qr_encoder_round_trip(qr_decoder) -> None:
    registry = encoders.create_default_registry()
    encoder = registry.get("qr")
    payload = "https://example.com/templator"
    image = encoder.encode(payload, size=(180, 180))
    decoded = qr_decoder(image)
    assert decoded == payload


def test_datamatrix_encoder_dimensions() -> None:
    pytest.importorskip("pystrich")
    registry = encoders.create_default_registry()
    encoder = registry.get("datamatrix")
    image = encoder.encode("HELLO", size=(96, 96))
    assert image.size == (96, 96)
    assert image.mode == "RGBA"


def test_registry_reports_missing_dependency() -> None:
    registry = encoders.EncoderRegistry()

    def factory() -> encoders.SymbolEncoder:
        raise ModuleNotFoundError("customlib")

    registry.register("custom", factory, dependency="customlib")
    with pytest.raises(encoders.EncoderDependencyError) as excinfo:
        registry.get("custom")
    assert "customlib" in str(excinfo.value)
