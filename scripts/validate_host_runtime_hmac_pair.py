"""Validate the production daemon/worker HMAC files without printing secrets."""

from __future__ import annotations

import base64
import binascii
import hmac
import stat
from pathlib import Path

REQUEST_PATH = Path("/etc/tinyassets/request-idempotency.env")
AGENT_PATH = Path("/etc/tinyassets/agent-interchange.env")
REQUEST_KEY = "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"
AGENT_KEY = "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY"
MIN_KEY_BYTES = 32


def _decode_secret(value: str) -> bytes:
    if not value or "\r" in value or "\n" in value:
        raise ValueError("secret must be non-empty single-line canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("secret must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("secret must use canonical standard base64 encoding")
    if len(decoded) < MIN_KEY_BYTES:
        raise ValueError(f"secret must decode to at least {MIN_KEY_BYTES} bytes")
    return decoded


def _read_dedicated_secret(
    path: Path,
    key: str,
    *,
    enforce_metadata: bool,
) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{path} must be a regular file")
    if enforce_metadata:
        import grp
        import pwd

        expected_uid = pwd.getpwnam("root").pw_uid
        expected_gid = grp.getgrnam("tinyassets").gr_gid
        if info.st_uid != expected_uid or info.st_gid != expected_gid:
            raise ValueError(f"{path} must be owned by root:tinyassets")
        if stat.S_IMODE(info.st_mode) != 0o640:
            raise ValueError(f"{path} must have mode 640")

    prefix = f"{key}="
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith(prefix):
            raise ValueError(f"{path} contains an unexpected setting")
        values.append(line[len(prefix) :])
    if len(values) != 1:
        raise ValueError(f"{path} must contain exactly one {key} setting")
    return _decode_secret(values[0])


def validate_pair(
    request_path: Path = REQUEST_PATH,
    agent_path: Path = AGENT_PATH,
    *,
    enforce_metadata: bool = True,
) -> None:
    request = _read_dedicated_secret(
        request_path,
        REQUEST_KEY,
        enforce_metadata=enforce_metadata,
    )
    agent = _read_dedicated_secret(
        agent_path,
        AGENT_KEY,
        enforce_metadata=enforce_metadata,
    )
    if hmac.compare_digest(request, agent):
        raise ValueError("request and agent-interchange HMAC keys must differ")


def main() -> int:
    try:
        validate_pair()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"::error::host runtime HMAC pair invalid: {exc}")
        return 1
    print("host runtime HMAC pair is canonical, distinct, and permission-safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
