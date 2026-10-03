"""Mint the self-issued VAPID keypair web push needs. No third party involved.

Web push (RFC 8292) authenticates the *sender* with a keypair the sender makes
itself -- there is no console to visit, no project to create, and nothing to
ask a founder for. That is why the browser and desktop notification channel can
be proven live before Firebase exists for the Android one.

    python scripts/webpush_keys.py --subject mailto:you@example.com

Prints the two environment variables to set. The private key is a CREDENTIAL:
put it in the vault, never in a committed file or a workflow literal.

    TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY   the PEM (secret)
    TINYASSETS_WEBPUSH_VAPID_SUBJECT       mailto: or https:// contact
    TINYASSETS_WEBPUSH_VAPID_PUBLIC_KEY    the base64url point the BROWSER needs

The public key is not a secret and is not read by the server: the client passes
it to ``pushManager.subscribe({applicationServerKey})``. It is derived from the
private key, so it is printed here rather than stored twice -- two definitions
of one fact is how they drift.
"""

from __future__ import annotations

import argparse
import base64
import sys


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate(subject: str) -> dict[str, str]:
    """A fresh P-256 keypair, as ``{env var: value}``."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    if not subject.startswith(("mailto:", "https://")):
        raise ValueError(
            "subject must be a mailto: address or an https:// URL -- a push "
            "service uses it to contact whoever is sending"
        )
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return {
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": pem,
        "TINYASSETS_WEBPUSH_VAPID_SUBJECT": subject,
        "TINYASSETS_WEBPUSH_VAPID_PUBLIC_KEY": _b64(public),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--subject", required=True,
        help="mailto: address or https:// URL a push service can contact",
    )
    args = parser.parse_args(argv)
    try:
        values = generate(args.subject)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("# Rotating these invalidates every existing browser subscription:")
    print("# each one is bound to the public key it was created with, so every")
    print("# browser has to subscribe again. Rotate deliberately.")
    print()
    for name, value in values.items():
        # One line per variable, so the output pastes straight into an env file
        # (/etc/tinyassets/env); the server reads the escaped newlines back.
        escaped = value.strip().replace("\n", "\\n")
        print(f"{name}={escaped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
