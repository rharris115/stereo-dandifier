from dataclasses import dataclass

from PySide6.QtCore import QLocale
from PySide6.QtGui import QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

FALLBACK_PREVIEW_DPI = 600
MIN_USEFUL_PRINTER_DPI = 150


@dataclass(frozen=True)
class PageLayout:
    name: str
    size_mm: tuple[float, float]
    dpi: int
    source: str
    from_printer: bool = False


def default_page_layout() -> PageLayout:
    printer_info = QPrinterInfo.defaultPrinter()
    if not printer_info.isNull():
        printer = QPrinter(printer_info)
        page_size = printer.pageLayout().pageSize()
        if page_size.isValid():
            dpi = printer_dpi(printer, printer_info)
            return PageLayout(
                name=display_page_name(page_size),
                size_mm=page_size_mm(page_size),
                dpi=dpi,
                source=(
                    f"Default printer paper from system: {display_page_name(page_size)}; "
                    f"preview/render DPI: {dpi}"
                ),
                from_printer=True,
            )

    page_size_id = locale_default_page_size_id()
    page_size = QPageSize(page_size_id)
    return PageLayout(
        name=display_page_name(page_size),
        size_mm=page_size_mm(page_size),
        dpi=FALLBACK_PREVIEW_DPI,
        source=(
            f"No system paper size found; using locale fallback: {display_page_name(page_size)}; "
            f"preview/render DPI: {FALLBACK_PREVIEW_DPI}"
        ),
        from_printer=False,
    )


def page_size_mm(page_size: QPageSize) -> tuple[float, float]:
    size = page_size.size(QPageSize.Unit.Millimeter)
    return float(size.width()), float(size.height())


def page_layout_for_name(name: str) -> PageLayout:
    page_size = QPageSize(page_size_id_for_name(name))
    return PageLayout(
        name=display_page_name(page_size),
        size_mm=page_size_mm(page_size),
        dpi=FALLBACK_PREVIEW_DPI,
        source=(
            f"Selected PDF paper size: {display_page_name(page_size)}; "
            f"preview/render DPI: {FALLBACK_PREVIEW_DPI}"
        ),
        from_printer=False,
    )


def printer_dpi(printer: QPrinter, printer_info: QPrinterInfo) -> int:
    supported = [
        dpi
        for dpi in printer_info.supportedResolutions()
        if dpi >= MIN_USEFUL_PRINTER_DPI
    ]
    if supported:
        return max(supported)

    resolution = printer.resolution()
    if resolution >= MIN_USEFUL_PRINTER_DPI:
        return resolution

    return FALLBACK_PREVIEW_DPI


def page_size_id_for_name(name: str) -> QPageSize.PageSizeId:
    if name == "Letter":
        return QPageSize.PageSizeId.Letter
    if name == "A4":
        return QPageSize.PageSizeId.A4
    raise ValueError(f"Unsupported paper size: {name}")


def display_page_name(page_size: QPageSize) -> str:
    page_size_id = page_size.id()
    if page_size_id == QPageSize.PageSizeId.A4:
        return "A4"
    if page_size_id == QPageSize.PageSizeId.Letter:
        return "Letter"
    return page_size.name()


def locale_default_page_size_id() -> QPageSize.PageSizeId:
    letter_territories = {
        QLocale.Country.Canada,
        QLocale.Country.Chile,
        QLocale.Country.Colombia,
        QLocale.Country.CostaRica,
        QLocale.Country.ElSalvador,
        QLocale.Country.Guatemala,
        QLocale.Country.Mexico,
        QLocale.Country.Nicaragua,
        QLocale.Country.Panama,
        QLocale.Country.Philippines,
        QLocale.Country.UnitedStates,
        QLocale.Country.Venezuela,
    }
    if QLocale.system().territory() in letter_territories:
        return QPageSize.PageSizeId.Letter
    return QPageSize.PageSizeId.A4
