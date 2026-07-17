"""Predeployment migration: quarantine RETIRED per-universe ``llm_subscription``
credential records (round-16 #2; packaged for deployability round-17 #2).

Founder subscription custody is a retired, blocked lane (2026-07-02 custody
research). After the S5 reshape, a universe whose vault still holds an
``llm_subscription`` record fails EVERY provider spawn
(``RetiredSubscriptionLaneError``). Re-declaring an engine only edits
``config.yaml`` — it cannot remove the vault record — so those universes are
stranded until the record is migrated out. This is the runnable, IDEMPOTENT,
crash-safe remediation the deploy pipeline runs as a pre-start step.

Round-17 #2: this lives INSIDE the ``tinyassets`` package (not ``scripts/``) so it
is importable + runnable wherever the package is installed. The documented command
is therefore::

    python -m tinyassets.migrations.retired_subscription_records --inventory
    python -m tinyassets.migrations.retired_subscription_records --migrate
    python -m tinyassets.migrations.retired_subscription_records --rollback --universe u-01k...

In the production image the ``tinyassets`` package is on ``PYTHONPATH=/app`` and
pip-installed into the venv, so ``python -m tinyassets.migrations.retired_subscription_records``
runs with no ``ModuleNotFoundError: tinyassets`` (the round-17 #2 blocker on the
old ``scripts/`` path). The deploy workflow runs ``--inventory`` then ``--migrate``
in a one-shot container from the NEW image against the mounted data volume BEFORE
restarting the daemon onto that image, and ABORTS the deploy on a non-zero exit.

Modes (exactly one):
  --inventory   List affected universes + record counts. Read-only. Run FIRST.
  --migrate     Quarantine + remove the llm_subscription records (idempotent,
                crash-safe). Archives them to ``.credential-vault-quarantine.json``
                per universe.
  --rollback    Restore the quarantined records back into each vault (reversible).

Scope: scans every universe directory under ``TINYASSETS_DATA_DIR`` (each child
dir holding a ``.credential-vault.json``). ``--data-dir`` overrides the root.
``--universe <id>`` limits to one universe. Exit code 0 on success; 2 if any
universe fails (the rest still process — failures are reported, not swallowed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tinyassets.credential_vault import (
    VAULT_FILENAME,
    load_credential_vault,
    quarantine_legacy_subscription_records,
    restore_quarantined_subscription_records,
)


def _data_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    from tinyassets.storage import data_dir

    return data_dir()


def _universe_dirs(root: Path, only: str | None) -> list[Path]:
    """Every universe dir (child of root) that has a credential vault."""
    if only:
        d = root / only
        return [d] if (d / VAULT_FILENAME).is_file() else []
    if not root.is_dir():
        return []
    return sorted(
        child
        for child in root.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and (child / VAULT_FILENAME).is_file()
    )


def _legacy_count(universe_dir: Path) -> int:
    return sum(
        1
        for r in load_credential_vault(universe_dir)
        if r.get("credential_type") == "llm_subscription"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tinyassets.migrations.retired_subscription_records",
        description=__doc__,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true",
                      help="list affected universes (read-only)")
    mode.add_argument("--migrate", action="store_true",
                      help="quarantine + remove llm_subscription records (idempotent)")
    mode.add_argument("--rollback", action="store_true",
                      help="restore quarantined records back into each vault")
    ap.add_argument("--data-dir", default=None,
                    help="override the universe root (default: TINYASSETS_DATA_DIR)")
    ap.add_argument("--universe", default=None,
                    help="limit to a single universe id")
    args = ap.parse_args(argv)

    root = _data_root(args.data_dir)
    universes = _universe_dirs(root, args.universe)
    results: list[dict] = []
    failures = 0

    for udir in universes:
        uid = udir.name
        try:
            if args.inventory:
                n = _legacy_count(udir)
                if n:
                    results.append({"universe": uid, "legacy_records": n,
                                    "status": "needs_migration"})
            elif args.migrate:
                summary = quarantine_legacy_subscription_records(udir)
                if summary["migrated"]:
                    results.append({"universe": uid, **summary})
            elif args.rollback:
                summary = restore_quarantined_subscription_records(udir)
                if summary["restored"]:
                    results.append({"universe": uid, **summary})
        except Exception as exc:  # noqa: BLE001 — report per-universe, don't swallow
            failures += 1
            results.append({"universe": uid, "error": str(exc)})

    verb = ("inventory" if args.inventory
            else "migrate" if args.migrate else "rollback")
    print(json.dumps({
        "mode": verb,
        "data_root": str(root),
        "universes_scanned": len(universes),
        "affected": [r for r in results if "error" not in r],
        "failures": [r for r in results if "error" in r],
    }, indent=2))
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
