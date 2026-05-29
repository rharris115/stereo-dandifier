import sys

from PySide6.QtWidgets import QApplication

from stereo_dandifier.ui import StereoDandifierWindow


def main() -> int:
    app = QApplication(sys.argv)

    window = StereoDandifierWindow()
    window.show()

    return app.exec()
