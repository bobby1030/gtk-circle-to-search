from .ocr.ocr import Image
from .ui.main_window import MainWindow

from gi.repository import Adw, Gio, GLib  # noqa: E402


class App(Adw.Application):
    """Main application class."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            flags=(
                Gio.ApplicationFlags.HANDLES_OPEN
                | Gio.ApplicationFlags.HANDLES_COMMAND_LINE
            ),
            **kwargs,
        )
        self._window: MainWindow | None = None
        self.add_main_option(
            "screenshot",
            ord("s"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Take a screenshot on startup",
            None,
        )

    def _get_window(self) -> MainWindow:
        if self._window is None:
            self._window = MainWindow(application=self)
        return self._window

    def do_activate(self) -> None:
        """Application activated by the shell or command line without file arguments."""
        self._get_window().present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        """Handle command-line requests in the primary application instance."""
        arguments = command_line.get_arguments()[1:]
        if arguments:
            files = [
                command_line.create_file_for_arg(argument)
                for argument in arguments
            ]
            self.do_open(files, len(files), "")
        else:
            self.activate()

        if command_line.get_options_dict().contains("screenshot"):
            window = self._get_window()
            window.present()
            GLib.idle_add(window.take_screenshot)

        return 0

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
