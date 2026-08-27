"""Typed authoring file I/O — declared manifests, execution-scoped handles,
bounded deliverables.

Requirement source: ``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets/
specs/node-authoring-and-autoresearch/spec.md`` — "Files are typed
execution-scoped inputs and deliverables" (tasks 4.2, 4.5).
"""

from __future__ import annotations

import base64
import json

import pytest

PDF = b"%PDF-1.4 tiny"


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    return base


@pytest.fixture
def store(env):
    from tinyassets.authoring.store import AuthoringStore

    st = AuthoringStore()
    st.initialize()
    return st


@pytest.fixture
def session(store):
    from tinyassets.authoring import service

    started = service.start_session(
        actor_id="alice", artifact_kind="node", sketch="summarize papers", store=store
    )
    service.apply_edit_batch(
        actor_id="alice",
        session_id=started["session_id"],
        store=store,
        operations=[
            {
                "op": "set",
                "path": "io_manifest",
                "value": {
                    "inputs": [
                        {
                            "name": "sources",
                            "io_type": "file_bundle",
                            "media_types": ["application/pdf"],
                            "min_count": 1,
                            "max_count": 3,
                            "max_bytes": 4096,
                            "required": True,
                        },
                        {
                            "name": "topic",
                            "io_type": "scalar",
                            "required": True,
                        },
                    ],
                    "outputs": [
                        {
                            "name": "digest",
                            "io_type": "file",
                            "media_types": ["text/markdown"],
                            "max_bytes": 4096,
                        },
                    ],
                },
            },
        ],
    )
    return service.get_session_record(
        actor_id="alice", session_id=started["session_id"], store=store
    )


def _attachment(name="paper.pdf", media="application/pdf", data=PDF):
    return {
        "filename": name,
        "media_type": media,
        "content_b64": base64.b64encode(data).decode("ascii"),
    }


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def test_manifest_declares_types_bounds_and_cardinality(session):
    from tinyassets.authoring import io

    manifest = io.parse_manifest(session.definition)
    sources = manifest.input("sources")
    assert sources.io_type == "file_bundle"
    assert sources.media_types == ("application/pdf",)
    assert (sources.min_count, sources.max_count) == (1, 3)
    assert sources.max_bytes == 4096
    assert manifest.input("topic").io_type == "scalar"
    assert manifest.output("digest").io_type == "file"


def test_unknown_io_type_fails_loudly(session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import AuthoringValidationError

    bad = dict(session.definition)
    bad["io_manifest"] = {"inputs": [{"name": "x", "io_type": "telepathy"}], "outputs": []}
    with pytest.raises(AuthoringValidationError) as exc:
        io.parse_manifest(bad)
    assert any(i.code == "manifest.unknown_io_type" for i in exc.value.issues)


# ---------------------------------------------------------------------------
# Input binding
# ---------------------------------------------------------------------------


def test_attached_pdfs_bind_to_opaque_execution_scoped_handles(store, session):
    from tinyassets.authoring import io

    bound = io.bind_inputs(
        session,
        {"sources": [_attachment("a.pdf"), _attachment("b.pdf")], "topic": "sourdough"},
        store=store,
        actor_id="alice",
    )

    handles = bound.values["sources"]
    assert len(handles) == 2
    for handle in handles:
        assert handle["handle_id"].startswith("fh_")
        assert handle["media_type"] == "application/pdf"
        assert handle["size_bytes"] == len(PDF)
        assert handle["sha256"]
        assert handle["expires_at"]
        # No client or host filesystem path is exposed to the definition.
        assert "path" not in handle
    serialized = json.dumps(bound.values)
    assert str(store.path.parent) not in serialized
    assert bound.values["topic"] == "sourdough"

    # The bytes are retrievable only through the handle boundary.
    assert io.read_handle_bytes(
        store,
        handles[0]["handle_id"],
        actor_id="alice",
        session_id=session.session_id,
    ) == PDF


def test_disallowed_media_type_fails_before_execution(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(
            session,
            {"sources": [_attachment("evil.exe", "application/x-msdownload")], "topic": "t"},
            store=store,
            actor_id="alice",
        )
    issues = {(i.code, i.path) for i in exc.value.issues}
    assert ("manifest.media_type_not_allowed", "sources[0]") in issues


def test_oversize_and_overcount_attachments_are_refused(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(
            session,
            {"sources": [_attachment(data=b"x" * 5000)], "topic": "t"},
            store=store,
            actor_id="alice",
        )
    assert any(i.code == "manifest.size_exceeded" for i in exc.value.issues)

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(
            session,
            {"sources": [_attachment() for _ in range(4)], "topic": "t"},
            store=store,
            actor_id="alice",
        )
    assert any(i.code == "manifest.cardinality" for i in exc.value.issues)


def test_missing_required_input_is_field_level_evidence(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(session, {"topic": "t"}, store=store, actor_id="alice")
    issues = {(i.code, i.path) for i in exc.value.issues}
    assert ("manifest.required_missing", "sources") in issues


def test_undeclared_input_is_refused(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(
            session,
            {"sources": [_attachment()], "topic": "t", "smuggled": "value"},
            store=store,
            actor_id="alice",
        )
    assert any(i.code == "manifest.undeclared_input" for i in exc.value.issues)


def test_client_paths_are_never_accepted_as_file_content(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    with pytest.raises(ManifestViolation) as exc:
        io.bind_inputs(
            session,
            {"sources": [{"filename": "a.pdf", "media_type": "application/pdf",
                          "path": "C:/Users/alice/secrets.pdf"}], "topic": "t"},
            store=store,
            actor_id="alice",
        )
    assert any(i.code == "manifest.unresolvable_attachment" for i in exc.value.issues)


# ---------------------------------------------------------------------------
# Filename policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "etc_passwd"),
        ("C:\\Windows\\system32\\evil.dll", "C_Windows_system32_evil.dll"),
        ("  spaced name .pdf ", "spaced name .pdf"),
        ("", "unnamed"),
        ("." * 5, "unnamed"),
    ],
)
def test_safe_filename_strips_traversal(raw, expected):
    from tinyassets.authoring import io

    assert io.safe_filename(raw) == expected


def test_bound_handle_filename_is_sanitized(store, session):
    from tinyassets.authoring import io

    bound = io.bind_inputs(
        session,
        {"sources": [_attachment("../../../etc/shadow.pdf")], "topic": "t"},
        store=store,
        actor_id="alice",
    )
    assert bound.values["sources"][0]["filename"] == "etc_shadow.pdf"


# ---------------------------------------------------------------------------
# Output deliverables
# ---------------------------------------------------------------------------


def test_declared_file_output_is_a_bounded_deliverable(store, session):
    from tinyassets.authoring import io

    manifest = io.parse_manifest(session.definition)
    deliverable = io.bind_output(
        manifest.output("digest"),
        filename="../digest.md",
        media_type="text/markdown",
        content=b"# notes",
    )
    assert deliverable["filename"] == "digest.md"
    assert deliverable["media_type"] == "text/markdown"
    assert deliverable["size_bytes"] == len(b"# notes")
    assert deliverable["disposition"] == "download"


def test_connector_push_disposition_requires_declaration(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    manifest = io.parse_manifest(session.definition)
    with pytest.raises(ManifestViolation) as exc:
        io.bind_output(
            manifest.output("digest"),
            filename="digest.md",
            media_type="text/markdown",
            content=b"# notes",
            disposition="connector_push",
        )
    assert any(i.code == "manifest.disposition_not_declared" for i in exc.value.issues)


def test_output_exceeding_bounds_or_media_type_is_refused(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import ManifestViolation

    manifest = io.parse_manifest(session.definition)
    with pytest.raises(ManifestViolation):
        io.bind_output(
            manifest.output("digest"),
            filename="digest.md",
            media_type="text/markdown",
            content=b"x" * 5000,
        )
    with pytest.raises(ManifestViolation):
        io.bind_output(
            manifest.output("digest"),
            filename="digest.exe",
            media_type="application/x-msdownload",
            content=b"x",
        )


# ---------------------------------------------------------------------------
# Handle lifetime + isolation
# ---------------------------------------------------------------------------


def test_handle_expires_and_then_fails_closed(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import AuthoringAccessError

    bound = io.bind_inputs(
        session,
        {"sources": [_attachment()], "topic": "t"},
        store=store,
        actor_id="alice",
        lifetime_seconds=1,
    )
    handle_id = bound.values["sources"][0]["handle_id"]
    assert io.read_handle_bytes(
        store, handle_id, actor_id="alice", session_id=session.session_id
    ) == PDF

    later = store.now() + 5.0
    with pytest.raises(AuthoringAccessError):
        io.read_handle_bytes(
            store, handle_id, actor_id="alice", session_id=session.session_id, now=later
        )


def test_revoked_handle_fails_closed(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import AuthoringAccessError

    bound = io.bind_inputs(
        session, {"sources": [_attachment()], "topic": "t"}, store=store, actor_id="alice"
    )
    handle_id = bound.values["sources"][0]["handle_id"]
    store.revoke_file_handle(handle_id, actor_id="alice")

    with pytest.raises(AuthoringAccessError):
        io.read_handle_bytes(
            store, handle_id, actor_id="alice", session_id=session.session_id
        )


def test_sibling_user_cannot_read_another_users_handle(store, session):
    from tinyassets.authoring import io
    from tinyassets.authoring.models import AuthoringAccessError

    bound = io.bind_inputs(
        session, {"sources": [_attachment()], "topic": "t"}, store=store, actor_id="alice"
    )
    handle_id = bound.values["sources"][0]["handle_id"]

    with pytest.raises(AuthoringAccessError):
        io.read_handle_bytes(
            store, handle_id, actor_id="mallory", session_id=session.session_id
        )


def test_handle_ids_are_unguessable_and_scoped_to_their_session(store, session):
    from tinyassets.authoring import io, service
    from tinyassets.authoring.models import AuthoringAccessError

    bound = io.bind_inputs(
        session, {"sources": [_attachment()], "topic": "t"}, store=store, actor_id="alice"
    )
    handle_id = bound.values["sources"][0]["handle_id"]

    other = service.start_session(
        actor_id="alice", artifact_kind="node", sketch="other", store=store
    )
    with pytest.raises(AuthoringAccessError):
        io.read_handle_bytes(
            store, handle_id, actor_id="alice", session_id=other["session_id"]
        )
