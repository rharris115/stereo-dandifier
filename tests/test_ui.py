import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication

from stereo_dandifier.ui import (
    CaptionDialog,
    ExportDialog,
    SourceWindowView,
    StereoDandifierWindow,
    WindowDialog,
    ZoomableImageView,
    editor_dpi_for_image,
    export_dpi_for_images,
    export_page_layouts,
    left_thumbnail_image,
    resize_crop_box_for_handle,
    window_shape_path,
    window_shapes_for_layout,
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
        settings=RenderSettings(layout_template="holmes_standard"),
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
        settings=RenderSettings(layout_template="holmes_standard"),
    )

    assert editor_dpi_for_image(project_image) == 2177


def test_export_dpi_for_images_uses_selected_originals(tmp_path):
    small = ProjectImage(
        path=tmp_path / "small.png",
        source=Image.new("RGB", (1000, 500), (120, 130, 140)),
        settings=RenderSettings(layout_template="holmes_standard"),
    )
    large = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template="holmes_standard"),
    )

    assert export_dpi_for_images([small, large]) == 2177


def test_caption_placement_updates_current_card_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings(caption_position="Left image"))

    dialog.caption_under_left.setChecked(False)
    dialog.caption_under_right.setChecked(True)

    assert app is not None
    assert dialog.caption_position == "Right image"


def test_caption_placement_controls_are_below_editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings())

    layout = dialog.layout()

    assert app is not None
    assert layout.indexOf(dialog.caption_placement_row) > layout.indexOf(dialog.editor)


def test_caption_typography_updates_current_card_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings())

    dialog.editor.setPlainText("First wicket")
    dialog.editor.selectAll()
    dialog.font_family.setCurrentFont(QFont("Georgia"))
    dialog.font_size.setValue(18)
    dialog.bold.setChecked(True)
    dialog.italic.setChecked(True)
    dialog.align_right.click()

    assert app is not None
    caption_html = dialog.caption_html
    assert "Georgia" in caption_html
    assert "18pt" in caption_html
    assert "font-weight" in caption_html
    assert "font-style:italic" in caption_html
    assert 'align="right"' in caption_html


def test_caption_editor_can_style_substrings_with_qt_document(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings())

    dialog.editor.setPlainText("First wicket")
    cursor = dialog.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    dialog.editor.setTextCursor(cursor)
    dialog.bold.setChecked(True)

    assert app is not None
    fragments = text_fragments(dialog.caption_html)
    assert [text for text, _format in fragments] == ["First", " wicket"]
    assert fragments[0][1].font().bold()
    assert not fragments[1][1].font().bold()


def test_caption_alignment_uses_icon_buttons(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings())

    dialog.editor.setPlainText("First wicket")
    dialog.align_left.click()

    assert app is not None
    assert dialog.align_left.isChecked()
    assert not dialog.align_center.isChecked()
    assert "First wicket" in dialog.caption_html


def test_properties_pane_does_not_include_caption_editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert not hasattr(window, "caption")
    assert not hasattr(window, "caption_position")
    assert not hasattr(window, "window_editor")


def test_card_preview_gets_caption_hotspot(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])

    assert app is not None
    assert window.card_view._hotspots


def test_card_preview_has_separate_window_and_caption_hotspots(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])

    callbacks = [callback for _bounds, callback, _tooltip in window.card_view._hotspots]
    assert app is not None
    assert callbacks.count(window.edit_window) == 2
    assert callbacks.count(window.edit_caption) == 2


def test_card_preview_hotspots_have_editing_tooltips(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(path)
    window = StereoDandifierWindow()

    window._import_paths([path])

    tooltips = [tooltip for _bounds, _callback, tooltip in window.card_view._hotspots]
    assert app is not None
    assert any("stereo window" in tooltip for tooltip in tooltips)
    assert any("caption" in tooltip for tooltip in tooltips)


def test_window_dialog_exposes_shape_size_and_crop_controls():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(
            layout_template="owl_recommended",
            window_shape="Circle",
            image_area_percent=75,
            crop_x_percent=-20,
            crop_y_percent=35,
        ),
        preview_image=Image.new("RGB", (100, 80), (120, 130, 140)),
    )

    dialog.shape_buttons["Arched top"].click()
    dialog._crop_changed_from_view(50, 15, -10)

    assert app is not None
    assert dialog.window_shape == "Arched top"
    assert dialog.image_area_percent == 50
    assert dialog.crop_x_percent == 15
    assert dialog.crop_y_percent == -10
    assert dialog.preview is not None
    assert "Oval" in dialog.shape_buttons
    assert "Circle" not in dialog.shape_buttons


def test_window_dialog_disables_round_corners_for_circle_shape():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(
            layout_template="holmes_standard",
            window_shape="Rectangle",
            window_round_corners=True,
        ),
        preview_image=Image.new("RGB", (100, 80), (120, 130, 140)),
    )

    dialog.shape_buttons["Circle"].click()

    assert app is not None
    assert not dialog.round_corners.isEnabled()
    assert not dialog.window_round_corners


def test_window_dialog_uses_oval_for_rectangular_layouts():
    settings = RenderSettings(layout_template="owl_recommended")

    assert window_shapes_for_layout(settings) == ("Rectangle", "Oval", "Arched top")


def test_window_dialog_keeps_round_corners_for_rectangle_shape():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(window_shape="Rectangle", window_round_corners=True),
        preview_image=Image.new("RGB", (100, 80), (120, 130, 140)),
    )

    assert app is not None
    assert dialog.round_corners.isEnabled()
    assert dialog.window_round_corners


def test_window_dialog_updates_position_from_drag_preview():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(image_area_percent=50),
        preview_image=Image.new("RGB", (100, 100), (120, 130, 140)),
    )

    dialog._crop_changed_from_view(50, 100, -100)

    assert app is not None
    assert dialog.crop_x_percent == 100
    assert dialog.crop_y_percent == -100
    assert dialog.preview._crop_box() == (43, 0, 100, 50)


def test_resize_handle_keeps_opposite_side_fixed_and_preserves_aspect():
    resized = resize_crop_box_for_handle(
        (100, 100),
        (25, 25, 75, 75),
        (1, 1),
        "top",
        50,
        10,
    )

    assert resized == (18, 10, 82, 75)


def test_resize_handle_updates_dialog_window_size_from_crop():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(image_area_percent=50),
        preview_image=Image.new("RGB", (100, 100), (120, 130, 140)),
    )

    dialog.preview._emit_crop_box_changed((18, 10, 82, 75))

    assert app is not None
    assert dialog.image_area_percent == 65


def test_source_window_view_greys_area_outside_window():
    app = QApplication.instance() or QApplication([])
    view = SourceWindowView(
        Image.new("RGB", (100, 100), (120, 130, 140)),
        RenderSettings(image_area_percent=50),
    )

    assert app is not None
    assert view._window_item.path().boundingRect() == QRectF(22, 25, 57, 50)
    assert view._shade_item.path().contains(QRectF(0, 0, 10, 10).center())


def test_source_window_view_reflects_selected_window_shape():
    app = QApplication.instance() or QApplication([])
    view = SourceWindowView(
        Image.new("RGB", (100, 100), (120, 130, 140)),
        RenderSettings(image_area_percent=50, window_shape="Circle"),
    )

    assert app is not None
    assert not view._window_path().contains(QRectF(25, 25, 1, 1).center())
    assert view._window_path().contains(QRectF(50, 50, 1, 1).center())


def test_window_shape_path_supports_arched_top():
    path = window_shape_path(QRectF(10, 10, 40, 60), "Arched top")

    assert not path.contains(QRectF(10, 10, 1, 1).center())
    assert path.contains(QRectF(30, 10, 1, 1).center())
    assert path.contains(QRectF(10, 69, 1, 1).center())
    assert not path.contains(QRectF(10, 12, 1, 1).center())


def test_window_shape_path_supports_rounded_rectangle():
    path = window_shape_path(QRectF(10, 10, 40, 60), "Rectangle", round_corners=True)

    assert not path.contains(QRectF(10, 10, 1, 1).center())
    assert path.contains(QRectF(30, 10, 1, 1).center())


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
