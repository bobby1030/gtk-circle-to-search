import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, Graphene

class ImageCoordinateMap(Gtk.Widget):
    def __init__(self, image_path):
        super().__init__()
        
        # 1. Load the background image as a texture
        self.texture = Gdk.Texture.new_from_filename(image_path)
        self.img_w = self.texture.get_width()
        self.img_h = self.texture.get_height()

        # Store child widgets and their original image coordinates
        self.children_data = []

        # We'll use this to store the rendered image bounds for the draw phase
        self.bg_rect = Graphene.Rect().init(0, 0, self.img_w, self.img_h)

    def add_child_at_coords(self, widget, img_x, img_y):
        """Add a widget at specific coordinates relative to the original image."""
        widget.set_parent(self)
        self.children_data.append({"widget": widget, "x": img_x, "y": img_y})

    def do_measure(self, orientation, for_size):
        # Return 0 for min/natural sizes so the window can be resized freely
        return 0, 0, -1, -1

    def do_size_allocate(self, width, height, baseline):
        """Called automatically whenever the window is resized."""
        
        # 1. Calculate the scale factor to fit the image (Maintain Aspect Ratio)
        scale = min(width / self.img_w, height / self.img_h)
        scaled_w = self.img_w * scale
        scaled_h = self.img_h * scale

        # 2. Calculate offsets to center the image in the newly allocated space
        offset_x = (width - scaled_w) / 2
        offset_y = (height - scaled_h) / 2

        # Save the background bounds for do_snapshot
        self.bg_rect = Graphene.Rect().init(offset_x, offset_y, scaled_w, scaled_h)

        # 3. Position each child widget
        for item in self.children_data:
            child = item["widget"]
            img_x = item["x"]
            img_y = item["y"]

            # Ask the child how big it wants to be (e.g., how wide the button text is)
            _, nat_w, _, _ = child.measure(Gtk.Orientation.HORIZONTAL, -1)
            _, nat_h, _, _ = child.measure(Gtk.Orientation.VERTICAL, -1)

            # Map the original image coordinates to the new screen coordinates
            alloc_x = int(offset_x + img_x * scale)
            alloc_y = int(offset_y + img_y * scale)

            # Assign the new position to the child widget
            alloc = Gdk.Rectangle()
            alloc.x = alloc_x
            alloc.y = alloc_y
            alloc.width = nat_w/2
            alloc.height = nat_h/2
            
            child.size_allocate(alloc, baseline)

    def do_snapshot(self, snapshot):
        """Called automatically when the widget needs to be drawn."""
        # 1. Draw the background texture
        snapshot.append_texture(self.texture, self.bg_rect)

        # 2. Ask GTK to draw each child widget on top
        for item in self.children_data:
            self.snapshot_child(item["widget"], snapshot)

    def do_dispose(self):
        """Clean up children to prevent memory leaks."""
        while self.children_data:
            item = self.children_data.pop()
            item["widget"].unparent()


class MyApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.example.ImageMap")

    def do_activate(self):
        window = Gtk.ApplicationWindow(application=self, title="Coordinate Overlay System")
        window.set_default_size(800, 600)

        # Initialize the custom widget (Make sure you have an image file here)
        try:
            map_widget = ImageCoordinateMap('test-screenshots/firefox.png')
        except Exception as e:
            print(f"Error loading image: {e}")
            return

        # Create buttons and add them using original image coordinates
        btn1 = Gtk.Button(label="Point A (500, 300)")
        btn1.add_css_class("suggested-action") # Optional styling
        map_widget.add_child_at_coords(btn1, 500, 300)

        btn2 = Gtk.Button(label="Point B (1200, 800)")
        btn2.add_css_class("destructive-action")
        map_widget.add_child_at_coords(btn2, 1200, 800)

        text = Gtk.Label(label="This is a label at (800, 600)")
        text.add_css_class("info")
        map_widget.add_child_at_coords(text, 800, 600)

        window.set_child(map_widget)
        window.present()

if __name__ == "__main__":
    app = MyApp()
    sys.exit(app.run(sys.argv))