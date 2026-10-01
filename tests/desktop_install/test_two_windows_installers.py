"""The Electron chat app and the server tray are two Windows installers that
must never be mistaken for each other.

Until 2026-10-01 both were `TinyAssetsSetup-*.exe` and both installed
`%LOCALAPPDATA%\\Programs\\TinyAssets\\TinyAssets.exe` with a `TinyAssets`
shortcut, so installing one replaced the other. Nothing built the chat app at
all, and the founder's copy kept loading the retired /mcp/app.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ISS = ROOT / "packaging" / "windows" / "TinyAssets.iss"
CHAT_PACKAGE = ROOT / "desktop-app" / "package.json"


def _iss_setting(name: str) -> str:
    match = re.search(rf"^{name}=(.+)$", ISS.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{name} missing from TinyAssets.iss"
    return match.group(1).strip()


def _chat_build() -> dict:
    return json.loads(CHAT_PACKAGE.read_text(encoding="utf-8"))["build"]


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_installer_file_names_are_distinct() -> None:
    tray = _iss_setting("OutputBaseFilename")
    build = _chat_build()
    chat_setup = build["nsis"]["artifactName"]
    chat_zip = build["win"]["artifactName"]

    assert tray.startswith("TinyAssetsServerSetup-")
    assert chat_setup.startswith("TinyAssetsChatSetup-")
    assert chat_zip.startswith("TinyAssetsChat-")
    # Neither is a prefix of the other, so no glob for one matches the other.
    for a, b in [(tray, chat_setup), (tray, chat_zip)]:
        stem_a, stem_b = a.split("-")[0], b.split("-")[0]
        assert not stem_a.startswith(stem_b) and not stem_b.startswith(stem_a)


def test_install_directories_and_shortcuts_do_not_collide() -> None:
    # electron-builder's per-user NSIS installs to
    # %LOCALAPPDATA%\Programs\<productName> and names its shortcut <productName>.
    chat_name = _chat_build()["productName"]
    tray_dir = _iss_setting("DefaultDirName")
    iss = ISS.read_text(encoding="utf-8")

    assert tray_dir.lower() != f"{{localappdata}}\\programs\\{chat_name}".lower()
    shortcut_names = re.findall(r'^Name: "\{[a-z]+\}\\([^"]+)";', iss, re.MULTILINE)
    assert shortcut_names, "no shortcuts found in TinyAssets.iss [Icons]"
    assert chat_name not in shortcut_names


def test_every_tray_installer_glob_names_the_server_installer() -> None:
    text = (WORKFLOWS / "desktop-release.yml").read_text(encoding="utf-8")
    globs = re.findall(r"packaging/dist/windows/(TinyAssets\w*Setup-)", text)
    assert globs and set(globs) == {"TinyAssetsServerSetup-"}
    lifecycle = (Path(__file__).with_name("windows_lifecycle.ps1")).read_text(encoding="utf-8")
    assert '"Programs\\TinyAssetsServer"' in lifecycle


def test_chat_app_workflow_builds_and_uploads_its_own_artifact() -> None:
    wf = _workflow("desktop-chat-app.yml")
    triggers = wf[True] if True in wf else wf["on"]
    assert "desktop-app/**" in triggers["push"]["paths"]
    assert "workflow_dispatch" in triggers

    steps = wf["jobs"]["build-windows"]["steps"]
    runs = "\n".join(step.get("run", "") for step in steps)
    assert "electron-builder --win nsis zip" in runs
    assert "--publish never" in runs
    upload = next(step for step in steps if "upload-artifact" in step.get("uses", ""))
    assert upload["with"]["name"] == "desktop-chat-windows-x86_64"
    assert "TinyAssetsChatSetup-" in upload["with"]["path"]
    assert "TinyAssetsServerSetup-" not in upload["with"]["path"]
    # The build holds no write authority: nothing here publishes.
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["build-windows"]["permissions"] == {"contents": "read"}
