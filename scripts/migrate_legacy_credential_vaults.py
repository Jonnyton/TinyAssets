#!/usr/bin/env python3
"""One-way migration off the legacy plaintext credential vaults.

Sweeps every universe under the data root (or one universe via --universe),
quarantines ``.credential-vault.json`` + ``.credentials/`` under the platform
KEK, records metadata-only ``needs_redeposit`` bindings, and removes the
plaintext. Values are NEVER promoted — founders re-deposit through the broker.

Requires ``TINYASSETS_VAULT_KEK_DIR`` (the platform KEK directory). A blocked
universe (unreadable/ambiguous legacy state) stops the sweep loudly with the
plaintext left in place.

Usage:
    python scripts/migrate_legacy_credential_vaults.py            # sweep all
    python scripts/migrate_legacy_credential_vaults.py --universe u-abc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.credential_migration import (  # noqa: E402
    CredentialMigrationBlocked,
    migrate_all_universes,
    migrate_universe_credentials,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe", default="", help="migrate a single universe id (default: all)"
    )
    parser.add_argument(
        "--base", default="", help="data root override (default: data_dir())"
    )
    args = parser.parse_args()
    base = args.base or None
    try:
        if args.universe:
            from tinyassets.storage import data_dir

            root = Path(base) if base else data_dir()
            summaries = [
                migrate_universe_credentials(root / args.universe, base=base)
            ]
        else:
            summaries = migrate_all_universes(base)
    except CredentialMigrationBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    for summary in summaries:
        print(json.dumps(summary, sort_keys=True))
    migrated = sum(1 for s in summaries if s.get("status") == "migrated")
    print(f"done: {len(summaries)} universes checked, {migrated} migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
