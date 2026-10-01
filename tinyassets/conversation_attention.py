"""Read receipts and unread counts for one owner's retained conversation.

Receipts are observational, never consent. The caller verifies the universe and
principal before using this module. Named readers survive tool-session restarts;
session readers keep concurrent foreground and background reads independent.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

_READER = r"[A-Za-z0-9_-]{1,64}\Z"


def reader_name(query):
    if not isinstance(query, str) or not query.startswith("reader:"):
        return None
    name = query.removeprefix("reader:")
    if not re.fullmatch(_READER, name):
        raise ValueError("conversation_reader_invalid")
    return "named:" + name


def _path(root, name):
    root = Path(root).resolve()
    path = root / name
    if path.resolve() != path:
        raise PermissionError("conversation_store_outside_universe")
    return path


def _receipt(payload):
    """Only an exact, successful message chunk is evidence of a read."""
    if not isinstance(payload, dict) or payload.get("available") is not True:
        return None
    if payload.get("error") or payload.get("truncated"):
        return None
    ident, offset, total, chunk = (
        payload.get("field_name"), payload.get("offset"),
        payload.get("total_chars"), payload.get("chunk"),
    )
    if (not isinstance(ident, str) or not ident.isascii() or not ident.isdecimal()
            or len(ident) > 18 or int(ident) <= 0
            or type(offset) is not int or type(total) is not int
            or offset < 0 or total < 0 or not isinstance(chunk, str)):
        return None
    end = offset + len(chunk)
    if end > total or payload.get("offset_unit") != "unicode_code_points":
        return None
    if payload.get("next_offset") != (end if end < total else None):
        return None
    return int(ident), offset, end, total


def returned_page(blocks):
    """Read the final bounded result, not an unreturned pre-truncation payload."""
    if len(blocks) != 1:
        return None
    text = getattr(blocks[0], "text", None)
    if not isinstance(text, str):
        return None
    try:
        document = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if isinstance(document, dict) and document.get("untrusted") is True:
        if document.get("source") != "conversation":
            return None
        document = document.get("content")
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except (ValueError, RecursionError):
                return None
    return document if isinstance(document, dict) else None


def observe(root, session_id, reader, *, page=None):
    """Atomically record returned coverage, then count retained unread messages."""
    if not session_id or not reader:
        raise ValueError("conversation_reader_required")
    transcript = _path(root, ".conversation_memory.db")
    if not transcript.exists():
        return {"available": False, "unread_count": None}
    receipts = _path(root, ".conversation_attention.db")
    # The transcript is read-only, including for old databases with no migrations.
    with closing(sqlite3.connect(
        transcript.as_uri() + "?mode=ro", uri=True, timeout=5.0,
    )) as history:
        history.execute("BEGIN")
        rows = history.execute(
            "SELECT id FROM conversation_turns WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    retained = {row[0] for row in rows}
    with closing(sqlite3.connect(receipts, timeout=5.0)) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS reads (
            session_id TEXT NOT NULL, reader TEXT NOT NULL, message_id INTEGER NOT NULL,
            total INTEGER NOT NULL, ranges TEXT NOT NULL,
            PRIMARY KEY(session_id, reader, message_id))""")
        conn.execute("BEGIN IMMEDIATE")
        got = _receipt(page)
        if got is not None:
            ident, start, end, total = got
            if ident in retained:
                previous = conn.execute(
                    "SELECT total, ranges FROM reads "
                    "WHERE session_id=? AND reader=? AND message_id=?",
                    (session_id, reader, ident),
                ).fetchone()
                ranges = json.loads(previous[1]) if previous and previous[0] == total else []
                ranges.append([start, end])
                merged = []
                for lo, hi in sorted(ranges):
                    if merged and lo <= merged[-1][1]:
                        merged[-1][1] = max(merged[-1][1], hi)
                    else:
                        merged.append([lo, hi])
                conn.execute(
                    "INSERT OR REPLACE INTO reads VALUES (?, ?, ?, ?, ?)",
                    (session_id, reader, ident, total, json.dumps(merged)),
                )
        seen = set()
        for ident, total, raw in conn.execute(
            "SELECT message_id, total, ranges FROM reads WHERE session_id=? AND reader=?",
            (session_id, reader),
        ):
            if ident in retained and json.loads(raw) == [[0, total]]:
                seen.add(ident)
        conn.commit()
    return {
        "available": True,
        "unread_count": len(retained - seen),
        "next_unread_id": min(retained - seen, default=None),
        "reader": reader,
        "retention": "Retained messages only; counts are observations, never consent.",
    }
