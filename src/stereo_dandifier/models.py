from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from pathlib import Path

from PIL import Image

DEFAULT_CAPTION_FONT_FAMILY = "Arial"
DEFAULT_CAPTION_FONT_SIZE = 14


class CardLayoutName(StrEnum):
    HOLMES_STANDARD = "holmes_standard"
    OWL_CONSERVATIVE = "owl_conservative"
    OWL_RECOMMENDED = "owl_recommended"
    OWL_DRAMATIC = "owl_dramatic"
    VICTORIAN_UNDERWOOD = "victorian_underwood"


class ToneMode(StrEnum):
    COLOUR = "Colour"
    BLACK_AND_WHITE = "Black and White"
    SEPIA = "Sepia"


class CaptionPosition(StrEnum):
    LEFT_IMAGE = "Left image"
    RIGHT_IMAGE = "Right image"
    BOTH_IMAGES = "Both images"


class WindowShape(StrEnum):
    RECTANGLE = "Rectangle"
    CIRCLE = "Circle"
    OVAL = "Oval"
    ARCHED_TOP = "Arched top"


def plain_caption_html(text: str, justification: str = "center") -> str:
    if not text:
        return ""
    return (
        "<p "
        f'align="{escape(justification, quote=True)}" '
        'style="margin:0; '
        f"font-family:{DEFAULT_CAPTION_FONT_FAMILY}; "
        f"font-size:{DEFAULT_CAPTION_FONT_SIZE}pt;"
        f'">{escape(text)}</p>'
    )


@dataclass
class RenderSettings:
    layout_template: CardLayoutName = CardLayoutName.OWL_RECOMMENDED
    tone_mode: ToneMode = ToneMode.COLOUR
    caption_html: str = ""
    caption_position: CaptionPosition = CaptionPosition.BOTH_IMAGES
    window_shape: WindowShape = WindowShape.RECTANGLE
    window_round_corners: bool = False
    image_area_percent: int = 100
    crop_x_percent: int = 0
    crop_y_percent: int = 0
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    sepia_strength: int = 45
    right_eye_transform: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        self.layout_template = CardLayoutName(self.layout_template)
        self.tone_mode = ToneMode(self.tone_mode)
        self.caption_position = CaptionPosition(self.caption_position)
        self.window_shape = WindowShape(self.window_shape)


@dataclass
class ProjectImage:
    path: Path
    source: Image.Image
    frame_index: int = 0
    frame_count: int = 1
    variant_name: str | None = None
    exif: dict[str, str] = field(default_factory=dict)
    settings: RenderSettings = field(default_factory=RenderSettings)

    @property
    def display_name(self) -> str:
        if self.variant_name:
            return f"{self.path.name} [{self.variant_name}]"
        if self.frame_count <= 1:
            return self.path.name
        return f"{self.path.name} [{self.frame_index + 1}/{self.frame_count}]"

    @property
    def thumbnail_name(self) -> str:
        if self.variant_name:
            return self.variant_name
        if self.frame_count > 1:
            return f"Image {self.frame_index + 1}"
        return "Card"
