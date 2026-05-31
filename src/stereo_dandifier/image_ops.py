from dataclasses import dataclass, replace

from PIL import Image, ImageDraw, ImageEnhance
from PIL.ImageQt import fromqimage
from PySide6.QtCore import QRectF, QSizeF
from PySide6.QtGui import QColor, QImage, QPainter, QTextDocument

from stereo_dandifier.formats import EXPORT_DPI, CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.models import ProjectImage, RenderSettings
from stereo_dandifier.print_layout import PageLayout

PDF_IMAGE_SAVE_OPTIONS = {
    "quality": 100,
    "subsampling": 0,
}
RECTIFICATION_WARNING_OFFSET_PX = 2.0
RECTIFICATION_BORDERLINE_OFFSET_PX = 0.8
RECTIFICATION_MIN_CONFIDENCE = 0.35


@dataclass(frozen=True)
class StereoAlignmentReport:
    vertical_offset_px: float | None
    confidence: float
    method: str


def split_stereo_pair(
    image: Image.Image, settings: RenderSettings
) -> tuple[Image.Image, Image.Image]:
    width, height = image.size
    midpoint = width // 2
    left = image.crop((0, 0, midpoint, height))
    right = image.crop((midpoint, 0, width, height))

    if settings.right_eye_transform:
        right = apply_rectification_transform(right, settings.right_eye_transform)

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


def apply_rectification_transform(
    image: Image.Image, transform: tuple[float, ...]
) -> Image.Image:
    if len(transform) == 6:
        return image.transform(
            image.size,
            Image.Transform.AFFINE,
            transform,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(245, 241, 232),
        )
    if len(transform) == 8:
        return image.transform(
            image.size,
            Image.Transform.PERSPECTIVE,
            transform,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(245, 241, 232),
        )
    return image


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


def card_window_geometry(
    settings: RenderSettings, dpi: int
) -> tuple[int, int, int, int, int, int]:
    spec = CARD_FORMATS[settings.layout_template]
    card_w, _card_h = mm_pair_to_px(spec.card_mm, dpi=dpi)
    image_w, image_h = mm_pair_to_px(spec.image_mm, dpi=dpi)
    top_margin = mm_to_px(spec.top_margin_mm, dpi=dpi)
    spacing = mm_to_px(spec.center_spacing_mm, dpi=dpi)
    left_x, right_x = stereo_window_x_positions(card_w, image_w, spacing)
    return left_x, right_x, top_margin, image_w, image_h, spacing


def caption_positions(
    caption_position: str, left_x: int, right_x: int, image_w: int
) -> list[int]:
    if caption_position == "Left image":
        return [left_x]
    if caption_position == "Right image":
        return [right_x]
    return [left_x, right_x]


def stereo_window_x_positions(
    card_w: int, image_w: int, spacing: int
) -> tuple[int, int]:
    pair_w = spacing + image_w
    left_x = (card_w - pair_w) // 2
    return left_x, left_x + spacing


def caption_windows(
    caption_position: str,
    left_x: int,
    right_x: int,
    left_fit: Image.Image,
    right_fit: Image.Image,
    image_y: int,
    image_h: int,
) -> list[tuple[int, int]]:
    left = (left_x, visible_image_bottom(image_y, image_h, left_fit.height))
    right = (right_x, visible_image_bottom(image_y, image_h, right_fit.height))
    if caption_position == "Left image":
        return [left]
    if caption_position == "Right image":
        return [right]
    return [left, right]


def visible_image_bottom(image_y: int, image_h: int, fitted_h: int) -> int:
    return image_y + ((image_h + fitted_h) // 2)


def crop_to_window(
    image: Image.Image, box_w: int, box_h: int, settings: RenderSettings
) -> Image.Image:
    source = image.convert("RGB")
    crop_box = source_crop_box(source.size, (box_w, box_h), settings)
    crop = source.crop(crop_box)
    return crop.resize((box_w, box_h), Image.Resampling.LANCZOS)


def source_crop_box(
    source_size: tuple[int, int],
    window_size: tuple[int, int],
    settings: RenderSettings,
) -> tuple[int, int, int, int]:
    source_w, source_h = source_size
    window_w, window_h = window_size
    area_percent = max(1, min(100, settings.image_area_percent))
    crop_h = max(1, round(source_h * area_percent / 100))
    crop_w = max(1, round(crop_h * window_w / window_h))
    if crop_w > source_w:
        crop_w = source_w
        crop_h = max(1, round(crop_w * window_h / window_w))

    left = crop_axis_origin(source_w - crop_w, settings.crop_x_percent)
    top = crop_axis_origin(source_h - crop_h, settings.crop_y_percent)
    return left, top, left + crop_w, top + crop_h


def crop_axis_origin(max_offset: int, percent: int) -> int:
    if max_offset <= 0:
        return 0
    normalised = max(-100, min(100, percent))
    return round((normalised + 100) / 200 * max_offset)


def caption_html_text(caption_html: str) -> str:
    if not caption_html:
        return ""
    document = QTextDocument()
    document.setHtml(caption_html)
    return document.toPlainText().strip()


def render_caption_html(
    caption_html: str, width: int, height: int, dpi: int
) -> Image.Image:
    scale = dpi / 72

    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.setDotsPerMeterX(round(dpi / 0.0254))
    image.setDotsPerMeterY(round(dpi / 0.0254))
    image.fill(QColor(0, 0, 0, 0))

    document = QTextDocument()
    document.setDocumentMargin(0)
    document.setHtml(caption_html)
    logical_width, logical_height, scale = fit_qtext_document_to_box(
        document, width, height, scale
    )
    document.setPageSize(QSizeF(logical_width, logical_height))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.scale(scale, scale)
    document.drawContents(painter, QRectF(0, 0, logical_width, logical_height))
    painter.end()

    return fromqimage(image).convert("RGBA")


def fit_qtext_document_to_box(
    document: QTextDocument, width: int, height: int, scale: float
) -> tuple[float, float, float]:
    logical_width = max(1, width / scale)
    logical_height = max(1, height / scale)
    document.setTextWidth(logical_width)

    content_height = max(1, document.size().height())
    if content_height * scale <= height:
        return logical_width, max(logical_height, content_height), scale

    scale = max(0.1, height / content_height)
    logical_width = max(1, width / scale)
    logical_height = max(1, height / scale)
    document.setTextWidth(logical_width)
    return logical_width, logical_height, scale


def trim_transparent(image: Image.Image) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def trim_vertical_transparent(image: Image.Image) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return image
    return image.crop((0, bbox[1], image.width, bbox[3]))


def centered_caption_y(
    window_bottom: int, card_bottom: int, caption_height: int
) -> int:
    band_height = max(0, card_bottom - window_bottom)
    return window_bottom + (band_height - caption_height) // 2


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
        **PDF_IMAGE_SAVE_OPTIONS,
    )


def render_project_card(project_image: ProjectImage, dpi: int) -> Image.Image:
    left, right = split_stereo_pair(project_image.source, project_image.settings)
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


def window_bounds_for_project(
    project_image: ProjectImage, dpi: int
) -> list[tuple[int, int, int, int]]:
    settings = project_image.settings
    left_x, right_x, top_margin, image_w, image_h, _spacing = card_window_geometry(
        settings, dpi
    )
    return [
        (left_x, top_margin, image_w, image_h),
        (right_x, top_margin, image_w, image_h),
    ]


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
    shape: str = "Rectangle",
    round_corners: bool = False,
    show_boundary: bool = False,
):
    mask = window_mask(image.width, image.height, shape, round_corners=round_corners)
    card.paste(image, (x, y), mask)

    if show_boundary:
        draw = ImageDraw.Draw(card)
        draw_window_boundary(
            draw, x, y, image.width, image.height, shape, round_corners=round_corners
        )


def effective_window_shape(settings: RenderSettings) -> str:
    shape = settings.window_shape
    if shape not in {"Rectangle", "Circle", "Oval", "Arched top"}:
        return "Rectangle"

    spec = CARD_FORMATS[settings.layout_template]
    image_w, image_h = spec.image_mm
    rectangular = abs(image_w - image_h) > 0.01
    if shape == "Circle" and rectangular:
        return "Oval"
    if shape == "Oval" and not rectangular:
        return "Circle"
    return shape


def window_mask(
    width: int, height: int, shape: str, round_corners: bool = False
) -> Image.Image:
    if shape == "Arched top":
        return arched_top_mask(width, height, round_corners=round_corners)

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    if shape == "Oval":
        draw.ellipse((0, 0, width - 1, height - 1), fill=255)
    elif shape == "Circle":
        diameter = min(width, height)
        left = (width - diameter) // 2
        top = (height - diameter) // 2
        draw.ellipse((left, top, left + diameter - 1, top + diameter - 1), fill=255)
    elif round_corners:
        radius = rounded_corner_radius(width, height)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    else:
        draw.rectangle((0, 0, width - 1, height - 1), fill=255)
    return mask


def arched_top_mask(
    width: int, height: int, round_corners: bool = False
) -> Image.Image:
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw_arched_top(
        draw, width * scale, height * scale, fill=255, round_corners=round_corners
    )
    return mask.resize((width, height), Image.Resampling.LANCZOS)


def draw_arched_top(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    fill,
    round_corners: bool = False,
):
    draw.polygon(
        arched_top_points(width, height, round_corners=round_corners), fill=fill
    )


def arched_top_points(
    width: int, height: int, round_corners: bool = False
) -> list[tuple[int, int]]:
    arch_height = arched_top_depth(width, height)
    center = (width - 1) / 2
    radius = rounded_corner_radius(width, height) if round_corners else 0
    bottom_y = height - 1
    left_bottom_x = radius
    right_bottom_x = width - 1 - radius
    points = [(left_bottom_x, bottom_y)]

    if radius:
        points.extend(
            quarter_arc_points(
                center_x=radius,
                center_y=height - 1 - radius,
                radius=radius,
                start_degrees=90,
                end_degrees=180,
            )
        )

    points.append((0, arch_height))
    steps = max(12, width // 8)

    for index in range(steps + 1):
        t = index / steps
        x = quadratic_bezier(0, 0, center, t)
        y = quadratic_bezier(arch_height, 0, 0, t)
        points.append((round(x), round(y)))

    for index in range(1, steps + 1):
        t = index / steps
        x = quadratic_bezier(center, width - 1, width - 1, t)
        y = quadratic_bezier(0, 0, arch_height, t)
        points.append((round(x), round(y)))

    points.append((width - 1, arch_height))
    if radius:
        points.extend(
            quarter_arc_points(
                center_x=width - 1 - radius,
                center_y=height - 1 - radius,
                radius=radius,
                start_degrees=0,
                end_degrees=90,
            )
        )
    points.append((right_bottom_x, bottom_y))
    return points


def quarter_arc_points(
    center_x: int,
    center_y: int,
    radius: int,
    start_degrees: int,
    end_degrees: int,
) -> list[tuple[int, int]]:
    import math

    steps = max(4, radius // 3)
    return [
        (
            round(center_x + radius * math.cos(math.radians(degrees))),
            round(center_y + radius * math.sin(math.radians(degrees))),
        )
        for degrees in [
            start_degrees + ((end_degrees - start_degrees) * index / steps)
            for index in range(steps + 1)
        ]
    ]


def quadratic_bezier(start: float, control: float, end: float, t: float) -> float:
    return ((1 - t) * (1 - t) * start) + (2 * (1 - t) * t * control) + (t * t * end)


def arched_top_depth(width: int, height: int) -> int:
    return max(1, round(min(height * 0.24, width * 0.32)))


def rounded_corner_radius(width: int, height: int) -> int:
    return max(1, round(min(width, height) * 0.08))


def draw_window_boundary(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    shape: str,
    round_corners: bool = False,
):
    outline = (220, 220, 220)
    if shape == "Oval":
        draw.ellipse((x, y, x + width, y + height), outline=outline, width=1)
    elif shape == "Circle":
        diameter = min(width, height)
        left = x + (width - diameter) // 2
        top = y + (height - diameter) // 2
        draw.ellipse((left, top, left + diameter, top + diameter), outline=outline)
    elif shape == "Arched top":
        arch_height = arched_top_depth(width, height)
        draw.line((x, y + arch_height, x, y + height), fill=outline)
        draw.line((x + width, y + arch_height, x + width, y + height), fill=outline)
        draw.line((x, y + height, x + width, y + height), fill=outline)
        points = [
            (x + offset_x, y + offset_y)
            for offset_x, offset_y in arched_top_points(width, height)[2:-2]
        ]
        draw.line(points, fill=outline, width=1)
        if round_corners:
            radius = rounded_corner_radius(width, height)
            draw.arc(
                (x, y + height - 1 - 2 * radius, x + 2 * radius, y + height - 1),
                90,
                180,
                fill=outline,
                width=1,
            )
            draw.arc(
                (
                    x + width - 1 - 2 * radius,
                    y + height - 1 - 2 * radius,
                    x + width - 1,
                    y + height - 1,
                ),
                0,
                90,
                fill=outline,
                width=1,
            )
    elif round_corners:
        radius = rounded_corner_radius(width, height)
        draw.rounded_rectangle(
            (x, y, x + width, y + height), radius=radius, outline=outline, width=1
        )
    else:
        draw.rectangle((x, y, x + width, y + height), outline=outline, width=1)


def score_comfort(image: Image.Image, settings: RenderSettings) -> str:
    alignment = stereo_alignment_report(image, settings)
    if (
        alignment.vertical_offset_px is not None
        and alignment.confidence >= RECTIFICATION_MIN_CONFIDENCE
    ):
        offset = abs(alignment.vertical_offset_px)
        warning_offset = rectification_warning_offset_px(image.height)
        borderline_offset = rectification_borderline_offset_px(image.height)
        if offset >= warning_offset:
            return f"Poor - vertical alignment off by {offset:.1f}px"
        if offset >= borderline_offset:
            return f"Borderline - vertical alignment off by {offset:.1f}px"

    width, height = image.size
    if width < height:
        return "Borderline - portrait source"
    if abs(settings.convergence) > 28:
        return "Borderline - strong convergence"
    if width / max(height, 1) < 1.7:
        return "Good - check stereo split"
    return "Excellent"


def rectification_warning_offset_px(eye_height: int) -> float:
    return max(RECTIFICATION_WARNING_OFFSET_PX, eye_height * 0.003)


def rectification_borderline_offset_px(eye_height: int) -> float:
    return max(RECTIFICATION_BORDERLINE_OFFSET_PX, eye_height * 0.001)


def stereo_alignment_report(
    image: Image.Image, settings: RenderSettings
) -> StereoAlignmentReport:
    left, right = split_stereo_pair(image, settings)
    report = opencv_stereo_alignment_report(left, right)
    if report is not None:
        return report
    return correlation_stereo_alignment_report(left, right)


def suggested_right_eye_transform(
    image: Image.Image, settings: RenderSettings
) -> tuple[float, ...] | None:
    source_settings = replace(settings, swap_eyes=False, right_eye_transform=None)
    left, right = split_stereo_pair(image, source_settings)
    transform = opencv_right_eye_rectification_transform(left, right)
    if transform is not None:
        return transform

    report = stereo_alignment_report(image, source_settings)
    if (
        report.vertical_offset_px is None
        or report.confidence < RECTIFICATION_MIN_CONFIDENCE
    ):
        return None
    return vertical_translation_transform(-round(report.vertical_offset_px))


def vertical_translation_transform(pixels: int) -> tuple[float, ...]:
    return (1.0, 0.0, 0.0, 0.0, 1.0, float(-pixels))


def opencv_right_eye_rectification_transform(
    left: Image.Image, right: Image.Image
) -> tuple[float, ...] | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    left_gray, scale = cv2_grayscale(left, cv2, np)
    right_gray, _right_scale = cv2_grayscale(right, cv2, np)
    left_points, right_points = matched_feature_points(left_gray, right_gray, cv2, np)
    if left_points is None or right_points is None or len(left_points) < 8:
        return None

    affine, inliers = cv2.estimateAffinePartial2D(
        right_points,
        left_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=2.5,
        maxIters=3000,
        confidence=0.995,
    )
    if affine is not None and ransac_inlier_count(inliers) >= 8:
        return cv2_affine_to_pillow_inverse(affine, scale, np)

    homography, inliers = cv2.findHomography(
        right_points,
        left_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=3.0,
        maxIters=3000,
        confidence=0.995,
    )
    if homography is not None and ransac_inlier_count(inliers) >= 10:
        return cv2_homography_to_pillow_inverse(homography, scale, np)

    return None


def matched_feature_points(left_gray, right_gray, cv2, np):
    if hasattr(cv2, "SIFT_create"):
        detector = cv2.SIFT_create(nfeatures=1600)
        norm = cv2.NORM_L2
    else:
        detector = cv2.ORB_create(nfeatures=1600)
        norm = cv2.NORM_HAMMING

    left_keypoints, left_descriptors = detector.detectAndCompute(left_gray, None)
    right_keypoints, right_descriptors = detector.detectAndCompute(right_gray, None)
    if left_descriptors is None or right_descriptors is None:
        return None, None
    if len(left_keypoints) < 12 or len(right_keypoints) < 12:
        return None, None

    matcher = cv2.BFMatcher(norm)
    matches = matcher.knnMatch(right_descriptors, left_descriptors, k=2)
    left_points = []
    right_points = []
    for pair in matches:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance >= second.distance * 0.75:
            continue
        right_point = right_keypoints[best.queryIdx].pt
        left_point = left_keypoints[best.trainIdx].pt
        right_points.append(right_point)
        left_points.append(left_point)

    if len(left_points) < 8:
        return None, None
    return (
        np.asarray(left_points, dtype=np.float32),
        np.asarray(right_points, dtype=np.float32),
    )


def ransac_inlier_count(inliers) -> int:
    if inliers is None:
        return 0
    return int(inliers.sum())


def cv2_affine_to_pillow_inverse(affine, scale: float, np) -> tuple[float, ...] | None:
    source_to_dest = np.vstack([affine, [0.0, 0.0, 1.0]])
    source_to_dest = unscale_transform(source_to_dest, scale, np)
    try:
        dest_to_source = np.linalg.inv(source_to_dest)
    except np.linalg.LinAlgError:
        return None
    return tuple(float(value) for value in dest_to_source[:2, :].reshape(6))


def cv2_homography_to_pillow_inverse(
    homography, scale: float, np
) -> tuple[float, ...] | None:
    source_to_dest = unscale_transform(homography, scale, np)
    try:
        dest_to_source = np.linalg.inv(source_to_dest)
    except np.linalg.LinAlgError:
        return None
    dest_to_source = dest_to_source / dest_to_source[2, 2]
    return tuple(float(value) for value in dest_to_source.reshape(9)[:8])


def unscale_transform(transform, scale: float, np):
    if scale == 1.0:
        return transform
    scaled_to_source = np.diag([scale, scale, 1.0])
    source_to_scaled = np.diag([1 / scale, 1 / scale, 1.0])
    return source_to_scaled @ transform @ scaled_to_source


def opencv_stereo_alignment_report(
    left: Image.Image, right: Image.Image
) -> StereoAlignmentReport | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    left_gray, scale = cv2_grayscale(left, cv2, np)
    right_gray, _right_scale = cv2_grayscale(right, cv2, np)
    orb = cv2.ORB_create(nfeatures=1200)
    left_keypoints, left_descriptors = orb.detectAndCompute(left_gray, None)
    right_keypoints, right_descriptors = orb.detectAndCompute(right_gray, None)
    if left_descriptors is None or right_descriptors is None:
        return None
    if len(left_keypoints) < 12 or len(right_keypoints) < 12:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(left_descriptors, right_descriptors, k=2)
    vertical_offsets = []
    for pair in matches:
        if len(pair) != 2:
            continue
        best, second = pair
        if best.distance >= second.distance * 0.75:
            continue
        left_point = left_keypoints[best.queryIdx].pt
        right_point = right_keypoints[best.trainIdx].pt
        vertical_offsets.append(right_point[1] - left_point[1])

    if len(vertical_offsets) < 8:
        return None

    offsets = np.asarray(vertical_offsets, dtype=np.float32)
    median = float(np.median(offsets))
    deviations = np.abs(offsets - median)
    inliers = offsets[deviations <= 2.5]
    if len(inliers) < 6:
        return None

    refined = float(np.median(inliers)) / scale
    confidence = min(1.0, len(inliers) / 30) * max(
        0.0, 1.0 - float(np.std(inliers)) / 3
    )
    return StereoAlignmentReport(refined, confidence, "opencv-orb")


def cv2_grayscale(image: Image.Image, cv2, np, max_width: int = 800):
    source = image.convert("RGB")
    scale = 1.0
    if source.width > max_width:
        scale = max_width / source.width
        height = max(1, round(source.height * scale))
        source = source.resize((max_width, height), Image.Resampling.BILINEAR)
    array = np.asarray(source)
    return cv2.cvtColor(array, cv2.COLOR_RGB2GRAY), scale


def correlation_stereo_alignment_report(
    left: Image.Image, right: Image.Image
) -> StereoAlignmentReport:
    try:
        import numpy as np
    except ImportError:
        return StereoAlignmentReport(None, 0.0, "unavailable")

    left_array, scale = downsampled_luminance(left, np)
    right_array, _right_scale = downsampled_luminance(right, np)
    if left_array.shape != right_array.shape:
        return StereoAlignmentReport(None, 0.0, "correlation")

    gradient_left = vertical_gradient(left_array, np)
    gradient_right = vertical_gradient(right_array, np)
    if float(np.std(gradient_left)) < 0.01 or float(np.std(gradient_right)) < 0.01:
        return StereoAlignmentReport(None, 0.0, "correlation")

    max_vertical_shift = max(1, min(10, round(left_array.shape[0] * 0.04)))
    max_horizontal_shift = max(2, min(24, round(left_array.shape[1] * 0.08)))
    scores: list[tuple[float, int, int]] = []
    for vertical_shift in range(-max_vertical_shift, max_vertical_shift + 1):
        best_for_vertical = -1.0
        best_horizontal_shift = 0
        for horizontal_shift in range(-max_horizontal_shift, max_horizontal_shift + 1):
            score = shifted_normalised_correlation(
                gradient_left,
                gradient_right,
                horizontal_shift,
                vertical_shift,
                np,
            )
            if score > best_for_vertical:
                best_for_vertical = score
                best_horizontal_shift = horizontal_shift
        scores.append((best_for_vertical, vertical_shift, best_horizontal_shift))

    best_score, best_vertical_shift, _best_horizontal_shift = max(
        scores, key=lambda item: item[0]
    )
    competing_scores = [
        score
        for score, vertical_shift, _horizontal_shift in scores
        if vertical_shift != best_vertical_shift
    ]
    next_best = max(competing_scores) if competing_scores else -1.0
    confidence = max(0.0, min(1.0, (best_score - next_best) * 8))
    return StereoAlignmentReport(best_vertical_shift / scale, confidence, "correlation")


def downsampled_luminance(image: Image.Image, np, max_width: int = 360):
    gray = image.convert("L")
    scale = 1.0
    if gray.width > max_width:
        scale = max_width / gray.width
        height = max(1, round(gray.height * scale))
        gray = gray.resize((max_width, height), Image.Resampling.BILINEAR)
    array = np.asarray(gray, dtype=np.float32) / 255.0
    return array, scale


def vertical_gradient(array, np):
    gradient = np.zeros_like(array)
    gradient[1:-1, :] = array[2:, :] - array[:-2, :]
    return gradient


def shifted_normalised_correlation(left, right, dx: int, dy: int, np) -> float:
    left_crop, right_crop = overlapping_shifted_regions(left, right, dx, dy)
    if left_crop.size < 100 or right_crop.size < 100:
        return -1.0

    left_values = left_crop.ravel()
    right_values = right_crop.ravel()
    left_values = left_values - float(np.mean(left_values))
    right_values = right_values - float(np.mean(right_values))
    denominator = float(np.linalg.norm(left_values) * np.linalg.norm(right_values))
    if denominator <= 0:
        return -1.0
    return float(np.dot(left_values, right_values) / denominator)


def overlapping_shifted_regions(left, right, dx: int, dy: int):
    height, width = left.shape
    left_x0 = max(0, -dx)
    right_x0 = max(0, dx)
    overlap_w = width - abs(dx)
    left_y0 = max(0, -dy)
    right_y0 = max(0, dy)
    overlap_h = height - abs(dy)
    return (
        left[left_y0 : left_y0 + overlap_h, left_x0 : left_x0 + overlap_w],
        right[right_y0 : right_y0 + overlap_h, right_x0 : right_x0 + overlap_w],
    )
