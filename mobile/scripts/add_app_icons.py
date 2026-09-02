#!/usr/bin/env python3
"""Install the pre-rendered launcher icon + splash into the generated Android project.

Why pre-rendered: CI installs JS deps with ``npm ci --ignore-scripts`` (read-only
build, Codex review 2026-08-21) and ``@capacitor/assets`` needs sharp's native
libvips, which only arrives through an install script. So the density set is
rendered once on a dev machine (Pillow, from ``mobile/resources/icon.png`` +
``splash.png``) into ``mobile/resources/android/`` and this script copies it in
after ``npx cap add android`` — the same post-generate shape as
``add_app_scheme.py``.

Fails loudly (exit 1) when the generated project carries an icon/splash PNG we
have no replacement for, or when a replacement's pixel size differs from the
template's file — a silently wrong-sized resource is exactly what Play's
pre-launch report would flag later.

Run from ``mobile/``: ``python3 scripts/add_app_icons.py``
"""
from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

MOBILE = Path(__file__).resolve().parents[1]
RES = MOBILE / "android" / "app" / "src" / "main" / "res"
SRC = MOBILE / "resources" / "android"
BACKGROUND = "#0B0B0F"  # matches capacitor.config.json android.backgroundColor

ADAPTIVE_ICON = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""

BACKGROUND_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">{BACKGROUND}</color>
</resources>
"""


def png_size(path: Path) -> tuple[int, int]:
    """Width/height straight from the PNG IHDR chunk — no image library needed."""
    with path.open("rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise SystemExit(f"not a PNG: {path}")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def is_target(rel: Path) -> bool:
    top = rel.parts[0]
    name = rel.name
    if top.startswith("mipmap-") and name.startswith("ic_launcher") and name.endswith(".png"):
        return True
    if top.startswith("drawable") and name == "splash.png":
        return True
    return False


def main() -> int:
    if not RES.is_dir():
        print(f"error: {RES} missing — run `npx cap add android` first", file=sys.stderr)
        return 1
    if not SRC.is_dir():
        print(f"error: {SRC} missing — render it with scripts/render_app_icons.py", file=sys.stderr)
        return 1

    targets = sorted(p for p in RES.rglob("*.png") if is_target(p.relative_to(RES)))
    if not targets:
        print("error: no icon/splash PNGs in the generated project — template changed?",
              file=sys.stderr)
        return 1

    problems: list[str] = []
    replaced = 0
    for dst in targets:
        rel = dst.relative_to(RES)
        src = SRC / rel
        if not src.is_file():
            problems.append(f"no pre-rendered replacement for {rel}")
            continue
        want, have = png_size(dst), png_size(src)
        if want != have:
            problems.append(
                f"{rel}: template is {want[0]}x{want[1]}, pre-rendered is {have[0]}x{have[1]}"
            )
            continue
        shutil.copyfile(src, dst)
        replaced += 1

    # Extra pre-rendered files with no counterpart in the template are a drift signal too.
    extras = sorted(
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.png")
        if not (RES / p.relative_to(SRC)).exists()
    )
    for e in extras:
        problems.append(f"pre-rendered {e} has no counterpart in the generated project")

    if problems:
        print("error: icon install aborted:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1

    anydpi = RES / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        (anydpi / name).write_text(ADAPTIVE_ICON, encoding="utf-8")
    values = RES / "values"
    values.mkdir(parents=True, exist_ok=True)
    (values / "ic_launcher_background.xml").write_text(BACKGROUND_XML, encoding="utf-8")

    print(f"installed {replaced} icon/splash PNGs + adaptive-icon XML (background {BACKGROUND})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
