"""RetroLab Windows launcher primitives for the MCP connector.

These helpers deliberately stay local-only: they install or launch an
allowlisted emulator and only point it at a user-provided local game path.
They never download game media, ROMs, firmware, or BIOS files.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

_EMULATORS: dict[str, dict[str, Any]] = {
    "dosbox-x": {
        "display_name": "DOSBox-X",
        "winget_id": "DOSBox-X.DOSBox-X",
        "commands": ("dosbox-x", "dosbox-x.exe"),
        "launch_args": lambda executable, game_path: [executable, str(game_path)],
    },
    "scummvm": {
        "display_name": "ScummVM",
        "winget_id": "ScummVM.ScummVM",
        "commands": ("scummvm", "scummvm.exe"),
        "launch_args": lambda executable, game_path: [executable, str(game_path)],
    },
}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _windows_status() -> tuple[bool, str]:
    current = platform.system()
    return current == "Windows", current


def _emulator_spec(emulator: str) -> tuple[str, dict[str, Any] | None]:
    key = (emulator or "dosbox-x").strip().lower()
    if key == "auto":
        key = "dosbox-x"
    return key, _EMULATORS.get(key)


def _find_emulator(emulator: str) -> tuple[str, str | None]:
    key, spec = _emulator_spec(emulator)
    if spec is None:
        return key, None
    for command in spec["commands"]:
        found = shutil.which(command)
        if found:
            return key, found
    return key, None


def _install_command(emulator: str) -> tuple[str, list[str] | None]:
    key, spec = _emulator_spec(emulator)
    if spec is None:
        return key, None
    return key, [
        "winget",
        "install",
        "--id",
        spec["winget_id"],
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


def install_retrolab_worker_windows(emulator: str = "dosbox-x", confirm: bool = False) -> str:
    """Install an allowlisted RetroLab emulator on Windows.

    Args:
        emulator: Allowlisted emulator package. Supported: dosbox-x, scummvm.
        confirm: Must be true before running winget. False returns a command
            preview for the chatbot to show the user.
    """
    is_windows, current_platform = _windows_status()
    key, command = _install_command(emulator)
    if command is None:
        return _json({
            "status": "unsupported_emulator",
            "emulator": emulator,
            "supported": sorted(_EMULATORS),
        })
    if not is_windows:
        return _json({
            "status": "not_available",
            "platform": current_platform,
            "requires": "Windows",
            "emulator": key,
        })
    if not confirm:
        return _json({
            "status": "needs_confirmation",
            "emulator": key,
            "command_preview": command,
            "note": (
                "Re-run with confirm=true only after the user approves "
                "installing the allowlisted emulator package."
            ),
        })
    if shutil.which("winget") is None:
        return _json({
            "status": "installer_not_found",
            "installer": "winget",
            "emulator": key,
            "next_step": "Install or enable Windows App Installer, then retry.",
        })

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        shell=False,
    )
    status = "installed" if completed.returncode == 0 else "install_failed"
    return _json({
        "status": status,
        "emulator": key,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    })


def verify_retro_game_windows(game_path: str = "", emulator: str = "auto") -> str:
    """Verify whether Windows can launch a user-owned local retro game path."""
    is_windows, current_platform = _windows_status()
    if not is_windows:
        return _json({
            "status": "not_available",
            "platform": current_platform,
            "requires": "Windows",
        })

    key, executable = _find_emulator(emulator)
    if key not in _EMULATORS:
        return _json({
            "status": "unsupported_emulator",
            "emulator": emulator,
            "supported": sorted(_EMULATORS),
        })

    resolved_game_path = Path(game_path).expanduser().resolve() if game_path else None
    game_path_ok = bool(resolved_game_path and resolved_game_path.exists())
    status = "ready" if executable and game_path_ok else "needs_setup"
    return _json({
        "status": status,
        "platform": current_platform,
        "emulator": key,
        "emulator_found": executable is not None,
        "emulator_path": executable,
        "game_path": str(resolved_game_path) if resolved_game_path else "",
        "game_path_ok": game_path_ok,
        "media_policy": (
            "Only use game files, ROMs, firmware, or BIOS files the user has "
            "rights to use."
        ),
    })


def launch_retro_game_windows(
    game_path: str,
    emulator: str = "auto",
    confirm: bool = False,
) -> str:
    """Launch an allowlisted emulator against a user-owned local game path.

    Args:
        game_path: Local path to the user's game directory or file.
        emulator: Allowlisted emulator. Supported: auto, dosbox-x, scummvm.
        confirm: Must be true before a local process is launched.
    """
    is_windows, current_platform = _windows_status()
    if not is_windows:
        return _json({
            "status": "not_available",
            "platform": current_platform,
            "requires": "Windows",
        })

    key, executable = _find_emulator(emulator)
    if key not in _EMULATORS:
        return _json({
            "status": "unsupported_emulator",
            "emulator": emulator,
            "supported": sorted(_EMULATORS),
        })

    resolved_game_path = Path(game_path).expanduser().resolve()
    if not resolved_game_path.exists():
        return _json({
            "status": "invalid_game_path",
            "game_path": str(resolved_game_path),
            "next_step": "Provide a local path to game files the user owns or has rights to use.",
        })
    if executable is None:
        return _json({
            "status": "emulator_not_found",
            "emulator": key,
            "next_step": "Call install_retrolab_worker_windows, then retry.",
        })

    command = _EMULATORS[key]["launch_args"](executable, resolved_game_path)
    if not confirm:
        return _json({
            "status": "needs_confirmation",
            "emulator": key,
            "game_path": str(resolved_game_path),
            "command_preview": command,
        })

    process = subprocess.Popen(command, shell=False)
    return _json({
        "status": "launched",
        "emulator": key,
        "game_path": str(resolved_game_path),
        "pid": process.pid,
    })
