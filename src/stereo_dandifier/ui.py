from dataclasses import replace
from importlib import resources
from pathlib import Path
from typing import Callable

from PIL import Image
from PIL.ImageQt import ImageQt

from PySide6.QtCore import QCoreApplication, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QButtonGroup,
    QProgressDialog,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFontComboBox,
)

from stereo_dandifier.card_json import save_card_json
from stereo_dandifier.card_rendering import (
    caption_bounds_for_project,
    render_project_card,
)
from stereo_dandifier.formats import CARD_FORMATS, format_particulars
from stereo_dandifier.image_metadata import export_dpi_for_source
from stereo_dandifier.photo_ops import apply_style, auto_improve_stereo_pair
from stereo_dandifier.print_rendering import (
    render_print_pages,
    save_pdf_pages,
)
from stereo_dandifier.stereo_ops import (
    score_comfort,
    split_stereo_pair,
    suggested_right_eye_transform,
)
from stereo_dandifier.window_geometry import (
    effective_window_shape,
    source_crop_box,
    window_bounds_for_project,
)
from stereo_dandifier.importer import load_project_images
from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    DEFAULT_CAPTION_FONT_FAMILY,
    DEFAULT_CAPTION_FONT_SIZE,
    ProjectImage,
    RenderSettings,
    ToneMode,
    WindowShape,
)
from stereo_dandifier.print_layout import (
    FALLBACK_PREVIEW_DPI,
    PageLayout,
    default_page_layout,
    page_layout_for_name,
)

SUPPORTED_IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.dng *.mpo *.tif *.tiff)"
MIN_CARD_EDITOR_DPI = FALLBACK_PREVIEW_DPI
_WALLPAPER_PIXMAP: QPixmap | None = None
_WALLPAPER_LOAD_ATTEMPTED = False


def wallpaper_pixmap() -> QPixmap | None:
    global _WALLPAPER_LOAD_ATTEMPTED, _WALLPAPER_PIXMAP

    if _WALLPAPER_LOAD_ATTEMPTED:
        return _WALLPAPER_PIXMAP

    _WALLPAPER_LOAD_ATTEMPTED = True
    try:
        wallpaper_path = resources.files("stereo_dandifier.resources").joinpath(
            "wallpaper.png"
        )
        pixmap = QPixmap(str(wallpaper_path))
        if not pixmap.isNull():
            _WALLPAPER_PIXMAP = pixmap
    except FileNotFoundError, ModuleNotFoundError:
        pass
    return _WALLPAPER_PIXMAP


def draw_wallpaper_background(view: QGraphicsView, painter: QPainter):
    painter.save()
    painter.resetTransform()
    pixmap = wallpaper_pixmap()
    viewport_rect = view.viewport().rect()
    if pixmap is None:
        painter.fillRect(viewport_rect, QColor(235, 230, 220))
    else:
        pixmap = QPixmap(pixmap)
        pixmap.setDevicePixelRatio(view.devicePixelRatioF())
        painter.drawTiledPixmap(viewport_rect, pixmap, QPoint(0, 0))
    painter.restore()


class ZoomableImageView(QGraphicsView):
    def __init__(self, placeholder: str):
        super().__init__()

        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._placeholder = QGraphicsTextItem(placeholder)
        self._placeholder.setDefaultTextColor(Qt.GlobalColor.darkGray)
        self._hotspot_item = QGraphicsRectItem()
        self._hotspot_item.setBrush(QBrush(QColor(185, 220, 255, 75)))
        self._hotspot_item.setPen(QPen(QColor(120, 175, 230, 120)))
        self._hotspot_item.setVisible(False)
        self._zoom = 0
        self._has_image = False
        self._default_tooltip = (
            "Mouse wheel zooms. Drag pans. Double-click fits the image."
        )
        self._hotspots: list[tuple[QRectF, Callable[[], None], str]] = []

        self._scene.addItem(self._placeholder)
        self._scene.addItem(self._pixmap_item)
        self._scene.addItem(self._hotspot_item)
        self.setScene(self._scene)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.Shape.StyledPanel)
        self.setObjectName("preview")
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(360, 320)
        self.setToolTip(self._default_tooltip)
        self.setMouseTracking(True)

    def set_image(self, image: Image.Image, reset_view: bool = False):
        pixmap = QPixmap.fromImage(ImageQt(image))
        self._pixmap_item.setPixmap(pixmap)
        self._placeholder.setVisible(False)
        self._has_image = True
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._hotspot_item.setVisible(False)

        if reset_view or self._zoom == 0:
            self.fit_to_view()

    def set_placeholder(self, text: str):
        self._pixmap_item.setPixmap(QPixmap())
        self._placeholder.setPlainText(text)
        self._placeholder.setVisible(True)
        self._has_image = False
        self._hotspots = []
        self._hotspot_item.setVisible(False)
        self._zoom = 0
        self.resetTransform()

    def set_hotspot_actions(
        self,
        hotspots: list[tuple[tuple[int, int, int, int], Callable[[], None], str]],
    ):
        self._hotspots = [
            (QRectF(x, y, width, height), callback, tooltip)
            for (x, y, width, height), callback, tooltip in hotspots
        ]
        self._hotspot_item.setVisible(False)

    def fit_to_view(self):
        if not self._has_image or self._pixmap_item.pixmap().isNull():
            return

        self._zoom = 0
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        if not self._has_image:
            super().wheelEvent(event)
            return

        if event.angleDelta().y() > 0:
            factor = 1.18
            self._zoom += 1
        else:
            factor = 1 / 1.18
            self._zoom -= 1

        if self._zoom <= 0:
            self.fit_to_view()
        elif self._zoom <= 32:
            self.scale(factor, factor)
        else:
            self._zoom = 32

    def mouseDoubleClickEvent(self, event):
        self.fit_to_view()
        super().mouseDoubleClickEvent(event)

    def drawBackground(self, painter, rect):
        draw_wallpaper_background(self, painter)

    def mouseMoveEvent(self, event):
        hotspot = self._hotspot_at(event.position().toPoint())
        if hotspot is None:
            self._hotspot_item.setVisible(False)
            self.viewport().unsetCursor()
            self.setToolTip(self._default_tooltip)
        else:
            bounds, _callback, tooltip = hotspot
            self._hotspot_item.setRect(bounds)
            self._hotspot_item.setVisible(True)
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(tooltip)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hotspot_item.setVisible(False)
        self.viewport().unsetCursor()
        self.setToolTip(self._default_tooltip)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        hotspot = self._hotspot_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and hotspot is not None:
            _bounds, callback, _tooltip = hotspot
            callback()
            return
        super().mousePressEvent(event)

    def _hotspot_at(self, viewport_position):
        scene_position = self.mapToScene(viewport_position)
        for hotspot, callback, tooltip in self._hotspots:
            if hotspot.contains(scene_position):
                return hotspot, callback, tooltip
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom == 0:
            self.fit_to_view()


class SourceWindowView(QGraphicsView):
    def __init__(self, image: Image.Image, settings: RenderSettings):
        super().__init__()
        self._image = image.convert("RGB")
        self._settings = settings
        self._crop_changed_callback: Callable[[int, int, int], None] | None = None
        self._drag_offset = None
        self._resize_handle: str | None = None

        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(ImageQt(self._image)))
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._shade_item = QGraphicsPathItem()
        self._shade_item.setBrush(QBrush(QColor(80, 80, 80, 145)))
        self._shade_item.setPen(QPen(Qt.PenStyle.NoPen))

        self._window_item = QGraphicsPathItem()
        self._window_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._window_item.setPen(QPen(QColor(120, 175, 230), 2))
        self._handles = {
            name: QGraphicsRectItem() for name in ["top", "right", "bottom", "left"]
        }
        for handle in self._handles.values():
            handle.setBrush(QBrush(QColor(255, 255, 255)))
            handle.setPen(QPen(QColor(70, 125, 190), 1))

        self._scene.addItem(self._pixmap_item)
        self._scene.addItem(self._shade_item)
        self._scene.addItem(self._window_item)
        for handle in self._handles.values():
            self._scene.addItem(handle)
        self.setScene(self._scene)
        self.setSceneRect(0, 0, self._image.width, self._image.height)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self._update_overlay()

    def drawBackground(self, painter, rect):
        draw_wallpaper_background(self, painter)

    def set_crop_changed_callback(self, callback: Callable[[int, int, int], None]):
        self._crop_changed_callback = callback

    def set_settings(self, settings: RenderSettings):
        self._settings = settings
        self._update_overlay()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            handle = self._handle_at(scene_pos)
            if handle is not None:
                self._resize_handle = handle
                self.viewport().setCursor(cursor_for_handle(handle, closed=True))
                event.accept()
                return
            window_path = self._window_path()
            if window_path.contains(scene_pos):
                self._drag_offset = scene_pos - self._crop_rect().topLeft()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._resize_handle is not None:
            crop_box = resize_crop_box_for_handle(
                self._image.size,
                self._crop_box(),
                source_window_aspect_size(self._settings),
                self._resize_handle,
                scene_pos.x(),
                scene_pos.y(),
            )
            self._emit_crop_box_changed(crop_box)
            self._update_overlay()
            event.accept()
            return

        if self._drag_offset is not None:
            crop_rect = self._crop_rect()
            left = clamp(
                round(scene_pos.x() - self._drag_offset.x()),
                0,
                self._image.width - round(crop_rect.width()),
            )
            top = clamp(
                round(scene_pos.y() - self._drag_offset.y()),
                0,
                self._image.height - round(crop_rect.height()),
            )
            crop_x = percent_for_axis_origin(
                self._image.width - round(crop_rect.width()), left
            )
            crop_y = percent_for_axis_origin(
                self._image.height - round(crop_rect.height()), top
            )
            if self._crop_changed_callback is not None:
                self._crop_changed_callback(
                    self._settings.image_area_percent, crop_x, crop_y
                )
            self._update_overlay()
            event.accept()
            return

        handle = self._handle_at(scene_pos)
        if handle is not None:
            self.viewport().setCursor(cursor_for_handle(handle))
            event.accept()
            return

        if self._window_path().contains(scene_pos):
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and (
            self._drag_offset is not None or self._resize_handle is not None
        ):
            self._drag_offset = None
            self._resize_handle = None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _crop_rect(self) -> QRectF:
        left, top, right, bottom = self._crop_box()
        return QRectF(left, top, right - left, bottom - top)

    def _crop_box(self) -> tuple[int, int, int, int]:
        return source_crop_box(
            self._image.size,
            source_window_aspect_size(self._settings),
            self._settings,
        )

    def _window_path(self) -> QPainterPath:
        return window_shape_path(
            self._crop_rect(),
            effective_window_shape(self._settings),
            round_corners=self._settings.window_round_corners,
        )

    def _update_overlay(self):
        image_path = QPainterPath()
        image_path.addRect(0, 0, self._image.width, self._image.height)
        window_path = self._window_path()
        shade_path = image_path.subtracted(window_path)
        self._shade_item.setPath(shade_path)
        self._window_item.setPath(window_path)
        self._update_handles()

    def _update_handles(self):
        rect = self._crop_rect()
        size = handle_size_for_image(self._image.size)
        half = size / 2
        centers = {
            "top": (rect.center().x(), rect.top()),
            "right": (rect.right(), rect.center().y()),
            "bottom": (rect.center().x(), rect.bottom()),
            "left": (rect.left(), rect.center().y()),
        }
        for name, (center_x, center_y) in centers.items():
            self._handles[name].setRect(center_x - half, center_y - half, size, size)

    def _handle_at(self, scene_pos):
        for name, handle in self._handles.items():
            if handle.rect().contains(scene_pos):
                return name
        return None

    def _emit_crop_box_changed(self, crop_box: tuple[int, int, int, int]):
        left, top, right, bottom = crop_box
        crop_w = right - left
        crop_h = bottom - top
        image_area = clamp(round(crop_h / self._image.height * 100), 10, 100)
        crop_x = percent_for_axis_origin(self._image.width - crop_w, left)
        crop_y = percent_for_axis_origin(self._image.height - crop_h, top)
        if self._crop_changed_callback is not None:
            self._crop_changed_callback(image_area, crop_x, crop_y)


class StereoDandifierWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("StereoDandifier")
        self.resize(1360, 860)
        self.setAcceptDrops(True)

        self.images: list[ProjectImage] = []
        self.current_index: int | None = None
        self._updating_controls = False
        self._cross_eyed_preview = False
        self.default_export_layout = default_page_layout()

        self._build_ui()
        self._apply_app_style()

    def _build_ui(self):
        self._build_actions()
        self._build_toolbar()

        root = QSplitter(Qt.Orientation.Horizontal)
        root.setChildrenCollapsible(False)
        self.setCentralWidget(root)

        root.addWidget(self._build_library())
        root.addWidget(self._build_canvas())
        root.addWidget(self._build_inspector())
        root.setSizes([240, 820, 300])

        self._build_status_bar()
        self._set_comfort("No image loaded")

    def _build_actions(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        self.import_action = QAction("Import Images", self)
        self.import_action.triggered.connect(self.import_images)

        self.export_action = QAction("Export PDF", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.export_card)

        self.save_card_action = QAction("Save Current Card Data", self)
        self.save_card_action.setEnabled(False)
        self.save_card_action.triggered.connect(self.save_current_card_data)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)

        file_menu.addAction(self.import_action)
        file_menu.addAction(self.save_card_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    def _build_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(self.export_action)
        toolbar.addAction(self.save_card_action)

    def _build_status_bar(self):
        status_bar = QStatusBar()
        self.comfort_label = QLabel()
        self.comfort_label.setObjectName("comfortLabel")
        status_bar.addPermanentWidget(self.comfort_label, 1)
        self.setStatusBar(status_bar)

    def _build_library(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        title = QLabel("Thumbnails")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.add_thumbnail_button = QToolButton()
        self.add_thumbnail_button.setText("+")
        self.add_thumbnail_button.setToolTip("Import images")
        self.add_thumbnail_button.clicked.connect(self.import_images)
        header.addWidget(self.add_thumbnail_button)

        self.remove_thumbnail_button = QToolButton()
        self.remove_thumbnail_button.setText("-")
        self.remove_thumbnail_button.setToolTip("Remove selected thumbnail")
        self.remove_thumbnail_button.setEnabled(False)
        self.remove_thumbnail_button.clicked.connect(self._remove_current_thumbnail)
        header.addWidget(self.remove_thumbnail_button)

        layout.addLayout(header)

        self.library = QListWidget()
        self.library.setIconSize(QSize(96, 64))
        self.library.currentItemChanged.connect(self._select_library_item)
        layout.addWidget(self.library)

        hint = QLabel("Drag SBS, MPO, JPEG, PNG, or DNG files here.")
        hint.setWordWrap(True)
        hint.setObjectName("hintText")
        layout.addWidget(hint)

        return panel

    def _build_canvas(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)

        preview_controls = QHBoxLayout()
        preview_controls.addStretch(1)
        self.cross_eyed_preview = QToolButton()
        self.cross_eyed_preview.setText("Cross-eyed preview")
        self.cross_eyed_preview.setCheckable(True)
        self.cross_eyed_preview.setToolTip(
            "Swap the preview eyes only. Exported and saved cards stay uncrossed."
        )
        self.cross_eyed_preview.toggled.connect(self._cross_eyed_preview_changed)
        preview_controls.addWidget(self.cross_eyed_preview)
        layout.addLayout(preview_controls)

        self.card_view = ZoomableImageView("Import an SBS stereo image to begin")
        layout.addWidget(self.card_view)

        return panel

    def _build_inspector(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Properties")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.image_group = QGroupBox("Image")
        image_layout = QFormLayout(self.image_group)
        self.auto_improve = QPushButton("Auto Improve Photo")
        self.auto_improve.setToolTip(
            "Apply one shared, stereo-safe levels adjustment to both eyes."
        )
        self.auto_improve.clicked.connect(self.auto_improve_current_image)
        image_layout.addRow(self.auto_improve)
        self.auto_rectify = QPushButton("Stereo Rectify")
        self.auto_rectify.setToolTip("Detect and correct vertical eye alignment.")
        self.auto_rectify.clicked.connect(self.auto_rectify_current_image)
        image_layout.addRow(self.auto_rectify)
        layout.addWidget(self.image_group)

        self.card_group = QGroupBox("Card")
        card_layout = QFormLayout(self.card_group)
        self.layout_template = QComboBox()
        self.layout_template.addItems([layout.value for layout in CARD_FORMATS])
        for index, name in enumerate(CARD_FORMATS):
            self.layout_template.setItemData(
                index,
                format_particulars(name),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.layout_template.currentTextChanged.connect(self._layout_template_changed)
        self.layout_info = QLabel()
        self.layout_info.setObjectName("infoBox")
        self.layout_info.setWordWrap(True)
        self.card_info = QLabel("No thumbnail selected")
        self.card_info.setObjectName("infoBox")
        self.card_info.setWordWrap(True)
        self._update_layout_info(CardLayoutName(self.layout_template.currentText()))
        self._update_card_info()
        card_layout.addRow("Layout", self.layout_template)
        card_layout.addRow(self.layout_info)
        card_layout.addRow(self.card_info)
        layout.addWidget(self.card_group)

        self.style_group = QGroupBox("Style")
        style_layout = QFormLayout(self.style_group)
        self.tone_mode = QComboBox()
        self.tone_mode.addItems([mode.value for mode in ToneMode])
        self.tone_mode.currentTextChanged.connect(self._tone_mode_changed)
        self.brightness = self._make_slider(-100, 300, 0, affects_comfort=False)
        self.contrast = self._make_slider(-100, 100, 0, affects_comfort=False)
        self.saturation_label, self.saturation = self._add_slider_row(
            style_layout, "Saturation", -100, 100, 0, affects_comfort=False
        )
        self.sepia_strength_label, self.sepia_strength = self._add_slider_row(
            style_layout, "Sepia Strength", 0, 100, 45, affects_comfort=False
        )
        style_layout.insertRow(0, "Mode", self.tone_mode)
        style_layout.insertRow(1, "Brightness", self.brightness)
        style_layout.insertRow(2, "Contrast", self.contrast)
        self._update_tone_controls(ToneMode(self.tone_mode.currentText()))
        layout.addWidget(self.style_group)
        self._set_card_controls_enabled(False)

        layout.addStretch(1)
        return panel

    def _make_slider(
        self,
        minimum: int,
        maximum: int,
        value: int,
        affects_comfort: bool = True,
    ) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setTracking(False)
        slider.valueChanged.connect(
            lambda _value, recalculate=affects_comfort: self._controls_changed(
                recalculate_comfort=recalculate
            )
        )
        return slider

    def _add_slider_row(
        self,
        layout: QFormLayout,
        label_text: str,
        minimum: int,
        maximum: int,
        value: int,
        affects_comfort: bool = True,
    ) -> tuple[QLabel, QSlider]:
        label = QLabel(label_text)
        slider = self._make_slider(minimum, maximum, value, affects_comfort)
        layout.addRow(label, slider)
        return label, slider

    def _apply_app_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #f4f1ea;
            }
            QMenuBar, QToolBar {
                background: #fbfaf6;
                border-bottom: 1px solid #d8d1c4;
                spacing: 8px;
            }
            QWidget {
                color: #252525;
                font-size: 13px;
            }
            QListWidget, QTextEdit, QComboBox {
                background: #fffdf8;
                border: 1px solid #d6cec0;
                border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item:selected {
                background: #d8e7e0;
                color: #14251f;
            }
            QListWidget::item:disabled {
                color: #6e675e;
                background: #f4f1ea;
            }
            QGroupBox {
                border: 1px solid #d6cec0;
                border-radius: 8px;
                margin-top: 18px;
                padding: 12px 8px 8px 8px;
                background: #fbfaf6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #5b5347;
            }
            QPushButton {
                background: #244e47;
                color: #ffffff;
                border: 0;
                border-radius: 6px;
                padding: 8px 10px;
            }
            QPushButton:disabled {
                background: #bbb4a8;
            }
            QLabel#panelTitle {
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#hintText {
                color: #6e675e;
            }
            QLabel#infoBox {
                background: #eef4f1;
                border: 1px solid #c7d8d0;
                border-radius: 6px;
                color: #345047;
                padding: 8px;
            }
            QTextEdit#captionEditor {
                background: #fffefb;
                border: 1px solid #cbbfae;
                border-radius: 6px;
                padding: 6px;
            }
            QToolButton {
                background: #fffdf8;
                border: 1px solid #d6cec0;
                border-radius: 5px;
                padding: 4px;
            }
            QToolButton:checked {
                background: #d8e7e0;
                border-color: #8fb4a6;
            }
            QCheckBox:disabled {
                color: #9a9388;
            }
            QGraphicsView#preview {
                background: #ebe6dc;
                border: 3px solid #d0c7b8;
                border-radius: 8px;
                color: #71685d;
            }
            QGraphicsView#preview[comfortState="excellent"] {
                border-color: #4f9d69;
            }
            QGraphicsView#preview[comfortState="good"] {
                border-color: #8fb4a6;
            }
            QGraphicsView#preview[comfortState="borderline"] {
                border-color: #d89b3d;
            }
            QGraphicsView#preview[comfortState="poor"] {
                border-color: #c85c4a;
            }
            QGraphicsView#preview[comfortState="neutral"] {
                border-color: #d0c7b8;
            }
            QLabel#comfortLabel {
                padding: 4px 10px;
                background: transparent;
                color: #17382f;
                font-weight: 700;
            }
            """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        self._import_paths(paths)

    def import_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Stereo Images",
            "",
            SUPPORTED_IMAGE_FILTER,
        )
        self._import_paths([Path(path) for path in file_paths])

    def _import_paths(self, paths: list[Path]):
        imported = 0
        for path in paths:
            if not path.is_file():
                continue
            try:
                project_images = load_project_images(path)
            except Exception as exc:
                QMessageBox.warning(
                    self, "Import failed", f"Could not open {path.name}: {exc}"
                )
                continue

            for project_image in project_images:
                if self._needs_file_separator(project_image.path):
                    self._add_file_separator(project_image.path)
                self.images.append(project_image)
                self._add_library_item(project_image, len(self.images) - 1)
                imported += 1

        if imported and self.current_index is None:
            self._select_first_image_item()
        elif imported:
            self.statusBar().showMessage(f"Imported {imported} image(s)")
        self._refresh_previews(reset_view=True)

    def _needs_file_separator(self, path: Path) -> bool:
        if not self.images:
            return False
        return self.images[-1].path != path

    def _add_file_separator(self, path: Path):
        item = QListWidgetItem(path.name)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.UserRole, None)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.library.addItem(item)

    def _add_library_item(self, project_image: ProjectImage, image_index: int):
        thumb = left_thumbnail_image(project_image.source)
        thumb.thumbnail((160, 100), Image.Resampling.LANCZOS)
        pixmap = QPixmap.fromImage(ImageQt(thumb))

        item = QListWidgetItem(project_image.thumbnail_name)
        item.setIcon(pixmap)
        item.setFlags(
            (item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
        )
        item.setData(Qt.ItemDataRole.UserRole, image_index)
        item.setToolTip(
            f"{project_image.path}\nFrame {project_image.frame_index + 1} of {project_image.frame_count}"
        )
        self.library.addItem(item)

    def _select_first_image_item(self):
        for row in range(self.library.count()):
            item = self.library.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self.library.setCurrentRow(row)
                return

    def _select_library_item(self, current: QListWidgetItem | None, _previous):
        if current is None:
            self.current_index = None
            self.remove_thumbnail_button.setEnabled(False)
            self.save_card_action.setEnabled(False)
            self._load_controls()
            self._refresh_previews(reset_view=True)
            return

        image_index = current.data(Qt.ItemDataRole.UserRole)
        if image_index is None:
            self.current_index = None
            self.remove_thumbnail_button.setEnabled(False)
            self.save_card_action.setEnabled(False)
            self._load_controls()
            self._refresh_previews(reset_view=True)
            return

        self.remove_thumbnail_button.setEnabled(True)
        self.save_card_action.setEnabled(True)
        self._select_image(image_index)

    def _select_image(self, index: int):
        if index < 0 or index >= len(self.images):
            return

        self.current_index = index
        self.card_view.fit_to_view()

        self._load_controls()
        self._refresh_previews(reset_view=True)
        self.statusBar().showMessage(f"Loaded: {self.current_image.display_name}")

    def _remove_current_thumbnail(self):
        item = self.library.currentItem()
        if item is None:
            return

        image_index = item.data(Qt.ItemDataRole.UserRole)
        if image_index is None:
            return

        row = self.library.row(item)
        removed = self.images.pop(image_index)
        self.library.blockSignals(True)
        self.library.takeItem(row)
        self._remove_orphan_file_separators()
        self._reindex_library_items()
        self._select_nearest_image_item(row)
        self.library.blockSignals(False)

        selected = self.library.currentItem()
        if selected is None:
            self.current_index = None
            self.remove_thumbnail_button.setEnabled(False)
            self.save_card_action.setEnabled(False)
            self._load_controls()
            self._refresh_previews(reset_view=True)
        else:
            self._select_library_item(selected, None)

        self.statusBar().showMessage(f"Removed: {removed.display_name}")

    def _remove_orphan_file_separators(self):
        row = 0
        while row < self.library.count():
            item = self.library.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                row += 1
                continue

            next_is_separator = (
                row + 1 >= self.library.count()
                or self.library.item(row + 1).data(Qt.ItemDataRole.UserRole) is None
            )
            if row == 0 or next_is_separator:
                self.library.takeItem(row)
                continue
            row += 1

    def _reindex_library_items(self):
        image_index = 0
        for row in range(self.library.count()):
            item = self.library.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is None:
                continue
            item.setData(Qt.ItemDataRole.UserRole, image_index)
            image_index += 1

    def _select_nearest_image_item(self, start_row: int):
        for row in range(start_row, self.library.count()):
            item = self.library.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self.library.setCurrentRow(row)
                return

        for row in range(min(start_row, self.library.count() - 1), -1, -1):
            item = self.library.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self.library.setCurrentRow(row)
                return

        self.library.setCurrentItem(None)

    @property
    def current_image(self) -> ProjectImage | None:
        if self.current_index is None:
            return None
        return self.images[self.current_index]

    def _load_controls(self):
        current = self.current_image
        if current is None:
            self._set_card_controls_enabled(False)
            self._update_card_info()
            return

        settings = current.settings
        self._set_card_controls_enabled(True)
        self._updating_controls = True
        self.layout_template.setCurrentText(settings.layout_template.value)
        self._update_layout_info(settings.layout_template)
        self.tone_mode.setCurrentText(settings.tone_mode.value)
        self.cross_eyed_preview.setChecked(self._cross_eyed_preview)
        self.brightness.setValue(settings.brightness)
        self.contrast.setValue(settings.contrast)
        self.saturation.setValue(settings.saturation)
        self.sepia_strength.setValue(settings.sepia_strength)
        self._update_tone_controls(settings.tone_mode)
        self._updating_controls = False
        self._update_card_info()

    def _tone_mode_changed(self, mode: str):
        tone_mode = ToneMode(mode)
        if self._updating_controls:
            self._update_tone_controls(tone_mode)
            return
        defaults = {
            ToneMode.COLOUR: {
                "brightness": 0,
                "contrast": 4,
                "saturation": 8,
                "sepia_strength": 45,
            },
            ToneMode.BLACK_AND_WHITE: {
                "brightness": 0,
                "contrast": 16,
                "saturation": 0,
                "sepia_strength": 45,
            },
            ToneMode.SEPIA: {
                "brightness": 2,
                "contrast": 8,
                "saturation": 0,
                "sepia_strength": 55,
            },
        }
        self._updating_controls = True
        self.brightness.setValue(defaults[tone_mode]["brightness"])
        self.contrast.setValue(defaults[tone_mode]["contrast"])
        self.saturation.setValue(defaults[tone_mode]["saturation"])
        self.sepia_strength.setValue(defaults[tone_mode]["sepia_strength"])
        self._update_tone_controls(tone_mode)
        self._updating_controls = False
        self._controls_changed(recalculate_comfort=False)

    def _update_tone_controls(self, mode: ToneMode):
        colour_mode = mode == ToneMode.COLOUR
        sepia_mode = mode == ToneMode.SEPIA
        self.saturation_label.setVisible(colour_mode)
        self.saturation.setVisible(colour_mode)
        self.sepia_strength_label.setVisible(sepia_mode)
        self.sepia_strength.setVisible(sepia_mode)

    def _layout_template_changed(self, name: str):
        layout_name = CardLayoutName(name)
        if self._updating_controls:
            self._update_layout_info(layout_name)
            return
        self._update_layout_info(layout_name)
        self._controls_changed()

    def _update_layout_info(self, name: CardLayoutName):
        particulars = format_particulars(name)
        self.layout_info.setText(particulars)
        self.layout_template.setToolTip(particulars)

    def _controls_changed(self, *_args, recalculate_comfort: bool = True):
        if self._updating_controls:
            return

        current = self.current_image
        if current is None:
            return

        current.settings = RenderSettings(
            layout_template=CardLayoutName(self.layout_template.currentText()),
            tone_mode=ToneMode(self.tone_mode.currentText()),
            caption_html=current.settings.caption_html,
            caption_position=current.settings.caption_position,
            window_shape=current.settings.window_shape,
            window_round_corners=current.settings.window_round_corners,
            image_area_percent=current.settings.image_area_percent,
            crop_x_percent=current.settings.crop_x_percent,
            crop_y_percent=current.settings.crop_y_percent,
            brightness=self.brightness.value(),
            contrast=self.contrast.value(),
            saturation=self.saturation.value(),
            sepia_strength=self.sepia_strength.value(),
            right_eye_transform=current.settings.right_eye_transform,
        )
        self._refresh_previews(recalculate_comfort=recalculate_comfort)

    def _cross_eyed_preview_changed(self, checked: bool):
        self._cross_eyed_preview = checked
        self._refresh_previews(recalculate_comfort=False)

    def auto_improve_current_image(self):
        current = self.current_image
        if current is None:
            return

        left, right = split_stereo_pair(current.source, RenderSettings())
        adjusted_left, adjusted_right = auto_improve_stereo_pair(left, right)

        improved = Image.new("RGB", current.source.size)
        improved.paste(adjusted_left, (0, 0))
        improved.paste(adjusted_right, (adjusted_left.width, 0))
        current.source = improved
        self._refresh_previews(reset_view=True)
        self.statusBar().showMessage("Applied stereo-safe photo improvement")

    def auto_rectify_current_image(self):
        current = self.current_image
        if current is None:
            return

        progress = QProgressDialog(
            "Detecting stereo rectification...",
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle("Stereo Rectify")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QCoreApplication.processEvents()

        try:
            right_eye_transform = suggested_right_eye_transform(current.source)
        finally:
            progress.close()

        if right_eye_transform is None:
            self.statusBar().showMessage(
                "Could not detect a reliable rectification transform"
            )
            return

        current.settings = replace(
            current.settings,
            right_eye_transform=right_eye_transform,
        )
        self._refresh_previews(reset_view=True)
        self.statusBar().showMessage("Applied right-eye rectification transform")

    def _refresh_previews(
        self, reset_view: bool = False, recalculate_comfort: bool = True
    ):
        self.export_action.setEnabled(bool(self.selected_project_images()))
        self._update_card_info()
        current = self.current_image
        self.save_card_action.setEnabled(current is not None)
        if current is None:
            self.card_view.set_placeholder("Select a thumbnail to edit its card")
            self._set_comfort("No thumbnail selected")
            return

        preview_dpi = editor_dpi_for_image(current)
        card = render_project_card(
            current, dpi=preview_dpi, cross_eyed=self._cross_eyed_preview
        )
        self.card_view.set_image(card, reset_view=reset_view)
        self.card_view.set_hotspot_actions(
            [
                *[
                    (
                        bounds,
                        self.edit_window,
                        "Click to edit the stereo window crop and shape.",
                    )
                    for bounds in window_bounds_for_project(current, preview_dpi)
                ],
                *[
                    (bounds, self.edit_caption, "Click to edit the card caption.")
                    for bounds in caption_bounds_for_project(current, preview_dpi)
                ],
            ]
        )
        if recalculate_comfort:
            self._set_comfort(score_comfort(current.source, current.settings))

    def edit_caption(self):
        current = self.current_image
        if current is None:
            return

        dialog = CaptionDialog(current.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        current.settings = replace(
            current.settings,
            caption_html=dialog.caption_html,
            caption_position=dialog.caption_position,
        )
        self._refresh_previews()

    def edit_window(self):
        current = self.current_image
        if current is None:
            return

        preview_image, _right = split_stereo_pair(current.source, current.settings)
        preview_image = apply_style(preview_image, current.settings)
        dialog = WindowDialog(current.settings, self, preview_image=preview_image)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        current.settings = replace(
            current.settings,
            window_shape=dialog.window_shape,
            window_round_corners=dialog.window_round_corners,
            image_area_percent=dialog.image_area_percent,
            crop_x_percent=dialog.crop_x_percent,
            crop_y_percent=dialog.crop_y_percent,
        )
        self._refresh_previews()

    def selected_project_images(self) -> list[ProjectImage]:
        return list(self.images)

    def _set_card_controls_enabled(self, enabled: bool):
        self.image_group.setEnabled(enabled)
        self.card_group.setEnabled(enabled)
        self.style_group.setEnabled(enabled)

    def _update_card_info(self):
        current = self.current_image
        if current is None:
            self.card_info.setText("No thumbnail selected")
            return

        spec = CARD_FORMATS[current.settings.layout_template]
        card_w, card_h = spec.card_mm
        image_w, image_h = spec.image_mm
        self.card_info.setText(
            f"{current.display_name}\n"
            f"Source: {current.source.width} x {current.source.height} px\n"
            f"Card: {card_w:g} x {card_h:g} mm; images: {image_w:g} x {image_h:g} mm"
        )

    def _set_comfort(self, text: str):
        self.comfort_label.setText(f"Comfort: {text}")
        self._set_preview_comfort_state(comfort_state_for_text(text))

    def _set_preview_comfort_state(self, state: str):
        self.card_view.setProperty("comfortState", state)
        self.card_view.style().unpolish(self.card_view)
        self.card_view.style().polish(self.card_view)
        self.card_view.update()

    def save_current_card_data(self):
        current = self.current_image
        if current is None:
            return

        default_name = current.path.with_suffix("").name
        if current.frame_count > 1:
            default_name = f"{default_name}-frame-{current.frame_index + 1}"
        if current.variant_name:
            default_name = f"{default_name}-{safe_filename_part(current.variant_name)}"
        default_name = f"{default_name}-stereocard.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Current Card Data",
            str(current.path.with_name(default_name)),
            "JSON document (*.json)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".json"):
            file_path += ".json"

        save_card_json(current, Path(file_path))
        self.statusBar().showMessage(f"Saved card data: {Path(file_path).name}")

    def export_card(self):
        selected_images = self.selected_project_images()
        if not selected_images:
            return

        export_dialog = ExportDialog(self.default_export_layout, selected_images, self)
        if export_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        page_layout = export_dialog.selected_layout
        self.default_export_layout = page_layout

        default_name = "stereocards.pdf"
        if len(selected_images) == 1:
            selected = selected_images[0]
            default_stem = selected.path.with_suffix("").name
            if selected.frame_count > 1:
                default_stem = f"{default_stem}-frame-{selected.frame_index + 1}"
            default_name = default_stem + "-stereocard.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            str(selected_images[0].path.with_name(default_name)),
            "PDF document (*.pdf)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        export_dpi = export_dpi_for_images(selected_images)
        cards = [
            render_project_card(project_image, dpi=export_dpi)
            for project_image in selected_images
        ]
        pages = render_print_pages(cards, page_layout, dpi=export_dpi)
        save_pdf_pages(pages, file_path, dpi=export_dpi)
        self.statusBar().showMessage(f"Exported: {Path(file_path).name}")


class CaptionDialog(QDialog):
    def __init__(self, settings: RenderSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Caption")
        self.resize(560, 360)
        self._updating_toolbar = False

        layout = QVBoxLayout(self)

        self.font_family = QFontComboBox()
        self.font_size = QSpinBox()
        self.font_size.setRange(6, 96)
        self.font_size.setValue(DEFAULT_CAPTION_FONT_SIZE)
        self.bold = make_editor_button("B", "Bold", False)
        self.italic = make_editor_button("I", "Italic", False)
        self.align_left = make_editor_button("align-left", "Align left", False)
        self.align_center = make_editor_button("align-center", "Align center", True)
        self.align_right = make_editor_button("align-right", "Align right", False)
        self.alignment_buttons = {
            "Left": self.align_left,
            "Center": self.align_center,
            "Right": self.align_right,
        }
        self.caption_under_left = QCheckBox("Under left")
        self.caption_under_right = QCheckBox("Under right")
        self._set_caption_position_checks(settings.caption_position)
        self.caption_under_left.toggled.connect(self._caption_position_changed)
        self.caption_under_right.toggled.connect(self._caption_position_changed)

        layout.addWidget(
            caption_editor_toolbar(
                self.font_family,
                self.font_size,
                self.bold,
                self.italic,
                self.align_left,
                self.align_center,
                self.align_right,
            )
        )

        self.editor = QTextEdit()
        self.editor.setObjectName("captionEditor")
        self.editor.setAcceptRichText(True)
        if settings.caption_html:
            self.editor.setHtml(settings.caption_html)
        else:
            self.editor.clear()
        layout.addWidget(self.editor, 1)
        self.caption_placement_row = caption_placement_controls(
            self.caption_under_left,
            self.caption_under_right,
        )
        layout.addWidget(self.caption_placement_row)

        self.font_family.currentFontChanged.connect(self._caption_font_changed)
        self.font_size.valueChanged.connect(self._caption_format_changed)
        self.bold.toggled.connect(self._caption_format_changed)
        self.italic.toggled.connect(self._caption_format_changed)
        self.align_left.clicked.connect(lambda: self._set_alignment("Left"))
        self.align_center.clicked.connect(lambda: self._set_alignment("Center"))
        self.align_right.clicked.connect(lambda: self._set_alignment("Right"))
        self.editor.currentCharFormatChanged.connect(self._load_text_format)
        self.editor.cursorPositionChanged.connect(self._load_alignment)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_text_format(self.editor.currentCharFormat())
        self._load_alignment()
        if not settings.caption_html:
            self._caption_format_changed()

    @property
    def caption_html(self) -> str:
        return caption_html_from_editor(self.editor)

    @property
    def caption_position(self) -> CaptionPosition:
        left = self.caption_under_left.isChecked()
        right = self.caption_under_right.isChecked()
        if left and not right:
            return CaptionPosition.LEFT_IMAGE
        if right and not left:
            return CaptionPosition.RIGHT_IMAGE
        return CaptionPosition.BOTH_IMAGES

    def _caption_format_changed(self, *_args):
        if self._updating_toolbar:
            return

        text_format = QTextCharFormat()
        text_format.setFontFamilies([self.font_family.currentFont().family()])
        text_format.setFontPointSize(self.font_size.value())
        text_format.setFontWeight(
            QFont.Weight.Bold if self.bold.isChecked() else QFont.Weight.Normal
        )
        text_format.setFontItalic(self.italic.isChecked())
        self.editor.mergeCurrentCharFormat(text_format)

    def _caption_font_changed(self, _font: QFont):
        self._caption_format_changed()

    def _set_alignment(self, justification: str):
        self._set_alignment_button(justification)
        self.editor.setAlignment(qt_alignment_from_caption(justification))

    def _set_alignment_button(self, justification: str):
        self._updating_toolbar = True
        for name, button in self.alignment_buttons.items():
            button.setChecked(name == justification)
        self._updating_toolbar = False

    def _load_text_format(self, text_format: QTextCharFormat):
        self._updating_toolbar = True
        self.font_family.setCurrentFont(
            QFont(caption_font_family_from_qt_format(text_format))
        )
        self.font_size.setValue(caption_font_size_from_qt_format(text_format))
        self.bold.setChecked(text_format.font().bold())
        self.italic.setChecked(text_format.font().italic())
        self._updating_toolbar = False

    def _load_alignment(self):
        self._set_alignment_button(
            caption_justification_from_qt_alignment(self.editor.alignment())
        )

    def _set_caption_position_checks(self, caption_position: CaptionPosition):
        self.caption_under_left.setChecked(
            caption_position != CaptionPosition.RIGHT_IMAGE
        )
        self.caption_under_right.setChecked(
            caption_position != CaptionPosition.LEFT_IMAGE
        )

    def _caption_position_changed(self):
        if self.caption_under_left.isChecked() or self.caption_under_right.isChecked():
            return
        sender = self.sender()
        fallback = (
            self.caption_under_right
            if sender is self.caption_under_left
            else self.caption_under_left
        )
        fallback.blockSignals(True)
        fallback.setChecked(True)
        fallback.blockSignals(False)


class WindowDialog(QDialog):
    def __init__(
        self,
        settings: RenderSettings,
        parent: QWidget | None = None,
        preview_image: Image.Image | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Window")
        self.resize(620, 620)
        self._base_settings = settings
        self._image_area_percent = settings.image_area_percent
        self._crop_x_percent = settings.crop_x_percent
        self._crop_y_percent = settings.crop_y_percent
        self._updating_from_view = False

        layout = QVBoxLayout(self)
        self.preview = None
        if preview_image is not None:
            self.preview = SourceWindowView(preview_image, settings)
            self.preview.set_crop_changed_callback(self._crop_changed_from_view)
            layout.addWidget(self.preview, 1)

        self.shape_buttons = {}
        self.shape_button_group = QButtonGroup(self)
        self.shape_button_group.setExclusive(True)
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)
        controls_layout.addStretch(1)
        shape_label = QLabel("Shape")
        controls_layout.addWidget(shape_label)
        window_shapes = window_shapes_for_layout(settings)
        selected_shape = effective_window_shape(settings)
        if selected_shape not in window_shapes:
            selected_shape = WindowShape.RECTANGLE
        for shape in window_shapes:
            button = make_shape_button(shape, checked=shape == selected_shape)
            button.clicked.connect(self._preview_controls_changed)
            self.shape_button_group.addButton(button)
            self.shape_buttons[shape] = button
            controls_layout.addWidget(button)

        self.round_corners = QCheckBox("Round corners")
        self.round_corners.setChecked(settings.window_round_corners)
        self.round_corners.toggled.connect(self._preview_controls_changed)
        controls_layout.addWidget(self.round_corners)
        self._update_round_corners_state()

        controls_layout.addStretch(1)
        layout.addWidget(controls)

        hint = QLabel(
            "Drag the clear window over the image. The greyed area is outside the "
            "card window; both stereo eyes keep the same linked crop."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintText")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def window_shape(self) -> WindowShape:
        for shape, button in self.shape_buttons.items():
            if button.isChecked():
                return shape
        return WindowShape.RECTANGLE

    @property
    def image_area_percent(self) -> int:
        return self._image_area_percent

    @property
    def window_round_corners(self) -> bool:
        return (
            self.window_shape not in {WindowShape.CIRCLE, WindowShape.OVAL}
            and self.round_corners.isChecked()
        )

    @property
    def crop_x_percent(self) -> int:
        return self._crop_x_percent

    @property
    def crop_y_percent(self) -> int:
        return self._crop_y_percent

    def _preview_settings(self) -> RenderSettings:
        return replace(
            self._base_settings,
            window_shape=self.window_shape,
            window_round_corners=self.window_round_corners,
            image_area_percent=self.image_area_percent,
            crop_x_percent=self.crop_x_percent,
            crop_y_percent=self.crop_y_percent,
        )

    def _preview_controls_changed(self, *_args):
        self._update_round_corners_state()
        if self._updating_from_view or self.preview is None:
            return
        self.preview.set_settings(self._preview_settings())

    def _crop_changed_from_view(
        self, image_area_percent: int, crop_x_percent: int, crop_y_percent: int
    ):
        self._updating_from_view = True
        self._image_area_percent = image_area_percent
        self._crop_x_percent = crop_x_percent
        self._crop_y_percent = crop_y_percent
        self._updating_from_view = False
        if self.preview is not None:
            self.preview.set_settings(self._preview_settings())

    def _update_round_corners_state(self):
        has_no_corners = self.window_shape in {WindowShape.CIRCLE, WindowShape.OVAL}
        if has_no_corners and self.round_corners.isChecked():
            self.round_corners.blockSignals(True)
            self.round_corners.setChecked(False)
            self.round_corners.blockSignals(False)
        self.round_corners.setEnabled(not has_no_corners)


class ExportDialog(QDialog):
    def __init__(
        self,
        default_layout: PageLayout,
        project_images: list[ProjectImage],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export PDF")
        self._layouts = export_page_layouts(default_layout)
        self._project_images = project_images

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.paper_choice = QComboBox()
        self.paper_choice.addItems(self._layouts.keys())
        self.paper_choice.setCurrentText(default_layout.name)
        self.paper_choice.currentTextChanged.connect(self._update_details)

        self.paper_size_label = QLabel()
        self.paper_source_label = QLabel()
        self.paper_source_label.setWordWrap(True)
        self.paper_source_label.setObjectName("hintText")

        form.addRow("Paper", self.paper_choice)
        form.addRow("Dimensions", self.paper_size_label)
        form.addRow(self.paper_source_label)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_details(self.paper_choice.currentText())

    @property
    def selected_layout(self) -> PageLayout:
        return self._layouts[self.paper_choice.currentText()]

    def _update_details(self, name: str):
        page_layout = self._layouts[name]
        width_mm, height_mm = page_layout.size_mm
        self.paper_size_label.setText(f"{width_mm:g} x {height_mm:g} mm")
        self.paper_source_label.setText(
            f"{page_layout.source}\nImages will be rendered from the selected originals "
            "at the highest useful resolution for the chosen card layout."
        )


def export_page_layouts(default_layout: PageLayout) -> dict[str, PageLayout]:
    layouts = {
        "A4": page_layout_for_name("A4"),
        "Letter": page_layout_for_name("Letter"),
    }
    layouts[default_layout.name] = default_layout
    return layouts


def export_dpi_for_images(project_images: list[ProjectImage]) -> int:
    if not project_images:
        return 1
    return max(
        export_dpi_for_source(
            project_image.source,
            project_image.settings,
            minimum_dpi=1,
        )
        for project_image in project_images
    )


def editor_dpi_for_image(project_image: ProjectImage) -> int:
    return export_dpi_for_source(
        project_image.source,
        project_image.settings,
        minimum_dpi=MIN_CARD_EDITOR_DPI,
    )


def comfort_state_for_text(text: str) -> str:
    if text.startswith("Excellent"):
        return "excellent"
    if text.startswith("Good"):
        return "good"
    if text.startswith("Borderline"):
        return "borderline"
    if text.startswith("Poor"):
        return "poor"
    return "neutral"


def safe_filename_part(value: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in value)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe.lower() or "card"


def caption_html_from_editor(editor: QTextEdit) -> str:
    if not editor.toPlainText().strip():
        return ""
    return editor.toHtml()


def caption_font_size_from_qt_format(text_format: QTextCharFormat) -> int:
    font = text_format.font()
    font_size = text_format.fontPointSize()
    if font_size <= 0:
        font_size = font.pointSizeF()
    if font_size <= 0:
        font_size = DEFAULT_CAPTION_FONT_SIZE
    return round(font_size)


def qt_alignment_from_caption(justification: str):
    if justification == "Left":
        return Qt.AlignmentFlag.AlignLeft
    if justification == "Right":
        return Qt.AlignmentFlag.AlignRight
    return Qt.AlignmentFlag.AlignHCenter


def caption_justification_from_qt_alignment(alignment) -> str:
    if alignment & Qt.AlignmentFlag.AlignRight:
        return "Right"
    if alignment & Qt.AlignmentFlag.AlignLeft:
        return "Left"
    return "Center"


def caption_font_family_from_qt_format(text_format: QTextCharFormat) -> str:
    font = text_format.font()
    families = text_format.fontFamilies()
    if families:
        return families[0]

    families = font.families()
    if families:
        return families[0]

    return DEFAULT_CAPTION_FONT_FAMILY


def caption_editor_toolbar(
    font_family: QFontComboBox,
    font_size: QSpinBox,
    bold: QToolButton,
    italic: QToolButton,
    align_left: QToolButton,
    align_center: QToolButton,
    align_right: QToolButton,
) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    font_family.setMinimumWidth(112)
    font_size.setFixedWidth(54)

    for control in [
        font_family,
        font_size,
        bold,
        italic,
        align_left,
        align_center,
        align_right,
    ]:
        layout.addWidget(control)
    layout.addStretch(1)
    return widget


def caption_placement_controls(
    caption_under_left: QCheckBox,
    caption_under_right: QCheckBox,
) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addStretch(1)
    layout.addWidget(caption_under_left)
    layout.addWidget(caption_under_right)
    layout.addStretch(1)
    return widget


def source_window_aspect_size(settings: RenderSettings) -> tuple[int, int]:
    spec = CARD_FORMATS[settings.layout_template]
    width_mm, height_mm = spec.image_mm
    return max(1, round((width_mm / height_mm) * 1000)), 1000


def resize_crop_box_for_handle(
    image_size: tuple[int, int],
    crop_box: tuple[int, int, int, int],
    aspect_size: tuple[int, int],
    handle: str,
    scene_x: float,
    scene_y: float,
) -> tuple[int, int, int, int]:
    image_w, image_h = image_size
    left, top, right, bottom = crop_box
    aspect = aspect_size[0] / aspect_size[1]
    min_h = image_h * 0.1

    if handle in {"top", "bottom"}:
        center_x = (left + right) / 2
        width_limit_h = (2 * min(center_x, image_w - center_x)) / aspect
        if handle == "top":
            max_h = min(bottom, width_limit_h)
            height = clamp_float(bottom - scene_y, min_h, max_h)
            top = bottom - height
        else:
            max_h = min(image_h - top, width_limit_h)
            height = clamp_float(scene_y - top, min_h, max_h)
            bottom = top + height
        width = height * aspect
        left = center_x - width / 2
        right = center_x + width / 2
    else:
        center_y = (top + bottom) / 2
        min_w = min_h * aspect
        height_limit_w = 2 * min(center_y, image_h - center_y) * aspect
        if handle == "left":
            max_w = min(right, height_limit_w)
            width = clamp_float(right - scene_x, min_w, max_w)
            left = right - width
        else:
            max_w = min(image_w - left, height_limit_w)
            width = clamp_float(scene_x - left, min_w, max_w)
            right = left + width
        height = width / aspect
        top = center_y - height / 2
        bottom = center_y + height / 2

    return (
        round(clamp_float(left, 0, image_w)),
        round(clamp_float(top, 0, image_h)),
        round(clamp_float(right, 0, image_w)),
        round(clamp_float(bottom, 0, image_h)),
    )


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    if maximum < minimum:
        return minimum
    return max(minimum, min(maximum, value))


def handle_size_for_image(image_size: tuple[int, int]) -> float:
    return max(6, min(image_size) * 0.035)


def cursor_for_handle(handle: str, closed: bool = False):
    if handle in {"top", "bottom"}:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.SizeHorCursor


def window_shape_path(
    rect: QRectF, shape: WindowShape, round_corners: bool = False
) -> QPainterPath:
    path = QPainterPath()
    if shape == WindowShape.OVAL:
        path.addEllipse(rect)
    elif shape == WindowShape.CIRCLE:
        diameter = min(rect.width(), rect.height())
        circle = QRectF(
            rect.x() + (rect.width() - diameter) / 2,
            rect.y() + (rect.height() - diameter) / 2,
            diameter,
            diameter,
        )
        path.addEllipse(circle)
    elif shape == WindowShape.ARCHED_TOP:
        arch_height = arched_top_depth(rect.width(), rect.height())
        radius = (
            rounded_corner_radius(rect.width(), rect.height()) if round_corners else 0
        )
        center_x = rect.left() + rect.width() / 2
        path.moveTo(rect.left() + radius, rect.bottom())
        if radius:
            path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
        path.lineTo(rect.left(), rect.top() + arch_height)
        path.quadTo(
            rect.left(),
            rect.top(),
            center_x,
            rect.top(),
        )
        path.quadTo(
            rect.right(),
            rect.top(),
            rect.right(),
            rect.top() + arch_height,
        )
        path.lineTo(rect.right(), rect.bottom() - radius)
        if radius:
            path.quadTo(
                rect.right(),
                rect.bottom(),
                rect.right() - radius,
                rect.bottom(),
            )
        else:
            path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()
    elif round_corners:
        radius = rounded_corner_radius(rect.width(), rect.height())
        path.addRoundedRect(rect, radius, radius)
    else:
        path.addRect(rect)
    return path


def arched_top_depth(width: float, height: float) -> float:
    return min(height * 0.24, width * 0.32)


def rounded_corner_radius(width: float, height: float) -> float:
    return max(1, min(width, height) * 0.04)


def clamp(value: int, minimum: int, maximum: int) -> int:
    if maximum < minimum:
        return minimum
    return max(minimum, min(maximum, value))


def percent_for_axis_origin(max_offset: int, origin: int) -> int:
    if max_offset <= 0:
        return 0
    return round((clamp(origin, 0, max_offset) / max_offset) * 200 - 100)


def window_shapes_for_layout(
    settings: RenderSettings,
) -> tuple[WindowShape, WindowShape, WindowShape]:
    spec = CARD_FORMATS[settings.layout_template]
    image_w, image_h = spec.image_mm
    round_shape = (
        WindowShape.OVAL if abs(image_w - image_h) > 0.01 else WindowShape.CIRCLE
    )
    return (WindowShape.RECTANGLE, round_shape, WindowShape.ARCHED_TOP)


def make_shape_button(shape: WindowShape, checked: bool) -> QToolButton:
    button = QToolButton()
    button.setCheckable(True)
    button.setChecked(checked)
    button.setIcon(shape_icon(shape))
    button.setIconSize(QSize(26, 26))
    button.setFixedSize(QSize(36, 34))
    button.setToolTip(shape.value)
    return button


def shape_icon(shape: WindowShape) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(Qt.GlobalColor.black, 2))
    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    painter.drawPath(window_shape_path(QRectF(6, 5, 20, 22), shape, round_corners=True))
    painter.end()
    return QIcon(pixmap)


def make_editor_button(icon_name: str, tooltip: str, checked: bool) -> QToolButton:
    button = QToolButton()
    button.setCheckable(True)
    button.setChecked(checked)
    button.setIcon(editor_icon(icon_name))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(QSize(30, 28))
    button.setToolTip(tooltip)
    return button


def editor_icon(name: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.GlobalColor.black)

    if name == "B":
        font = QFont(DEFAULT_CAPTION_FONT_FAMILY, 13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "B")
    elif name == "I":
        font = QFont(DEFAULT_CAPTION_FONT_FAMILY, 13)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "I")
    else:
        draw_alignment_icon(painter, name)

    painter.end()
    return QIcon(pixmap)


def draw_alignment_icon(painter: QPainter, name: str):
    widths = {
        "align-left": [16, 11, 15, 9],
        "align-center": [12, 16, 10, 14],
        "align-right": [16, 11, 15, 9],
    }[name]
    y_values = [6, 10, 14, 18]

    for width, y in zip(widths, y_values):
        if name == "align-center":
            x = (24 - width) // 2
        elif name == "align-right":
            x = 20 - width
        else:
            x = 4
        painter.drawLine(x, y, x + width, y)


def left_thumbnail_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 1:
        return image.copy()
    return image.crop((0, 0, width // 2, height))
