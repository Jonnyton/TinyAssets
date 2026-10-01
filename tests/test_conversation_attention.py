"""Unread observations: real SQLite transcripts, no network or model calls."""
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from tinyassets.conversation_attention import observe, reader_name, returned_page


def chunk(ident, text, offset=0, count=32768):
    value = text[offset:offset + count]
    end = offset + len(value)
    return dict(available=True, field_name=str(ident), offset=offset,
                total_chars=len(text), chunk=value, offset_unit="unicode_code_points",
                next_offset=end if end < len(text) else None)


class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with sqlite3.connect(self.root / ".conversation_memory.db") as conn:
            conn.execute("CREATE TABLE conversation_turns "
                         "(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, content TEXT)")
        self.session = "principal:founder"
        self.reader = reader_name("reader:background")

    def add(self, value, session=None):
        with sqlite3.connect(self.root / ".conversation_memory.db") as conn:
            return conn.execute("INSERT INTO conversation_turns(session_id,content) VALUES (?,?)",
                                (session or self.session, value)).lastrowid

    def watch(self, page=None, reader=None):
        return observe(self.root, self.session, reader or self.reader, page=page)

    def test_new_arrival_during_read_remains_unread(self):
        first = self.add("earlier")
        page = chunk(first, "earlier")
        second = self.add("arrived while reading")
        status = self.watch(page)
        self.assertEqual(status["unread_count"], 1)
        self.assertEqual(status["next_unread_id"], second)

    def test_catalog_is_not_a_read(self):
        ident = self.add("body")
        self.assertEqual(self.watch({"available": True, "messages": [{"id": ident}]})
                         ["unread_count"], 1)

    def test_partial_unicode_gap_and_duplicate_chunks(self):
        text = "a🌱b\x00cdef"
        ident = self.add(text)
        for offset, count in [(4, 4), (0, 2), (0, 2)]:
            self.assertEqual(self.watch(chunk(ident, text, offset, count))["unread_count"], 1)
        self.assertEqual(self.watch(chunk(ident, text, 2, 2))["unread_count"], 0)

    def test_out_of_order_message_reads_do_not_skip_older_unread(self):
        first = self.add("one")
        second = self.add("two")
        status = self.watch(chunk(second, "two"))
        self.assertEqual(status["unread_count"], 1)
        self.assertEqual(status["next_unread_id"], first)

    def test_named_reader_survives_reopen_foreground_stays_independent(self):
        ident = self.add("one")
        self.watch(chunk(ident, "one"), reader="session:foreground")
        self.assertEqual(self.watch()["unread_count"], 1)
        self.watch(chunk(ident, "one"))
        self.assertEqual(observe(self.root, self.session, "named:background")["unread_count"], 0)
        self.assertEqual(self.watch(reader="session:other")["unread_count"], 1)

    def test_other_principal_and_unknown_ids_cannot_be_acknowledged(self):
        mine = self.add("mine")
        theirs = self.add("theirs", session="principal:other")
        self.assertEqual(self.watch(chunk(theirs, "theirs"))["unread_count"], 1)
        self.assertEqual(self.watch()["next_unread_id"], mine)
        with sqlite3.connect(self.root / ".conversation_attention.db") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reads").fetchone()[0], 0)

    def test_deleted_history_not_in_count(self):
        self.add("gone")
        with sqlite3.connect(self.root / ".conversation_memory.db") as conn:
            conn.execute("DELETE FROM conversation_turns")
        self.assertEqual(self.watch()["unread_count"], 0)

    def test_missing_store_is_unknown_without_creation(self):
        (self.root / ".conversation_memory.db").unlink()
        self.assertIsNone(self.watch()["unread_count"])
        self.assertFalse((self.root / ".conversation_memory.db").exists())

    def test_symlink_store_refused(self):
        target = self.root / "outside.db"
        (self.root / ".conversation_memory.db").rename(target)
        try:
            (self.root / ".conversation_memory.db").symlink_to(target)
        except PermissionError:
            self.skipTest("sandbox forbids creating symlinks; CI must exercise this guard")
        with self.assertRaises(PermissionError):
            self.watch()

    def test_invalid_and_truncated_results_do_not_ack(self):
        ident = self.add("body")
        page = chunk(ident, "body")
        for change in [{"truncated": True}, {"available": False}, {"error": "failed"},
                       {"offset": -1}, {"next_offset": 5}, {"field_name": "99"}]:
            self.assertEqual(self.watch(dict(page, **change))["unread_count"], 1)
        bounded = {"truncated": True, "content": json.dumps(page)}
        parsed = returned_page([SimpleNamespace(text=json.dumps(bounded))])
        self.assertEqual(self.watch(parsed)["unread_count"], 1)

    def test_exact_untrusted_envelope_and_empty_message(self):
        ident = self.add("")
        envelope = {"untrusted": True, "source": "conversation", "content": chunk(ident, "")}
        page = returned_page([SimpleNamespace(text=json.dumps(envelope))])
        self.assertEqual(self.watch(page)["unread_count"], 0)
        envelope["source"] = "commons:another"
        self.assertIsNone(returned_page([SimpleNamespace(text=json.dumps(envelope))]))

    def test_parallel_chunks_merge_without_lost_update(self):
        ident = self.add("abcdefgh")
        self.watch()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(self.watch, [chunk(ident, "abcdefgh", 0, 4),
                                       chunk(ident, "abcdefgh", 4, 4)]))
        self.assertEqual(self.watch()["unread_count"], 0)

    def test_reader_validation(self):
        for name in ["reader:", "reader:../other", "reader:a b"]:
            with self.assertRaises(ValueError):
                reader_name(name)
        self.assertIsNone(reader_name("something else"))


if __name__ == "__main__":
    unittest.main()
