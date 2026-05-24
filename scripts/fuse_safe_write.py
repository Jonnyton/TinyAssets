#!/usr/bin/env python3
"""Atomic, FUSE-truncation-resistant file writer.

Background: the Cowork sandbox mounts the Windows project folder over
FUSE. The MCP `Write`/`Edit` tools silently truncate file overwrites on
this mount — they return success while chopping the tail. Bash heredoc
is the workaround for inline content; this script is the workaround
when heredoc is awkward (binary content, CRLF preservation, very large
files, content that would clash with the heredoc delimiter).

Usage:
    python3 scripts/fuse_safe_write.py --path FILE --content-from SOURCE
    python3 scripts/fuse_safe_write.py --path FILE --content-stdin <<<TEXT

What it does:
  1. Reads content from --content-from path or stdin into memory.
  2. Writes to a temp file in the same directory (atomic rename
     constraint — temp must share filesystem with target).
  3. Verifies temp size matches source size byte-for-byte.
  4. Atomic os.replace() onto the target.
  5. Verifies on-disk size after rename.
  6. Exits non-zero loudly on any size mismatch.

Why this is safer than Write/Edit:
  - Atomic temp+rename — no partial state visible to readers mid-write.
  - Size verification at TWO checkpoints (temp + final).
  - Explicit failure rather than silent success.

Spec reference: WebSite/HOOKS_FUSE_QUIRKS.md (auto-iterate ladder rung 4,
2026-05-02, after workflow/api/status.py truncation incident).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile


def _read_content(args: argparse.Namespace) -> bytes:
    if args.content_stdin:
        return sys.stdin.buffer.read()
    if args.content_from:
        with open(args.content_from, "rb") as f:
            return f.read()
    raise SystemExit("ERROR: must provide --content-from PATH or --content-stdin")


def _atomic_write(target: str, content: bytes) -> None:
    target_dir = os.path.dirname(os.path.abspath(target)) or "."
    os.makedirs(target_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".fuse_safe_write_",
        suffix=".tmp",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

        # Verify temp size matches expected.
        actual = os.path.getsize(temp_path)
        expected = len(content)
        if actual != expected:
            raise RuntimeError(
                f"temp file size mismatch: expected {expected}, got {actual}. "
                "FUSE truncation likely. Aborting before rename."
            )

        os.replace(temp_path, target)

        # Final verify after rename.
        final = os.path.getsize(target)
        if final != expected:
            raise RuntimeError(
                f"final file size mismatch: expected {expected}, got {final}. "
                "FUSE truncation occurred during rename. File may be corrupt."
            )
    except Exception:
        # Clean up temp on any failure.
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FUSE-truncation-resistant atomic file writer.",
    )
    parser.add_argument("--path", required=True, help="Target file path")
    parser.add_argument(
        "--content-from",
        help="Read content from this file path",
    )
    parser.add_argument(
        "--content-stdin",
        action="store_true",
        help="Read content from stdin",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success message",
    )
    args = parser.parse_args()

    if args.content_from and args.content_stdin:
        print("ERROR: --content-from and --content-stdin are mutually exclusive",
              file=sys.stderr)
        return 2

    content = _read_content(args)

    try:
        _atomic_write(args.path, content)
    except Exception as exc:
        print(f"FUSE_SAFE_WRITE: FAILED — {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"FUSE_SAFE_WRITE: ok — {args.path} ({len(content)} bytes)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
