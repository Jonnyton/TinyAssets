"""Tests for .github/workflows/p0-outage-triage.yml structure.

Covers:
  (a) YAML parses without error
  (b) Triggered only on issues.labeled (not schedule, not push)
  (c) Job condition gates on p0-outage label only
  (d) SSH secrets verified before acting
  (e) Compose restart command is non-destructive (--force-recreate daemon only)
  (f) Re-probe uses canonical CANARY_URL
  (g) Green path closes issue
  (h) Red path adds needs-human label (not closes)
  (i) Concurrency group is issue-scoped (prevents concurrent restarts)
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "p0-outage-triage.yml"

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _triggers(wf: dict) -> dict:
    return wf.get(True, {}) or {}


def _steps(wf: dict) -> list[dict]:
    return wf.get("jobs", {}).get("triage", {}).get("steps", [])


# ---------------------------------------------------------------------------
# (a) YAML parses
# ---------------------------------------------------------------------------

def test_p0_triage_yml_parses():
    _load()


# ---------------------------------------------------------------------------
# (b) Triggered only on issues.labeled
# ---------------------------------------------------------------------------

def test_triggered_on_issues_labeled():
    wf = _load()
    triggers = _triggers(wf)
    assert "issues" in triggers, "must have issues trigger"
    issues_trigger = triggers["issues"] or {}
    types = issues_trigger.get("types", [])
    assert "labeled" in types, "must trigger on issues.labeled"


def test_not_triggered_on_schedule():
    wf = _load()
    triggers = _triggers(wf)
    assert "schedule" not in triggers, (
        "p0-triage must NOT run on schedule — only on label events"
    )


def test_not_triggered_on_push():
    wf = _load()
    triggers = _triggers(wf)
    assert "push" not in triggers, "p0-triage must not run on push"


# ---------------------------------------------------------------------------
# (c) Job condition gates on p0-outage label
# ---------------------------------------------------------------------------

def test_job_condition_checks_p0_outage_label():
    wf = _load()
    job_if = wf.get("jobs", {}).get("triage", {}).get("if", "")
    assert "p0-outage" in str(job_if), (
        "triage job must be conditional on p0-outage label"
    )


# ---------------------------------------------------------------------------
# (d) SSH secrets verified
# ---------------------------------------------------------------------------

def test_secrets_verified_before_ssh():
    text = _text()
    assert "DO_SSH_KEY" in text
    assert "DO_DROPLET_HOST" in text
    assert "DO_SSH_USER" in text
    # There must be a verification step before the restart step.
    steps = _steps(_load())
    step_names = [s.get("name", "").lower() for s in steps]
    verify_idx = next((i for i, n in enumerate(step_names) if "secret" in n or "verify" in n), None)
    restart_idx = next((i for i, n in enumerate(step_names) if "restart" in n), None)
    assert verify_idx is not None, "must have a secrets-verify step"
    assert restart_idx is not None, "must have a restart step"
    assert verify_idx < restart_idx, "secrets verify must come before restart"


# ---------------------------------------------------------------------------
# (e) Compose restart is non-destructive
# ---------------------------------------------------------------------------

def test_restart_uses_force_recreate_daemon_only():
    text = _text()
    assert "--force-recreate" in text, "restart must use --force-recreate"
    assert "daemon" in text, "restart must target daemon service only"
    # Must NOT use `down` (destructive) or restart all services
    assert "compose down" not in text, (
        "restart must not use 'compose down' — non-destructive only"
    )


def test_restart_uses_env_file():
    assert "--env-file /etc/workflow/env" in _text()


def test_triage_uses_live_systemd_compose_file():
    text = _text()
    assert "/opt/workflow/compose.yml" in text
    assert "/opt/workflow/deploy/compose.yml" not in text


def test_image_pull_repair_uses_immutable_release_state_rollback_target():
    text = _text()
    assert "ghcr.io/jonnyton/workflow-daemon:latest" not in text
    assert "release-state.json" in text
    assert "rollback_target" in text
    assert "*@sha256:*" in text


# ---------------------------------------------------------------------------
# (f) Re-probe uses canonical URL
# ---------------------------------------------------------------------------

def test_reprobe_uses_canary_url():
    text = _text()
    assert "CANARY_URL" in text
    assert "tinyassets.io/mcp" in text


def test_reprobe_step_present():
    steps = _steps(_load())
    reprobe_steps = [s for s in steps if "probe" in (s.get("name") or "").lower()
                     and "pre" not in (s.get("name") or "").lower()]
    assert reprobe_steps, "must have a re-probe step after restart"


def test_classifier_step_does_not_inline_multiline_diag_in_bash():
    steps = _steps(_load())
    step = next(s for s in steps if s.get("id") == "classify")
    run = step.get("run", "")
    env = step.get("env", {})

    assert "steps.prediag.outputs.diag" not in run, (
        "raw diagnostics must not be interpolated into bash; multiline log "
        "content can contain shell syntax and break auto-triage"
    )
    assert env.get("DIAG") == "${{ steps.prediag.outputs.diag }}"
    assert "--input-file" in run


# ---------------------------------------------------------------------------
# (g) Green path closes issue
# ---------------------------------------------------------------------------

def test_green_path_closes_issue():
    text = _text()
    assert "state: 'closed'" in text or '"closed"' in text or "'closed'" in text, (
        "green path must close the issue"
    )
    assert "auto-recover" in text.lower() or "auto_recover" in text.lower(), (
        "green path comment must mention auto-recovery"
    )


# ---------------------------------------------------------------------------
# (h) Red path adds needs-human label (does not close)
# ---------------------------------------------------------------------------

def test_red_path_adds_needs_human_label():
    text = _text()
    assert "needs-human" in text, "red path must add needs-human label"


def test_red_path_does_not_close_issue():
    # The needs-human step should not call issues.update with state: closed.
    # Check that closing only happens in the green-path conditional block.
    steps = _steps(_load())
    red_step = next(
        (s for s in steps if "needs-human" in str(s.get("with", {}).get("script", ""))),
        None,
    )
    if red_step:
        script = red_step.get("with", {}).get("script", "")
        assert "state: 'closed'" not in script and '"closed"' not in script, (
            "red path must not close the issue"
        )


# ---------------------------------------------------------------------------
# (i) Concurrency group is issue-scoped
# ---------------------------------------------------------------------------

def test_concurrency_group_is_issue_scoped():
    wf = _load()
    concurrency = wf.get("concurrency", {})
    group = str(concurrency.get("group", ""))
    assert "issue" in group.lower() or "number" in group.lower(), (
        "concurrency group must be scoped per issue to prevent concurrent restarts"
    )


def test_concurrency_not_cancel_in_progress():
    """Triage must complete even if a second label event fires mid-run."""
    wf = _load()
    concurrency = wf.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False
