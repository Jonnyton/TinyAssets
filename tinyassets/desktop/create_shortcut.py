"""Create a Windows desktop shortcut for TinyAssets.

Usage::

    python -m tinyassets.desktop.create_shortcut

Creates a .lnk shortcut (if ``winshell`` is installed) or a .bat launcher
on the user's Desktop that runs ``tinyassets.pyw`` via ``pythonw``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    """Return the project root (parent of the TinyAssets package)."""
    return Path(__file__).resolve().parent.parent.parent


def _pyw_path() -> Path:
    """Return the absolute path to tinyassets.pyw."""
    return _project_root() / "tinyassets.pyw"


def _icon_path() -> Path:
    """Return the absolute path to app.ico (may not exist yet)."""
    return Path(__file__).resolve().parent / "app.ico"


def _desktop_dir() -> Path:
    """Return the user's Desktop directory."""
    return Path.home() / "Desktop"


def _create_lnk(target: Path, desktop: Path, icon: Path) -> Path:
    """Create a .lnk shortcut using winshell."""
    import winshell  # type: ignore[import-untyped]

    shortcut_path = desktop / "TinyAssets.lnk"
    pythonw = Path(sys.executable).parent / "pythonw.exe"

    winshell.CreateShortcut(
        Path=str(shortcut_path),
        Target=str(pythonw),
        Arguments=f'"{target}"',
        StartIn=str(target.parent),
        Icon=(str(icon), 0) if icon.exists() else (str(pythonw), 0),
        Description="TinyAssets -- autonomous fiction generation",
    )
    return shortcut_path


def _create_bat(target: Path, desktop: Path) -> Path:
    """Create a .bat launcher as a fallback when winshell is unavailable."""
    bat_path = desktop / "TinyAssets.bat"
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    bat_path.write_text(
        f'@echo off\nstart "" "{pythonw}" "{target}"\n',
        encoding="utf-8",
    )
    return bat_path


def create_shortcut() -> Path:
    """Create a desktop shortcut and return its path."""
    target = _pyw_path()
    desktop = _desktop_dir()
    icon = _icon_path()

    if not target.exists():
        raise FileNotFoundError(f"Launcher not found: {target}")

    if not desktop.exists():
        raise FileNotFoundError(f"Desktop directory not found: {desktop}")

    try:
        return _create_lnk(target, desktop, icon)
    except ImportError:
        return _create_bat(target, desktop)


def main() -> None:
    """Entry point for ``python -m tinyassets.desktop.create_shortcut``."""
    path = create_shortcut()
    print(f"Shortcut created: {path}")


if __name__ == "__main__":
    main()
