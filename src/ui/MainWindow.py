"""Main application window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from gi.repository import Adw, Gtk

from src.ocr.ocr import Image, Text
from src.ui.ImageTextOverlay import ImageTextOverlay


@Gtk.Template(filename=str(Path(__file__).with_name("assets") / "main-window.ui"))
class MainWindow(Adw.ApplicationWindow):
    """An Adwaita window containing an image and its OCR text overlay."""

    __gtype_name__ = "MainWindow"

    _overlay_container: Adw.Bin = Gtk.Template.Child("overlay_container")

    def __init__(
        self,
        application: Adw.Application,
        image: Image,
        texts: Sequence[Text],
        on_text_clicked: Callable[[Text], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(application=application, **kwargs)

        self._overlay_container.set_child(
            ImageTextOverlay(
                image=image,
                texts=texts,
                on_text_clicked=on_text_clicked,
            )
        )
