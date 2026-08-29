"""Sealed server-side store for the app's AuthKit refresh tokens.

The onboarding app hands the browser an opaque *handle* and keeps the WorkOS
refresh token here. Two properties this module owns, both of which the previous
plaintext store lacked:

**Sealed at rest.** Every record is AES-GCM ciphertext under a process key, with
the handle's own bytes as the AAD -- so a record copied onto another handle's
filename does not decrypt. What this defends against is a reader of the *data
dir* that is not this process: a stray backup, a detached volume, a container
sidecar, a mounted-in tool. It is **not** a boundary against code executing
inside this process (see
``docs/concerns/2026-08-28-user-code-runs-in-process.md``) -- that needs a
process split, and encryption must not be mistaken for it. What sealing does buy
against that attacker is the key hygiene below.

**The key never reaches a child.** ``TINYASSETS_SESSION_SEAL_KEY`` is read once
and immediately popped from ``os.environ``, because provider children are spawned
from this process with a *copy* of the environment
(``tinyassets.providers.base.subprocess_env_without_api_keys`` copies
``os.environ`` wholesale). Without the pop, every ``claude -p`` / ``codex exec``
subprocess would inherit the key that opens every user's session.

**Handles rotate.** A refresh mints a NEW handle and marks the old one
superseded for a short grace window, so a captured handle stops working roughly
a rotation after capture instead of lasting the full 7-day TTL. The old handle
follows exactly ONE hop during grace -- long enough for a second tab that lost
the rotation race, short of walking a chain. If that one hop lands on a record
that has itself been superseded (two rotations inside 120s), the read fails
closed so the caller falls back to its cookie rather than presenting a token
AuthKit has already retired.

The filename is a keyed digest of the handle, never the handle: the handle is a
bearer credential, so using it as a filename published every live session to
anything that could list the directory.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_LOG = logging.getLogger("tinyassets.onboarding")

#: 32 bytes, base64url or hex. Absent -> ephemeral per-process key + a warning.
SEAL_KEY_ENV = "TINYASSETS_SESSION_SEAL_KEY"

#: Under ``.runtime/`` so it sits apart from user-visible universe state.
_STORE_DIRNAME = "app_refresh_sessions"
_LEGACY_DIRNAME = "app_refresh_sessions"

#: AuthKit's default maximum session length.
REFRESH_SESSION_TTL = 7 * 24 * 3600
#: How long a superseded handle keeps resolving. Covers a multi-tab rotation
#: race; short enough that a stolen handle dies about a rotation after capture.
GRACE_SECONDS = 120
#: ``secrets.token_urlsafe(32)`` is 43 url-safe characters.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_MAX_TOKEN = 4096
_RECORD_VERSION = 1

_key: bytes | None = None
_initialised: set[str] = set()


def _reset_for_tests() -> None:
    """Drop the key singleton and the per-directory init memo.

    Tests point ``TINYASSETS_DATA_DIR`` at a fresh tmp dir per test; without this
    the first test's key would seal records the next test cannot open, and the
    one-time legacy discard would be skipped for every directory after the first.
    """
    global _key
    _key = None
    _initialised.clear()


# --- the seal key -------------------------------------------------------------


def _decode_key(raw: str) -> bytes | None:
    """32 bytes from base64url or hex, else None. Standard base64 is tolerated."""
    text = raw.strip()
    if not text:
        return None
    if len(text) == 64:
        # 64 base64url chars would decode to 48 bytes, so this is unambiguous.
        try:
            return bytes.fromhex(text)
        except ValueError:
            return None
    padded = text.replace("+", "-").replace("/", "_")
    padded += "=" * (-len(padded) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError):
        return None
    return decoded if len(decoded) == 32 else None


def _load_key() -> bytes:
    raw = os.environ.get(SEAL_KEY_ENV, "")
    # Pop FIRST and unconditionally -- before any parse can fail and before any
    # provider child can be spawned. os.environ is copied wholesale into child
    # environments, so a key still sitting here is a key handed to every
    # subprocess the daemon starts.
    os.environ.pop(SEAL_KEY_ENV, None)
    if raw.strip():
        key = _decode_key(raw)
        if key is not None:
            return key
        _LOG.error(
            "%s is set but is not 32 bytes of base64url or hex; ignoring it",
            SEAL_KEY_ENV,
        )
    _LOG.warning(
        "%s is not configured: app refresh sessions are sealed with an ephemeral "
        "per-process key and will NOT survive a restart (every signed-in user "
        "re-logs-in). Set %s to 32 bytes, base64url or hex.",
        SEAL_KEY_ENV,
        SEAL_KEY_ENV,
    )
    return secrets.token_bytes(32)


def seal_key() -> bytes:
    """The process seal key, loaded once."""
    global _key
    if _key is None:
        _key = _load_key()
    return _key


# --- paths --------------------------------------------------------------------


def _handle_path_key(handle: str) -> str:
    """The on-disk name for a handle -- a keyed digest of it, never the handle.

    Keyed with the seal key (always present -- ephemeral if unconfigured), so a
    directory listing is not one ``sha256()`` of a guess away from a live bearer
    credential.
    """
    return hmac.new(seal_key(), handle.encode("utf-8"), hashlib.sha256).hexdigest()


def store_dir() -> Path:
    """The sealed store directory, created 0700, legacy plaintext discarded."""
    from tinyassets.storage import data_dir

    root = data_dir()
    directory = root / ".runtime" / _STORE_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    marker = str(directory)
    if marker not in _initialised:
        _initialised.add(marker)
        _discard_legacy_store(root)
        _sweep_expired(directory)
    return directory


def _record_path(handle: str) -> Path:
    """The ONLY place a record path is built -- one digest call, no exceptions."""
    return store_dir() / f"{_handle_path_key(handle)}.json"


def _discard_legacy_store(root: Path) -> None:
    """Delete the plaintext store outright. Never migrate it.

    Those files hold raw refresh tokens at whatever mode the process umask gave
    them (0644 was observed in production). Reading them to re-seal would mean
    trusting material we already treat as disclosed; the cost of refusing is one
    re-login.
    """
    legacy = root / _LEGACY_DIRNAME
    if not legacy.is_dir():
        return
    import shutil

    try:
        shutil.rmtree(legacy)
    except OSError as exc:
        _LOG.warning(
            "legacy plaintext refresh sessions could not be removed (%s): %s",
            legacy,
            exc.__class__.__name__,
        )
        return
    _LOG.warning("legacy plaintext refresh sessions discarded; users re-login once")


def _sweep_expired(directory: Path) -> None:
    """Drop records past their TTL on first use of the directory.

    ``exp`` is outside the ciphertext precisely so this works after a restart
    with an ephemeral key, when nothing in the directory can be opened and the
    filenames no longer match any live handle.
    """
    now = int(time.time())
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for path in entries:
        if path.suffix == ".tmp":
            _unlink(path)  # a write that died between write_text and os.replace
            continue
        if path.suffix != ".json":
            continue
        record = _read_json(path)
        if record is None or int(record.get("exp") or 0) < now:
            _unlink(path)


# --- record I/O ---------------------------------------------------------------


def _read_json(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _write_record(handle: str, record: dict) -> None:
    path = _record_path(handle)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    # Narrowed BEFORE the atomic swap, not after: the window in between is the
    # whole problem -- the file must never exist at the umask default.
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _unb64(text: object) -> bytes | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return base64.urlsafe_b64decode(text)
    except (binascii.Error, ValueError):
        return None


def _seal(handle: str, refresh_token: str) -> dict:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(seal_key()).encrypt(
        nonce, refresh_token.encode("utf-8"), handle.encode("utf-8")
    )
    return {
        "v": _RECORD_VERSION,
        "nonce": _b64(nonce),
        "ct": _b64(ciphertext),
        "exp": int(time.time()) + REFRESH_SESSION_TTL,
        "superseded_by": None,
        "grace_until": None,
    }


def _open(handle: str, record: dict) -> str:
    """The refresh token in ``record``, or "" if it is not this handle's."""
    if int(record.get("v") or 0) != _RECORD_VERSION:
        return ""
    nonce = _unb64(record.get("nonce"))
    ciphertext = _unb64(record.get("ct"))
    if nonce is None or ciphertext is None or len(nonce) != 12:
        return ""
    try:
        # AAD is the handle: a record copied to another handle's filename fails
        # here rather than handing that handle someone else's session.
        plaintext = AESGCM(seal_key()).decrypt(
            nonce, ciphertext, handle.encode("utf-8")
        )
    except (InvalidTag, ValueError):
        return ""
    try:
        token = plaintext.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return token if 0 < len(token) <= _MAX_TOKEN else ""


# --- the store API ------------------------------------------------------------


def valid_handle(handle: str) -> bool:
    return bool(_HANDLE_RE.match(handle or ""))


def mint(refresh_token: str) -> str:
    """A fresh handle sealing ``refresh_token``, or "" if there is nothing to seal."""
    if not refresh_token or len(refresh_token) > _MAX_TOKEN:
        return ""
    handle = secrets.token_urlsafe(32)
    _write_record(handle, _seal(handle, refresh_token))
    return handle


def read(handle: str) -> tuple[str, str]:
    """``(refresh_token, current_handle)`` for a live handle, else ``("", "")``.

    The returned handle is the one the token now lives under -- the same handle
    normally, the successor during a rotation grace. Callers rotate from THAT
    handle, so a grace read never resurrects a superseded chain.
    """
    if not valid_handle(handle):
        return ("", "")
    path = _record_path(handle)
    record = _read_json(path)
    if record is None:
        return ("", "")
    now = int(time.time())
    if int(record.get("exp") or 0) < now:
        _unlink(path)
        return ("", "")

    successor = record.get("superseded_by")
    if successor:
        if not isinstance(successor, str) or not valid_handle(successor):
            return ("", "")
        if now > int(record.get("grace_until") or 0):
            return ("", "")
        return _read_successor(successor, now)

    token = _open(handle, record)
    if not token:
        _unlink(path)
        return ("", "")
    return (token, handle)


def _read_successor(successor: str, now: int) -> tuple[str, str]:
    """One hop, no rotation, no write."""
    path = _record_path(successor)
    record = _read_json(path)
    if record is None:
        return ("", "")
    if int(record.get("exp") or 0) < now:
        _unlink(path)
        return ("", "")
    if record.get("superseded_by"):
        # Two rotations inside the grace window. Chaining further would hand back
        # a token AuthKit has already retired and the caller would 401 with no
        # way back; failing closed lets it fall through to the cookie instead.
        return ("", "")
    token = _open(successor, record)
    if not token:
        _unlink(path)
        return ("", "")
    return (token, successor)


def rotate(current_handle: str, new_refresh_token: str) -> str:
    """Seal ``new_refresh_token`` under a NEW handle; leave the old one in grace.

    The old record keeps its own (now stale) ciphertext -- nothing is re-sealed
    under a handle a caller may have chosen -- and simply learns where the
    session moved to.
    """
    new_handle = mint(new_refresh_token)
    if not new_handle or not valid_handle(current_handle):
        return new_handle
    path = _record_path(current_handle)
    record = _read_json(path)
    if record is None:
        return new_handle
    record["superseded_by"] = new_handle
    record["grace_until"] = int(time.time()) + GRACE_SECONDS
    _write_record(current_handle, record)
    return new_handle


def drop(handle: str) -> None:
    """End the session. Logout intent covers the successor too, not just this hop."""
    if not valid_handle(handle):
        return
    path = _record_path(handle)
    record = _read_json(path)
    if record is not None:
        successor = record.get("superseded_by")
        if isinstance(successor, str) and valid_handle(successor):
            _unlink(_record_path(successor))
    _unlink(path)
