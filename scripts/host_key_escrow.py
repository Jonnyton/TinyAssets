"""Host-side escrow of the keys a restored platform needs to read its own data.

Runs ON a host, as root, stdlib only. No human or agent ever sees a value: this
script never prints one, and the only output is key NAMES, hashes, and verdicts.

    host_key_escrow.py write <out>       write the escrow file (0600), or refuse
    host_key_escrow.py hashes-host       NAME <sha256|ABSENT|UNSUPPORTED> per key
    host_key_escrow.py verify            escrow on stdin vs this host: verdicts only
    host_key_escrow.py install <helper>  escrow on stdin -> host env files, set-once
    host_key_escrow.py check-manifest <file>  host keys vs a backup's hash manifest

Why these four: they exist only on the production host, and losing them leaves
restored data unusable. Sealed sessions cannot be opened, entitlement claims
cannot be verified (that key cannot be re-issued at all), push subscriptions
are orphaned, and app ingress cannot be checked
(docs/design-notes/2026-10-02-vault-key-escrow.md).

Where the escrow lives: the off-region bucket (tinyassets-offregion, nyc3), under
its own `escrow/` prefix, written by the nightly backup job with the droplet's
per-bucket key. It is PLAINTEXT in a private bucket. That is the same trust level
as /etc/tinyassets/env on the droplet today, and the same as the backups
themselves, which already hold /data in plaintext in that bucket. Encrypting it
needs a key that survives losing the droplet without a human holding it. At $0
there is no such place: GitHub secrets cannot be written by a workflow, and
anything the droplet holds dies with the droplet. A founder-held key is a later
nicety, accepted under the slim-until-paying-users rule.

Value shape: exactly one unquoted `NAME=value` line per key (verified on prod,
2026-10-02). Any other shape is UNSUPPORTED rather than guessed: a partial
reimplementation of Compose's grammar is how a check reports a false match.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

# The host's env directory. Overridable only so the backup harness can point
# it at a temp tree; production never sets it.
_ETC = os.environ.get("TINYASSETS_ESCROW_ETC", "/etc/tinyassets")

# name -> the host env file it lives in
ESCROWED_KEYS: dict[str, str] = {
    "TINYASSETS_SESSION_SEAL_KEY": f"{_ETC}/env",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY": f"{_ETC}/env",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": f"{_ETC}/env",
    "TINYASSETS_APP_INGRESS_HMAC_KEY": f"{_ETC}/app-ingress.env",
}

# Dedicated files get a nonexistent legacy path, as deploy-prod does for the
# HMAC files, so the env helper never migrates from the shared env.
_LEGACY_FOR = {
    f"{_ETC}/app-ingress.env": f"{_ETC}/no-app-ingress-legacy",
}

UNSUPPORTED = object()


def parse_value(text: str, name: str):
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


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def host_values() -> dict[str, object]:
    return {name: parse_value(_read(path), name) for name, path in ESCROWED_KEYS.items()}


def escrow_values(text: str) -> dict[str, object]:
    return {name: parse_value(text, name) for name in ESCROWED_KEYS}


def write(out: Path) -> int:
    values = host_values()
    bad = [name for name, value in values.items() if value is None or value is UNSUPPORTED]
    if bad:
        # Never escrow a partial or guessed set: a blank written over a good
        # escrow is how the copy you need disappears.
        print("refusing to escrow; missing or unsupported on this host: " + ", ".join(bad),
              file=sys.stderr)
        return 2
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        for name, value in values.items():
            handle.write(f"{name}={value}\n")
    return 0


def _verdict(host, escrow) -> str:
    if escrow is None:
        return "not-in-escrow"
    if escrow is UNSUPPORTED:
        return "escrow-format-unsupported"
    if host is None:
        return "not-on-host"
    if host is UNSUPPORTED:
        return "host-format-unsupported"
    return "match" if digest(host) == digest(escrow) else "MISMATCH"


def verify(escrow_text: str) -> int:
    host = host_values()
    escrow = escrow_values(escrow_text)
    verdicts = {name: _verdict(host[name], escrow[name]) for name in ESCROWED_KEYS}
    for name, verdict in verdicts.items():
        print(f"{name}: {verdict}")
    return 0 if all(v == "match" for v in verdicts.values()) else 1


def install(escrow_text: str, helper: str) -> int:
    """Set-once each key into its host file. Refuses (exit 1) on any mismatch."""
    escrow = escrow_values(escrow_text)
    bad = [n for n, v in escrow.items() if v is None or v is UNSUPPORTED]
    if bad:
        print("refusing to install; escrow is missing or unsupported for: " + ", ".join(bad),
              file=sys.stderr)
        return 2
    failed = 0
    for name, path in ESCROWED_KEYS.items():
        env = {**os.environ, "TINYASSETS_ENV_FILE": path}
        if path in _LEGACY_FOR:
            env["TINYASSETS_LEGACY_ENV_FILE"] = _LEGACY_FOR[path]
        result = subprocess.run(
            ["bash", helper, "set-once", name],
            input=str(escrow[name]), text=True, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            print(f"{name}: installed")
        else:
            # The helper's stderr names keys, never values; pass its exit code.
            print(f"{name}: refused (helper exit {result.returncode})")
            failed = 1
    return failed


def check_manifest(manifest_text: str) -> int:
    """Prove the keys on this host are the ones a restored backup was written under.

    The manifest (NAME sha256 lines) is written into every backup by backup.sh. A
    match for every key means restored sealed data will open under these keys.
    """
    expected: dict[str, str] = {}
    for line in manifest_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ESCROWED_KEYS:
            expected[parts[0]] = parts[1]
    host = host_values()
    ok = True
    for name in ESCROWED_KEYS:
        want = expected.get(name)
        have = host[name]
        if want is None or want in {"ABSENT", "UNSUPPORTED"}:
            verdict = "not-in-manifest"
        elif have is None or have is UNSUPPORTED:
            verdict = "not-on-host"
        else:
            verdict = "match" if digest(have) == want else "MISMATCH"
        ok = ok and verdict == "match"
        print(f"{name}: {verdict}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["write"] and len(argv) == 2:
        return write(Path(argv[1]))
    if argv == ["hashes-host"]:
        for name, value in host_values().items():
            if value is None:
                print(name, "ABSENT")
            elif value is UNSUPPORTED:
                print(name, "UNSUPPORTED")
            else:
                print(name, digest(value))
        return 0
    if argv == ["verify"]:
        return verify(sys.stdin.read())
    if argv[:1] == ["check-manifest"] and len(argv) == 2:
        return check_manifest(_read(argv[1]))
    if argv[:1] == ["install"] and len(argv) == 2:
        return install(sys.stdin.read(), argv[1])
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
