from PIL import Image
from PIL.ImageQt import fromqimage
from PySide6.QtCore import QRectF, QSizeF
from PySide6.QtGui import QColor, QImage, QPainter, QTextDocument

from stereo_dandifier.models import CaptionPosition


def caption_windows(
    caption_position: CaptionPosition,
    left_x: int,
    right_x: int,
    left_fit: Image.Image,
    right_fit: Image.Image,
    image_y: int,
    image_h: int,
) -> list[tuple[int, int]]:
    left = (left_x, visible_image_bottom(image_y, image_h, left_fit.height))
    right = (right_x, visible_image_bottom(image_y, image_h, right_fit.height))
    if caption_position == CaptionPosition.LEFT_IMAGE:
        return [left]
    if caption_position == CaptionPosition.RIGHT_IMAGE:
        return [right]
    return [left, right]


def visible_image_bottom(image_y: int, image_h: int, fitted_h: int) -> int:
    return image_y + ((image_h + fitted_h) // 2)


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
