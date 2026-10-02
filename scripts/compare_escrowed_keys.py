"""Compare escrowed GitHub secrets with the host's hashes; print verdicts only.

Reads `NAME sha256-or-ABSENT` lines (from escrowed_key_hashes.py on the host)
on stdin, and the GitHub secret values from this process's environment. Prints
one verdict per key: match, MISMATCH, not-in-github or not-on-host. Never prints
a value or a hash. Exits 1 unless every key matches.
"""

from __future__ import annotations

import hashlib
import os
import sys

KEYS = (
    "TINYASSETS_SESSION_SEAL_KEY",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY",
    "TINYASSETS_APP_INGRESS_HMAC_KEY",
)


def verdicts(host_lines: str, env: dict[str, str]) -> dict[str, str]:
    host: dict[str, str] = {}
    for line in host_lines.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in KEYS:
            host[parts[0]] = parts[1]
    out: dict[str, str] = {}
    for name in KEYS:
        secret = env.get(name, "")
        on_host = host.get(name, "ABSENT")
        if not secret:
            out[name] = "not-in-github"
        elif on_host == "ABSENT":
            out[name] = "not-on-host"
        elif hashlib.sha256(secret.encode("utf-8")).hexdigest() == on_host:
            out[name] = "match"
        else:
            out[name] = "MISMATCH"
    return out


def main() -> int:
    result = verdicts(sys.stdin.read(), dict(os.environ))
    for name, verdict in result.items():
        print(f"{name}: {verdict}")
    return 0 if all(v == "match" for v in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
