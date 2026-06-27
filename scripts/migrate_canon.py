"""Migration: move ALL user-uploaded canon files to sources/.

Provenance-based routing: user uploads -> sources/, daemon docs -> canon/.
Identifies user uploads by checking .reviewed markers (model != daemon-generated).

Usage:
    python scripts/migrate_canon.py [--base PATH] [--dry-run]
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyassets.ingestion.core import SourceManifest, ingest_file


def _is_user_upload(canon_dir: Path, filename: str) -> bool:
    """Check if a file is a user upload.

    User uploads: no .reviewed marker, or marker with model="user".
    Daemon docs: .reviewed marker with a model name (e.g. "claude-code").
    """
    marker = canon_dir / f".{filename}.reviewed"
    if not marker.exists():
        return True  # No marker = manually placed = user upload
    try:
        data = _json.loads(marker.read_text(encoding="utf-8"))
        model = data.get("model", "")
        return model == "user" or model == ""
    except Exception:
        return True


def migrate_universe(universe_path: Path) -> dict[str, int]:
    """Move all user-uploaded canon files to sources/.

    Returns dict with counts: scanned, migrated, skipped, errors.
    """
    canon_dir = universe_path / "canon"
    if not canon_dir.is_dir():
        return {"scanned": 0, "migrated": 0, "skipped": 0, "errors": 0}

    sources_dir = canon_dir / "sources"
    manifest = SourceManifest.load(canon_dir)

    stats = {"scanned": 0, "migrated": 0, "skipped": 0, "errors": 0}

    for f in sorted(canon_dir.iterdir()):
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue

        stats["scanned"] += 1

        # Skip daemon-generated files (they belong in canon/)
        if not _is_user_upload(canon_dir, f.name):
            stats["skipped"] += 1
            continue

        # Skip if already in sources/
        if sources_dir.is_dir() and (sources_dir / f.name).exists():
            stats["skipped"] += 1
            continue

        # Skip if already in manifest as a source
        existing = manifest.get(f.name)
        if existing and existing.routed_to == "sources":
            stats["skipped"] += 1
            continue

        data = f.read_bytes()
        try:
            result = ingest_file(
                canon_dir, f.name, data,
                universe_path=universe_path,
                user_upload=True,
            )
            print(
                f"  {f.name}: {len(data):,} bytes -> {result.routed_to}"
                f" ({result.file_type.value}, signal={result.signal_emitted})"
            )

            # Remove the original from canon/ (now in sources/)
            if result.routed_to == "sources" and f.exists():
                f.unlink()
                print("    Removed original from canon/")

            stats["migrated"] += 1
        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            stats["errors"] += 1

    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate user-uploaded canon files to sources/",
    )
    parser.add_argument(
        "--base",
        default="C:/Users/Jonathan/Documents/Fantasy Author",
        help="Base directory containing universe subdirectories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it",
    )
    args = parser.parse_args()

    base = Path(args.base)
    if not base.is_dir():
        print(f"Base directory not found: {base}")
        sys.exit(1)

    total = {"scanned": 0, "migrated": 0, "skipped": 0, "errors": 0}

    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        canon_dir = entry / "canon"
        if not canon_dir.is_dir():
            continue

        # Check for user-uploaded files still in canon/
        user_files = [
            f for f in canon_dir.iterdir()
            if f.is_file()
            and not f.name.startswith(".")
            and _is_user_upload(canon_dir, f.name)
        ]

        if not user_files:
            continue

        print(f"\n{'='*60}")
        print(f"Universe: {entry.name}")
        print(f"User uploads in canon/: {len(user_files)}")

        if args.dry_run:
            for f in user_files:
                size = f.stat().st_size
                print(f"  [DRY RUN] {f.name}: {size:,} bytes")
            total["scanned"] += len(user_files)
            continue

        stats = migrate_universe(entry)
        for k, v in stats.items():
            total[k] = total.get(k, 0) + v

    print(f"\n{'='*60}")
    print(f"TOTAL: scanned={total['scanned']}, migrated={total['migrated']}, "
          f"skipped={total['skipped']}, errors={total['errors']}")


if __name__ == "__main__":
    main()
