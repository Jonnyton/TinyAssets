"""Finish the generated iOS project so in-app OAuth works.

`npx cap add ios` generates ios/ (gitignored); this runs right after it in CI
(and locally) to register the ``tinyassets://auth`` custom URL scheme in the
app's Info.plist (CFBundleURLTypes), so the in-app OAuth browser tab can hand
the sign-in code back to the app — the iOS counterpart of the Android
intent-filter added by add_app_scheme.py.

iOS needs no loopback foreground-service (unlike Android's dataSync service):
ASWebAuthenticationSession + the custom scheme carry the sign-in return natively.

Idempotent.
"""

from __future__ import annotations

import pathlib
import sys

MOBILE = pathlib.Path(__file__).resolve().parents[1]
INFO_PLIST = MOBILE / "ios" / "App" / "App" / "Info.plist"

# The CFBundleURLTypes block registering the tinyassets:// scheme. Inserted once,
# right before the plist's final closing </dict>.
URL_TYPES_BLOCK = """\t<key>CFBundleURLTypes</key>
\t<array>
\t\t<dict>
\t\t\t<key>CFBundleURLName</key>
\t\t\t<string>io.tinyassets.app</string>
\t\t\t<key>CFBundleURLSchemes</key>
\t\t\t<array>
\t\t\t\t<string>tinyassets</string>
\t\t\t</array>
\t\t</dict>
\t</array>
"""


def main() -> int:
    if not INFO_PLIST.exists():
        print(f"Info.plist not found at {INFO_PLIST} — run `npx cap add ios` first.")
        return 1
    text = INFO_PLIST.read_text(encoding="utf-8")
    if "<string>tinyassets</string>" in text:
        print("tinyassets URL scheme already registered in Info.plist — nothing to do.")
        return 0
    marker = "</dict>\n</plist>"
    if marker not in text:
        # Tolerate trailing whitespace variations.
        idx = text.rfind("</dict>")
        if idx == -1:
            print("::error:: could not find closing </dict> in Info.plist")
            return 1
        new_text = text[:idx] + URL_TYPES_BLOCK + text[idx:]
    else:
        new_text = text.replace(marker, URL_TYPES_BLOCK + marker, 1)
    INFO_PLIST.write_text(new_text, encoding="utf-8")
    # Verify.
    check = INFO_PLIST.read_text(encoding="utf-8")
    if "<string>tinyassets</string>" not in check:
        print("::error:: failed to register the tinyassets URL scheme")
        return 1
    print("registered tinyassets:// URL scheme in Info.plist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
