#!/usr/bin/env python3
"""Operator-only reset of a vault after the restore guard has been bumped.

Run only in a one-shot operator container with the data and rollback-guard
volumes mounted. Normal daemon construction does not install the recovery
authorizer, and this module is not exposed through MCP or ``VaultBroker``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credentials import PlatformVaultBackend  # noqa: E402

# ``PlatformVaultBackend`` keeps an injected-authorizer seam so normal callers
# cannot recover a store. This script is the privileged adapter: invocation as
# root in a one-shot container with BOTH volumes mounted is the authorization
# boundary. The marker only satisfies the unchanged backend API; it is not a
# caller credential and must never be described as one.
_OPERATOR_BOUNDARY_MARKER = b"privileged-one-shot-operator-container"


class _RecoveryOnlyKeyProvider:
    """Recovery purges ciphertext without unwrapping any credential key."""

    def active_key_id(self) -> str:
        raise RuntimeError("restore recovery must not touch KEKs")

    def get_key(self, key_id: str) -> bytes:
        raise RuntimeError("restore recovery must not touch KEKs")


def main() -> int:
    backend = PlatformVaultBackend(
        _RecoveryOnlyKeyProvider(),
        operator_recovery_authorizer=lambda candidate: (
            candidate is _OPERATOR_BOUNDARY_MARKER
        ),
    )
    backend.recover_after_restore(operator_token=_OPERATOR_BOUNDARY_MARKER)
    print(
        "vault-restore-recover: uncertain credentials and job grants erased; "
        "fresh founder-authorized deposits are now enabled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
