"""Qt desktop GUI for TIFF Spot White."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .core import ConversionResult, LoadedImage, convert_image, default_output_path, generate_spot_mask, load_image


def supported_image_extensions() -> set[str]:
    Image.init()
    return {extension.lower() for extension in Image.registered_extensions()}


def image_file_filter() -> str:
    extensions = sorted(supported_image_extensions())
    patterns = " ".join(f"*{extension}" for extension in extensions)
    return f"Supported images ({patterns});;TIFF files (*.tif *.tiff);;All files (*)"


class Processor(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, input_path: Path, output_path: Path, action: str):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.action = action

    def run(self) -> None:
        try:
            self.finished_ok.emit(convert_image(self.input_path, self.output_path, self.action))
        except Exception as exc:
            self.failed.emit(str(exc))


class DropLabel(QLabel):
    file_dropped = Signal(Path)

    def __init__(self) -> None:
        super().__init__("Drop one image here or choose a file")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(360)
        self.setStyleSheet("QLabel { border: 1px solid #999; background: #202124; color: #ddd; }")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.file_dropped.emit(Path(urls[0].toLocalFile()))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TIFF Spot White")
        self.resize(900, 720)
        self.loaded: LoadedImage | None = None
        self.input_path: Path | None = None
        self.output_path: Path | None = None
        self.worker: Processor | None = None

        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        self.choose_button = QPushButton("Choose Image")
        self.choose_button.clicked.connect(self.choose_file)
        self.convert_button = QPushButton("Convert")
        self.convert_button.setEnabled(False)
        self.convert_button.clicked.connect(self.convert)
        top.addWidget(self.choose_button)
        top.addWidget(self.convert_button)
        top.addStretch()
        layout.addLayout(top)

        toggle_row = QHBoxLayout()
        self.original_radio = QRadioButton("Original preview")
        self.overlay_radio = QRadioButton("Spot overlay preview")
        self.original_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.original_radio)
        group.addButton(self.overlay_radio)
        self.original_radio.toggled.connect(self.refresh_preview)
        self.overlay_radio.toggled.connect(self.refresh_preview)
        toggle_row.addWidget(self.original_radio)
        toggle_row.addWidget(self.overlay_radio)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        self.preview = DropLabel()
        self.preview.file_dropped.connect(self.open_file)
        layout.addWidget(self.preview, 1)

        self.path_label = QLabel("Output: -")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMinimumHeight(140)
        layout.addWidget(self.messages)

        self.setCentralWidget(root)

    def log(self, lines: list[str] | str) -> None:
        if isinstance(lines, str):
            lines = [lines]
        self.messages.setPlainText("\n".join(lines))

    def choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose Image", "", image_file_filter())
        if filename:
            self.open_file(Path(filename))

    def open_file(self, path: Path) -> None:
        if path.suffix.lower() not in supported_image_extensions():
            self.log("Choose an image file supported by Pillow.")
            return
        try:
            loaded = load_image(path)
        except Exception as exc:
            self.log(f"Could not load image: {exc}")
            self.convert_button.setEnabled(False)
            return
        self.loaded = loaded
        self.input_path = path
        self.output_path = default_output_path(path)
        self.path_label.setText(f"Output: {self.output_path}")
        messages = [f"Input: {path}", f"Output: {self.output_path}"]
        messages.extend(f"Warning: {warning}" for warning in loaded.warnings)
        if "white" in [name.lower() for name in loaded.extra_names]:
            messages.append('Warning: input already has a channel named "white"; conversion will ask how to proceed.')
        self.log(messages)
        self.convert_button.setEnabled(True)
        self.refresh_preview()

    def _preview_rgb(self) -> np.ndarray | None:
        if self.loaded is None:
            return None
        cmyk = self.loaded.cmyk
        rgb = np.asarray(Image.fromarray(cmyk, "CMYK").convert("RGB"), dtype=np.uint8)
        alpha = self.loaded.alpha.astype(np.float32) / 255.0
        rgb = (rgb.astype(np.float32) * alpha[..., None] + 255 * (1 - alpha[..., None])).astype(np.uint8)
        if self.overlay_radio.isChecked():
            spot = generate_spot_mask(self.loaded.cmyk, self.loaded.alpha) > 0
            overlay = np.zeros_like(rgb)
            overlay[..., 0] = 255
            overlay[..., 2] = 255
            rgb = np.where(spot[..., None], (rgb.astype(np.uint16) // 2 + overlay.astype(np.uint16) // 2), rgb).astype(np.uint8)
        return rgb

    def refresh_preview(self) -> None:
        rgb = self._preview_rgb()
        if rgb is None:
            return
        height, width, _ = rgb.shape
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self.refresh_preview()

    def _existing_action(self) -> str:
        if not self.loaded or "white" not in [name.lower() for name in self.loaded.extra_names]:
            return "cancel"
        box = QMessageBox(self)
        box.setWindowTitle('Existing "white" channel')
        box.setText('The input already contains a channel named "white".')
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        overwrite = box.addButton("Overwrite existing", QMessageBox.DestructiveRole)
        alternate = box.addButton('Save as "white 2"', QMessageBox.AcceptRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return "overwrite"
        if clicked is alternate:
            return "alternate"
        if clicked is cancel:
            return "cancel"
        return "cancel"

    def convert(self) -> None:
        if self.input_path is None or self.output_path is None:
            return
        if self.output_path.exists():
            response = QMessageBox.question(
                self,
                "Overwrite output?",
                f"{self.output_path} already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if response != QMessageBox.Yes:
                return
        action = self._existing_action()
        if action == "cancel" and self.loaded and "white" in [name.lower() for name in self.loaded.extra_names]:
            self.log("Conversion cancelled.")
            return
        self.convert_button.setEnabled(False)
        self.log([f"Processing: {self.input_path}", f"Output: {self.output_path}"])
        self.worker = Processor(self.input_path, self.output_path, action)
        self.worker.finished_ok.connect(self.done)
        self.worker.failed.connect(self.failed)
        self.worker.start()

    def done(self, result: ConversionResult) -> None:
        lines = [f"Saved: {result.output_path}", f"Spot channel: {result.spot_name}"]
        lines.extend(f"Warning: {warning}" for warning in result.warnings)
        lines.extend(f"Validation: {check}" for check in result.validation)
        lines.append("Confirm final spot-channel recognition in Photoshop or the target RIP.")
        self.log(lines)
        self.convert_button.setEnabled(True)

    def failed(self, message: str) -> None:
        self.log(f"Error: {message}")
        self.convert_button.setEnabled(True)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
