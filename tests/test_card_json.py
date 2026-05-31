import base64
import json
from io import BytesIO

from PIL import Image

from stereo_dandifier.card_json import (
    CardData,
    card_data_from_project_image,
    load_card_json,
    save_card_json,
)
from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    ProjectImage,
    RenderSettings,
    ToneMode,
    WindowShape,
)


def test_card_data_embeds_source_image_as_base64_png(tmp_path):
    project_image = ProjectImage(
        path=tmp_path / "source.png",
        source=Image.new("RGB", (4, 2), (10, 20, 30)),
        exif={"Camera": "Stereo Box"},
        settings=RenderSettings(
            brightness=120,
            right_eye_transform=(1.0, 0.0, 2.0, 0.0, 1.0, -3.0),
        ),
    )

    card_data = card_data_from_project_image(project_image)
    payload = json.loads(card_data.model_dump_json())
    parsed = CardData.model_validate(payload)
    decoded = Image.open(BytesIO(base64.b64decode(parsed.source_image.data)))

    assert parsed.exif == {"Camera": "Stereo Box"}
    assert "swap_eyes" not in payload["settings"]
    assert parsed.settings.brightness == 120
    assert parsed.settings.right_eye_transform == [1.0, 0.0, 2.0, 0.0, 1.0, -3.0]
    assert parsed.source_image.media_type == "image/png"
    assert decoded.size == (4, 2)
    assert decoded.getpixel((0, 0)) == (10, 20, 30)


def test_load_card_json_restores_source_image_and_settings(tmp_path):
    path = tmp_path / "card.stereocard.json"
    project_image = ProjectImage(
        path=tmp_path / "source.png",
        source=Image.new("RGB", (6, 4), (100, 80, 60)),
        exif={"Lens": "stereo"},
        settings=RenderSettings(
            layout_template=CardLayoutName.HOLMES_STANDARD,
            tone_mode=ToneMode.SEPIA,
            caption_html="<p>Loaded card</p>",
            caption_position=CaptionPosition.LEFT_IMAGE,
            window_shape=WindowShape.CIRCLE,
            window_round_corners=True,
            image_area_percent=70,
            crop_x_percent=20,
            crop_y_percent=-10,
            brightness=30,
            contrast=12,
            saturation=-5,
            sepia_strength=80,
            right_eye_transform=(1.0, 0.0, 2.0, 0.0, 1.0, -3.0),
        ),
    )

    save_card_json(project_image, path)
    loaded = load_card_json(path)

    assert loaded.path == path
    assert loaded.exif == {"Lens": "stereo"}
    assert loaded.source.size == (6, 4)
    assert loaded.source.getpixel((0, 0)) == (100, 80, 60)
    assert loaded.settings.layout_template is CardLayoutName.HOLMES_STANDARD
    assert loaded.settings.tone_mode is ToneMode.SEPIA
    assert loaded.settings.caption_html == "<p>Loaded card</p>"
    assert loaded.settings.caption_position is CaptionPosition.LEFT_IMAGE
    assert loaded.settings.window_shape is WindowShape.CIRCLE
    assert loaded.settings.window_round_corners
    assert loaded.settings.image_area_percent == 70
    assert loaded.settings.crop_x_percent == 20
    assert loaded.settings.crop_y_percent == -10
    assert loaded.settings.brightness == 30
    assert loaded.settings.contrast == 12
    assert loaded.settings.saturation == -5
    assert loaded.settings.sepia_strength == 80
    assert loaded.settings.right_eye_transform == (1.0, 0.0, 2.0, 0.0, 1.0, -3.0)
