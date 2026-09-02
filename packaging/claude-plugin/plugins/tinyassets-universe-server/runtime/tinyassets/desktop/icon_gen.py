"""The TinyAssets mark, and the one place its geometry lives.

The mark is the monogram **TA** set in Fraunces SemiBold over a single accent
rule -- a masthead, not a symbol to decode. Cream on ink; the rule is the one
warm accent, and it is the same ruled line the site uses to separate sections.

Every rendering comes from this module: the Windows tray ``.ico``
(``generate_icon``), the brand exports under ``WebSite/brand/`` and ``assets/``,
the desktop and Android app icons, and the SVG the site inlines
(``WebSite/brand/render_marks.py`` imports ``draw_mark`` and ``mark_svg``).
Change the numbers here, re-run that script, and every surface follows.

``TA_PATH`` holds the letterforms as SVG path data in a 64x64 viewBox, so no
font file has to ship or be installed to draw the mark. It was extracted once
from Fraunces SemiBold (Google Fonts v38, upem 2000, glyphs T and A, -60 units
of tracking, ink scaled to 46 units wide on a baseline at y=43) with
``fontTools``' ``SVGPathPen``. To change the letterforms, re-extract with those
parameters rather than editing the numbers by hand.

Exports
-------
draw_mark(size, tile=False)
    A PIL image of the mark at ``size`` px (RGBA; ``tile`` puts it on the
    rounded ink square the app icons use).
mark_svg(tile=False)
    The same drawing as an SVG document string.
create_icon_image(size)
    The app-icon tile, for the tray and the launcher.
generate_icon(output_path)
    Render the multi-size tray ``.ico``.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# ---- palette (matches WebSite/design-system/src/styles/tokens.css) ----------
INK = (0x14, 0x14, 0x0F)      # --bg-0, the ground the site sits on
CREAM = (0xF2, 0xEF, 0xE6)    # --fg-1, the letterforms
ACCENT = (0xE0, 0x70, 0x3F)   # --ember-600, the rule

INK_HEX = "#14140f"
CREAM_HEX = "#f2efe6"
ACCENT_HEX = "#e0703f"

# ---- geometry, in a 64 x 64 box -------------------------------------------
VIEWBOX = 64.0
TILE_RADIUS = 13.0            # rounded corner of the app-icon tile
RULE_X0, RULE_X1 = 9.0, 55.0  # the accent rule under the monogram
RULE_Y = 49.0
RULE_H = 4.0

_SUPERSAMPLE = 4

# The monogram outlines. See the module docstring for how these were produced.
TA_PATH = (
    "M13.92 19.24H25.86Q26.49 19.24 26.90 19.08Q27.31 18.92 27.62 18.77Q27.93 18.61 28.31 "
    "18.61Q28.87 18.61 29.16 18.89Q29.44 19.16 29.61 19.80L30.75 25.28Q30.85 25.76 30.68 "
    "26.06Q30.51 26.37 30.11 26.45Q29.72 26.52 29.42 26.38Q29.12 26.23 28.92 25.81Q28.04 "
    "23.82 27.40 22.80Q26.76 21.77 26.13 21.40Q25.49 21.02 24.59 21.02H22.52V40.17Q22.52 "
    "40.54 22.74 40.78Q22.96 41.01 23.37 41.13L24.34 41.35Q25.05 41.57 25.05 42.22Q25.05 "
    "43.00 24.01 43.00H15.75Q15.24 43.00 14.99 42.79Q14.73 42.58 14.73 42.22Q14.73 41.57 "
    "15.44 41.35L16.41 41.13Q16.84 41.01 17.05 40.78Q17.26 40.54 17.26 "
    "40.17V21.02H15.19Q14.31 21.02 13.66 21.40Q13.02 21.77 12.38 22.80Q11.74 23.82 10.86 "
    "25.81Q10.66 26.23 10.36 26.38Q10.06 26.52 9.67 26.45Q9.27 26.37 9.11 26.06Q8.94 "
    "25.76 9.03 25.28L10.17 19.80Q10.34 19.16 10.62 18.89Q10.91 18.61 11.47 18.61Q11.85 "
    "18.61 12.16 18.77Q12.47 18.92 12.88 19.08Q13.29 19.24 13.92 19.24Z M36.62 "
    "33.34H46.65L46.74 35.11H36.50ZM38.61 42.22Q38.61 42.58 38.36 42.79Q38.12 43.00 37.57 "
    "43.00H32.24Q31.72 43.00 31.46 42.79Q31.21 42.58 31.21 42.22Q31.21 41.96 31.35 "
    "41.79Q31.50 41.61 31.87 41.42L32.43 41.20Q32.94 40.95 33.22 40.54Q33.50 40.13 33.82 "
    "39.10L39.25 22.50Q39.47 21.75 39.37 21.42Q39.27 21.09 38.68 20.89Q38.20 20.74 38.01 "
    "20.52Q37.83 20.31 37.83 20.01Q37.83 19.65 38.08 19.45Q38.34 19.24 38.88 "
    "19.24H47.16Q47.70 19.24 47.96 19.45Q48.21 19.65 48.21 20.01Q48.21 20.33 48.02 "
    "20.53Q47.82 20.74 47.40 20.87Q46.94 21.01 46.85 21.26Q46.77 21.52 46.96 22.09L52.73 "
    "39.49Q53.00 40.34 53.30 40.73Q53.61 41.13 54.17 41.30Q54.66 41.49 54.83 41.69Q55.00 "
    "41.90 55.00 42.22Q55.00 42.58 54.75 42.79Q54.49 43.00 53.95 43.00H46.46Q45.94 43.00 "
    "45.68 42.79Q45.43 42.58 45.43 42.22Q45.43 41.91 45.61 41.73Q45.79 41.54 46.16 "
    "41.42L47.13 41.22Q47.57 41.08 47.55 40.78Q47.53 40.47 47.33 39.81L41.32 21.28L41.88 "
    "20.94L36.06 38.83Q35.84 39.52 35.84 39.97Q35.84 40.42 36.12 40.70Q36.40 40.98 36.98 "
    "41.22L37.89 41.44Q38.23 41.57 38.42 41.74Q38.61 41.91 38.61 42.22Z"
)

_NUM = re.compile(r"[-+]?[0-9]*\.?[0-9]+")


def _flatten(path: str, steps: int = 12) -> list[list[tuple[float, float]]]:
    """Turn the path's M/H/V/L/Q/Z commands into closed polygons.

    TrueType outlines are quadratic, so only ``Q`` curves appear; each is
    sampled at ``steps`` points, which is indistinguishable from the real curve
    once the 4x supersampled render is scaled back down.
    """
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    x = y = 0.0
    for command, raw in re.findall(r"([MLHVQZ])([^MLHVQZ]*)", path, flags=re.I):
        nums = [float(n) for n in _NUM.findall(raw)]
        if command in "Mm":
            if current:
                contours.append(current)
            x, y = nums[0], nums[1]
            current = [(x, y)]
        elif command in "Ll":
            for i in range(0, len(nums), 2):
                x, y = nums[i], nums[i + 1]
                current.append((x, y))
        elif command in "Hh":
            for n in nums:
                x = n
                current.append((x, y))
        elif command in "Vv":
            for n in nums:
                y = n
                current.append((x, y))
        elif command in "Qq":
            for i in range(0, len(nums), 4):
                cx, cy, nx, ny = nums[i : i + 4]
                for step in range(1, steps + 1):
                    t = step / steps
                    u = 1.0 - t
                    current.append(
                        (
                            u * u * x + 2 * u * t * cx + t * t * nx,
                            u * u * y + 2 * u * t * cy + t * t * ny,
                        )
                    )
                x, y = nx, ny
        elif command in "Zz":
            if current:
                contours.append(current)
                current = []
    if current:
        contours.append(current)
    return [c for c in contours if len(c) >= 3]


def _monogram_mask(px: int) -> Image.Image:
    """An 'L' mask of the monogram, even-odd filled so the A keeps its counter."""
    k = px / VIEWBOX
    mask = Image.new("1", (px, px), 0)
    for contour in _flatten(TA_PATH):
        layer = Image.new("1", (px, px), 0)
        ImageDraw.Draw(layer).polygon([(cx * k, cy * k) for cx, cy in contour], fill=1)
        # XOR is the even-odd rule: the A's counter is drawn inside its outer
        # contour, so XOR punches the hole instead of filling it twice.
        mask = ImageChops.logical_xor(mask, layer)
    return mask.convert("L")


def draw_mark(size: int = 64, tile: bool = False) -> Image.Image:
    """Render the mark at ``size`` px. ``tile`` adds the rounded ink square."""
    if size < 8:
        raise ValueError("mark size must be at least 8 px")
    size = int(size)
    px = size * _SUPERSAMPLE
    k = px / VIEWBOX
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if tile:
        draw.rounded_rectangle(
            [0, 0, px - 1, px - 1], radius=TILE_RADIUS * k, fill=INK + (255,)
        )

    letters = Image.new("RGBA", (px, px), CREAM + (255,))
    letters.putalpha(_monogram_mask(px))
    img.alpha_composite(letters)

    draw.rectangle(
        [RULE_X0 * k, RULE_Y * k, RULE_X1 * k, (RULE_Y + RULE_H) * k],
        fill=ACCENT + (255,),
    )
    return img.resize((size, size), Image.LANCZOS)


def mark_svg(tile: bool = False) -> str:
    """The same drawing as SVG (viewBox 0 0 64 64)."""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'width="64" height="64" role="img" aria-label="TinyAssets">'
    ]
    if tile:
        parts.append(f'<rect width="64" height="64" rx="{TILE_RADIUS:g}" fill="{INK_HEX}"/>')
    parts.append(f'<path d="{TA_PATH}" fill="{CREAM_HEX}"/>')
    parts.append(
        f'<rect x="{RULE_X0:g}" y="{RULE_Y:g}" width="{RULE_X1 - RULE_X0:g}" '
        f'height="{RULE_H:g}" fill="{ACCENT_HEX}"/>'
    )
    parts.append("</svg>")
    return "".join(parts) + "\n"


def create_icon_image(size: int = 64) -> Image.Image:
    """The app-icon tile: the monogram on its rounded ink square."""
    return draw_mark(size, tile=True)


def generate_icon(output_path: str | Path | None = None) -> Path:
    """Generate the multi-size tray ``.ico`` (16, 32, 48, 256).

    Defaults to ``tinyassets/desktop/app.ico``.
    """
    if output_path is None:
        output_path = Path(__file__).parent / "app.ico"
    else:
        output_path = Path(output_path)

    sizes = [16, 32, 48, 256]
    images = [create_icon_image(s) for s in sizes]
    images[-1].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    return output_path


if __name__ == "__main__":  # pragma: no cover
    print(generate_icon())
