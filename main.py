import shutil
import subprocess
from pathlib import Path


def _compile_blueprints() -> None:
    """Compile the Blueprint sources before GTK loads their templates."""
    compiler = shutil.which("blueprint-compiler")
    if compiler is None:
        raise RuntimeError("blueprint-compiler is required to run the app")

    assets_dir = Path(__file__).resolve().parent / "src" / "ui" / "assets"
    blueprints = sorted(assets_dir.glob("*.blp"))
    if not blueprints:
        return

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
    from src.ui import App

    _compile_blueprints()

    app = App(application_id="com.github.circle-to-search")
    sys.exit(app.run(sys.argv))
