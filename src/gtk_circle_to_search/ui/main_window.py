"""Main application window."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from urllib.parse import urlencode

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Xdp, XdpGtk4

from ..ocr.ocr import Image, Text
from .image_text_overlay import ImageTextOverlay
from .translator_pane import TranslatorPane

logger = logging.getLogger(__name__)


class SelectedText(GObject.Object):
    """GObject model for the currently selected OCR text."""

    __gtype_name__ = "SelectedText"

    text = GObject.Property(type=str, default="NA")  # Selected text
    score = GObject.Property(type=str, default="0.000")  # Confidence score


@Gtk.Template(resource_path="/com/github/circle_to_search/ui/main-window.ui")
class MainWindow(Adw.ApplicationWindow):
    """An Adwaita window containing an image and its OCR text overlay."""

    __gtype_name__ = "MainWindow"

    # state storing the currently active image, which is bound to the overlay
    active_image = GObject.Property(type=object)

    _main_stack: Gtk.Stack = Gtk.Template.Child("main-stack")
    _image_drop_target: Gtk.DropTarget = Gtk.Template.Child("image-drop-target")
    _start_page: Adw.StatusPage = Gtk.Template.Child("start-page")
    _overlay_container: Adw.Bin = Gtk.Template.Child("overlay_container")
    _image_text_overlay: ImageTextOverlay = Gtk.Template.Child("image-text-overlay")
    _toast_overlay: Adw.ToastOverlay = Gtk.Template.Child("toast-overlay")
    _selected_text: SelectedText = Gtk.Template.Child("selected_text")
    _recognized_text_buffer: Gtk.TextBuffer = Gtk.Template.Child(
        "recognized-text-buffer"
    )
    _btn_copy_text: Gtk.Button = Gtk.Template.Child("btn-copy-text")
    _translator_pane: TranslatorPane = Gtk.Template.Child("translator-pane")

    def __init__(
        self,
        application: Adw.Application,
        **kwargs,
    ) -> None:
        super().__init__(application=application, **kwargs)

        style_provider = Gtk.CssProvider()
        style_provider.load_from_resource(
            "/com/github/circle_to_search/style.css"
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._translator_pane.connect(
            "toast-requested",
            self._handle_translator_toast,
        )
        self._image_text_overlay.connect(
            "texts-selected",
            self._handle_texts_selected,
        )

        self._image_drop_target.set_gtypes([Gdk.FileList])

    def set_image(self, image: Image) -> None:
        """Set and display the active image."""
        self.props.active_image = image
        self._main_stack.set_visible_child(self._overlay_container)

    def _load_image_file(self, file: Gio.File) -> bool:
        """Load a local image file and report whether it succeeded."""
        path = file.get_path()
        if path is None:
            self._toast_overlay.add_toast(
                Adw.Toast.new("Only local image files are supported")
            )
            return False

        try:
            self.set_image(Image(path))
        except Exception as error:
            logger.exception("Could not open image %s", path)
            self._toast_overlay.add_toast(
                Adw.Toast.new(f"Could not open image: {error}")
            )
            return False

        return True

    @Gtk.Template.Callback()
    def on_image_dropped(
        self,
        _target: Gtk.DropTarget,
        files: Gdk.FileList,
        _x: float,
        _y: float,
    ) -> bool:
        """Load the first image file dropped onto the image area."""
        dropped_files = files.get_files()
        if not dropped_files:
            return False

        return self._load_image_file(dropped_files[0])

    @Gtk.Template.Callback()
    def on_open_image_clicked(self, _button: Gtk.Button) -> None:
        """Prompt the user to choose an image to open."""
        image_filter = Gtk.FileFilter(name="Images")
        image_filter.add_mime_type("image/*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)

        dialog = Gtk.FileDialog(
            title="Open Image",
            modal=True,
            filters=filters,
            default_filter=image_filter,
        )

        def _on_open_image_finished(
            dialog: Gtk.FileDialog,
            result: Gio.AsyncResult,
        ) -> None:
            """Load the image selected through the asynchronous file dialog."""
            try:
                file = dialog.open_finish(result)
            except GLib.Error as error:
                if not error.matches(
                    Gio.io_error_quark(),
                    Gio.IOErrorEnum.CANCELLED,
                ):
                    logger.warning("Image selection failed: %s", error)
                    self._toast_overlay.add_toast(
                        Adw.Toast.new("Could not open the image chooser")
                    )
                return

            self._load_image_file(file)

        dialog.open(self, None, _on_open_image_finished)

    @Gtk.Template.Callback()
    def on_screenshot_clicked(self, _button: Gtk.Button) -> None:
        """Request an interactive screenshot through the desktop portal."""
        portal = Xdp.Portal.new()
        parent = XdpGtk4.parent_new_gtk(self)

        def _on_screenshot_finished(
            portal: Xdp.Portal,
            result: Gio.AsyncResult,
            _parent: Xdp.Parent = parent,
        ) -> None:
            try:
                uri = portal.take_screenshot_finish(result)
            except GLib.Error as error:
                if not error.matches(
                    Gio.io_error_quark(),
                    Gio.IOErrorEnum.CANCELLED,
                ):
                    logger.warning("Screenshot request failed: %s", error)
                    self._toast_overlay.add_toast(
                        Adw.Toast.new("Could not take screenshot")
                    )
                return

            if not uri:
                self._toast_overlay.add_toast(
                    Adw.Toast.new("The screenshot portal returned no image")
                )
                return

            self._load_image_file(Gio.File.new_for_uri(uri))

        portal.take_screenshot(
            parent,
            Xdp.ScreenshotFlags.INTERACTIVE,
            None,
            _on_screenshot_finished,
        )

    @Gtk.Template.Callback()
    def on_clear_image_clicked(self, _button: Gtk.Button) -> None:
        """Clear the active image and return to the start page."""
        self.props.active_image = None
        self._selected_text.props.text = "NA"
        self._selected_text.props.score = "0.000"
        self._main_stack.set_visible_child(self._start_page)

    def _handle_texts_selected(
        self,
        _overlay: ImageTextOverlay,
        texts: Sequence[Text],
    ) -> None:
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
        _source: Gtk.EventControllerFocus | Gtk.EventControllerKey,
    ) -> None:
        """Commit manual edits after focus loss or Ctrl+Enter."""
        start, end = self._recognized_text_buffer.get_bounds()
        text = self._recognized_text_buffer.get_text(start, end, True)
        if text != self._selected_text.props.text:
            self._selected_text.props.text = text

    @Gtk.Template.Callback()
    def on_recognized_text_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        """Commit the multiline editor with Ctrl+Enter."""
        if keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        if not state & Gdk.ModifierType.CONTROL_MASK:
            return False

        self.on_recognized_text_commit(controller)
        return True

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
            self._toast_overlay.add_toast(Adw.Toast.new("Select some text to search"))
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
