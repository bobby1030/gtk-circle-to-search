import asyncio
import sys
import gi
import pytesseract
from pydantic import BaseModel
import base64
import json
from PIL import Image

gi.require_version("Xdp", "1.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.events import GLibEventLoopPolicy  # noqa: E402
from gi.repository import Xdp, Gio, Gtk, Adw, GdkPixbuf, Gdk  # noqa: E402


class TextBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    text: str


class TextDetectionResult(BaseModel):
    text_boxes: list[TextBox]


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


def get_bounding_boxes_paddleocr(image_uri):
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


def make_drawing_area(image_uri: str) -> Gtk.DrawingArea:
    drawing_area = Gtk.DrawingArea()
    area_w = 960
    area_h = 720
    drawing_area.set_content_width(area_w)
    drawing_area.set_content_height(area_h)

    image_file = Gio.File.new_for_uri(image_uri)
    stream = image_file.read(None)

    pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)

    # Scale down to fit drawing area while preserving aspect ratio
    img_w = pixbuf.get_width()
    img_h = pixbuf.get_height()
    s = min(area_w / img_w, area_h / img_h, 1.0)  # only scale down

    # Border boxes that highlight texts detected in the image
    # [{x1, y1, x2, y2, text}, ...]
    bboxes = get_bounding_boxes_paddleocr(image_uri)
    bboxes_active = [False for bbox in bboxes]  # Track active state of each box

    def on_draw(area, context, area_w, area_h, user_data):
        # Draw the image onto the drawing area
        if s < 1.0:
            pixbuf_scaled = pixbuf.scale_simple(
                s * img_w, s * img_h, GdkPixbuf.InterpType.BILINEAR
            )
        Gdk.cairo_set_source_pixbuf(context, pixbuf_scaled, 0, 0)
        context.paint()

        # Draw bounding boxes around detected text
        for i, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
            context.set_source_rgba(1, 0, 0, 0.8)  # Red color
            context.rectangle(s * x1, s * y1, s * (x2 - x1), s * (y2 - y1))
            context.stroke()

            # If the box is active, fill it with a semi-transparent color
            if bboxes_active[i]:
                context.set_source_rgba(1, 0, 0, 0.3)
                context.rectangle(s * x1, s * y1, s * (x2 - x1), s * (y2 - y1))
                context.fill()

    def on_click(gesture, n_press, x, y):
        # Check if the click is inside any of the bounding boxes and update their active state
        # (x, y) are in scaled coordinates, dividing by s to get original image coordinates
        for i, bbox in enumerate(bboxes):
            bboxes_active[i] = is_inside_box(
                x / s, y / s, bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
            )

        # Update the status label with the detected text if the box is active
        if get_unique_active_box(bboxes_active, bboxes):
            active_box_idx = get_unique_active_box(bboxes_active, bboxes)
            status_label.set_text(f"Detected text: {bboxes[active_box_idx]['text']}")

        drawing_area.queue_draw()  # Trigger a redraw to update the bounding boxes

    drawing_area.set_draw_func(on_draw, None)

    # Make drawing area clickable
    gesture_click = Gtk.GestureClick()
    gesture_click.connect("pressed", on_click)
    drawing_area.add_controller(gesture_click)

    status_label = Gtk.Label(label="Click on the image to see detected text.")

    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    container.append(drawing_area)
    container.append(status_label)

    return container


def show_app(image_uri: str) -> None:
    app = Adw.Application(application_id="com.github.py_screenshot.viewer")

    def on_activate(app: Adw.Application) -> None:
        window = Adw.ApplicationWindow(application=app, title="Image Viewer")
        window.set_default_size(960, 720)

        drawing_area = make_drawing_area(image_uri)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.append(drawing_area)

        window.set_content(container)
        window.present()

    app.connect("activate", on_activate)
    app.connect("shutdown", lambda _: app.quit())
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
