import base64
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    ProjectImage,
    RenderSettings,
    ToneMode,
    WindowShape,
)

CARD_JSON_SCHEMA_VERSION = 1


class RenderSettingsData(BaseModel):
    layout_template: CardLayoutName
    tone_mode: ToneMode
    caption_html: str
    caption_position: CaptionPosition
    window_shape: WindowShape
    window_round_corners: bool
    image_area_percent: int
    crop_x_percent: int
    crop_y_percent: int
    brightness: int
    contrast: int
    saturation: int
    sepia_strength: int
    right_eye_transform: list[float] | None

    @classmethod
    def from_render_settings(cls, settings: RenderSettings) -> "RenderSettingsData":
        return cls(
            layout_template=settings.layout_template,
            tone_mode=settings.tone_mode,
            caption_html=settings.caption_html,
            caption_position=settings.caption_position,
            window_shape=settings.window_shape,
            window_round_corners=settings.window_round_corners,
            image_area_percent=settings.image_area_percent,
            crop_x_percent=settings.crop_x_percent,
            crop_y_percent=settings.crop_y_percent,
            brightness=settings.brightness,
            contrast=settings.contrast,
            saturation=settings.saturation,
            sepia_strength=settings.sepia_strength,
            right_eye_transform=(
                list(settings.right_eye_transform)
                if settings.right_eye_transform is not None
                else None
            ),
        )

    def to_render_settings(self) -> RenderSettings:
        return RenderSettings(
            layout_template=self.layout_template,
            tone_mode=self.tone_mode,
            caption_html=self.caption_html,
            caption_position=self.caption_position,
            window_shape=self.window_shape,
            window_round_corners=self.window_round_corners,
            image_area_percent=self.image_area_percent,
            crop_x_percent=self.crop_x_percent,
            crop_y_percent=self.crop_y_percent,
            brightness=self.brightness,
            contrast=self.contrast,
            saturation=self.saturation,
            sepia_strength=self.sepia_strength,
            right_eye_transform=(
                tuple(self.right_eye_transform)
                if self.right_eye_transform is not None
                else None
            ),
        )


class EmbeddedImageData(BaseModel):
    media_type: Literal["image/png"] = "image/png"
    encoding: Literal["base64"] = "base64"
    width: int
    height: int
    data: str = Field(description="Base64-encoded PNG image data.")


class CardData(BaseModel):
    schema_version: int = CARD_JSON_SCHEMA_VERSION
    exif: dict[str, str]
    settings: RenderSettingsData
    source_image: EmbeddedImageData


def card_data_from_project_image(project_image: ProjectImage) -> CardData:
    return CardData(
        exif=dict(project_image.exif),
        settings=RenderSettingsData.from_render_settings(project_image.settings),
        source_image=embedded_png_from_image(project_image.source),
    )


def embedded_png_from_image(image: Image.Image) -> EmbeddedImageData:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return EmbeddedImageData(
        width=image.width,
        height=image.height,
        data=encoded,
    )


def image_from_embedded_png(image_data: EmbeddedImageData) -> Image.Image:
    decoded = base64.b64decode(image_data.data)
    with Image.open(BytesIO(decoded)) as image:
        return image.convert("RGB")


def project_image_from_card_data(card_data: CardData, path: Path) -> ProjectImage:
    return ProjectImage(
        path=path,
        source=image_from_embedded_png(card_data.source_image),
        exif=dict(card_data.exif),
        settings=card_data.settings.to_render_settings(),
    )


def load_card_json(path: Path) -> ProjectImage:
    card_data = CardData.model_validate_json(path.read_text(encoding="utf-8"))
    return project_image_from_card_data(card_data, path)


def save_card_json(project_image: ProjectImage, path: Path) -> None:
    card_data = card_data_from_project_image(project_image)
    path.write_text(card_data.model_dump_json(indent=2), encoding="utf-8")
