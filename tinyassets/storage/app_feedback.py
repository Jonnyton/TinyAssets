"""Private, exportable support tickets. Submission never authorizes execution."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

KINDS = ("bug_report", "patch_request", "idea")
STATUSES = ("received", "needs_details", "in_review", "planned", "in_progress", "resolved", "closed")
LIMITS = {
    "title": 200, "description": 10000, "steps_to_reproduce": 4000,
    "expected": 2000, "actual": 2000, "app_version": 100, "surface": 100,
}


class FeedbackError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.status = status


def normalize(data):
    if not isinstance(data, dict) or set(data) - set(LIMITS) - {"kind"}:
        raise FeedbackError("invalid_submission_fields")
    if data.get("kind") not in KINDS:
        raise FeedbackError("invalid_kind")
    clean = {"kind": data["kind"]}
    for key, limit in LIMITS.items():
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            raise FeedbackError("invalid_" + key)
        clean[key] = value
    if any(not clean[key].strip() for key in ("title", "description")):
        raise FeedbackError("title_and_description_required")
    missing = [
        key for key in ("steps_to_reproduce", "expected", "actual")
        if clean["kind"] == "bug_report" and not clean[key].strip()
    ]
    return clean, missing


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
 id TEXT PRIMARY KEY, submitter TEXT NOT NULL, request_key TEXT NOT NULL,
 submission TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(submitter, request_key)
);
CREATE INDEX IF NOT EXISTS feedback_owner_created ON tickets(submitter, created);
CREATE INDEX IF NOT EXISTS feedback_created ON tickets(created);
CREATE TABLE IF NOT EXISTS events (
 ticket TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
 actor TEXT NOT NULL, created REAL NOT NULL,
 PRIMARY KEY(ticket, revision)
);
CREATE TABLE IF NOT EXISTS admission (
 actor TEXT PRIMARY KEY, window REAL NOT NULL, count INTEGER NOT NULL
);
"""


class FeedbackStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _db(self, write=False):
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        else:
            db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True,
                                 timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA secure_delete=ON")
                db.executescript(_SCHEMA)
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _actor(actor):
        if not isinstance(actor, str) or not actor.strip():
            raise FeedbackError("authentication_required", 401)

    @staticmethod
    def _visible(row, actor, reviewer):
        if row is None or (row["submitter"] != actor and actor != reviewer):
            raise FeedbackError("ticket_not_found", 404)

    @staticmethod
    def _view(row):
        submission = json.loads(row["submission"])
        _, missing = normalize(submission)
        return {
            "ticket_id": row["id"], "submission": submission,
            "status": row["status"], "revision": row["revision"],
            "created_at": row["created"], "updated_at": row["updated"],
            "missing_fields": missing, "trust": "untrusted_user_content",
            "execution_authorized": False,
        }

    def submit(self, actor, key, data):
        self._actor(actor)
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise FeedbackError("invalid_idempotency_key")
        clean, missing = normalize(data)
        body = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        now = time.time()
        with self._db(True) as db:
            old = db.execute("SELECT * FROM tickets WHERE submitter=? AND request_key=?",
                             (actor, key)).fetchone()
            if old:
                if old["submission"] != body:
                    raise FeedbackError("idempotency_conflict", 409)
                return self._view(old), False
            # Admission survives deleting a ticket and concurrent processes.
            admission = db.execute("SELECT * FROM admission WHERE actor=?", (actor,)).fetchone()
            if admission and admission["window"] > now - 3600:
                if admission["count"] >= 20:
                    raise FeedbackError("rate_limited", 429)
                db.execute("UPDATE admission SET count=count+1 WHERE actor=?", (actor,))
            else:
                db.execute("INSERT OR REPLACE INTO admission VALUES (?, ?, 1)", (actor, now))
            ticket = "fb_" + uuid.uuid4().hex
            status = "needs_details" if missing else "received"
            db.execute("INSERT INTO tickets VALUES (?,?,?,?,?,1,?,?)",
                       (ticket, actor, key, body, status, now, now))
            db.execute("INSERT INTO events VALUES (?,1,?,'',?,?)",
                       (ticket, status, actor, now))
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
            return self._view(row), True

    def list(self, actor, reviewer="", *, inbox=False, offset=0, limit=50):
        self._actor(actor)
        if inbox and (not reviewer or actor != reviewer):
            raise FeedbackError("reviewer_required", 403)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise FeedbackError("invalid_pagination")
        if not self.path.exists():
            return {"tickets": [], "next_offset": None}
        with self._db() as db:
            where, args = ("", []) if inbox else ("WHERE submitter=?", [actor])
            rows = db.execute(
                "SELECT * FROM tickets " + where + " ORDER BY created DESC, id DESC LIMIT ? OFFSET ?",
                [*args, limit + 1, offset],
            ).fetchall()
            return {
                "tickets": [self._view(row) for row in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def get(self, actor, ticket, reviewer=""):
        self._actor(actor)
        if not self.path.exists():
            raise FeedbackError("ticket_not_found", 404)
        with self._db() as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
            self._visible(row, actor, reviewer)
            result = self._view(row)
            result["history"] = [
                {"revision": e["revision"], "status": e["status"],
                 "note": e["note"], "created_at": e["created"],
                 "author": "submitter" if e["actor"] == row["submitter"] else "reviewer"}
                for e in db.execute("SELECT * FROM events WHERE ticket=? ORDER BY revision", (ticket,))
            ]
            return result

    def update(self, actor, ticket, reviewer, *, revision, status, note=""):
        self._actor(actor)
        if not reviewer or actor != reviewer:
            raise FeedbackError("reviewer_required", 403)
        if type(revision) is not int or revision < 1 or status not in STATUSES:
            raise FeedbackError("invalid_status_or_revision")
        if not isinstance(note, str) or len(note) > 4000 or "\x00" in note:
            raise FeedbackError("invalid_note")
        if not self.path.exists():
            raise FeedbackError("ticket_not_found", 404)
        with self._db(True) as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
            self._visible(row, actor, reviewer)
            if row["revision"] != revision:
                raise FeedbackError("revision_conflict", 409)
            if revision >= 200:
                raise FeedbackError("ticket_history_limit", 429)
            now = time.time()
            db.execute("UPDATE tickets SET status=?, revision=revision+1, updated=? WHERE id=?",
                       (status, now, ticket))
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                       (ticket, revision + 1, status, note, actor, now))
            return self._view(db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone())

    def reply(self, actor, ticket, reviewer, *, revision, note):
        self._actor(actor)
        if type(revision) is not int or revision < 1:
            raise FeedbackError("invalid_revision")
        if not isinstance(note, str) or not note.strip() or len(note) > 4000 or "\x00" in note:
            raise FeedbackError("invalid_note")
        if not self.path.exists():
            raise FeedbackError("ticket_not_found", 404)
        with self._db(True) as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
            self._visible(row, actor, reviewer)
            if row["revision"] != revision:
                raise FeedbackError("revision_conflict", 409)
            # Bound history growth per ticket, including duplicate button clicks.
            if revision >= 200:
                raise FeedbackError("ticket_history_limit", 429)
            now = time.time()
            db.execute("UPDATE tickets SET revision=revision+1, updated=? WHERE id=?", (now, ticket))
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                       (ticket, revision + 1, row["status"], note, actor, now))
            return self._view(db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone())

    def delete(self, actor, ticket, reviewer=""):
        self._actor(actor)
        if not self.path.exists():
            raise FeedbackError("ticket_not_found", 404)
        with self._db(True) as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
            self._visible(row, actor, reviewer)
            db.execute("DELETE FROM tickets WHERE id=?", (ticket,))

    def delete_actor(self, actor):
        """Account deletion: erase submitted content and admission identity."""
        self._actor(actor)
        if not self.path.exists():
            return
        with self._db(True) as db:
            db.execute("DELETE FROM tickets WHERE submitter=?", (actor,))
            db.execute("DELETE FROM admission WHERE actor=?", (actor,))
            # Preserve status history on others' tickets without retaining this actor.
            db.execute("UPDATE events SET actor='' WHERE actor=?", (actor,))
