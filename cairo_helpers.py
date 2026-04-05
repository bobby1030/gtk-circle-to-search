import cairo


def draw_rounded_rectangle(ctx: cairo.Context, x, y, width, height, radius):
    """Draw a rounded rectangle on the given Cairo context."""
    ctx.new_sub_path()
    ctx.arc(x + width - radius, y + radius, radius, -90 * (3.14 / 180), 0)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, 90 * (3.14 / 180))
    ctx.arc(
        x + radius, y + height - radius, radius, 90 * (3.14 / 180), 180 * (3.14 / 180)
    )
    ctx.arc(x + radius, y + radius, radius, 180 * (3.14 / 180), 270 * (3.14 / 180))
    ctx.close_path()
