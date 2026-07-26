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

datas.append((str(repo / "tinyassets" / "desktop" / "app.ico"), "tinyassets/desktop"))

analysis = Analysis(
    [str(repo / "packaging" / "windows" / "entrypoint.py")],
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
    analysis.binaries,
    analysis.datas,
    [],
    name="TinyAssets",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(repo / "tinyassets" / "desktop" / "app.ico"),
)
