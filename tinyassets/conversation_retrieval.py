"""Read-only, lossless paging of the current founder's retained conversation.

The caller supplies a verified universe directory and principal session. This
module never discovers other sessions and never creates or migrates a store.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

PAGE_SIZE = 20


def read_conversation_page(universe_dir, session_id, *, field_name="", offset=0, max_chars=8192):
    if not session_id:
        raise ValueError("conversation_session_required")
    if type(offset) is not int or offset < 0:
        raise ValueError("conversation_offset_invalid")
    if type(max_chars) is not int or not 1 <= max_chars <= 32768:
        raise ValueError("conversation_chunk_size_invalid")
    root = Path(universe_dir).resolve()
    path = root / ".conversation_memory.db"
    if path.resolve() != path:
        raise PermissionError("conversation_store_outside_universe")
    if not path.exists():
        return {"available": False, "messages": [], "next_offset": None}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)) as conn:
        conn.row_factory = sqlite3.Row
        if field_name:
            if not field_name.isascii() or not field_name.isdecimal() or len(field_name) > 18:
                raise ValueError("conversation_message_id_invalid")
            row = conn.execute(
                "SELECT id, speaker, ts, content FROM conversation_turns "
                "WHERE session_id = ? AND id = ?",
                (session_id, int(field_name)),
            ).fetchone()
            if row is None:
                return {"available": True, "error": "conversation_message_not_found"}
            value = dict(row)
            content = value.pop("content")
            value["total_chars"] = len(content)
            value["chunk"] = content[offset:offset + max_chars]
            end = offset + len(value["chunk"])
            return dict(
                value, available=True, field_name=str(row["id"]),
                offset=offset, offset_unit="unicode_code_points",
                next_offset=end if end < value["total_chars"] else None,
            )
        # Keyset pagination: new arrivals cannot shift or skip the older page.
        where = "session_id = ?" + (" AND id < ?" if offset else "")
        args = (session_id, offset, PAGE_SIZE + 1) if offset else (session_id, PAGE_SIZE + 1)
        rows = conn.execute(
             "SELECT id, speaker, ts, length(CAST(content AS BLOB)) AS total_bytes "
            f"FROM conversation_turns WHERE {where} ORDER BY id DESC LIMIT ?", args,
        ).fetchall()
        kept = rows[:PAGE_SIZE]
        return {
            "available": True,
            "messages": [dict(row) for row in kept],
            "next_offset": kept[-1]["id"] if len(rows) > PAGE_SIZE else None,
            "offset_unit": "before_message_id",
            "read": "Use field_name=<id> to read a message; output_offset then counts Unicode characters.",
            "retention": "Only retained messages are available; deleted history cannot be reconstructed.",
        }
