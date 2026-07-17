from src.ocr.ocr import Image, Text
from . import MainWindow

from gi.repository import Adw  # noqa: E402


class App(Adw.Application):
    """Main application class."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._image: Image | None = None
        self._recognized_texts: list[Text] | None = None
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            # initialize the main window and OCR the image
            self._image = Image("tests/spotify2.png")
            self._image.recognize_text()
            self._recognized_texts = self._image.recognized_texts

            self._window = MainWindow(
                application=self,
                image=self._image,
                texts=self._recognized_texts,
                on_text_clicked=None,
            )

        self._window.present()
