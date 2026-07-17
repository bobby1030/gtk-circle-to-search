"""Reusable sidebar pane for translating selected text."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Gtk

logger = logging.getLogger(__name__)


@Gtk.Template(
    filename=str(Path(__file__).with_name("assets") / "translator-pane.ui")
)
class TranslatorPane(Adw.PreferencesGroup):
    """Translate text into a selected target language."""

    __gtype_name__ = "TranslatorPane"
    __gsignals__ = {
        "toast-requested": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str,),
        ),
    }

    LANGUAGES = (
        ("English", "en"),
        ("Traditional Chinese", "zh-TW"),
        ("Simplified Chinese", "zh-CN"),
        ("Japanese", "ja"),
        ("Korean", "ko"),
        ("Spanish", "es"),
        ("French", "fr"),
        ("German", "de"),
    )

    source_text = GObject.Property(type=str, default="")

    _language_row: Adw.ComboRow = Gtk.Template.Child("language-row")
    _translated_text_row: Adw.EntryRow = Gtk.Template.Child(
        "translated-text-row"
    )
    _translate_button: Adw.ButtonRow = Gtk.Template.Child("translate-button")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._translation_request_id = 0
        self._language_row.set_model(
            Gtk.StringList.new([name for name, _code in self.LANGUAGES])
        )
        self.connect("notify::source-text", self._handle_source_text_changed)

    def _handle_source_text_changed(
        self,
        _pane: TranslatorPane,
        _pspec: GObject.ParamSpec,
    ) -> None:
        self._translation_request_id += 1
        self._translated_text_row.set_text("")

        # Invoke the translation automatically if the source text is non-empty
        if self.props.source_text.strip():
            self._translate_button.activate()

    @Gtk.Template.Callback()
    def on_translate_activated(self, _row: Adw.ButtonRow) -> None:
        """Translate the source text without blocking GTK."""
        source_text = self.props.source_text.strip()
        if not source_text or source_text == "NA":
            self.emit("toast-requested", "Select some text to translate")
            return

        language_index = self._language_row.get_selected()
        if language_index >= len(self.LANGUAGES):
            return
        _language_name, language_code = self.LANGUAGES[language_index]

        self._translation_request_id += 1
        request_id = self._translation_request_id
        self._translate_button.set_sensitive(False)
        self._translate_button.set_title("Translating…")
        self._language_row.set_sensitive(False)

        threading.Thread(
            target=self._translate_text,
            args=(request_id, source_text, language_code),
            name="selected-text-translation",
            daemon=True,
        ).start()

    def _translate_text(
        self,
        request_id: int,
        source_text: str,
        target_language: str,
    ) -> None:
        try:
            os.environ.setdefault("translators_default_region", "EN")
            import translators as translators_api

            result = translators_api.translate_text(
                query_text=source_text,
                translator="google",
                from_language="auto",
                to_language=target_language,
                timeout=15,
                if_print_warning=False,
            )
            if not isinstance(result, str):
                raise TypeError("Translation service returned a non-text result")
        except Exception:
            logger.exception("Translation failed")
            GLib.idle_add(self._finish_translation, request_id, None)
            return

        GLib.idle_add(self._finish_translation, request_id, result)

    def _finish_translation(
        self,
        request_id: int,
        translated_text: str | None,
    ) -> bool:
        self._translate_button.set_sensitive(True)
        self._translate_button.set_title("Translate")
        self._language_row.set_sensitive(True)

        if request_id != self._translation_request_id:
            return GLib.SOURCE_REMOVE

        if translated_text is None:
            self.emit("toast-requested", "Translation failed")
        else:
            self._translated_text_row.set_text(translated_text)
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_copy_translation_clicked(self, _button: Gtk.Button) -> None:
        """Copy the translated text to the clipboard."""
        translated_text = self._translated_text_row.get_text().strip()
        if not translated_text:
            self.emit("toast-requested", "Nothing to copy yet")
            return

        content = Gdk.ContentProvider.new_for_bytes(
            "text/plain;charset=utf-8",
            GLib.Bytes.new(translated_text.encode("utf-8")),
        )
        self.get_display().get_clipboard().set_content(content)
        self.emit("toast-requested", "Translation copied to clipboard")
