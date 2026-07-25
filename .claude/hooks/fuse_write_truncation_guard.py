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

Reads stdin JSON. Tool-name keys vary by Claude version, so we check
both `tool_name`/`tool` and accept either `tool_input`/`input`.
"""

from __future__ import annotations

import json
import os
import sys

# Tolerance: allow slight differences (line endings, BOM, etc.). Anything
# more than this in absolute byte difference is treated as truncation.
TOLERANCE_BYTES = 32


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
    try:
        actual_size = os.path.getsize(file_path)
    except OSError:
        return 0
    expected_size = len(content.encode("utf-8"))
    diff = abs(actual_size - expected_size)
    if diff <= TOLERANCE_BYTES:
        return 0
    return _emit_truncation(
        file_path,
        f"sent {expected_size} bytes, on disk {actual_size} (diff {diff})",
    )


def _check_edit(tool_input):
    file_path = tool_input.get("file_path")
    new_string = tool_input.get("new_string")
    if not file_path or not isinstance(new_string, str) or not new_string:
        return 0
    if not os.path.isfile(file_path):
        return 0
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            actual = f.read()
    except OSError:
        return 0
    # If new_string is present verbatim, the edit landed correctly.
    if new_string in actual:
        return 0
    # Otherwise, find the longest prefix of new_string that IS present —
    # that's where the FUSE truncation cut off.
    cut_at = 0
    for n in range(len(new_string) - 1, 0, -1):
        if new_string[:n] in actual:
            cut_at = n
            break
    return _emit_truncation(
        file_path,
        f"new_string ({len(new_string)} chars) not found in file; only first "
        f"{cut_at} chars survive — tail of edit was chopped",
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
