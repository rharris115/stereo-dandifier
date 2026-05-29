from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass
class RenderSettings:
    layout_template: str = "Holmes (standard)"
    tone_mode: str = "Colour"
    caption: str = ""
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
    exif: dict[str, str] = field(default_factory=dict)
    settings: RenderSettings = field(default_factory=RenderSettings)

    @property
    def display_name(self) -> str:
        if self.variant_name:
            return f"{self.path.name} [{self.variant_name}]"
        if self.frame_count <= 1:
            return self.path.name
        return f"{self.path.name} [{self.frame_index + 1}/{self.frame_count}]"
