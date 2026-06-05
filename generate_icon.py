"""Generate QBot icon matching CustomTkinter's blue rounded-square style with 'Q' letter."""
from PIL import Image, ImageDraw, ImageFont
import os


def _round_rect(draw, xy, radius, fill):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    r = radius
    # Corners
    draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
    draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
    draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)
    # Rectangles to fill the gaps
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)


def generate_icon_size(size):
    """Generate a single icon image at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, int(size * 0.06))
    radius = int(size * 0.22)

    # Background: gradient-like effect using two layers
    # Darker blue border/shadow
    _round_rect(draw, (margin, margin, size - margin, size - margin),
                radius, fill=(0, 98, 177, 255))
    # Brighter blue inner area (slightly inset)
    inset = max(1, int(size * 0.04))
    _round_rect(draw, (margin + inset, margin + inset,
                        size - margin - inset, size - margin - inset),
                radius - inset, fill=(2, 156, 255, 255))

    # Draw "Q" letter
    font_size = int(size * 0.52)
    font = None
    for font_name in ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    cx, cy = size / 2, size / 2
    bbox = draw.textbbox((0, 0), "Q", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1] - size * 0.02  # slight upward nudge
    draw.text((tx, ty), "Q", fill=(255, 255, 255, 255), font=font)

    return img


def generate_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    images = [generate_icon_size(s) for s in sizes]

    icon_path = os.path.join(os.path.dirname(__file__), "qbot.ico")
    images[0].save(icon_path, format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    print(f"Icon saved to {icon_path}")

    # Also save a PNG for use in the app UI
    png_path = os.path.join(os.path.dirname(__file__), "qbot_logo.png")
    img_64 = generate_icon_size(64)
    img_64.save(png_path, format="PNG")
    print(f"Logo PNG saved to {png_path}")

    return icon_path


if __name__ == "__main__":
    generate_icon()
