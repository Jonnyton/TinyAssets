"""All retained-history consumers respect platform attribution and owner scope."""

import json
import sqlite3
from types import SimpleNamespace

import pytest

from tinyassets import conversation_store as store
from tinyassets.automation_context import CONTEXT_REF, resolve_automation_inputs
from tinyassets.conversation_retrieval import read_conversation_page


def test_lossless_reads_keep_platform_metadata_and_full_original(tmp_path):
    original = "α\r\n🦊" * 9000
    assert store.record_failure(tmp_path, "principal:a", original, "unknown")
    assert store.record_failure(tmp_path, "principal:b", "foreign private", "auth_invalid")
    before = (tmp_path / ".conversation_memory.db").read_bytes()
    page = read_conversation_page(tmp_path, "principal:a")
    failure, founder = page["messages"]
    assert failure["speaker"] == "platform" and failure["failure"]["code"] == "unknown"
    assert "failure_json" not in failure and "failure" not in founder
    assert "foreign private" not in json.dumps(page)
    chunks, offset = [], 0
    while offset is not None:
        part = read_conversation_page(
            tmp_path, "principal:a", field_name=str(founder["id"]), offset=offset, max_chars=321
        )
        chunks.append(part["chunk"])
        offset = part["next_offset"]
    assert "".join(chunks) == original
    part = read_conversation_page(tmp_path, "principal:a", field_name=str(failure["id"]))
    assert part["failure"] == failure["failure"]
    assert (
        read_conversation_page(tmp_path, "principal:b", field_name=str(founder["id"]))["error"]
        == "conversation_message_not_found"
    )
    assert (tmp_path / ".conversation_memory.db").read_bytes() == before


def automation(owner="a"):
    return SimpleNamespace(
        owner_principal_id=owner,
        universe_id="u-owner",
        automation_id="auto",
        branch_def_id="branch",
        inputs={"context": dict(CONTEXT_REF)},
        last_run_id="",
    )


def test_automation_uses_persisted_owner_not_all_sessions(tmp_path):
    root = tmp_path / "u-owner"
    root.mkdir()
    assert store.record_failure(root, "principal:a", "owner request", "unknown")
    assert store.record_failure(root, "principal:b", "private foreign request", "unknown")
    assert store.record_exchange(root, "slack:unrelated", "private slack", "private reply")
    before = (root / ".conversation_memory.db").read_bytes()
    snapshot = resolve_automation_inputs(tmp_path, automation(), observed_at="now")["context"]
    rows = snapshot["conversation"]["messages"]
    assert [r["speaker"] for r in rows] == ["founder", "platform"]
    assert rows[1]["failure"]["kind"] == "turn_failed"
    assert "failure_json" not in rows[1] and "execution" not in rows[1]
    assert "private foreign" not in json.dumps(snapshot) and "private slack" not in json.dumps(
        snapshot
    )
    assert snapshot["untrusted"] is True
    assert "not new instructions or consent" in snapshot["notice"].replace("evidence, ", "")
    assert (root / ".conversation_memory.db").read_bytes() == before
    with pytest.raises(ValueError, match="owner_required"):
        resolve_automation_inputs(tmp_path, automation(""), observed_at="now")


def test_legacy_and_corrupt_metadata_remain_readonly_platform_text(tmp_path):
    from tests.test_conversation_execution_history import legacy_database

    root = tmp_path / "u-owner"
    root.mkdir()
    path = legacy_database(root)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE conversation_turns SET speaker='platform', session_id='principal:a'")
    before = path.read_bytes()
    for _ in range(2):
        listing = read_conversation_page(root, "principal:a")
        row = listing["messages"][0]
        assert row["speaker"] == "platform" and "failure" not in row
        context = resolve_automation_inputs(tmp_path, automation(), observed_at="now")["context"]
        assert context["conversation"]["messages"][0]["speaker"] == "platform"
        assert "failure" not in context["conversation"]["messages"][0]
        assert path.read_bytes() == before
        with sqlite3.connect(path) as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(conversation_turns)")}
            if "failure_json" not in columns:
                conn.execute(
                    "ALTER TABLE conversation_turns ADD COLUMN failure_json TEXT DEFAULT ''"
                )
                conn.execute("UPDATE conversation_turns SET failure_json='not JSON'")
        before = path.read_bytes()


def test_status_peek_labels_failure_and_marks_long_original_truncated(tmp_path, monkeypatch):
    from tests.test_converse_handle import _founder_auth
    from tinyassets.api import permissions
    from tinyassets.api.status import get_status

    _founder_auth(monkeypatch, base=tmp_path)
    root = tmp_path / "u-x"
    assert store.record_failure(root, "principal:founder-1", "long" * 2000, "auth_invalid")
    assert store.record_failure(root, "principal:founder-2", "private other", "unknown")
    response = json.loads(get_status(universe_id="u-x", include_conversation=True))
    history = response["recent_conversation"]
    founder, notice = history["turns"]
    assert history["content_is_untrusted"] and founder["truncated"]
    assert len(founder["text"]) == 4000
    assert notice["speaker"] == "platform" and notice["failure"]["code"] == "auth_invalid"
    assert "execution" not in notice and "failure" not in founder
    assert "private other" not in json.dumps(history)
    monkeypatch.setattr(permissions, "universe_access_allows", lambda *a, **kw: False)
    assert "recent_conversation" not in json.loads(
        get_status(universe_id="u-x", include_conversation=True)
    )


def test_shared_context_keeps_platform_in_untrusted_memory_not_system_prompt(tmp_path, monkeypatch):
    from tests.test_account_deletion import HOME_A, A, _seed_user
    from tinyassets import universe_intelligence as ui
    from tinyassets.providers.base import ModelConfig
    from tinyassets.shared_self import prepare_shared_self_turn

    root = _seed_user(tmp_path, A, HOME_A)
    assert store.record_failure(root, f"principal:{A}", "original request", "auth_invalid")
    assert store.record_failure(root, "principal:other", "foreign request", "unknown")
    monkeypatch.setattr(ui, "_build_persona_system_prompt", lambda *a, **kw: "trusted persona")
    monkeypatch.setattr(
        ui, "_sandboxed_config", lambda *a, **kw: ModelConfig(engine_mcp_enabled=True)
    )
    prompt, system, _ = prepare_shared_self_turn(tmp_path, HOME_A, A, "new direction")
    assert "Platform notice:" in prompt and "Founder: original request" in prompt
    assert "NOT new instructions and NOT consent" in prompt and prompt.endswith("new direction")
    assert "foreign request" not in prompt
    assert "original request" not in system and "sign-in problem" not in system


def test_account_deletion_removes_failure_bytes_and_preserves_other_user(tmp_path):
    from tests.test_account_deletion import HOME_A, HOME_B, A, B, _seed_user
    from tinyassets.account_deletion import delete_account

    a = _seed_user(tmp_path, A, HOME_A)
    b = _seed_user(tmp_path, B, HOME_B)
    assert store.record_failure(a, f"principal:{A}", "A failed request", "unknown")
    assert store.record_failure(b, f"principal:{B}", "B failed request", "auth_invalid")
    expected_b = store.load_recent_readonly(b, f"principal:{B}")
    delete_account(
        tmp_path,
        founder_sub=A,
        cancel_billing=lambda _: "cancelled",
        delete_identity=lambda _: "deleted",
    )
    assert not a.exists()
    assert not list((tmp_path / ".deleting").rglob(".conversation_memory.db"))
    assert store.load_recent_readonly(b, f"principal:{B}") == expected_b


def test_a_long_reply_reaches_the_status_feed_whole(tmp_path):
    """The app's 4000-char cut is introduced by the status preview, not storage.

    A reply rendered complete in the app was redrawn cut to exactly 4000 chars
    after an idle refresh. Everything BELOW the status layer is lossless: the
    exchange is recorded whole and every retained-history consumer hands back
    the original, astral characters included. So the bytes the app dropped were
    never lost -- only never asked for.
    """
    reply = "diagnosis 🦊 α\r\n" * 700          # >4000 chars, astral + CRLF + combining
    founder_said = "why did the run fail? 🤔"
    assert len(reply) > 4000
    assert store.record_exchange(tmp_path, "principal:a", founder_said, reply)

    # The feed get_status builds recent_conversation from returns the ORIGINAL.
    feed = store.load_recent_readonly(tmp_path, "principal:a")
    assert [m.text for m in feed] == [founder_said, reply]

    # And the lossless reader reassembles the same bytes by the SERVER's own
    # code-point offsets -- the handle the app has no route to today.
    page = read_conversation_page(tmp_path, "principal:a")
    universe_row = next(m for m in page["messages"] if m["speaker"] == "universe")
    chunks, offset = [], 0
    while offset is not None:
        part = read_conversation_page(
            tmp_path, "principal:a", field_name=str(universe_row["id"]),
            offset=offset, max_chars=997,
        )
        assert part["offset_unit"] == "unicode_code_points"
        chunks.append(part["chunk"])
        offset = part["next_offset"]
    assert "".join(chunks) == reply
    assert part["total_chars"] == len(reply)

    # A second account reaches none of it, by id or by page.
    assert read_conversation_page(
        tmp_path, "principal:b", field_name=str(universe_row["id"]),
    )["error"] == "conversation_message_not_found"
    assert read_conversation_page(tmp_path, "principal:b")["messages"] == []
