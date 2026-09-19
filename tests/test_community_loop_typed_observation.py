"""Exact-attempt canary receipts, never whole-workflow success, attest health."""

import datetime as dt
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts import community_loop_watch as watch

NOW = dt.datetime(2026, 9, 19, 7, 0, tzinfo=dt.timezone.utc)
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def observation(monkeypatch):
    run = dict(id=123, run_attempt=2, status="completed", conclusion="success",
               head_sha="a" * 40, head_branch="main", event="schedule",
               path=".github/workflows/uptime-canary.yml",
               head_repository={"full_name": "owner/repo"},
               created_at="2026-09-19T06:55:00Z", html_url="https://example.test/run/123")
    job = dict(name="probe", run_id=123, run_attempt=2, head_sha="a" * 40,
               status="completed", completed_at="2026-09-19T06:56:00Z", steps=[
                   dict(name="Layer-1 measured red v1", status="completed", conclusion="skipped"),
                   dict(name="Layer-1 measured green v1", status="completed", conclusion="skipped"),
               ])
    state = dict(run=run, jobs={"total_count": 1, "jobs": [job]}, reread=deepcopy(run), calls=[])
    monkeypatch.setattr(watch, "_latest_workflow_run", lambda *a, **kw: state["run"])

    def get(url, **kwargs):
        state["calls"].append(url)
        if "jobs?" in url:
            assert "/runs/123/attempts/2/jobs?" in url
            return state["jobs"], None
        assert url.endswith("/runs/123")
        return state["reread"], None

    monkeypatch.setattr(watch, "_gh_get_url", get)
    return state


def stage():
    return watch.workflow_stage(
        "Observation canary", "owner/repo", "uptime-canary.yml", api="https://api.test",
        token=None, timeout=1, now=NOW, max_age_min=90,
    )


def test_successful_unknown_classification_is_not_green(observation):
    assert stage()["status"] == "unknown"


@pytest.mark.parametrize("color", ["red", "green"])
def test_only_exact_positive_receipt_establishes_measured_state(observation, color):
    index, conclusion = (0, "failure") if color == "red" else (1, "success")
    observation["jobs"]["jobs"][0]["steps"][index]["conclusion"] = conclusion
    observation["run"]["conclusion"] = "failure" if color == "red" else "success"
    assert stage()["status"] == color
    assert len(observation["calls"]) == 2


@pytest.mark.parametrize("mutation", [
    "no_jobs", "truncated_jobs", "duplicate_job", "wrong_run", "wrong_attempt", "wrong_head",
    "wrong_branch", "wrong_source", "wrong_repo", "future_run", "old_job", "future_job",
    "missing_red", "duplicate_green", "conflicting_receipts", "malformed_step", "rerun",
    "bad_time", "null_repo", "incomplete_job", "invalid_head", "bad_conclusion",
    "stale_wrong_source",
])
def test_incomplete_or_ambiguous_green_cannot_attest_recovery(observation, mutation):
    job = observation["jobs"]["jobs"][0]
    job["steps"][1]["conclusion"] = "success"
    if mutation == "no_jobs":
        observation["jobs"] = {}
    elif mutation == "truncated_jobs":
        observation["jobs"]["total_count"] = 101
    elif mutation == "duplicate_job":
        observation["jobs"]["jobs"].append(deepcopy(job))
        observation["jobs"]["total_count"] = 2
    elif mutation in {"wrong_run", "wrong_attempt", "wrong_head"}:
        job[{"wrong_run": "run_id", "wrong_attempt": "run_attempt", "wrong_head": "head_sha"}[
            mutation]] = "wrong"
    elif mutation == "wrong_branch":
        observation["run"]["head_branch"] = "other"
    elif mutation == "wrong_source":
        observation["run"]["path"] = ".github/workflows/other.yml"
    elif mutation == "wrong_repo":
        observation["run"]["head_repository"] = {"full_name": "foreign/repo"}
    elif mutation == "future_run":
        observation["run"]["created_at"] = "2026-09-20T00:00:00Z"
    elif mutation in {"old_job", "future_job"}:
        job["completed_at"] = (
            "2026-09-19T00:00:00Z" if mutation == "old_job" else "2026-09-20T00:00:00Z"
        )
    elif mutation == "missing_red":
        job["steps"].pop(0)
    elif mutation == "duplicate_green":
        job["steps"].append(deepcopy(job["steps"][1]))
    elif mutation == "conflicting_receipts":
        job["steps"][0]["conclusion"] = "failure"
    elif mutation == "malformed_step":
        job["steps"].append(None)
    elif mutation == "bad_time":
        observation["run"]["created_at"] = 12
    elif mutation == "null_repo":
        observation["run"]["head_repository"] = None
    elif mutation == "incomplete_job":
        job["status"] = "in_progress"
    elif mutation == "invalid_head":
        observation["run"]["head_sha"] = "z" * 40
    elif mutation == "bad_conclusion":
        job["steps"][1]["conclusion"] = []
    elif mutation == "stale_wrong_source":
        observation["run"].update(path="other.yml", created_at="2026-09-18T00:00:00Z")
    else:
        observation["reread"]["run_attempt"] = 3
    assert stage()["status"] == "unknown"


def test_unrelated_workflow_failure_is_not_a_measured_canary_red(observation):
    observation["run"]["conclusion"] = "failure"
    assert stage()["status"] == "unknown"


def test_receipt_read_failure_is_visible_unknown(observation, monkeypatch):
    def fail(*args, **kwargs):
        raise watch.WatchError("unavailable")
    monkeypatch.setattr(watch, "_gh_get_url", fail)
    result = stage()
    assert result["status"] == "unknown"
    assert "could not be read" in result["summary"]


def test_legacy_positive_red_remains_measured_red(observation):
    steps = observation["jobs"]["jobs"][0]["steps"]
    steps.pop(1)
    steps[0]["conclusion"] = "failure"
    assert stage()["status"] == "red"


def test_other_workflow_status_does_not_require_canary_receipts(observation):
    result = watch.workflow_stage(
        "Production deploy", "owner/repo", "deploy-prod.yml", api="https://api.test",
        token=None, timeout=1, now=NOW, max_age_min=None,
    )
    assert result["status"] == "green"
    assert not observation["calls"]


def test_unknown_does_not_hide_another_measured_red():
    assert watch.classify([{"status": "unknown"}, {"status": "red"}]) == "red"


@pytest.mark.parametrize("overall", ["unknown", "yellow", "", "unexpected", "red", "green"])
def test_real_alarm_script_only_literal_green_recovers(overall):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node executes the real alarm script")
    workflow = yaml.safe_load((REPO / ".github/workflows/community-loop-watch.yml").read_text(
        encoding="utf-8"))
    script = workflow["jobs"]["alarm-sink"]["steps"][0]["with"]["script"]
    harness = r"""
const fs = require('fs'); const script = fs.readFileSync(0, 'utf8'); const calls = [];
const issues = new Proxy({}, {get: (_, name) => async (args) => {
  calls.push({name, args});
  return {data: name === 'listForRepo' ? [{number: 7, title: 'Community loop watch red'}] : {}};
}});
const actions = {createWorkflowDispatch: async (args) => {calls.push({name:'dispatch',args});}};
const github = {rest: {issues, actions}};
const context = {repo: {owner:'owner',repo:'repo'},payload:{inputs:{}}};
const core = {warning:()=>{}};
new (Object.getPrototypeOf(async function(){}).constructor)('github','context','core',script)(
  github,context,core).then(()=>console.log(JSON.stringify(calls))).catch(e=>{console.error(e);process.exit(1)});
"""
    result = subprocess.run([node, "-e", harness], input=script, text=True, encoding="utf-8",
                            capture_output=True, timeout=10, env={**os.environ,
                            "OVERALL": overall, "LABEL": "community-loop-red",
                            "PROBE_MSG": '{"stages":[]}'})
    assert result.returncode == 0, result.stderr
    calls = json.loads(result.stdout.strip().splitlines()[-1])
    if overall not in {"red", "green"}:
        assert calls == []
    elif overall == "red":
        assert any(call["name"] == "createComment" for call in calls)
        assert not any(call["name"] == "update" for call in calls)
    else:
        assert any(call["name"] == "update" and call["args"]["state"] == "closed" for call in calls)


def test_positive_green_receipt_is_emitted_only_on_measured_green():
    workflow = yaml.safe_load((REPO / ".github/workflows/uptime-canary.yml").read_text(
        encoding="utf-8"))
    marker = next(step for step in workflow["jobs"]["probe"]["steps"]
                  if step.get("name") == "Layer-1 measured green v1")
    assert marker["if"] == "steps.combine.outputs.overall == 'green'"
    assert marker["run"] == "exit 0"
    assert not marker.get("continue-on-error")
