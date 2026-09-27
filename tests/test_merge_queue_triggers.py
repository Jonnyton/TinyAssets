"""Every required check must report in the merge queue.

A merge queue waits for each required status check on the merge-group commit.
A required check whose workflow has no `merge_group` trigger never reports
there, so GitHub holds every queued PR until the status-check timeout and then
ejects it. The required contexts on `main` are pinned below. Adding one
without a `merge_group` trigger fails here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

#: Branch-protection context -> (workflow file, job id).
REQUIRED_CONTEXTS = {
    "Diff scope declared": ("pr-scope-guard.yml", "scope"),
    "required-tests": ("tests.yml", "required-tests"),
    "slow-tests": ("tests.yml", "slow-tests"),
    "invariants": ("invariants.yml", "invariants"),
}

_GATE_ONLY = "github.event_name == 'pull_request_target'"
_QUEUE_ONLY = "github.event_name == 'merge_group'"


def _load(name: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def _if(node: dict) -> str:
    text = " ".join(str(node.get("if", "")).split())
    if text.startswith("${{") and text.endswith("}}"):
        text = " ".join(text[3:-2].split())
    return text


def test_every_required_context_runs_on_merge_group() -> None:
    for context, (name, job_id) in REQUIRED_CONTEXTS.items():
        wf = _load(name)
        triggers = _triggers(wf)
        assert "merge_group" in triggers, f"{name} ({context!r}) lacks merge_group"
        types = (triggers["merge_group"] or {}).get("types", ["checks_requested"])
        assert "checks_requested" in types, name
        job = wf["jobs"][job_id]
        assert job.get("name", job_id) == context, (
            f"{name}:{job_id} must report the protected context {context!r}"
        )
        # A job-level `if:` can skip the job, and branch protection counts a
        # skipped required check as passed. `always()` is the one condition
        # allowed: it cannot evaluate false (the sharded `required-tests`
        # aggregate needs it to report when a shard fails).
        assert _if(job) in ("", "always()"), (
            f"{name}:{job_id} must not carry a job-level if: that can skip it; "
            f"got {_if(job)!r}"
        )


def test_scope_guard_gate_steps_run_only_on_the_pull_request() -> None:
    """The queue step passes; every other step is the gate and runs on the PR.

    Pinned exactly. A gate step whose condition also admitted merge_group would
    fail there: the event carries no PR number, head, body or labels.
    """
    steps = _load("pr-scope-guard.yml")["jobs"]["scope"]["steps"]
    queue_steps = [s for s in steps if _if(s) == _QUEUE_ONLY]
    gate_steps = [s for s in steps if s not in queue_steps]
    assert len(queue_steps) == 1
    assert "exit 1" not in queue_steps[0]["run"]
    assert len(gate_steps) >= 3
    for step in gate_steps:
        assert _if(step) == _GATE_ONLY, (
            f"scope-guard step {step.get('name')!r} must run only on "
            f"pull_request_target; got if={_if(step)!r}"
        )


def test_scope_guard_queue_entries_do_not_cancel_each_other() -> None:
    """A merge_group event has no PR number; the group must still be unique.

    Keyed on the PR number alone, every queue entry lands in the group
    `pr-scope-guard-`, cancel-in-progress cancels all but the newest, and a
    cancelled required check ejects its PR from the queue.
    """
    group = str(_load("pr-scope-guard.yml")["concurrency"]["group"])
    assert "github.event.merge_group.head_ref" in group
