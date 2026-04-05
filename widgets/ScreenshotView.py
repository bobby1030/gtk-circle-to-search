from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gio, Gtk, Adw  # noqa: E402


class BoundingBox(TypedDict, total=False):
    x1: float
    y1: float
    x2: float
    y2: float
    text: str


class ScreenshotView(Gtk.Overlay):
    """Display an image with bounding boxes using built-in GTK widgets.

    Coordinates in bounding boxes are expected in source image pixels.
    """

    def __init__(
        self,
        image_path: str | Path,
        boxes: list[BoundingBox] | None = None,
        box_button_onclick: callable[[BoundingBox], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self._image_path = Path(image_path)
        self._boxes: list[BoundingBox] = boxes or []
        self._box_widgets: list[Gtk.Widget] = []
        self._box_button_onclick = box_button_onclick

        texture = Gdk.Texture.new_from_file(
            Gio.File.new_for_path(str(self._image_path))
        )

        self.image_width = texture.get_width()
        self.image_height = texture.get_height()

        # Draw the image using Gtk.Picture with a Gdk.Texture
        self._picture = Gtk.Picture.new_for_paintable(texture)
        self._picture.set_can_shrink(False)
        self._picture.set_content_fit(Gtk.ContentFit.FILL)
        self.set_child(self._picture)

        # Overlay a fixed container on top of the image to hold bounding box widgets
        self._fixed = Gtk.Fixed()
        self._fixed.set_halign(Gtk.Align.FILL)
        self._fixed.set_valign(Gtk.Align.FILL)
        self.add_overlay(self._fixed)

        # Set the size of the ScreenshotView to match the image, and prevent it from expanding
        self.set_size_request(self.image_width, self.image_height)
        self.set_hexpand(False)
        self.set_vexpand(False)
        self.set_halign(Gtk.Align.START)  # Don't stretch horizontally
        self.set_valign(Gtk.Align.START)  # Don't stretch vertically

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            .box_button {
                background-color: rgba(59, 130, 246, 0.1);
                padding: 0;
            }

            .box_button:hover {
                background-color: rgba(59, 130, 246, 0.3);
            }

            .box_button:active {
                background-color: rgba(59, 130, 246, 0.5);
            }

            .box_button.success {
                background-color: rgba(34, 197, 94, 0.1);
            }
            """
        )
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        # Update bounding box positions and sizes based on the new scaling factors
        self.set_bounding_boxes(self._boxes)

    def set_bounding_boxes(self, boxes: list[BoundingBox]) -> None:
        # Remove old box widgets from the fixed container
        for widget in self._box_widgets:
            self._fixed.remove(widget)

        self._box_widgets.clear()

        # Draw new bounding boxes
        self._boxes = boxes
        for box in self._boxes:
            x1 = int(box["x1"])
            y1 = int(box["y1"])
            x2 = int(box["x2"])
            y2 = int(box["y2"])

            width = max(1, x2 - x1)
            height = max(1, y2 - y1)

            box_button = Gtk.Button()
            box_button.set_size_request(width, height)
            box_button.set_css_classes(["box_button", "pill"])

            if self._box_button_onclick:
                box_button.connect(
                    "clicked", lambda btn, b=box: self.box_button_onclick(btn, b)
                )

            self._fixed.put(box_button, x1, y1)
            self._box_widgets.append(box_button)

    def box_button_onclick(self, button: Gtk.Button, box: BoundingBox) -> None:
        button.add_css_class("success")

        # Call the provided callback with the box data
        self._box_button_onclick(box)
