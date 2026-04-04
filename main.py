import asyncio
import sys
import gi
import pytesseract

gi.require_version("Xdp", "1.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.events import GLibEventLoopPolicy  # noqa: E402
from gi.repository import Xdp, Gio, Gtk, Adw, GdkPixbuf, Gdk  # noqa: E402


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
    drawing_area.set_content_width(800)
    drawing_area.set_content_height(600)

    # Border boxes that highlight texts detected in the image
    # [{x1, y1, x2, y2, text}, ...]
    bboxes = get_bounding_boxes(image_uri)
    bboxes_active = [False for bbox in bboxes]  # Track active state of each box

    def on_draw(area, context, width, height, user_data):
        # Draw the image onto the drawing area
        image_file = Gio.File.new_for_uri(image_uri)
        stream = image_file.read(None)

        pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint()

        # Draw bounding boxes around detected text
        for i, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
            context.set_source_rgba(1, 0, 0, 0.8)  # Red color
            context.rectangle(x1, y1, x2 - x1, y2 - y1)
            context.stroke()

            # If the box is active, fill it with a semi-transparent color
            if bboxes_active[i]:
                context.set_source_rgba(1, 0, 0, 0.3)
                context.rectangle(x1, y1, x2 - x1, y2 - y1)
                context.fill()

    def on_click(gesture, n_press, x, y):
        # Check if the click is inside any of the bounding boxes and update their active state
        for i, bbox in enumerate(bboxes):
            bboxes_active[i] = is_inside_box(
                x, y, bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
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
