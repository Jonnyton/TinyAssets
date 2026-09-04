#!/usr/bin/env python3
"""Fail closed on Android package, version, SDK, manifest, and artwork drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from configure_android_release import AndroidRelease, load_release

DEFAULT_MOBILE = Path(__file__).resolve().parents[1]
ANDROID_NS = "http://schemas.android.com/apk/res/android"
A = f"{{{ANDROID_NS}}}"


def _value(text: str, pattern: str, label: str) -> str:
    found = re.findall(pattern, text, flags=re.MULTILINE)
    if len(found) != 1:
        raise ValueError(f"expected exactly one {label}; found {len(found)}")
    return found[0]


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def verify_gradle(mobile: Path, release: AndroidRelease) -> None:
    gradle = (mobile / "android/app/build.gradle").read_text(encoding="utf-8")
    variables = (mobile / "android/variables.gradle").read_text(encoding="utf-8")
    checks = {
        "namespace": (
            _value(gradle, r'^\s*namespace\s*(?:=\s*)?["\']([^"\']+)', "namespace"),
            release.app_id,
        ),
        "applicationId": (
            _value(gradle, r'^\s*applicationId\s*(?:=\s*)?["\']([^"\']+)', "applicationId"),
            release.app_id,
        ),
        "versionCode": (
            _value(gradle, r"^\s*versionCode\s*(?:=\s*)?(\d+)", "versionCode"),
            str(release.version_code),
        ),
        "versionName": (
            _value(gradle, r'^\s*versionName\s*(?:=\s*)?["\']([^"\']+)', "versionName"),
            release.version_name,
        ),
        "minSdkVersion": (
            _value(variables, r"^\s*minSdkVersion\s*=\s*(\d+)", "minSdkVersion"),
            str(release.min_sdk),
        ),
        "targetSdkVersion": (
            _value(variables, r"^\s*targetSdkVersion\s*=\s*(\d+)", "targetSdkVersion"),
            str(release.target_sdk),
        ),
        "compileSdkVersion": (
            _value(variables, r"^\s*compileSdkVersion\s*=\s*(\d+)", "compileSdkVersion"),
            str(release.compile_sdk),
        ),
    }
    drift = [
        f"{name}={have!r}, expected {want!r}"
        for name, (have, want) in checks.items()
        if have != want
    ]
    if drift:
        raise ValueError("Android Gradle release drift: " + "; ".join(drift))


def verify_manifest(path: Path, release: AndroidRelease, *, merged: bool) -> None:
    root = ET.parse(path).getroot()
    if merged:
        values = {
            "package": root.get("package"),
            "versionCode": root.get(A + "versionCode"),
            "versionName": root.get(A + "versionName"),
        }
        wanted = {
            "package": release.app_id,
            "versionCode": str(release.version_code),
            "versionName": release.version_name,
        }
        drift = [
            f"{key}={values[key]!r}, expected {wanted[key]!r}"
            for key in wanted
            if values[key] != wanted[key]
        ]
        uses_sdk = root.find("uses-sdk")
        if uses_sdk is None:
            drift.append("merged manifest has no uses-sdk")
        else:
            for attr, expected in (
                ("minSdkVersion", release.min_sdk),
                ("targetSdkVersion", release.target_sdk),
            ):
                if uses_sdk.get(A + attr) != str(expected):
                    drift.append(f"{attr}={uses_sdk.get(A + attr)!r}, expected {expected}")
        if drift:
            raise ValueError("merged manifest release drift: " + "; ".join(drift))

    application = root.find("application")
    if application is None:
        raise ValueError(f"{path} has no application element")
    if application.get(A + "allowBackup") != "false":
        raise ValueError("android:allowBackup must be false for the remote authenticated shell")
    if application.get(A + "usesCleartextTraffic") != "false":
        raise ValueError("android:usesCleartextTraffic must be explicitly false")
    if merged and application.get(A + "debuggable") == "true":
        raise ValueError("release manifest is debuggable")

    permissions = {
        item.get(A + "name")
        for tag in ("uses-permission", "uses-permission-sdk-23")
        for item in root.findall(tag)
    }
    allowed = {
        "android.permission.INTERNET",
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.RECORD_AUDIO",
        f"{release.app_id}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
    }
    unexpected = sorted(str(item) for item in permissions - allowed)
    required = allowed - {f"{release.app_id}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"}
    missing = sorted(required - permissions)
    if unexpected or missing:
        raise ValueError(f"permission drift: missing={missing}, unexpected={unexpected}")

    components = []
    for tag in ("activity", "activity-alias", "service", "receiver", "provider"):
        components.extend(application.findall(tag))
    main = next(
        (item for item in components if (item.get(A + "name") or "").endswith("MainActivity")), None
    )
    if main is None or main.get(A + "exported") != "true":
        raise ValueError("MainActivity must be present and exported for the launcher/deep link")
    filters = main.findall("intent-filter")
    has_auth_callback = any(
        {action.get(A + "name") for action in intent_filter.findall("action")}
        >= {"android.intent.action.VIEW"}
        and {category.get(A + "name") for category in intent_filter.findall("category")}
        >= {"android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"}
        and any(
            data.get(A + "scheme") == "tinyassets" and data.get(A + "host") == "auth"
            for data in intent_filter.findall("data")
        )
        for intent_filter in filters
    )
    has_share = any(
        {action.get(A + "name") for action in intent_filter.findall("action")}
        >= {"android.intent.action.SEND"}
        and {category.get(A + "name") for category in intent_filter.findall("category")}
        >= {"android.intent.category.DEFAULT"}
        and any(data.get(A + "mimeType") == "text/plain" for data in intent_filter.findall("data"))
        for intent_filter in filters
    )
    if not has_auth_callback or not has_share:
        raise ValueError("MainActivity is missing the tinyassets://auth or share-to-app callback")

    service = next(
        (
            item
            for item in components
            if (item.get(A + "name") or "").endswith("LocalCallbackService")
        ),
        None,
    )
    if (
        service is None
        or service.get(A + "exported") != "false"
        or service.get(A + "foregroundServiceType") != "dataSync"
    ):
        raise ValueError(
            "LocalCallbackService must be non-exported and foregroundServiceType=dataSync"
        )

    for component in components:
        if (
            component.get(A + "exported") == "true"
            and component is not main
            and not component.get(A + "permission")
        ):
            raise ValueError(
                f"exported component lacks a protecting permission: {component.get(A + 'name')}"
            )


def verify_sources(mobile: Path, release: AndroidRelease) -> None:
    capacitor = json.loads((mobile / "capacitor.config.json").read_text(encoding="utf-8"))
    if capacitor.get("appId") != release.app_id:
        raise ValueError("capacitor appId differs from android-release.json")
    server = capacitor.get("server", {})
    if server.get("cleartext") is not False or server.get("androidScheme") != "https":
        raise ValueError("Capacitor Android transport must be HTTPS with cleartext=false")
    if not str(server.get("url", "")).startswith("https://"):
        raise ValueError("Capacitor server.url must be HTTPS")

    for name in (
        "LocalCallbackPlugin.java",
        "LocalCallbackService.java",
        "VoiceWebChromeClient.java",
    ):
        text = (mobile / "native/android" / name).read_text(encoding="utf-8")
        if not re.search(rf"^package\s+{re.escape(release.app_id)};", text, re.MULTILINE):
            raise ValueError(f"{name} package differs from {release.app_id}")
    plugin = (mobile / "native/android/LocalCallbackPlugin.java").read_text(encoding="utf-8")
    if f"package={release.app_id};end" not in plugin:
        raise ValueError("LocalCallbackPlugin intent package differs from release identity")
    notification_safeguards = (
        "Manifest.permission.POST_NOTIFICATIONS",
        '@Permission(alias = "notifications"',
        'getPermissionState("notifications") != PermissionState.GRANTED',
        'requestPermissionForAlias("notifications", call, "notificationPermissionCallback")',
        "@PermissionCallback",
        'call.reject("Notification permission is required while browser sign-in is active")',
    )
    missing = [item for item in notification_safeguards if item not in plugin]
    if missing:
        raise ValueError(f"LocalCallbackPlugin is missing notification safeguards: {missing}")
    voice = (mobile / "native/android/VoiceWebChromeClient.java").read_text(encoding="utf-8")
    safeguards = (
        'TRUSTED_SCHEME = "https"',
        'TRUSTED_HOST = "tinyassets.io"',
        "PermissionRequest.RESOURCE_AUDIO_CAPTURE",
        "resources.length == 1",
        "activity.hasWindowFocus()",
        "ActivityCompat.requestPermissions",
        "Manifest.permission.RECORD_AUDIO",
        "if (pendingRequest != null)",
        "onPermissionRequestCanceled",
        "request == pendingRequest",
        "isTrustedOrigin(current)",
        "track.stop()",
    )
    missing = [item for item in safeguards if item not in voice]
    if missing:
        raise ValueError(f"VoiceWebChromeClient is missing release safeguards: {missing}")


def verify_generated_java(mobile: Path, release: AndroidRelease) -> None:
    package_dir = mobile / "android/app/src/main/java" / Path(*release.app_id.split("."))
    main = (package_dir / "MainActivity.java").read_text(encoding="utf-8")
    if not re.search(rf"^package\s+{re.escape(release.app_id)};", main, re.MULTILINE):
        raise ValueError("generated MainActivity package differs from release identity")
    if "registerPlugin(LocalCallbackPlugin.class)" not in main:
        raise ValueError("generated MainActivity did not register LocalCallbackPlugin")
    if "new VoiceWebChromeClient(bridge, this)" not in main:
        raise ValueError("generated MainActivity did not install VoiceWebChromeClient")
    if "voiceChromeClient.stopCapture(bridge.getWebView())" not in main:
        raise ValueError("generated MainActivity does not stop microphone capture on pause")
    for name in (
        "LocalCallbackPlugin.java",
        "LocalCallbackService.java",
        "VoiceWebChromeClient.java",
    ):
        source = mobile / "native/android" / name
        generated = package_dir / name
        if not generated.is_file() or _sha256(generated) != _sha256(source):
            raise ValueError(f"generated native source differs from committed source: {generated}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_app_artwork(mobile: Path) -> None:
    launcher = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    foreground = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    fixed = {
        mobile / "resources/icon.png": (1024, 1024),
        mobile / "resources/splash.png": (2732, 2732),
    }
    for path, wanted in fixed.items():
        if _png_size(path) != wanted:
            raise ValueError(f"wrong committed artwork size: {path}, expected {wanted}")
    for density, side in launcher.items():
        for name in ("ic_launcher.png", "ic_launcher_round.png"):
            path = mobile / "resources/android" / f"mipmap-{density}" / name
            if _png_size(path) != (side, side):
                raise ValueError(f"wrong committed launcher size: {path}")
    for density, side in foreground.items():
        path = mobile / "resources/android" / f"mipmap-{density}" / "ic_launcher_foreground.png"
        if _png_size(path) != (side, side):
            raise ValueError(f"wrong committed adaptive foreground size: {path}")


def verify_play_artwork(mobile: Path) -> None:
    play = mobile.parent / "docs/ops/play-assets"
    for path, wanted in (
        (play / "icon-512.png", (512, 512)),
        (play / "feature-graphic-1024x500.png", (1024, 500)),
    ):
        if _png_size(path) != wanted:
            raise ValueError(f"wrong Play artwork size: {path}, expected {wanted}")
    screenshots = sorted((play / "screenshots").glob("*.png"))
    if len(screenshots) < 2:
        raise ValueError("Play listing requires at least two phone screenshots")
    for path in screenshots:
        width, height = _png_size(path)
        short, long = sorted((width, height))
        if short < 320 or long > 3840 or long > 2 * short:
            raise ValueError(
                f"Play screenshot outside 320..3840 / 2:1 bounds: {path} ({width}x{height})"
            )


def verify_committed_artwork(mobile: Path) -> None:
    verify_app_artwork(mobile)
    verify_play_artwork(mobile)


def verify_generated_artwork(mobile: Path) -> None:
    generated = mobile / "android/app/src/main/res"
    committed = mobile / "resources/android"
    for source in committed.rglob("*.png"):
        target = generated / source.relative_to(committed)
        if not target.is_file() or _sha256(target) != _sha256(source):
            raise ValueError(f"generated artwork differs from committed source: {target}")
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        if not (generated / "mipmap-anydpi-v26" / name).is_file():
            raise ValueError(f"missing adaptive icon XML: {name}")


def find_merged_manifest(mobile: Path) -> Path:
    root = mobile / "android/app/build/intermediates/merged_manifest/release"
    candidates = sorted(root.glob("**/AndroidManifest.xml"))
    if len(candidates) != 1:
        raise ValueError(
            f"expected one release merged manifest under {root}; found {len(candidates)}"
        )
    return candidates[0]


def verify(mobile: Path, *, merged: bool = False, source_only: bool = False) -> AndroidRelease:
    release = load_release(mobile)
    verify_sources(mobile, release)
    if source_only:
        verify_committed_artwork(mobile)
    else:
        verify_app_artwork(mobile)
    if source_only:
        print(
            f"verified Android release sources {release.app_id} "
            f"{release.version_name} ({release.version_code}) and committed artwork"
        )
        return release
    verify_gradle(mobile, release)
    verify_generated_java(mobile, release)
    verify_manifest(mobile / "android/app/src/main/AndroidManifest.xml", release, merged=False)
    verify_generated_artwork(mobile)
    if merged:
        verify_manifest(find_merged_manifest(mobile), release, merged=True)
    print(
        f"verified Android release {release.app_id} "
        f"{release.version_name} ({release.version_code}), "
        f"SDK {release.min_sdk}/{release.target_sdk}/{release.compile_sdk}, manifest and artwork"
    )
    return release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mobile-root", type=Path, default=DEFAULT_MOBILE)
    parser.add_argument(
        "--merged", action="store_true", help="also verify Gradle's release merged manifest"
    )
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="verify checked-in identity and artwork without a generated Android project",
    )
    parser.add_argument(
        "--artwork-only",
        action="store_true",
        help="verify committed mobile and Play artwork without release/package inputs",
    )
    args = parser.parse_args(argv)
    try:
        if args.artwork_only:
            if args.source_only or args.merged:
                raise ValueError("--artwork-only cannot be combined with other modes")
            mobile = args.mobile_root.resolve()
            verify_committed_artwork(mobile)
            print(f"verified committed Android and Play artwork under {mobile}")
            return 0
        if args.source_only and args.merged:
            raise ValueError("--source-only and --merged are mutually exclusive")
        verify(
            args.mobile_root.resolve(),
            merged=args.merged,
            source_only=args.source_only,
        )
    except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
