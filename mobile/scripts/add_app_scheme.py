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
VOICE_CHROME_SRC = MOBILE / "native/android/VoiceWebChromeClient.java"
VOICE_CHROME_DST = JAVA_PKG_DIR / "VoiceWebChromeClient.java"

# The loopback listener's keep-alive: a dataSync foreground service. Android 14+
# requires the type in the manifest, and Play requires a matching Console
# declaration plus behavior video. Stopped when the user flow ends.
SERVICE_XML = """        <service
            android:name=".LocalCallbackService"
            android:exported="false"
            android:foregroundServiceType="dataSync" />
"""
REQUIRED_PERMISSIONS = (
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.RECORD_AUDIO",
)

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
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends BridgeActivity {
    private VoiceWebChromeClient voiceChromeClient;

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
        bridgeBuilder.addWebViewListener(new WebViewListener() {
            @Override
            public void onPageLoaded(WebView webView) {
                VoiceWebChromeClient.installMediaTracker(webView);
            }
        });
        setIntent(rewriteSharedCallback(getIntent()));
        super.onCreate(savedInstanceState);
        if (bridge != null) {
            voiceChromeClient = new VoiceWebChromeClient(bridge, this);
            bridge.getWebView().setWebChromeClient(voiceChromeClient);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(rewriteSharedCallback(intent));
    }

    @Override
    public void onPause() {
        if (voiceChromeClient != null && bridge != null) {
            voiceChromeClient.stopCapture(bridge.getWebView());
        }
        super.onPause();
    }

    @Override
    public void onStop() {
        if (voiceChromeClient != null && bridge != null) {
            voiceChromeClient.stopCaptureAndDeny(bridge.getWebView());
        }
        super.onStop();
    }

    @Override
    public void onDestroy() {
        if (voiceChromeClient != null && bridge != null) {
            voiceChromeClient.stopCaptureAndDeny(bridge.getWebView());
        }
        super.onDestroy();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        boolean handled = voiceChromeClient != null
            && voiceChromeClient.onRequestPermissionsResult(requestCode, permissions, results);
        if (handled) {
            return;
        }
        super.onRequestPermissionsResult(requestCode, permissions, results);
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
    if 'android:label="Finish sign-in in TinyAssets"' not in text:
        text = text.replace(marker, send_filter + "        " + marker, 1)
        added.append("share-to-app")
    if added:
        MANIFEST.write_text(text, encoding="utf-8")
        print("registered intent-filters: " + ", ".join(added))
    else:
        print("intent-filters already registered")
    return 0


def harden_application() -> int:
    """Keep authenticated WebView state out of backups and reject cleartext."""
    text = MANIFEST.read_text(encoding="utf-8")
    matches = list(re.finditer(r"<application\b[^>]*>", text, re.DOTALL))
    if len(matches) != 1:
        print(f"expected one <application> tag, found {len(matches)}", file=sys.stderr)
        return 1
    match = matches[0]
    tag = match.group(0)
    for attr, value in (
        ("android:allowBackup", "false"),
        ("android:usesCleartextTraffic", "false"),
    ):
        pattern = rf'{re.escape(attr)}="[^"]*"'
        if re.search(pattern, tag):
            tag = re.sub(pattern, f'{attr}="{value}"', tag, count=1)
        else:
            tag = tag[:-1] + f'\n        {attr}="{value}">'
    updated = text[: match.start()] + tag + text[match.end() :]
    if updated != text:
        MANIFEST.write_text(updated, encoding="utf-8")
        print("disabled Android backup + cleartext traffic")
    else:
        print("Android backup + cleartext hardening already current")
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
    marker = "</manifest>"
    if marker not in text:
        print("no </manifest> in manifest", file=sys.stderr)
        return 1
    for permission in REQUIRED_PERMISSIONS:
        if f'android:name="{permission}"' not in text:
            declaration = f'    <uses-permission android:name="{permission}" />\n'
            text = text.replace(marker, declaration + marker, 1)
            changed = True
    if changed:
        MANIFEST.write_text(text, encoding="utf-8")
        print("registered LocalCallbackService + foreground-service permissions")
    else:
        print("service already registered")
    return 0


def install_plugin() -> int:
    for src in (PLUGIN_SRC, SERVICE_SRC, VOICE_CHROME_SRC):
        if not src.exists():
            print(f"plugin source missing: {src}", file=sys.stderr)
            return 1
    JAVA_PKG_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve bytes so the release verifier's source hash stays stable on both
    # Windows and Linux regardless of newline translation.
    PLUGIN_DST.write_bytes(PLUGIN_SRC.read_bytes())
    SERVICE_DST.write_bytes(SERVICE_SRC.read_bytes())
    VOICE_CHROME_DST.write_bytes(VOICE_CHROME_SRC.read_bytes())
    current = MAIN_ACTIVITY.read_text(encoding="utf-8") if MAIN_ACTIVITY.exists() else ""
    if current == MAIN_ACTIVITY_SRC:
        print("MainActivity already current")
        return 0
    # Replace ONLY a recognized MainActivity: Capacitor's untouched template
    # (an empty BridgeActivity subclass) or a version this script wrote earlier
    # (carries its plugin registration). Anything hand-customized is left alone.
    template = bool(
        re.fullmatch(
            r"\s*package io\.tinyassets\.app;\s*import com\.getcapacitor\.BridgeActivity;\s*"
            r"public class MainActivity extends BridgeActivity\s*\{\s*\}\s*",
            current,
        )
    )
    ours = "registerPlugin(LocalCallbackPlugin.class)" in current
    if current and not (template or ours):
        print("customized MainActivity; refusing to overwrite", file=sys.stderr)
        return 1
    MAIN_ACTIVITY.write_text(MAIN_ACTIVITY_SRC, encoding="utf-8")
    print("installed LocalCallback plugin + MainActivity (plugin registration, share rewrite)")
    return 0


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST} (run `npx cap add android` first)", file=sys.stderr)
        return 1
    rc = harden_application()
    if rc:
        return rc
    rc = register_scheme()
    if rc:
        return rc
    rc = register_service()
    if rc:
        return rc
    return install_plugin()


if __name__ == "__main__":
    raise SystemExit(main())
