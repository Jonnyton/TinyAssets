#!/usr/bin/env python3
"""Render the app's icon/splash art (dev machine only — needs Pillow).

Two stages, both idempotent:

1. ``--from-logo PATH`` (optional): render the *sources* from a square logo mark —
   ``resources/icon.png`` (1024²), ``resources/splash.png`` (2732²) and the Play
   listing graphics under ``docs/ops/play-assets/`` (icon-512, feature graphic).
2. Always: render the Android density set from the sources into
   ``resources/android/`` — the exact files ``add_app_icons.py`` copies into the
   generated project after ``npx cap add android``. Sizes mirror the Capacitor 6
   Android template; the installer refuses any mismatch, so a template change
   shows up as a red build, not a blank icon.

Usage (from ``mobile/``):
    python scripts/render_app_icons.py
    python scripts/render_app_icons.py --from-logo ../assets/icon.png

``WebSite/brand/render_marks.py`` runs the second form for you as part of exporting
the mark to every surface.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MOBILE = Path(__file__).resolve().parents[1]
REPO = MOBILE.parent
RES = MOBILE / "resources"
OUT = RES / "android"
PLAY = REPO / "docs" / "ops" / "play-assets"
BG = (0x0B, 0x0B, 0x0F)  # capacitor.config.json android.backgroundColor

LAUNCHER = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
SPLASH_PORT = {
    "mdpi": (320, 480), "hdpi": (480, 800), "xhdpi": (720, 1280),
    "xxhdpi": (960, 1600), "xxxhdpi": (1280, 1920),
}


def _font(size: int, bold: bool) -> ImageFont.ImageFont:
    names = ["segoeuib.ttf", "seguisb.ttf"] if bold else ["segoeui.ttf"]
    names += ["arialbd.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    print(f"{path.relative_to(REPO).as_posix()} {im.size[0]}x{im.size[1]}")


def render_sources(logo_path: Path) -> None:
    logo = Image.open(logo_path).convert("RGBA")
    if logo.size[0] != logo.size[1]:
        raise SystemExit(f"logo must be square, got {logo.size}")

    icon = Image.new("RGB", (1024, 1024), BG)
    big = logo.resize((1024, 1024), Image.LANCZOS)
    icon.paste(big, (0, 0), big)
    _save(icon, RES / "icon.png")

    splash = Image.new("RGB", (2732, 2732), BG)
    side = 820
    mark = logo.resize((side, side), Image.LANCZOS)
    splash.paste(mark, ((2732 - side) // 2, (2732 - side) // 2), mark)
    _save(splash, RES / "splash.png")

    i512 = Image.new("RGB", (512, 512), BG)
    m512 = logo.resize((512, 512), Image.LANCZOS)
    i512.paste(m512, (0, 0), m512)
    _save(i512, PLAY / "icon-512.png")

    fg = Image.new("RGB", (1024, 500), BG)
    m = logo.resize((360, 360), Image.LANCZOS)
    fg.paste(m, (70, 70), m)
    d = ImageDraw.Draw(fg)
    x = 470
    d.text((x, 150), "TinyAssets", font=_font(84, True), fill=(0xF2, 0xF0, 0xEC))
    sub = _font(30, False)
    d.text((x + 4, 262), "Your own AI universe.", font=sub, fill=(0x5E, 0xD6, 0xA6))
    d.text((x + 4, 304), "Runs real work on your own LLM.", font=sub, fill=(0xC8, 0xC6, 0xC2))
    _save(fg, PLAY / "feature-graphic-1024x500.png")


def _legacy_icon(icon: Image.Image, size: int, round_mask: bool) -> Image.Image:
    im = icon.resize((size, size), Image.LANCZOS)
    if not round_mask:
        return im
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _foreground(icon: Image.Image, size: int) -> Image.Image:
    # Adaptive icon: 108dp canvas, launchers mask to the centre ~66dp. Keep the
    # mark inside that safe zone; the background layer is the solid colour resource.
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mark = int(size * 0.66)
    m = icon.resize((mark, mark), Image.LANCZOS)
    out.paste(m, ((size - mark) // 2, (size - mark) // 2), m)
    return out


def _splash(icon: Image.Image, w: int, h: int) -> Image.Image:
    out = Image.new("RGB", (w, h), BG)
    side = int(min(w, h) * 0.42)
    m = icon.resize((side, side), Image.LANCZOS)
    out.paste(m, ((w - side) // 2, (h - side) // 2), m)
    return out


def render_density_set() -> None:
    src = RES / "icon.png"
    if not src.is_file():
        raise SystemExit(f"{src} missing — run with --from-logo first")
    icon = Image.open(src).convert("RGBA")
    for d, s in LAUNCHER.items():
        _save(_legacy_icon(icon, s, False), OUT / f"mipmap-{d}" / "ic_launcher.png")
        _save(_legacy_icon(icon, s, True), OUT / f"mipmap-{d}" / "ic_launcher_round.png")
    for d, s in FOREGROUND.items():
        _save(_foreground(icon, s), OUT / f"mipmap-{d}" / "ic_launcher_foreground.png")
    _save(_splash(icon, 480, 320), OUT / "drawable" / "splash.png")
    for d, (w, h) in SPLASH_PORT.items():
        _save(_splash(icon, w, h), OUT / f"drawable-port-{d}" / "splash.png")
        _save(_splash(icon, h, w), OUT / f"drawable-land-{d}" / "splash.png")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--from-logo", type=Path,
        help="square logo PNG to render icon.png/splash.png/Play graphics from",
    )
    args = ap.parse_args(argv)
    if args.from_logo:
        render_sources(args.from_logo)
    render_density_set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
