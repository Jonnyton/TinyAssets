#!/usr/bin/env python3
"""Advance the vault's anti-rollback guard after a data-volume restore.

``deploy/backup-restore.sh`` calls this AFTER extracting a snapshot into the
data volume. It bumps the external epoch guard through the BACKEND'S OWN
epoch-guard object — the guard key is identity-derived (custody + recovery
domain), so constructing it any other way (e.g. from a raw store_id) would
silently target the wrong guard row and mask the rollback.

After the bump every vault operation raises ``REAUTHORIZATION_REQUIRED``
until founders re-authorize — that is the vault's honest post-restore
contract (a restored one-use refresh token may already be redeemed at the
provider; serving it would be dishonest).

The KEK is NOT needed: only the guard row is touched. The guard lives at
``TINYASSETS_VAULT_ROLLBACK_GUARD`` (a persistent volume OUTSIDE the data
volume — see docs/reference/environment-variables.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credentials import PlatformVaultBackend  # noqa: E402
from tinyassets.credentials.rollback import GuardMismatch  # noqa: E402


class _GuardOnlyKeyProvider:
    """The guard bump never unwraps a key; refuse loudly if anything tries."""

    def active_key_id(self) -> str:
        raise RuntimeError("restore-bump must not touch KEKs")

    def get_key(self, key_id: str) -> bytes:
        raise RuntimeError("restore-bump must not touch KEKs")


def main() -> int:
    backend = PlatformVaultBackend(_GuardOnlyKeyProvider())
    try:
        # The backend's own EpochGuard carries the identity-derived key for
        # the platform recovery domain; bump_for_restore raises GuardMismatch
        # when no guard row exists yet (nothing to roll back).
        backend._epoch.bump_for_restore()  # noqa: SLF001 - ops seam, by design
    except GuardMismatch:
        print(
            "vault-restore-bump: no existing guard row — vault was never "
            "used on this host; nothing to invalidate."
        )
        return 0
    print(
        "vault-restore-bump: guard advanced. Every vault credential now "
        "requires re-authorization (intended fail-closed post-restore state)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
