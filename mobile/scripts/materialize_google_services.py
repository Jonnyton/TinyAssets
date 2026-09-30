#!/usr/bin/env python3
"""Put Firebase's ``google-services.json`` into the generated Android project.

The file is build input, never source: this repo is public, so it is not
committed (``mobile/.gitignore`` covers it) and is materialised at build time
from a secret, the same way the upload keystore is -- the keystore's secret
names live in ``android-release.yml``; this one's are:

* ``ANDROID_GOOGLE_SERVICES_JSON_B64`` -- the file, base64-encoded (CI secret).
* ``ANDROID_GOOGLE_SERVICES_JSON_FILE`` -- a path to the file, for a local or
  container build. When unset, ``/keys/google-services.json`` is tried, which is
  where ``mobile/container`` mounts ``~/.tinyassets/android``.

Not configured is a supported state, not an error: nothing is written, the log
says plainly that push is DISABLED in this build, and Gradle's google-services
plugin (which Capacitor's generated ``app/build.gradle`` applies only when the
file is present) stays off. The app still builds and runs; the owner simply
cannot turn phone notifications on. A file that IS supplied but is unusable
fails loudly -- a half-configured build that looks like a working one is the
failure this script exists to prevent.

The contents are never printed: only the project id and package name, which the
Play listing already shows.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from pathlib import Path

DEFAULT_MOBILE = Path(__file__).resolve().parents[1]
CONTAINER_DEFAULT = Path("/keys/google-services.json")
MAX_BYTES = 256 * 1024


def _source(env: dict[str, str]) -> tuple[str, bytes | None]:
    """``(where it came from, raw bytes)``, or ``("", None)`` when unset."""
    encoded = (env.get("ANDROID_GOOGLE_SERVICES_JSON_B64") or "").strip()
    if encoded:
        try:
            return "ANDROID_GOOGLE_SERVICES_JSON_B64", base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                "ANDROID_GOOGLE_SERVICES_JSON_B64 is set but is not valid base64"
            ) from exc
    named = (env.get("ANDROID_GOOGLE_SERVICES_JSON_FILE") or "").strip()
    path = Path(named) if named else CONTAINER_DEFAULT
    if path.is_file():
        return str(path), path.read_bytes()
    if named:
        raise ValueError(f"ANDROID_GOOGLE_SERVICES_JSON_FILE names a missing file: {path}")
    return "", None


def validate(raw: bytes, app_id: str) -> dict:
    """The parsed document, or ValueError. Checks the package it is FOR."""
    if len(raw) > MAX_BYTES:
        raise ValueError("google-services.json is implausibly large")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("google-services.json is not JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("google-services.json is not a JSON object")
    info = document.get("project_info")
    if not isinstance(info, dict) or not str(info.get("project_id") or "").strip():
        raise ValueError("google-services.json has no project_info.project_id")
    packages = {
        ((client.get("client_info") or {}).get("android_client_info") or {}).get("package_name")
        for client in document.get("client") or []
        if isinstance(client, dict)
    }
    if app_id not in packages:
        # Firebase's own Gradle plugin fails on this too, but later and with a
        # message about a missing client. Say which app the file is for.
        listed = sorted(p for p in packages if p)
        raise ValueError(f"google-services.json is not for {app_id} (it lists {listed})")
    return document


def materialize(mobile: Path, env: dict[str, str]) -> bool:
    """Write the file if one is configured. Returns whether push is enabled."""
    from configure_android_release import load_release

    app_id = load_release(mobile).app_id
    origin, raw = _source(env)
    if raw is None:
        print(
            "push DISABLED in this build: no google-services.json configured "
            "(set ANDROID_GOOGLE_SERVICES_JSON_B64 or ANDROID_GOOGLE_SERVICES_JSON_FILE; "
            "docs/host-actions.md, 'Firebase project for phone notifications'). "
            "The app builds and runs; phone notifications cannot be turned on."
        )
        return False
    document = validate(raw, app_id)
    target = mobile / "android" / "app" / "google-services.json"
    if not target.parent.is_dir():
        raise ValueError(f"{target.parent} does not exist -- run `npx cap add android` first")
    target.write_bytes(raw)
    print(
        f"push ENABLED: google-services.json from {origin} "
        f"(project {document['project_info']['project_id']}, package {app_id})"
    )
    return True


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    mobile = DEFAULT_MOBILE
    if argv:
        mobile = Path(argv[0]).resolve()
    try:
        materialize(mobile, dict(os.environ))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
