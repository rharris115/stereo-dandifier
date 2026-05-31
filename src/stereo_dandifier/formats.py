from dataclasses import dataclass

from stereo_dandifier.models import CardLayoutName

EXPORT_DPI = 300
MM_PER_INCH = 25.4


@dataclass(frozen=True)
class CardLayout:
    card_mm: tuple[float, float]
    image_mm: tuple[float, float]
    center_spacing_mm: float
    top_margin_mm: float
    side_margin_mm: float
    bottom_margin_mm: float
    caption_height_mm: float


CARD_LAYOUTS = {
    CardLayoutName.HOLMES_STANDARD: CardLayout(
        card_mm=(180, 90),
        image_mm=(70, 70),
        center_spacing_mm=76,
        top_margin_mm=8,
        side_margin_mm=14,
        bottom_margin_mm=12,
        caption_height_mm=10,
    ),
    CardLayoutName.OWL_CONSERVATIVE: CardLayout(
        card_mm=(178, 85),
        image_mm=(68, 60),
        center_spacing_mm=70,
        top_margin_mm=7,
        side_margin_mm=18,
        bottom_margin_mm=16,
        caption_height_mm=12,
    ),
    CardLayoutName.OWL_RECOMMENDED: CardLayout(
        card_mm=(178, 85),
        image_mm=(72, 63),
        center_spacing_mm=72,
        top_margin_mm=7,
        side_margin_mm=17,
        bottom_margin_mm=15,
        caption_height_mm=12,
    ),
    CardLayoutName.OWL_DRAMATIC: CardLayout(
        card_mm=(178, 85),
        image_mm=(75, 65),
        center_spacing_mm=75,
        top_margin_mm=6,
        side_margin_mm=14,
        bottom_margin_mm=14,
        caption_height_mm=12,
    ),
    CardLayoutName.VICTORIAN_UNDERWOOD: CardLayout(
        card_mm=(178, 89),
        image_mm=(76, 76),
        center_spacing_mm=76,
        top_margin_mm=5,
        side_margin_mm=11,
        bottom_margin_mm=8,
        caption_height_mm=8,
    ),
}

CARD_FORMATS = CARD_LAYOUTS


def mm_to_px(mm: float, dpi: int = EXPORT_DPI) -> int:
    return round((mm / MM_PER_INCH) * dpi)


def mm_pair_to_px(value: tuple[float, float], dpi: int = EXPORT_DPI) -> tuple[int, int]:
    return mm_to_px(value[0], dpi=dpi), mm_to_px(value[1], dpi=dpi)


def format_particulars(name: CardLayoutName) -> str:
    layout = CARD_LAYOUTS[name]
    card_w, card_h = layout.card_mm
    image_w, image_h = layout.image_mm
    return (
        f"{card_w:g} x {card_h:g} mm card; {image_w:g} x {image_h:g} mm images; "
        f"{layout.center_spacing_mm:g} mm centers; "
        f"{layout.top_margin_mm:g} mm top, {layout.side_margin_mm:g} mm sides, "
        f"{layout.bottom_margin_mm:g} mm bottom; "
        f"{layout.caption_height_mm:g} mm caption area."
    )
