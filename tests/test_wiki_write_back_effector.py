"""PR-166 wiki write-back external-write effector tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tinyassets.api.wiki import _ensure_wiki_scaffold
from tinyassets.branches import NodeDefinition
from tinyassets.effectors import (
    EXTERNAL_WRITE_SINK_GITHUB_PR,
    EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
    read_repo_files,
    run_effects_for_branch,
    run_wiki_write_back_effector,
    search_repo_files,
)
from tinyassets.storage.effector_consents import grant_consent
from tinyassets.storage.external_write_receipts import (
    STATUS_SUCCEEDED,
    lookup_receipt,
)


def _wiki_env(tmp_path):
    wiki_root = tmp_path / "wiki"
    _ensure_wiki_scaffold(wiki_root)
    target = wiki_root / "pages" / "patch-requests" / "pr-166-test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\ntitle: PR-166 Test\ntype: patch_request\n---\n\n# PR-166 Test\n",
        encoding="utf-8",
    )
    return target


def _packet(**overrides):
    packet = {
        "sink": EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
        "destination": "pages/patch-requests/pr-166-test.md",
        "payload": {
            "heading": "Loop result packet",
            "body": (
                "Decision: KEEP\n\n"
                "Evidence: open_pr dry-run produced a proposed patch."
            ),
        },
        "idempotency_hint": "pr-166-loop-result-run-1",
    }
    packet.update(overrides)
    return packet


def test_effectors_package_preserves_existing_exports():
    assert EXTERNAL_WRITE_SINK_GITHUB_PR == "github_pull_request"
    assert callable(read_repo_files)
    assert callable(search_repo_files)
    assert callable(run_wiki_write_back_effector)


def test_wiki_write_back_without_consent_dry_runs_before_write(tmp_path):
    target = _wiki_env(tmp_path)
    before = target.read_text(encoding="utf-8")

    result = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-no-consent",
    )

    assert result["dry_run"] is True
    assert result["reason"] == "missing_consent"
    assert result["destination"] == "pages/patch-requests/pr-166-test.md"
    assert target.read_text(encoding="utf-8") == before


def test_wiki_write_back_rejects_packet_controlled_path_escape(tmp_path):
    _wiki_env(tmp_path)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
        destination="../outside.md",
        granted_by="tester",
    )

    result = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": _packet(destination="../outside.md")},
        base_path=tmp_path,
        run_id="run-path-escape",
    )

    assert result["error_kind"] == "invalid_destination"
    assert not (tmp_path / "outside.md").exists()


def test_wiki_write_back_requires_idempotency_hint_for_real_write(tmp_path):
    target = _wiki_env(tmp_path)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
        destination="pages/patch-requests/pr-166-test.md",
        granted_by="tester",
    )

    result = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": _packet(idempotency_hint="")},
        base_path=tmp_path,
        run_id="run-no-idem",
    )

    assert result["dry_run"] is True
    assert result["reason"] == "missing_idempotency_hint"
    assert "Loop result packet" not in target.read_text(encoding="utf-8")


def test_wiki_write_back_appends_section_and_records_receipt(tmp_path):
    target = _wiki_env(tmp_path)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
        destination="pages/patch-requests/pr-166-test.md",
        granted_by="tester",
    )

    result = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": json.dumps(_packet())},
        base_path=tmp_path,
        run_id="run-ok",
    )

    assert result["phase"] == "phase_2"
    assert result["status"] == "written"
    assert result["path"] == "pages/patch-requests/pr-166-test.md"
    text = target.read_text(encoding="utf-8")
    assert "## Loop result packet" in text
    assert "Decision: KEEP" in text
    assert "tinyassets-wiki-write-back:pr-166-loop-result-run-1" in text

    receipt = lookup_receipt(
        tmp_path,
        idempotency_hint="pr-166-loop-result-run-1",
        sink=EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
    )
    assert receipt is not None
    assert receipt["status"] == STATUS_SUCCEEDED
    assert receipt["evidence"]["path"] == "pages/patch-requests/pr-166-test.md"


def test_wiki_write_back_idempotency_dedup_does_not_append_twice(tmp_path):
    target = _wiki_env(tmp_path)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
        destination="pages/patch-requests/pr-166-test.md",
        granted_by="tester",
    )

    first = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-first",
    )
    second = run_wiki_write_back_effector(
        node_id="publish",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-second",
    )

    assert first["status"] == "written"
    assert second["idempotency_dedup_hit"] is True
    text = target.read_text(encoding="utf-8")
    assert text.count("## Loop result packet") == 1


def test_branch_dispatch_routes_wiki_write_back_sink(tmp_path):
    _wiki_env(tmp_path)
    branch = SimpleNamespace(
        node_defs=[
            NodeDefinition(
                node_id="publish",
                display_name="Publish",
                output_keys=["packet"],
                effects=[EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK],
            ),
        ],
    )

    ev_map = run_effects_for_branch(
        branch=branch,
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-dispatch",
    )

    ev = ev_map["publish"][EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK]
    assert ev["reason"] == "missing_consent"
