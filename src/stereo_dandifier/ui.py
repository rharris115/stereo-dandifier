from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
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
from stereo_dandifier.models import ProjectImage, RenderSettings
from stereo_dandifier.print_layout import default_page_layout, page_layout_for_name

SUPPORTED_IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.dng *.mpo *.tif *.tiff)"


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
        self.page_layout = default_page_layout()

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
        self.paper_label = QLabel(f"Paper: {self.page_layout.name}")
        self.paper_label.setObjectName("paperLabel")
        self.paper_label.setToolTip(self.page_layout.source)
        toolbar.addSeparator()
        toolbar.addWidget(self.comfort_label)
        toolbar.addWidget(self.paper_label)

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

        title = QLabel("Inspector")
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

        paper_group = QGroupBox("Paper")
        paper_layout = QFormLayout(paper_group)
        self.paper_choice = QComboBox()
        self.paper_choice.addItems(["A4", "Letter"])
        if self.page_layout.name not in {"A4", "Letter"}:
            self.paper_choice.addItem(self.page_layout.name)
        self.paper_choice.setCurrentText(self.page_layout.name)
        self.paper_choice.currentTextChanged.connect(self._paper_choice_changed)
        self.paper_size_label = QLabel()
        self.paper_dpi_label = QLabel()
        self.paper_source_label = QLabel()
        self.paper_source_label.setWordWrap(True)
        self.paper_source_label.setObjectName("hintText")
        paper_layout.addRow("Size", self.paper_choice)
        paper_layout.addRow("Dimensions", self.paper_size_label)
        paper_layout.addRow("DPI", self.paper_dpi_label)
        paper_layout.addRow(self.paper_source_label)
        self._update_paper_controls()
        layout.addWidget(paper_group)

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
        self.caption = QLineEdit()
        self.caption.setPlaceholderText("Caption")
        self.caption.textChanged.connect(self._controls_changed)
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
            QListWidget, QLineEdit, QComboBox {
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
            QLabel#paperLabel {
                padding: 4px 10px;
                border-radius: 12px;
                background: #edf2f8;
                color: #314960;
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
        self.caption.setText(settings.caption)
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

    def _paper_choice_changed(self, name: str):
        if self._updating_controls:
            return
        self.page_layout = page_layout_for_name(name)
        self._update_paper_controls()
        self._refresh_previews(reset_view=True)

    def _update_paper_controls(self):
        width_mm, height_mm = self.page_layout.size_mm
        self.paper_label.setText(f"Paper: {self.page_layout.name}")
        self.paper_label.setToolTip(self.page_layout.source)
        self.paper_size_label.setText(f"{width_mm:g} x {height_mm:g} mm")
        self.paper_dpi_label.setText(f"{self.page_layout.dpi} dpi")
        self.paper_source_label.setText(self.page_layout.source)

    def _controls_changed(self, *_args):
        if self._updating_controls:
            return

        current = self.current_image
        if current is None:
            return

        current.settings = RenderSettings(
            layout_template=self.layout_template.currentText(),
            tone_mode=self.tone_mode.currentText(),
            caption=self.caption.text(),
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

        card = render_project_card(current, dpi=self.page_layout.dpi)
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

        export_dpi = max(
            export_dpi_for_source(
                project_image.source,
                project_image.settings,
                minimum_dpi=self.page_layout.dpi,
            )
            for project_image in selected_images
        )
        cards = [
            render_project_card(project_image, dpi=export_dpi)
            for project_image in selected_images
        ]
        pages = render_print_pages(cards, self.page_layout, dpi=export_dpi)
        save_pdf_pages(pages, file_path, dpi=export_dpi)
        self.statusBar().showMessage(
            f"Exported: {Path(file_path).name} at {export_dpi} dpi"
        )


def left_thumbnail_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width <= 1:
        return image.copy()
    return image.crop((0, 0, width // 2, height))
