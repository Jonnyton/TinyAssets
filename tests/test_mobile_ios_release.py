"""Release-shape guards for the generated Capacitor iOS application."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MOBILE = REPO / "mobile"
BUILD_WORKFLOW = REPO / ".github" / "workflows" / "ios-build.yml"
RELEASE_WORKFLOW = REPO / ".github" / "workflows" / "ios-release.yml"


def _load_asset_installer():
    path = MOBILE / "scripts" / "add_ios_assets.py"
    spec = importlib.util.spec_from_file_location("add_ios_assets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_catalog(directory: Path, filenames: set[str]) -> None:
    directory.mkdir(parents=True)
    (directory / "Contents.json").write_text(
        json.dumps({"images": [{"filename": name} for name in sorted(filenames)]}),
        encoding="utf-8",
    )


def test_ios_asset_installer_replaces_every_catalog_image(tmp_path: Path) -> None:
    installer = _load_asset_installer()
    catalog = tmp_path / "Assets.xcassets"
    icon_catalog = catalog / "AppIcon.appiconset"
    splash_catalog = catalog / "Splash.imageset"
    _write_catalog(icon_catalog, installer.ICON_FILES)
    _write_catalog(splash_catalog, installer.SPLASH_FILES)

    icon = MOBILE / "resources" / "icon.png"
    splash = MOBILE / "resources" / "splash.png"
    assert installer.png_color_type(icon) == 2
    assert installer.png_color_type(splash) == 2
    for name in installer.ICON_FILES:
        shutil.copyfile(icon, icon_catalog / name)
    for name in installer.SPLASH_FILES:
        shutil.copyfile(splash, splash_catalog / name)

    assert installer.install_assets(catalog, icon, splash) == 0
    for name in installer.ICON_FILES:
        assert (icon_catalog / name).read_bytes() == icon.read_bytes()
    for name in installer.SPLASH_FILES:
        assert (splash_catalog / name).read_bytes() == splash.read_bytes()


def test_ios_asset_installer_fails_on_capacitor_catalog_drift(tmp_path: Path) -> None:
    installer = _load_asset_installer()
    catalog = tmp_path / "Assets.xcassets"
    _write_catalog(catalog / "AppIcon.appiconset", {"new-template-icon.png"})
    _write_catalog(catalog / "Splash.imageset", installer.SPLASH_FILES)
    for name in installer.SPLASH_FILES:
        shutil.copyfile(
            MOBILE / "resources" / "splash.png",
            catalog / "Splash.imageset" / name,
        )
    (catalog / "AppIcon.appiconset" / "new-template-icon.png").write_bytes(
        (MOBILE / "resources" / "icon.png").read_bytes()
    )

    assert installer.install_assets(
        catalog,
        MOBILE / "resources" / "icon.png",
        MOBILE / "resources" / "splash.png",
    ) == 1


def test_ios_asset_installer_rejects_an_alpha_channel_in_store_art(tmp_path: Path) -> None:
    installer = _load_asset_installer()
    catalog = tmp_path / "Assets.xcassets"
    icon_catalog = catalog / "AppIcon.appiconset"
    splash_catalog = catalog / "Splash.imageset"
    _write_catalog(icon_catalog, installer.ICON_FILES)
    _write_catalog(splash_catalog, installer.SPLASH_FILES)

    real_icon = MOBILE / "resources" / "icon.png"
    splash = MOBILE / "resources" / "splash.png"
    alpha_icon = tmp_path / "alpha-icon.png"
    alpha_bytes = bytearray(real_icon.read_bytes())
    alpha_bytes[25] = 6  # PNG IHDR truecolor + alpha; CRC is irrelevant to this header check.
    alpha_icon.write_bytes(alpha_bytes)
    for name in installer.ICON_FILES:
        shutil.copyfile(real_icon, icon_catalog / name)
    for name in installer.SPLASH_FILES:
        shutil.copyfile(splash, splash_catalog / name)

    assert installer.install_assets(catalog, alpha_icon, splash) == 1


def test_ios_build_and_release_install_real_artwork() -> None:
    build_workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")
    assert "python3 scripts/add_ios_assets.py" in build_workflow
    assert build_workflow.count('".github/workflows/ios-release.yml"') == 2
    assert "python3 scripts/add_ios_assets.py" in RELEASE_WORKFLOW.read_text(encoding="utf-8")


def test_ios_release_is_manual_and_upload_is_opt_in() -> None:
    workflow = yaml.load(RELEASE_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["concurrency"] == {
        "group": "ios-release",
        "cancel-in-progress": "false",
    }
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["upload_to_testflight"]["default"] == "false"
    assert workflow["jobs"]["build-signed-ipa"]["environment"] == "app-store"
    upload_job = workflow["jobs"]["upload-testflight"]
    assert "inputs.upload_to_testflight" in upload_job["if"]
    assert upload_job["environment"] == "app-store"


def test_ios_release_fails_closed_and_never_submits_for_review() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    for required in (
        "profile bundle id is",
        "development provisioning profile supplied",
        "Apple Distribution signing identity",
        "codesign --verify --deep --strict",
        "xcrun altool --validate-app",
        "xcrun altool --upload-app",
        "shasum -a 256 -c SHA256SUMS",
    ):
        assert required in workflow
    assert "--submit" not in workflow
    assert "submitForReview" not in workflow


def test_ios_bundle_id_is_one_consistent_permanent_identifier() -> None:
    config = json.loads((MOBILE / "capacitor.config.json").read_text(encoding="utf-8"))
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    scheme_installer = (MOBILE / "scripts" / "add_ios_scheme.py").read_text(
        encoding="utf-8"
    )
    assert config["appId"] == "io.tinyassets.app"
    assert "BUNDLE_ID: io.tinyassets.app" in workflow
    assert "<string>io.tinyassets.app</string>" in scheme_installer


def test_mobile_build_chain_does_not_restore_the_vulnerable_asset_generator() -> None:
    package = json.loads((MOBILE / "package.json").read_text(encoding="utf-8"))
    lockfile = (MOBILE / "package-lock.json").read_text(encoding="utf-8")
    assert "@capacitor/assets" not in package.get("devDependencies", {})
    assert "capacitor-assets" not in package.get("scripts", {}).values()
    assert 'node_modules/@capacitor/assets' not in lockfile
    assert '"sharp"' not in lockfile
