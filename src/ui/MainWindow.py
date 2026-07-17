"""Main application window."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlencode

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from src.ocr.ocr import Image, Text
from src.ui.ImageTextOverlay import ImageTextOverlay
from src.ui.TranslatorPane import TranslatorPane


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
    _recognized_text_row: Adw.EntryRow = Gtk.Template.Child(
        "recognized-text-row"
    )
    _btn_copy_text: Gtk.Button = Gtk.Template.Child("btn-copy-text")
    _translator_pane: TranslatorPane = Gtk.Template.Child("translator-pane")

    def __init__(
        self,
        application: Adw.Application,
        image: Image,
        **kwargs,
    ) -> None:
        super().__init__(application=application, **kwargs)
        self._translator_pane.connect(
            "toast-requested",
            self._handle_translator_toast,
        )
        self._translator_pane.connect(
            "source-text-replaced",
            self._handle_translator_source_replaced,
        )

        # Put the image and its text overlay into the overlay container
        self._overlay_container.set_child(
            ImageTextOverlay(
                image=image,
                on_texts_selected=self._handle_texts_selected,
            )
        )

    def _handle_texts_selected(self, texts: Sequence[Text]) -> None:
        """Update the selected-text model from one or more OCR regions."""
        combined_text = "\n".join(text.text for text in texts)
        average_score = sum(text.score for text in texts) / len(texts)
        self._selected_text.props.text = combined_text
        self._selected_text.props.score = f"{average_score:.3f}"

        # Copy the complete selection using the existing copy action.
        self._btn_copy_text.activate()

    @Gtk.Template.Callback()
    def on_recognized_text_commit(
        self,
        _source: Adw.EntryRow | Gtk.EventControllerFocus,
    ) -> None:
        """Commit manual edits after activation or focus loss."""
        text = self._recognized_text_row.get_text()
        if text != self._selected_text.props.text:
            self._selected_text.props.text = text

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

    @Gtk.Template.Callback()
    def on_google_search_activated(self, _row: Adw.ButtonRow) -> None:
        """Search for the selected OCR text in the default browser."""
        query = self._selected_text.props.text.strip()
        if not query or query == "NA":
            self._toast_overlay.add_toast(
                Adw.Toast.new("Select some text to search")
            )
            return

        uri = f"https://www.google.com/search?{urlencode({'q': query})}"
        try:
            launched = Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error:
            launched = False

        if not launched:
            self._toast_overlay.add_toast(
                Adw.Toast.new("Could not open the default browser")
            )

    def _handle_translator_toast(
        self,
        _pane: TranslatorPane,
        message: str,
    ) -> None:
        toast = Adw.Toast.new(message)
        if message == "Translation copied to clipboard":
            toast.set_timeout(1)
        self._toast_overlay.add_toast(toast)

    def _handle_translator_source_replaced(
        self,
        _pane: TranslatorPane,
        source_text: str,
    ) -> None:
        """Keep all selected-text consumers synchronized after a swap."""
        self._selected_text.props.text = source_text
