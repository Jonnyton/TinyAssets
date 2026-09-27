"""One-shot migration: make every defaulted-public universe private.

Founder, 2026-09-26: "nodes in users universes should be private unless they
make them other user accessible or visible or interactable in some way." The
creation default and the boot backfill now declare ``private``
(``tinyassets/api/visibility.py``), but every universe declared BEFORE that
change holds a level the platform supplied rather than one its owner chose.
This flips those to ``private``.

**Why every current non-private declaration counts as defaulted.** Nothing in
the store recorded WHO decided a level until this change added
``visibility_level_source``. The inference is not a guess:

  * ``DEFAULT_CREATE_VISIBILITY`` was ``"public"``, and the public
    ``write_graph target=universe`` create never forwarded a visibility, so
    every universe born through the connector took that default.
  * ``backfill_universe_visibility`` derived the level from the legacy
    ``public_read`` bit, whose own column default is ``1``, so every legacy
    directory and every maintenance bucket was declared ``public`` at boot.
  * No production caller ever set a level on an owner's behalf — before the new
    ``set_visibility`` action, ``set_universe_visibility`` had no caller outside
    creation and the backfill.

So no ``public`` row in the store can have come from an owner's decision, and
this script flips all of them. Rows written from now on carry a provenance, so
a level an owner chose (``source="owner"``) is skipped — which is what makes a
re-run safe after someone publishes.

**It deletes nothing.** The only write is an update to a universe's rules
metadata (plus the legacy ``public_read`` ceiling kept consistent by
``set_universe_visibility``). The ``_backup_subject_migration_*`` and
``_removed_universes_*`` records are migration backups and stay exactly where
they are — only their visibility changes.

Run::

    python scripts/migrate_private_by_default.py               # dry run, lists
    python scripts/migrate_private_by_default.py --apply       # writes
    python scripts/migrate_private_by_default.py --json        # machine record
    python scripts/migrate_private_by_default.py --apply --skip paper-notes

Idempotent: a second run reports zero candidates.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("migrate_private_by_default")

#: Levels that expose anything at all to a reader holding no grant. A universe
#: already at ``private`` is not a candidate no matter who declared it.
_EXPOSED_LEVELS = ("public", "metadata_only", "unlisted")


def _declared_universe_ids(base_path: Any) -> list[str]:
    """Every universe id with a rules row, plus every discoverable one.

    Reads ``universe_rules`` directly rather than going through the visibility
    module's ``_discover_universe_ids``: that helper enumerates *discoverable
    directories* (and is being narrowed to OWNED ones), while the records that
    most need flipping are precisely the unowned maintenance buckets. The union
    with discovery still catches a universe that has a directory and no rules
    row.
    """
    from tinyassets.api import visibility as vis
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.storage import _connect

    # Idempotent, and required here rather than only in `main()`: `plan()` and
    # `run()` are called directly (by tests, and by anything importing this), and
    # a data dir whose universes are bare on-disk directories has no schema yet —
    # the raw `SELECT` then dies with "no such table: universe_rules". Every
    # daemon_server accessor does this for the same reason.
    initialize_author_server(base_path)

    ids: list[str] = []
    seen: set[str] = set()
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT universe_id FROM universe_rules ORDER BY universe_id",
        ).fetchall()
    for row in rows:
        uid = str(row["universe_id"] or "").strip()
        if uid and uid not in seen:
            seen.add(uid)
            ids.append(uid)
    try:
        discovered = vis._discover_universe_ids()
    except Exception:  # noqa: BLE001 - discovery is the secondary source here
        logger.warning("on-disk discovery failed; using rules rows only", exc_info=True)
        discovered = []
    for uid in discovered:
        uid = (uid or "").strip()
        if uid and uid not in seen:
            seen.add(uid)
            ids.append(uid)
    return ids


def _legacy_bit_is_open(base_path: Any, universe_id: str) -> bool:
    """Whether the legacy ``public_read`` bit still permits a read.

    Read separately from the declared level because it is a SECOND read gate, not
    a projection of the first: ``permissions.universe_access_allows`` consults it
    alone, and readers that predate the visibility layer (e.g.
    ``get_memory_scope_status``) go through that. Its column default is ``1``, so
    an undeclared universe is open on that path even though the layered resolver
    reports it ``private``. Missing row -> open, matching the permissive path.
    """
    from tinyassets.daemon_server import get_universe_rules

    try:
        return bool(get_universe_rules(base_path, universe_id=universe_id).get(
            "public_read", True
        ))
    except KeyError:
        return True  # no rules row at all -> the permissive path lets reads in.
    except Exception:  # noqa: BLE001 - unreadable row: treat as needing the fix.
        logger.warning(
            "could not read public_read for %s; treating as open", universe_id,
            exc_info=True,
        )
        return True


def plan(base_path: Any, *, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Classify every universe without writing anything.

    Returns ``{"candidates": [...], "kept": [...], "already_private": [...],
    "skipped": [...]}`` where each row is
    ``{"universe_id", "level", "source", "reason"}``.

    A universe is a candidate when ANY of these holds:

      * it carries no explicit declaration. The layered resolver reports an
        undeclared universe as ``private``, and an earlier cut of this script read
        that as "already closed" and skipped it. **It is not closed**: the legacy
        ``public_read`` bit is a separate gate, its default is ``1``, and readers
        that predate the visibility layer consult it alone — so an undeclared
        universe stayed readable and the migration reported zero candidates
        (Codex cross-family review of PR #4019, reproduced). Declaring it
        ``private`` closes both.
      * its declared level exposes something and no owner chose it.
      * it is declared ``private`` yet the legacy bit is still open — an
        inconsistent row, which the layered resolver hides and the legacy path
        honours. Re-declaring is idempotent and closes the bit.
    """
    from tinyassets.api import visibility as vis

    result: dict[str, list[dict[str, str]]] = {
        "candidates": [],
        "kept": [],
        "already_private": [],
        "skipped": [],
    }
    for uid in _declared_universe_ids(base_path):
        level = vis.declared_level_name(uid)
        declared = vis.is_declared(uid)
        source = vis.declared_level_source(uid) or "(unrecorded)"
        legacy_open = _legacy_bit_is_open(base_path, uid)
        row = {
            "universe_id": uid,
            "level": level if declared else "(undeclared)",
            "source": source,
            "legacy_public_read": "open" if legacy_open else "closed",
            "reason": "",
        }
        if uid in skip:
            result["skipped"].append(row)
            continue
        if not declared:
            row["reason"] = "undeclared; the legacy read bit still decides"
            result["candidates"].append(row)
        elif level in _EXPOSED_LEVELS and not vis.level_was_chosen_by_owner(uid):
            row["reason"] = "exposed by a platform default, not by its owner"
            result["candidates"].append(row)
        elif level in _EXPOSED_LEVELS:
            result["kept"].append(row)
        elif legacy_open:
            row["reason"] = "declared private but the legacy read bit is open"
            result["candidates"].append(row)
        else:
            result["already_private"].append(row)
    return dict(result)


def run(
    base_path: Any,
    *,
    apply: bool = False,
    skip: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Plan, then (with ``apply``) flip every candidate to ``private``."""
    from tinyassets.api import visibility as vis
    from tinyassets.daemon_server import register_universe_if_absent

    summary = plan(base_path, skip=skip)
    summary["applied"] = bool(apply)
    flipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    if apply:
        for row in summary["candidates"]:
            uid = row["universe_id"]
            try:
                # Register BEFORE declaring, and ONLY IF ABSENT. `universe_rules`
                # has an FK onto `universes`, so a bare on-disk directory with no
                # DB rows — the record that most needs closing, since the legacy
                # bit's default serves it — made the write die with
                # `FOREIGN KEY constraint failed` and stay readable (Codex review
                # round 2; a second `--apply` repeated the failure).
                #
                # Registering UNCONDITIONALLY then destroyed data, because
                # `ensure_universe_registered` is an UPSERT that resets
                # `display_name` to the raw id and `metadata_json` to `{}` when
                # those are not passed (Codex review round 3).
                # `register_universe_if_absent` is the single guarded form every
                # FK-only caller uses, and it lives in `daemon_server` beside the
                # UPSERT it guards — a migration that closes a read hole must not
                # silently rename someone's universe to do it.
                register_universe_if_absent(base_path, universe_id=uid)
                vis.set_universe_visibility(uid, "private", source="migration")
            except Exception as exc:  # noqa: BLE001 - one bad row must not stop the rest
                logger.error("could not flip %s: %s", uid, exc, exc_info=True)
                failed.append({**row, "error": str(exc)})
                continue
            now = vis.declared_level_name(uid)
            if now != "private" or not vis.is_declared(uid):
                # Fail loudly rather than reporting a write that did not take.
                logger.error("flip of %s did not take: level is now %r", uid, now)
                failed.append({**row, "error": f"level is still {now!r} after write"})
                continue
            if _legacy_bit_is_open(base_path, uid):
                # Both gates or neither: a closed level over an open legacy bit is
                # the exact inconsistency this migration exists to remove.
                logger.error("flip of %s left public_read open", uid)
                failed.append({**row, "error": "public_read still open after write"})
                continue
            logger.info("%s: %s (%s) -> private", uid, row["level"], row["source"])
            flipped.append(row)
    summary["flipped"] = flipped
    summary["failed"] = failed
    return summary


def _print_human(summary: dict[str, Any]) -> None:
    def _rows(key: str, heading: str) -> None:
        rows = summary.get(key) or []
        print(f"\n{heading} ({len(rows)}):")
        if not rows:
            print("  (none)")
            return
        for row in rows:
            extra = f"  ERROR: {row['error']}" if row.get("error") else ""
            if row.get("reason"):
                extra = f"  ({row['reason']}){extra}"
            print(
                f"  {row['universe_id']:<48} level={row['level']:<14}"
                f" source={row['source']:<14}"
                f" public_read={row.get('legacy_public_read', '?')}{extra}"
            )

    _rows("candidates", "WOULD FLIP to private" if not summary["applied"] else "FLIP candidates")
    if summary["applied"]:
        _rows("flipped", "FLIPPED to private")
        _rows("failed", "FAILED")
    _rows("kept", "KEPT — the owner chose this level")
    _rows("already_private", "already private or undeclared")
    _rows("skipped", "skipped by --skip")
    if not summary["applied"]:
        print(
            "\nDry run — nothing was written. Re-run with --apply to flip the "
            f"{len(summary['candidates'])} candidate(s) above."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the flips; without it the script only lists what it would do",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the summary as JSON instead of a table",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="UNIVERSE_ID",
        help=(
            "leave this universe alone — for a record the host has decided "
            "should stay exposed. Repeatable."
        ),
    )
    parser.add_argument(
        "--base-path",
        default="",
        help="data dir override; defaults to tinyassets.storage.data_dir()",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # `set_universe_visibility` writes through `tinyassets.api.helpers._base_path`,
    # which resolves `TINYASSETS_DATA_DIR` on every call. An override that only
    # changed the path this script ENUMERATES would read one data dir and write
    # to another, so it sets the canonical env var and then resolves through the
    # same resolver everything else uses — never a second precedence rule.
    if args.base_path:
        os.environ["TINYASSETS_DATA_DIR"] = args.base_path

    from tinyassets.api.helpers import _base_path

    base_path = _base_path()

    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(base_path)

    summary = run(base_path, apply=args.apply, skip=frozenset(args.skip))
    summary["base_path"] = str(base_path)
    if args.as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"data dir: {base_path}")
        _print_human(summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
