"""Print `NAME <sha256 | ABSENT | UNSUPPORTED>` for each escrowed key on the host.

Runs ON the production host (`ssh ... "sudo python3 -" < this file`). Stdlib
only. Prints hashes, never values; the caller compares them and prints only a
verdict.

It reads the env FILES, which is what the next container start loads, not
the environment of the running container.

Only the one shape these keys actually have is accepted (verified on prod
2026-10-02): exactly one `NAME=value` line, unquoted, single line. Compose
parses more (export prefixes, quoting, escapes, comments), and a partial
reimplementation of that grammar is how a check reports a false match. So any
other shape for a key yields UNSUPPORTED rather than a guess (Codex on #4283).
Trailing whitespace is stripped, as Compose does for unquoted values.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# name -> the host file it lives in
ESCROWED_KEYS: dict[str, str] = {
    "TINYASSETS_SESSION_SEAL_KEY": "/etc/tinyassets/env",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY": "/etc/tinyassets/env",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": "/etc/tinyassets/env",
    "TINYASSETS_APP_INGRESS_HMAC_KEY": "/etc/tinyassets/app-ingress.env",
}

UNSUPPORTED = object()


def host_value(text: str, name: str):
    """The value, None if absent, or UNSUPPORTED for any shape we will not guess at."""
    mentions = [line for line in text.splitlines()
                if re.match(rf"^\s*(export\s+)?{re.escape(name)}\s*=", line)]
    if not mentions:
        return None
    if len(mentions) != 1 or not mentions[0].startswith(name + "="):
        return UNSUPPORTED
    value = mentions[0].split("=", 1)[1].rstrip()
    if not value or value[0] in "'\"" or " #" in value:
        return UNSUPPORTED
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
        if value is None:
            print(name, "ABSENT")
        elif value is UNSUPPORTED:
            print(name, "UNSUPPORTED")
        else:
            print(name, digest(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
