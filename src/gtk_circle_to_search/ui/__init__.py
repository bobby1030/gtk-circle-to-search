import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Xdp", "1.0")
gi.require_version("XdpGtk4", "1.0")

from ..resources import register_resources  # noqa: E402

register_resources()

from .image_text_overlay import ImageTextOverlay  # noqa: E402
from .translator_pane import TranslatorPane  # noqa: E402
from .main_window import MainWindow  # noqa: E402

__all__ = [
    "ImageTextOverlay",
    "TranslatorPane",
    "MainWindow",
]
