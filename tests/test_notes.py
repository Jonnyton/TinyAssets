"""Tests for the unified notes system."""

from __future__ import annotations

from tinyassets.notes import (
    Note,
    add_note,
    bulk_update_status,
    delete_note,
    format_notes_for_context,
    get_unread_notes_for_orient,
    list_notes,
    mark_notes_read,
    update_note_status,
)


class TestNoteModel:
    def test_roundtrip(self):
        note = Note(
            id="test-1", source="user", text="Focus on tension",
            category="direction",
        )
        d = note.to_dict()
        restored = Note.from_dict(d)
        assert restored.id == "test-1"
        assert restored.source == "user"
        assert restored.text == "Focus on tension"
        assert restored.category == "direction"
        assert restored.status == "unread"

    def test_defaults(self):
        note = Note.from_dict({"id": "x", "text": "hello"})
        assert note.source == "system"
        assert note.category == "observation"
        assert note.status == "unread"
        assert note.clearly_wrong is False
        assert note.anchor == {}


class TestCRUD:
    def test_add_and_list(self, tmp_path):
        note = add_note(
            tmp_path, source="user", text="More tension",
            category="direction",
        )
        assert note.id
        assert note.source == "user"

        notes = list_notes(tmp_path)
        assert len(notes) == 1
        assert notes[0].text == "More tension"

    def test_add_line_anchor(self, tmp_path):
        note = add_note(
            tmp_path,
            source="user",
            text="This phrase needs a sharper verb.",
            category="direction",
            target="output/chapter-1.md",
            anchor={
                "start_line": 12,
                "end_line": 12,
                "start_column": 9,
                "end_column": 21,
            },
        )

        restored = list_notes(tmp_path)[0]
        assert restored.id == note.id
        assert restored.target == "output/chapter-1.md"
        assert restored.anchor == {
            "start_line": 12,
            "end_line": 12,
            "start_column": 9,
            "end_column": 21,
        }

    def test_list_with_filters(self, tmp_path):
        add_note(tmp_path, source="user", text="A", category="direction")
        add_note(tmp_path, source="editor", text="B", category="concern")
        add_note(tmp_path, source="structural", text="C", category="error")

        assert len(list_notes(tmp_path, source="user")) == 1
        assert len(list_notes(tmp_path, category="concern")) == 1
        assert len(list_notes(tmp_path, status="unread")) == 3

    def test_update_status(self, tmp_path):
        note = add_note(
            tmp_path, source="editor", text="Issue",
            category="concern",
        )
        assert update_note_status(tmp_path, note.id, "read")
        notes = list_notes(tmp_path, status="read")
        assert len(notes) == 1

    def test_update_invalid_status(self, tmp_path):
        note = add_note(
            tmp_path, source="user", text="X", category="direction",
        )
        assert not update_note_status(tmp_path, note.id, "invalid")

    def test_update_nonexistent(self, tmp_path):
        assert not update_note_status(tmp_path, "nonexistent", "read")

    def test_bulk_update(self, tmp_path):
        n1 = add_note(tmp_path, source="editor", text="A", category="concern")
        n2 = add_note(tmp_path, source="editor", text="B", category="concern")
        add_note(tmp_path, source="user", text="C", category="direction")

        count = bulk_update_status(tmp_path, [n1.id, n2.id], "read")
        assert count == 2
        assert len(list_notes(tmp_path, status="read")) == 2
        assert len(list_notes(tmp_path, status="unread")) == 1

    def test_delete(self, tmp_path):
        note = add_note(
            tmp_path, source="user", text="Remove me",
            category="direction",
        )
        assert delete_note(tmp_path, note.id)
        assert len(list_notes(tmp_path)) == 0

    def test_delete_nonexistent(self, tmp_path):
        assert not delete_note(tmp_path, "nonexistent")

    def test_empty_universe(self, tmp_path):
        assert list_notes(tmp_path) == []


class TestOrientIntegration:
    def test_unread_sorted_by_priority(self, tmp_path):
        add_note(tmp_path, source="user", text="direction", category="direction")
        add_note(tmp_path, source="structural", text="error", category="error")
        add_note(tmp_path, source="editor", text="concern", category="concern")
        add_note(tmp_path, source="editor", text="protect", category="protect")

        notes = get_unread_notes_for_orient(tmp_path)
        categories = [n.category for n in notes]
        assert categories == ["error", "concern", "direction", "protect"]

    def test_excludes_read_notes(self, tmp_path):
        n1 = add_note(tmp_path, source="user", text="A", category="direction")
        add_note(tmp_path, source="user", text="B", category="direction")
        update_note_status(tmp_path, n1.id, "read")

        notes = get_unread_notes_for_orient(tmp_path)
        assert len(notes) == 1
        assert notes[0].text == "B"

    def test_format_for_context(self, tmp_path):
        notes = [
            Note(id="1", source="user", text="Focus on tension", category="direction"),
            Note(
                id="2", source="editor", text="Wrong name",
                category="error", clearly_wrong=True,
                quoted_passage="Kael said",
            ),
        ]
        context = format_notes_for_context(notes)
        assert "[user/direction]" in context
        assert "[editor/ERROR]" in context
        assert "Focus on tension" in context
        assert '"Kael said"' in context

    def test_format_empty(self):
        assert format_notes_for_context([]) == ""

    def test_mark_notes_read(self, tmp_path):
        n1 = add_note(tmp_path, source="user", text="A", category="direction")
        n2 = add_note(tmp_path, source="editor", text="B", category="concern")

        count = mark_notes_read(tmp_path, [n1.id, n2.id])
        assert count == 2
        assert len(list_notes(tmp_path, status="read")) == 2
