import asyncio
import sys
import gi
import pytesseract
from pydantic import BaseModel
import base64
import json
from PIL import Image
import subprocess

from widgets import ScreenshotView

gi.require_version("Xdp", "1.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.events import GLibEventLoopPolicy  # noqa: E402
from gi.repository import Xdp, Gio, Gtk, Adw, Gdk, Graphene  # noqa: E402


class TextBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    text: str


class TextDetectionResult(BaseModel):
    text_boxes: list[TextBox]


def wl_copy(text):
    """Copy text to clipboard using wl-copy command."""
    try:
        process = subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
    except subprocess.CalledProcessError as e:
        print("Failed to copy text to clipboard.")
    except Exception as e:
        print("Error copying text to clipboard:", e)


async def take_screenshot():
    "Take a screenshot using the xdg-desktop-portal API and return the URI of the saved screenshot."
    portal = Xdp.Portal()

    flags = Xdp.ScreenshotFlags.INTERACTIVE
    screenshot_uri = await portal.take_screenshot(None, flags)

    return screenshot_uri


def get_bounding_boxes(image_uri):
    """Use pytesseract to get bounding boxes of detected text in the image."""
    path = Gio.File.new_for_uri(image_uri).get_path()

    try:
        # Get bounding box data from pytesseract
        data = pytesseract.image_to_data(
            path, lang="eng+chi_tra", output_type=pytesseract.Output.DICT
        )
        print(data)

        bboxes = []
        for i in range(len(data["level"])):
            if int(data["conf"][i]) > 0:  # Filter out low-confidence detections
                bboxes.append(
                    {
                        "x1": data["left"][i],
                        "y1": data["top"][i],
                        "x2": data["left"][i] + data["width"][i],
                        "y2": data["top"][i] + data["height"][i],
                        "text": data["text"][i],
                    }
                )
        return bboxes
    except Exception as e:
        print("Error getting bounding boxes:", e)
        return []


def get_bounding_boxes_llama(image_uri):
    """Use llama.cpp-supported model to get bounding boxes of detected text in the image."""
    from llama_cpp import Llama  # noqa: E402
    from llama_cpp.llama_chat_format import Qwen35ChatHandler  # noqa: E402

    chat_handler = Qwen35ChatHandler.from_pretrained(
        repo_id="unsloth/Qwen3.5-9B-GGUF",
        filename="mmproj-F16.gguf",
        image_min_tokens=1024,
        enable_thinking=False,
    )
    llm = Llama.from_pretrained(
        repo_id="unsloth/Qwen3.5-9B-GGUF",
        filename="Qwen3.5-9B-Q4_K_M.gguf",
        chat_handler=chat_handler,
        n_ctx=4096,
        n_gpu_layers=-1,
    )
    with open(Gio.File.new_for_uri(image_uri).get_path(), "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

    response = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": """
                    You are an expert in text detection in images. You can analyze
                    the image and return the bounding boxes of detected text in the
                    specified format. Detect text in the image and return their 
                    bounding boxes in the format of {x1, y1, x2, y2, text},
                    where (x1, y1) is the top-left corner and (x2, y2) is the
                    bottom-right corner of the bounding box, and text is the
                    detected text within the bounding box.
                """,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    }
                ],
            },
        ],
        response_format={
            "type": "json_object",
            "schema": TextDetectionResult.model_json_schema(),
        },
    )

    bboxes = json.loads(response["choices"][0]["message"]["content"])["text_boxes"]

    # Qwen uses 1000-based coordinates, convert them to pixel-based coordinates
    image = Image.open(Gio.File.new_for_uri(image_uri).get_path())
    for bbox in bboxes:
        bbox["x1"] = int(bbox["x1"] * image.width / 1000)
        bbox["y1"] = int(bbox["y1"] * image.height / 1000)
        bbox["x2"] = int(bbox["x2"] * image.width / 1000)
        bbox["y2"] = int(bbox["y2"] * image.height / 1000)

    return bboxes


def get_bounding_boxes_paddleocr(image_uri, score_threshold=0.8):
    """Use PaddleOCR to get bounding boxes of detected text in the image."""
    from paddleocr import PaddleOCR  # noqa: E402

    ocr = PaddleOCR(
        use_doc_unwarping=False,  # Disable doc unwarping to get bounding boxes in the original image coordinates
        use_doc_orientation_classify=False,  # Disable orientation classification (screenshots are usually correctly oriented)
        use_textline_orientation=False,  # Disable textline orientation (we only care about bounding boxes, not orientation)
    )
    path = Gio.File.new_for_uri(image_uri).get_path()
    result = ocr.predict(path)[0]

    length = len(result["rec_texts"])

    bboxes = []
    for i in range(length):
        if result["rec_scores"][i] > score_threshold:
            # rec_boxes is a length-by-4 ndarray, each row is a tuple of (x1,y1,x2,y2)
            bboxes.append(
                {
                    "x1": int(result["rec_boxes"][i, 0]),
                    "y1": int(result["rec_boxes"][i, 1]),
                    "x2": int(result["rec_boxes"][i, 2]),
                    "y2": int(result["rec_boxes"][i, 3]),
                    "text": result["rec_texts"][i],
                }
            )

    return bboxes


def is_inside_box(x, y, x1, y1, x2, y2):
    """Check if the point (x, y) is inside the box defined by (x1, y1, x2, y2)."""
    return x1 <= x <= x2 and y1 <= y <= y2


def get_unique_active_box(bboxes_active, bboxes):
    """Return the index of the unique active box, or the smallest active box if there are multiple active boxes."""
    bboxes_size = [
        (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]) for bbox in bboxes
    ]
    active_boxes = [i for i, active in enumerate(bboxes_active) if active]
    if len(active_boxes) == 1:
        return active_boxes[0]
    elif len(active_boxes) > 1:
        return min(active_boxes, key=lambda i: bboxes_size[i])
    return None


class App(Adw.Application):
    def __init__(self, screenshot_uri):
        super().__init__(application_id="me.bobbyho.GtkCircleToSearch")
        self.screenshot_uri = screenshot_uri
        self.screenshot_path = Gio.File.new_for_uri(screenshot_uri).get_path()

        self.connect("activate", self.on_activate)
        self.connect("shutdown", lambda _: self.quit())

    def on_activate(self, app):
        self.window = MainWindow(self)
        self.window.present()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Circle to Search")
        self.set_default_size(960, 720)

        def box_button_onclick(box):
            wl_copy(box.get("text", ""))
            text_buffer.set_text(f"Copied to clipboard: {box.get('text', '')}")

        drawing_area = ScreenshotView(
            image_path=app.screenshot_path,
            boxes=get_bounding_boxes_paddleocr(app.screenshot_uri),
            box_button_onclick=box_button_onclick,
        )

        text_buffer = Gtk.TextBuffer(
            text="Click on the detected text in the image to see it here."
        )
        detected_text = Gtk.TextView(
            buffer=text_buffer,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.append(drawing_area)
        container.append(detected_text)

        self.set_content(container)


def show_app(screenshot_uri) -> None:
    app = App(screenshot_uri=screenshot_uri)
    app.run(sys.argv)


async def main():
    screenshot_uri = await take_screenshot()
    print("Screenshot taken:", screenshot_uri)

    # Display the screenshot in a GTK window
    show_app(screenshot_uri)

    # Clean up the screenshot file if needed
    if screenshot_uri:
        file = Gio.File.new_for_uri(screenshot_uri)
        try:
            file.delete()
            print("Screenshot file deleted.")
        except Exception as e:
            print("Failed to delete screenshot file:", e)


if __name__ == "__main__":
    # Set up the GLib event loop
    policy = GLibEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    loop = policy.get_event_loop()

    # Run the main function in the event loop
    loop.run_until_complete(main())
