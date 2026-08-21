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
SERVICE_SRC = MOBILE / "native/android/LocalCallbackService.java"
SERVICE_DST = JAVA_PKG_DIR / "LocalCallbackService.java"

# The loopback listener's keep-alive: a dataSync foreground service (Android
# 14 requires a declared type; dataSync needs no Play-review justification and
# its daily budget vastly exceeds a sign-in). Stopped when the flow ends.
SERVICE_XML = """        <service
            android:name=".LocalCallbackService"
            android:exported="false"
            android:foregroundServiceType="dataSync" />
"""
PERMISSIONS_XML = """    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
"""

FILTER = """            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="tinyassets" android:host="auth" />
            </intent-filter>
            <!-- Share-to-app fallback for the OpenAI sign-in: if the provider's
                 localhost redirect cannot reach the app (the phone froze it),
                 the stuck browser page still has the callback URL in its address
                 bar; the tab's Share button sends it here and MainActivity turns
                 it into the tinyassets://auth deep link. -->
            <intent-filter android:label="Finish sign-in in TinyAssets">
                <action android:name="android.intent.action.SEND" />
                <category android:name="android.intent.category.DEFAULT" />
                <data android:mimeType="text/plain" />
            </intent-filter>
"""

MAIN_ACTIVITY_SRC = r"""package io.tinyassets.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends BridgeActivity {
    // A shared OAuth callback URL (from the browser tab's Share button after a
    // failed localhost redirect). Only the loopback callback shape is accepted;
    // its query (code + state) is re-issued as the app's own deep link, which
    // the web layer verifies against the pending flow's state before use.
    private static final Pattern CALLBACK = Pattern.compile(
        "https?://(?:localhost|127\\.0\\.0\\.1)(?::\\d+)?/auth/callback\\?([^\\s]+)");

    private static Intent rewriteSharedCallback(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return intent;
        String text = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (text == null) return intent;
        Matcher m = CALLBACK.matcher(text);
        if (!m.find()) return intent;
        String query = m.group(1);
        int hash = query.indexOf('#');
        if (hash >= 0) query = query.substring(0, hash);
        Uri deep = Uri.parse("tinyassets://auth?provider=openai&" + query);
        return new Intent(Intent.ACTION_VIEW, deep);
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Local (non-npm) plugin: the loopback OAuth catcher. Must be registered
        // before super.onCreate() loads the bridge.
        registerPlugin(LocalCallbackPlugin.class);
        setIntent(rewriteSharedCallback(getIntent()));
        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(rewriteSharedCallback(intent));
    }
}
"""


def register_scheme() -> int:
    """Add each intent-filter independently, so a generated project patched by
    an OLDER version of this script still gains the newer filters."""
    text = MANIFEST.read_text(encoding="utf-8")
    marker = "</activity>"
    if marker not in text:
        print("no </activity> in manifest", file=sys.stderr)
        return 1
    # Capacitor's MainActivity is the first (and only) <activity>; launchMode is
    # singleTask in the template, so the VIEW intent reaches the running app via
    # onNewIntent -> Capacitor App plugin `appUrlOpen`.
    view_filter, send_filter = FILTER.split("            <!--", 1)
    send_filter = "            <!--" + send_filter
    added = []
    if 'android:scheme="tinyassets"' not in text:
        text = text.replace(marker, view_filter + "        " + marker, 1)
        added.append("tinyassets://auth")
    if 'android.intent.action.SEND' not in text:
        text = text.replace(marker, send_filter + "        " + marker, 1)
        added.append("share-to-app")
    if added:
        MANIFEST.write_text(text, encoding="utf-8")
        print("registered intent-filters: " + ", ".join(added))
    else:
        print("intent-filters already registered")
    return 0


def register_service() -> int:
    """Declare the keep-alive foreground service + its permissions."""
    text = MANIFEST.read_text(encoding="utf-8")
    changed = False
    if 'android:name=".LocalCallbackService"' not in text:
        marker = "</application>"
        if marker not in text:
            print("no </application> in manifest", file=sys.stderr)
            return 1
        text = text.replace(marker, SERVICE_XML + "    " + marker, 1)
        changed = True
    if "FOREGROUND_SERVICE_DATA_SYNC" not in text:
        marker = "</manifest>"
        if marker not in text:
            print("no </manifest> in manifest", file=sys.stderr)
            return 1
        text = text.replace(marker, PERMISSIONS_XML + marker, 1)
        changed = True
    if changed:
        MANIFEST.write_text(text, encoding="utf-8")
        print("registered LocalCallbackService + foreground-service permissions")
    else:
        print("service already registered")
    return 0


def install_plugin() -> int:
    for src in (PLUGIN_SRC, SERVICE_SRC):
        if not src.exists():
            print(f"plugin source missing: {src}", file=sys.stderr)
            return 1
    JAVA_PKG_DIR.mkdir(parents=True, exist_ok=True)
    PLUGIN_DST.write_text(PLUGIN_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    SERVICE_DST.write_text(SERVICE_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    current = MAIN_ACTIVITY.read_text(encoding="utf-8") if MAIN_ACTIVITY.exists() else ""
    if current == MAIN_ACTIVITY_SRC:
        print("MainActivity already current")
        return 0
    # Replace any RECOGNIZED MainActivity (Capacitor's template or an earlier
    # version written by this script) so upgrades pick up the share rewrite.
    if current and not re.search(r"class MainActivity extends BridgeActivity", current):
        print("unexpected MainActivity shape; refusing to overwrite", file=sys.stderr)
        return 1
    MAIN_ACTIVITY.write_text(MAIN_ACTIVITY_SRC, encoding="utf-8")
    print("installed LocalCallback plugin + MainActivity (plugin registration, share rewrite)")
    return 0


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST} (run `npx cap add android` first)", file=sys.stderr)
        return 1
    rc = register_scheme()
    if rc:
        return rc
    rc = register_service()
    if rc:
        return rc
    return install_plugin()


if __name__ == "__main__":
    raise SystemExit(main())
