import shutil
import subprocess
from pathlib import Path

from gtk_circle_to_search.main import main


def _compile_blueprints() -> None:
    """Compile the Blueprint sources before GTK loads their templates."""
    compiler = shutil.which("blueprint-compiler")
    if compiler is None:
        raise RuntimeError("blueprint-compiler is required to run the app")

    assets_dir = (
        Path(__file__).resolve().parent
        / "gtk_circle_to_search"
        / "ui"
        / "assets"
    )
    blueprints = sorted(assets_dir.glob("*.blp"))
    if not blueprints:
        return

    # Pretify the generated .ui files
    subprocess.run(
        [
            compiler,
            "format",
            "-f",
            *(str(blueprint) for blueprint in blueprints),
        ],
        check=True,
    )

    subprocess.run(
        [
            compiler,
            "batch-compile",
            str(assets_dir),
            str(assets_dir),
            *(str(blueprint) for blueprint in blueprints),
        ],
        check=True,
    )


if __name__ == "__main__":
    import sys

    _compile_blueprints()
    sys.exit(main())
