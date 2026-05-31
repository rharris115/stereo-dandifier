from PIL import Image, ImageDraw

from stereo_dandifier.formats import EXPORT_DPI, mm_pair_to_px
from stereo_dandifier.print_layout import PageLayout

PDF_IMAGE_SAVE_OPTIONS = {
    "quality": 100,
    "subsampling": 0,
}


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
        **PDF_IMAGE_SAVE_OPTIONS,
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
