from src.ui import MainWindow

if __name__ == "__main__":
    import sys

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
