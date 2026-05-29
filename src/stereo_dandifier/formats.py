EXPORT_DPI = 300
MM_PER_INCH = 25.4

CARD_FORMATS = {
    "Holmes (standard)": {
        "card_mm": (180, 90),
        "image_mm": (70, 70),
        "center_spacing_mm": 76,
        "gap_mm": 6,
        "top_margin_mm": 8,
        "side_margin_mm": 14,
        "bottom_mm": 12,
        "notes": "Classic Holmes viewer.",
    },
    "Owl": {
        "card_mm": (178, 89),
        "image_mm": (63.5, 63.5),
        "center_spacing_mm": 64,
        "gap_mm": 6,
        "top_margin_mm": 8,
        "side_margin_mm": 14,
        "bottom_mm": 18,
        "notes": "Square windows, pleasant geometry.",
    },
    "Realist print": {
        "card_mm": (173, 101),
        "image_mm": (23, 24),
        "center_spacing_mm": 70,
        "gap_mm": None,
        "top_margin_mm": 18,
        "side_margin_mm": 51.5,
        "bottom_mm": 12,
        "notes": "For Stereo Realist mounts.",
    },
    "Victorian / Underwood": {
        "card_mm": (178, 89),
        "image_mm": (76, 76),
        "center_spacing_mm": 76,
        "gap_mm": 6,
        "top_margin_mm": 5,
        "side_margin_mm": 10,
        "bottom_mm": 12,
        "notes": "Big dramatic images.",
    },
    "Modern SBS print": {
        "card_mm": (180, 90),
        "image_mm": (70, 70),
        "center_spacing_mm": 76,
        "gap_mm": 6,
        "top_margin_mm": 8,
        "side_margin_mm": 14,
        "bottom_mm": 12,
        "notes": "Configurable headset / free-viewing export defaults.",
    },
}


def mm_to_px(mm: float, dpi: int = EXPORT_DPI) -> int:
    return round((mm / MM_PER_INCH) * dpi)


def mm_pair_to_px(value: tuple[float, float], dpi: int = EXPORT_DPI) -> tuple[int, int]:
    return mm_to_px(value[0], dpi=dpi), mm_to_px(value[1], dpi=dpi)


def format_particulars(name: str) -> str:
    spec = CARD_FORMATS[name]
    card_w, card_h = spec["card_mm"]
    image_w, image_h = spec["image_mm"]
    gap = f"{spec['gap_mm']:g} mm" if spec["gap_mm"] is not None else "N/A"
    return (
        f"{card_w:g} x {card_h:g} mm card; {image_w:g} x {image_h:g} mm images; "
        f"{spec['center_spacing_mm']:g} mm centers; {gap} gap; "
        f"{spec['top_margin_mm']:g} mm top, {spec['side_margin_mm']:g} mm sides, "
        f"{spec['bottom_mm']:g} mm caption area. {spec['notes']}"
    )
