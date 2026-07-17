from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable, Sequence

import numpy as np

from gi.repository import Gdk, GLib, Graphene, Gtk  # noqa: E402

from src.ocr.ocr import Image, Text

logger = logging.getLogger(__name__)


class ImageTextOverlay(Gtk.Widget):
    """Display an OCR image with clickable text regions over it."""

    __gtype_name__ = "ImageTextOverlay"
    MIN_ZOOM = 1.0
    MAX_ZOOM = 5.0
    ZOOM_STEP = 1.12
    AREA_SELECT_THRESHOLD = 5.0
    OCR_GRADIENT_FADE_MS = 750

    def __init__(
        self,
        image: Image,
        on_texts_selected: Callable[[Sequence[Text]], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self._texture = Gdk.Texture.new_from_filename(image.image_path)
        self._image_width = self._texture.get_width()
        self._image_height = self._texture.get_height()
        self._image_rect = Graphene.Rect().init(
            0, 0, self._image_width, self._image_height
        )
        self._image = image
        self._on_texts_selected = on_texts_selected
        self._texts: list[Text] = []
        self._buttons: list[Gtk.Button] = []
        self._selected_texts: list[Text] = []
        self._ocr_scheduled = False
        self._ocr_started = False
        self._ocr_thread: threading.Thread | None = None
        self._ocr_hide_source: int | None = None
        self._zoom = self.MIN_ZOOM
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._pointer_x: float | None = None
        self._pointer_y: float | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._selection_start: tuple[float, float] | None = None
        self._selection_end: tuple[float, float] | None = None
        self._is_area_selecting = False
        self._disposed = False

        # OCR-in-progress gradient overlay
        self._ocr_gradient = Gtk.Box()
        self._ocr_gradient.add_css_class("ocr-gradient-overlay")
        self._ocr_gradient.set_can_target(False)
        self._ocr_gradient.set_visible(False)
        self._ocr_gradient.set_parent(self)

        self._area_selector = Gtk.Box()
        self._area_selector.add_css_class("text-area-selector")
        self._area_selector.set_can_target(False)
        self._area_selector.set_visible(False)
        self._area_selector.set_parent(self)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self._handle_pointer_motion)
        self.add_controller(motion_controller)

        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self._handle_scroll)
        self.add_controller(scroll_controller)

        drag_controller = Gtk.GestureDrag.new()
        drag_controller.set_button(Gdk.BUTTON_PRIMARY)
        drag_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drag_controller.connect("drag-begin", self._handle_drag_begin)
        drag_controller.connect("drag-update", self._handle_drag_update)
        drag_controller.connect("drag-end", self._handle_drag_end)
        self.add_controller(drag_controller)

        self._install_css()

    def _handle_pointer_motion(
        self,
        _controller: Gtk.EventControllerMotion,
        x: float,
        y: float,
    ) -> None:
        self._pointer_x = x
        self._pointer_y = y

    def _handle_scroll(
        self,
        _controller: Gtk.EventControllerScroll,
        _delta_x: float,
        delta_y: float,
    ) -> bool:
        if delta_y == 0:
            return False

        zoom_delta = max(-10.0, min(10.0, -delta_y))
        new_zoom = max(
            self.MIN_ZOOM,
            min(self.MAX_ZOOM, self._zoom * self.ZOOM_STEP**zoom_delta),
        )
        if abs(new_zoom - self._zoom) < 1e-6:
            return True

        width = self.get_width()
        height = self.get_height()
        image_width = self._image_rect.get_width()
        image_height = self._image_rect.get_height()
        if width > 0 and height > 0 and image_width > 0 and image_height > 0:
            pointer_x = (
                self._pointer_x if self._pointer_x is not None else width / 2
            )
            pointer_y = (
                self._pointer_y if self._pointer_y is not None else height / 2
            )
            image_x = max(
                0.0,
                min(1.0, (pointer_x - self._image_rect.get_x()) / image_width),
            )
            image_y = max(
                0.0,
                min(1.0, (pointer_y - self._image_rect.get_y()) / image_height),
            )

            fit_scale = min(
                width / self._image_width,
                height / self._image_height,
            )
            scaled_width = self._image_width * fit_scale * new_zoom
            scaled_height = self._image_height * fit_scale * new_zoom
            self._pan_x = (
                pointer_x
                - image_x * scaled_width
                - (width - scaled_width) / 2
            )
            self._pan_y = (
                pointer_y
                - image_y * scaled_height
                - (height - scaled_height) / 2
            )

        self._zoom = new_zoom
        if self._zoom == self.MIN_ZOOM:
            self._pan_x = 0.0
            self._pan_y = 0.0
        self.queue_allocate()
        return True

    def _handle_drag_begin(
        self,
        _gesture: Gtk.GestureDrag,
        start_x: float,
        start_y: float,
    ) -> None:
        self._drag_origin = (start_x, start_y)
        start = self._clamp_to_visible_image(start_x, start_y)
        self._selection_start = start
        self._selection_end = start
        self._is_area_selecting = False
        self._area_selector.set_visible(False)

    def _handle_drag_update(
        self,
        gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if self._selection_start is None or self._drag_origin is None:
            return

        if not self._is_area_selecting and math.hypot(
            offset_x, offset_y
        ) >= self.AREA_SELECT_THRESHOLD:
            self._is_area_selecting = True
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self._area_selector.set_visible(True)
            self.set_cursor_from_name("crosshair")

        if not self._is_area_selecting:
            return

        start_x, start_y = self._drag_origin
        self._selection_end = self._clamp_to_visible_image(
            start_x + offset_x,
            start_y + offset_y,
        )
        self.queue_allocate()

    def _handle_drag_end(
        self,
        gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        self._handle_drag_update(gesture, offset_x, offset_y)

        if self._is_area_selecting:
            selected = [
                text
                for text, button in zip(self._texts, self._buttons)
                if self._selection_intersects(button.get_allocation())
            ]
            self._select_texts(selected, keep_highlight=True)

        self._drag_origin = None
        self._selection_start = None
        self._selection_end = None
        self._is_area_selecting = False
        self._area_selector.set_visible(False)
        self.set_cursor(None)

    def _clamp_to_visible_image(self, x: float, y: float) -> tuple[float, float]:
        left = max(0.0, self._image_rect.get_x())
        top = max(0.0, self._image_rect.get_y())
        right = min(
            float(self.get_width()),
            self._image_rect.get_x() + self._image_rect.get_width(),
        )
        bottom = min(
            float(self.get_height()),
            self._image_rect.get_y() + self._image_rect.get_height(),
        )
        return max(left, min(right, x)), max(top, min(bottom, y))

    def _selection_bounds(self) -> tuple[float, float, float, float] | None:
        if self._selection_start is None or self._selection_end is None:
            return None

        start_x, start_y = self._selection_start
        end_x, end_y = self._selection_end
        return (
            min(start_x, end_x),
            min(start_y, end_y),
            max(start_x, end_x),
            max(start_y, end_y),
        )

    def _selection_intersects(self, allocation: Gdk.Rectangle) -> bool:
        bounds = self._selection_bounds()
        if bounds is None:
            return False

        left, top, right, bottom = bounds
        return (
            allocation.x < right
            and allocation.x + allocation.width > left
            and allocation.y < bottom
            and allocation.y + allocation.height > top
        )

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
        self._selected_texts = []

        for text in self._texts:
            button = Gtk.Button()
            button.add_css_class("text-overlay-button")
            button.set_tooltip_text(text.text)
            button.connect("clicked", self._handle_click, text)
            button.set_parent(self)
            self._buttons.append(button)

        self.queue_allocate()

    def _handle_click(self, _button: Gtk.Button, text: Text) -> None:
        self._select_texts([text], keep_highlight=False)

    def _select_texts(
        self,
        texts: Sequence[Text],
        *,
        keep_highlight: bool,
    ) -> None:
        selected_ids = {id(text) for text in texts}
        self._selected_texts = list(texts)

        for text, button in zip(self._texts, self._buttons):
            if id(text) in selected_ids:
                if keep_highlight:
                    button.add_css_class("selected")
                else:
                    button.remove_css_class("selected")
                button.add_css_class("success")
                GLib.timeout_add(
                    1000,
                    lambda button=button: button.remove_css_class("success"),
                )
            else:
                button.remove_css_class("selected")

        if self._selected_texts and self._on_texts_selected is not None:
            self._on_texts_selected(self._selected_texts)

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

        scale = (
            min(width / self._image_width, height / self._image_height)
            * self._zoom
        )
        scaled_width = self._image_width * scale
        scaled_height = self._image_height * scale
        centered_x = (width - scaled_width) / 2
        centered_y = (height - scaled_height) / 2
        offset_x = centered_x + self._pan_x
        offset_y = centered_y + self._pan_y

        if scaled_width <= width:
            offset_x = centered_x
        else:
            offset_x = max(width - scaled_width, min(0.0, offset_x))

        if scaled_height <= height:
            offset_y = centered_y
        else:
            offset_y = max(height - scaled_height, min(0.0, offset_y))

        self._pan_x = offset_x - centered_x
        self._pan_y = offset_y - centered_y

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

        selection_bounds = self._selection_bounds()
        if self._area_selector.get_visible() and selection_bounds is not None:
            left, top, right, bottom = selection_bounds
            selection_allocation = Gdk.Rectangle()
            selection_allocation.x = math.floor(left)
            selection_allocation.y = math.floor(top)
            selection_allocation.width = max(
                1, math.ceil(right) - selection_allocation.x
            )
            selection_allocation.height = max(
                1, math.ceil(bottom) - selection_allocation.y
            )
            self._area_selector.size_allocate(selection_allocation, -1)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if self._image_rect.get_width() < 1 or self._image_rect.get_height() < 1:
            return

        snapshot.append_texture(self._texture, self._image_rect)

        if self._ocr_gradient.get_visible():
            self.snapshot_child(self._ocr_gradient, snapshot)

        for button in self._buttons:
            self.snapshot_child(button, snapshot)

        if self._area_selector.get_visible():
            self.snapshot_child(self._area_selector, snapshot)

        if not self._ocr_scheduled and not self._ocr_started:
            self._ocr_scheduled = True
            GLib.idle_add(self._start_ocr)

    def do_dispose(self) -> None:
        self._disposed = True
        self._stop_ocr_animation()
        if self._ocr_gradient.get_parent() is self:
            self._ocr_gradient.unparent()
        if self._area_selector.get_parent() is self:
            self._area_selector.unparent()
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
                background-color: transparent;
                border-color: transparent;
                border-width: 3px;
                border-style: solid;
                transition: background-color 250ms ease-out;
                animation: text-overlay-button-fade-in 250ms ease-out;
            }

            .text-overlay-button:hover {
                background-color: alpha(@accent_color, 0.4);
            }

            .text-overlay-button.selected {
                background-color: alpha(@accent_color, 0.28);
            }

            .text-overlay-button.selected:hover {
                background-color: alpha(@accent_color, 0.42);
            }

            .text-area-selector {
                background-color: alpha(@accent_color, 0.12);
                border: 1px solid alpha(@accent_color, 0.85);
                border-radius: 6px;
            }

            .text-overlay-button.success {
                background-color: transparent;
                background-image: none;
                box-shadow: none;
                animation: text-overlay-button-border-spin 1s linear both;
            }

            @keyframes text-overlay-button-border-spin {
                0% {
                    border-color:
                        rgba(35, 120, 255, 0)
                        rgba(0, 210, 190, 0)
                        rgba(30, 210, 115, 0)
                        rgba(0, 210, 190, 0);
                }

                15% {
                    border-color:
                        rgba(35, 120, 255, 0.5)
                        rgba(0, 210, 190, 0.5)
                        rgba(30, 210, 115, 0.5)
                        rgba(0, 210, 190, 0.5);
                }

                35% {
                    border-color:
                        rgba(0, 210, 190, 0.5)
                        rgba(35, 120, 255, 0.5)
                        rgba(0, 210, 190, 0.5)
                        rgba(30, 210, 115, 0.5);
                }

                55% {
                    border-color:
                        rgba(30, 210, 115, 0.5)
                        rgba(0, 210, 190, 0.5)
                        rgba(35, 120, 255, 0.5)
                        rgba(0, 210, 190, 0.5);
                }

                75% {
                    border-color:
                        rgba(0, 210, 190, 0.5)
                        rgba(30, 210, 115, 0.5)
                        rgba(0, 210, 190, 0.5)
                        rgba(35, 120, 255, 0.5);
                }

                85% {
                    border-color:
                        rgba(35, 120, 255, 0.5)
                        rgba(0, 210, 190, 0.5)
                        rgba(30, 210, 115, 0.5)
                        rgba(0, 210, 190, 0.5);
                }

                100% {
                    border-color:
                        rgba(35, 120, 255, 0)
                        rgba(0, 210, 190, 0)
                        rgba(30, 210, 115, 0)
                        rgba(0, 210, 190, 0);
                }
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
