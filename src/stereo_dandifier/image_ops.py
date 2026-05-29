from PIL import Image, ImageDraw, ImageEnhance

from stereo_dandifier.formats import EXPORT_DPI, CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.models import ProjectImage, RenderSettings
from stereo_dandifier.print_layout import PageLayout


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
    left: Image.Image,
    right: Image.Image,
    settings: RenderSettings,
    dpi: int = EXPORT_DPI,
) -> Image.Image:
    spec = CARD_FORMATS[settings.layout_template]
    card_w, card_h = mm_pair_to_px(spec["card_mm"], dpi=dpi)
    image_w, image_h = mm_pair_to_px(spec["image_mm"], dpi=dpi)
    side_margin = mm_to_px(spec["side_margin_mm"], dpi=dpi)
    top_margin = mm_to_px(spec["top_margin_mm"], dpi=dpi)
    bottom_area = mm_to_px(spec["bottom_mm"], dpi=dpi)
    if spec["gap_mm"] is None:
        spacing = mm_to_px(spec["center_spacing_mm"], dpi=dpi)
    else:
        spacing = image_w + mm_to_px(spec["gap_mm"], dpi=dpi)

    card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    left_fit = fit_to_box(left, image_w, image_h)
    right_fit = fit_to_box(right, image_w, image_h)

    left_x = side_margin
    right_x = left_x + spacing
    image_y = top_margin
    paste_window(card, left_fit, left_x, image_y, image_w, image_h)
    paste_window(card, right_fit, right_x, image_y, image_w, image_h)

    if settings.caption:
        draw.text(
            (card_w // 2, card_h - bottom_area + mm_to_px(2, dpi=dpi)),
            settings.caption,
            fill=(67, 53, 40),
            anchor="ma",
        )

    return card


def native_card_image_dpi(source: Image.Image, settings: RenderSettings) -> int:
    spec = CARD_FORMATS[settings.layout_template]
    image_w_mm, image_h_mm = spec["image_mm"]
    left, _right = split_stereo_pair(source, settings)

    width_dpi = left.width / (image_w_mm / 25.4)
    height_dpi = left.height / (image_h_mm / 25.4)
    return max(1, round(min(width_dpi, height_dpi)))


def export_dpi_for_source(
    source: Image.Image, settings: RenderSettings, minimum_dpi: int
) -> int:
    return max(minimum_dpi, native_card_image_dpi(source, settings))


def render_print_preview(
    card: Image.Image, page_layout: PageLayout, dpi: int = EXPORT_DPI
) -> Image.Image:
    return render_print_page([card], page_layout, dpi=dpi)


def render_print_pages(
    cards: list[Image.Image], page_layout: PageLayout, dpi: int = EXPORT_DPI
) -> list[Image.Image]:
    if not cards:
        return [blank_print_page(page_layout, dpi=dpi)]

    per_page = cards_per_page(cards[0].size, page_layout, dpi=dpi)
    return [
        render_print_page(cards[index : index + per_page], page_layout, dpi=dpi)
        for index in range(0, len(cards), per_page)
    ]


def render_print_page(
    cards: list[Image.Image], page_layout: PageLayout, dpi: int = EXPORT_DPI
) -> Image.Image:
    page_w, page_h = mm_pair_to_px(page_layout.size_mm, dpi=dpi)
    page = Image.new("RGB", (page_w, page_h), (255, 255, 255))
    if not cards:
        return page

    card_w, card_h = cards[0].size
    columns, rows = card_grid(card_w, card_h, page_layout, dpi=dpi)
    count = min(len(cards), columns * rows)
    grid_w = columns * card_w
    grid_h = rows * card_h
    start_x = (page_w - grid_w) // 2
    start_y = (page_h - grid_h) // 2

    for index, card in enumerate(cards[:count]):
        column = index % columns
        row = index // columns
        x = start_x + column * card_w
        y = start_y + row * card_h
        page.paste(card, (x, y))
        draw_guillotine_guides(page, (x, y, x + card.width, y + card.height))

    return page


def blank_print_page(page_layout: PageLayout, dpi: int = EXPORT_DPI) -> Image.Image:
    page_w, page_h = mm_pair_to_px(page_layout.size_mm, dpi=dpi)
    return Image.new("RGB", (page_w, page_h), (255, 255, 255))


def cards_per_page(
    card_size: tuple[int, int], page_layout: PageLayout, dpi: int = EXPORT_DPI
) -> int:
    columns, rows = card_grid(card_size[0], card_size[1], page_layout, dpi=dpi)
    return columns * rows


def card_grid(
    card_w: int, card_h: int, page_layout: PageLayout, dpi: int = EXPORT_DPI
) -> tuple[int, int]:
    page_w, page_h = mm_pair_to_px(page_layout.size_mm, dpi=dpi)
    columns = max(1, page_w // card_w)
    rows = max(1, page_h // card_h)
    return columns, rows


def save_pdf(page: Image.Image, file_path: str, dpi: int):
    save_pdf_pages([page], file_path, dpi=dpi)


def save_pdf_pages(pages: list[Image.Image], file_path: str, dpi: int):
    if not pages:
        raise ValueError("Cannot save a PDF without at least one page")

    first, *rest = [page.convert("RGB") for page in pages]
    first.save(
        file_path,
        "PDF",
        resolution=dpi,
        save_all=bool(rest),
        append_images=rest,
    )


def render_project_card(project_image: ProjectImage, dpi: int) -> Image.Image:
    left, right = split_stereo_pair(project_image.source, project_image.settings)
    return render_card(
        apply_style(left, project_image.settings),
        apply_style(right, project_image.settings),
        project_image.settings,
        dpi=dpi,
    )


def draw_guillotine_guides(page: Image.Image, bounds: tuple[int, int, int, int]):
    draw = ImageDraw.Draw(page)
    left, top, right, bottom = bounds
    guide_colour = (170, 210, 246)
    width = 2

    draw.line((left, 0, left, page.height - 1), fill=guide_colour, width=width)
    draw.line((right, 0, right, page.height - 1), fill=guide_colour, width=width)
    draw.line((0, top, page.width - 1, top), fill=guide_colour, width=width)
    draw.line((0, bottom, page.width - 1, bottom), fill=guide_colour, width=width)


def fit_to_box(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    fitted = image.copy()
    fitted.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    return fitted


def paste_window(
    card: Image.Image,
    image: Image.Image,
    x: int,
    y: int,
    box_w: int,
    box_h: int,
    show_boundary: bool = False,
):
    image_x = x + (box_w - image.width) // 2
    image_y = y + (box_h - image.height) // 2
    card.paste(image, (image_x, image_y))

    if show_boundary:
        draw = ImageDraw.Draw(card)
        draw.rectangle((x, y, x + box_w, y + box_h), outline=(220, 220, 220), width=1)


def score_comfort(image: Image.Image, settings: RenderSettings) -> str:
    width, height = image.size
    if width < height:
        return "Borderline - portrait source"
    if abs(settings.convergence) > 28:
        return "Borderline - strong convergence"
    if width / max(height, 1) < 1.7:
        return "Good - check stereo split"
    return "Excellent"
