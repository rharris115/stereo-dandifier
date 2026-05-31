from PIL import Image

from stereo_dandifier.caption_rendering import (
    caption_html_text,
    caption_windows,
    centered_caption_y,
    render_caption_html,
    trim_vertical_transparent,
)
from stereo_dandifier.formats import EXPORT_DPI, CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.models import ProjectImage, RenderSettings
from stereo_dandifier.photo_ops import apply_style
from stereo_dandifier.stereo_ops import split_stereo_pair
from stereo_dandifier.window_geometry import (
    card_window_geometry,
    crop_to_window,
    effective_window_shape,
    paste_window,
    stereo_window_x_positions,
)


def render_card(
    left: Image.Image,
    right: Image.Image,
    settings: RenderSettings,
    dpi: int = EXPORT_DPI,
) -> Image.Image:
    spec = CARD_FORMATS[settings.layout_template]
    card_w, card_h = mm_pair_to_px(spec.card_mm, dpi=dpi)
    image_w, image_h = mm_pair_to_px(spec.image_mm, dpi=dpi)
    top_margin = mm_to_px(spec.top_margin_mm, dpi=dpi)
    spacing = mm_to_px(spec.center_spacing_mm, dpi=dpi)

    card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
    left_fit = crop_to_window(left, image_w, image_h, settings)
    right_fit = crop_to_window(right, image_w, image_h, settings)

    left_x, right_x = stereo_window_x_positions(card_w, image_w, spacing)
    image_y = top_margin
    window_shape = effective_window_shape(settings)
    paste_window(
        card,
        left_fit,
        left_x,
        image_y,
        window_shape,
        round_corners=settings.window_round_corners,
    )
    paste_window(
        card,
        right_fit,
        right_x,
        image_y,
        window_shape,
        round_corners=settings.window_round_corners,
    )

    if caption_html_text(settings.caption_html):
        for window_x, visible_bottom in caption_windows(
            settings.caption_position,
            left_x,
            right_x,
            left_fit,
            right_fit,
            image_y,
            image_h,
        ):
            caption_h = max(1, card_h - visible_bottom)
            caption = render_caption_html(
                settings.caption_html, image_w, caption_h, dpi=dpi
            )
            caption_content = trim_vertical_transparent(caption)
            caption_y = centered_caption_y(
                window_bottom=visible_bottom,
                card_bottom=card_h,
                caption_height=caption_content.height,
            )
            card.paste(caption_content, (window_x, caption_y), caption_content)

    return card


def render_project_card(
    project_image: ProjectImage, dpi: int, cross_eyed: bool = False
) -> Image.Image:
    left, right = split_stereo_pair(project_image.source, project_image.settings)
    if cross_eyed:
        left, right = right, left
    return render_card(
        apply_style(left, project_image.settings),
        apply_style(right, project_image.settings),
        project_image.settings,
        dpi=dpi,
    )


def caption_bounds_for_project(
    project_image: ProjectImage, dpi: int
) -> list[tuple[int, int, int, int]]:
    settings = project_image.settings
    spec = CARD_FORMATS[settings.layout_template]
    _card_w, card_h = mm_pair_to_px(spec.card_mm, dpi=dpi)
    left_x, right_x, top_margin, image_w, image_h, _spacing = card_window_geometry(
        settings, dpi
    )

    left, right = split_stereo_pair(project_image.source, settings)
    left_fit = crop_to_window(left, image_w, image_h, settings)
    right_fit = crop_to_window(right, image_w, image_h, settings)

    return [
        (window_x, visible_bottom, image_w, card_h - visible_bottom)
        for window_x, visible_bottom in caption_windows(
            settings.caption_position,
            left_x,
            right_x,
            left_fit,
            right_fit,
            top_margin,
            image_h,
        )
    ]
