# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

repo = Path.cwd()
datas = []
binaries = []
hiddenimports = []
for package in ("tinyassets", "fantasy_daemon", "domains"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(repo / "packaging" / "macos" / "entrypoint.py")],
    pathex=[str(repo)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TinyAssets",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TinyAssets",
)
app = BUNDLE(
    collection,
    name="TinyAssets.app",
    bundle_identifier="io.tinyassets.tray",
    info_plist={
        "CFBundleDisplayName": "TinyAssets",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
)
