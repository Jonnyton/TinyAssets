"""Contract tests for the filing-only ``file_bug`` response."""

from __future__ import annotations

import json

import pytest

from tinyassets.api.wiki import _wiki_file_bug, wiki


@pytest.fixture
def filing_wiki(tmp_path, monkeypatch):
    wiki_root = tmp_path / "Wiki"
    for path in (
        "pages/bugs",
        "pages/feature-requests",
        "drafts/bugs",
        "drafts/feature-requests",
    ):
        (wiki_root / path).mkdir(parents=True)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID",
        "retired-branch-value",
    )
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_GOAL_ID",
        "retired-goal-value",
    )
    return wiki_root


def _file_one(*, verbose: bool) -> dict:
    return json.loads(
        _wiki_file_bug(
            component="probe",
            severity="cosmetic",
            title=f"filing-only-response-{verbose}",
            observed="x",
            expected="y",
            kind="feature",
            verbose=verbose,
        )
    )


@pytest.mark.parametrize("verbose", [False, True])
def test_response_has_no_retired_automation_metadata(filing_wiki, verbose):
    response = _file_one(verbose=verbose)

    assert response["status"] == "filed"
    assert set(response) == {
        "path",
        "bug_id",
        "status",
        "kind",
        "severity",
        "component",
        "effort_classification",
        "effort_dispatch_route",
        "note",
    }
    serialized = json.dumps(response)
    for forbidden in (
        '"investigation"',
        '"trigger"',
        "branch_task",
        "dispatcher_request_id",
        "trigger_attempt_id",
        '"run_id"',
    ):
        assert forbidden not in serialized
    assert "pipeline" not in response["note"].lower()
    assert len(serialized) < 1024


@pytest.mark.parametrize("verbose", [False, True])
def test_wiki_dispatch_cannot_restore_retired_verbose_shape(filing_wiki, verbose):
    response = json.loads(
        wiki(
            action="file_bug",
            component="probe",
            severity="cosmetic",
            title=f"dispatch-filing-only-{verbose}",
            kind="feature",
            observed="x",
            verbose=verbose,
        )
    )

    assert response["status"] == "filed"
    assert "investigation" not in response
    assert "trigger" not in response
    page = (filing_wiki / response["path"]).read_text(encoding="utf-8")
    assert "## Investigation" not in page
    assert "## Patch Packet" not in page
