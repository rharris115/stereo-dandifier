from PIL import Image

from stereo_dandifier.formats import CARD_FORMATS
from stereo_dandifier.models import RenderSettings
from stereo_dandifier.stereo_ops import split_stereo_pair


def native_card_image_dpi(source: Image.Image, settings: RenderSettings) -> int:
    spec = CARD_FORMATS[settings.layout_template]
    image_w_mm, image_h_mm = spec.image_mm
    left, _right = split_stereo_pair(source, settings)

    width_dpi = left.width / (image_w_mm / 25.4)
    height_dpi = left.height / (image_h_mm / 25.4)
    return max(1, round(min(width_dpi, height_dpi)))


def export_dpi_for_source(
    source: Image.Image, settings: RenderSettings, minimum_dpi: int
) -> int:
    return max(
        minimum_dpi,
        native_card_image_dpi(source, settings),
        source_metadata_dpi(source) or 0,
    )


def source_metadata_dpi(source: Image.Image) -> int | None:
    dpi = source.info.get("dpi")
    if isinstance(dpi, tuple) and dpi:
        values = [
            value for value in dpi if isinstance(value, int | float) and value > 0
        ]
        if values:
            return round(min(values))
    if isinstance(dpi, int | float) and dpi > 0:
        return round(dpi)
    return None
