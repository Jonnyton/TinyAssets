"""Tests for .github/workflows/llm-binding-canary.yml.

Pins the structural contract so the workflow cannot silently drift
to a shape that no longer alarms on LLM binding loss.
"""

from __future__ import annotations

import os
import re

import pytest

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_WF_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    ".github", "workflows", "llm-binding-canary.yml",
)
_RUNBOOK_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "docs", "ops", "host-independence-runbook.md",
)


@pytest.fixture(scope="module")
def wf() -> dict:
    if not _YAML_AVAILABLE:
        pytest.skip("pyyaml not installed")
    with open(_WF_PATH, encoding="utf-8") as f:
        # PyYAML parses bare `on:` as bool True — use get() with both keys.
        raw = yaml.safe_load(f)
    return raw


@pytest.fixture(scope="module")
def wf_text() -> str:
    with open(_WF_PATH, encoding="utf-8") as f:
        return f.read()


def _on(wf: dict) -> dict:
    return wf.get(True, wf.get("on", {}))


# ── Trigger ──────────────────────────────────────────────────────────


def test_workflow_file_exists() -> None:
    assert os.path.isfile(_WF_PATH), f"missing: {_WF_PATH}"


def test_trigger_is_schedule_and_dispatch(wf) -> None:
    triggers = _on(wf)
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


def test_schedule_is_every_6_hours(wf) -> None:
    schedules = _on(wf)["schedule"]
    crons = [s["cron"] for s in schedules]
    assert any(re.search(r"0 \*/6 \* \* \*", c) for c in crons), (
        f"expected '0 */6 * * *' schedule, got: {crons}"
    )


def test_no_push_or_pr_trigger(wf) -> None:
    triggers = _on(wf)
    assert "push" not in triggers
    assert "pull_request" not in triggers


# ── Permissions ───────────────────────────────────────────────────────


def test_issues_write_permission(wf) -> None:
    perms = wf.get("permissions", {})
    assert perms.get("issues") == "write"


def test_contents_read_permission(wf) -> None:
    perms = wf.get("permissions", {})
    assert perms.get("contents") == "read"


# ── Env / config ──────────────────────────────────────────────────────


def test_probe_url_is_canonical(wf) -> None:
    env = wf.get("env", {})
    assert env.get("PROBE_URL") == "https://tinyassets.io/mcp"


def test_alarm_label_is_llm_binding_red(wf) -> None:
    env = wf.get("env", {})
    assert env.get("ALARM_ISSUE_LABEL") == "llm-binding-red"


def test_threshold_is_2(wf) -> None:
    env = wf.get("env", {})
    assert str(env.get("ALARM_THRESHOLD")) == "2"


def test_no_extra_secrets_required(wf_text) -> None:
    # Only GITHUB_TOKEN (built-in) should be used — no host SSH secrets.
    assert "DO_SSH_KEY" not in wf_text
    assert "DO_DROPLET_HOST" not in wf_text
    assert "DO_SSH_USER" not in wf_text


# ── Jobs ──────────────────────────────────────────────────────────────


def test_probe_job_exists(wf) -> None:
    jobs = wf.get("jobs", {})
    assert "probe" in jobs


def test_alarm_sink_job_exists(wf) -> None:
    jobs = wf.get("jobs", {})
    assert "alarm-sink" in jobs


def test_alarm_sink_needs_probe(wf) -> None:
    alarm = wf["jobs"]["alarm-sink"]
    needs = alarm.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    assert "probe" in needs


def test_alarm_sink_runs_on_always(wf) -> None:
    alarm = wf["jobs"]["alarm-sink"]
    assert alarm.get("if", "").strip().lower() == "always()"


def test_probe_propagates_published_red_as_job_failure(wf) -> None:
    job = wf["jobs"]["probe"]
    steps = job["steps"]
    probe_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "probe"
    )
    probe = steps[probe_index]
    terminal = steps[-1]

    assert probe.get("continue-on-error") is True
    assert job["outputs"]["overall"] == "${{ steps.probe.outputs.overall }}"
    assert probe_index < len(steps) - 1
    assert terminal.get("env", {}).get("OVERALL") == (
        "${{ steps.probe.outputs.overall }}"
    )
    assert '"$OVERALL" = "red"' in terminal.get("run", "")
    assert "exit 1" in terminal.get("run", "")
    assert terminal.get("continue-on-error", False) is False


# ── Probe step calls verify_llm_binding.py ────────────────────────────


def test_probe_calls_verify_llm_binding(wf_text) -> None:
    assert "verify_llm_binding.py" in wf_text


def test_probe_passes_url_arg(wf_text) -> None:
    assert "--url" in wf_text


# ── Alarm sink: consecutive-red dedup ────────────────────────────────


def test_alarm_sink_uses_github_script(wf) -> None:
    steps = wf["jobs"]["alarm-sink"]["steps"]
    uses_vals = [s.get("uses", "") for s in steps]
    assert any("github-script" in u for u in uses_vals)


def test_alarm_sink_opens_issue_on_threshold(wf_text) -> None:
    assert "issues.create" in wf_text


def test_alarm_sink_closes_issue_on_recovery(wf_text) -> None:
    assert "state: 'closed'" in wf_text or '"closed"' in wf_text


def test_alarm_sink_first_red_does_not_open_issue(wf_text) -> None:
    # Pattern: first-red path logs without creating issue.
    assert "first-red" in wf_text or "not yet alarming" in wf_text


def test_alarm_issue_title_mentions_binding(wf_text) -> None:
    assert "binding" in wf_text.lower() or "endpoint_bound" in wf_text


# ── Concurrency ───────────────────────────────────────────────────────


def test_concurrency_group_is_scoped(wf) -> None:
    conc = wf.get("concurrency", {})
    group = conc.get("group", "")
    assert "llm-binding" in group


def test_concurrency_not_cancel_in_progress(wf) -> None:
    conc = wf.get("concurrency", {})
    assert conc.get("cancel-in-progress") is False


# ── Runbook ───────────────────────────────────────────────────────────


def test_runbook_exists() -> None:
    assert os.path.isfile(_RUNBOOK_PATH), f"missing: {_RUNBOOK_PATH}"


def test_runbook_mentions_llm_binding_canary() -> None:
    with open(_RUNBOOK_PATH, encoding="utf-8") as f:
        text = f.read()
    assert "llm-binding-canary" in text


def test_runbook_mentions_verify_llm_binding() -> None:
    with open(_RUNBOOK_PATH, encoding="utf-8") as f:
        text = f.read()
    assert "verify_llm_binding" in text


def test_runbook_lists_likely_causes() -> None:
    with open(_RUNBOOK_PATH, encoding="utf-8") as f:
        text = f.read()
    assert "OPENAI_API_KEY" in text or "codex" in text.lower()
