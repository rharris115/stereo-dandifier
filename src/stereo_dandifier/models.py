from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from PIL import Image

DEFAULT_CAPTION_FONT_FAMILY = "Arial"
DEFAULT_CAPTION_FONT_SIZE = 14


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
    layout_template: str = "owl_recommended"
    tone_mode: str = "Colour"
    caption_html: str = ""
    caption_position: str = "Both images"
    window_shape: str = "Rectangle"
    window_round_corners: bool = False
    image_area_percent: int = 100
    crop_x_percent: int = 0
    crop_y_percent: int = 0
    swap_eyes: bool = True
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    sepia_strength: int = 45
    convergence: int = 0


@dataclass
class ProjectImage:
    path: Path
    source: Image.Image
    frame_index: int = 0
    frame_count: int = 1
    variant_name: str | None = None
    selected_for_export: bool = True
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
