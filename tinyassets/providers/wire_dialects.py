"""Bundled model wire dialects: data documents resolved by structural name.

A dialect describes HOW a model endpoint is spoken to, never WHO runs it. Each
document in ``dialects/`` names one structure (``chat_messages``,
``content_blocks``) and declares its message shape, tool shape, where the
system prompt goes, the text request path, any headers the wire itself needs,
and (for tool-capable dialects) the agent envelope of field names and response
pointers. A connection's ``uses.model.wire`` names one of these documents, so a
provider nobody has written code for connects by naming the structure it speaks.

Older stored rows name a dialect by a historical alias; ``canonical_dialect``
maps the alias to its structural name so those rows resolve unchanged. Nothing
here performs I/O beyond reading the bundled documents, and nothing here
touches credentials, grants or model admission.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

#: Structural message shapes an installed encoder implements.
MESSAGE_DIALECTS = frozenset({"chat_messages", "content_blocks"})
#: Structural tool shapes. ``none`` means text-only on this dialect.
TOOL_DIALECTS = frozenset({"chat_functions", "none"})
#: Where each message dialect places the system prompt. The document states it
#: and loading checks it, so a document cannot describe a placement its
#: encoder does not perform.
_SYSTEM_PLACEMENT = {"chat_messages": "message", "content_blocks": "top_level"}

_FIELDS = {"dialect", "aliases", "message_dialect", "tool_dialect", "system",
           "text_path", "headers"}
_OPTIONAL = {"envelope"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_PATH_RE = re.compile(r"^/[A-Za-z0-9_/.-]{0,511}$")
_HEADER_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class UnknownDialect(ValueError):
    """A connection named a wire dialect that is not bundled."""


def _validate(document: Any, filename: str) -> dict[str, Any]:
    if type(document) is not dict or not _FIELDS <= document.keys() <= _FIELDS | _OPTIONAL:
        raise ValueError(f"wire dialect {filename}: fields are invalid")
    name = document["dialect"]
    if type(name) is not str or not _NAME_RE.match(name) or f"{name}.json" != filename:
        raise ValueError(f"wire dialect {filename}: name must match its file")
    aliases = document["aliases"]
    if type(aliases) is not list or any(
        type(alias) is not str or not _NAME_RE.match(alias) for alias in aliases
    ):
        raise ValueError(f"wire dialect {filename}: aliases are invalid")
    message = document["message_dialect"]
    if message not in MESSAGE_DIALECTS:
        raise ValueError(f"wire dialect {filename}: message_dialect is not installed")
    tools = document["tool_dialect"]
    if tools not in TOOL_DIALECTS:
        raise ValueError(f"wire dialect {filename}: tool_dialect is not installed")
    if tools == "chat_functions" and message != "chat_messages":
        raise ValueError(f"wire dialect {filename}: chat_functions needs chat_messages")
    if (tools == "none") != ("envelope" not in document):
        raise ValueError(f"wire dialect {filename}: a tool dialect needs an envelope")
    if document["system"] != _SYSTEM_PLACEMENT[message]:
        raise ValueError(f"wire dialect {filename}: system placement disagrees with encoder")
    path = document["text_path"]
    if type(path) is not str or not _PATH_RE.match(path) or "//" in path:
        raise ValueError(f"wire dialect {filename}: text_path is invalid")
    headers = document["headers"]
    if type(headers) is not dict or any(
        type(key) is not str or not _HEADER_RE.match(key)
        or type(value) is not str or not value.isprintable() or len(value) > 200
        for key, value in headers.items()
    ):
        raise ValueError(f"wire dialect {filename}: headers are invalid")
    return document


@cache
def _documents() -> tuple[tuple[str, str], ...]:
    """(name, canonical JSON) for every bundled document; CWD-independent."""
    folder = Path(__file__).with_name("dialects")
    loaded = []
    for path in sorted(folder.glob("*.json")):
        document = _validate(json.loads(path.read_text(encoding="utf-8")), path.name)
        loaded.append((document["dialect"], json.dumps(document, sort_keys=True)))
    if not loaded:
        raise ValueError("no bundled wire dialects")
    return tuple(loaded)


@cache
def _names() -> dict[str, str]:
    names: dict[str, str] = {}
    for name, raw in _documents():
        for key in (name, *json.loads(raw)["aliases"]):
            if key in names:
                raise ValueError(f"wire dialect name {key!r} is declared twice")
            names[key] = name
    return names


def dialect_names() -> tuple[str, ...]:
    """Structural names of the bundled dialects."""
    return tuple(name for name, _ in _documents())


def known_names() -> tuple[str, ...]:
    """Every name a stored row or a new connection may use, aliases included."""
    return tuple(sorted(_names()))


def canonical_dialect(name: Any) -> str:
    """Structural name for ``name`` (itself, or the dialect an alias belongs to)."""
    try:
        return _names()[name]
    except (KeyError, TypeError):
        raise UnknownDialect(
            "wire must name a bundled dialect: " + ", ".join(dialect_names())
        ) from None


def same_dialect(left: Any, right: Any) -> bool:
    """Whether two stored names denote one dialect (``openai_chat`` == ``chat_messages``)."""
    try:
        return canonical_dialect(left) == canonical_dialect(right)
    except UnknownDialect:
        return False


def dialect_document(name: Any) -> dict[str, Any]:
    """A detached copy of the document ``name`` resolves to."""
    canonical = canonical_dialect(name)
    raw = dict(_documents())[canonical]
    return json.loads(raw)


__all__ = [
    "MESSAGE_DIALECTS",
    "TOOL_DIALECTS",
    "UnknownDialect",
    "canonical_dialect",
    "dialect_document",
    "dialect_names",
    "known_names",
    "same_dialect",
]
