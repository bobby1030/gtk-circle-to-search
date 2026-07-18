"""Load the application's compiled GResource bundle."""

from __future__ import annotations

from importlib.resources import as_file, files

from gi.repository import Gio

_RESOURCE: Gio.Resource | None = None


def register_resources() -> None:
    """Register the packaged GTK resources once per process."""
    global _RESOURCE
    if _RESOURCE is not None:
        return

    resource_ref = files(__package__).joinpath("circle-to-search.gresource")
    with as_file(resource_ref) as resource_path:
        _RESOURCE = Gio.Resource.load(str(resource_path))

    Gio.resources_register(_RESOURCE)
