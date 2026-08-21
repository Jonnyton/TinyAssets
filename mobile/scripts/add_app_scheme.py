"""Finish the generated Android project so in-app OAuth works.

`npx cap add android` generates android/ (gitignored); this runs right after it
in CI (and locally) to:

1. register the tinyassets://auth deep link (intent-filter on MainActivity) so
   the in-app OAuth tab can hand the sign-in code back to the app;
2. install the LocalCallback plugin (mobile/native/android/LocalCallbackPlugin.java)
   and register it in MainActivity, so the app can catch a provider's
   http://localhost:PORT/auth/callback redirect — the same browser sign-in a
   desktop CLI completes, with no per-account "device code" setting needed.

Idempotent.
"""

from __future__ import annotations

import pathlib
import re
import sys

MOBILE = pathlib.Path(__file__).resolve().parents[1]
ANDROID = MOBILE / "android"
MANIFEST = ANDROID / "app/src/main/AndroidManifest.xml"
JAVA_PKG_DIR = ANDROID / "app/src/main/java/io/tinyassets/app"
MAIN_ACTIVITY = JAVA_PKG_DIR / "MainActivity.java"
PLUGIN_SRC = MOBILE / "native/android/LocalCallbackPlugin.java"
PLUGIN_DST = JAVA_PKG_DIR / "LocalCallbackPlugin.java"

FILTER = """            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="tinyassets" android:host="auth" />
            </intent-filter>
"""

MAIN_ACTIVITY_SRC = """package io.tinyassets.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Local (non-npm) plugin: the loopback OAuth catcher. Must be registered
        // before super.onCreate() loads the bridge.
        registerPlugin(LocalCallbackPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
"""


def register_scheme() -> int:
    text = MANIFEST.read_text(encoding="utf-8")
    if 'android:scheme="tinyassets"' in text:
        print("app scheme already registered")
        return 0
    marker = "</activity>"
    if marker not in text:
        print("no </activity> in manifest", file=sys.stderr)
        return 1
    # Capacitor's MainActivity is the first (and only) <activity>; launchMode is
    # singleTask in the template, so the VIEW intent reaches the running app via
    # onNewIntent -> Capacitor App plugin `appUrlOpen`.
    text = text.replace(marker, FILTER + "        " + marker, 1)
    MANIFEST.write_text(text, encoding="utf-8")
    print("registered tinyassets://auth intent-filter")
    return 0


def install_plugin() -> int:
    if not PLUGIN_SRC.exists():
        print(f"plugin source missing: {PLUGIN_SRC}", file=sys.stderr)
        return 1
    JAVA_PKG_DIR.mkdir(parents=True, exist_ok=True)
    PLUGIN_DST.write_text(PLUGIN_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    current = MAIN_ACTIVITY.read_text(encoding="utf-8") if MAIN_ACTIVITY.exists() else ""
    if "registerPlugin(LocalCallbackPlugin.class)" in current:
        print("LocalCallback plugin already registered")
        return 0
    if current and not re.search(r"class MainActivity extends BridgeActivity", current):
        print("unexpected MainActivity shape; refusing to overwrite", file=sys.stderr)
        return 1
    MAIN_ACTIVITY.write_text(MAIN_ACTIVITY_SRC, encoding="utf-8")
    print("installed + registered LocalCallback plugin")
    return 0


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST} (run `npx cap add android` first)", file=sys.stderr)
        return 1
    rc = register_scheme()
    if rc:
        return rc
    return install_plugin()


if __name__ == "__main__":
    raise SystemExit(main())
