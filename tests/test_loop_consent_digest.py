"""Tests for scripts/loop_consent_digest.py.

Unit-scope: pure-function helpers (parse_reopen_numbers, render_audit_log, build_digest with
mocked HTTP) plus a YAML structural test on the consent-digest + reopen workflows.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from scripts import loop_consent_digest as digest_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "loop-consent-digest.yml"
REOPEN_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "loop-consent-reopen.yml"


# ---------------------------------------------------------------------------
# parse_reopen_numbers
# ---------------------------------------------------------------------------


def test_parse_reopen_numbers_single():
    assert digest_mod.parse_reopen_numbers("reopen #918") == [918]


def test_parse_reopen_numbers_multiple_space_separated():
    assert digest_mod.parse_reopen_numbers("reopen #918 #922 #877") == [918, 922, 877]


def test_parse_reopen_numbers_multiple_comma_separated():
    assert digest_mod.parse_reopen_numbers("reopen #918, #922, #877") == [918, 922, 877]


def test_parse_reopen_numbers_case_insensitive():
    assert digest_mod.parse_reopen_numbers("REOPEN #918") == [918]
    assert digest_mod.parse_reopen_numbers("Reopen #918") == [918]


def test_parse_reopen_numbers_ignores_surrounding_text():
    body = (
        "Looks good overall but reopen #918, #922 — I want to redesign those before they "
        "die."
    )
    assert digest_mod.parse_reopen_numbers(body) == [918, 922]


def test_parse_reopen_numbers_dedupes_and_preserves_order():
    assert digest_mod.parse_reopen_numbers("reopen #918 #918 #922") == [918, 922]


def test_parse_reopen_numbers_returns_empty_for_unrelated_comment():
    assert digest_mod.parse_reopen_numbers("LGTM") == []
    assert digest_mod.parse_reopen_numbers("#918 is interesting") == []


def test_parse_reopen_numbers_handles_multiline_directives():
    body = "reopen #918\n\nAlso reopen #922 #923 because shared root cause."
    assert digest_mod.parse_reopen_numbers(body) == [918, 922, 923]


# ---------------------------------------------------------------------------
# render_audit_log
# ---------------------------------------------------------------------------


def _sample_digest_with_decisions() -> dict:
    return {
        "decisions": [
            {
                "number": 918,
                "title": "External long-run checkpoint/resume provenance primitive",
                "url": "https://github.com/Jonnyton/Workflow/issues/918",
                "decision": "auto-fix-exhausted",
                "labels": [
                    "auto-fix-exhausted",
                    "auto-fix-retries-5",
                    "auto-fix-writer-failed",
                    "daemon-request",
                ],
                "updated_at": "2026-05-20T01:30:00Z",
                "retry_count": 5,
            },
            {
                "number": 877,
                "title": "Open-brain v2 slice B — soul-guided dispatch",
                "url": "https://github.com/Jonnyton/Workflow/issues/877",
                "decision": "auto-fix-already-fixed",
                "labels": ["auto-fix-already-fixed", "daemon-request"],
                "updated_at": "2026-05-19T05:26:00Z",
                "retry_count": 0,
            },
        ],
        "summary_counts": {
            "auto-fix-exhausted": 1,
            "auto-fix-blocked": 0,
            "auto-fix-pr-blocked": 0,
            "auto-fix-branch-push-blocked": 0,
            "auto-fix-already-fixed": 1,
        },
        "cutoff": "2026-05-19T08:15:00Z",
        "generated_at": "2026-05-20T14:30:00Z",
        "should_open_pr": True,
    }


def test_render_audit_log_includes_summary_counts_and_per_issue_sections():
    rendered = digest_mod.render_audit_log(_sample_digest_with_decisions())
    assert "# Loop decisions consent — 2026-05-20" in rendered
    assert "Generated: 2026-05-20T14:30:00Z" in rendered
    assert "Decisions since: 2026-05-19T08:15:00Z" in rendered
    assert "1 auto-fix-exhausted" in rendered
    assert "1 auto-fix-already-fixed" in rendered
    assert "### #918 — auto-fix-exhausted" in rendered
    assert "### #877 — auto-fix-already-fixed" in rendered
    assert "**Retry count:** 5" in rendered
    # zero-retry decisions should not surface a stray Retry count line
    section_877 = rendered.split("### #877")[1]
    assert "**Retry count:**" not in section_877
    assert "reopen #918" in rendered
    assert "reopen #877" in rendered
    assert "Merging this PR records host consent" in rendered


def test_render_audit_log_handles_empty_decision_set():
    digest = {
        "decisions": [],
        "summary_counts": {label: 0 for label in digest_mod.TERMINAL_DECISION_LABELS},
        "cutoff": None,
        "generated_at": "2026-05-20T14:30:00Z",
        "should_open_pr": False,
    }
    rendered = digest_mod.render_audit_log(digest)
    assert "No decisions to record." in rendered
    assert "(no prior consent PR" in rendered


# ---------------------------------------------------------------------------
# _classify_decision
# ---------------------------------------------------------------------------


def test_classify_decision_prefers_exhausted_over_blocked():
    """auto-fix-exhausted is the more specific decision and should win when both labels are
    co-present (which can happen if retry-exhaustion landed on a previously-blocked issue)."""
    labels = {"auto-fix-exhausted", "auto-fix-blocked"}
    assert digest_mod._classify_decision(labels) == "auto-fix-exhausted"


def test_classify_decision_falls_back_to_unknown_when_no_terminal_label():
    assert digest_mod._classify_decision({"daemon-request", "needs-human"}) == "unknown"


def test_classify_decision_recognizes_each_terminal_label():
    for label in digest_mod.TERMINAL_DECISION_LABELS:
        assert digest_mod._classify_decision({label}) == label


# ---------------------------------------------------------------------------
# build_digest with mocked HTTP
# ---------------------------------------------------------------------------


def test_build_digest_filters_decisions_before_cutoff(monkeypatch):
    def fake_list_open_issues(repo, labels, *, api, token, timeout):
        return [
            {
                "number": 918,
                "title": "Recent decision",
                "html_url": "https://example.test/918",
                "labels": [{"name": "auto-fix-exhausted"}, {"name": "auto-fix-retries-5"}],
                "updated_at": "2026-05-20T01:30:00Z",
            },
            {
                "number": 100,
                "title": "Old decision pre-cutoff",
                "html_url": "https://example.test/100",
                "labels": [{"name": "auto-fix-blocked"}],
                "updated_at": "2026-05-15T01:30:00Z",
            },
        ]

    monkeypatch.setattr(digest_mod, "list_open_issues_with_any_label", fake_list_open_issues)
    cutoff = dt.datetime(2026, 5, 19, 8, 15, tzinfo=dt.timezone.utc)
    now = dt.datetime(2026, 5, 20, 14, 30, tzinfo=dt.timezone.utc)
    digest = digest_mod.build_digest(
        "owner/repo", api="https://api.test", token=None, timeout=1, cutoff=cutoff, now=now
    )
    numbers = [d["number"] for d in digest["decisions"]]
    assert 918 in numbers
    assert 100 not in numbers
    assert digest["should_open_pr"] is True


def test_build_digest_returns_no_open_pr_when_no_terminal_issues(monkeypatch):
    monkeypatch.setattr(
        digest_mod,
        "list_open_issues_with_any_label",
        lambda *_args, **_kwargs: [],
    )
    digest = digest_mod.build_digest(
        "owner/repo",
        api="https://api.test",
        token=None,
        timeout=1,
        cutoff=None,
        now=dt.datetime(2026, 5, 20, 14, 30, tzinfo=dt.timezone.utc),
    )
    assert digest["should_open_pr"] is False
    assert digest["decisions"] == []


def test_build_digest_records_retry_count_from_labels(monkeypatch):
    def fake_list_open_issues(repo, labels, *, api, token, timeout):
        return [
            {
                "number": 918,
                "title": "Exhausted after several retries",
                "html_url": "https://example.test/918",
                "labels": [
                    {"name": "auto-fix-exhausted"},
                    {"name": "auto-fix-retries-5"},
                ],
                "updated_at": "2026-05-20T01:30:00Z",
            }
        ]

    monkeypatch.setattr(digest_mod, "list_open_issues_with_any_label", fake_list_open_issues)
    digest = digest_mod.build_digest(
        "owner/repo",
        api="https://api.test",
        token=None,
        timeout=1,
        cutoff=None,
        now=dt.datetime(2026, 5, 20, 14, 30, tzinfo=dt.timezone.utc),
    )
    assert digest["decisions"][0]["retry_count"] == 5


# ---------------------------------------------------------------------------
# workflow YAML structure
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def digest_workflow() -> dict:
    return yaml.safe_load(DIGEST_WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def reopen_workflow() -> dict:
    return yaml.safe_load(REOPEN_WORKFLOW.read_text(encoding="utf-8"))


def test_digest_workflow_runs_on_schedule_and_dispatch(digest_workflow):
    triggers = digest_workflow.get(True, digest_workflow.get("on", {}))
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


def test_digest_workflow_invokes_the_script(digest_workflow):
    script_steps = digest_workflow["jobs"]["digest"]["steps"]
    run_steps = [str(s.get("run", "")) for s in script_steps if "run" in s]
    combined = "\n".join(run_steps)
    assert "scripts/loop_consent_digest.py" in combined
    assert "--print-pr-body" in combined


def test_digest_workflow_creates_consent_pr_with_label(digest_workflow):
    steps_text = "\n".join(
        str(s.get("run", "")) for s in digest_workflow["jobs"]["digest"]["steps"]
    )
    assert "gh pr create" in steps_text
    assert "--label loop-consent" in steps_text


def test_reopen_workflow_triggers_on_issue_comment(reopen_workflow):
    triggers = reopen_workflow.get(True, reopen_workflow.get("on", {}))
    assert "issue_comment" in triggers


def test_reopen_workflow_gates_on_loop_consent_label_and_collaborator(reopen_workflow):
    script = str(reopen_workflow["jobs"]["reopen"]["steps"][-1]["with"]["script"])
    assert "loop-consent" in script
    assert "checkCollaborator" in script
    job_if = str(reopen_workflow["jobs"]["reopen"].get("if", ""))
    assert "github.event.issue.pull_request" in job_if


def test_reopen_workflow_clears_terminal_labels_and_retry_series(reopen_workflow):
    script = str(reopen_workflow["jobs"]["reopen"]["steps"][-1]["with"]["script"])
    assert "auto-fix-exhausted" in script
    assert "auto-fix-blocked" in script
    assert "auto-fix-pr-blocked" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "auto-fix-already-fixed" in script
    assert "auto-fix-retries-" in script
    assert "removeLabel" in script


def test_reopen_workflow_posts_audit_comment_on_consent_pr(reopen_workflow):
    script = str(reopen_workflow["jobs"]["reopen"]["steps"][-1]["with"]["script"])
    assert "Reopen acknowledged" in script
    assert "createComment" in script
