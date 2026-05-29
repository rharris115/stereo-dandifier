import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from stereo_dandifier.ui import ZoomableImageView


def test_zoomable_image_view_accepts_full_size_image():
    app = QApplication.instance() or QApplication([])
    view = ZoomableImageView("Preview")
    view.resize(400, 300)

    view.set_image(Image.new("RGB", (800, 300), (120, 130, 140)), reset_view=True)

    assert app is not None
    assert view._has_image
    assert not view._pixmap_item.pixmap().isNull()
