"""Main application window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Gtk

from src.ocr.ocr import Image, Text
from src.ui.ImageTextOverlay import ImageTextOverlay


class SelectedText(GObject.Object):
    """GObject model for the currently selected OCR text."""

    __gtype_name__ = "SelectedText"

    text = GObject.Property(type=str, default="NA")  # Selected text
    score = GObject.Property(type=str, default="0.000")  # Confidence score


@Gtk.Template(filename=str(Path(__file__).with_name("assets") / "main-window.ui"))
class MainWindow(Adw.ApplicationWindow):
    """An Adwaita window containing an image and its OCR text overlay."""

    __gtype_name__ = "MainWindow"

    _overlay_container: Adw.Bin = Gtk.Template.Child("overlay_container")
    _toast_overlay: Adw.ToastOverlay = Gtk.Template.Child("toast-overlay")
    _selected_text: SelectedText = Gtk.Template.Child("selected_text")
    _btn_copy_text: Gtk.Button = Gtk.Template.Child("btn-copy-text")

    def __init__(
        self,
        application: Adw.Application,
        image: Image,
        **kwargs,
    ) -> None:
        super().__init__(application=application, **kwargs)

        # Put the image and its text overlay into the overlay container
        self._overlay_container.set_child(
            ImageTextOverlay(
                image=image,
                texts=image.recognize_text(),
                on_text_clicked=self._handle_text_clicked,
            )
        )

    def _handle_text_clicked(self, text: Text) -> None:
        "Handle a click on a text bounding box by updating the selected text property."
        self._selected_text.props.text = text.text
        self._selected_text.props.score = f"{text.score:.3f}"
        print(f"Selected text: {text.text} (score: {text.score:.3f})")

        # When clicking on a text, activate the copy button
        self._btn_copy_text.activate()

    @Gtk.Template.Callback()
    def on_copy_text_clicked(self, _button: Gtk.Button) -> None:
        """Handle a click on the copy text button"""
        content = Gdk.ContentProvider.new_for_bytes(
            "text/plain;charset=utf-8",
            GLib.Bytes.new(self._selected_text.props.text.encode("utf-8")),
        )
        self.get_display().get_clipboard().set_content(content)

        # Notify the text has been copied
        toast = Adw.Toast.new("Text copied to clipboard")
        toast.set_timeout(1)
        self._toast_overlay.add_toast(toast)
