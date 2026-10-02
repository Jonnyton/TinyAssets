"""The Android push build: Firebase config from a secret, and the native wiring.

``google-services.json`` is build input on a public repo, so it is never
committed and is materialised from a secret. The contract these pin:

* not configured is a supported state -- the build proceeds, says push is
  DISABLED, and writes nothing;
* configured-but-wrong fails loudly, including a file minted for another app;
* the file's contents never reach the log;
* the manifest swap that makes the app (not the plugin) draw the notification
  is idempotent, and the release gate refuses a manifest where the plugin's own
  service would survive the merge.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Loaded in dependency order: the scripts import each other by bare name.
sys.path.insert(0, str(MOBILE / "scripts"))
try:
    _load("configure_android_release", MOBILE / "scripts/configure_android_release.py")
    materialize = _load(
        "materialize_google_services", MOBILE / "scripts/materialize_google_services.py"
    )
    scheme = _load("add_app_scheme_push", MOBILE / "scripts/add_app_scheme.py")
    verify = _load("verify_android_release_push", MOBILE / "scripts/verify_android_release.py")
finally:
    sys.path.pop(0)

APP_ID = "io.tinyassets.app"
SECRET_MARKER = "AIza-not-a-real-key-but-must-not-be-logged"


def _document(package: str = APP_ID) -> dict:
    return {
        "project_info": {"project_number": "1", "project_id": "proj-test"},
        "client": [{
            "client_info": {
                "mobilesdk_app_id": "1:1:android:abc",
                "android_client_info": {"package_name": package},
            },
            "api_key": [{"current_key": SECRET_MARKER}],
        }],
    }


def _mobile(tmp_path: Path) -> Path:
    mobile = tmp_path / "mobile"
    (mobile / "android/app").mkdir(parents=True)
    (mobile / "android-release.json").write_text(json.dumps({
        "appId": APP_ID, "versionCode": 5, "versionName": "1.0.4",
        "minSdk": 24, "targetSdk": 36, "compileSdk": 36,
    }), encoding="utf-8")
    return mobile


def _b64(document) -> str:
    raw = document if isinstance(document, bytes) else json.dumps(document).encode()
    return base64.b64encode(raw).decode("ascii")


# --- google-services.json ------------------------------------------------------


def test_unconfigured_build_succeeds_with_push_disabled_and_writes_nothing(
    tmp_path, capsys, monkeypatch,
):
    monkeypatch.setattr(materialize, "CONTAINER_DEFAULT", tmp_path / "absent.json")
    mobile = _mobile(tmp_path)

    assert materialize.materialize(mobile, {}) is False

    assert "push DISABLED" in capsys.readouterr().out
    assert not (mobile / "android/app/google-services.json").exists()


def test_a_configured_secret_is_written_and_its_contents_are_not_logged(
    tmp_path, capsys,
):
    mobile = _mobile(tmp_path)

    enabled = materialize.materialize(
        mobile, {"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64(_document())},
    )

    assert enabled is True
    written = json.loads((mobile / "android/app/google-services.json").read_text("utf-8"))
    assert written["project_info"]["project_id"] == "proj-test"
    out = capsys.readouterr().out
    assert "push ENABLED" in out and "proj-test" in out
    assert SECRET_MARKER not in out


def test_a_file_without_the_debug_client_says_debug_builds_have_no_push(tmp_path, capsys):
    # The debug build installs as io.tinyassets.app.debug; Firebase's plugin
    # refuses that variant without its own client, so the log must say why.
    mobile = _mobile(tmp_path)
    materialize.materialize(mobile, {"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64(_document())})
    out = capsys.readouterr().out
    assert "no io.tinyassets.app.debug client" in out and "processDebugGoogleServices" in out

    both = _document()
    both["client"].append(_document(APP_ID + ".debug")["client"][0])
    materialize.materialize(mobile, {"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64(both)})
    assert "debug builds:" not in capsys.readouterr().out


def test_a_file_path_is_an_equivalent_source(tmp_path):
    mobile = _mobile(tmp_path)
    source = tmp_path / "gs.json"
    source.write_text(json.dumps(_document()), encoding="utf-8")

    assert materialize.materialize(
        mobile, {"ANDROID_GOOGLE_SERVICES_JSON_FILE": str(source)},
    ) is True
    assert (mobile / "android/app/google-services.json").is_file()


@pytest.mark.parametrize("env,match", [
    ({"ANDROID_GOOGLE_SERVICES_JSON_B64": "!!not base64!!"}, "base64"),
    ({"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64(b"not json")}, "not JSON"),
    ({"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64([1])}, "not a JSON object"),
    ({"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64({"client": []})}, "project_id"),
    ({"ANDROID_GOOGLE_SERVICES_JSON_B64": _b64(_document("com.someone.else"))},
     "not for io.tinyassets.app"),
    ({"ANDROID_GOOGLE_SERVICES_JSON_FILE": "/nope/missing.json"}, "missing file"),
])
def test_a_supplied_but_unusable_config_fails_loudly(tmp_path, env, match):
    mobile = _mobile(tmp_path)

    with pytest.raises(ValueError, match=match):
        materialize.materialize(mobile, env)

    assert not (mobile / "android/app/google-services.json").exists()


def test_main_exits_nonzero_on_a_bad_config_and_zero_when_unconfigured(
    tmp_path, monkeypatch, capsys,
):
    mobile = _mobile(tmp_path)
    monkeypatch.setattr(materialize, "CONTAINER_DEFAULT", tmp_path / "absent.json")
    monkeypatch.delenv("ANDROID_GOOGLE_SERVICES_JSON_B64", raising=False)
    monkeypatch.delenv("ANDROID_GOOGLE_SERVICES_JSON_FILE", raising=False)
    assert materialize.main([str(mobile)]) == 0

    monkeypatch.setenv("ANDROID_GOOGLE_SERVICES_JSON_B64", _b64(b"garbage"))
    assert materialize.main([str(mobile)]) == 1
    assert "error:" in capsys.readouterr().err


def test_the_config_file_can_never_be_committed():
    ignore = (MOBILE / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "google-services.json" in ignore
    tracked = subprocess.run(
        ["git", "ls-files", "*google-services.json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert tracked.strip() == ""


def test_workflow_and_container_materialise_it_from_a_secret_not_a_literal():
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")
    assert "secrets.ANDROID_GOOGLE_SERVICES_JSON_B64" in workflow
    assert "materialize_google_services.py" in workflow
    build = (MOBILE / "container/build.sh").read_text(encoding="utf-8")
    assert "materialize_google_services.py" in build


# --- the manifest swap ---------------------------------------------------------

_BASE_MANIFEST = (
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
    '  <application android:label="TinyAssets">\n'
    "  </application>\n</manifest>\n"
)
_BASE_GRADLE = "android {\n}\n\ndependencies {\n    implementation 'x:y:1'\n}\n"


def _generated(tmp_path, monkeypatch):
    android = tmp_path / "android"
    (android / "app").mkdir(parents=True)
    manifest = android / "app/AndroidManifest.xml"
    gradle = android / "app/build.gradle"
    manifest.write_text(_BASE_MANIFEST, encoding="utf-8")
    gradle.write_text(_BASE_GRADLE, encoding="utf-8")
    monkeypatch.setattr(scheme, "MANIFEST", manifest)
    monkeypatch.setattr(scheme, "APP_BUILD_GRADLE", gradle)
    return manifest, gradle


def test_the_app_service_replaces_the_plugins_and_firebase_reaches_the_app_module(
    tmp_path, monkeypatch,
):
    manifest, gradle = _generated(tmp_path, monkeypatch)

    assert scheme.register_notifications() == 0

    text = manifest.read_text(encoding="utf-8")
    assert 'xmlns:tools="http://schemas.android.com/tools"' in text
    assert 'android:name=".TinyAssetsMessagingService"' in text
    assert 'android:exported="false"' in text
    assert scheme.PLUGIN_SERVICE in text and 'tools:node="remove"' in text
    assert scheme.FIREBASE_MESSAGING in gradle.read_text(encoding="utf-8")


def test_registering_notifications_twice_changes_nothing(tmp_path, monkeypatch):
    manifest, gradle = _generated(tmp_path, monkeypatch)
    scheme.register_notifications()
    first = (manifest.read_text("utf-8"), gradle.read_text("utf-8"))

    assert scheme.register_notifications() == 0

    assert (manifest.read_text("utf-8"), gradle.read_text("utf-8")) == first
    assert first[1].count(scheme.FIREBASE_MESSAGING) == 1
    assert first[0].count("TinyAssetsMessagingService") == 1


def test_a_gradle_file_without_a_dependencies_block_is_an_error(tmp_path, monkeypatch):
    _manifest, gradle = _generated(tmp_path, monkeypatch)
    gradle.write_text("android {\n}\n", encoding="utf-8")

    assert scheme.register_notifications() == 1


def test_a_manifest_without_the_app_service_is_refused(tmp_path):
    from tests.test_android_release_pipeline import _release, _source_manifest

    text = _source_manifest().replace(
        '<service android:name=".TinyAssetsMessagingService" android:exported="false">'
        '<intent-filter><action android:name="com.google.firebase.MESSAGING_EVENT"/>'
        "</intent-filter></service>",
        "",
    )
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="TinyAssetsMessagingService"):
        verify.verify_manifest(manifest, _release(), merged=False)


def test_a_surviving_plugin_service_fails_the_manifest_gate(tmp_path):
    from tests.test_android_release_pipeline import _release, _source_manifest

    text = _source_manifest().replace(
        "</application>",
        '<service android:name="com.capacitorjs.plugins.pushnotifications.MessagingService" '
        'android:exported="false"/></application>',
    )
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="must be removed"):
        verify.verify_manifest(manifest, _release(), merged=False)


def test_firebase_merged_permissions_are_allowed_only_in_the_merged_manifest(tmp_path):
    from tests.test_android_release_pipeline import _release, _source_manifest

    extra = "".join(
        f'<uses-permission android:name="{name}"/>'
        for name in verify.MERGED_ONLY_PERMISSIONS
    )
    text = _source_manifest().replace("<application", extra + "<application", 1)
    manifest = tmp_path / "AndroidManifest.xml"
    manifest.write_text(text, encoding="utf-8")
    # Allowed where Firebase contributes them; never required of the source.
    verify.verify_manifest(manifest, _release(), merged=False)
    bare = tmp_path / "bare.xml"
    bare.write_text(_source_manifest(), encoding="utf-8")
    verify.verify_manifest(bare, _release(), merged=False)


# --- the native source ---------------------------------------------------------


def _java(name: str) -> str:
    return (MOBILE / "native/android" / name).read_text(encoding="utf-8")


def test_the_reply_intent_is_bound_to_a_secret_only_this_app_holds():
    service = _java("TinyAssetsMessagingService.java")
    injector = (MOBILE / "scripts/add_app_scheme.py").read_text(encoding="utf-8")

    # Stored privately, compared in constant time, required before any reply
    # text is honoured -- the activity is exported, so this is the whole gate.
    assert "Context.MODE_PRIVATE" in service and "SecureRandom" in service
    assert "MessageDigest.isEqual" in injector
    assert injector.index("MessageDigest.isEqual") < injector.index("NotificationReplyPlugin.park")
    # Only the reply is mutable (RemoteInput writes into it): never IMMUTABLE on
    # the reply at any API level, which is what silently dropped the text before
    # Android 12; the plain tap stays immutable.
    assert re.search(r"if \(!reply\) \{\s+flags \|= PendingIntent\.FLAG_IMMUTABLE;", service)
    assert "else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)" in service
    # Display is gated by the owner's switch, checked per arriving message and
    # set synchronously by the page -- so a message after sign-out is dropped
    # even if FCM has not finished deleting the token.
    assert "!armed.equals(recipient)" in service
    # Check-and-post and arm/disarm share one lock (FCM delivers on a worker
    # thread), a clear is fenced by recipient like everything else, and a Reply
    # carries the tag of the MESSAGE it came from, not whatever is armed later.
    assert service.count("synchronized (ARM_LOCK)") == 2
    assert service.index("synchronized (ARM_LOCK)") < service.index('"clear".equals')
    assert "intent.putExtra(EXTRA_RECIPIENT, recipient);" in service
    assert "armedRecipient(this));" not in service.split("private PendingIntent pending")[1]
    assert "!armed.equals(recipient)" in injector
    assert "static void setActive(Context context, boolean active, String recipient)" in service
    assert "setActive(PluginCall call)" in _java("NotificationReplyPlugin.java")
    # The only things an intent carries are the two ids, the secret and the
    # recipient tag: the notification has no credential to leak by construction.
    extras = re.findall(r"putExtra\((\w+)", service)
    assert sorted(extras) == [
        "EXTRA_ITEM_ID", "EXTRA_NONCE", "EXTRA_RECIPIENT", "EXTRA_REQUEST_ID",
    ]


def test_a_notification_opens_the_request_deep_link_and_ids_are_validated():
    injector = (MOBILE / "scripts/add_app_scheme.py").read_text(encoding="utf-8")
    assert '"https://tinyassets.io/app"' in injector
    assert '"?request=" + Uri.encode(requestId)' in injector
    assert '"&item=" + Uri.encode(itemId)' in injector
    assert "TinyAssetsMessagingService.safeId(" in injector
    assert "registerPlugin(NotificationReplyPlugin.class)" in injector


def test_every_native_source_is_installed_and_package_checked():
    for name in scheme.NOTIFY_SOURCES:
        assert name in verify.NATIVE_SOURCES
        assert f"package {APP_ID};" in _java(name)
