"""The TinyAssets mark, and the one place its geometry lives.

The mark is a ring (a universe) crossed low by a rule that runs off to the
right (a ledger line, the site's receipt motif) with one warm dot sitting on
the rule (the agent). Ink on paper, one accent, legible at 16 px.

Every rendering of the mark comes from this module: the Windows tray ``.ico``
(``generate_icon``), the brand exports under ``WebSite/brand/`` and
``assets/``, the desktop and Android app icons, and the SVG the site inlines
(``WebSite/brand/render_marks.py`` imports ``draw_mark`` and ``mark_svg``).
Change the numbers here, re-run that script, and every surface follows.

Exports
-------
draw_mark(size, tile=True)
    Return a PIL Image of the mark at ``size`` px (RGBA; the tile version has
    a rounded paper square behind the mark, the bare version is transparent).
mark_svg(tile=True)
    Return the same drawing as an SVG document string.
create_icon_image(size)
    Backwards-compatible alias for ``draw_mark(size)`` (tray + launcher).
generate_icon(output_path)
    Render the multi-size tray ``.ico``.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# ---- palette (matches WebSite/design-system/src/styles/tokens.css) ----------
PAPER = (0xF6, 0xF1, 0xE6)  # --paper-100
INK = (0x1E, 0x1A, 0x17)  # --ink-text-900
ACCENT = (0xB5, 0x47, 0x1F)  # --ember-600 (terracotta)

PAPER_HEX = "#f6f1e6"
INK_HEX = "#1e1a17"
ACCENT_HEX = "#b5471f"

# ---- geometry, in a 64 x 64 box -------------------------------------------
VIEWBOX = 64.0
TILE_RADIUS = 14.0  # rounded corner of the paper tile
RING_CX, RING_CY, RING_R = 32.0, 30.0, 18.5
RING_STROKE = 5.0
RULE_Y = 38.0
RULE_X0, RULE_X1 = 15.5, 59.0
RULE_STROKE = 4.0
DOT_CX, DOT_CY, DOT_R = 32.0, 38.0, 6.0
DOT_HALO = 2.5  # paper ring around the dot so it separates from the rule

_SUPERSAMPLE = 4


def _draw_at(size: int, tile: bool) -> Image.Image:
    px = size * _SUPERSAMPLE
    k = px / VIEWBOX
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if tile:
        d.rounded_rectangle(
            [0, 0, px - 1, px - 1], radius=TILE_RADIUS * k, fill=PAPER + (255,)
        )

    # Ring.
    w = RING_STROKE * k
    d.ellipse(
        [
            (RING_CX - RING_R) * k,
            (RING_CY - RING_R) * k,
            (RING_CX + RING_R) * k,
            (RING_CY + RING_R) * k,
        ],
        outline=INK + (255,),
        width=max(1, round(w)),
    )

    # Rule: a flat-capped bar from inside the ring off to the right.
    h = RULE_STROKE * k
    d.rectangle(
        [RULE_X0 * k, (RULE_Y * k) - h / 2, RULE_X1 * k, (RULE_Y * k) + h / 2],
        fill=INK + (255,),
    )

    # Dot with a halo so it reads as sitting on the rule. On the tile the halo
    # is paper; on the bare mark it is a transparent punch through the rule.
    halo = (DOT_R + DOT_HALO) * k
    halo_box = [DOT_CX * k - halo, DOT_CY * k - halo, DOT_CX * k + halo, DOT_CY * k + halo]
    if tile:
        d.ellipse(halo_box, fill=PAPER + (255,))
    else:
        punch = Image.new("L", (px, px), 255)
        ImageDraw.Draw(punch).ellipse(halo_box, fill=0)
        img.putalpha(ImageChops.darker(img.getchannel("A"), punch))
        d = ImageDraw.Draw(img)
    r = DOT_R * k
    d.ellipse(
        [DOT_CX * k - r, DOT_CY * k - r, DOT_CX * k + r, DOT_CY * k + r],
        fill=ACCENT + (255,),
    )

    return img.resize((size, size), Image.LANCZOS)


def draw_mark(size: int = 64, tile: bool = True) -> Image.Image:
    """Render the mark at ``size`` px. ``tile`` adds the rounded paper square."""
    if size < 8:
        raise ValueError("mark size must be at least 8 px")
    return _draw_at(int(size), bool(tile))


def mark_svg(tile: bool = True) -> str:
    """The same drawing as SVG (viewBox 0 0 64 64)."""
    halo = DOT_R + DOT_HALO
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'width="64" height="64" role="img" aria-label="TinyAssets">'
    ]
    if tile:
        parts.append(
            f'<rect width="64" height="64" rx="{TILE_RADIUS:g}" fill="{PAPER_HEX}"/>'
        )
        rule_attrs = ""
    else:
        parts.append(
            '<defs><mask id="ta-halo"><rect width="64" height="64" fill="#fff"/>'
            f'<circle cx="{DOT_CX:g}" cy="{DOT_CY:g}" r="{halo:g}" fill="#000"/>'
            "</mask></defs>"
        )
        rule_attrs = ' mask="url(#ta-halo)"'
    parts.append(
        f'<circle cx="{RING_CX:g}" cy="{RING_CY:g}" r="{RING_R:g}" fill="none" '
        f'stroke="{INK_HEX}" stroke-width="{RING_STROKE:g}"/>'
    )
    parts.append(
        f'<rect{rule_attrs} x="{RULE_X0:g}" y="{RULE_Y - RULE_STROKE / 2:g}" '
        f'width="{RULE_X1 - RULE_X0:g}" height="{RULE_STROKE:g}" fill="{INK_HEX}"/>'
    )
    if tile:
        parts.append(
            f'<circle cx="{DOT_CX:g}" cy="{DOT_CY:g}" r="{halo:g}" fill="{PAPER_HEX}"/>'
        )
    parts.append(
        f'<circle cx="{DOT_CX:g}" cy="{DOT_CY:g}" r="{DOT_R:g}" fill="{ACCENT_HEX}"/>'
    )
    parts.append("</svg>")
    return "".join(parts) + "\n"


def create_icon_image(size: int = 64) -> Image.Image:
    """Create the TinyAssets icon at the given pixel size (paper tile)."""
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
