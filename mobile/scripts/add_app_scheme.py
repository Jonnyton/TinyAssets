"""Register the tinyassets://auth deep link on the generated Android project.

`npx cap add android` generates android/ (gitignored); this runs right after it
in CI (and locally) to add the intent-filter that lets the in-app OAuth tab hand
the sign-in code back to the app. Idempotent.
"""

from __future__ import annotations

import pathlib
import sys

MANIFEST = pathlib.Path(__file__).resolve().parents[1] / "android/app/src/main/AndroidManifest.xml"
FILTER = """            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="tinyassets" android:host="auth" />
            </intent-filter>
"""


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST} (run `npx cap add android` first)", file=sys.stderr)
        return 1
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


if __name__ == "__main__":
    raise SystemExit(main())
