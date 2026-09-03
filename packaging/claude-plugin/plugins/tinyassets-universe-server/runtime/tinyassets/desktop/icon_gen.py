"""The TinyAssets mark, and the one place its geometry lives.

The mark is a circular badge: **Mount Baker seen from the south**, a **wolf
howling** on the snowfield, the **moon** in the brand's ember, and the
**galaxy** arcing overhead. The mountain is the broad glaciated dome it
actually is from that side, with the Black Buttes as the jagged rock group to
the west (left from the south) and a few ruled crevasse lines that double as
the site's own rule motif.

Every rendering comes from the ``EMBLEM`` layer list below: the Windows tray
``.ico`` (``generate_icon``), the brand exports under ``WebSite/brand/`` and
``assets/``, the desktop and Android app icons, and the SVG the site inlines
(``WebSite/brand/render_marks.py`` imports ``draw_mark`` and ``mark_svg``).
One description, two renderers -- ``mark_svg`` emits it as SVG and
``draw_mark`` rasterises the same list with Pillow -- so a change here reaches
every surface and nothing can drift.

A layer is a dict:

    {"kind": "circle", "cx", "cy", "r", "fill", "opacity"?, "clip"?}
    {"kind": "path",   "d",  "fill", "opacity"?, "clip"?, "transform"?}
    {"kind": "stroke", "d",  "stroke", "width", "opacity"?, "clip"?}

``clip`` confines a layer to the badge outline (the disc, or the rounded
square when ``tile`` is set). ``transform`` is ``(tx, ty, scale)``, which is
how the wolf is drawn in comfortable coordinates and then placed.

Exports
-------
draw_mark(size, tile=False)   PIL image of the badge at ``size`` px (RGBA).
mark_svg(tile=False)          the same badge as an SVG document string.
create_icon_image(size)       the app-icon tile, for the tray and launcher.
generate_icon(output_path)    the multi-size tray ``.ico``.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# ---- palette (matches WebSite/design-system/src/styles/tokens.css) ----------
INK = (0x14, 0x14, 0x0F)      # --bg-0, the ground the site sits on
SKY = (0x1B, 0x1B, 0x24)      # the night sky: lifted off the ground so the
                              # badge keeps an edge on the site's own ink
CREAM = (0xF2, 0xEF, 0xE6)    # --fg-1: snow, stars, the badge rim
ACCENT = (0xE0, 0x70, 0x3F)   # --ember-600: the moon
DUST = (0xC9, 0xB6, 0xFF)     # the cool cast of the galaxy disc
ROCK = (0x33, 0x33, 0x3D)     # the Black Buttes: bare rock, not snow
SHADE = (0xD2, 0xCC, 0xBE)    # the foreground snowfield, in the mountain's shadow

INK_HEX = "#14140f"
SKY_HEX = "#1b1b24"
CREAM_HEX = "#f2efe6"
ACCENT_HEX = "#e0703f"
DUST_HEX = "#c9b6ff"
ROCK_HEX = "#33333d"
SHADE_HEX = "#d2ccbe"

# ---- geometry, in a 64 x 64 box -------------------------------------------
VIEWBOX = 64.0
DISC_CX = DISC_CY = 32.0
DISC_R = 31.0
RIM_R = 30.4
RIM_W = 1.2
TILE_RADIUS = 13.0            # rounded corner when the badge is an app tile
MOON_CX, MOON_CY, MOON_R = 47.0, 14.5, 4.2

_SUPERSAMPLE = 4

# The wolf, drawn around a 30 x 32 box, then placed on the snowfield.
_WOLF_AT = (29.0, 47.6, 0.38)

# ---- Mount Baker from the south -------------------------------------------
# Traced from photographs taken from Everett and Seattle, both of which look at
# the mountain from the south. Left to right the skyline runs:
#
#   * Lincoln Peak, a sharp twin spire (9,080 ft), lowest and furthest west;
#   * a gap, then Colfax Peak, broader and higher (9,440 ft) -- together the
#     Black Buttes, dark rock left over from the older volcano on Baker's
#     west shoulder, standing about half the height of the summit;
#   * a col, then the fairly straight rise of the Roman Wall;
#   * the SUMMIT AS A BROAD, NEARLY LEVEL PLATEAU -- the ice dome over Carmelo
#     Crater. This is the detail every stylisation gets wrong: from the south
#     Baker has a flat top, not a peak;
#   * a step down to a rounded shoulder, then a long, gentle descent down the
#     south-east flank, roughly twice the length of the left side.
#
# Sherman Peak (10,140 ft) sits on the west rim of Sherman Crater, south of the
# summit, and shows as a rock patch at the plateau's left shoulder.
_SNOW = (
    # Traced from the Everett photograph by modelling the sky gradient and
    # finding, per column, the first row that departs from it. Landmarks left
    # to right: Lincoln Peak, a saddle, Colfax Peak (together the Black Buttes,
    # about half the summit height), the col, the long straight rise of the
    # Roman Wall, THE SUMMIT PLATEAU -- flat, not a point -- a step down, the
    # rounded east shoulder, and the long south-east flank.
    "M-6 64 L-6 43.4 L-2 38.5 L0 36.1 L1.5 34.6 L3 33.3 "
    "L4.5 36.2 L6 38.9 L7.5 40.0 L9 38.2 L10 37.0 L11.5 40.0 L13 40.5 L14 38.8 "
    "L15 34.6 L16.5 32.6 L18 30.8 L19.5 32.2 L21 32.4 L23 33.0 L25 35.3 L26.2 37.0 "
    "L28 34.5 L30 31.8 L32 29.3 L34 26.9 L36 23.6 L37.5 21.2 "
    "L39 20.6 L41 20.2 L43 20.5 L45 21.1 L47 21.5 "
    "L48.5 23.2 L50 26.3 L51.5 25.2 L53 26.4 L55 28.9 L57 30.7 L59 33.0 "
    "L61 34.9 L63 37.1 L65 41.9 L67 43.5 L70 43.5 L70 64 Z"
)
# The foreground snowfield: a shadowed rise the wolf stands on, so the lit
# range reads as mountains behind it instead of one white mass.
_FOREGROUND = "M-4 64 L-4 49.6 Q10 46.4 26 48.8 Q42 51.2 56 48 L68 45.4 L68 64 Z"

# ---- the galaxy -----------------------------------------------------------
# An inclined spiral -- disc, two arms, bright core -- so it reads as a galaxy
# rather than as cloud or a scatter of stars.
_GALAXY_AT = (17.0, 12.5, 0.85)
_GALAXY_DISC = "M-10 0 Q-10 -4.6 0 -4.6 Q10 -4.6 10 0 Q10 4.6 0 4.6 Q-10 4.6 -10 0 Z"
_GALAXY_ARMS = [
    "M-8.8 -1.3 Q-4.8 -3.7 0 -3.3 Q5.4 -2.9 8.4 0.3",
    "M8.8 1.3 Q4.8 3.7 0 3.3 Q-5.4 2.9 -8.4 -0.3",
]

# The wolf, drawn in its own 29 x 26 box and then placed on the snowfield.
# Circles are native layers rather than arc paths: a canid silhouette is mostly
# rounded masses (haunch, chest, skull) and drawing them as arcs was what made
# earlier attempts read as a giraffe.
_WOLF: list[dict] = [
    {"kind": "circle", "cx": 6.4, "cy": 15.8, "r": 3.9},          # haunch
    {"kind": "path", "d": "M4.4 13.8 L16.0 12.4 L17.2 18.4 L5.2 19.6 Z"},
    {"kind": "circle", "cx": 15.2, "cy": 15.4, "r": 4.0},         # chest
    {"kind": "path", "d": "M5.0 16.8 L7.4 16.8 L7.2 24.6 L4.9 24.6 Z"},
    {"kind": "path", "d": "M8.6 17.4 L10.7 17.4 L10.6 24.6 L8.5 24.6 Z"},
    {"kind": "path", "d": "M13.8 16.6 L16.1 16.6 L15.9 24.6 L13.7 24.6 Z"},
    {"kind": "path", "d": "M16.8 16.2 L18.8 16.2 L18.7 24.6 L16.7 24.6 Z"},
    {"kind": "path", "d": "M4.6 14.0 C2.0 13.4 0.6 14.8 0.4 17.8 "
                          "C0.3 20.0 1.0 21.8 2.4 23.0 C2.4 20.4 2.9 18.5 3.9 17.4 "
                          "C4.6 16.6 5.4 16.2 6.4 16.1 Z"},          # tail
    {"kind": "path", "d": "M13.4 12.8 L17.0 15.8 L20.9 10.8 L17.6 8.4 Z"},  # neck
    {"kind": "path", "d": "M22.99 8.30 Q23.75 9.35 22.60 10.83 Q21.45 12.30 19.30 12.16 "
                          "Q17.15 12.02 16.01 10.85 Q14.87 9.68 16.02 8.20 "
                          "Q17.17 6.73 19.32 6.87 Q21.47 7.01 22.99 8.30 Z"},  # skull
    {"kind": "path", "d": "M20.6 7.9 L25.3 5.0 L26.1 6.4 L21.5 9.7 Z"},       # muzzle
    {"kind": "circle", "cx": 25.5, "cy": 5.7, "r": 0.8},                      # nose
    {"kind": "path", "d": "M18.9 8.5 L20.9 7.1 L18.3 4.5 Z"},                 # ears
    {"kind": "path", "d": "M20.2 9.9 L22.1 8.5 L19.6 5.9 Z"},
]

_STARS = [
    (9, 14, 0.80, 1.0), (16, 8, 0.50, 1.0), (5, 24, 0.45, 1.0),
    (55, 26, 0.70, 1.0), (59, 18, 0.45, 1.0), (26, 6, 0.45, 1.0),
    (49, 20, 0.40, 1.0), (12, 21, 0.35, 1.0), (30, 11, 0.45, 1.0),
    (36, 6, 0.40, 1.0), (54, 9, 0.5, 1.0), (24, 18, 0.35, 1.0),
    (42, 12, 0.35, 1.0), (7, 33, 0.40, 1.0), (58, 33, 0.40, 1.0),
    (21, 26, 0.3, 1.0), (33, 19, 0.3, 1.0),
]


def _emblem() -> list[dict]:
    """The badge, back to front."""
    layers: list[dict] = [{"kind": "sky", "fill": SKY}]

    # the galaxy: faint disc, two arms, a warm core
    layers.append({"kind": "path", "clip": True, "fill": DUST, "opacity": 0.13,
                   "d": _GALAXY_DISC, "transform": _GALAXY_AT})
    for arm in _GALAXY_ARMS:
        layers.append({"kind": "stroke", "clip": True, "stroke": CREAM, "width": 0.7,
                       "opacity": 0.30, "d": arm, "transform": _GALAXY_AT})
    layers.append({"kind": "circle", "clip": True, "cx": _GALAXY_AT[0], "cy": _GALAXY_AT[1],
                   "r": 2.4, "fill": ACCENT, "opacity": 0.26})
    layers.append({"kind": "circle", "clip": True, "cx": _GALAXY_AT[0], "cy": _GALAXY_AT[1],
                   "r": 1.2, "fill": CREAM, "opacity": 0.75})

    for cx, cy, r, opacity in _STARS:
        layers.append({"kind": "circle", "clip": True, "cx": cx, "cy": cy,
                       "r": r, "fill": CREAM, "opacity": opacity})

    # the moon: pale, with two faint maria so it cannot read as a sun
    layers += [
        {"kind": "circle", "clip": True, "cx": MOON_CX, "cy": MOON_CY,
         "r": MOON_R + 2.2, "fill": CREAM, "opacity": 0.10},
        {"kind": "circle", "clip": True, "cx": MOON_CX, "cy": MOON_CY,
         "r": MOON_R, "fill": CREAM},
        {"kind": "circle", "clip": True, "cx": MOON_CX - 1.3, "cy": MOON_CY - 1.1,
         "r": 1.15, "fill": SKY, "opacity": 0.13},
        {"kind": "circle", "clip": True, "cx": MOON_CX + 1.2, "cy": MOON_CY + 1.4,
         "r": 0.8, "fill": SKY, "opacity": 0.11},
        # the mountain
        {"kind": "path", "clip": True, "d": _SNOW, "fill": CREAM},
        # crevasses, drawn as the site's ruled lines
        {"kind": "stroke", "clip": True, "stroke": SKY, "width": 0.45, "opacity": 0.22,
         "d": "M38 25.5 Q43 25 48 26.6"},
        {"kind": "stroke", "clip": True, "stroke": SKY, "width": 0.45, "opacity": 0.22,
         "d": "M34 30 Q42 29 50 31.6"},
        # the shadowed foreground the wolf stands on
        {"kind": "path", "clip": True, "d": _FOREGROUND, "fill": SHADE},
    ]

    for part in _WOLF:
        layers.append({**part, "clip": True, "fill": INK, "transform": _WOLF_AT})
    layers.append({"kind": "rim"})
    return layers


EMBLEM = _emblem()

# --------------------------------------------------------------------------
# path handling: one flattener, shared by both renderers
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"([MLHVQCAZ])([^MLHVQCAZ]*)", re.I)
_NUM = re.compile(r"[-+]?[0-9]*\.?[0-9]+")


def _flatten(path: str, steps: int = 14) -> list[list[tuple[float, float]]]:
    """M/L/H/V/Q/C/A/Z into closed polygons.

    Only the arc form this module uses appears (``a r r 0 f s dx dy`` drawing a
    half circle), so arcs are sampled as semicircles rather than implementing
    the full endpoint parameterisation.
    """
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    x = y = 0.0
    for command, raw in _TOKEN.findall(path):
        nums = [float(n) for n in _NUM.findall(raw)]
        upper = command.upper()
        relative = command.islower()
        if upper == "M":
            if current:
                contours.append(current)
            x, y = (x + nums[0], y + nums[1]) if relative else (nums[0], nums[1])
            current = [(x, y)]
            for i in range(2, len(nums) - 1, 2):
                x, y = (x + nums[i], y + nums[i + 1]) if relative else (nums[i], nums[i + 1])
                current.append((x, y))
        elif upper == "L":
            for i in range(0, len(nums) - 1, 2):
                x, y = (x + nums[i], y + nums[i + 1]) if relative else (nums[i], nums[i + 1])
                current.append((x, y))
        elif upper == "H":
            for n in nums:
                x = x + n if relative else n
                current.append((x, y))
        elif upper == "V":
            for n in nums:
                y = y + n if relative else n
                current.append((x, y))
        elif upper == "Q":
            for i in range(0, len(nums) - 3, 4):
                cx, cy, nx, ny = nums[i : i + 4]
                if relative:
                    cx, cy, nx, ny = x + cx, y + cy, x + nx, y + ny
                for step in range(1, steps + 1):
                    t = step / steps
                    u = 1 - t
                    current.append((u * u * x + 2 * u * t * cx + t * t * nx,
                                    u * u * y + 2 * u * t * cy + t * t * ny))
                x, y = nx, ny
        elif upper == "C":
            for i in range(0, len(nums) - 5, 6):
                c1x, c1y, c2x, c2y, nx, ny = nums[i : i + 6]
                if relative:
                    c1x, c1y = x + c1x, y + c1y
                    c2x, c2y = x + c2x, y + c2y
                    nx, ny = x + nx, y + ny
                for step in range(1, steps + 1):
                    t = step / steps
                    u = 1 - t
                    current.append((
                        u ** 3 * x + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t ** 3 * nx,
                        u ** 3 * y + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t ** 3 * ny,
                    ))
                x, y = nx, ny
        elif upper == "A":
            # `a rx ry rot large sweep dx dy` — always a half circle here.
            for i in range(0, len(nums) - 6, 7):
                rx, _ry, _rot, _large, sweep, dx, dy = nums[i : i + 7]
                nx, ny = (x + dx, y + dy) if relative else (dx, dy)
                mx, my = (x + nx) / 2, (y + ny) / 2
                for step in range(1, steps + 1):
                    a = math.pi * step / steps
                    direction = 1 if sweep else -1
                    current.append((mx - rx * math.cos(a) * (1 if nx >= x else -1),
                                    my + direction * rx * math.sin(a)))
                x, y = nx, ny
        elif upper == "Z":
            if current:
                contours.append(current)
                current = []
    if current:
        contours.append(current)
    return [c for c in contours if len(c) >= 3]


def _place(points, transform):
    if not transform:
        return points
    tx, ty, scale = transform
    return [(tx + px * scale, ty + py * scale) for px, py in points]


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------


def _clip_mask(px: int, tile: bool) -> Image.Image:
    k = px / VIEWBOX
    mask = Image.new("L", (px, px), 0)
    d = ImageDraw.Draw(mask)
    if tile:
        d.rounded_rectangle([0, 0, px - 1, px - 1], radius=TILE_RADIUS * k, fill=255)
    else:
        d.ellipse([(DISC_CX - DISC_R) * k, (DISC_CY - DISC_R) * k,
                   (DISC_CX + DISC_R) * k, (DISC_CY + DISC_R) * k], fill=255)
    return mask


def draw_mark(size: int = 64, tile: bool = False) -> Image.Image:
    """Render the badge at ``size`` px. ``tile`` squares it off for an app icon."""
    if size < 8:
        raise ValueError("mark size must be at least 8 px")
    size = int(size)
    px = size * _SUPERSAMPLE
    k = px / VIEWBOX
    clip = _clip_mask(px, tile)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))

    for layer in EMBLEM:
        kind = layer["kind"]
        if kind == "rim":
            rim = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            if not tile:
                ImageDraw.Draw(rim).ellipse(
                    [(DISC_CX - RIM_R) * k, (DISC_CY - RIM_R) * k,
                     (DISC_CX + RIM_R) * k, (DISC_CY + RIM_R) * k],
                    outline=CREAM + (230,), width=max(1, round(RIM_W * k)))
                img.alpha_composite(rim)
            continue

        layer_img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer_img)
        alpha = round(255 * layer.get("opacity", 1.0))

        if kind == "sky":
            # The night sky fills the badge outline, whether disc or tile.
            solid = Image.new("RGBA", (px, px), layer["fill"] + (255,))
            solid.putalpha(clip)
            img.alpha_composite(solid)
            continue
        elif kind == "circle":
            cx, cy, r = layer["cx"], layer["cy"], layer["r"]
            if layer.get("transform"):
                tx, ty, scale = layer["transform"]
                cx, cy, r = tx + cx * scale, ty + cy * scale, r * scale
            draw.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                         fill=layer["fill"] + (alpha,))
        elif kind == "path":
            fill = layer["fill"] + (alpha,)
            shape = Image.new("1", (px, px), 0)
            shape_draw = ImageDraw.Draw(shape)
            for contour in _flatten(layer["d"]):
                pts = [(cx * k, cy * k) for cx, cy in _place(contour, layer.get("transform"))]
                one = Image.new("1", (px, px), 0)
                ImageDraw.Draw(one).polygon(pts, fill=1)
                shape = ImageChops.logical_xor(shape, one)
            del shape_draw
            solid = Image.new("RGBA", (px, px), fill)
            layer_img = Image.composite(solid, layer_img, shape)
        elif kind == "stroke":
            for contour in _flatten(layer["d"]):
                pts = [(cx * k, cy * k) for cx, cy in _place(contour, layer.get("transform"))]
                draw.line(pts, fill=layer["stroke"] + (alpha,),
                          width=max(1, round(layer["width"] * k)), joint="curve")

        if layer.get("clip", False):
            existing = layer_img.getchannel("A")
            layer_img.putalpha(ImageChops.multiply(existing, clip))
        img.alpha_composite(layer_img)

    return img.resize((size, size), Image.LANCZOS)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def mark_svg(tile: bool = False) -> str:
    """The same badge as SVG (viewBox 0 0 64 64)."""
    clip_shape = (
        f'<rect width="{VIEWBOX:g}" height="{VIEWBOX:g}" rx="{TILE_RADIUS:g}"/>'
        if tile
        else f'<circle cx="{DISC_CX:g}" cy="{DISC_CY:g}" r="{DISC_R:g}"/>'
    )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX:g} {VIEWBOX:g}" '
        'width="64" height="64" role="img" '
        'aria-label="TinyAssets: Mount Baker under a wolf moon">',
        f'<defs><clipPath id="ta-badge">{clip_shape}</clipPath></defs>',
    ]
    for layer in EMBLEM:
        kind = layer["kind"]
        if kind == "rim":
            if not tile:
                out.append(
                    f'<circle cx="{DISC_CX:g}" cy="{DISC_CY:g}" r="{RIM_R:g}" fill="none" '
                    f'stroke="{CREAM_HEX}" stroke-width="{RIM_W:g}" opacity=".9"/>'
                )
            continue
        clip = ' clip-path="url(#ta-badge)"' if layer.get("clip") else ""
        opacity = layer.get("opacity", 1.0)
        op = f' opacity="{opacity:g}"' if opacity != 1.0 else ""
        transform = layer.get("transform")
        tf = ""
        if transform:
            tx, ty, scale = transform
            tf = f' transform="translate({tx:g} {ty:g}) scale({scale:g})"'
        if kind == "sky":
            out.append(
                f'<rect width="{VIEWBOX:g}" height="{VIEWBOX:g}" rx="{TILE_RADIUS:g}" '
                f'fill="{_hex(layer["fill"])}"/>'
                if tile
                else f'<circle cx="{DISC_CX:g}" cy="{DISC_CY:g}" r="{DISC_R:g}" '
                     f'fill="{_hex(layer["fill"])}"/>'
            )
        elif kind == "circle":
            out.append(
                f'<circle{clip} cx="{layer["cx"]:g}" cy="{layer["cy"]:g}" '
                f'r="{layer["r"]:g}" fill="{_hex(layer["fill"])}"{op}/>'
            )
        elif kind == "path":
            out.append(
                f'<path{clip}{tf} d="{layer["d"]}" fill="{_hex(layer["fill"])}"{op}/>'
            )
        elif kind == "stroke":
            out.append(
                f'<path{clip}{tf} d="{layer["d"]}" fill="none" '
                f'stroke="{_hex(layer["stroke"])}" stroke-width="{layer["width"]:g}" '
                f'stroke-linecap="round"{op}/>'
            )
    out.append("</svg>")
    return "".join(out) + "\n"


def create_icon_image(size: int = 64) -> Image.Image:
    """The app-icon tile: the badge squared off with rounded corners."""
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
