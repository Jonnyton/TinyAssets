#!/usr/bin/env python3
"""Export the TinyAssets mark to every surface that carries it.

The drawing lives in ``tinyassets/desktop/icon_gen.py`` (one geometry, one
palette). This script renders it out (dev machine only; needs Pillow) so the
site, the repo brand assets, the served web app, the desktop and Android apps,
the tray and the Play listing all show the same symbol.

Run from the repo root::

    python WebSite/brand/render_marks.py

Outputs (all overwritten):

- ``WebSite/brand/mark.svg`` (bare) and ``mark-tile.svg`` (paper tile)
- ``WebSite/site-react/public/``: favicon.ico, icon.svg, apple-touch-icon.png,
  icon-192.png, icon-512.png, logo-mark.png, tinyassets-mark.png
- ``assets/icon.png``, ``assets/icon.svg``, ``assets/brand/tinyassets-logo-{icon,mark}.{png,svg}``
- ``desktop-app/build/icon.{png,ico,icns}`` (electron-builder buildResources)
- ``tinyassets/desktop/app.ico`` (Windows tray; also used by the launcher)
- ``mobile/resources/{icon,splash}.png`` + the Android density set +
  ``docs/ops/play-assets/{icon-512,feature-graphic-1024x500}.png`` via
  ``mobile/scripts/render_app_icons.py --from-logo``

The OG card (``og-image.png``) is rendered separately by ``render_og.py``
because it needs the site's web fonts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tinyassets.desktop.icon_gen import draw_mark, generate_icon, mark_svg  # noqa: E402

BRAND = REPO / "WebSite" / "brand"
SITE_PUBLIC = REPO / "WebSite" / "site-react" / "public"
ASSETS = REPO / "assets"
DESKTOP_BUILD = REPO / "desktop-app" / "build"
TRAY_ICO = REPO / "tinyassets" / "desktop" / "app.ico"


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_bytes(data)
    print(path.relative_to(REPO).as_posix())


def _png(path: Path, size: int, tile: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    draw_mark(size, tile=tile).save(path, optimize=True)
    print(f"{path.relative_to(REPO).as_posix()} {size}x{size}")


def _ico(path: Path, sizes: tuple[int, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [draw_mark(s, tile=True) for s in sizes]
    images[-1].save(
        path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1]
    )
    print(f"{path.relative_to(REPO).as_posix()} {sizes}")


def _icns(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = (16, 32, 64, 128, 256, 512, 1024)
    images = [draw_mark(s, tile=True) for s in sizes]
    images[-1].save(path, format="ICNS", append_images=images[:-1])
    print(f"{path.relative_to(REPO).as_posix()} {sizes}")


def main() -> int:
    bare_svg = mark_svg(tile=False)
    tile_svg = mark_svg(tile=True)

    # Brand source exports.
    _write(BRAND / "mark.svg", bare_svg)
    _write(BRAND / "mark-tile.svg", tile_svg)

    # Site.
    _ico(SITE_PUBLIC / "favicon.ico", (16, 32, 48))
    _write(SITE_PUBLIC / "icon.svg", tile_svg)
    _png(SITE_PUBLIC / "apple-touch-icon.png", 180, tile=True)
    _png(SITE_PUBLIC / "icon-192.png", 192, tile=True)
    _png(SITE_PUBLIC / "icon-512.png", 512, tile=True)
    _png(SITE_PUBLIC / "logo-mark.png", 512, tile=True)
    _png(SITE_PUBLIC / "tinyassets-mark.png", 512, tile=False)

    # Repo brand assets.
    _png(ASSETS / "icon.png", 512, tile=True)
    _write(ASSETS / "icon.svg", tile_svg)
    _png(ASSETS / "brand" / "tinyassets-logo-icon.png", 512, tile=True)
    _write(ASSETS / "brand" / "tinyassets-logo-icon.svg", tile_svg)
    _png(ASSETS / "brand" / "tinyassets-logo-mark.png", 512, tile=False)
    _write(ASSETS / "brand" / "tinyassets-logo-mark.svg", bare_svg)

    # Desktop (electron-builder picks build/icon.* up by convention).
    _png(DESKTOP_BUILD / "icon.png", 512, tile=True)
    _ico(DESKTOP_BUILD / "icon.ico", (16, 32, 48, 64, 128, 256))
    _icns(DESKTOP_BUILD / "icon.icns")

    # Tray.
    generate_icon(TRAY_ICO)
    print(TRAY_ICO.relative_to(REPO).as_posix())

    # Android + Play listing, through the mobile renderer's own contract.
    logo = ASSETS / "icon.png"
    subprocess.run(
        [sys.executable, "scripts/render_app_icons.py", "--from-logo", str(logo)],
        cwd=REPO / "mobile",
        check=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
