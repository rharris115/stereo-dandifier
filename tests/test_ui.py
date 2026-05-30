import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication

from stereo_dandifier.ui import (
    ExportDialog,
    StereoDandifierWindow,
    ZoomableImageView,
    editor_dpi_for_image,
    export_dpi_for_images,
    export_page_layouts,
    left_thumbnail_image,
)
from stereo_dandifier.models import ProjectImage, RenderSettings
from stereo_dandifier.print_layout import default_page_layout, page_layout_for_name


def test_zoomable_image_view_accepts_full_size_image():
    app = QApplication.instance() or QApplication([])
    view = ZoomableImageView("Preview")
    view.resize(400, 300)

    view.set_image(Image.new("RGB", (800, 300), (120, 130, 140)), reset_view=True)

    assert app is not None
    assert view._has_image
    assert not view._pixmap_item.pixmap().isNull()


def test_main_editor_defers_paper_choices_to_export():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert not hasattr(window, "paper_choice")
    assert not hasattr(window, "paper_label")


def test_export_dialog_hides_render_dpi_detail(tmp_path):
    app = QApplication.instance() or QApplication([])
    default_layout = default_page_layout()
    project_image = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template="Holmes (standard)"),
    )
    dialog = ExportDialog(default_layout, [project_image])

    assert app is not None
    assert dialog.paper_choice.currentText() == default_layout.name
    assert dialog.paper_size_label.text()
    assert not hasattr(dialog, "image_dpi_label")
    assert "highest useful resolution" in dialog.paper_source_label.text()
    assert "dpi" not in dialog.paper_source_label.text().lower()


def test_export_page_layouts_always_include_a4_and_letter():
    layouts = export_page_layouts(page_layout_for_name("A4"))

    assert {"A4", "Letter"}.issubset(layouts)


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


def test_editor_dpi_uses_source_detail_for_zoomable_card_preview(tmp_path):
    project_image = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template="Holmes (standard)"),
    )

    assert editor_dpi_for_image(project_image) == 2177


def test_export_dpi_for_images_uses_selected_originals(tmp_path):
    small = ProjectImage(
        path=tmp_path / "small.png",
        source=Image.new("RGB", (1000, 500), (120, 130, 140)),
        settings=RenderSettings(layout_template="Holmes (standard)"),
    )
    large = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template="Holmes (standard)"),
    )

    assert export_dpi_for_images([small, large]) == 2177


def test_caption_placement_updates_current_card_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])
    window.caption_position.setCurrentText("Right image")

    assert app is not None
    assert window.current_image.settings.caption_position == "Right image"


def test_caption_typography_updates_current_card_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])
    window.caption.setPlainText("First wicket")
    window.caption.selectAll()
    window.caption_font_family.setCurrentFont(QFont("Georgia"))
    window.caption_font_size.setValue(18)
    window.caption_bold.setChecked(True)
    window.caption_italic.setChecked(True)
    window.caption_align_right.click()

    assert app is not None
    caption_html = window.current_image.settings.caption_html
    assert "Georgia" in caption_html
    assert "18pt" in caption_html
    assert "font-weight" in caption_html
    assert "font-style:italic" in caption_html
    assert 'align="right"' in caption_html


def test_caption_editor_can_style_substrings_with_qt_document(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])
    window.caption.setPlainText("First wicket")
    cursor = window.caption.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    window.caption.setTextCursor(cursor)
    window.caption_bold.setChecked(True)

    assert app is not None
    fragments = text_fragments(window.current_image.settings.caption_html)
    assert [text for text, _format in fragments] == ["First", " wicket"]
    assert fragments[0][1].font().bold()
    assert not fragments[1][1].font().bold()


def test_caption_alignment_uses_icon_buttons(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])
    window.caption.setPlainText("First wicket")
    window.caption_align_left.click()

    assert app is not None
    assert window.caption_align_left.isChecked()
    assert not window.caption_align_center.isChecked()
    assert "First wicket" in window.current_image.settings.caption_html


def text_fragments(caption_html: str):
    document = QTextDocument()
    document.setHtml(caption_html)
    fragments = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.text():
                fragments.append((fragment.text(), fragment.charFormat()))
            iterator += 1
        block = block.next()
    return fragments


def test_left_thumbnail_image_uses_left_half():
    image = Image.new("RGB", (4, 2), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, 2, 2))

    thumbnail = left_thumbnail_image(image)

    assert thumbnail.size == (2, 2)
    assert thumbnail.getpixel((0, 0)) == (255, 0, 0)
