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
        "source-text-replaced": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str,),
        ),
    }

    AUTO_TRANSLATE_DELAY_MS = 650
    LANGUAGES = (
        ("Arabic", "ar"),
        ("Dutch", "nl"),
        ("English", "en"),
        ("French", "fr"),
        ("German", "de"),
        ("Greek", "el"),
        ("Hebrew", "he"),
        ("Hindi", "hi"),
        ("Indonesian", "id"),
        ("Italian", "it"),
        ("Japanese", "ja"),
        ("Korean", "ko"),
        ("Polish", "pl"),
        ("Portuguese", "pt"),
        ("Russian", "ru"),
        ("Simplified Chinese", "zh-CN"),
        ("Spanish", "es"),
        ("Thai", "th"),
        ("Traditional Chinese", "zh-TW"),
        ("Turkish", "tr"),
        ("Ukrainian", "uk"),
        ("Vietnamese", "vi"),
    )
    _LANGUAGE_NAMES = {code: name for name, code in LANGUAGES}
    _translation_lock = threading.Lock()

    source_text = GObject.Property(type=str, default="")

    _source_language_row: Adw.ActionRow = Gtk.Template.Child(
        "source-language-row"
    )
    _language_row: Adw.ComboRow = Gtk.Template.Child("language-row")
    _auto_translate_row: Adw.SwitchRow = Gtk.Template.Child(
        "auto-translate-row"
    )
    _translated_text_buffer: Gtk.TextBuffer = Gtk.Template.Child(
        "translated-text-buffer"
    )
    _translation_error_row: Adw.ActionRow = Gtk.Template.Child(
        "translation-error-row"
    )
    _translate_button: Adw.ButtonRow = Gtk.Template.Child("translate-button")
    _swap_button: Gtk.Button = Gtk.Template.Child("swap-button")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._translation_request_id = 0
        self._active_request_id: int | None = None
        self._auto_translate_source_id: int | None = None
        self._source_language_code = "auto"
        self._detected_language_code: str | None = None
        self._last_source_text = ""
        self._last_translation = ""
        self._updating_controls = False

        self._language_row.set_model(
            Gtk.StringList.new([name for name, _code in self.LANGUAGES])
        )
        self._select_target_language("en")
        self.connect("notify::source-text", self._handle_source_text_changed)
        self._language_row.connect(
            "notify::selected", self._handle_target_language_changed
        )
        self._auto_translate_row.connect(
            "notify::active", self._handle_auto_translate_changed
        )

    def _handle_source_text_changed(
        self,
        _pane: TranslatorPane,
        _pspec: GObject.ParamSpec,
    ) -> None:
        if self._updating_controls:
            return

        self._source_language_code = "auto"
        self._detected_language_code = None
        self._source_language_row.set_subtitle("Detect automatically")
        self._invalidate_translation(clear_result=True)
        self._schedule_auto_translation()

    def _handle_target_language_changed(
        self,
        _row: Adw.ComboRow,
        _pspec: GObject.ParamSpec,
    ) -> None:
        if self._updating_controls:
            return

        self._invalidate_translation(clear_result=True)
        self._schedule_auto_translation()

    def _handle_auto_translate_changed(
        self,
        _row: Adw.SwitchRow,
        _pspec: GObject.ParamSpec,
    ) -> None:
        self._cancel_auto_translation()
        if self._auto_translate_row.get_active():
            self._schedule_auto_translation()

    def _invalidate_translation(self, *, clear_result: bool) -> None:
        """Invalidate pending work so an old worker cannot update the UI."""
        self._translation_request_id += 1
        self._active_request_id = None
        self._set_busy(False)
        self._hide_error()
        if clear_result:
            self._translated_text_buffer.set_text("")
            self._last_translation = ""
            self._swap_button.set_sensitive(False)

    def _cancel_auto_translation(self) -> None:
        if self._auto_translate_source_id is None:
            return
        GLib.source_remove(self._auto_translate_source_id)
        self._auto_translate_source_id = None

    def _schedule_auto_translation(self) -> None:
        self._cancel_auto_translation()
        source_text = self.props.source_text.strip()
        if (
            not self._auto_translate_row.get_active()
            or not source_text
            or source_text == "NA"
        ):
            return

        self._auto_translate_source_id = GLib.timeout_add(
            self.AUTO_TRANSLATE_DELAY_MS,
            self._run_scheduled_translation,
        )

    def _run_scheduled_translation(self) -> bool:
        self._auto_translate_source_id = None
        self._start_translation(show_empty_message=False)
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_translate_activated(self, _row: Adw.ButtonRow) -> None:
        """Translate the source text without blocking GTK."""
        self._cancel_auto_translation()
        self._start_translation(show_empty_message=True)

    @Gtk.Template.Callback()
    def on_retry_translation_clicked(self, _button: Gtk.Button) -> None:
        """Retry the current translation inputs after an error."""
        self._start_translation(show_empty_message=True)

    def _start_translation(self, *, show_empty_message: bool) -> None:
        source_text = self.props.source_text.strip()
        if not source_text or source_text == "NA":
            if show_empty_message:
                self.emit("toast-requested", "Select some text to translate")
            return

        target_language = self._get_target_language()
        if target_language is None:
            return

        self._translation_request_id += 1
        request_id = self._translation_request_id
        self._active_request_id = request_id
        self._last_source_text = source_text
        self._hide_error()
        self._set_busy(True)

        threading.Thread(
            target=self._translate_text,
            args=(
                request_id,
                source_text,
                self._source_language_code,
                target_language,
            ),
            name="selected-text-translation",
            daemon=True,
        ).start()

    def _translate_text(
        self,
        request_id: int,
        source_text: str,
        source_language: str,
        target_language: str,
    ) -> None:
        try:
            if request_id != self._translation_request_id:
                return
            os.environ.setdefault("translators_default_region", "EN")
            import translators as translators_api

            # TranslatorsServer reuses mutable sessions internally. Serialize
            # calls so a stale request and its replacement do not race inside
            # the package; GTK remains responsive because this is a worker.
            with self._translation_lock:
                if request_id != self._translation_request_id:
                    return
                result = translators_api.translate_text(
                    query_text=source_text,
                    translator="google",
                    from_language=source_language,
                    to_language=target_language,
                    timeout=15,
                    if_print_warning=False,
                )
            if not isinstance(result, str):
                raise TypeError("Translation service returned a non-text result")
            detected_language = (
                source_language
                if source_language != "auto"
                else self._detect_language(source_text)
            )
        except Exception as error:
            logger.exception("Translation failed")
            GLib.idle_add(
                self._finish_translation,
                request_id,
                None,
                None,
                str(error),
            )
            return

        GLib.idle_add(
            self._finish_translation,
            request_id,
            result,
            detected_language,
            None,
        )

    def _finish_translation(
        self,
        request_id: int,
        translated_text: str | None,
        detected_language: str | None,
        error_message: str | None,
    ) -> bool:
        if (
            request_id != self._translation_request_id
            or request_id != self._active_request_id
        ):
            return GLib.SOURCE_REMOVE

        self._active_request_id = None
        self._set_busy(False)

        if translated_text is None:
            self._show_error(error_message)
            self.emit("toast-requested", "Translation failed")
            return GLib.SOURCE_REMOVE

        self._hide_error()
        self._detected_language_code = detected_language
        self._last_translation = translated_text
        self._translated_text_buffer.set_text(translated_text)
        self._update_source_language_row(detected_language)
        self._update_swap_sensitivity()
        return GLib.SOURCE_REMOVE

    def _set_busy(self, busy: bool) -> None:
        self._translate_button.set_sensitive(not busy)
        self._translate_button.set_title(
            "Translating…" if busy else "Translate"
        )
        self._language_row.set_sensitive(not busy)
        self._swap_button.set_sensitive(False if busy else self._can_swap())

    def _show_error(self, error_message: str | None) -> None:
        detail = "Check your connection and try again."
        if error_message:
            first_line = error_message.strip().splitlines()[0]
            if first_line:
                detail = first_line[:160]
        self._translation_error_row.set_subtitle(detail)
        self._translation_error_row.set_visible(True)

    def _hide_error(self) -> None:
        self._translation_error_row.set_visible(False)

    def _get_target_language(self) -> str | None:
        language_index = self._language_row.get_selected()
        if language_index >= len(self.LANGUAGES):
            return None
        return self.LANGUAGES[language_index][1]

    def _select_target_language(self, language_code: str) -> bool:
        for index, (_name, code) in enumerate(self.LANGUAGES):
            if code == language_code:
                self._language_row.set_selected(index)
                return True
        return False

    def _update_source_language_row(self, language_code: str | None) -> None:
        if language_code is None:
            self._source_language_row.set_subtitle("Detected automatically")
            return
        language_name = self._LANGUAGE_NAMES.get(
            language_code, language_code.upper()
        )
        suffix = "detected" if self._source_language_code == "auto" else "source"
        self._source_language_row.set_subtitle(f"{language_name} ({suffix})")

    def _can_swap(self) -> bool:
        target_language = self._get_target_language()
        source_language = (
            self._detected_language_code
            if self._source_language_code == "auto"
            else self._source_language_code
        )
        return bool(
            self._last_source_text
            and self._last_translation
            and source_language
            and target_language
            and source_language != target_language
            and source_language in self._LANGUAGE_NAMES
        )

    def _update_swap_sensitivity(self) -> None:
        self._swap_button.set_sensitive(self._can_swap())

    @Gtk.Template.Callback()
    def on_swap_languages_clicked(self, _button: Gtk.Button) -> None:
        """Use the translation as source and reverse the language direction."""
        if not self._can_swap():
            return

        previous_source = self._last_source_text
        previous_translation = self._last_translation
        previous_target = self._get_target_language()
        previous_source_language = (
            self._detected_language_code
            if self._source_language_code == "auto"
            else self._source_language_code
        )
        if previous_target is None or previous_source_language is None:
            return

        self._cancel_auto_translation()
        self._updating_controls = True
        try:
            self.props.source_text = previous_translation
            self._select_target_language(previous_source_language)
            # The host updates its selected-text model synchronously. Keep the
            # guard active while its binding writes the same value back here.
            self.emit("source-text-replaced", previous_translation)
        finally:
            self._updating_controls = False

        self._translation_request_id += 1
        self._active_request_id = None
        self._source_language_code = previous_target
        self._detected_language_code = previous_target
        self._last_source_text = previous_translation
        self._last_translation = previous_source
        self._translated_text_buffer.set_text(previous_source)
        self._hide_error()
        self._update_source_language_row(previous_target)
        self._update_swap_sensitivity()
        self.emit("toast-requested", "Translation languages swapped")

    @staticmethod
    def _detect_language(text: str) -> str | None:
        """Estimate a source language locally for display and swapping.

        The translators API does not expose Google's detected language in its
        normal string response, so script ranges provide a deterministic hint
        without adding another network request.
        """
        if any("\uac00" <= character <= "\ud7af" for character in text):
            return "ko"
        if any(
            "\u3040" <= character <= "\u30ff" for character in text
        ):
            return "ja"
        if any("\u4e00" <= character <= "\u9fff" for character in text):
            traditional_markers = set("國學體臺灣萬與為這來時會說話後裡點麼")
            return "zh-TW" if traditional_markers.intersection(text) else "zh-CN"
        if any("\u0400" <= character <= "\u04ff" for character in text):
            return "uk" if set("іїєґІЇЄҐ").intersection(text) else "ru"
        if any("\u0600" <= character <= "\u06ff" for character in text):
            return "ar"
        if any("\u0900" <= character <= "\u097f" for character in text):
            return "hi"
        if any("\u0e00" <= character <= "\u0e7f" for character in text):
            return "th"
        if any("\u0590" <= character <= "\u05ff" for character in text):
            return "he"
        if any("\u0370" <= character <= "\u03ff" for character in text):
            return "el"
        if any(character.isascii() and character.isalpha() for character in text):
            return "en"
        return None

    @Gtk.Template.Callback()
    def on_copy_translation_clicked(self, _button: Gtk.Button) -> None:
        """Copy the translated text to the clipboard."""
        start, end = self._translated_text_buffer.get_bounds()
        translated_text = self._translated_text_buffer.get_text(
            start,
            end,
            True,
        ).strip()
        if not translated_text:
            self.emit("toast-requested", "Nothing to copy yet")
            return

        content = Gdk.ContentProvider.new_for_bytes(
            "text/plain;charset=utf-8",
            GLib.Bytes.new(translated_text.encode("utf-8")),
        )
        self.get_display().get_clipboard().set_content(content)
        self.emit("toast-requested", "Translation copied to clipboard")
