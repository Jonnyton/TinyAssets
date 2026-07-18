#!/usr/bin/env python3
"""Operator-only reset of a vault after the restore guard has been bumped.

Run only in a one-shot operator container with the data and rollback-guard
volumes mounted. Normal daemon construction does not install the recovery
authorizer, and this module is not exposed through MCP or ``VaultBroker``.
"""

from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credentials import PlatformVaultBackend  # noqa: E402

_TOKEN_ENV = "TINYASSETS_VAULT_RECOVERY_TOKEN"


class _RecoveryOnlyKeyProvider:
    """Recovery purges ciphertext without unwrapping any credential key."""

    def active_key_id(self) -> str:
        raise RuntimeError("restore recovery must not touch KEKs")

    def get_key(self, key_id: str) -> bytes:
        raise RuntimeError("restore recovery must not touch KEKs")


def main() -> int:
    token = os.environ.get(_TOKEN_ENV, "").encode("utf-8")
    if len(token) < 32:
        print(
            f"vault-restore-recover: {_TOKEN_ENV} must contain at least 32 bytes",
            file=sys.stderr,
        )
        return 2

    backend = PlatformVaultBackend(
        _RecoveryOnlyKeyProvider(),
        operator_recovery_authorizer=lambda candidate: hmac.compare_digest(
            candidate, token
        ),
    )
    backend.recover_after_restore(operator_token=token)
    print(
        "vault-restore-recover: uncertain credentials and job grants erased; "
        "fresh founder-authorized deposits are now enabled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
