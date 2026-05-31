import os
import json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication, QDialog, QToolBar, QToolButton

from stereo_dandifier.ui import (
    CaptionDialog,
    ExportDialog,
    SourceWindowView,
    StereoDandifierWindow,
    WindowDialog,
    ZoomableImageView,
    comfort_state_for_text,
    editor_dpi_for_image,
    export_dpi_for_images,
    export_page_layouts,
    left_thumbnail_image,
    resize_crop_box_for_handle,
    rounded_corner_radius,
    window_shape_path,
    window_shapes_for_layout,
)
from stereo_dandifier.models import (
    CaptionPosition,
    CardLayoutName,
    ProjectImage,
    RenderSettings,
    WindowShape,
)
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


def test_thumbnail_pane_owns_import_and_remove_buttons():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    toolbar_actions = [
        action.text()
        for toolbar in window.findChildren(QToolBar)
        for action in toolbar.actions()
    ]

    assert app is not None
    assert "Import Images" not in toolbar_actions
    assert window.add_thumbnail_button.text() == "+"
    assert window.remove_thumbnail_button.text() == "-"
    assert window.save_card_action.text() == "Save Current Card Data"
    assert not window.save_card_action.isEnabled()


def test_comfort_report_lives_in_bottom_status_bar():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    toolbar_widgets = [
        toolbar.widgetForAction(action)
        for toolbar in window.findChildren(QToolBar)
        for action in toolbar.actions()
    ]

    assert app is not None
    assert window.statusBar() is not None
    assert window.comfort_label not in toolbar_widgets
    assert window.comfort_label.parent() is window.statusBar()
    assert window.auto_rectify.text() == "Stereo Rectify"


def test_comfort_state_controls_preview_border_state():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    window._set_comfort("Poor - vertical alignment off by 4.0px")

    assert app is not None
    assert window.card_view.property("comfortState") == "poor"


def test_comfort_state_for_text_maps_score_prefixes():
    assert comfort_state_for_text("Excellent") == "excellent"
    assert comfort_state_for_text("Good - check stereo split") == "good"
    assert comfort_state_for_text("Borderline - portrait source") == "borderline"
    assert comfort_state_for_text("Poor - vertical alignment off by 4.0px") == "poor"
    assert comfort_state_for_text("No thumbnail selected") == "neutral"


def test_style_sliders_do_not_track_every_drag_tick():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert not window.brightness.hasTracking()
    assert not window.contrast.hasTracking()
    assert not window.saturation.hasTracking()
    assert not window.sepia_strength.hasTracking()


def test_style_sliders_have_expanded_adjustment_ranges():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert (window.brightness.minimum(), window.brightness.maximum()) == (-100, 300)
    assert (window.contrast.minimum(), window.contrast.maximum()) == (-100, 100)
    assert (window.saturation.minimum(), window.saturation.maximum()) == (-100, 100)
    assert (window.sepia_strength.minimum(), window.sepia_strength.maximum()) == (
        0,
        100,
    )


def test_style_slider_changes_do_not_recalculate_comfort(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "first.png"
    Image.new("RGB", (80, 40), (120, 130, 140)).save(path)
    window = StereoDandifierWindow()
    calls = []

    def fake_refresh(*, reset_view=False, recalculate_comfort=True):
        calls.append((reset_view, recalculate_comfort))

    window._import_paths([path])
    monkeypatch.setattr(window, "_refresh_previews", fake_refresh)

    window.brightness.setValue(12)

    assert app is not None
    assert calls[-1] == (False, False)


def test_auto_improve_photo_button_is_explicit_and_updates_current_source(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "first.png"
    source = Image.new("RGB", (4, 1))
    source.putdata(
        [
            (20, 20, 20),
            (80, 80, 80),
            (120, 120, 120),
            (220, 220, 220),
        ]
    )
    source.save(path)
    window = StereoDandifierWindow()
    monkeypatch.setattr("stereo_dandifier.ui.score_comfort", lambda *_args: "Excellent")

    window._import_paths([path])
    before = [
        tuple(pixel) for pixel in np.asarray(window.current_image.source).reshape(-1, 3)
    ]
    window.auto_improve.click()
    after = [
        tuple(pixel) for pixel in np.asarray(window.current_image.source).reshape(-1, 3)
    ]

    assert app is not None
    assert window.auto_improve.text() == "Auto Improve Photo"
    assert before == [
        (20, 20, 20),
        (80, 80, 80),
        (120, 120, 120),
        (220, 220, 220),
    ]
    assert after[0] == (0, 0, 0)
    assert after[-1] == (255, 255, 255)
    assert window.current_image.source.size == (4, 1)


def test_export_dialog_hides_render_dpi_detail(tmp_path):
    app = QApplication.instance() or QApplication([])
    default_layout = default_page_layout()
    project_image = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD),
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


def test_library_uses_file_separators_without_export_checkboxes(tmp_path):
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
    assert not window.library.item(0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert window.library.item(1).flags() == Qt.ItemFlag.NoItemFlags
    assert not window.library.item(2).flags() & Qt.ItemFlag.ItemIsUserCheckable


def test_removing_thumbnail_removes_it_from_export_set(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(first)
    Image.new("RGB", (8, 4), (0, 0, 255)).save(second)
    window = StereoDandifierWindow()

    window._import_paths([first, second])
    window.library.setCurrentRow(0)
    window._remove_current_thumbnail()

    assert app is not None
    assert [image.path for image in window.selected_project_images()] == [second]
    assert window.library.count() == 1
    assert window.library.item(0).text() == "Card"
    assert window.current_image.path == second


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
    assert window.save_card_action.isEnabled()


def test_save_current_card_data_writes_json(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "card.png"
    output_path = tmp_path / "card-data"
    Image.new("RGB", (8, 4), (25, 50, 75)).save(image_path)
    window = StereoDandifierWindow()

    window._import_paths([image_path])
    monkeypatch.setattr(
        "stereo_dandifier.ui.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(output_path), "JSON document (*.json)"),
    )

    window.save_current_card_data()

    saved_path = output_path.with_suffix(".json")
    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert app is not None
    assert "source_path" not in payload
    assert payload["settings"]["layout_template"] == CardLayoutName.OWL_RECOMMENDED
    assert payload["source_image"]["media_type"] == "image/png"
    assert payload["source_image"]["data"]


def test_editor_dpi_uses_source_detail_for_zoomable_card_preview(tmp_path):
    project_image = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD),
    )

    assert editor_dpi_for_image(project_image) == 2177


def test_export_dpi_for_images_uses_selected_originals(tmp_path):
    small = ProjectImage(
        path=tmp_path / "small.png",
        source=Image.new("RGB", (1000, 500), (120, 130, 140)),
        settings=RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD),
    )
    large = ProjectImage(
        path=tmp_path / "large.png",
        source=Image.new("RGB", (12000, 6000), (120, 130, 140)),
        settings=RenderSettings(layout_template=CardLayoutName.HOLMES_STANDARD),
    )

    assert export_dpi_for_images([small, large]) == 2177


def test_caption_placement_updates_current_card_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = CaptionDialog(RenderSettings(caption_position=CaptionPosition.LEFT_IMAGE))

    dialog.caption_under_left.setChecked(False)
    dialog.caption_under_right.setChecked(True)

    assert app is not None
    assert dialog.caption_position == CaptionPosition.RIGHT_IMAGE


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
    assert window.cross_eyed_preview not in window.image_group.findChildren(QToolButton)


def test_cross_eyed_preview_control_lives_with_card_view():
    app = QApplication.instance() or QApplication([])
    window = StereoDandifierWindow()

    assert app is not None
    assert window.cross_eyed_preview.isCheckable()
    assert window.cross_eyed_preview.text() == "Cross-eyed preview"
    assert window.cross_eyed_preview.parentWidget() is not window.image_group


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


def test_window_editor_preview_uses_style_adjustments(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "card.png"
    image = Image.new("RGB", (8, 4), (50, 50, 50))
    image.save(path)
    window = StereoDandifierWindow()
    captured = {}

    class FakeWindowDialog:
        def __init__(self, settings, parent=None, preview_image=None):
            captured["preview_image"] = preview_image
            self.window_shape = settings.window_shape
            self.window_round_corners = settings.window_round_corners
            self.image_area_percent = settings.image_area_percent
            self.crop_x_percent = settings.crop_x_percent
            self.crop_y_percent = settings.crop_y_percent

        def exec(self):
            return QDialog.DialogCode.Rejected

    window._import_paths([path])
    window.current_image.settings.brightness = 100
    monkeypatch.setattr("stereo_dandifier.ui.WindowDialog", FakeWindowDialog)

    window.edit_window()

    assert app is not None
    assert captured["preview_image"].getpixel((0, 0)) == (100, 100, 100)


def test_window_dialog_exposes_shape_size_and_crop_controls():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(
            layout_template=CardLayoutName.OWL_RECOMMENDED,
            window_shape=WindowShape.CIRCLE,
            image_area_percent=75,
            crop_x_percent=-20,
            crop_y_percent=35,
        ),
        preview_image=Image.new("RGB", (100, 80), (120, 130, 140)),
    )

    dialog.shape_buttons[WindowShape.ARCHED_TOP].click()
    dialog._crop_changed_from_view(50, 15, -10)

    assert app is not None
    assert dialog.window_shape == WindowShape.ARCHED_TOP
    assert dialog.image_area_percent == 50
    assert dialog.crop_x_percent == 15
    assert dialog.crop_y_percent == -10
    assert dialog.preview is not None
    assert WindowShape.OVAL in dialog.shape_buttons
    assert WindowShape.CIRCLE not in dialog.shape_buttons


def test_window_dialog_disables_round_corners_for_circle_shape():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(
            layout_template=CardLayoutName.HOLMES_STANDARD,
            window_shape=WindowShape.RECTANGLE,
            window_round_corners=True,
        ),
        preview_image=Image.new("RGB", (100, 80), (120, 130, 140)),
    )

    dialog.shape_buttons[WindowShape.CIRCLE].click()

    assert app is not None
    assert not dialog.round_corners.isEnabled()
    assert not dialog.window_round_corners


def test_window_dialog_uses_oval_for_rectangular_layouts():
    settings = RenderSettings(layout_template=CardLayoutName.OWL_RECOMMENDED)

    assert window_shapes_for_layout(settings) == (
        WindowShape.RECTANGLE,
        WindowShape.OVAL,
        WindowShape.ARCHED_TOP,
    )


def test_window_dialog_keeps_round_corners_for_rectangle_shape():
    app = QApplication.instance() or QApplication([])
    dialog = WindowDialog(
        RenderSettings(window_shape=WindowShape.RECTANGLE, window_round_corners=True),
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
        RenderSettings(image_area_percent=50, window_shape=WindowShape.CIRCLE),
    )

    assert app is not None
    assert not view._window_path().contains(QRectF(25, 25, 1, 1).center())
    assert view._window_path().contains(QRectF(50, 50, 1, 1).center())


def test_window_shape_path_supports_arched_top():
    path = window_shape_path(QRectF(10, 10, 40, 60), WindowShape.ARCHED_TOP)

    assert not path.contains(QRectF(10, 10, 1, 1).center())
    assert path.contains(QRectF(30, 10, 1, 1).center())
    assert path.contains(QRectF(10, 69, 1, 1).center())
    assert not path.contains(QRectF(10, 12, 1, 1).center())


def test_window_shape_path_supports_rounded_rectangle():
    path = window_shape_path(
        QRectF(10, 10, 40, 60), WindowShape.RECTANGLE, round_corners=True
    )

    assert not path.contains(QPointF(10.1, 10.1))
    assert path.contains(QRectF(30, 10, 1, 1).center())


def test_rounded_corner_radius_uses_subtle_rounding():
    assert rounded_corner_radius(40, 60) == 1.6


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
