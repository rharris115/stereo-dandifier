import math

from PIL import Image, ImageDraw

from stereo_dandifier.formats import CARD_FORMATS, mm_pair_to_px, mm_to_px
from stereo_dandifier.models import ProjectImage, RenderSettings, WindowShape


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


def stereo_window_x_positions(
    card_w: int, image_w: int, spacing: int
) -> tuple[int, int]:
    pair_w = spacing + image_w
    left_x = (card_w - pair_w) // 2
    return left_x, left_x + spacing


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


def paste_window(
    card: Image.Image,
    image: Image.Image,
    x: int,
    y: int,
    shape: WindowShape = WindowShape.RECTANGLE,
    round_corners: bool = False,
):
    mask = window_mask(image.width, image.height, shape, round_corners=round_corners)
    card.paste(image, (x, y), mask)


def effective_window_shape(settings: RenderSettings) -> WindowShape:
    shape = settings.window_shape

    spec = CARD_FORMATS[settings.layout_template]
    image_w, image_h = spec.image_mm
    rectangular = abs(image_w - image_h) > 0.01
    if shape == WindowShape.CIRCLE and rectangular:
        return WindowShape.OVAL
    if shape == WindowShape.OVAL and not rectangular:
        return WindowShape.CIRCLE
    return shape


def window_mask(
    width: int, height: int, shape: WindowShape, round_corners: bool = False
) -> Image.Image:
    if shape == WindowShape.ARCHED_TOP:
        return arched_top_mask(width, height, round_corners=round_corners)

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    if shape == WindowShape.OVAL:
        draw.ellipse((0, 0, width - 1, height - 1), fill=255)
    elif shape == WindowShape.CIRCLE:
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
