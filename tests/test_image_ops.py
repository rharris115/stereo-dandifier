import os

import numpy as np
import pytest
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from stereo_dandifier.formats import CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.image_ops import (
    PDF_IMAGE_SAVE_OPTIONS,
    apply_shared_levels,
    apply_style,
    auto_improve_stereo_pair,
    caption_html_text,
    caption_windows,
    card_window_geometry,
    compute_shared_levels,
    centered_caption_y,
    crop_axis_origin,
    crop_to_window,
    effective_window_shape,
    export_dpi_for_source,
    card_grid,
    native_card_image_dpi,
    render_caption_html,
    render_project_card,
    render_print_pages,
    render_card,
    save_pdf_pages,
    score_comfort,
    source_metadata_dpi,
    split_stereo_pair,
    source_crop_box,
    stereo_alignment_report,
    stereo_window_x_positions,
    suggested_right_eye_transform,
    trim_vertical_transparent,
    visible_image_bottom,
    window_bounds_for_project,
    window_mask,
)
from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    ProjectImage,
    RenderSettings,
    ToneMode,
    WindowShape,
    plain_caption_html,
)
from stereo_dandifier.print_layout import page_layout_for_name


def test_split_stereo_pair_keeps_left_right_order():
    image = Image.new("RGB", (4, 2))
    image.paste((255, 0, 0), (0, 0, 2, 2))
    image.paste((0, 0, 255), (2, 0, 4, 2))

    left, right = split_stereo_pair(image, RenderSettings())

    assert left.getpixel((0, 0)) == (255, 0, 0)
    assert right.getpixel((0, 0)) == (0, 0, 255)


def test_split_stereo_pair_applies_rectification_transform_before_swap():
    image = Image.new("RGB", (4, 4), (0, 0, 0))
    image.paste((255, 0, 0), (0, 2, 2, 4))
    image.paste((0, 0, 255), (2, 2, 4, 4))

    left, right = split_stereo_pair(
        image,
        RenderSettings(
            right_eye_transform=(1.0, 0.0, 0.0, 0.0, 1.0, -2.0),
        ),
    )

    assert left.getpixel((0, 2)) == (255, 0, 0)
    assert right.getpixel((0, 0)) == (0, 0, 255)


def test_render_project_card_only_crosses_when_preview_requests_it(tmp_path):
    source = Image.new("RGB", (800, 300))
    source.paste((255, 0, 0), (0, 0, 400, 300))
    source.paste((0, 0, 255), (400, 0, 800, 300))
    project_image = ProjectImage(path=tmp_path / "card.png", source=source)
    left_x, right_x, top, image_w, image_h, _spacing = card_window_geometry(
        project_image.settings, dpi=300
    )

    normal = render_project_card(project_image, dpi=300)
    crossed = render_project_card(project_image, dpi=300, cross_eyed=True)
    sample_y = top + image_h // 2

    assert normal.getpixel((left_x + image_w // 2, sample_y)) == (255, 0, 0)
    assert normal.getpixel((right_x + image_w // 2, sample_y)) == (0, 0, 255)
    assert crossed.getpixel((left_x + image_w // 2, sample_y)) == (0, 0, 255)
    assert crossed.getpixel((right_x + image_w // 2, sample_y)) == (255, 0, 0)


@pytest.mark.parametrize("name,spec", CARD_FORMATS.items())
def test_render_card_uses_selected_format_size(name, spec):
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings(layout_template=name)
    left, right = split_stereo_pair(source, settings)
    card = render_card(left, right, settings)

    assert card.size == mm_pair_to_px(spec.card_mm)


def test_render_card_can_use_higher_preview_dpi():
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings()
    left, right = split_stereo_pair(source, settings)

    card = render_card(left, right, settings, dpi=600)

    assert card.size == mm_pair_to_px(
        CARD_FORMATS[settings.layout_template].card_mm, dpi=600
    )


def test_native_card_image_dpi_uses_original_eye_pixels_and_card_window_size():
    source = Image.new("RGB", (4000, 2000), (120, 130, 140))
    settings = RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD)

    assert native_card_image_dpi(source, settings) == 726


def test_export_dpi_uses_native_source_detail_above_preview_floor():
    source = Image.new("RGB", (12000, 6000), (120, 130, 140))
    settings = RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD)

    assert export_dpi_for_source(source, settings, minimum_dpi=600) == 2177


def test_export_dpi_never_drops_below_preview_floor():
    source = Image.new("RGB", (1000, 500), (120, 130, 140))
    settings = RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD)

    assert export_dpi_for_source(source, settings, minimum_dpi=600) == 600


def test_export_dpi_can_use_source_metadata_dpi():
    source = Image.new("RGB", (1000, 500), (120, 130, 140))
    source.info["dpi"] = (720, 720)
    settings = RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD)

    assert export_dpi_for_source(source, settings, minimum_dpi=1) == 720


def test_source_metadata_dpi_uses_lower_axis_value():
    source = Image.new("RGB", (1000, 500), (120, 130, 140))
    source.info["dpi"] = (600.4, 300.2)

    assert source_metadata_dpi(source) == 300


def test_render_card_defaults_to_white_without_visible_window_borders():
    source = Image.new("RGB", (800, 300), (120, 130, 140))
    settings = RenderSettings()
    left, right = split_stereo_pair(source, settings)

    card = render_card(left, right, settings)

    assert card.getpixel((5, 5)) == (255, 255, 255)


def test_stereo_window_positions_center_pair_on_card():
    left_x, right_x = stereo_window_x_positions(card_w=2126, image_w=827, spacing=898)

    assert left_x == 200
    assert right_x == 1098
    assert left_x == 2126 - (right_x + 827) - 1


@pytest.mark.parametrize("name,spec", CARD_FORMATS.items())
def test_rendered_window_pair_has_balanced_outer_margins(name, spec):
    card_w, _card_h = mm_pair_to_px(spec.card_mm)
    image_w, _image_h = mm_pair_to_px(spec.image_mm)
    spacing = mm_to_px(spec.center_spacing_mm)

    left_x, right_x = stereo_window_x_positions(card_w, image_w, spacing)
    left_margin = left_x
    right_margin = card_w - (right_x + image_w)

    assert abs(left_margin - right_margin) <= 1


def test_caption_windows_start_from_visible_fitted_image_bottom():
    left = Image.new("RGB", (70, 30))
    right = Image.new("RGB", (70, 50))

    assert caption_windows(
        CaptionPosition.BOTH_IMAGES, 10, 90, left, right, image_y=8, image_h=70
    ) == [
        (10, 58),
        (90, 68),
    ]


def test_visible_image_bottom_uses_centered_fitted_image():
    assert visible_image_bottom(image_y=8, image_h=70, fitted_h=30) == 58


def test_caption_html_text_extracts_plain_text_with_qt_document():
    assert caption_html_text(plain_caption_html("First wicket")) == "First wicket"


def test_caption_render_scales_with_output_resolution():
    app = QApplication.instance() or QApplication([])

    low = render_caption_html(plain_caption_html("First wicket"), 1000, 300, dpi=72)
    high = render_caption_html(plain_caption_html("First wicket"), 1000, 300, dpi=600)

    assert app is not None
    assert alpha_height(high) > alpha_height(low) * 4


def test_caption_render_includes_multiple_lines():
    app = QApplication.instance() or QApplication([])
    caption = (
        '<p style="margin:0; font-family:Arial; font-size:14pt;">First wicket</p>'
        '<p style="margin:0; font-family:Arial; font-size:14pt;">Second innings</p>'
    )

    rendered = render_caption_html(caption, 827, 142, dpi=300)

    assert app is not None
    assert len(alpha_line_clusters(rendered)) >= 2


def test_trim_vertical_transparent_keeps_caption_width_for_alignment():
    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    image.paste((10, 20, 30, 255), (4, 6, 12, 14))

    trimmed = trim_vertical_transparent(image)

    assert trimmed.size == (20, 8)


def test_centered_caption_y_bisects_window_bottom_to_card_bottom():
    y = centered_caption_y(window_bottom=100, card_bottom=160, caption_height=20)

    assert y == 120
    assert y - 100 == 160 - (y + 20)


def test_caption_is_centered_between_visible_image_bottom_and_card_bottom():
    app = QApplication.instance() or QApplication([])
    settings = RenderSettings(caption_html=plain_caption_html("First wicket"))
    left = Image.new("RGB", (800, 300), (120, 130, 140))
    right = Image.new("RGB", (800, 300), (120, 130, 140))

    card = render_card(left, right, settings, dpi=300)
    left_x, _right_x, top_margin, image_w, image_h, _spacing = card_window_geometry(
        settings, dpi=300
    )
    visible_bottom = top_margin + image_h
    caption_bbox = non_white_bbox(
        card, (left_x, visible_bottom, left_x + image_w, card.height)
    )

    assert app is not None
    assert caption_bbox is not None
    above = caption_bbox[1] - visible_bottom
    below = card.height - caption_bbox[3]
    assert abs(above - below) <= 8


def test_circle_window_masks_window_corners():
    settings = RenderSettings(
        layout_template=CardLayoutName.HOLMES_STANDARD,
        window_shape=WindowShape.CIRCLE,
    )
    source = Image.new("RGB", (800, 300), (255, 0, 0))

    card = render_card(source, source, settings, dpi=300)
    left_x, _right_x = stereo_window_x_positions(
        card_w=2126,
        image_w=827,
        spacing=898,
    )

    assert card.getpixel((left_x, 95)) == (255, 255, 255)
    assert card.getpixel((left_x + 413, 95 + 413)) == (255, 0, 0)


def test_rectangular_layouts_render_circle_choice_as_oval():
    settings = RenderSettings(
        layout_template=CardLayoutName.OWL_RECOMMENDED,
        window_shape=WindowShape.CIRCLE,
    )

    assert effective_window_shape(settings) == WindowShape.OVAL


def test_window_crop_offset_selects_different_source_area():
    source = Image.new("RGB", (4, 4))
    source.paste((255, 0, 0), (0, 0, 2, 4))
    source.paste((0, 0, 255), (2, 0, 4, 4))

    left_crop = crop_to_window(
        source, 2, 2, RenderSettings(image_area_percent=50, crop_x_percent=-100)
    )
    right_crop = crop_to_window(
        source, 2, 2, RenderSettings(image_area_percent=50, crop_x_percent=100)
    )

    assert left_crop.getpixel((0, 0)) == (255, 0, 0)
    assert right_crop.getpixel((0, 0)) == (0, 0, 255)


def test_image_area_percent_selects_vertical_source_distance():
    settings = RenderSettings(image_area_percent=50)

    assert source_crop_box((100, 200), (50, 100), settings) == (25, 50, 75, 150)


def test_vertical_movement_shifts_visible_source_area():
    top = source_crop_box(
        (100, 200),
        (50, 100),
        RenderSettings(image_area_percent=50, crop_y_percent=-100),
    )
    bottom = source_crop_box(
        (100, 200),
        (50, 100),
        RenderSettings(image_area_percent=50, crop_y_percent=100),
    )

    assert top == (25, 0, 75, 100)
    assert bottom == (25, 100, 75, 200)


def test_crop_axis_origin_maps_percent_to_available_offset():
    assert crop_axis_origin(100, -100) == 0
    assert crop_axis_origin(100, 0) == 50
    assert crop_axis_origin(100, 100) == 100


def test_window_mask_supports_classic_arched_top():
    mask = window_mask(20, 30, WindowShape.ARCHED_TOP)

    assert mask.getpixel((0, 0)) == 0
    assert mask.getpixel((10, 0)) > 200
    assert mask.getpixel((0, 5)) < 255
    assert mask.getpixel((0, 8)) > 0
    assert mask.getpixel((0, 29)) == 255


def test_window_mask_supports_rounded_rectangle_corners():
    mask = window_mask(40, 60, WindowShape.RECTANGLE, round_corners=True)

    assert mask.getpixel((0, 0)) == 0
    assert mask.getpixel((20, 0)) == 255
    assert mask.getpixel((0, 30)) == 255


def test_window_mask_supports_rounded_arched_bottom_corners():
    mask = window_mask(40, 60, WindowShape.ARCHED_TOP, round_corners=True)

    assert mask.getpixel((0, 59)) < 255
    assert mask.getpixel((20, 59)) == 255


def test_window_bounds_for_project_matches_rendered_window_pair(tmp_path):
    project_image = ProjectImage(
        path=tmp_path / "card.png",
        source=Image.new("RGB", (800, 300), (255, 0, 0)),
        settings=RenderSettings(),
    )

    bounds = window_bounds_for_project(project_image, dpi=300)

    assert bounds == [(201, 83, 850, 744), (1051, 83, 850, 744)]


def test_black_and_white_mode_removes_colour():
    source = Image.new("RGB", (1, 1), (200, 80, 20))
    styled = apply_style(source, RenderSettings(tone_mode=ToneMode.BLACK_AND_WHITE))

    red, green, blue = styled.getpixel((0, 0))
    assert red == green == blue


def test_sepia_mode_tints_grayscale_image():
    source = Image.new("RGB", (1, 1), (200, 80, 20))
    styled = apply_style(
        source, RenderSettings(tone_mode=ToneMode.SEPIA, sepia_strength=80)
    )

    red, green, blue = styled.getpixel((0, 0))
    assert red > green > blue


def test_colour_mode_can_adjust_saturation():
    source = Image.new("RGB", (1, 1), (180, 100, 100))
    styled = apply_style(
        source, RenderSettings(tone_mode=ToneMode.COLOUR, saturation=40)
    )

    assert styled.getpixel((0, 0)) != source.getpixel((0, 0))


def test_compute_shared_levels_uses_combined_eye_statistics():
    left = Image.new("RGB", (2, 1))
    left.putdata([(10, 20, 30), (100, 110, 120)])
    right = Image.new("RGB", (2, 1))
    right.putdata([(150, 160, 170), (240, 250, 255)])

    low, high = compute_shared_levels(left, right, cutoff=0)

    np.testing.assert_allclose(low, np.array([10, 20, 30], dtype=np.float32))
    np.testing.assert_allclose(high, np.array([240, 250, 255], dtype=np.float32))


def test_auto_improve_stereo_pair_applies_identical_levels_to_both_eyes():
    left = Image.new("RGB", (3, 1))
    left.putdata([(20, 20, 20), (100, 120, 140), (120, 120, 120)])
    right = Image.new("RGB", (3, 1))
    right.putdata([(100, 120, 140), (180, 180, 180), (240, 240, 240)])

    adjusted_left, adjusted_right = auto_improve_stereo_pair(left, right, cutoff=0)

    assert adjusted_left.getpixel((1, 0)) == adjusted_right.getpixel((0, 0))


def test_auto_improve_stereo_pair_preserves_size_and_returns_rgb():
    left = Image.new("L", (3, 2), 80)
    right = Image.new("RGBA", (4, 1), (120, 130, 140, 128))

    adjusted_left, adjusted_right = auto_improve_stereo_pair(left, right)

    assert adjusted_left.size == left.size
    assert adjusted_right.size == right.size
    assert adjusted_left.mode == "RGB"
    assert adjusted_right.mode == "RGB"


def test_shared_levels_handles_flat_low_contrast_images_cleanly():
    left = Image.new("L", (2, 2), 118)
    right = Image.new("RGB", (2, 2), (120, 120, 120))

    adjusted_left, adjusted_right = auto_improve_stereo_pair(left, right)

    assert adjusted_left.mode == "RGB"
    assert adjusted_right.mode == "RGB"
    assert adjusted_left.size == left.size
    assert adjusted_right.size == right.size
    assert adjusted_left.getpixel((0, 0)) == (0, 0, 0)
    assert adjusted_right.getpixel((0, 0)) == (255, 255, 255)


def test_apply_shared_levels_leaves_zero_range_channels_unchanged():
    image = Image.new("RGB", (1, 1), (40, 100, 200))
    low = np.array([40, 100, 10], dtype=np.float32)
    high = np.array([40, 100, 210], dtype=np.float32)

    adjusted = apply_shared_levels(image, low, high)

    assert adjusted.getpixel((0, 0)) == (40, 100, 242)


def test_stereo_alignment_report_detects_vertical_offset():
    source = synthetic_stereo_pair(vertical_offset=4)

    report = stereo_alignment_report(source, RenderSettings())

    assert report.vertical_offset_px == pytest.approx(4, abs=0.25)
    assert report.confidence >= 0.35


def test_comfort_status_warns_about_rectification_issue():
    source = synthetic_stereo_pair(vertical_offset=4)

    score = score_comfort(source, RenderSettings())

    assert score.startswith("Poor - vertical alignment off by")


def test_suggested_right_eye_transform_corrects_rectification_issue():
    source = synthetic_stereo_pair(vertical_offset=4)

    transform = suggested_right_eye_transform(source)
    rectified_settings = RenderSettings(right_eye_transform=transform)

    assert transform is not None
    assert len(transform) in {6, 9}
    assert transform[5] == pytest.approx(-4, abs=0.5)
    assert score_comfort(source, rectified_settings) == "Excellent"


def test_comfort_status_ignores_textureless_alignment_analysis():
    source = Image.new("RGB", (320, 100), (120, 130, 140))

    assert score_comfort(source, RenderSettings()) == "Excellent"


def test_print_preview_places_card_on_paper_with_blue_cut_guides():
    card = Image.new("RGB", (300, 120), (255, 255, 255))
    page_layout = page_layout_for_name("A4")

    preview = render_print_pages([card], page_layout)[0]

    assert preview.size == mm_pair_to_px(page_layout.size_mm)
    columns, rows = card_grid(card.width, card.height, page_layout)
    left = (preview.width - columns * card.width) // 2
    top = (preview.height - rows * card.height) // 2
    right = left + card.width
    bottom = top + card.height
    guide_colour = (170, 210, 246)
    assert preview.getpixel((left, 0)) == guide_colour
    assert preview.getpixel((right, 0)) == guide_colour
    assert preview.getpixel((0, top)) == guide_colour
    assert preview.getpixel((0, bottom)) == guide_colour
    assert preview.getpixel((left + 10, top + 10)) == (255, 255, 255)


def test_print_pages_maximise_cards_per_page():
    page_layout = page_layout_for_name("A4")
    card = Image.new(
        "RGB",
        mm_pair_to_px(CARD_FORMATS[CardLayoutName.HOLMES_STANDARD].card_mm),
        (255, 255, 255),
    )

    pages = render_print_pages([card, card, card, card], page_layout)

    assert len(pages) == 2


def test_save_pdf_pages_uses_high_quality_image_encoding(monkeypatch):
    calls = []

    def fake_save(self, file_path, file_format, **kwargs):
        calls.append((file_path, file_format, kwargs))

    monkeypatch.setattr(Image.Image, "save", fake_save)

    save_pdf_pages([Image.new("RGB", (120, 80), (255, 255, 255))], "card.pdf", dpi=600)

    assert calls[0][1] == "PDF"
    for key, value in PDF_IMAGE_SAVE_OPTIONS.items():
        assert calls[0][2][key] == value


def alpha_height(image: Image.Image) -> int:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return 0
    return bbox[3] - bbox[1]


def alpha_line_clusters(image: Image.Image) -> list[tuple[int, int]]:
    alpha = image.getchannel("A")
    rows = []
    for y in range(alpha.height):
        if alpha.crop((0, y, alpha.width, y + 1)).getbbox() is not None:
            rows.append(y)

    clusters = []
    for y in rows:
        if not clusters or y > clusters[-1][1] + 1:
            clusters.append((y, y))
        else:
            clusters[-1] = (clusters[-1][0], y)
    return clusters


def synthetic_stereo_pair(vertical_offset: int = 0) -> Image.Image:
    rng = np.random.default_rng(123)
    left = Image.fromarray(
        rng.integers(0, 256, (160, 220, 3), dtype=np.uint8),
        mode="RGB",
    )
    draw = ImageDraw.Draw(left)
    for _index in range(40):
        x = int(rng.integers(5, 200))
        y = int(rng.integers(5, 145))
        radius = int(rng.integers(2, 7))
        colour = tuple(int(value) for value in rng.integers(0, 256, 3))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)

    right = Image.new("RGB", left.size, (128, 128, 128))
    right.paste(left, (9, vertical_offset))

    source = Image.new("RGB", (left.width + right.width, left.height), (128, 128, 128))
    source.paste(left, (0, 0))
    source.paste(right, (left.width, 0))
    return source


def non_white_bbox(
    image: Image.Image, bounds: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    crop = image.crop(bounds).convert("RGB")
    pixels = []
    for y in range(crop.height):
        for x in range(crop.width):
            if crop.getpixel((x, y)) != (255, 255, 255):
                pixels.append((x + bounds[0], y + bounds[1]))

    if not pixels:
        return None
    xs = [x for x, _y in pixels]
    ys = [y for _x, y in pixels]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
