from src.ocr.ocr import Image
from . import MainWindow

from gi.repository import Adw  # noqa: E402


class App(Adw.Application):
    """Main application class."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._image: Image | None = None
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            # Initialize the window; its overlay starts OCR asynchronously.
            self._image = Image("tests/spotify2.png")

            self._window = MainWindow(
                application=self,
                image=self._image,
            )

        self._window.present()
