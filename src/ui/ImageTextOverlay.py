from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence

import numpy as np

from gi.repository import Gdk, GLib, Graphene, Gtk  # noqa: E402

from src.ocr.ocr import Image, Text

logger = logging.getLogger(__name__)


class ImageTextOverlay(Gtk.Widget):
    """Display an OCR image with clickable text regions over it."""

    __gtype_name__ = "ImageTextOverlay"
    OCR_GRADIENT_FADE_MS = 750

    def __init__(
        self,
        image: Image,
        on_text_clicked: Callable[[Text], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self._texture = Gdk.Texture.new_from_filename(image.image_path)
        self._image_width = self._texture.get_width()
        self._image_height = self._texture.get_height()
        self._image_rect = Graphene.Rect().init(
            0, 0, self._image_width, self._image_height
        )
        self._image = image
        self._on_text_clicked = on_text_clicked
        self._texts: list[Text] = []
        self._buttons: list[Gtk.Button] = []
        self._ocr_scheduled = False
        self._ocr_started = False
        self._ocr_thread: threading.Thread | None = None
        self._ocr_hide_source: int | None = None
        self._disposed = False

        # OCR-in-progress gradient overlay
        self._ocr_gradient = Gtk.Box()
        self._ocr_gradient.add_css_class("ocr-gradient-overlay")
        self._ocr_gradient.set_can_target(False)
        self._ocr_gradient.set_visible(False)
        self._ocr_gradient.set_parent(self)

        self._install_css()

    def _start_ocr(self) -> bool:
        """Start OCR after GTK has rendered the initial image frame."""
        self._ocr_scheduled = False
        if self._disposed or self._ocr_started:
            return GLib.SOURCE_REMOVE

        self._ocr_started = True
        self._start_ocr_animation()
        self._ocr_thread = threading.Thread(
            target=self._recognize_text,
            name="image-text-overlay-ocr",
            daemon=True,
        )
        self._ocr_thread.start()
        return GLib.SOURCE_REMOVE

    def _recognize_text(self) -> None:
        """Run the blocking OCR pipeline outside the GTK main thread."""
        try:
            texts = list(self._image.recognize_text())
        except Exception:
            logger.exception("OCR failed for %s", self._image.image_path)
            GLib.idle_add(self._finish_ocr, None)
            return

        GLib.idle_add(self._finish_ocr, texts)

    def _finish_ocr(self, texts: list[Text] | None) -> bool:
        """Apply OCR results on the GTK main thread."""
        self._ocr_thread = None
        self._stop_ocr_animation()
        if not self._disposed and texts is not None:
            self.set_texts(texts)
        return GLib.SOURCE_REMOVE

    def _start_ocr_animation(self) -> None:
        if self._ocr_hide_source is not None:
            GLib.source_remove(self._ocr_hide_source)
            self._ocr_hide_source = None

        self._ocr_gradient.set_visible(True)
        self._ocr_gradient.add_css_class("running")

    def _stop_ocr_animation(self) -> None:
        if self._ocr_hide_source is not None:
            GLib.source_remove(self._ocr_hide_source)
            self._ocr_hide_source = None

        self._ocr_gradient.remove_css_class("running")
        # self._ocr_gradient.set_visible(False)

    def set_texts(self, texts: Sequence[Text]) -> None:
        """Replace the text regions displayed over the image."""
        for button in self._buttons:
            button.unparent()

        self._texts = list(texts)
        self._buttons = []

        for text in self._texts:
            button = Gtk.Button()
            button.add_css_class("text-overlay-button")
            button.set_tooltip_text(text.text)
            button.connect("clicked", self._handle_click, text)
            button.set_parent(self)
            self._buttons.append(button)

        self.queue_allocate()

    def _handle_click(self, button: Gtk.Button, text: Text) -> None:
        button.add_css_class("success")

        # drop the success class after 1 second
        GLib.timeout_add(200, lambda: button.remove_css_class("success"))

        if self._on_text_clicked is not None:
            self._on_text_clicked(text)

    def do_measure(
        self, orientation: Gtk.Orientation, for_size: int
    ) -> tuple[int, int, int, int]:
        del for_size
        natural_size = (
            self._image_width
            if orientation == Gtk.Orientation.HORIZONTAL
            else self._image_height
        )
        return 0, natural_size, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        del baseline
        if width <= 0 or height <= 0:
            self._image_rect = Graphene.Rect().init(0, 0, 0, 0)
            return

        scale = min(width / self._image_width, height / self._image_height)
        scaled_width = self._image_width * scale
        scaled_height = self._image_height * scale
        offset_x = (width - scaled_width) / 2
        offset_y = (height - scaled_height) / 2

        self._image_rect = Graphene.Rect().init(
            offset_x, offset_y, scaled_width, scaled_height
        )

        gradient_allocation = Gdk.Rectangle()
        gradient_allocation.x = round(offset_x)
        gradient_allocation.y = round(offset_y)
        gradient_allocation.width = max(1, round(scaled_width))
        gradient_allocation.height = max(1, round(scaled_height))
        self._ocr_gradient.size_allocate(gradient_allocation, -1)

        for text, button in zip(self._texts, self._buttons):
            box = np.asarray(text.box)
            x1 = float(box[:, 0].min())
            y1 = float(box[:, 1].min())
            x2 = float(box[:, 0].max())
            y2 = float(box[:, 1].max())

            allocation = Gdk.Rectangle()
            allocation.x = round(offset_x + x1 * scale)
            allocation.y = round(offset_y + y1 * scale)
            allocation.width = max(1, round((x2 - x1) * scale))
            allocation.height = max(1, round((y2 - y1) * scale))
            button.size_allocate(allocation, -1)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if self._image_rect.get_width() < 1 or self._image_rect.get_height() < 1:
            return

        snapshot.append_texture(self._texture, self._image_rect)

        if self._ocr_gradient.get_visible():
            self.snapshot_child(self._ocr_gradient, snapshot)

        for button in self._buttons:
            self.snapshot_child(button, snapshot)

        if not self._ocr_scheduled and not self._ocr_started:
            self._ocr_scheduled = True
            GLib.idle_add(self._start_ocr)

    def do_dispose(self) -> None:
        self._disposed = True
        self._stop_ocr_animation()
        if self._ocr_gradient.get_parent() is self:
            self._ocr_gradient.unparent()
        while self._buttons:
            self._buttons.pop().unparent()

    @staticmethod
    def _install_css() -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return

        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            .text-overlay-button {
                min-width: 0;
                min-height: 0;
                padding: 0;
                background-color: rgba(53, 132, 228, 0.20);
            }

            .text-overlay-button:hover {
                background-color: rgba(53, 132, 228, 0.40);
            }

            .text-overlay-button.success {
                background-color: rgba(46, 194, 126, 0.40);
            }

            .ocr-gradient-overlay {
                opacity: 0;
                transition: opacity 750ms ease-in-out;
                animation: ocr-gradient-spin 2s linear infinite;
            }

            .ocr-gradient-overlay.running {
                opacity: 0.55;
            }

            @keyframes ocr-gradient-spin {
                from {
                    background-image: linear-gradient(
                        -45deg,
                        rgba(35, 120, 255, 0.58) 0%,
                        rgba(0, 210, 190, 0.52) 50%,
                        rgba(30, 210, 115, 0.58) 100%
                    );
                }

                to {
                    background-image: linear-gradient(
                        315deg,
                        rgba(35, 120, 255, 0.58) 0%,
                        rgba(0, 210, 190, 0.52) 50%,
                        rgba(30, 210, 115, 0.58) 100%
                    );
                }
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
