from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPainter,
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
    QGraphicsPixmapItem,
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

from stereo_dandifier.formats import CARD_FORMATS, format_particulars
from stereo_dandifier.image_ops import (
    export_dpi_for_source,
    render_print_pages,
    render_project_card,
    save_pdf_pages,
    score_comfort,
)
from stereo_dandifier.importer import load_project_images
from stereo_dandifier.models import (
    DEFAULT_CAPTION_FONT_FAMILY,
    DEFAULT_CAPTION_FONT_SIZE,
    ProjectImage,
    RenderSettings,
)
from stereo_dandifier.print_layout import (
    FALLBACK_PREVIEW_DPI,
    PageLayout,
    default_page_layout,
    page_layout_for_name,
)

SUPPORTED_IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.dng *.mpo *.tif *.tiff)"
MIN_CARD_EDITOR_DPI = FALLBACK_PREVIEW_DPI


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
        self._zoom = 0
        self._has_image = False

        self._scene.addItem(self._placeholder)
        self._scene.addItem(self._pixmap_item)
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
        self.setToolTip("Mouse wheel zooms. Drag pans. Double-click fits the image.")

    def set_image(self, image: Image.Image, reset_view: bool = False):
        pixmap = QPixmap.fromImage(ImageQt(image))
        self._pixmap_item.setPixmap(pixmap)
        self._placeholder.setVisible(False)
        self._has_image = True
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

        if reset_view or self._zoom == 0:
            self.fit_to_view()

    def set_placeholder(self, text: str):
        self._pixmap_item.setPixmap(QPixmap())
        self._placeholder.setPlainText(text)
        self._placeholder.setVisible(True)
        self._has_image = False
        self._zoom = 0
        self.resetTransform()

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom == 0:
            self.fit_to_view()


class StereoDandifierWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("StereoDandifier")
        self.resize(1360, 860)
        self.setAcceptDrops(True)

        self.images: list[ProjectImage] = []
        self.current_index: int | None = None
        self._updating_controls = False
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

        self.setStatusBar(QStatusBar())
        self._set_comfort("No image loaded")

    def _build_actions(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        self.import_action = QAction("Import Images", self)
        self.import_action.triggered.connect(self.import_images)

        self.export_action = QAction("Export PDF", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.export_card)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)

        file_menu.addAction(self.import_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    def _build_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(self.import_action)
        toolbar.addAction(self.export_action)

        self.comfort_label = QLabel()
        self.comfort_label.setObjectName("comfortLabel")
        toolbar.addSeparator()
        toolbar.addWidget(self.comfort_label)

    def _build_library(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Thumbnails")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.library = QListWidget()
        self.library.setIconSize(QSize(96, 64))
        self.library.currentItemChanged.connect(self._select_library_item)
        self.library.itemChanged.connect(self._library_item_changed)
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
        self.swap_eyes = QCheckBox("Swap eyes for cross-eyed preview")
        self.swap_eyes.toggled.connect(self._controls_changed)
        self.convergence = self._make_slider(-40, 40, 0)
        image_layout.addRow(self.swap_eyes)
        image_layout.addRow("Convergence", self.convergence)
        auto_rectify = QPushButton("Auto Rectify")
        auto_rectify.setEnabled(False)
        auto_rectify.setToolTip("Planned for the next stereo correction milestone.")
        image_layout.addRow(auto_rectify)
        layout.addWidget(self.image_group)

        self.card_group = QGroupBox("Card")
        card_layout = QFormLayout(self.card_group)
        self.layout_template = QComboBox()
        self.layout_template.addItems(CARD_FORMATS.keys())
        for index, name in enumerate(CARD_FORMATS):
            self.layout_template.setItemData(
                index,
                format_particulars(name),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.layout_template.currentTextChanged.connect(self._layout_template_changed)
        self.caption = QTextEdit()
        self.caption.setAcceptRichText(True)
        self.caption.setPlaceholderText("Caption")
        self.caption.setObjectName("captionEditor")
        self.caption.setFixedHeight(104)
        self.caption.textChanged.connect(self._controls_changed)
        self.caption_position = QComboBox()
        self.caption_position.addItems(["Both images", "Left image", "Right image"])
        self.caption_position.currentTextChanged.connect(self._controls_changed)
        self.caption_font_family = QFontComboBox()
        self.caption_font_family.setCurrentFont(QFont(DEFAULT_CAPTION_FONT_FAMILY))
        self.caption_font_family.currentFontChanged.connect(self._caption_font_changed)
        self.caption_font_size = QSpinBox()
        self.caption_font_size.setRange(6, 36)
        self.caption_font_size.setValue(DEFAULT_CAPTION_FONT_SIZE)
        self.caption_font_size.valueChanged.connect(self._caption_format_changed)
        self.caption_bold = make_editor_button("B", "Bold", checked=False)
        self.caption_bold.toggled.connect(self._caption_format_changed)
        self.caption_italic = make_editor_button("I", "Italic", checked=False)
        self.caption_italic.toggled.connect(self._caption_format_changed)
        self.caption_align_left = make_editor_button(
            "align-left", "Align left", checked=False
        )
        self.caption_align_center = make_editor_button(
            "align-center", "Align center", checked=True
        )
        self.caption_align_right = make_editor_button(
            "align-right", "Align right", checked=False
        )
        self.caption_alignment_buttons = {
            "Left": self.caption_align_left,
            "Center": self.caption_align_center,
            "Right": self.caption_align_right,
        }
        for justification, button in self.caption_alignment_buttons.items():
            button.clicked.connect(
                lambda _checked=False, value=justification: (
                    self._caption_justification_changed(value)
                )
            )
        self.caption_style_bar = editor_button_bar(
            [self.caption_bold, self.caption_italic]
        )
        self.caption_alignment_bar = editor_button_bar(
            [
                self.caption_align_left,
                self.caption_align_center,
                self.caption_align_right,
            ]
        )
        self.caption_toolbar = caption_editor_toolbar(
            self.caption_font_family,
            self.caption_font_size,
            self.caption_bold,
            self.caption_italic,
            self.caption_align_left,
            self.caption_align_center,
            self.caption_align_right,
        )
        self.layout_info = QLabel()
        self.layout_info.setObjectName("infoBox")
        self.layout_info.setWordWrap(True)
        self.card_info = QLabel("No thumbnail selected")
        self.card_info.setObjectName("infoBox")
        self.card_info.setWordWrap(True)
        self._update_layout_info(self.layout_template.currentText())
        self._update_card_info()
        card_layout.addRow("Layout", self.layout_template)
        card_layout.addRow(self.layout_info)
        card_layout.addRow(self.card_info)
        card_layout.addRow("Caption placement", self.caption_position)
        card_layout.addRow(self.caption_toolbar)
        card_layout.addRow("Caption", self.caption)
        layout.addWidget(self.card_group)

        self.style_group = QGroupBox("Style")
        style_layout = QFormLayout(self.style_group)
        self.tone_mode = QComboBox()
        self.tone_mode.addItems(["Colour", "Black and White", "Sepia"])
        self.tone_mode.currentTextChanged.connect(self._tone_mode_changed)
        self.brightness = self._make_slider(-50, 50, 0)
        self.contrast = self._make_slider(-50, 50, 0)
        self.saturation_label, self.saturation = self._add_slider_row(
            style_layout, "Saturation", -50, 50, 0
        )
        self.sepia_strength_label, self.sepia_strength = self._add_slider_row(
            style_layout, "Sepia Strength", 0, 100, 45
        )
        style_layout.insertRow(0, "Mode", self.tone_mode)
        style_layout.insertRow(1, "Brightness", self.brightness)
        style_layout.insertRow(2, "Contrast", self.contrast)
        self._update_tone_controls(self.tone_mode.currentText())
        layout.addWidget(self.style_group)
        self._set_card_controls_enabled(False)

        layout.addStretch(1)
        return panel

    def _make_slider(self, minimum: int, maximum: int, value: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(self._controls_changed)
        return slider

    def _add_slider_row(
        self,
        layout: QFormLayout,
        label_text: str,
        minimum: int,
        maximum: int,
        value: int,
    ) -> tuple[QLabel, QSlider]:
        label = QLabel(label_text)
        slider = self._make_slider(minimum, maximum, value)
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
            QGraphicsView#preview {
                background: #ebe6dc;
                border: 1px solid #d0c7b8;
                border-radius: 8px;
                color: #71685d;
            }
            QLabel#comfortLabel {
                padding: 4px 10px;
                border-radius: 12px;
                background: #d8e7e0;
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
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
        )
        item.setCheckState(
            Qt.CheckState.Checked
            if project_image.selected_for_export
            else Qt.CheckState.Unchecked
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
            self._load_controls()
            self._refresh_previews(reset_view=True)
            return

        image_index = current.data(Qt.ItemDataRole.UserRole)
        if image_index is None:
            self.current_index = None
            self._load_controls()
            self._refresh_previews(reset_view=True)
            return

        self._select_image(image_index)

    def _library_item_changed(self, item: QListWidgetItem):
        image_index = item.data(Qt.ItemDataRole.UserRole)
        if image_index is None:
            return

        self.images[image_index].selected_for_export = (
            item.checkState() == Qt.CheckState.Checked
        )
        self.export_action.setEnabled(bool(self.selected_project_images()))
        if image_index == self.current_index:
            self._update_card_info()

    def _select_image(self, index: int):
        if index < 0 or index >= len(self.images):
            return

        self.current_index = index
        self.card_view.fit_to_view()

        self._load_controls()
        self._refresh_previews(reset_view=True)
        self.statusBar().showMessage(f"Loaded: {self.current_image.display_name}")

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
        self.layout_template.setCurrentText(settings.layout_template)
        self._update_layout_info(settings.layout_template)
        self.tone_mode.setCurrentText(settings.tone_mode)
        if settings.caption_html:
            self.caption.setHtml(settings.caption_html)
        else:
            self.caption.clear()
        caption_format = self.caption.currentCharFormat()
        self.caption_position.setCurrentText(settings.caption_position)
        self.caption_font_family.setCurrentFont(
            QFont(caption_font_family_from_qt_format(caption_format))
        )
        self.caption_font_size.setValue(
            caption_font_size_from_qt_format(caption_format)
        )
        self.caption_bold.setChecked(caption_format.font().bold())
        self.caption_italic.setChecked(caption_format.font().italic())
        self._set_caption_alignment_button(
            caption_justification_from_qt_alignment(self.caption.alignment())
        )
        self.swap_eyes.setChecked(settings.swap_eyes)
        self.brightness.setValue(settings.brightness)
        self.contrast.setValue(settings.contrast)
        self.saturation.setValue(settings.saturation)
        self.sepia_strength.setValue(settings.sepia_strength)
        self.convergence.setValue(settings.convergence)
        self._update_tone_controls(settings.tone_mode)
        self._updating_controls = False
        self._update_card_info()

    def _tone_mode_changed(self, mode: str):
        if self._updating_controls:
            self._update_tone_controls(mode)
            return
        defaults = {
            "Colour": {
                "brightness": 0,
                "contrast": 4,
                "saturation": 8,
                "sepia_strength": 45,
            },
            "Black and White": {
                "brightness": 0,
                "contrast": 16,
                "saturation": 0,
                "sepia_strength": 45,
            },
            "Sepia": {
                "brightness": 2,
                "contrast": 8,
                "saturation": 0,
                "sepia_strength": 55,
            },
        }
        self._updating_controls = True
        self.brightness.setValue(defaults[mode]["brightness"])
        self.contrast.setValue(defaults[mode]["contrast"])
        self.saturation.setValue(defaults[mode]["saturation"])
        self.sepia_strength.setValue(defaults[mode]["sepia_strength"])
        self._update_tone_controls(mode)
        self._updating_controls = False
        self._controls_changed()

    def _update_tone_controls(self, mode: str):
        colour_mode = mode == "Colour"
        sepia_mode = mode == "Sepia"
        self.saturation_label.setVisible(colour_mode)
        self.saturation.setVisible(colour_mode)
        self.sepia_strength_label.setVisible(sepia_mode)
        self.sepia_strength.setVisible(sepia_mode)

    def _layout_template_changed(self, name: str):
        if self._updating_controls:
            self._update_layout_info(name)
            return
        self._update_layout_info(name)
        self._controls_changed()

    def _update_layout_info(self, name: str):
        particulars = format_particulars(name)
        self.layout_info.setText(particulars)
        self.layout_template.setToolTip(particulars)

    def _caption_format_changed(self, *_args):
        if self._updating_controls:
            return

        text_format = QTextCharFormat()
        text_format.setFontFamilies([self.caption_font_family.currentFont().family()])
        text_format.setFontPointSize(self.caption_font_size.value())
        text_format.setFontWeight(
            QFont.Weight.Bold if self.caption_bold.isChecked() else QFont.Weight.Normal
        )
        text_format.setFontItalic(self.caption_italic.isChecked())
        self.caption.mergeCurrentCharFormat(text_format)
        self._controls_changed()

    def _caption_font_changed(self, font: QFont):
        if self._updating_controls:
            return
        self._caption_format_changed()

    def _caption_justification_changed(self, justification: str):
        if self._updating_controls:
            return

        self._set_caption_alignment_button(justification)
        self.caption.setAlignment(qt_alignment_from_caption(justification))
        self._controls_changed()

    def _set_caption_alignment_button(self, justification: str):
        for name, button in self.caption_alignment_buttons.items():
            button.setChecked(name == justification)

    def _controls_changed(self, *_args):
        if self._updating_controls:
            return

        current = self.current_image
        if current is None:
            return

        current.settings = RenderSettings(
            layout_template=self.layout_template.currentText(),
            tone_mode=self.tone_mode.currentText(),
            caption_html=caption_html_from_editor(self.caption),
            caption_position=self.caption_position.currentText(),
            swap_eyes=self.swap_eyes.isChecked(),
            brightness=self.brightness.value(),
            contrast=self.contrast.value(),
            saturation=self.saturation.value(),
            sepia_strength=self.sepia_strength.value(),
            convergence=self.convergence.value(),
        )
        self._refresh_previews()

    def _refresh_previews(self, reset_view: bool = False):
        self.export_action.setEnabled(bool(self.selected_project_images()))
        self._update_card_info()
        current = self.current_image
        if current is None:
            self.card_view.set_placeholder("Select a thumbnail to edit its card")
            self._set_comfort("No thumbnail selected")
            return

        card = render_project_card(current, dpi=editor_dpi_for_image(current))
        self.card_view.set_image(card, reset_view=reset_view)
        self._set_comfort(score_comfort(current.source, current.settings))

    def selected_project_images(self) -> list[ProjectImage]:
        return [image for image in self.images if image.selected_for_export]

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
        card_w, card_h = spec["card_mm"]
        image_w, image_h = spec["image_mm"]
        export_state = (
            "Included in export"
            if current.selected_for_export
            else "Not included in export"
        )
        self.card_info.setText(
            f"{current.display_name}\n"
            f"Source: {current.source.width} x {current.source.height} px\n"
            f"Card: {card_w:g} x {card_h:g} mm; images: {image_w:g} x {image_h:g} mm\n"
            f"{export_state}"
        )

    def _set_comfort(self, text: str):
        self.comfort_label.setText(f"Comfort: {text}")
        self.statusBar().showMessage(text)

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


def editor_button_bar(buttons: list[QToolButton]) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return widget


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
