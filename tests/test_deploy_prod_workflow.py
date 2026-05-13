"""Tests for .github/workflows/deploy-prod.yml structure and DO secret names.

Covers:
  (a) YAML parses without error
  (b) workflow_dispatch trigger is present (manual test-deploy path)
  (c) workflow_run trigger fires on build-image success
  (d) Required DO secret names referenced (not legacy Hetzner names)
  (e) SSH key file and known_hosts use DO_DROPLET_HOST variable
  (f) Post-deploy canary step probes ONLY canonical URL (not direct)
  (g) Rollback step present and conditioned on failure
  (h) CF Access gate step blocks deploy on 200 (Access broken); advisory on tunnel-down
  (i) Optional Codex subscription auth bundle is synced without API-key fallback
  (j) Droplet disk pressure is pruned before image pull/restart
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
_WORKFLOW = _REPO / ".github" / "workflows" / "deploy-prod.yml"

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _triggers(wf: dict) -> dict:
    return wf.get(True, {}) or {}


# ---------------------------------------------------------------------------
# (a) YAML parses
# ---------------------------------------------------------------------------


def test_deploy_prod_yml_parses():
    _load()


# ---------------------------------------------------------------------------
# (b) workflow_dispatch present (manual deploy path)
# ---------------------------------------------------------------------------


def test_has_workflow_dispatch_trigger():
    wf = _load()
    triggers = _triggers(wf)
    assert "workflow_dispatch" in triggers, (
        "deploy-prod must have workflow_dispatch for manual invocation"
    )


def test_workflow_dispatch_has_image_tag_input():
    wf = _load()
    triggers = _triggers(wf)
    dispatch = triggers.get("workflow_dispatch") or {}
    inputs = (dispatch.get("inputs") or {})
    assert "image_tag" in inputs, "workflow_dispatch must expose image_tag input"


# ---------------------------------------------------------------------------
# (c) workflow_run trigger fires on build-image success
# ---------------------------------------------------------------------------


def test_has_workflow_run_trigger():
    wf = _load()
    triggers = _triggers(wf)
    assert "workflow_run" in triggers


def test_workflow_run_fires_on_build_image():
    wf = _load()
    triggers = _triggers(wf)
    wr = triggers.get("workflow_run") or {}
    workflows = wr.get("workflows", [])
    assert any("Build" in w for w in workflows), \
        "workflow_run must reference the build-image workflow"


# ---------------------------------------------------------------------------
# (d) DO secret names — not legacy Hetzner names
# ---------------------------------------------------------------------------


def test_do_droplet_host_secret_referenced():
    assert "DO_DROPLET_HOST" in _text()


def test_do_ssh_user_secret_referenced():
    assert "DO_SSH_USER" in _text()


def test_do_ssh_key_secret_referenced():
    assert "DO_SSH_KEY" in _text()


def test_codex_subscription_bundle_secret_referenced():
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in _text()


def test_no_legacy_hetzner_secrets():
    text = _text()
    assert "HETZNER_HOST" not in text, "Legacy HETZNER_HOST still in deploy-prod.yml"
    assert "HETZNER_SSH_USER" not in text, "Legacy HETZNER_SSH_USER still in deploy-prod.yml"
    assert "HETZNER_SSH_KEY" not in text, "Legacy HETZNER_SSH_KEY still in deploy-prod.yml"


# ---------------------------------------------------------------------------
# (e) SSH step uses DO_DROPLET_HOST
# ---------------------------------------------------------------------------


def test_ssh_keyscan_uses_do_droplet_host():
    assert "DO_DROPLET_HOST" in _text()
    assert "hetzner_deploy" not in _text(), "Stale hetzner_deploy key filename still in workflow"


# ---------------------------------------------------------------------------
# (f) Post-deploy canary step present
# ---------------------------------------------------------------------------


def _steps(wf: dict) -> list[dict]:
    return wf.get("jobs", {}).get("deploy", {}).get("steps", [])


def test_post_deploy_canary_step_present():
    wf = _load()
    names = [s.get("name", "") for s in _steps(wf)]
    assert any("canary" in (n or "").lower() for n in names), \
        "deploy job must have a post-deploy canary step"


def test_canary_step_only_probes_canonical():
    """Canary must NOT probe the direct URL (returns 403 after CF Access cutover)."""
    wf = _load()
    for step in _steps(wf):
        name = step.get("name", "") or ""
        if "canary" in name.lower() and "access" not in name.lower():
            run_script = step.get("run", "") or ""
            assert "DIRECT_URL" not in run_script, (
                f"Canary step '{name}' must not probe DIRECT_URL — it correctly "
                "returns 403 after CF Access Option-1 cutover. Only canonical URL is valid."
            )
            assert "CANARY_URL" in run_script, (
                f"Canary step '{name}' must probe CANARY_URL (canonical)"
            )
            return
    pytest.fail("Post-deploy canary step not found")


def test_access_gate_step_present():
    """A separate advisory step must verify the direct URL still returns 403/401."""
    wf = _load()
    steps = _steps(wf)
    access_steps = [s for s in steps if "access" in (s.get("name") or "").lower()]
    assert access_steps, (
        "deploy job must have a CF Access gate verification step "
        "(expects 403/401 from direct URL — advisory, not blocking)"
    )


def test_access_gate_blocks_on_200():
    """Access gate step must exit 1 when direct URL returns 200 (CF Access broken),
    but must NOT unconditionally exit 1 — tunnel-down (000) is advisory only."""
    wf = _load()
    for step in _steps(wf):
        if "access" in (step.get("name") or "").lower():
            run_script = step.get("run", "") or ""
            assert "exit 1" in run_script, (
                "Access gate step must exit 1 when direct URL returns 200 "
                "(CF Access disabled — this is a deploy-blocking security failure)"
            )
            # The step must NOT be unconditionally blocking — tunnel-down (000)
            # is advisory. Verify exit 1 is guarded (inside an if-block).
            assert run_script.count("exit 1") < run_script.count("if ["), (
                "Access gate step exit 1 must be inside a conditional — "
                "tunnel-down (000) case must be advisory, not blocking"
            )
            return
    pytest.fail("Access gate step not found")


# ---------------------------------------------------------------------------
# (g) Rollback step present and conditioned on failure
# ---------------------------------------------------------------------------


def test_rollback_step_present():
    wf = _load()
    names = [s.get("name", "") for s in _steps(wf)]
    assert any("rollback on failure" in (n or "").lower() for n in names), \
        "deploy job must have a 'Rollback on failure' step"


def test_rollback_conditioned_on_failure():
    wf = _load()
    for step in _steps(wf):
        if "rollback on failure" in (step.get("name") or "").lower():
            cond = step.get("if", "")
            assert "failure" in cond, "rollback step must be conditioned on failure()"
            return
    pytest.fail("'Rollback on failure' step not found")


# ---------------------------------------------------------------------------
# (i) Codex subscription auth sync
# ---------------------------------------------------------------------------


def test_deploy_syncs_codex_subscription_bundle_with_helper():
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None, "deploy job must have a deploy step"
    run_script = deploy_step.get("run", "") or ""
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in run_script
    assert "install-workflow-env.sh set WORKFLOW_CODEX_AUTH_JSON_B64" in run_script
    assert "install-workflow-env.sh set WORKFLOW_ALLOW_API_KEY_PROVIDERS" in run_script
    assert "OPENAI_API_KEY" not in run_script, (
        "deploy must not recover the public daemon by syncing API-key writer auth"
    )


def test_deploy_syncs_runtime_compose_and_systemd_files():
    wf = _load()
    sync_step = next(
        (s for s in _steps(wf) if s.get("name") == "Sync runtime deploy files"),
        None,
    )
    assert sync_step is not None, "deploy must sync runtime compose files"
    run_script = sync_step.get("run", "") or ""
    assert "deploy/compose.yml" in run_script
    assert "/opt/workflow/compose.yml" in run_script
    assert "/opt/workflow/deploy/compose.yml" in run_script
    assert "deploy/workflow-daemon.service" in run_script
    assert "/etc/systemd/system/workflow-daemon.service" in run_script
    assert "systemctl daemon-reload" in run_script
    assert "vector-entrypoint.sh" in run_script


# ---------------------------------------------------------------------------
# (j) Disk preflight before image pull/restart
# ---------------------------------------------------------------------------


def test_disk_preflight_runs_before_deploy_image_pull():
    wf = _load()
    steps = _steps(wf)
    names = [s.get("name", "") for s in steps]
    preflight_idx = next(
        i for i, name in enumerate(names)
        if name == "Preflight droplet disk before image pull"
    )
    deploy_idx = next(
        i for i, step in enumerate(steps)
        if step.get("id") == "deploy"
    )

    assert preflight_idx < deploy_idx, (
        "disk preflight must happen before WORKFLOW_IMAGE is changed, "
        "docker pull runs, or systemd restart can take the live daemon down"
    )


def test_disk_preflight_prunes_disposable_state_and_fails_before_restart():
    wf = _load()
    step = next(
        s for s in _steps(wf)
        if s.get("name") == "Preflight droplet disk before image pull"
    )
    run_script = step.get("run", "") or ""

    assert "df -h / /var/lib/docker /data" in run_script
    assert "docker system prune -af" in run_script
    assert "docker builder prune -af" in run_script
    assert "journalctl --vacuum-time=3d" in run_script
    assert "fail_threshold=90" in run_script
    assert "refusing deploy before image pull/restart" in run_script


def test_deploy_scrubs_stdio_only_workflow_universe_from_cloud_env():
    wf = _load()
    scrub_step = next(
        (s for s in _steps(wf) if s.get("name") == "Scrub stale cloud env overrides"),
        None,
    )
    assert scrub_step is not None
    run_script = scrub_step.get("run", "") or ""
    assert "delete WORKFLOW_WIKI_PATH WORKFLOW_UNIVERSE" in run_script


def test_deploy_verifies_cloud_worker_running():
    wf = _load()
    worker_step = next(
        (s for s in _steps(wf) if s.get("name") == "Verify cloud worker is running"),
        None,
    )
    assert worker_step is not None, "deploy must verify workflow-worker is running"
    run_script = worker_step.get("run", "") or ""
    assert "workflow-worker" in run_script
    assert "docker inspect" in run_script
    assert "State.Running" in run_script
    assert "for i in $(seq 1 30)" in run_script
    assert "sleep 2" in run_script
    assert "exit 1" in run_script


def test_deploy_rejects_cloud_worker_workflow_universe_override():
    wf = _load()
    worker_step = next(
        (s for s in _steps(wf) if s.get("name") == "Verify cloud worker is running"),
        None,
    )
    assert worker_step is not None
    run_script = worker_step.get("run", "") or ""
    assert "grep -q '^WORKFLOW_UNIVERSE='" in run_script
    assert "stdio-only override" in run_script
    assert "_resolve_universe_path" in run_script


def test_deploy_verifies_llm_binding_when_codex_auth_is_synced():
    wf = _load()
    for step in _steps(wf):
        if "Verify subscription LLM binding" in (step.get("name") or ""):
            assert "HAS_CODEX_AUTH_BUNDLE" in str(step.get("if", ""))
            run_script = step.get("run", "") or ""
            assert "verify_llm_binding.py" in run_script
            assert "--require-sandbox" in run_script
            assert "--retries 12" in run_script
            assert "--retry-delay 10" in run_script
            return
    pytest.fail("deploy must verify LLM binding when it syncs Codex subscription auth")


def test_deploy_requires_llm_binding_even_without_visible_deploy_secret():
    wf = _load()
    step_name = "Report subscription LLM binding when no deploy auth bundle is configured"
    step = next(
        (
            s for s in _steps(wf)
            if s.get("name") == step_name
        ),
        None,
    )
    assert step is not None
    run_script = step.get("run", "") or ""
    assert "verify_llm_binding.py" in run_script
    assert "--require-sandbox" in run_script
    assert "--retries 12" in run_script
    assert "--retry-delay 10" in run_script
    assert "::warning::No deploy-visible WORKFLOW_CODEX_AUTH_JSON_B64" not in run_script
