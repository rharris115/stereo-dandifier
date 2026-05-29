import pytest
from PIL import Image

from stereo_dandifier.formats import CARD_FORMATS, mm_pair_to_px
from stereo_dandifier.image_ops import apply_style, render_card, split_stereo_pair
from stereo_dandifier.models import RenderSettings


def test_split_stereo_pair_swaps_eyes_by_default():
    image = Image.new("RGB", (4, 2))
    image.paste((255, 0, 0), (0, 0, 2, 2))
    image.paste((0, 0, 255), (2, 0, 4, 2))

    left, right = split_stereo_pair(image, RenderSettings())

    assert left.getpixel((0, 0)) == (0, 0, 255)
    assert right.getpixel((0, 0)) == (255, 0, 0)


@pytest.mark.parametrize("name,spec", CARD_FORMATS.items())
def test_render_card_uses_selected_format_size(name, spec):
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings(layout_template=name)
    left, right = split_stereo_pair(source, settings)
    card = render_card(left, right, settings)

    assert card.size == mm_pair_to_px(spec["card_mm"])


def test_black_and_white_mode_removes_colour():
    source = Image.new("RGB", (1, 1), (200, 80, 20))
    styled = apply_style(source, RenderSettings(tone_mode="Black and White"))

    red, green, blue = styled.getpixel((0, 0))
    assert red == green == blue


def test_sepia_mode_tints_grayscale_image():
    source = Image.new("RGB", (1, 1), (200, 80, 20))
    styled = apply_style(source, RenderSettings(tone_mode="Sepia", sepia_strength=80))

    red, green, blue = styled.getpixel((0, 0))
    assert red > green > blue


def test_colour_mode_can_adjust_saturation():
    source = Image.new("RGB", (1, 1), (180, 100, 100))
    styled = apply_style(source, RenderSettings(tone_mode="Colour", saturation=40))

    assert styled.getpixel((0, 0)) != source.getpixel((0, 0))
