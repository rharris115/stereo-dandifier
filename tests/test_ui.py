import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from stereo_dandifier.ui import (
    StereoDandifierWindow,
    ZoomableImageView,
    left_thumbnail_image,
)


def test_zoomable_image_view_accepts_full_size_image():
    app = QApplication.instance() or QApplication([])
    view = ZoomableImageView("Preview")
    view.resize(400, 300)

    view.set_image(Image.new("RGB", (800, 300), (120, 130, 140)), reset_view=True)

    assert app is not None
    assert view._has_image
    assert not view._pixmap_item.pixmap().isNull()


def test_inspector_exposes_paper_size_and_dpi():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert window.paper_choice.currentText() == window.page_layout.name
    assert window.paper_choice.isEnabled()
    assert window.paper_size_label.text()
    assert window.paper_dpi_label.text() == f"{window.page_layout.dpi} dpi"


def test_library_uses_checkboxes_and_file_separators(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(first)
    Image.new("RGB", (8, 4), (0, 0, 255)).save(second)
    window = StereoDandifierWindow()

    window._import_paths([first, second])

    assert app is not None
    assert window.library.count() == 3
    assert window.library.item(0).text() == "Card"
    assert window.library.item(1).text() == "second.png"
    assert window.library.item(2).text() == "Card"
    assert window.library.item(0).checkState() == Qt.CheckState.Checked
    assert window.library.item(1).flags() == Qt.ItemFlag.NoItemFlags
    assert window.library.item(2).checkState() == Qt.CheckState.Checked


def test_card_editor_follows_single_thumbnail_selection(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(first)
    Image.new("RGB", (8, 4), (0, 0, 255)).save(second)
    window = StereoDandifierWindow()

    window._import_paths([first, second])
    window.library.setCurrentRow(2)

    assert app is not None
    assert window.current_image.path == second
    assert "second.png" in window.card_info.text()
    assert window.card_view._has_image


def test_left_thumbnail_image_uses_left_half():
    image = Image.new("RGB", (4, 2), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, 2, 2))

    thumbnail = left_thumbnail_image(image)

    assert thumbnail.size == (2, 2)
    assert thumbnail.getpixel((0, 0)) == (255, 0, 0)
