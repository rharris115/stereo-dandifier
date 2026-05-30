import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def cleanup_qt_widgets():
    yield
    app = QApplication.instance()
    if app is None:
        return

    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
