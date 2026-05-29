import pytest
from PIL import Image

from stereo_dandifier.formats import CARD_FORMATS, mm_pair_to_px
from stereo_dandifier.image_ops import (
    apply_style,
    export_dpi_for_source,
    native_card_image_dpi,
    render_card,
    render_print_preview,
    save_pdf,
    split_stereo_pair,
)
from stereo_dandifier.models import RenderSettings
from stereo_dandifier.print_layout import page_layout_for_name


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


def test_render_card_can_use_higher_preview_dpi():
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings()
    left, right = split_stereo_pair(source, settings)

    card = render_card(left, right, settings, dpi=600)

    assert card.size == mm_pair_to_px(
        CARD_FORMATS[settings.layout_template]["card_mm"], dpi=600
    )


def test_native_card_image_dpi_uses_original_eye_pixels_and_card_window_size():
    source = Image.new("RGB", (4000, 2000), (120, 130, 140))
    settings = RenderSettings(layout_template="Holmes (standard)")

    assert native_card_image_dpi(source, settings) == 726


def test_export_dpi_uses_native_source_detail_above_preview_floor():
    source = Image.new("RGB", (12000, 6000), (120, 130, 140))
    settings = RenderSettings(layout_template="Holmes (standard)")

    assert export_dpi_for_source(source, settings, minimum_dpi=600) == 2177


def test_export_dpi_never_drops_below_preview_floor():
    source = Image.new("RGB", (1000, 500), (120, 130, 140))
    settings = RenderSettings(layout_template="Holmes (standard)")

    assert export_dpi_for_source(source, settings, minimum_dpi=600) == 600


def test_render_card_defaults_to_white_without_visible_window_borders():
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings()
    left, right = split_stereo_pair(source, settings)

    card = render_card(left, right, settings)

    assert card.getpixel((5, 5)) == (255, 255, 255)


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


def test_print_preview_places_card_on_paper_with_blue_cut_guides():
    card = Image.new("RGB", (300, 120), (255, 255, 255))
    page_layout = page_layout_for_name("A4")

    preview = render_print_preview(card, page_layout)

    assert preview.size == mm_pair_to_px(page_layout.size_mm)
    left = (preview.width - card.width) // 2
    top = (preview.height - card.height) // 2
    right = left + card.width
    bottom = top + card.height
    guide_colour = (170, 210, 246)
    assert preview.getpixel((left, 0)) == guide_colour
    assert preview.getpixel((right, 0)) == guide_colour
    assert preview.getpixel((0, top)) == guide_colour
    assert preview.getpixel((0, bottom)) == guide_colour
    assert preview.getpixel((left + 10, top + 10)) == (255, 255, 255)


def test_save_pdf_writes_pdf_file(tmp_path):
    path = tmp_path / "card.pdf"
    page = Image.new("RGB", (120, 80), (255, 255, 255))

    save_pdf(page, str(path), dpi=600)

    assert path.read_bytes().startswith(b"%PDF")
