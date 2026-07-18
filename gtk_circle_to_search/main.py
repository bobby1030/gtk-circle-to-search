"""Entry point for the application."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application, letting GApplication handle file arguments."""
    from .ui import App

    application_argv = sys.argv if argv is None else [sys.argv[0], *argv]
    app = App(application_id="com.github.circle-to-search")

    return app.run(application_argv)
