from PIL import Image, ImageDraw, ImageEnhance

from stereo_dandifier.formats import CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.models import RenderSettings


def split_stereo_pair(
    image: Image.Image, settings: RenderSettings
) -> tuple[Image.Image, Image.Image]:
    width, height = image.size
    midpoint = width // 2
    left = image.crop((0, 0, midpoint, height))
    right = image.crop((midpoint, 0, width, height))

    if settings.convergence:
        left = horizontal_shift(left, settings.convergence)
        right = horizontal_shift(right, -settings.convergence)

    if settings.swap_eyes:
        return right, left
    return left, right


def horizontal_shift(image: Image.Image, pixels: int) -> Image.Image:
    if pixels == 0:
        return image
    shifted = Image.new("RGB", image.size, (245, 241, 232))
    shifted.paste(image, (pixels, 0))
    return shifted


def apply_style(image: Image.Image, settings: RenderSettings) -> Image.Image:
    styled = image.convert("RGB")

    if settings.brightness:
        factor = 1 + (settings.brightness / 100)
        styled = ImageEnhance.Brightness(styled).enhance(factor)

    if settings.contrast:
        factor = 1 + (settings.contrast / 100)
        styled = ImageEnhance.Contrast(styled).enhance(factor)

    if settings.tone_mode == "Black and White":
        return styled.convert("L").convert("RGB")

    if settings.tone_mode == "Sepia":
        grey = styled.convert("L").convert("RGB")
        sepia = Image.new("RGB", styled.size, (118, 88, 55))
        toned = Image.blend(grey, sepia, 0.36)
        return Image.blend(grey, toned, settings.sepia_strength / 100)

    if settings.saturation:
        factor = 1 + (settings.saturation / 100)
        styled = ImageEnhance.Color(styled).enhance(factor)

    return styled


def render_card(
    left: Image.Image, right: Image.Image, settings: RenderSettings
) -> Image.Image:
    spec = CARD_FORMATS[settings.layout_template]
    card_w, card_h = mm_pair_to_px(spec["card_mm"])
    image_w, image_h = mm_pair_to_px(spec["image_mm"])
    side_margin = mm_to_px(spec["side_margin_mm"])
    top_margin = mm_to_px(spec["top_margin_mm"])
    bottom_area = mm_to_px(spec["bottom_mm"])
    if spec["gap_mm"] is None:
        spacing = mm_to_px(spec["center_spacing_mm"])
    else:
        spacing = image_w + mm_to_px(spec["gap_mm"])

    card = Image.new("RGB", (card_w, card_h), (246, 240, 226))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (mm_to_px(1.5), mm_to_px(1.5), card_w - mm_to_px(1.5), card_h - mm_to_px(1.5)),
        radius=18,
        outline=(133, 111, 80),
        width=4,
    )

    left_fit = fit_to_box(left, image_w, image_h)
    right_fit = fit_to_box(right, image_w, image_h)

    left_x = side_margin
    right_x = left_x + spacing
    image_y = top_margin
    paste_with_border(card, left_fit, left_x, image_y, image_w, image_h)
    paste_with_border(card, right_fit, right_x, image_y, image_w, image_h)

    if settings.caption:
        draw.text(
            (card_w // 2, card_h - bottom_area + mm_to_px(2)),
            settings.caption,
            fill=(67, 53, 40),
            anchor="ma",
        )

    return card


def fit_to_box(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    fitted = image.copy()
    fitted.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    return fitted


def paste_with_border(
    card: Image.Image, image: Image.Image, x: int, y: int, box_w: int, box_h: int
):
    draw = ImageDraw.Draw(card)
    draw.rectangle((x - 8, y - 8, x + box_w + 8, y + box_h + 8), fill=(232, 221, 200))
    image_x = x + (box_w - image.width) // 2
    image_y = y + (box_h - image.height) // 2
    card.paste(image, (image_x, image_y))
    draw.rectangle(
        (x - 8, y - 8, x + box_w + 8, y + box_h + 8), outline=(112, 94, 68), width=3
    )


def score_comfort(image: Image.Image, settings: RenderSettings) -> str:
    width, height = image.size
    if width < height:
        return "Borderline - portrait source"
    if abs(settings.convergence) > 28:
        return "Borderline - strong convergence"
    if width / max(height, 1) < 1.7:
        return "Good - check stereo split"
    return "Excellent"
