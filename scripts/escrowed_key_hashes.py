"""Print `NAME sha256-or-ABSENT` for each escrowed key, as the host holds it.

Runs ON the production host (`ssh ... "sudo python3 -" < this file`). Stdlib
only. Prints hashes, never values; the caller compares them and prints only
match/mismatch. The value is read the way Compose reads an env file for these
single-line assignments: the last `NAME=` line wins, and one pair of
surrounding quotes is removed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# name -> the host file it lives in
ESCROWED_KEYS: dict[str, str] = {
    "TINYASSETS_SESSION_SEAL_KEY": "/etc/tinyassets/env",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY": "/etc/tinyassets/env",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": "/etc/tinyassets/env",
    "TINYASSETS_APP_INGRESS_HMAC_KEY": "/etc/tinyassets/app-ingress.env",
}


def host_value(text: str, name: str) -> str | None:
    value = None
    for line in text.splitlines():
        if line.startswith(name + "="):
            value = line.split("=", 1)[1]
    if value is not None and len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    for name, path in ESCROWED_KEYS.items():
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            text = ""
        value = host_value(text, name)
        print(name, digest(value) if value else "ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
