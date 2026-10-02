"""Add or remove one named section of an rclone.conf, atomically, root 0600.

    rclone_conf_section.py add    <rclone.conf> <section-file>
    rclone_conf_section.py remove <rclone.conf> <section-name>

`add` replaces any existing section with the same name and keeps every other
section byte-for-byte, so installing `[offregion]` never disturbs `[spaces]`,
the sfo3 backup remote the nightly backup already depends on. The result is
written to a sibling temp file, fsynced, given mode 0600, and renamed over the
original, so a crash leaves either the old file or the new one.

Stdlib only: this runs on the droplet host, outside the image.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_HEADER = re.compile(r"^\[([^\]\r\n]+)\]\s*$")


def _split(text: str) -> list[tuple[str | None, list[str]]]:
    """Return [(section name or None for the preamble, lines)], in order."""
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines(keepends=True):
        match = _HEADER.match(line)
        if match:
            blocks.append((match.group(1), [line]))
        else:
            blocks[-1][1].append(line)
    return blocks


def _join(blocks: list[tuple[str | None, list[str]]]) -> str:
    out = "".join("".join(lines) for _, lines in blocks)
    return out if out.endswith("\n") or not out else out + "\n"


def add(text: str, section: str) -> str:
    new_blocks = [b for b in _split(section) if b[0] is not None]
    if len(new_blocks) != 1:
        raise ValueError("section file must contain exactly one [name] section")
    name = new_blocks[0][0]
    kept = [b for b in _split(text) if b[0] != name]
    body = _join(kept)
    if body and not body.endswith("\n\n"):
        body += "\n"
    return body + _join(new_blocks)


def remove(text: str, name: str) -> str:
    return _join([b for b in _split(text) if b[0] != name])


def _write(path: Path, text: str) -> None:
    if path.is_symlink():
        raise SystemExit(f"refusing to write through a symlink: {path}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".rclone.conf.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in {"add", "remove"}:
        print(__doc__, file=sys.stderr)
        return 2
    action, conf, arg = argv
    path = Path(conf)
    if action == "remove" and not path.exists():
        return 0
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if action == "add":
        updated = add(current, Path(arg).read_text(encoding="utf-8"))
    else:
        updated = remove(current, arg)
    _write(path, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
