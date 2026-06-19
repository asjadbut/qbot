"""Generate QBot icon files (qbot.ico + qbot_logo.png) from the source logo image.

The source is qbot_logo_source.png in the project root. Running this script
regenerates both the Windows .ico (all standard sizes) and the 64x64 UI PNG.
"""
from PIL import Image
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SOURCE = os.path.join(_ROOT, "qbot_logo_source.png")


def generate_icon():
    """Regenerate qbot.ico and qbot_logo.png from qbot_logo_source.png."""
    if not os.path.exists(_SOURCE):
        # Fall back to qbot_logo.png itself as the source
        src = os.path.join(_ROOT, "qbot_logo.png")
    else:
        src = _SOURCE

    img = Image.open(src).convert("RGBA")

    sizes = [256, 128, 64, 48, 32, 16]
    frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]

    icon_path = os.path.join(_ROOT, "qbot.ico")
    frames[0].save(icon_path, format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=frames[1:])
    print(f"Icon saved to {icon_path}")

    png_path = os.path.join(_ROOT, "qbot_logo.png")
    frames[2].save(png_path, format="PNG")  # 64×64
    print(f"Logo PNG saved to {png_path}")

    return icon_path


if __name__ == "__main__":
    generate_icon()
