"""The Electron chat app and the server tray are two Windows installers that
must never be mistaken for each other.

Until 2026-10-01 both were `TinyAssetsSetup-*.exe` and both put a `TinyAssets`
shortcut on the desktop (they install to different directories: the tray to
`Programs\\TinyAssets`, electron-builder's per-user NSIS to
`Programs\\tinyassets-desktop`). Nothing built the chat app at all, and the
founder's copy kept loading the retired /mcp/app.
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


def _chat_install_dir_name() -> str:
    """electron-builder 26's per-user one-click NSIS dir under Programs\\.

    `getWindowsInstallationDirName(appInfo, !oneClick || perMachine)`: the
    default (oneClick, per-user) uses the package NAME, not productName.
    """
    package = json.loads(CHAT_PACKAGE.read_text(encoding="utf-8"))
    nsis = package["build"].get("nsis", {})
    assert nsis.get("oneClick", True) and not nsis.get("perMachine", False), (
        "the chat installer left one-click per-user; re-derive its install dir"
    )
    return package["name"]


def test_install_directories_and_shortcuts_do_not_collide() -> None:
    # electron-builder names its desktop and Start-menu shortcuts <productName>.
    chat_name = _chat_build()["productName"]
    tray_dir = _iss_setting("DefaultDirName")
    iss = ISS.read_text(encoding="utf-8")

    chat_dir = f"{{localappdata}}\\programs\\{_chat_install_dir_name()}"
    assert tray_dir.lower() != chat_dir.lower()
    shortcut_names = re.findall(r'^Name: "\{[a-z]+\}\\([^"]+)";', iss, re.MULTILINE)
    assert shortcut_names, "no shortcuts found in TinyAssets.iss [Icons]"
    assert chat_name not in shortcut_names


def test_earlier_tray_shortcuts_are_removed_only_by_target() -> None:
    """Earlier tray installs used the chat app's shortcut name; the upgrade
    removes them only when they launch this tray, never by name alone."""
    iss = ISS.read_text(encoding="utf-8")
    for place in ("userstartup", "userdesktop", "group"):
        assert f"RemoveEarlierTrayShortcut(ExpandConstant('{{{place}}}\\TinyAssets.lnk'))" in iss
    body = iss.split("procedure RemoveEarlierTrayShortcut", 1)[1].split("end;", 2)
    guarded = body[0] + "end;" + body[1]
    assert "ExpandConstant('{app}\\TinyAssets.exe')" in guarded
    assert guarded.index("CompareText(") < guarded.index("DeleteFile(Path)")
    lifecycle = Path(__file__).with_name("windows_lifecycle.ps1").read_text(encoding="utf-8")
    assert "Programs\\tinyassets-desktop\\TinyAssets.exe" in lifecycle
    assert "Get-TrayStartupLinks" in lifecycle


def test_every_tray_installer_glob_names_the_server_installer() -> None:
    text = (WORKFLOWS / "desktop-release.yml").read_text(encoding="utf-8")
    globs = re.findall(r"packaging/dist/windows/(TinyAssets\w*Setup-)", text)
    assert globs and set(globs) == {"TinyAssetsServerSetup-"}
    lifecycle = (Path(__file__).with_name("windows_lifecycle.ps1")).read_text(encoding="utf-8")
    # The lifecycle test probes the directory the installer actually uses.
    tray_dir = _iss_setting("DefaultDirName").replace("{localappdata}\\", "")
    assert f'$env:LOCALAPPDATA "{tray_dir}"' in lifecycle


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
