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

    _compile_blueprints()

    from gi.repository import Adw

    from src.ocr.ocr import Image, Text

    app = Adw.Application(application_id="com.github.circle-to-search")
    app.register()

    image = Image("tests/spotify.png")
    image.recognize_text()
    texts = image.recognized_texts

    def on_text_clicked(text: Text) -> None:
        print(f"Clicked on text: {text.text}")

    window = MainWindow(
        application=app,
        image=image,
        texts=texts,
        on_text_clicked=on_text_clicked,
    )
    window.present()

    sys.exit(app.run(sys.argv))
