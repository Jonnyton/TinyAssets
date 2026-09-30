"""Web push (RFC 8030 + VAPID RFC 8292), for the browser and desktop app.

This is the channel that needs **nothing from anyone**: the VAPID keypair is
self-issued (``scripts/webpush_keys.py``), so the whole request-to-notification
chain can be proven live before any third-party messaging project exists. That
is why it is built alongside the Android transport rather than after it.

Payload encryption is aes128gcm (RFC 8291). The subscription's own public key
and auth secret come from the owner's device row -- the browser minted them --
so nothing a caller supplies chooses a recipient or a key.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from tinyassets.notify import (
    OUTCOME_REFUSED,
    OUTCOME_SENT,
    OUTCOME_UNAVAILABLE,
    Notification,
    TransportFailed,
    TransportGone,
)

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10.0
_TTL_S = 86_400
#: RFC 8292: an assertion good for at most 24h. 12h leaves room for clock skew
#: at both ends without minting one per send.
_ASSERTION_LIFETIME_S = 12 * 3600
#: RFC 8291 record size. One record is enough for a bounded notification.
_RECORD_SIZE = 4096
_MAX_PLAINTEXT = _RECORD_SIZE - 17  # 16-byte tag + the 1-byte padding delimiter


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def record_budget() -> int:
    """The largest plaintext one record holds. The composer's byte budget.

    Exposed so composition can fit the record instead of discovering at the
    transport that it does not. A notification refused here is a notification
    the owner never gets, and the shape that caused it (emoji) is accepted
    input (gpt-6-astra round 2, 2026-09-29).
    """
    return _MAX_PLAINTEXT


def payload_bytes(notification: Notification) -> bytes:
    """Exactly the bytes :func:`webpush_transport` will encrypt.

    ONE definition, used by both the composer and the sender: a second copy of
    "how big is this" is how the two drift and the budget stops meaning
    anything.
    """
    return json.dumps({
        "title": notification.title,
        "body": notification.body,
        "data": notification.data,
        "silent": notification.silent,
    }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _subscription(device: dict) -> dict:
    """The browser's own subscription document off the device row."""
    raw = device.get("token")
    document = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(document, dict):
        raise TransportFailed(OUTCOME_REFUSED)
    endpoint = str(document.get("endpoint") or "")
    keys = document.get("keys") or {}
    if not endpoint.startswith("https://") or not isinstance(keys, dict):
        raise TransportFailed(OUTCOME_REFUSED)
    if not keys.get("p256dh") or not keys.get("auth"):
        raise TransportFailed(OUTCOME_REFUSED)
    return {"endpoint": endpoint, "p256dh": str(keys["p256dh"]),
            "auth": str(keys["auth"])}


def _encrypt(plaintext: bytes, p256dh: str, auth: str) -> bytes:
    """aes128gcm-encrypt one record for this subscription (RFC 8291)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    if len(plaintext) > _MAX_PLAINTEXT:
        # The caller composes a bounded notification, so this is a guard, not a
        # truncation point: silently cutting an encrypted body would ship a
        # half-sentence to a lock screen.
        raise TransportFailed(OUTCOME_REFUSED)
    client_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), _unb64(p256dh)
    )
    server_private = ec.generate_private_key(ec.SECP256R1())
    server_public_bytes = server_private.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    shared = server_private.exchange(ec.ECDH(), client_public)
    auth_secret = _unb64(auth)
    client_public_bytes = client_public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    prk = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=auth_secret,
        info=b"WebPush: info\x00" + client_public_bytes + server_public_bytes,
    ).derive(shared)
    salt = os.urandom(16)
    key = HKDF(
        algorithm=hashes.SHA256(), length=16, salt=salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(prk)
    nonce = HKDF(
        algorithm=hashes.SHA256(), length=12, salt=salt,
        info=b"Content-Encoding: nonce\x00",
    ).derive(prk)
    body = AESGCM(key).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + struct.pack("!I", _RECORD_SIZE) + bytes([len(server_public_bytes)])
    return header + server_public_bytes + body


def _assertion(private_key_pem: str, subject: str, endpoint: str) -> tuple[str, str]:
    """A VAPID ``(token, public_key)`` pair for this endpoint's origin."""
    import jwt
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    parts = urllib.parse.urlsplit(endpoint)
    token = jwt.encode(
        {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int(time.time()) + _ASSERTION_LIFETIME_S,
            "sub": subject,
        },
        key,
        algorithm="ES256",
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return token, _b64(public)


def vapid_private_pem(env) -> str:
    """The configured VAPID private key as a PEM, or "".

    The one parser of TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY. An env file holds one
    line per variable, so the PEM is written there with its newlines escaped as
    ``\\n``; both forms are accepted.
    """
    pem = (env.get("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY") or "").strip()
    return pem.replace("\\n", "\n")


def webpush_transport(env: dict[str, str]):
    """Build the web transport, or raise ValueError on a bad key."""
    from cryptography.hazmat.primitives import serialization

    pem = vapid_private_pem(env)
    subject = (env.get("TINYASSETS_WEBPUSH_VAPID_SUBJECT") or "").strip()
    if not subject.startswith(("mailto:", "https://")):
        raise ValueError("VAPID subject must be a mailto: or https:// URL")
    try:
        serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except Exception as exc:  # noqa: BLE001 - a key we cannot load is a config fault
        raise ValueError("VAPID private key is not a usable PEM key") from exc

    def send(device: dict, notification: Notification) -> str:
        subscription = _subscription(device)
        payload = payload_bytes(notification)
        token, public = _assertion(pem, subject, subscription["endpoint"])
        request = urllib.request.Request(
            subscription["endpoint"],
            data=_encrypt(payload, subscription["p256dh"], subscription["auth"]),
            method="POST",
            headers={
                "Authorization": f"vapid t={token}, k={public}",
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": str(_TTL_S),
                "Urgency": "low" if notification.silent else "high",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                response.read(4096)
            return OUTCOME_SENT
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                # The browser dropped the subscription. Retire it rather than
                # pushing at a dead endpoint on every future request.
                raise TransportGone(str(exc.code)) from None
            logger.warning("notify.webpush: send refused (HTTP %s)", exc.code)
            raise TransportFailed(
                OUTCOME_REFUSED if 400 <= exc.code < 500 else OUTCOME_UNAVAILABLE
            ) from None
        except TransportFailed:
            raise
        except Exception:  # noqa: BLE001 - network, DNS, TLS, crypto
            raise TransportFailed(OUTCOME_UNAVAILABLE) from None

    return send


__all__ = ["payload_bytes", "record_budget", "webpush_transport"]
