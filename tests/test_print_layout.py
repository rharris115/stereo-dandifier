from PySide6.QtGui import QPageSize

from stereo_dandifier.print_layout import (
    FALLBACK_PREVIEW_DPI,
    page_layout_for_name,
    page_size_mm,
    printer_dpi,
)


def test_page_layout_for_name_uses_qt_page_size_data():
    layout = page_layout_for_name("A4")

    assert layout.name == "A4"
    assert layout.size_mm == page_size_mm(QPageSize(QPageSize.PageSizeId.A4))
    assert layout.dpi == FALLBACK_PREVIEW_DPI
    assert not layout.from_printer


def test_letter_page_layout_uses_qt_page_size_data():
    layout = page_layout_for_name("Letter")

    assert layout.name == "Letter"
    assert layout.size_mm == page_size_mm(QPageSize(QPageSize.PageSizeId.Letter))
    assert layout.dpi == FALLBACK_PREVIEW_DPI
    assert not layout.from_printer


def test_printer_dpi_ignores_low_quality_72_dpi_default():
    assert printer_dpi(FakePrinter(72), FakePrinterInfo([])) == FALLBACK_PREVIEW_DPI


def test_printer_dpi_prefers_supported_print_resolution():
    assert printer_dpi(FakePrinter(72), FakePrinterInfo([300, 600])) == 600


class FakePrinter:
    def __init__(self, resolution: int):
        self._resolution = resolution

    def resolution(self) -> int:
        return self._resolution


class FakePrinterInfo:
    def __init__(self, supported_resolutions: list[int]):
        self._supported_resolutions = supported_resolutions

    def supportedResolutions(self) -> list[int]:
        return self._supported_resolutions
