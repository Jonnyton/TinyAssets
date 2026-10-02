"""A whole command center as one public package: manifest, scrub, store, quarantine.

Founder, 2026-10-02: "the publish and use as the second user will be on the
sharing a whole command center as a package". The ``publish`` ask already makes
workflows, one UI and automation triggers public as one definition. This module
adds what travels beside them -- the command center's FILES (harness,
workspace, wiki pages) -- and the install side (change
``command-center-packages``).

* **One manifest.** ``command-center.json`` (``build_manifest``) is the document
  the D11 export writes too; ``profile`` says which cut it is. Only ``publish``
  is built here.
* **The scrub** (``classify``) decides per file whether it may be public. The
  never-list and the detections win over the owner: a dot entry, a runtime
  file, an owner-describing brain file, a binary, or a detected credential or
  contact detail (in the content OR the path) stays out whatever the owner
  names. ``final_check`` then scans the whole public output once more.
* **The store.** A package's content is ONE canonical JSON blob, written once
  under ``<data root>/.command-center-packages/blobs/<sha256>.json`` -- outside
  every command-center folder, so no agent environment reaches it (harness
  §4.16). Ownership is recorded BEFORE the write, so the ``packages`` store
  charges even a blob a failed publish left unlisted.
* **The ingestion boundary** (``check_blob``) runs on every read of a blob,
  before anything is planned from it.
* **Pins.** The consent record of a ``publish`` or ``install`` ask -- its
  action, digest, tab text and (for install) destination plan -- lives here,
  keyed by (command center, request). The rail renders those asks from the pin
  and the answer executes the pin, never the pending-request row, which sits
  inside the agent-writable folder.
* **The writer** (``write_new_file``) creates each file ``O_EXCL |
  O_NOFOLLOW`` beneath directories opened one component at a time, so an
  install never overwrites the installer's own file and never follows a link
  the installer's agent planted.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterator

from tinyassets import workspace_fs as fs
from tinyassets.universe_files import (
    MAX_UNIVERSE_FILE_BYTES,
    list_universe_dir,
    read_universe_file,
)

FORMAT_VERSION = 1
PROFILE_PUBLISH = "publish"
PACKAGE_TAG = "tinyassets.command-center-package.v1"
PACKAGE_KIND = "tinyassets.package.v1"

#: The data-root directory every package record lives in (§4.16: outside every
#: command-center folder; no jail binds the data root).
ROOT_DIR = ".command-center-packages"
_BLOBS = "blobs"
_DB = "packages.db"

# -- the ingestion boundary's bounds -------------------------------------------
MAX_FILES = 5000
MAX_DEPTH = 24
MAX_PATH_CHARS = 400
MAX_FILE_BYTES = MAX_UNIVERSE_FILE_BYTES
#: A ceiling no package passes whatever the quota: import is never unlimited
#: (§4.17). Below it, the publisher's storage quota is the limit.
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
#: Entries the publish walk visits before refusing.
MAX_WALK_ENTRIES = 20000

# -- the scrub -------------------------------------------------------------------
#: Harness files at the command-center root: they travel, and an install lands
#: them under ``agents/<slug>/`` (§4.14 roster layout).
HARNESS_ROOT_FILES = frozenset({"AGENTS.md", "identity.md", "MEMORY.md", "settings.yaml"})
HARNESS_ROOT_DIRS = frozenset({"skills", "extensions", "prompts"})
MEMORY_FILE = "MEMORY.md"

_BRAIN_FILES = frozenset({"founder.md", "soul.md", "soul.edit.md", "log.md"})
#: Platform-written runtime state at the folder root.
_RUNTIME_FILES = frozenset({
    "activity.log", "status.json", "ledger.json", "work_targets.json", "notes.json",
    "timeline.json", "promises.json", "facts.json", "characters.json",
    "dispatcher_config.yaml", "config.yaml",
})
NEVER_DIRS = frozenset({"workspaces", "soul_versions"})
#: Under ``wiki/`` only the curated ``pages/`` travel (okf_export's set).
WIKI_DIR = "wiki"
WIKI_PAGES = "pages"
_DB_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_PHONE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
    r"|\(\d{3}\)\s?\d{3}[-.\s]\d{4}|\d{3}[-.]\d{3}[-.]\d{4})(?!\w)"
)
_MEMORY_ID = re.compile(r"m_[A-Za-z0-9]{1,32}")
_MEMORY_ITEM = re.compile(r"^\s*[-*]\s*\[(m_[A-Za-z0-9]{1,32})\]")
_CONNECTION_NAME = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,126}$")
_CONNECTION_KEYS = frozenset({"destination", "connection", "connection_name"})
_SLUG = re.compile(r"[^a-z0-9]+")
_AGENT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
#: Hash-valued fields: hex digests are key-shaped by design, so the final
#: credential scan skips exactly these keys (their values are platform-computed).
_DIGEST_KEYS = frozenset({"sha256", "blob_sha256", "published_version_id"})

#: Excluded-file reasons, as the tab words them.
R_DOT = "platform or private state"
R_RUNTIME = "platform runtime file"
R_BRAIN = "describes you or holds your command center's control settings"
R_WIKI = "wiki drafts and raw material stay private"
R_MEMORY = "memory is private unless you name items"
R_CREDENTIAL = "a credential was detected"
R_CONTACT = "contact details were detected"
R_PATH = "its name carries a credential or contact details"
R_BINARY = "not text, so it cannot be checked"
R_DATABASE = "a database file"
R_EXCLUDED = "you left it out"
R_TOO_BIG = "over the per-file size bound"
R_UNREADABLE = "a link or not a regular file"
R_CHECKOUT = "a managed repository checkout"
R_DEEP = "deeper than a package may go"


class PackageError(ValueError):
    """A package was refused. The message is the owner-facing reason."""


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def check_path(raw: Any) -> str:
    """``raw`` as a package-relative POSIX path, or raise `PackageError`.

    Refused: non-text, empty, absolute, a drive, a backslash, a control
    character, an empty / ``.`` / ``..`` component, any dot-prefixed component,
    over ``MAX_PATH_CHARS``, deeper than ``MAX_DEPTH``.
    """
    if not isinstance(raw, str) or not raw:
        raise PackageError("a package path must be non-empty text")
    if len(raw) > MAX_PATH_CHARS:
        raise PackageError(f"a package path is over {MAX_PATH_CHARS} characters")
    if "\\" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise PackageError(f"{raw!r} is not a relative package path")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise PackageError("a package path holds a control character")
    parts = raw.split("/")
    if len(parts) > MAX_DEPTH:
        raise PackageError(f"{raw!r} is deeper than {MAX_DEPTH} folders")
    for part in parts:
        if part in ("", ".", ".."):
            raise PackageError(f"{raw!r} has an empty or traversal component")
        if part.startswith("."):
            raise PackageError(f"{raw!r} has a hidden component")
    return raw


def collision_key(path: str) -> str:
    """Two paths with one key would be one file on a case-insensitive or
    Unicode-normalising filesystem."""
    return unicodedata.normalize("NFC", path).casefold()


def check_tree(paths: list[str]) -> None:
    """Refuse a set of paths that cannot coexist as one tree: two that collide,
    or a file where another path needs a folder."""
    keys: dict[str, str] = {}
    for path in paths:
        key = collision_key(path)
        if key in keys:
            raise PackageError(f"{path!r} collides with {keys[key]!r}")
        keys[key] = path
    folders = {collision_key("/".join(p.split("/")[:i]))
               for p in paths for i in range(1, p.count("/") + 1)}
    for key, path in keys.items():
        if key in folders:
            raise PackageError(f"{path!r} is a file where another path needs a folder")


# --------------------------------------------------------------------------- #
# The scrub
# --------------------------------------------------------------------------- #


def structural_exclusion(rel: str) -> str | None:
    """The reason ``rel`` can never be public, from its path alone, or None."""
    parts = rel.split("/")
    reason = dir_exclusion("/".join(parts[:-1])) if len(parts) > 1 else None
    if reason:
        return reason
    if parts[-1].startswith("."):
        return R_DOT
    if len(parts) == 1 and parts[0] in _BRAIN_FILES:
        return R_BRAIN
    if len(parts) == 1 and parts[0] in _RUNTIME_FILES:
        return R_RUNTIME
    if parts[0] == WIKI_DIR and (len(parts) < 3 or parts[1] != WIKI_PAGES):
        return R_WIKI
    if parts[-1].lower().endswith(_DB_SUFFIXES):
        return R_DATABASE
    return None


def dir_exclusion(rel_dir: str) -> str | None:
    """The reason no file under the folder ``rel_dir`` can be public, or None.
    The walk does not descend into such a folder at all."""
    parts = rel_dir.split("/")
    if any(part.startswith(".") for part in parts):
        return R_DOT
    if parts[0] in NEVER_DIRS:
        return R_CHECKOUT if parts[0] == "workspaces" else R_BRAIN
    if parts[0] == WIKI_DIR and len(parts) >= 2 and parts[1] != WIKI_PAGES:
        return R_WIKI
    return None


def text_detection(text: str) -> str | None:
    """``R_CREDENTIAL`` / ``R_CONTACT`` for text that may not be public, else None.

    The credential test is the platform's own parser (``credential_shape``),
    line by line; contact details are an email address or a phone number.
    """
    from tinyassets.credential_shape import credential_shape

    for line in text.splitlines() or [text]:
        if credential_shape(line):
            return R_CREDENTIAL
    if _EMAIL.search(text) or _PHONE.search(text):
        return R_CONTACT
    return None


def as_text(data: bytes) -> str | None:
    """The file as text, or None when it is not inspectable UTF-8 text."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return None if "\x00" in text else text


def _excluded_by_owner(rel: str, exclude: list[str]) -> bool:
    return any(rel == item or rel.startswith(item + "/") for item in exclude)


def is_memory_file(rel: str) -> bool:
    parts = rel.split("/")
    return rel == MEMORY_FILE or (len(parts) == 3 and parts[0] == "agents"
                                  and parts[2] == MEMORY_FILE)


def classify(rel: str, data: bytes, *, exclude: list[str],
             memory_items: dict[str, list[str]]) -> tuple[bytes | None, str]:
    """``(bytes to publish, "")`` or ``(None, reason)`` for one file.

    Order is the floor: the path never-list, the path's own text, the owner's
    exclusions and memory choice, then the content: a binary, a credential,
    contact details. Nothing the owner names lifts a never-list or a detection.
    """
    reason = structural_exclusion(rel)
    if reason:
        return None, reason
    if text_detection(rel.replace("/", " ")):
        return None, R_PATH
    if len(data) > MAX_FILE_BYTES:
        return None, R_TOO_BIG
    if _excluded_by_owner(rel, exclude):
        return None, R_EXCLUDED
    if is_memory_file(rel):
        if not memory_items.get(rel):
            return None, R_MEMORY
        data = select_memory(data, memory_items[rel], rel)
    text = as_text(data)
    if text is None:
        return None, R_BINARY
    reason = text_detection(text)
    if reason:
        return None, reason
    return data, ""


def select_memory(data: bytes, wanted: list[str], rel: str = MEMORY_FILE) -> bytes:
    """Only the memory bullets whose ids the owner named (§4.13 ids)."""
    keep = set(wanted)
    chosen = []
    for line in data.decode("utf-8", "replace").splitlines():
        match = _MEMORY_ITEM.match(line)
        if match and match.group(1) in keep:
            chosen.append(line)
            keep.discard(match.group(1))
    if keep:
        raise PackageError(f"{rel} has no item {', '.join(sorted(keep))}")
    return ("# Memory\n\n" + "\n".join(chosen) + "\n").encode("utf-8")


def scan_public(value: Any, where: str = "") -> None:
    """The final-output check: every string in ``value`` (keys included) must
    pass the credential parser and the contact detector. Hex digest fields the
    platform computed are skipped by key. Raises `PackageError` naming where."""
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{where}.{key}" if where else str(key)
            if text_detection(str(key)):
                raise PackageError(f"{where or 'the package'} has a field name that "
                                   "carries a credential or contact details")
            if str(key) in _DIGEST_KEYS:
                continue
            scan_public(child, here)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_public(child, f"{where}[{index}]")
    elif isinstance(value, str):
        reason = text_detection(value)
        if reason:
            raise PackageError(f"{where or 'the package'}: {reason}; nothing was "
                               "published. Remove it and ask again")


# --------------------------------------------------------------------------- #
# The publish walk
# --------------------------------------------------------------------------- #


def _entry_kind(universe_dir: Path, rel: str) -> str:
    try:
        info = os.lstat(Path(universe_dir) / rel)
    except OSError:
        return "other"
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0):
        return "other"
    if stat.S_ISDIR(info.st_mode):
        return "dir"
    return "file" if stat.S_ISREG(info.st_mode) else "other"


def walk(universe_dir: Path) -> Iterator[tuple[str, str]]:
    """Every entry under the folder as ``(rel, kind)``, never following a link.

    Listing goes through the no-follow lister. A never-list folder is reported
    once (``skipped-dir``) and not descended into, so its contents are never
    read.
    """
    pending = [""]
    seen = 0
    while pending:
        rel_dir = pending.pop()
        try:
            names = list_universe_dir(universe_dir, rel_dir)
        except OSError:
            continue
        for name in names:
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                raise PackageError(
                    f"this command center has over {MAX_WALK_ENTRIES} files and folders; "
                    "leave the large folders out and ask again")
            rel = f"{rel_dir}/{name}" if rel_dir else name
            kind = _entry_kind(universe_dir, rel)
            if kind == "dir":
                if dir_exclusion(rel) or rel.count("/") + 1 >= MAX_DEPTH:
                    yield rel + "/", "skipped-dir"
                    continue
                pending.append(rel)
            else:
                yield rel, kind


def collect(universe_dir: Path, *, exclude: list[str],
            memory_items: dict[str, list[str]]
            ) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    """The files a ``publish`` package carries, and every entry left out with why."""
    files: dict[str, bytes] = {}
    excluded: list[dict[str, str]] = []
    for rel, kind in sorted(walk(universe_dir)):
        if kind == "skipped-dir":
            reason = dir_exclusion(rel.rstrip("/")) or R_DEEP
            if reason != R_DOT:
                # Dot folders are platform state the owner never sees; listing
                # each would only bury what they need to read.
                excluded.append({"path": rel, "reason": reason})
            continue
        if kind != "file":
            excluded.append({"path": rel, "reason": R_UNREADABLE})
            continue
        reason = structural_exclusion(rel)
        if reason:
            if reason != R_DOT:
                excluded.append({"path": rel, "reason": reason})
            continue
        try:
            check_path(rel)
            data = read_universe_file(universe_dir, rel, max_bytes=MAX_FILE_BYTES)
        except PackageError:
            excluded.append({"path": rel, "reason": R_UNREADABLE})
            continue
        except OSError as exc:
            reason = R_TOO_BIG if "bound" in str(exc) else R_UNREADABLE
            excluded.append({"path": rel, "reason": reason})
            continue
        kept, reason = classify(rel, data, exclude=exclude, memory_items=memory_items)
        if kept is None:
            excluded.append({"path": rel, "reason": reason})
            continue
        files[rel] = kept
    missing = sorted(set(memory_items) - set(files))
    if missing:
        raise PackageError(f"you named memory items in {', '.join(missing)}, but that "
                           "file could not be included")
    try:
        check_tree(list(files))
    except PackageError as exc:
        raise PackageError(f"two files in this command center would be one file in a "
                           f"copy: {exc}") from None
    return files, excluded


def connection_names(rows: Any) -> list[str]:
    """Connection names a published workflow refers to: named references only."""
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if (str(key).lower() in _CONNECTION_KEYS and isinstance(child, str)
                        and _CONNECTION_NAME.match(child.strip().lower())):
                    found.add(child.strip().lower())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(rows)
    return sorted(found)


def model_need(files: dict[str, bytes]) -> str:
    raw = files.get("settings.yaml")
    if not raw:
        return ""
    from tinyassets.universe_files import load_untrusted_yaml

    try:
        doc = load_untrusted_yaml(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return ""
    model = doc.get("model") if isinstance(doc, dict) else None
    return model.strip()[:120] if isinstance(model, str) else ""


def agents_in(files: dict[str, bytes]) -> list[str]:
    names = {p.split("/")[1] for p in files if p.startswith("agents/") and p.count("/") >= 2}
    root = any(p in HARNESS_ROOT_FILES or p.split("/")[0] in HARNESS_ROOT_DIRS for p in files)
    return (["main"] if root else []) + sorted(names)


def build_manifest(*, profile: str, name: str, description: str, files: dict[str, bytes],
                   workflows: list[dict[str, Any]], ui: str, automations: list[dict[str, Any]],
                   connections: list[str]) -> dict[str, Any]:
    """``command-center.json``: one manifest for every profile (§4.17, D1)."""
    return {
        "format_version": FORMAT_VERSION,
        "profile": profile,
        "name": name,
        "description": description,
        "agents": agents_in(files),
        "files": [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                  for p, b in sorted(files.items())],
        "workflows": workflows,
        "ui": ui,
        "automations": automations,
        "needs": {"model": model_need(files), "connections": connections},
    }


def build_blob(manifest: dict[str, Any], files: dict[str, bytes]) -> bytes:
    """The canonical package content. Its sha256 is the package's identity."""
    doc = {"format_version": FORMAT_VERSION, "manifest": manifest,
           "files": {p: base64.b64encode(b).decode("ascii") for p, b in sorted(files.items())}}
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def build_publish_package(universe_dir: Path, *, name: str, description: str,
                          options: dict[str, Any], branch_rows: Any,
                          workflows: list[dict[str, Any]], ui: str,
                          automations: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the ``publish`` ask pins for a package. Reads the folder only."""
    files, excluded = collect(universe_dir, exclude=options["exclude"],
                              memory_items=options["memory_items"])
    if not files:
        raise PackageError("nothing in this command center can be published as files")
    if len(files) > MAX_FILES:
        raise PackageError(f"a package holds at most {MAX_FILES} files; this one has "
                           f"{len(files)}. Leave some folders out and ask again")
    manifest = build_manifest(
        profile=PROFILE_PUBLISH, name=name, description=description, files=files,
        workflows=workflows, ui=ui, automations=automations,
        connections=connection_names(branch_rows))
    blob = build_blob(manifest, files)
    if len(blob) > MAX_PACKAGE_BYTES:
        raise PackageError(f"this package is {human(len(blob))}, over the "
                           f"{human(MAX_PACKAGE_BYTES)} a package may be")
    return {"blob": blob, "sha256": hashlib.sha256(blob).hexdigest(), "manifest": manifest,
            "excluded": excluded}


def human(size: int | float) -> str:
    value = float(size)
    for unit in ("bytes", "KiB", "MiB"):
        if value < 1024:
            return f"{int(value)} bytes" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def validate_options(raw: Any) -> dict[str, Any]:
    """The ``package`` block of a ``publish`` action, shape only."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("package must be an object")
    unknown = set(raw) - {"exclude", "memory_items", "agent"}
    if unknown:
        raise ValueError(f"package has unknown fields: {', '.join(sorted(unknown))}")
    value = raw.get("exclude") or []
    if not isinstance(value, list) or len(value) > 500:
        raise ValueError("package.exclude must be a list of at most 500 paths")
    exclude: list[str] = []
    for item in value:
        try:
            path = check_path(item.rstrip("/") if isinstance(item, str) else item)
        except PackageError as exc:
            raise ValueError(f"package.exclude: {exc}") from None
        if path not in exclude:
            exclude.append(path)
    items = raw.get("memory_items") or []
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("package.memory_items must be a list of memory item ids")
    memory: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, str):
            raise ValueError("package.memory_items must be a list of memory item ids")
        path, _, ident = item.rpartition("#")
        path = path or MEMORY_FILE
        if not _MEMORY_ID.fullmatch(ident) or not is_memory_file(path):
            raise ValueError(f"package.memory_items: {item!r} is not an item id like m_7f3a "
                             "or agents/<id>/MEMORY.md#m_7f3a")
        memory.setdefault(path, [])
        if ident not in memory[path]:
            memory[path].append(ident)
    return {"exclude": sorted(exclude),
            "memory_items": {p: sorted(ids) for p, ids in sorted(memory.items())},
            "agent": agent_id(raw.get("agent"))}


def agent_id(raw: Any) -> str:
    """The acting agent (multi-agent invariant, §4.18). ``main`` is a default,
    not a special case."""
    from tinyassets.agent_rules import MAIN_AGENT

    text = MAIN_AGENT if raw in (None, "") else raw
    if not isinstance(text, str) or not _AGENT_ID.fullmatch(text):
        raise ValueError("agent must be an agent id")
    return text


# --------------------------------------------------------------------------- #
# Store: blobs, versions, pins
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
    author_id   TEXT NOT NULL,
    blob_sha256 TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at  REAL NOT NULL,
    PRIMARY KEY (author_id, blob_sha256)
);
CREATE TABLE IF NOT EXISTS package_versions (
    author_id     TEXT NOT NULL,
    name          TEXT NOT NULL,
    version       INTEGER NOT NULL CHECK (version >= 1),
    blob_sha256   TEXT NOT NULL,
    definition_id TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    PRIMARY KEY (author_id, name, version)
);
-- The consent record of a publish or install ask, bound to the request that
-- displayed it. Answers execute THIS, never the pending-request row.
CREATE TABLE IF NOT EXISTS pins (
    universe_id  TEXT NOT NULL,
    pin_id       TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('publish', 'install')),
    agent_id     TEXT NOT NULL,
    digest       TEXT NOT NULL,
    request_id   TEXT NOT NULL DEFAULT '',
    record_json  TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'pinned'
                 CHECK (state IN ('pinned', 'activating', 'activated')),
    progress_json TEXT NOT NULL DEFAULT '{}',
    claimed_at   REAL,
    created_at   REAL NOT NULL,
    activated_at REAL,
    PRIMARY KEY (universe_id, pin_id)
);
CREATE INDEX IF NOT EXISTS idx_pins_request ON pins(universe_id, request_id);
"""


def store_dir(base_path: str | Path) -> Path:
    return Path(base_path) / ROOT_DIR


@contextlib.contextmanager
def _db(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    root = store_dir(base_path)
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / _DB, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.executescript(_SCHEMA)
        yield conn
    finally:
        conn.close()


def next_version(base_path: str | Path, author_id: str, name: str) -> int:
    with _db(base_path) as conn:
        row = conn.execute(
            "SELECT MAX(version) AS v FROM package_versions WHERE author_id = ? AND name = ?",
            (author_id, name)).fetchone()
    return int(row["v"] or 0) + 1


def _blob_path(base_path: str | Path, sha256: str) -> Path:
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise PackageError("not a package content id")
    return store_dir(base_path) / _BLOBS / f"{sha256}.json"


def blob_owned(base_path: str | Path, author_id: str, sha256: str) -> bool:
    with _db(base_path) as conn:
        return conn.execute(
            "SELECT 1 FROM blobs WHERE author_id = ? AND blob_sha256 = ?",
            (author_id, sha256)).fetchone() is not None


def store_blob(base_path: str | Path, *, author_id: str, blob: bytes) -> str:
    """Record ``author_id`` as an owner of ``blob``, then write it once.

    Ownership first: a crash between the two leaves a charged row and no file
    (an over-count), never an uncharged file. Content-addressed, so a second
    write of identical bytes is a no-op.
    """
    sha = hashlib.sha256(blob).hexdigest()
    path = _blob_path(base_path, sha)
    with _db(base_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blobs (author_id, blob_sha256, size_bytes, created_at) "
            "VALUES (?, ?, ?, ?)", (author_id, sha, len(blob), time.time()))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return sha
    tmp = path.with_name(f".{sha}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    with open(tmp, "xb") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return sha


def read_blob(base_path: str | Path, sha256: str) -> bytes:
    """The blob, verified against its own name."""
    path = _blob_path(base_path, sha256)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise PackageError("this package's content is not available") from None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PACKAGE_BYTES:
        raise PackageError("this package's content is not available")
    with open(path, "rb") as handle:
        data = handle.read(MAX_PACKAGE_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise PackageError("this package's content does not match its id")
    return data


def record_version(base_path: str | Path, *, author_id: str, name: str, version: int,
                   sha256: str) -> None:
    """List ``version``. Re-recording the same content is a no-op (a retry);
    another content under the same number is a lost race."""
    with _db(base_path) as conn:
        row = conn.execute(
            "SELECT blob_sha256 FROM package_versions WHERE author_id = ? AND name = ? "
            "AND version = ?", (author_id, name, version)).fetchone()
        if row is not None:
            if row["blob_sha256"] == sha256:
                return
            raise PackageError(
                f"version {version} of \"{name}\" was published meanwhile; ask again")
        conn.execute(
            "INSERT INTO package_versions (author_id, name, version, blob_sha256, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (author_id, name, version, sha256, time.time()))


def set_version_definition(base_path: str | Path, *, author_id: str, name: str,
                           version: int, definition_id: str) -> None:
    with _db(base_path) as conn:
        conn.execute(
            "UPDATE package_versions SET definition_id = ? WHERE author_id = ? AND name = ? "
            "AND version = ?", (definition_id, author_id, name, version))


def drop_version(base_path: str | Path, *, author_id: str, name: str, version: int) -> None:
    with _db(base_path) as conn:
        conn.execute(
            "DELETE FROM package_versions WHERE author_id = ? AND name = ? AND version = ? "
            "AND definition_id = ''", (author_id, name, version))


def measure_packages(base_path: str | Path, actors: list[str]) -> int:
    """The ``packages`` store: every blob these principals own, listed or not."""
    path = store_dir(base_path) / _DB
    if not path.exists() or not actors:
        return 0
    marks = ",".join("?" * len(actors))
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        row = conn.execute(
            f"SELECT SUM(size_bytes) FROM blobs WHERE author_id IN ({marks})",
            tuple(actors)).fetchone()
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()
    return int(row[0] or 0)


def pin(base_path: str | Path, *, universe_id: str, kind: str, agent: str, digest: str,
        record: dict[str, Any]) -> str:
    """Pin a consent record; returns its id. The same content pins once."""
    pin_id = hashlib.sha256(f"{kind}\x00{agent}\x00{digest}".encode()).hexdigest()[:32]
    with _db(base_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO pins (universe_id, pin_id, kind, agent_id, digest, "
            "record_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (universe_id, pin_id, kind, agent, digest,
             json.dumps(record, sort_keys=True), time.time()))
    return pin_id


def bind_request(base_path: str | Path, *, universe_id: str, pin_id: str,
                 request_id: str) -> None:
    """Tie a pin to the request that displays it. First request wins: no later
    request can take over a pin."""
    with _db(base_path) as conn:
        conn.execute(
            "UPDATE pins SET request_id = ? WHERE universe_id = ? AND pin_id = ? "
            "AND request_id = ''", (request_id, universe_id, pin_id))


def pin_for_request(base_path: str | Path, *, universe_id: str,
                    request_id: str) -> dict[str, Any] | None:
    """The consent record bound to ``request_id`` in this command center, or None."""
    if not request_id:
        return None
    with _db(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM pins WHERE universe_id = ? AND request_id = ?",
            (universe_id, request_id)).fetchone()
    if row is None:
        return None
    return {"pin_id": row["pin_id"], "kind": row["kind"], "agent": row["agent_id"],
            "digest": row["digest"], "record": json.loads(row["record_json"]),
            "state": row["state"], "progress": json.loads(row["progress_json"])}


#: How long one activation holds its claim. A second confirm inside it is
#: refused rather than run beside the first; after it, the claim is a crashed
#: activation's and a confirm resumes it.
CLAIM_LEASE_S = 600.0


def claim(base_path: str | Path, *, universe_id: str, pin_id: str,
          now: float | None = None) -> str:
    """Claim a pin for activation, atomically. Returns ``pinned`` (claimed
    fresh), ``activating`` (a stale claim taken over: resume), or
    ``activated`` (done already). A live claim raises `PackageError`."""
    moment = time.time() if now is None else now
    with _db(base_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT state, claimed_at FROM pins WHERE universe_id = ? AND pin_id = ?",
                (universe_id, pin_id)).fetchone()
            if row is None:
                raise PackageError("this request's consent record is missing")
            state = str(row["state"])
            if state == "activating" and moment - float(row["claimed_at"] or 0) < CLAIM_LEASE_S:
                raise PackageError("this is already being installed; wait a moment")
            if state != "activated":
                conn.execute("UPDATE pins SET state = 'activating', claimed_at = ? "
                             "WHERE universe_id = ? AND pin_id = ?",
                             (moment, universe_id, pin_id))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return state


def unclaim(base_path: str | Path, *, universe_id: str, pin_id: str) -> None:
    """Let the next confirm resume at once: a failed activation stops holding."""
    with _db(base_path) as conn:
        conn.execute("UPDATE pins SET claimed_at = 0 WHERE universe_id = ? AND pin_id = ? "
                     "AND state = 'activating'", (universe_id, pin_id))


def record_progress(base_path: str | Path, *, universe_id: str, pin_id: str,
                    progress: dict[str, Any]) -> None:
    with _db(base_path) as conn:
        conn.execute("UPDATE pins SET progress_json = ? WHERE universe_id = ? AND pin_id = ?",
                     (json.dumps(progress, sort_keys=True, default=str), universe_id, pin_id))


def finish(base_path: str | Path, *, universe_id: str, pin_id: str,
           progress: dict[str, Any]) -> None:
    with _db(base_path) as conn:
        conn.execute(
            "UPDATE pins SET state = 'activated', progress_json = ?, activated_at = ? "
            "WHERE universe_id = ? AND pin_id = ?",
            (json.dumps(progress, sort_keys=True, default=str), time.time(), universe_id,
             pin_id))


# --------------------------------------------------------------------------- #
# The ingestion boundary
# --------------------------------------------------------------------------- #


def check_blob(blob: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """``(manifest, files)`` from a blob, or `PackageError`. Nothing is written.

    Bounds bytes, file count, depth and path length; refuses absolute,
    traversal, hidden and colliding paths and a file where a folder must be;
    every file must be listed in the manifest with the size and sha256 it has.
    """
    if len(blob) > MAX_PACKAGE_BYTES:
        raise PackageError(f"this package is over {human(MAX_PACKAGE_BYTES)}")
    try:
        doc = json.loads(blob)
    except (ValueError, RecursionError):
        raise PackageError("this package's content is not a package") from None
    if not isinstance(doc, dict) or doc.get("format_version") != FORMAT_VERSION:
        raise PackageError("this package's format is not one this platform reads")
    manifest, raw_files = doc.get("manifest"), doc.get("files")
    if not isinstance(manifest, dict) or not isinstance(raw_files, dict):
        raise PackageError("this package's content is not a package")
    if manifest.get("profile") != PROFILE_PUBLISH:
        raise PackageError("only published packages install")
    if len(raw_files) > MAX_FILES:
        raise PackageError(f"this package has over {MAX_FILES} files")
    listed = manifest.get("files")
    if not isinstance(listed, list) or len(listed) != len(raw_files):
        raise PackageError("this package's file list does not match its content")
    files: dict[str, bytes] = {}
    for path, encoded in raw_files.items():
        check_path(path)
        if not isinstance(encoded, str):
            raise PackageError(f"{path!r} is not a regular file")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise PackageError(f"{path!r} is not a regular file") from None
        if len(data) > MAX_FILE_BYTES:
            raise PackageError(f"{path!r} is over the per-file bound")
        files[path] = data
    check_tree(list(files))
    for entry in listed:
        if not isinstance(entry, dict) or entry.get("path") not in files:
            raise PackageError("this package's file list does not match its content")
        data = files[entry["path"]]
        if entry.get("size") != len(data) or entry.get("sha256") != hashlib.sha256(
                data).hexdigest():
            raise PackageError(f"{entry['path']!r} does not match its listed digest")
    return manifest, files


# --------------------------------------------------------------------------- #
# Install: where files land, and the writer
# --------------------------------------------------------------------------- #


def slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = _SLUG.sub("-", ascii_name.lower()).strip("-")[:40].strip("-")
    return text or "package"


def destination(path: str, agent_slug: str) -> str:
    """Where a package file lands in the installer's command center.

    Root harness files become a roster agent (``agents/<slug>/``) and the
    package's own roster agents ``agents/<slug>-<id>/``: the installer's main
    agent is never written. Workspace files and wiki pages keep their path,
    because the UI and the workflows address them by path.
    """
    parts = path.split("/")
    if path in HARNESS_ROOT_FILES or (len(parts) > 1 and parts[0] in HARNESS_ROOT_DIRS):
        return f"agents/{agent_slug}/{path}"
    if parts[0] == "agents" and len(parts) >= 3:
        return f"agents/{agent_slug}-{parts[1]}/" + "/".join(parts[2:])
    return path


def _exists(universe_dir: Path, rel: str) -> bool:
    try:
        os.lstat(Path(universe_dir) / rel)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _blocked(universe_dir: Path, rel: str) -> bool:
    """A parent of ``rel`` exists and is not a plain folder (a file or a link)."""
    parts = rel.split("/")
    for i in range(1, len(parts)):
        try:
            info = os.lstat(Path(universe_dir) / "/".join(parts[:i]))
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) \
                or getattr(info, "st_reparse_tag", 0):
            return True
    return False


def plan_install(universe_dir: Path, manifest: dict[str, Any],
                 files: dict[str, bytes]) -> dict[str, Any]:
    """Every file's destination, and which stay the installer's own.

    A destination that already exists, or whose folder is taken by a file or a
    link, is kept as theirs and named. The destination map is checked as a
    tree after relocation.
    """
    base = slug(str(manifest.get("name") or "package"))
    agent_slug, n = base, 1
    while _exists(universe_dir, f"agents/{agent_slug}") or any(
            _exists(universe_dir, f"agents/{agent_slug}-{a}") for a in manifest.get(
                "agents") or [] if isinstance(a, str) and a != "main"):
        n += 1
        agent_slug = f"{base}-{n}"
    mapping = {path: check_path(destination(path, agent_slug)) for path in sorted(files)}
    check_tree(list(mapping.values()))
    land: list[dict[str, str]] = []
    keep: list[str] = []
    for path, dest in mapping.items():
        if _exists(universe_dir, dest) or _blocked(universe_dir, dest):
            keep.append(dest)
        else:
            land.append({"path": path, "to": dest})
    return {"agent_slug": agent_slug, "land": land, "keep": keep,
            "bytes": sum(len(files[e["path"]]) for e in land)}


def write_new_file(universe_dir: Path, rel: str, data: bytes) -> bool:
    """Create ``rel`` holding ``data``. False if it already exists.

    Every directory is created and then opened through its parent without
    following a link; the file is created ``O_EXCL | O_NOFOLLOW``. A link
    planted anywhere on the path refuses (``OSError``) rather than redirecting.
    """
    check_path(rel)
    parts = rel.split("/")
    if getattr(fs, "_POSIX", False):
        current = fs.open_dir_nofollow(Path(universe_dir).resolve(strict=False))
        try:
            for part in parts[:-1]:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, 0o755, dir_fd=current)
                child = fs.open_subdir_nofollow(current, part)
                os.close(current)
                current = child
            try:
                fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o644,
                             dir_fd=current)
            except FileExistsError:
                return False
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(parts[-1], dir_fd=current)
                raise
            return True
        finally:
            os.close(current)
    # Non-POSIX (a single-tenant tray): refuse a link at any component.
    current = Path(universe_dir)
    for part in parts[:-1]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0)
                or not stat.S_ISDIR(info.st_mode)):
            raise OSError(f"{part!r} is a link or not a folder")
    target = current / parts[-1]
    try:
        with open(target, "xb") as handle:  # noqa: PTH123 - parents link-checked above
            handle.write(data)
    except FileExistsError:
        return False
    return True


__all__ = [
    "FORMAT_VERSION",
    "PACKAGE_KIND",
    "PACKAGE_TAG",
    "PROFILE_PUBLISH",
    "PackageError",
    "build_manifest",
    "build_publish_package",
    "check_blob",
    "check_path",
    "classify",
    "plan_install",
    "read_blob",
    "scan_public",
    "store_blob",
    "write_new_file",
]
