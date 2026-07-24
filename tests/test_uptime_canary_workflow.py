"""Executable regression tests for the uptime-canary alarm sink."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "uptime-canary.yml"
_NODE = shutil.which("node")


def _workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _alarm_script() -> str:
    step = next(
        step
        for step in _workflow()["jobs"]["alarm-sink"]["steps"]
        if step.get("id") == "gate"
    )
    return step["with"]["script"]


_HARNESS = r"""
const fs = require('fs');
const config = JSON.parse(process.env.TEST_CONFIG);
const script = fs.readFileSync(0, 'utf8');
const calls = [];
const outputs = {};
const warnings = [];
const summaries = [];

function record(name, result) {
  return async (args) => {
    calls.push({name, args});
    return result;
  };
}

const issues = {
  getLabel: async (args) => {
    calls.push({name: 'issues.getLabel', args});
    if (config.missingLabel) {
      const error = new Error('not found');
      error.status = 404;
      throw error;
    }
    return {data: {}};
  },
  createLabel: record('issues.createLabel', {data: {}}),
  listForRepo: record('issues.listForRepo', {data: config.openIssue ? [config.openIssue] : []}),
  createComment: record('issues.createComment', {data: {}}),
  create: record('issues.create', {data: {number: 99}}),
  update: record('issues.update', {data: {}}),
};
const github = {
  rest: {
    issues,
    actions: {
      listWorkflowRuns: record('actions.listWorkflowRuns', {
        data: {workflow_runs: config.priorRed ? [{id: 1, conclusion: 'failure'}] : []},
      }),
    },
  },
};
const core = {
  setOutput: (key, value) => { outputs[key] = value; },
  warning: (message) => { warnings.push(message); },
  summary: {
    addRaw: (message) => ({ write: async () => { summaries.push(message); } }),
  },
};
const context = {repo: {owner: 'owner', repo: 'repo'}};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
  .then(() => console.log('__RESULT__' + JSON.stringify({calls, outputs, warnings, summaries})))
  .catch((error) => {
    console.error(error.stack || error);
    process.exitCode = 1;
  });
"""


def _run_alarm_script(overall: str, **config: object) -> dict:
    if not _NODE:
        pytest.skip("node is required to execute the github-script alarm sink")
    result = subprocess.run(
        [_NODE, "-e", _HARNESS],
        input=_alarm_script(),
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env={
            **os.environ,
            "OVERALL": overall,
            "PROBE_STATUS": "",
            "PROBE_MSG": "",
            "LABEL": "p0-outage",
            "THRESHOLD": "2",
            "PROBE_URL": "https://tinyassets.io/mcp",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "2",
            "TEST_CONFIG": json.dumps(config),
        },
    )
    assert result.returncode == 0, result.stderr
    marker = next(
        line.removeprefix("__RESULT__")
        for line in result.stdout.splitlines()
        if line.startswith("__RESULT__")
    )
    return json.loads(marker)


@pytest.mark.parametrize("overall", ["", "unknown", "greenish"])
def test_unknown_result_makes_no_rest_calls_or_state_mutation(overall: str) -> None:
    observed = _run_alarm_script(overall, missingLabel=True)

    assert observed["calls"] == []
    assert observed["outputs"] == {
        "page_eligible": "false",
        "issue_number": "",
        "is_first_alarm": "false",
    }
    assert observed["warnings"]
    assert observed["summaries"]


def test_literal_green_recovers_only_an_existing_issue_without_creating_label() -> None:
    observed = _run_alarm_script("green", openIssue={"number": 42}, missingLabel=True)

    assert [call["name"] for call in observed["calls"]] == [
        "issues.listForRepo",
        "issues.createComment",
        "issues.update",
    ]
    assert observed["outputs"]["page_eligible"] == "false"


def test_red_keeps_label_threshold_and_paging_behavior() -> None:
    observed = _run_alarm_script("red", missingLabel=True, priorRed=True)

    assert [call["name"] for call in observed["calls"]] == [
        "issues.getLabel",
        "issues.createLabel",
        "issues.listForRepo",
        "actions.listWorkflowRuns",
        "issues.create",
    ]
    assert observed["outputs"] == {
        "page_eligible": "true",
        "issue_number": "99",
        "is_first_alarm": "true",
    }


def test_unknown_guard_and_literal_green_recovery_precede_mutation_logic() -> None:
    script = _alarm_script()

    defaults = script.index("core.setOutput('page_eligible', 'false')")
    unknown_guard = script.index("overall !== 'red' && overall !== 'green'")
    label_lookup = script.index("github.rest.issues.getLabel")
    green_guard = script.index("if (overall === 'green')")
    recovery = script.index("GREEN — RECOVERED")

    assert defaults < unknown_guard < label_lookup
    assert green_guard < recovery


def test_alarm_sink_stays_always_and_failed_deploy_still_skips_probe() -> None:
    workflow = _workflow()

    assert workflow["jobs"]["alarm-sink"]["if"].strip().lower() == "always()"
    assert workflow["jobs"]["probe"]["if"] == (
        "github.event_name != 'workflow_run' || "
        "github.event.workflow_run.conclusion == 'success'"
    )
    assert workflow["env"]["ALARM_THRESHOLD"] == 2


def test_wiki_probe_uses_gha_output_mode_and_preserves_diagnostic() -> None:
    workflow = _workflow()
    step = next(
        item
        for item in workflow["jobs"]["probe"]["steps"]
        if item.get("id") == "wiki_probe"
    )
    run = step["run"]

    assert "python scripts/wiki_canary.py" in run
    assert "--verbose" in run
    assert "--format gha" in run
    assert "output=$(" in run and "2>&1" in run
    assert "echo \"wiki_msg<<${_delim}\"" in run
    assert "echo \"$output\"" in run
