"""The universe agent's hands: a stdio MCP server bound to ONE universe.

Why this exists
---------------
`converse` used to run with ``_ENGINE_ALLOWED_TOOLS = ("WebFetch",)`` and no way
to write anything. Durable state came from `extract_learning` — a *second* model
pass that re-read the transcript and filled a hardcoded schema afterwards. That
is not agency, and it is not safe: on 2026-08-07 a founder asked the live
universe to BUILD an OpenClaw-style agent and the extractor decided the sentence
described what the universe *is*, overwriting `body.md`. The agent never chose
it and was never told.

An agent that cannot write must have its intent guessed, and a guesser must pick
a slot. So the agent gets tools and decides for itself.

Why an MCP server rather than the CLI's own tools
-------------------------------------------------
`Read` cannot be confined to a directory through the CLI: headless treats
``Read``/``Glob``/``Grep`` as default-allowed, a bare deny is all-or-nothing, and
deny beats a scoped allow — so ``Read(./**)`` cannot be expressed. Granting them
re-opens the 2026-07-03 disk-wide read leak.

Here, containment is a `Path.resolve()` check in Python — the same shape as
`_scoped_wiki_root` — so it is ours to enforce and ours to test.

The one rule that makes this safe
---------------------------------
**No tool takes a universe id.** The server binds its universe at construction,
from server-side state. This is the same rule that removed
``fallback_universe_id`` from `deliver_app_event`: a tool that accepts a
universe id is a tool that can be talked into naming somebody else's.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Refuse absurd writes outright rather than filling a disk one turn at a time.
MAX_WRITE_BYTES = 512 * 1024

#: Never listed, never readable, never writable through these tools. The vault
#: lives under the universe dir, so plain containment is not enough on its own —
#: a confined agent could still read its own provider credentials and quote them
#: into a chat reply.
RESERVED_DIR_NAMES = frozenset({".credentials", ".soul.lock"})


class AgentToolError(ValueError):
    """The tool call was refused. The message reaches the model, so keep it
    actionable and free of host paths."""


@dataclass(frozen=True, slots=True)
class UniverseWorkspace:
    """A universe directory, and the only door into it.

    ``root`` is resolved once at construction. Every path the model supplies is
    resolved and then proven to sit inside that root — never string-prefixed,
    which ``/data/u-tiny-evil`` would defeat against ``/data/u-tiny``.
    """

    root: Path

    @classmethod
    def for_dir(cls, universe_dir: str | Path) -> "UniverseWorkspace":
        root = Path(universe_dir).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise AgentToolError("this universe has no workspace on disk")
        return cls(root=root)

    def resolve(self, relative: str, *, for_write: bool = False) -> Path:
        """Resolve a model-supplied path, or refuse.

        Refuses absolute paths, parent traversal, and anything that *resolves*
        outside the root — the last one is what catches a symlink planted by an
        earlier turn, because `resolve()` follows links before the check.
        """
        raw = (relative or "").strip()
        if not raw:
            raise AgentToolError("path is required")
        candidate = Path(raw)
        if candidate.is_absolute() or raw.startswith(("/", "\\")):
            raise AgentToolError("path must be relative to your own workspace")
        if candidate.drive or candidate.root:
            raise AgentToolError("path must be relative to your own workspace")

        resolved = (self.root / candidate).resolve(strict=False)
        if not _is_within(resolved, self.root):
            raise AgentToolError("path escapes your workspace")

        rel_parts = resolved.relative_to(self.root).parts
        if any(part in RESERVED_DIR_NAMES for part in rel_parts):
            raise AgentToolError("that path is reserved and not accessible")
        if for_write and resolved == self.root:
            raise AgentToolError("cannot write over the workspace itself")
        return resolved

    def relative(self, path: Path) -> str:
        """A workspace-relative display path. Host layout never leaks upward."""
        return path.relative_to(self.root).as_posix()


def _is_within(candidate: Path, root: Path) -> bool:
    """True when *candidate* is *root* or sits underneath it.

    `Path.is_relative_to` is a pure lexical check on already-resolved paths,
    which is exactly right here: both sides are resolved, so symlink escapes
    have already been collapsed into real locations by the time we compare.
    """
    try:
        return candidate == root or candidate.is_relative_to(root)
    except (ValueError, OSError):
        return False


def list_files(workspace: UniverseWorkspace, subpath: str = ".") -> list[str]:
    """Directory listing, workspace-relative, directories marked with a slash."""
    target = workspace.root if subpath.strip() in {"", "."} else workspace.resolve(subpath)
    if not target.is_dir():
        raise AgentToolError("not a directory")
    entries: list[str] = []
    for child in sorted(target.iterdir()):
        if child.name in RESERVED_DIR_NAMES:
            continue
        entries.append(workspace.relative(child) + ("/" if child.is_dir() else ""))
    return entries


def read_file(workspace: UniverseWorkspace, path: str) -> str:
    target = workspace.resolve(path)
    if not target.is_file():
        raise AgentToolError("no such file in your workspace")
    if target.stat().st_size > MAX_WRITE_BYTES:
        raise AgentToolError("file is too large to read in one call")
    return target.read_text(encoding="utf-8", errors="replace")


def write_file(workspace: UniverseWorkspace, path: str, content: str) -> str:
    """Create or replace one file. Returns the workspace-relative path written.

    Deliberately whole-file: a patch/diff tool would need the model to describe
    an edit it cannot verify. It can read, decide, and write back — which is
    also what makes the write *its* decision rather than an inference about it.
    """
    if not isinstance(content, str):
        raise AgentToolError("content must be text")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        raise AgentToolError("content is too large")
    target = workspace.resolve(path, for_write=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write via a sibling temp + replace so a crashed turn cannot leave a
    # half-written soul file behind.
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
    return workspace.relative(target)


def delete_file(workspace: UniverseWorkspace, path: str) -> str:
    target = workspace.resolve(path, for_write=True)
    if not target.is_file():
        raise AgentToolError("no such file in your workspace")
    target.unlink()
    return workspace.relative(target)


__all__ = [
    "AgentToolError",
    "MAX_WRITE_BYTES",
    "RESERVED_DIR_NAMES",
    "UniverseWorkspace",
    "delete_file",
    "list_files",
    "read_file",
    "write_file",
]
