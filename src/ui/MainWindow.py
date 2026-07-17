"""Main application window."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from src.ocr.ocr import Image, Text
from src.ui.ImageTextOverlay import ImageTextOverlay


class MainWindow(Adw.ApplicationWindow):
    """An Adwaita window containing an image and its OCR text overlay."""

    def __init__(
        self,
        application: Adw.Application,
        image: Image,
        texts: Sequence[Text],
        on_text_clicked: Callable[[Text], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(application=application, **kwargs)

        self.set_title("Circle to Search")
        self.set_default_size(1200, 800)
        self.set_content(
            ImageTextOverlay(
                image=image,
                texts=texts,
                on_text_clicked=on_text_clicked,
            )
        )
