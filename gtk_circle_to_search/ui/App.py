from ..ocr.ocr import Image
from .MainWindow import MainWindow

from gi.repository import Adw, Gio  # noqa: E402


class App(Adw.Application):
    """Main application class."""

    def __init__(self, **kwargs) -> None:
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_OPEN, **kwargs)
        self._window: MainWindow | None = None

    def _get_window(self) -> MainWindow:
        if self._window is None:
            self._window = MainWindow(application=self)
        return self._window

    def do_activate(self) -> None:
        """Application activated by the shell or command line without file arguments."""
        self._get_window().present()

    def do_open(
        self,
        files: list[Gio.File],
        _n_files: int,
        _hint: str,
    ) -> None:
        """Open the first file supplied by the shell or command line."""
        path = files[0].get_path()
        if path is None:
            self.activate()
            return

        window = self._get_window()
        window.set_image(Image(path))
        window.present()
