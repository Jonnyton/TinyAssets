from pathlib import Path

DOC = Path("pages/plans/chatbot-builder-behaviors.md")


def test_chatbot_builder_behaviors_documents_concurrent_session_discipline() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "## Concurrent-session discipline" in text
    assert "source_read_proof.sha256" in text
    assert "expected_sha256" in text
    assert "pages/notes/<project>-in-flight-<subslice>-<session>-<date>.md" in text
    assert "wiki action=since changed_since=<recent ISO timestamp>" in text
    assert "stop forward progress and write a concern note" in text
