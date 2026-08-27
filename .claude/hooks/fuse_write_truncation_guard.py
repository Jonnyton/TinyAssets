#!/usr/bin/env python3
"""Detect FUSE-mount silent truncation on Write **and** Edit tool calls.

Background: in some Cowork session FUSE mounts, the Write/Edit tools report
success but silently truncate files when overwriting an existing path
(esp. larger files). The new file ends up much smaller than the content
that was sent, often chopped mid-line at the end of the buffer.

This hook catches both shapes:

* Write: compares on-disk size to the size of the content sent.
* Edit:  reads the file and verifies that the supplied `new_string` is
         present as a contiguous substring of the result. If the edit
         truncated the tail (the most common FUSE failure mode), the
         tail of `new_string` will be missing.

On detection: emit a loud stderr message and exit 2 so the agent has to
re-do the write via bash heredoc (the only path that survives the FUSE
truncation bug).

SCOPE (2026-08-07): this guard only runs where the failure mode exists — a
FUSE-backed path. It used to run everywhere, and on a native Windows checkout
that produced 458 non-blocking errors in four days with zero true positives.

That scoping is not a convenience; it is what makes the check sound. Three
rounds of cross-family review established that you cannot reliably tell "the
mount truncated the write" from "a formatter legitimately rewrote the file" by
inspecting the result afterwards: every size- or content-heuristic that forgives
a shortening formatter also forgives a real truncation, and every one strict
enough to catch the truncation fires on the formatter. There is no threshold
that separates them, because the two produce identical artifacts.

So the guard stops guessing and splits the problem by environment instead:

* Not on FUSE  -> no-op. The failure mode cannot occur, so any alarm is noise.
* On FUSE      -> STRICT equality (modulo newline representation, and a
                  file-level BOM). A mismatch of any size is reported, because
                  there a mismatch means the mount ate the write, and silent
                  data loss costs far more than an occasional formatter alarm.

Set TINYASSETS_FUSE_GUARD_FORCE=1 to run the checks regardless of mount type
(used by the test suite, and available to any session that wants the strict
behavior on a non-FUSE path).

KNOWN LIMITS — accepted, not oversights (cross-family review, 2026-08-07):

* Edit can only verify that `new_string` is present. If the truncation lands
  entirely AFTER the edited fragment, the fragment is still there and the check
  passes. The payload simply does not say what the rest of the file should be,
  so this is not recoverable from the hook's inputs. Write is the strict path.
* A loss of only newline REPRESENTATION is invisible ("abc\r\n" truncated to
  "abc\r" folds to the same "abc\n"). This is the direct cost of the newline
  folding that makes the check usable at all, and it is one byte of separator.
* On FUSE, a formatter that rewrites a file after the write WILL be reported.
  That is deliberate: on a mount known to eat writes, a false alarm is cheaper
  than silent data loss. Off FUSE, the guard is silent, so the noise never
  reaches a normal session.

BIGGEST CAVEAT: Cowork -- the only environment with this FUSE mount -- does not
execute `.claude/settings.json` hooks at all, so this guard has never once run
where its failure mode exists. It is kept as a backstop for a future harness
that both runs hooks and mounts over FUSE; Cowork itself follows the rule
manually (see docs/reference/fuse-write-discipline.md).

Reads stdin JSON. Tool-name keys vary by Claude version, so we check
both `tool_name`/`tool` and accept either `tool_input`/`input`.
"""

from __future__ import annotations

import json
import os
import sys

# There is deliberately NO byte tolerance. Two cross-family review rounds killed
# that primitive: at 32 bytes a 52-byte write losing 16 whole lines was waved
# through, and at 1 byte a genuine one-byte loss was forgiven while a formatter
# adding two newlines was reported as truncation. Every constant was wrong,
# because absolute byte delta is not what "truncated" means.
#
# What it means instead: the file on disk is SHORTER than what was sent and does
# not match it. So the test is directional and content-based —
#   1. normalized equal                      -> clean
#   2. equal ignoring trailing newlines      -> clean (the one benign difference)
#   3. disk is not shorter than what we sent -> clean; whatever changed the file
#      made it bigger, which is a formatter/rewrite, not a truncation
#   4. otherwise                             -> truncated
# No magic number survives anywhere in that ladder.

# Files larger than this are skipped rather than read into memory. FUSE tail
# truncation is a source-file failure mode; multi-hundred-MB blobs are not worth
# an unbounded read (and an uncaught MemoryError inside a hook is worse than a
# missed check). The skip is announced, never silent.
MAX_READ_BYTES = 64 * 1024 * 1024

_BOM = b"\xef\xbb\xbf"


def _is_fuse_path(file_path: str) -> bool:
    """True when `file_path` lives on a FUSE mount — the only place this bug exists.

    Windows has no FUSE mount type at all, which is the whole reason the guard
    was pure noise there. On Linux, consult the mount table and pick the longest
    matching mount point. Anything we cannot classify is treated as NOT FUSE:
    this hook fires on every Write and Edit, so an unknown filesystem defaulting
    to "alarm" is how the 458-error flood happened in the first place.
    """
    if os.environ.get("TINYASSETS_FUSE_GUARD_FORCE") == "1":
        return True
    if sys.platform == "win32":
        return False
    target = os.path.realpath(file_path)
    if sys.platform == "darwin":
        return _darwin_fstype(target).startswith(("fuse", "osxfuse", "macfuse"))
    try:
        best_len, best_is_fuse = -1, False
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount_point, fstype = _unescape_mount(parts[1]), parts[2]
                if (
                    target == mount_point
                    or target.startswith(mount_point.rstrip("/") + "/")
                ) and len(mount_point) > best_len:
                    best_len = len(mount_point)
                    best_is_fuse = fstype.startswith("fuse")
        return best_is_fuse
    except OSError:
        return False


def _unescape_mount(field: str) -> str:
    """Decode /proc/mounts octal escapes (space is `\\040`, tab `\\011`, ...).

    Without this, any mount point containing a space fails to match the target
    path and its filesystem type is never consulted.
    """
    if "\\" not in field:
        return field
    out, i = [], 0
    while i < len(field):
        if field[i] == "\\" and i + 3 < len(field) and field[i + 1 : i + 4].isdigit():
            try:
                out.append(chr(int(field[i + 1 : i + 4], 8)))
                i += 4
                continue
            except ValueError:
                pass
        out.append(field[i])
        i += 1
    return "".join(out)


def _darwin_fstype(target: str) -> str:
    """Filesystem type for `target` on macOS, via statfs(2). '' if undetermined.

    macOS has no /proc/mounts, so the Linux path above is blind there — which
    matters because macOS is a real Cowork/FUSE platform.
    """
    try:
        import ctypes

        class _Statfs(ctypes.Structure):
            _fields_ = [
                ("f_bsize", ctypes.c_uint32),
                ("f_iosize", ctypes.c_int32),
                ("f_blocks", ctypes.c_uint64),
                ("f_bfree", ctypes.c_uint64),
                ("f_bavail", ctypes.c_uint64),
                ("f_files", ctypes.c_uint64),
                ("f_ffree", ctypes.c_uint64),
                ("f_fsid", ctypes.c_uint32 * 2),
                ("f_owner", ctypes.c_uint32),
                ("f_type", ctypes.c_uint32),
                ("f_flags", ctypes.c_uint32),
                ("f_fssubtype", ctypes.c_uint32),
                ("f_fstypename", ctypes.c_char * 16),
                ("f_mntonname", ctypes.c_char * 1024),
                ("f_mntfromname", ctypes.c_char * 1024),
                ("f_reserved", ctypes.c_uint32 * 8),
            ]

        libc = ctypes.CDLL("libc.dylib", use_errno=True)
        buf = _Statfs()
        if libc.statfs(target.encode("utf-8"), ctypes.byref(buf)) != 0:
            return ""
        return buf.f_fstypename.decode("utf-8", "replace").lower()
    except Exception:
        return ""


def _fold_newlines(raw: bytes) -> bytes:
    """Fold CRLF/CR to LF in BYTES, never text.

    Both comparisons here are cross-representation: the tool payload carries
    whatever the model emitted, while the on-disk file carries whatever the
    platform/git wrote (on Windows with `core.autocrlf=true`, CRLF).

    Byte-level is load-bearing, not a style choice. Decoding with
    `errors="replace"` and re-encoding silently rewrites the length: a truncation
    landing mid-multibyte-character re-encodes 101 disk bytes as 103, and 100
    invalid bytes re-encode as 300. Never round-trip content you are measuring.
    """
    # CRLF first: reversing the order would turn each CRLF into two LFs.
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _strip_bom(raw: bytes) -> bytes:
    """Drop a leading UTF-8 BOM — only valid where `raw` is a WHOLE file.

    A BOM at offset 0 of a file is an encoding signature. The same bytes at the
    start of an Edit's `new_string` are ordinary content that may legitimately
    sit mid-file, so the Edit path must not strip them: doing so would accept a
    file that is missing a character the edit intended to insert.
    """
    return raw[len(_BOM) :] if raw.startswith(_BOM) else raw


def _read_file(file_path: str, *, strip_bom: bool) -> bytes | None:
    """Read a whole file as newline-folded bytes, optionally BOM-stripped.

    `strip_bom` must match what the caller does to the OTHER side of the
    comparison — stripping one side only is what broke the Edit path.

    Returns None when the file should not be judged; the caller announces why.
    Fails OPEN on IO errors: an unreadable file is an unrelated problem, and
    blocking every edit on a permission error is worse than a missed check.
    """
    try:
        if os.path.getsize(file_path) > MAX_READ_BYTES:
            print(
                "FUSE_WRITE_TRUNCATION_GUARD: skipped "
                f"{file_path} — larger than {MAX_READ_BYTES} bytes, so truncation "
                "was NOT checked. Verify the tail by hand.",
                file=sys.stderr,
            )
            return None
        with open(file_path, "rb") as f:
            raw = f.read()
        return _fold_newlines(_strip_bom(raw) if strip_bom else raw)
    except (OSError, MemoryError) as exc:
        print(
            f"FUSE_WRITE_TRUNCATION_GUARD: could not read {file_path} "
            f"({type(exc).__name__}) — truncation was NOT checked.",
            file=sys.stderr,
        )
        return None


def _emit_truncation(file_path: str, why: str) -> int:
    print(
        "FUSE_WRITE_TRUNCATION_GUARD: "
        f"{file_path} appears truncated ({why}).\n"
        "Rewrite via bash heredoc — Edit/Write are unreliable on this FUSE mount:\n"
        f'  cat > "{file_path}" << "FILE_EOF"\n'
        "  ...full file content...\n"
        "  FILE_EOF\n"
        "Quote the delimiter ('FILE_EOF') so shell expansion stays off.",
        file=sys.stderr,
    )
    return 2


def _check_write(tool_input):
    file_path = tool_input.get("file_path")
    content = tool_input.get("content")
    if not file_path or content is None or not isinstance(content, str):
        return 0
    if not os.path.isfile(file_path):
        return 0  # write failed entirely — different problem
    if not _is_fuse_path(file_path):
        return 0
    actual = _read_file(file_path, strip_bom=True)
    if actual is None:
        return 0
    # Both sides are whole files here, so strip the BOM from both — symmetric.
    expected = _fold_newlines(_strip_bom(content.encode("utf-8")))
    if actual == expected:
        return 0
    # On FUSE, ANY mismatch is reported. No tolerance, no directional shortcut:
    # a partial overwrite can leave a stale suffix (making the file LONGER while
    # still corrupt), and a purely-newline loss is still loss.
    if len(actual) < len(expected):
        why = (
            f"sent {len(expected)} bytes, only {len(actual)} on disk — "
            f"{len(expected) - len(actual)} bytes short"
        )
    else:
        why = (
            f"sent {len(expected)} bytes, {len(actual)} on disk — content "
            "differs (stale bytes left behind, or rewritten after the write)"
        )
    return _emit_truncation(file_path, why + "; BOM-stripped, newline-normalized")


def _check_edit(tool_input):
    file_path = tool_input.get("file_path")
    new_string = tool_input.get("new_string")
    if not file_path or not isinstance(new_string, str) or not new_string:
        return 0
    if not os.path.isfile(file_path):
        return 0
    if not _is_fuse_path(file_path):
        return 0
    # Strip the BOM from NEITHER side. `new_string` is a fragment, so a leading
    # U+FEFF in it is content the edit meant to insert. Stripping only the
    # haystack made the comparison asymmetric: a correct edit producing
    # "BOM + ABC" then failed to match a needle that legitimately carried it.
    # Leaving the BOM in place is symmetric — a needle without one still matches
    # at offset 3, and a needle with one matches only if the file really has it.
    actual = _read_file(file_path, strip_bom=False)
    if actual is None:
        return 0
    # Fold newlines on both sides: a CRLF-bearing new_string would otherwise
    # mismatch at its very first newline against an LF-folded file.
    needle = _fold_newlines(new_string.encode("utf-8"))
    if not needle:
        return 0
    # If new_string is present verbatim, the edit landed correctly.
    if needle in actual:
        return 0
    # Otherwise, find the longest prefix of new_string that IS present —
    # that's where the FUSE truncation cut off.
    cut_at = 0
    for n in range(len(needle) - 1, 0, -1):
        if needle[:n] in actual:
            cut_at = n
            break
    return _emit_truncation(
        file_path,
        f"new_string ({len(needle)} bytes) not found in file; only first "
        f"{cut_at} bytes survive — tail of edit was chopped",
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool = payload.get("tool_name") or payload.get("tool") or ""
    tool_input = payload.get("tool_input") or payload.get("input") or payload
    if not isinstance(tool_input, dict):
        return 0

    if tool == "Write":
        return _check_write(tool_input)
    if tool == "Edit":
        return _check_edit(tool_input)
    # If matcher didn't filter for us, try both — cheap.
    rc = _check_write(tool_input)
    if rc:
        return rc
    return _check_edit(tool_input)


if __name__ == "__main__":
    raise SystemExit(main())
