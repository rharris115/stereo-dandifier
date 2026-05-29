from pathlib import Path
import sys

from PIL import Image
from PIL.ImageQt import ImageQt

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


class StereoDandifierWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("StereoDandifier")
        self.resize(1200, 800)

        self.current_image = None

        self._build_ui()

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.open_button = QPushButton("Open Stereo Image")
        self.open_button.clicked.connect(self.open_image)
        layout.addWidget(self.open_button)

        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.setStatusBar(QStatusBar())

        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        open_action = QAction("Open Image", self)
        open_action.triggered.connect(self.open_image)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)

        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Stereo Image",
            "",
            "Images (*.jpg *.jpeg *.png *.dng)",
        )

        if not file_path:
            return

        image = Image.open(file_path)
        image = make_cross_eyed(image=image)

        image.thumbnail((1000, 700))

        qt_image = ImageQt(image)
        pixmap = QPixmap.fromImage(qt_image)

        self.image_label.setPixmap(pixmap)

        self.current_image = file_path

        self.statusBar().showMessage(f"Loaded: {Path(file_path).name}")


def make_cross_eyed(image: Image.Image) -> Image.Image:
    width, height = image.size
    midpoint = width // 2

    left = image.crop((0, 0, midpoint, height))
    right = image.crop((midpoint, 0, width, height))

    output = Image.new(image.mode, image.size)
    output.paste(right, (0, 0))
    output.paste(left, (midpoint, 0))

    return output


def main():
    app = QApplication(sys.argv)

    window = StereoDandifierWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
