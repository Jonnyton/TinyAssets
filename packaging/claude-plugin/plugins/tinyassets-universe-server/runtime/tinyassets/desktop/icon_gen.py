"""Icon generator for TinyAssets desktop application.

Generates a stylized open-book icon with a quill using Pillow.
Color scheme: deep blue/purple background, gold/amber book.

Exports
-------
generate_icon(output_path)
    Render multi-size .ico to disk.
create_icon_image(size)
    Return a single PIL Image at the requested size.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


def create_icon_image(size: int = 64) -> Image.Image:
    """Create a branded TinyAssets icon at the given pixel size.

    Draws a stylized open book with a quill pen on a deep blue-purple
    background with gold/amber accents.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded-feel circle with deep blue-purple gradient effect
    bg_color = (30, 27, 75)  # deep indigo
    draw.ellipse([0, 0, size - 1, size - 1], fill=bg_color)

    # Inner glow ring
    margin = max(1, size // 16)
    glow_color = (55, 48, 110)
    draw.ellipse(
        [margin, margin, size - 1 - margin, size - 1 - margin],
        fill=glow_color,
    )

    # Book colors
    gold = (218, 165, 32)       # book cover / spine
    page_color = (245, 235, 210)  # pages
    quill_color = (255, 215, 0)   # quill highlight

    cx, cy = size / 2, size / 2

    # --- Open book (two pages) ---
    # Left page
    left_page = [
        (cx - size * 0.35, cy - size * 0.12),
        (cx - size * 0.04, cy - size * 0.18),
        (cx - size * 0.04, cy + size * 0.22),
        (cx - size * 0.35, cy + size * 0.16),
    ]
    draw.polygon(left_page, fill=page_color, outline=gold)

    # Right page
    right_page = [
        (cx + size * 0.35, cy - size * 0.12),
        (cx + size * 0.04, cy - size * 0.18),
        (cx + size * 0.04, cy + size * 0.22),
        (cx + size * 0.35, cy + size * 0.16),
    ]
    draw.polygon(right_page, fill=page_color, outline=gold)

    # Spine line
    spine_width = max(1, size // 32)
    draw.line(
        [(cx, cy - size * 0.20), (cx, cy + size * 0.24)],
        fill=gold,
        width=spine_width,
    )

    # Page lines on left page (text illusion)
    line_width = max(1, size // 64)
    for i in range(3):
        y_off = cy - size * 0.06 + i * size * 0.07
        x_start = cx - size * 0.30
        x_end = cx - size * 0.08
        draw.line(
            [(x_start, y_off), (x_end, y_off)],
            fill=(180, 160, 120),
            width=line_width,
        )

    # Page lines on right page
    for i in range(3):
        y_off = cy - size * 0.06 + i * size * 0.07
        x_start = cx + size * 0.08
        x_end = cx + size * 0.30
        draw.line(
            [(x_start, y_off), (x_end, y_off)],
            fill=(180, 160, 120),
            width=line_width,
        )

    # --- Quill pen (diagonal from upper-right) ---
    quill_width = max(1, size // 20)

    # Quill shaft
    tip_x = cx + size * 0.05
    tip_y = cy + size * 0.10
    end_x = cx + size * 0.38
    end_y = cy - size * 0.35

    draw.line(
        [(tip_x, tip_y), (end_x, end_y)],
        fill=quill_color,
        width=quill_width,
    )

    # Feather vanes (two small triangles on shaft)
    angle = math.atan2(end_y - tip_y, end_x - tip_x)
    perp_angle = angle + math.pi / 2
    mid_x = (tip_x + end_x) * 0.65 + end_x * 0.35
    mid_y = (tip_y + end_y) * 0.65 + end_y * 0.35

    feather_len = size * 0.10
    fx1 = mid_x + feather_len * math.cos(perp_angle)
    fy1 = mid_y + feather_len * math.sin(perp_angle)
    fx2 = mid_x - feather_len * math.cos(perp_angle)
    fy2 = mid_y - feather_len * math.sin(perp_angle)

    # Upper feather vane
    upper_tip_x = mid_x + size * 0.06 * math.cos(angle)
    upper_tip_y = mid_y + size * 0.06 * math.sin(angle)
    draw.polygon(
        [(mid_x, mid_y), (fx1, fy1), (upper_tip_x, upper_tip_y)],
        fill=(200, 180, 50),
    )
    # Lower feather vane
    draw.polygon(
        [(mid_x, mid_y), (fx2, fy2), (upper_tip_x, upper_tip_y)],
        fill=(180, 155, 40),
    )

    # Nib (small triangle at writing end)
    nib_len = size * 0.04
    nib_x = tip_x - nib_len * math.cos(angle)
    nib_y = tip_y - nib_len * math.sin(angle)
    nib_w = size * 0.02
    draw.polygon(
        [
            (nib_x, nib_y),
            (tip_x + nib_w * math.cos(perp_angle), tip_y + nib_w * math.sin(perp_angle)),
            (tip_x - nib_w * math.cos(perp_angle), tip_y - nib_w * math.sin(perp_angle)),
        ],
        fill=(60, 40, 20),
    )

    return img.convert("RGB")


def generate_icon(output_path: str | Path | None = None) -> Path:
    """Generate a multi-size .ico file.

    Parameters
    ----------
    output_path : str or Path, optional
        Where to write the .ico file.  Defaults to
        ``tinyassets/desktop/app.ico``.

    Returns
    -------
    Path
        The path to the generated .ico file.
    """
    if output_path is None:
        output_path = Path(__file__).parent / "app.ico"
    else:
        output_path = Path(output_path)

    sizes = [16, 32, 48, 256]
    images = [create_icon_image(s) for s in sizes]

    # ICO format: save the largest, append the rest
    images[-1].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )

    return output_path
