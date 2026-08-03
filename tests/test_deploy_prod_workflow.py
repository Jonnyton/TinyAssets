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

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.retire_cheat_loop_deploy_fence import RECOVERY_SCRIPT_PATH
from scripts.sanitize_startup_diagnostics import (
    STATE_SEPARATOR,
    sanitize_candidate_state,
)

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "deploy-prod.yml"
_RECOVERY_OVERRIDE = _REPO / "deploy" / "recovery-restart-no.yml"

pytestmark = pytest.mark.skipif(not _YAML_AVAILABLE, reason="pyyaml not installed")


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
    inputs = dispatch.get("inputs") or {}
    assert "image_tag" in inputs, "workflow_dispatch must expose image_tag input"


def test_workflow_dispatch_has_explicit_request_hmac_rotation_input():
    wf = _load()
    inputs = (_triggers(wf).get("workflow_dispatch") or {}).get("inputs") or {}
    rotation = inputs["rotate_request_idempotency_hmac"]
    assert rotation.get("type") == "boolean"
    assert rotation.get("default") is False
    assert "exposed" in str(rotation.get("description", "")).lower()


def test_manual_unsafe_fence_recovery_is_separate_and_source_bound():
    wf = _load()
    inputs = (_triggers(wf).get("workflow_dispatch") or {}).get("inputs") or {}
    assert "unsafe_fence_source_run_id" in inputs
    assert "<run_id>-<attempt>" in str(
        inputs["unsafe_fence_source_run_id"].get("description", "")
    )
    recovery = wf["jobs"]["recover-unsafe"]
    assert "workflow_dispatch" in str(recovery.get("if", ""))
    checkout = recovery["steps"][0]
    assert checkout.get("uses") == "actions/checkout@v4"
    assert checkout.get("with", {}).get("fetch-depth") == 0
    step = _step_named({"jobs": {"deploy": recovery}}, "Recover canonical unsafe fence")
    script = str(step.get("run", ""))
    assert "recover-unsafe --source-run-id" in script
    assert "[A-Za-z0-9._-]{1,128}" in script
    assert step.get("env", {}).get("SOURCE_RUN_ID") == (
        "${{ inputs.unsafe_fence_source_run_id }}"
    )
    assert "inputs.unsafe_fence_source_run_id" not in script
    assert " --image-ref " in script
    assert " --revision " in script
    assert " --expected-script-sha256 " in script
    assert "sha256sum scripts/retire_cheat_loop_deploy_fence.py" in script
    assert "sha256sum -c -" in script
    assert "set -euo pipefail" in script
    assert "deploy/recovery-restart-no.yml" in script
    assert "deploy/tinyassets-recovery-reconcile.service" in script
    assert "systemctl enable tinyassets-recovery-reconcile.service" in script
    reconcile_unit = (
        Path("deploy/tinyassets-recovery-reconcile.service")
        .read_text(encoding="utf-8")
    )
    assert "reconcile-recovery-on-boot" in reconcile_unit
    assert "After=docker.service" in reconcile_unit
    for unit in (
        "daemon-watchdog.timer",
        "tinyassets-watchdog.timer",
        "tinyassets-autoheal.timer",
        "tinyassets-daemon.service",
    ):
        assert unit in reconcile_unit
    recovery_script_path = RECOVERY_SCRIPT_PATH.as_posix()
    assert recovery_script_path in script
    assert (
        f"/tmp/retire-cheat-loop-deploy-fence.py {recovery_script_path}"
        in script
    )
    assert "recovery_pending_canary" not in script
    resolve = _step_named(
        {"jobs": {"deploy": recovery}}, "Resolve unsafe recovery image"
    )
    resolve_script = str(resolve.get("run", ""))
    assert "docker buildx imagetools inspect" in resolve_script
    assert "org.opencontainers.image.revision" in resolve_script
    assert "35da9d4fc1a1fc51d3db56bf5d1627691f54d894" in resolve_script
    assert "git merge-base --is-ancestor" in resolve_script
    refence = _step_named(
        {"jobs": {"deploy": recovery}}, "Re-fence failed recovery"
    )
    refence_script = str(refence.get("run", ""))
    assert "refence-recovery --source-run-id" in refence_script
    assert "[A-Za-z0-9._-]{1,128}" in refence_script
    assert "quiesce-unsafe" not in refence_script
    assert "cancelled()" in str(refence.get("if", ""))
    finalize = _step_named(
        {"jobs": {"deploy": recovery}},
        "Finalize canonical unsafe-fence recovery",
    )
    assert "finalize-recovery --source-run-id" in str(finalize.get("run", ""))
    step_names = [str(item.get("name", "")) for item in recovery["steps"]]
    pull_index = step_names.index("Pull recovery image on production host")
    recover_index = step_names.index("Recover canonical unsafe fence")
    assert pull_index < recover_index
    host_pull = _step_named(
        {"jobs": {"deploy": recovery}},
        "Pull recovery image on production host",
    )
    host_pull_script = str(host_pull.get("run", ""))
    assert host_pull.get("env", {}).get("RECOVERY_IMAGE_REF") == (
        "${{ steps.recovery-image.outputs.image_ref }}"
    )
    assert "sudo docker pull '${RECOVERY_IMAGE_REF}'" in host_pull_script
    assert step_names.index("Recovery canonical MCP canary") < step_names.index(
        "Finalize canonical unsafe-fence recovery"
    )
    assert step_names.index("Recovery exact-seven surface assertion") < step_names.index(
        "Finalize canonical unsafe-fence recovery"
    )
    assert "inputs.unsafe_fence_source_run_id == ''" in str(
        wf["jobs"]["deploy"].get("if", "")
    )


def test_recovery_override_fences_writers_and_fixed_name_sidecars():
    override = yaml.safe_load(_RECOVERY_OVERRIDE.read_text(encoding="utf-8"))
    services = override["services"]
    assert set(services) == {
        "daemon",
        "worker",
        "worker-codex-2",
        "worker-claude-1",
        "worker-claude-2",
        "cloudflared",
        "logs",
    }
    assert all(service.get("restart") == "no" for service in services.values())


def test_deploy_resolves_image_to_digest_and_never_latest():
    text = _text()
    assert "image_ref=" in text
    assert "docker buildx imagetools inspect" in text
    assert 'tag="latest"' not in text
    assert ":latest" not in text, "deploy-prod must not use :latest for deploy or rollback targets"


def test_manual_image_tag_is_env_bound_and_validated_before_use():
    wf = _load()
    step = _step_named(wf, "Resolve image tag")
    run_script = step.get("run", "") or ""
    env = step.get("env") or {}

    assert env.get("REQUESTED_IMAGE_TAG") == "${{ inputs.image_tag }}"
    assert "${{ inputs.image_tag }}" not in run_script, (
        "workflow input must not be interpolated into executable shell source"
    )
    assert "[A-Za-z0-9_][A-Za-z0-9._-]{0,127}" in run_script
    assert "refusing invalid OCI image tag" in run_script


def test_resolved_digest_is_canonical_before_any_host_write():
    wf = _load()
    step = _step_named(wf, "Resolve image tag")
    run_script = step.get("run", "") or ""

    assert "sha256:[0-9a-f]{64}" in run_script
    assert "refusing non-canonical immutable image digest" in run_script


def test_capture_previous_uses_configured_and_running_digest_observations():
    wf = _load()
    step = _step_named(wf, "Capture previous image tag (for rollback)")
    run_script = step.get("run", "") or ""

    assert "docker inspect --type container" in run_script
    assert "{{.Image}}" in run_script
    assert "tinyassets-daemon" in run_script
    assert "docker image inspect" in run_script
    assert "{{json .RepoDigests}}" in run_script
    assert "configured_image_ref=" in run_script
    assert "running_image_ref=" in run_script
    assert "previous=" in run_script
    assert "docker buildx imagetools inspect" not in run_script, (
        "a mutable configured tag cannot be converted into rollback proof"
    )


def test_capture_previous_transports_bounded_prior_receipt_read_only():
    wf = _load()
    step = _step_named(wf, "Capture previous image tag (for rollback)")
    run_script = step.get("run", "") or ""

    assert "docker volume inspect tinyassets-data" in run_script
    assert "head -c 65537" in run_script
    assert "base64 -w0" in run_script
    assert "prior_receipt_b64=" in run_script
    for forbidden in (" install ", " mv ", " rm ", "set TINYASSETS_IMAGE"):
        assert forbidden not in run_script, (
            "pre-mutation capture must remain read-only on the production host"
        )


def test_capture_previous_does_not_emit_untrusted_image_labels_as_outputs():
    wf = _load()
    step = _step_named(wf, "Capture previous image tag (for rollback)")
    run_script = step.get("run", "") or ""

    assert "previous_active_revision_label=" not in run_script
    assert "active_revision_label" not in run_script
    assert "org.opencontainers.image.revision" not in run_script


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
    assert any("Build" in w for w in workflows), (
        "workflow_run must reference the build-image workflow"
    )


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
    assert "TINYASSETS_CODEX_AUTH_JSON_B64" in _text()


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


def _step_named(wf: dict, name: str) -> dict:
    step = next(
        (candidate for candidate in _steps(wf) if candidate.get("name") == name),
        None,
    )
    assert step is not None, f"deploy job must include a '{name}' step"
    return step


def _step_with_run_token(wf: dict, token: str) -> dict:
    step = next(
        (candidate for candidate in _steps(wf) if token in (candidate.get("run", "") or "")),
        None,
    )
    assert step is not None, f"deploy job must include a run step containing {token!r}"
    return step


def _previous_executable_line(lines: list[str], before: int) -> str:
    for line in reversed(lines[:before]):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def test_post_deploy_canary_step_present():
    wf = _load()
    names = [s.get("name", "") for s in _steps(wf)]
    assert any("canary" in (n or "").lower() for n in names), (
        "deploy job must have a post-deploy canary step"
    )


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
    assert any("rollback on failure" in (n or "").lower() for n in names), (
        "deploy job must have a 'Rollback on failure' step"
    )


def test_failed_candidate_diagnostics_are_preserved_before_rollback():
    wf = _load()
    steps = _steps(wf)
    health = _step_named(wf, "Wait for daemon health")
    capture = _step_named(wf, "Capture failed candidate startup diagnostics")
    upload = _step_named(wf, "Upload failed candidate startup diagnostics")
    rollback = _step_named(wf, "Rollback on failure")
    cleanup = _step_named(wf, "Transitional task 2.1 restore restart racers when safe")
    terminal = _step_named(wf, "Publish release-state receipt")

    assert steps.index(health) < steps.index(capture) < steps.index(rollback)
    assert steps.index(rollback) < steps.index(cleanup) < steps.index(terminal)
    assert steps.index(terminal) < steps.index(upload)
    assert health.get("id") == "candidate_health"
    assert capture.get("id") == "candidate_diagnostics"
    capture_condition = str(capture.get("if", "")).strip()
    assert capture_condition == (
        "${{ always() && steps.deploy.outputs.image_mutation_started == 'true' "
        "&& (failure() || cancelled()) }}"
    )
    assert "always()" in capture_condition
    assert "failure()" in capture_condition
    assert "cancelled()" in capture_condition
    assert "steps.deploy.outputs.image_mutation_started == 'true'" in capture_condition
    assert "steps.candidate_health.outcome" not in capture_condition, (
        "post-mutation deploy and env-assert failures skip health but still "
        "need identity-bound diagnostics"
    )
    upload_condition = str(upload.get("if", "")).strip()
    assert upload_condition == (
        "${{ always() && steps.candidate_diagnostics.outcome == 'success' "
        "&& steps.terminal.outputs.terminal_receipt_result == 'published' "
        "&& (steps.stop-writer-cleanup.outputs.cleanup_restored == 'true' "
        "|| steps.stop-writer-cleanup.outputs.cleanup_safely_fenced == 'true') }}"
    )
    assert "always()" in upload_condition
    assert "steps.candidate_diagnostics.outcome == 'success'" in upload_condition
    assert (
        "steps.terminal.outputs.terminal_receipt_result == 'published'"
        in upload_condition
    )
    assert (
        "steps.stop-writer-cleanup.outputs.cleanup_restored == 'true'"
        in upload_condition
    )
    assert (
        "steps.stop-writer-cleanup.outputs.cleanup_safely_fenced == 'true'"
        in upload_condition
    )
    assert "steps.candidate_health.outcome" not in upload_condition

    capture_script = str(capture.get("run", ""))
    assert "docker inspect --type container tinyassets-daemon" in capture_script
    assert "docker logs --tail 200 tinyassets-daemon" in capture_script
    assert "tail -c 131072" in capture_script
    assert "scripts/sanitize_startup_diagnostics.py" in capture_script
    assert "ConnectTimeout=10" in capture_script
    assert "ServerAliveInterval=5" in capture_script
    assert "ServerAliveCountMax=2" in capture_script
    assert capture_script.count("timeout 25s ssh") >= 2
    assert capture_script.count("timeout 15s sudo docker") >= 2
    assert "head -c 16385" in capture_script
    assert 'rm -f "${raw_log}"' in capture_script
    assert "TARGET_REVISION" in (capture.get("env") or {})
    assert "TARGET_IMAGE_REF" in (capture.get("env") or {})
    assert "org.opencontainers.image.revision" in capture_script
    assert ".Config.Image" in capture_script
    assert r"\t" not in capture_script
    state_template_match = re.search(r"--format '([^']+)'", capture_script)
    assert state_template_match is not None
    state_template = state_template_match.group(1)
    expected_state_template = STATE_SEPARATOR.join(
        (
            "{{.State.Status}}",
            "{{.State.Running}}",
            "{{.State.Restarting}}",
            "{{.State.ExitCode}}",
            "{{.State.OOMKilled}}",
            "{{if .State.Health}}{{.State.Health.Status}}{{end}}",
            r'{{index .Config.Labels \"org.opencontainers.image.revision\"}}',
            "{{.Config.Image}}",
            "{{json .State.Error}}",
        )
    )
    assert state_template == expected_state_template
    assert state_template.count(STATE_SEPARATOR) == 8
    revision = "a" * 40
    image_ref = f"ghcr.io/jonnyton/tinyassets-daemon@sha256:{'b' * 64}"
    rendered_state = STATE_SEPARATOR.join(
        (
            "exited",
            "false",
            "false",
            "1",
            "false",
            "unhealthy",
            revision,
            image_ref,
            json.dumps(""),
        )
    ).encode()
    assert (
        sanitize_candidate_state(
            rendered_state,
            target_revision=revision,
            target_image_ref=image_ref,
        )["candidate_identity_match"]
        is True
    )
    assert "candidate_identity_match" in capture_script
    assert "--state" in capture_script
    assert '--target-revision "${TARGET_REVISION}"' in capture_script
    assert '--target-image-ref "${TARGET_IMAGE_REF}"' in capture_script
    assert 'if [ "${candidate_identity_match}" = "true" ]' in capture_script
    assert "GITHUB_SHA" not in capture_script
    assert "docker compose" not in capture_script
    assert "compose-ps" not in capture_script
    assert "daemon.log" not in capture_script
    assert "/etc/tinyassets/env" not in capture_script
    assert ".Config.Env" not in capture_script
    assert "{{json .State.Error}}" in capture_script

    upload_with = upload.get("with") or {}
    assert (
        upload.get("uses")
        == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert "actions/upload-artifact@v4" not in _text()
    assert _text().count(
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    ) == 3
    assert upload_with.get("if-no-files-found") == "error"
    assert 0 < int(upload_with["retention-days"]) <= 7


def test_rollback_runs_always_and_eligibility_keys_to_image_marker():
    wf = _load()
    step = _step_named(wf, "Rollback on failure")
    cond = str(step.get("if", ""))
    step_env = step.get("env") or {}
    run_script = step.get("run", "") or ""

    assert cond.strip() == "always()", (
        "rollback must always run so pre-host, pre-image, success, and required "
        "rollback paths all publish a bounded result tuple"
    )
    assert "failure()" not in cond
    assert "steps.prev.outputs.previous != ''" not in cond
    assert "image_mutation_started" in str(step_env.get("IMAGE_MUTATION_STARTED", "")), (
        "rollback eligibility must consume the image-mutation marker"
    )
    assert "IMAGE_MUTATION_STARTED" in run_script
    assert "production_mutation_started" not in cond, (
        "production mutation requires terminal publication, but it must not "
        "make image rollback eligible"
    )


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
    assert "TINYASSETS_CODEX_AUTH_JSON_B64" in run_script
    assert "install-tinyassets-env.sh set TINYASSETS_CODEX_AUTH_JSON_B64" in run_script
    assert "install-tinyassets-env.sh set TINYASSETS_ALLOW_API_KEY_PROVIDERS" in run_script
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
    assert "/opt/tinyassets/compose.yml" in run_script
    assert "/opt/tinyassets/deploy/compose.yml" in run_script
    assert "deploy/tinyassets-daemon.service" in run_script
    assert "/etc/systemd/system/tinyassets-daemon.service" in run_script
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
        i for i, name in enumerate(names) if name == "Preflight droplet disk before image pull"
    )
    deploy_idx = next(i for i, step in enumerate(steps) if step.get("id") == "deploy")

    assert preflight_idx < deploy_idx, (
        "disk preflight must happen before TINYASSETS_IMAGE is changed, "
        "docker pull runs, or systemd restart can take the live daemon down"
    )


def test_disk_preflight_prunes_disposable_state_and_fails_before_restart():
    wf = _load()
    step = next(
        s for s in _steps(wf) if s.get("name") == "Preflight droplet disk before image pull"
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
    assert "delete TINYASSETS_WIKI_PATH TINYASSETS_UNIVERSE" in run_script


def test_deploy_scrubs_legacy_workflow_env_from_cloud_env():
    wf = _load()
    scrub_step = next(
        (s for s in _steps(wf) if s.get("name") == "Scrub stale cloud env overrides"),
        None,
    )
    assert scrub_step is not None
    run_script = scrub_step.get("run", "") or ""

    for key in (
        "WORKFLOW_IMAGE",
        "WORKFLOW_DATA_DIR",
        "WORKFLOW_MCP_CANARY_URL",
        "WORKFLOW_CODEX_AUTH_JSON_B64",
        "WORKFLOW_CLAUDE_CREDENTIALS_JSON_B64",
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        "BACKUP_GH_REPO",
        "LOG_DEST",
    ):
        assert key in run_script


def test_deploy_preserves_host_owned_backup_destination():
    wf = _load()
    scrub_step = next(
        (s for s in _steps(wf) if s.get("name") == "Scrub stale cloud env overrides"),
        None,
    )
    assert scrub_step is not None
    run_script = scrub_step.get("run", "") or ""

    assert "BACKUP_DEST" not in run_script


def test_deploy_verifies_cloud_worker_running():
    wf = _load()
    worker_step = next(
        (s for s in _steps(wf) if s.get("name") == "Verify cloud worker is running"),
        None,
    )
    assert worker_step is not None, "deploy must verify cloud workers are running"
    run_script = worker_step.get("run", "") or ""
    for name in (
        "tinyassets-worker",
        "tinyassets-worker-codex-2",
        "tinyassets-worker-claude-1",
        "tinyassets-worker-claude-2",
    ):
        assert name in run_script
    assert "docker inspect" in run_script
    assert "State.Running" in run_script
    assert "for i in $(seq 1 30)" in run_script
    assert "sleep 2" in run_script
    assert "docker compose --env-file /etc/tinyassets/env" in run_script
    assert "exit 1" in run_script


def test_deploy_retires_legacy_workflow_service_before_restart():
    wf = _load()
    steps = _steps(wf)
    retire_idx = next(
        (i for i, s in enumerate(steps) if s.get("name") == "Retire legacy Workflow service"),
        None,
    )
    deploy_idx = next(
        (i for i, s in enumerate(steps) if s.get("name") == "Deploy new image"),
        None,
    )
    assert retire_idx is not None
    assert deploy_idx is not None
    assert retire_idx < deploy_idx

    run_script = steps[retire_idx].get("run", "") or ""
    assert "workflow-daemon.service" in run_script
    assert "workflow.service" in run_script
    assert "workflow-watchdog.timer" in run_script
    assert "workflow-backup.timer" in run_script
    assert "workflow-ship-logs.timer" in run_script
    assert "systemctl disable --now" in run_script
    assert "/opt/workflow/compose.yml" in run_script
    assert "/etc/workflow/env" in run_script
    assert "workflow-tunnel" in run_script
    assert "workflow-worker-codex-2" in run_script
    assert "workflow-worker-claude-1" in run_script
    assert "workflow-worker-claude-2" in run_script
    assert "docker rm -f" in run_script
    assert 'rm -f "$unit_file"' in run_script
    assert "systemctl mask workflow-daemon.service" in run_script


def test_deploy_rejects_cloud_worker_workflow_universe_override():
    wf = _load()
    worker_step = next(
        (s for s in _steps(wf) if s.get("name") == "Verify cloud worker is running"),
        None,
    )
    assert worker_step is not None
    run_script = worker_step.get("run", "") or ""
    assert "grep -q '^TINYASSETS_UNIVERSE='" in run_script
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
        (s for s in _steps(wf) if s.get("name") == step_name),
        None,
    )
    assert step is not None
    run_script = step.get("run", "") or ""
    assert "verify_llm_binding.py" in run_script
    assert "--require-sandbox" in run_script
    assert "--retries 12" in run_script
    assert "--retry-delay 10" in run_script
    assert "::warning::No deploy-visible TINYASSETS_CODEX_AUTH_JSON_B64" not in run_script


def test_production_marker_is_immediately_before_first_scrub_host_write():
    wf = _load()
    scrub_step = _step_named(wf, "Scrub stale cloud env overrides")
    run_script = scrub_step.get("run", "") or ""
    lines = run_script.splitlines()
    first_host_write = next(i for i, line in enumerate(lines) if line.strip().startswith("ssh "))
    marker_line = _previous_executable_line(lines, first_host_write)

    assert scrub_step.get("id"), (
        "the scrub step needs an id so later always-running steps can consume "
        "production_mutation_started even when the SSH write fails"
    )
    assert "production_mutation_started=true" in marker_line
    assert "GITHUB_OUTPUT" in marker_line


def test_image_marker_is_immediately_before_first_tinyassets_image_write():
    wf = _load()
    deploy_step = next(step for step in _steps(wf) if step.get("id") == "deploy")
    run_script = deploy_step.get("run", "") or ""
    lines = run_script.splitlines()
    image_write_line = next(
        i
        for i, line in enumerate(lines)
        if "install-tinyassets-env.sh set TINYASSETS_IMAGE" in line
        and not line.lstrip().startswith("#")
    )

    # Walk to the start of the continued ssh command that invokes the helper.
    command_start = image_write_line
    while command_start > 0 and lines[command_start - 1].rstrip().endswith("\\"):
        command_start -= 1
    marker_line = _previous_executable_line(lines, command_start)

    assert "image_mutation_started=true" in marker_line
    assert "GITHUB_OUTPUT" in marker_line


def test_rollback_and_terminal_receipt_are_ordered_under_always():
    wf = _load()
    steps = _steps(wf)
    canary_step = _step_named(wf, "Post-deploy canary — canonical URL only")
    access_step = _step_named(wf, "Verify CF Access gates direct URL (expects 403/401)")
    rollback_step = _step_named(wf, "Rollback on failure")
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")

    assert str(rollback_step.get("if", "")).strip() == "always()"
    assert str(terminal_step.get("if", "")).strip() == "always()"
    assert steps.index(canary_step) < steps.index(rollback_step)
    assert steps.index(access_step) < steps.index(rollback_step)
    assert steps.index(rollback_step) < steps.index(terminal_step), (
        "terminal classification must run after rollback so its receipt "
        "describes the final observed production state"
    )


def test_daemon_deploy_owns_exact_public_server_name_assertion():
    wf = _load()
    canary_step = _step_named(wf, "Post-deploy canary — canonical URL only")
    run_script = canary_step.get("run", "") or ""

    assert "scripts/mcp_public_canary.py" in run_script
    assert "--assert-name TinyAssets" in run_script


def test_terminal_receipt_keys_to_production_marker():
    wf = _load()
    scrub_step = _step_named(wf, "Scrub stale cloud env overrides")
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    step_env = terminal_step.get("env") or {}
    run_script = terminal_step.get("run", "") or ""

    expected_ref = f"steps.{scrub_step['id']}.outputs.production_mutation_started"
    assert expected_ref in str(step_env.get("PRODUCTION_MUTATION_STARTED", ""))
    assert (
        "steps.stop-writer-cleanup.outputs.cutover_started"
        in str(step_env.get("PRODUCTION_MUTATION_STARTED", ""))
    )
    assert "PRODUCTION_MUTATION_STARTED" in run_script
    assert "not_applicable" in run_script
    assert "failed" in run_script


def test_rollback_emits_safe_defaults_and_final_outputs_before_exit():
    wf = _load()
    rollback_step = _step_named(wf, "Rollback on failure")
    run_script = rollback_step.get("run", "") or ""
    output_keys = (
        "rollback_attempted",
        "rollback_result",
        "rollback_canary_status",
        "rollback_reason",
    )

    fallible_positions = [
        position
        for token in ("scp ", "ssh ", "scripts/mcp_public_canary.py")
        if (position := run_script.find(token)) != -1
    ]
    assert fallible_positions, "rollback must contain the fallible rollback work"
    first_fallible = min(fallible_positions)
    output_helper = "emit_rollback_outputs"

    for key in output_keys:
        first_output = run_script.find(f"{key}=")
        assert first_output != -1, f"rollback must expose {key}"
        assert first_output < first_fallible, (
            f"rollback must emit a safe {key} default before fallible work"
        )

    final_exit = run_script.rfind("exit ")
    assert final_exit != -1, "rollback must return its exact classified exit"
    if output_helper in run_script:
        assert run_script.count(output_helper) >= 3, (
            "the rollback output helper must be defined and called for both "
            "safe defaults and the final tuple"
        )
        helper_definition = run_script.find(output_helper)
        first_helper_call = run_script.find(output_helper, helper_definition + len(output_helper))
        assert first_helper_call < first_fallible
        assert first_fallible < run_script.rfind(output_helper) < final_exit
    else:
        for key in output_keys:
            assert run_script.count(f"{key}=") >= 2, (
                f"rollback must emit both the safe default and final {key} output"
            )
            assert run_script.rfind(f"{key}=") < final_exit, (
                f"rollback final {key} output must be visible before failure"
            )


def test_rollback_identity_failure_preserves_the_passed_canary_tuple():
    wf = _load()
    rollback_step = _step_named(wf, "Rollback on failure")
    run_script = rollback_step.get("run", "") or ""

    passed_idx = run_script.find("rollback_canary_status=passed")
    identity_check_idx = run_script.find('if [ "${identity_status}" -ne 0 ]')
    assert 0 <= passed_idx < identity_check_idx
    pre_identity = run_script[passed_idx:identity_check_idx]
    assert "rollback_result=succeeded" in pre_identity, (
        "a passed rollback canary must retain the valid succeeded/passed tuple "
        "so terminal classification can record rollback_failed when the "
        "separate identity proof fails"
    )
    identity_failure = run_script[identity_check_idx : run_script.find("fi", identity_check_idx)]
    assert "rollback_result=failed" not in identity_failure, (
        "failed/passed is a contradictory tuple rejected by the pure builder"
    )


def test_terminal_receipt_invokes_pure_helper_and_preserves_atomic_writer():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""

    helper_idx = run_script.find("python scripts/deploy_terminal_receipt.py")
    transfer_idx = run_script.find("scp ")
    install_idx = run_script.find("install -m 0644 -o 1001 -g 1001")
    assert helper_idx != -1, (
        "terminal publication must invoke the directly executable pure classifier/builder"
    )
    assert transfer_idx != -1
    assert install_idx != -1
    assert helper_idx < transfer_idx < install_idx
    assert "release-state.json" in run_script
    assert "/data/release-state.json" in run_script
    assert "release-state.json.next" in run_script
    assert "mv " in run_script, (
        "receipt replacement must rename a validated same-volume sibling "
        "instead of exposing a partially written terminal receipt"
    )
    assert terminal_step.get("continue-on-error") is not True, (
        "terminal writer failure must keep the workflow red"
    )


def test_terminal_receipt_never_mutates_the_deployed_image_after_publication():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""

    published_idx = run_script.find("terminal_receipt_result=published")
    assert published_idx != -1
    post_publication = run_script[published_idx:]
    for forbidden in (
        "TINYASSETS_IMAGE",
        "docker pull",
        "systemctl restart tinyassets-daemon",
        "${PREV_IMAGE}",
    ):
        assert forbidden not in post_publication, (
            "the installed terminal receipt must describe the final production "
            f"state; found a later image mutation token: {forbidden}"
        )


def test_terminal_receipt_summary_python_is_executable(tmp_path):
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""
    match = re.search(
        r"python -c '([^']+)' \"\$RUNNER_TEMP/tinyassets-release-state\.json\"",
        run_script,
    )
    assert match is not None, "terminal receipt outcome summary command is missing"

    receipt_path = tmp_path / "release-state.json"
    receipt_path.write_text(json.dumps({"outcome": "deployed"}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", match.group(1), str(receipt_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "deployed"


def test_terminal_receipt_does_not_assign_manual_image_source_from_github_sha():
    text = _text()
    assert "github.event.workflow_run.head_sha || github.sha" not in text
    assert "org.opencontainers.image.revision" in text


def test_terminal_writer_outputs_are_visible_before_fallible_work():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""
    first_fallible = min(
        position
        for token in ("ssh ", "scp ", "python scripts/deploy_terminal_receipt.py")
        if (position := run_script.find(token)) != -1
    )

    failed_idx = run_script.find("terminal_receipt_result=failed")
    not_applicable_idx = run_script.find("terminal_receipt_result=not_applicable")
    published_idx = run_script.find("terminal_receipt_result=published")
    install_idx = run_script.find("install -m 0644 -o 1001 -g 1001")
    assert 0 <= failed_idx < first_fallible, (
        "writer failure must leave a visible failed output before host "
        "observation, classification, transfer, or install can fail"
    )
    assert 0 <= not_applicable_idx < first_fallible, (
        "the pre-host path must publish not_applicable without host contact"
    )
    assert install_idx != -1
    assert published_idx > install_idx, (
        "published is truthful only after the atomic receipt install succeeds"
    )
    for output_name in (
        "terminal_outcome",
        "terminal_active_identity_status",
        "terminal_canary_status",
    ):
        output_idx = run_script.find(f"{output_name}=")
        assert 0 <= output_idx < install_idx, (
            f"{output_name} must be exposed before atomic install so issue "
            "wording survives writer failure"
        )


def test_terminal_canary_output_preserves_the_raw_applicable_canary():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""

    assert "terminal_canary_status={receipt['canary_bundle_status']}" not in run_script
    assert 'receipt["forward_canary_status"]' in run_script
    assert 'receipt["rollback_canary_status"]' in run_script
    assert 'receipt["rollback_attempted"]' in run_script


def test_forward_green_terminal_identity_failure_stays_red_after_publication():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""

    published_idx = run_script.find("terminal_receipt_result=published")
    proof_gate_idx = run_script.find('if [ "${FORWARD_SUCCEEDED}" = "true" ]')
    proof_error_idx = run_script.find("forward terminal state is unproven")
    assert 0 <= published_idx < proof_gate_idx < proof_error_idx, (
        "terminal evidence must be installed before the forward identity gate returns nonzero"
    )
    proof_tail = run_script[proof_gate_idx:]
    assert "exit 1" in proof_tail
    for required in ("deployed", "active_identity_status", "agreed", "passed"):
        assert required in proof_tail


def test_deploy_failure_issue_consumes_rollback_and_terminal_outputs():
    wf = _load()
    rollback_step = _step_named(wf, "Rollback on failure")
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    issue_step = _step_named(wf, "Open deploy-failed issue")
    assert rollback_step.get("id"), "rollback outputs require a stable step id"
    assert terminal_step.get("id"), "terminal outputs require a stable step id"

    cond = str(issue_step.get("if", ""))
    env_text = "\n".join(str(value) for value in (issue_step.get("env") or {}).values())
    assert "always()" in cond and "failure()" in cond, (
        "the issue must still run after a red rollback or terminal writer"
    )
    for output_name in (
        "rollback_attempted",
        "rollback_result",
        "rollback_canary_status",
        "rollback_reason",
    ):
        assert f"steps.{rollback_step['id']}.outputs.{output_name}" in env_text, (
            f"deploy-failed issue must consume {output_name}"
        )
    for output_name in (
        "terminal_receipt_result",
        "terminal_outcome",
        "terminal_active_identity_status",
        "terminal_canary_status",
        "terminal_configured_image_ref",
        "terminal_running_image_ref",
        "terminal_active_image_ref",
    ):
        assert f"steps.{terminal_step['id']}.outputs.{output_name}" in env_text, (
            f"deploy-failed issue must consume {output_name}"
        )


def test_deploy_failure_issue_rejects_partial_or_contradictory_tuples():
    wf = _load()
    issue_step = _step_named(wf, "Open deploy-failed issue")
    script = str((issue_step.get("with") or {}).get("script", ""))

    for required in (
        "productionNotStarted",
        "imageNotStarted",
        "rollbackNotAttempted",
        'rollbackResult === "not_attempted"',
        'rollbackResult === "succeeded"',
        'rollbackResult === "failed"',
        'rollbackCanary === "not_run"',
        'rollbackCanary === "passed"',
        'rollbackCanary === "failed"',
        'rollbackReason === "attempted"',
        "canonicalRepoDigest.test(previousImage)",
    ):
        assert required in script
    assert 'rollbackAttempted && rollbackCanary === "failed"' not in script
    assert 'rollbackAttempted && rollbackCanary === "not_run"' not in script


def test_deploy_failure_issue_has_truthful_bounded_wording():
    wf = _load()
    issue_step = _step_named(wf, "Open deploy-failed issue")
    script = str((issue_step.get("with") or {}).get("script", ""))

    assert "Rolled back to:" not in script, (
        "a previous-image value is not proof that rollback succeeded"
    )
    for required_sentence in (
        "Production host write did not start; image rollback was not attempted.",
        (
            "Production mutation started, but image mutation did not; "
            "image rollback was not required."
        ),
        (
            "Rollback was not needed because terminal outcome is deployed, "
            "active image identity agrees, and the applicable canary passed."
        ),
        "Rollback was not attempted; forward production health is unproven.",
        "Rollback succeeded and the rollback canary passed.",
        ("Rollback status is unavailable; rollback success was not proven."),
        "Terminal release-state receipt published.",
        (
            "Terminal release-state publication failed; durable active-release "
            "truth is not proven and the prior receipt may be stale."
        ),
        (
            "Terminal release-state publication was not applicable; the prior "
            "receipt was left unchanged."
        ),
    ):
        assert required_sentence in script


# ---------------------------------------------------------------------------
# Codex auth persistent volume (PR #965) — idempotence + ownership repair
# ---------------------------------------------------------------------------


def _codex_volume_step(wf: dict) -> dict:
    step = next(
        (s for s in _steps(wf) if s.get("name") == "Prepare codex auth persistent volume"),
        None,
    )
    assert step is not None, (
        "deploy must include a 'Prepare codex auth persistent volume' "
        "step that provisions tinyassets-data/.codex on every deploy "
        "(Forever Rule — no host-action required)"
    )
    return step


def test_codex_volume_step_runs_before_deploy():
    wf = _load()
    steps = _steps(wf)
    names = [s.get("name", "") for s in steps]
    volume_idx = names.index("Prepare codex auth persistent volume")
    deploy_idx = next(i for i, step in enumerate(steps) if step.get("id") == "deploy")
    assert volume_idx < deploy_idx, (
        "Codex auth volume must be provisioned BEFORE the daemon "
        "container restarts; otherwise the first restart may miss "
        "the persistent CODEX_HOME auth directory."
    )


def test_codex_volume_step_chown_is_unconditional():
    """Regression guard for Codex round-2 Finding 2.

    Round-1 placed `chown` inside the `if [ ! -d "$VOLUME_DIR" ]` branch.
    If a prior deploy attempt left the dir root-owned, subsequent
    deploys silently skipped the ownership repair and uid 1001 couldn't
    write. Fix: run chown unconditionally every deploy.
    """
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""

    # Extract the heredoc body so we can reason about block structure.
    # The heredoc starts after `<<'SH'` and ends at a line containing `SH`.
    lines = run_script.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.endswith("<<'SH'")),
        None,
    )
    end = (
        next(
            (
                i
                for i, line in enumerate(lines[start + 1 :], start=start + 1)
                if line.strip() == "SH"
            ),
            None,
        )
        if start is not None
        else None
    )
    assert start is not None and end is not None, (
        "Could not locate heredoc body in 'Prepare codex auth persistent volume'"
    )
    body = lines[start + 1 : end]

    chown_line_idx = next(
        (
            i
            for i, line in enumerate(body)
            if line.strip().startswith('chown "$TINYASSETS_UID:$TINYASSETS_GID" "$CODEX_DIR"')
        ),
        None,
    )
    chmod_line_idx = next(
        (i for i, line in enumerate(body) if line.strip().startswith('chmod 700 "$CODEX_DIR"')),
        None,
    )
    assert chown_line_idx is not None, "chown on $CODEX_DIR must be present"
    assert chmod_line_idx is not None, "chmod 700 on $CODEX_DIR must be present"

    # Walk backwards from each line; the most recent unmatched `if [` must
    # NOT be the `[ ! -d "$CODEX_DIR" ]` branch. Track indent depth via
    # leading whitespace as a coarse signal — both unconditional lines
    # should sit at the heredoc's base indent.
    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    base_indent = min(
        (_indent(line) for line in body if line.strip()),
        default=0,
    )
    chown_indent = _indent(body[chown_line_idx])
    chmod_indent = _indent(body[chmod_line_idx])
    assert chown_indent == base_indent, (
        f"chown line must sit at heredoc base indent ({base_indent}); "
        f"got indent {chown_indent}. Being nested inside `if [ ! -d ]` "
        "is exactly the Finding-2 regression we are guarding against."
    )
    assert chmod_indent == base_indent, (
        f"chmod line must sit at heredoc base indent ({base_indent}); got indent {chmod_indent}."
    )


def test_codex_volume_step_creates_dir_idempotently():
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""
    assert 'docker volume create "$VOLUME_NAME"' in run_script, (
        "tinyassets-data named volume must be created idempotently before resolving its mountpoint"
    )
    assert 'docker volume inspect "$VOLUME_NAME"' in run_script, (
        "deploy must resolve the local volume mountpoint before preparing .codex"
    )
    assert 'CODEX_DIR="$VOLUME_DIR/.codex"' in run_script
    assert 'mkdir -p "$CODEX_DIR"' in run_script, (
        "directory creation must use `mkdir -p` so re-running the step "
        "is a no-op when the dir already exists"
    )
    assert 'if [ ! -d "$CODEX_DIR" ]' in run_script, (
        "dir-create branch must be guarded by an existence check so the "
        "create-log line is skipped when the dir already exists"
    )


def test_codex_volume_step_repairs_volume_root_for_auth_db():
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""

    assert 'chown "$TINYASSETS_UID:$TINYASSETS_GID" "$VOLUME_DIR"' in run_script
    assert 'chmod 755 "$VOLUME_DIR"' in run_script
    assert ".auth.db" in run_script
    assert "unable to open database file" in run_script


def test_codex_volume_step_migrates_from_running_container_once():
    """First deploy after CODEX_HOME migration onto a live droplet must copy the
    rotated auth.json out of the running tinyassets-worker into the
    persistent volume. Subsequent deploys skip (auth.json already
    present). No-op when no live source container exists.
    """
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""
    assert 'if [ ! -f "$CODEX_DIR/auth.json" ]' in run_script, (
        "migration branch must be guarded so it fires exactly once"
    )
    assert "docker inspect tinyassets-worker" in run_script, (
        "migration must check tinyassets-worker presence before docker cp"
    )
    assert "docker exec tinyassets-worker test -f /data/.codex/auth.json" in run_script, (
        "migration must check the new CODEX_HOME path before copying"
    )
    assert "docker exec tinyassets-worker test -f /app/.codex/auth.json" in run_script, (
        "migration must also support one-time legacy /app/.codex pickup"
    )
    assert "docker cp tinyassets-worker:/data/.codex/auth.json" in run_script
    assert "docker cp tinyassets-worker:/app/.codex/auth.json" in run_script
    assert 'chown "$TINYASSETS_UID:$TINYASSETS_GID" "$CODEX_DIR/auth.json"' in run_script
    assert 'chmod 600 "$CODEX_DIR/auth.json"' in run_script


def test_subscription_volume_step_prepares_claude_config_dir():
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""
    assert 'CLAUDE_DIR="$VOLUME_DIR/.claude"' in run_script
    assert 'mkdir -p "$CLAUDE_DIR"' in run_script
    assert 'chown -R "$TINYASSETS_UID:$TINYASSETS_GID" "$CLAUDE_DIR"' in run_script
    assert 'chmod 700 "$CLAUDE_DIR"' in run_script
    assert "docker exec tinyassets-worker test -d /data/.claude" in run_script
    assert "docker exec tinyassets-worker test -d /app/.claude" in run_script
    assert "docker cp tinyassets-worker:/data/.claude/." in run_script
    assert "docker cp tinyassets-worker:/app/.claude/." in run_script


# ---------------------------------------------------------------------------
# PR-128 — Phase 2 capability map sync into /etc/tinyassets/env
# ---------------------------------------------------------------------------


def test_deploy_job_env_has_github_pr_capability_flag():
    """The job-level env block must surface ``HAS_GITHUB_PR_CAPABILITY``
    so the Deploy step + summary can branch on whether the secret is
    visible to this run. Pattern mirrors ``HAS_CODEX_AUTH_BUNDLE``."""
    wf = _load()
    job_env = (wf.get("jobs", {}).get("deploy", {}) or {}).get("env") or {}
    assert "HAS_GITHUB_PR_CAPABILITY" in job_env, (
        "deploy job env must expose HAS_GITHUB_PR_CAPABILITY so the "
        "Deploy step and summary can branch on capability visibility"
    )
    raw_value = str(job_env["HAS_GITHUB_PR_CAPABILITY"])
    assert "secrets.WORKFLOW_GITHUB_PR_CAPABILITIES" in raw_value, (
        "the bounded migration must use the one existing pre-rename secret "
        "as its unambiguous source of truth"
    )
    assert "secrets.TINYASSETS_GITHUB_PR_CAPABILITIES" not in raw_value, (
        "dual secret precedence makes revocation ambiguous; the migration "
        "must select exactly one repository secret"
    )
    assert "!= ''" in raw_value, (
        "HAS_GITHUB_PR_CAPABILITY must use a non-empty-string check, "
        "matching the HAS_CODEX_AUTH_BUNDLE pattern"
    )


def test_deploy_step_env_imports_github_pr_capabilities_secret():
    """The Deploy step's local env block must import the capability
    map secret so the inline ssh-piping path can read it."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None, "deploy job must have a deploy step"
    step_env = deploy_step.get("env") or {}
    assert "GITHUB_PR_CAPABILITIES_SOURCE" in step_env, (
        "Deploy step must import the bounded migration source without "
        "pretending the unvalidated map is already the runtime value"
    )
    raw_value = str(step_env["GITHUB_PR_CAPABILITIES_SOURCE"])
    assert "secrets.WORKFLOW_GITHUB_PR_CAPABILITIES" in raw_value
    assert "secrets.TINYASSETS_GITHUB_PR_CAPABILITIES" not in raw_value


def test_deploy_requires_and_installs_agent_interchange_hmac_secret():
    wf = _load()
    steps = _steps(wf)
    validation_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Validate agent interchange HMAC prerequisite"
    )
    validation_step = steps[validation_index]
    validation_env = validation_step.get("env") or {}
    secret_source = str(
        validation_env.get("TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", "")
    )
    assert "secrets.TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY" in secret_source
    assert validation_step.get("run") == "python scripts/validate_agent_interchange_hmac.py"

    mutating_steps = {
        "Install daemon-only agent interchange HMAC secret",
        "Preflight droplet disk before image pull",
        "Transitional task 2.1 stop-writer preflight",
        "Scrub stale cloud env overrides",
        "Sync runtime deploy files",
        "Prepare codex auth persistent volume",
        "Retire legacy Workflow service",
        "Deploy new image",
    }
    mutation_indexes = [
        index for index, step in enumerate(steps) if step.get("name") in mutating_steps
    ]
    assert len(mutation_indexes) == len(mutating_steps)
    assert validation_index < min(mutation_indexes)

    step_indexes = {step.get("name"): index for index, step in enumerate(steps)}
    assert step_indexes["Preflight droplet disk before image pull"] < step_indexes[
        "Install daemon-only agent interchange HMAC secret"
    ]
    assert step_indexes["Transitional task 2.1 stop-writer preflight"] < step_indexes[
        "Install daemon-only agent interchange HMAC secret"
    ]
    assert step_indexes["Install daemon-only agent interchange HMAC secret"] < (
        step_indexes["Scrub stale cloud env overrides"]
    )

    install_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Install daemon-only agent interchange HMAC secret"
    )
    install_step = steps[install_index]
    install_env = install_step.get("env") or {}
    install_secret = str(
        install_env.get("TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", "")
    )
    assert "secrets.TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY" in install_secret

    deploy_step = next(step for step in steps if step.get("id") == "deploy")
    step_env = deploy_step.get("env") or {}
    assert "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY" not in step_env

    script = install_step.get("run", "") or ""
    assert re.search(
        r'printf \'%s\' "\$\{TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY\}" '
        r'\|\s*\\?\s*ssh',
        script,
    )
    install = script.index(
        "install-tinyassets-env.sh set TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY"
    )
    assert install > 0
    assert install_index < steps.index(deploy_step)
    assert "TINYASSETS_ENV_FILE=/etc/tinyassets/agent-interchange.env" in script
    assert 'echo "${TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY}"' not in script
    assert "set TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY '" not in script


def test_self_host_template_declares_empty_agent_interchange_hmac_key():
    shared = Path("deploy/tinyassets-env.template").read_text(encoding="utf-8")
    dedicated = Path("deploy/agent-interchange-env.template").read_text(
        encoding="utf-8"
    )
    assert "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY" not in shared
    assert "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY=" in dedicated
    assert "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY=change" not in dedicated

    compose = yaml.safe_load(Path("deploy/compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    dedicated_path = "/etc/tinyassets/agent-interchange.env"
    assert dedicated_path in services["daemon"]["env_file"]
    for name, service in services.items():
        if name != "daemon":
            assert dedicated_path not in (service.get("env_file") or []), name


@pytest.mark.parametrize(
    "value",
    [
        "",
        base64.b64encode(b"x" * 31).decode("ascii"),
        base64.b64encode(b"x" * 32).decode("ascii") + "\nINJECTED_SETTING=1",
        "not-base64!",
        base64.b64encode(b"x" * 32).decode("ascii").rstrip("="),
    ],
)
def test_agent_interchange_hmac_validator_rejects_unsafe_values(value: str):
    from scripts.validate_agent_interchange_hmac import validate_secret

    with pytest.raises(ValueError):
        validate_secret(value)


def test_agent_interchange_hmac_validator_accepts_32_random_bytes():
    from scripts.validate_agent_interchange_hmac import validate_secret

    raw = bytes(range(32))
    encoded = base64.b64encode(raw).decode("ascii")
    assert validate_secret(encoded) == raw


def test_agent_interchange_hmac_validator_never_echoes_rejected_secret():
    secret = base64.b64encode(b"x" * 32).decode("ascii") + "\nINJECTED_SETTING=1"
    env = {**os.environ, "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY": secret}
    result = subprocess.run(
        [sys.executable, "scripts/validate_agent_interchange_hmac.py"],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert secret not in result.stdout
    assert "INJECTED_SETTING" not in result.stdout
    assert secret not in result.stderr


def test_deploy_requires_and_installs_daemon_request_idempotency_hmac_secret():
    wf = _load()
    steps = _steps(wf)
    indexes = {step.get("name"): index for index, step in enumerate(steps)}

    validation_name = "Validate request idempotency HMAC prerequisite"
    install_name = "Install daemon-only request idempotency HMAC secret"
    validation = steps[indexes[validation_name]]
    validation_secret = str(
        (validation.get("env") or {}).get(
            "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY", ""
        )
    )
    assert "secrets.TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" in validation_secret
    validation_companion = str(
        (validation.get("env") or {}).get(
            "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY", ""
        )
    )
    assert "secrets.TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY" in validation_companion
    assert validation.get("run") == (
        "python scripts/validate_request_idempotency_hmac.py"
    )

    mutating_names = {
        "Preflight droplet disk before image pull",
        "Transitional task 2.1 stop-writer preflight",
        "Install daemon-only agent interchange HMAC secret",
        install_name,
        "Scrub stale cloud env overrides",
        "Sync runtime deploy files",
        "Prepare codex auth persistent volume",
        "Retire legacy Workflow service",
        "Deploy new image",
    }
    assert indexes[validation_name] < min(
        indexes[name] for name in mutating_names
    )
    assert indexes["Transitional task 2.1 stop-writer preflight"] < indexes[
        install_name
    ]
    assert indexes[install_name] < indexes[
        "Install daemon-only agent interchange HMAC secret"
    ]
    assert indexes["Install daemon-only agent interchange HMAC secret"] < indexes[
        "Validate installed host HMAC pair"
    ]
    assert indexes["Validate installed host HMAC pair"] < indexes[
        "Scrub stale cloud env overrides"
    ]
    host_validation = steps[indexes["Validate installed host HMAC pair"]]
    host_validation_script = host_validation.get("run", "") or ""
    assert "scripts/validate_host_runtime_hmac_pair.py" in host_validation_script
    assert '"sudo python3 -"' in host_validation_script
    assert indexes[install_name] < indexes["Scrub stale cloud env overrides"]

    install = steps[indexes[install_name]]
    install_secret = str(
        (install.get("env") or {}).get(
            "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY", ""
        )
    )
    assert "secrets.TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" in install_secret
    script = install.get("run", "") or ""
    assert re.search(
        r'printf \'%s\' "\$\{TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY\}" '
        r'\|\s*\\?\s*ssh',
        script,
    )
    assert "TINYASSETS_ENV_FILE=/etc/tinyassets/request-idempotency.env" in script
    assert "no-request-idempotency-legacy" in script
    install_mode = str((install.get("env") or {}).get("REQUEST_HMAC_INSTALL_MODE", ""))
    assert "github.event_name == 'workflow_dispatch'" in install_mode
    assert "inputs.rotate_request_idempotency_hmac" in install_mode
    assert "set-once" in install_mode
    assert "set" in install_mode
    assert 'case "${REQUEST_HMAC_INSTALL_MODE}" in' in script
    assert "set-once|set)" in script
    assert "bash /tmp/install-tinyassets-env.sh '${REQUEST_HMAC_INSTALL_MODE}'" in script
    assert 'echo "${TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY}"' not in script

    deploy_step = next(step for step in steps if step.get("id") == "deploy")
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" not in (
        deploy_step.get("env") or {}
    )


def test_request_idempotency_hmac_template_and_compose_contract():
    template = Path("deploy/tinyassets-env.template").read_text(encoding="utf-8")
    dedicated = Path("deploy/request-idempotency-env.template").read_text(
        encoding="utf-8"
    )
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" not in template
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=" in dedicated
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=change" not in dedicated

    compose = yaml.safe_load(Path("deploy/compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    dedicated_path = "/etc/tinyassets/request-idempotency.env"
    assert dedicated_path in (services["daemon"].get("env_file") or [])
    for name, service in services.items():
        if name != "daemon":
            assert dedicated_path not in (service.get("env_file") or []), name


@pytest.mark.parametrize(
    "value",
    [
        "",
        base64.b64encode(b"x" * 31).decode("ascii"),
        base64.b64encode(b"x" * 32).decode("ascii") + "\nINJECTED_SETTING=1",
        "not-base64!",
        base64.b64encode(b"x" * 32).decode("ascii").rstrip("="),
    ],
)
def test_request_idempotency_hmac_validator_rejects_unsafe_values(value: str):
    from scripts.validate_request_idempotency_hmac import validate_secret

    with pytest.raises(ValueError):
        validate_secret(value)


def test_request_idempotency_hmac_validator_accepts_and_never_echoes_secret():
    from scripts.validate_request_idempotency_hmac import validate_secret

    raw = bytes(range(48))
    encoded = base64.b64encode(raw).decode("ascii")
    assert validate_secret(encoded) == raw

    rejected = encoded + "\nINJECTED_SETTING=1"
    env = {**os.environ, "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY": rejected}
    result = subprocess.run(
        [sys.executable, "scripts/validate_request_idempotency_hmac.py"],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert rejected not in result.stdout
    assert "INJECTED_SETTING" not in result.stdout
    assert rejected not in result.stderr


def test_request_idempotency_hmac_validator_rejects_agent_key_reuse():
    encoded = base64.b64encode(bytes(range(48))).decode("ascii")
    env = {
        **os.environ,
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY": encoded,
        "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY": encoded,
    }
    result = subprocess.run(
        [sys.executable, "scripts/validate_request_idempotency_hmac.py"],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert encoded not in result.stdout
    assert encoded not in result.stderr
    assert "must differ" in result.stdout


def test_unsafe_recovery_validates_both_hmac_prerequisites_before_mutation():
    wf = _load()
    steps = wf["jobs"]["recover-unsafe"]["steps"]
    indexes = {step.get("name"): index for index, step in enumerate(steps)}
    request = steps[indexes["Validate recovery request idempotency HMAC"]]
    agent = steps[indexes["Validate recovery agent interchange HMAC"]]
    assert request.get("run") == (
        "python scripts/validate_request_idempotency_hmac.py"
    )
    assert agent.get("run") == "python scripts/validate_agent_interchange_hmac.py"
    assert indexes["Validate recovery request idempotency HMAC"] < indexes[
        "Pull recovery image on production host"
    ]
    assert indexes["Validate recovery agent interchange HMAC"] < indexes[
        "Pull recovery image on production host"
    ]
    host = steps[indexes["Validate host HMAC pair before recovery mutation"]]
    host_script = host.get("run", "") or ""
    assert "scripts/validate_host_runtime_hmac_pair.py" in host_script
    assert '"sudo python3 -"' in host_script
    assert indexes["Install recovery SSH key"] < indexes[
        "Validate host HMAC pair before recovery mutation"
    ]
    assert indexes["Validate host HMAC pair before recovery mutation"] < indexes[
        "Pull recovery image on production host"
    ]


def test_deploy_step_syncs_github_pr_capabilities_when_set():
    """When ``HAS_GITHUB_PR_CAPABILITY=true``, the Deploy step must
    pipe the secret into install-tinyassets-env.sh via the same atomic
    helper used for TINYASSETS_CODEX_AUTH_JSON_B64."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""

    # Required-shape assertions: the conditional, the pipe, the helper
    # invocation, and the warning surface for the missing-secret case.
    assert 'if [ "${HAS_GITHUB_PR_CAPABILITY}" = "true" ]' in run_script, (
        "deploy must gate the exact GitHub push-capability sync on "
        "HAS_GITHUB_PR_CAPABILITY=true so absence is a warning, not "
        "an unbound-variable failure"
    )
    assert 'destination = "Jonnyton/TinyAssets"' in run_script
    assert 'historical_destination = "Jonnyton/Workflow"' in run_script
    assert "set(source) == {destination}" in run_script
    assert "set(source) == {historical_destination}" in run_script
    assert "json.dumps(" in run_script
    assert "{destination: token}" in run_script
    assert "GITHUB_PR_CAPABILITIES_SOURCE" in run_script
    assert "printf '%s' \"${scoped_github_pr_capabilities}\"" in run_script, (
        "deploy must pipe only the validated exact-destination map and never "
        "echo the broad source map or token"
    )
    assert "unset scoped_github_pr_capabilities" in run_script
    assert "install-tinyassets-env.sh set TINYASSETS_GITHUB_PUSH_CAPABILITIES" in run_script, (
        "deploy must call the atomic install-tinyassets-env.sh helper "
        "(the same path that enforces root:tinyassets 640 + post-write "
        "readability) to write the capability map"
    )
    assert "GitHub PR capability source is not visible to deploy" in run_script, (
        "deploy must emit a structured ::warning:: when the secret is "
        "absent so the operator notices before chatbots try real-PR "
        "emission and see missing_capability dry-run evidence"
    )


def test_deploy_step_invalid_capability_source_revokes_before_failure():
    """Malformed or wrong-destination migration input must fail closed.

    The deploy must remove any previously installed runtime capability before
    exiting, instead of retaining stale authority or installing an empty map.
    """
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""
    validation = "if ! scoped_github_pr_capabilities="
    delete = (
        "install-tinyassets-env.sh delete "
        "TINYASSETS_GITHUB_PUSH_CAPABILITIES "
        "TINYASSETS_GITHUB_PR_CAPABILITIES"
    )
    failure = 'exit 1'
    validation_idx = run_script.find(validation)
    delete_idx = run_script.find(delete, validation_idx)
    restart_idx = run_script.find(
        "systemctl restart tinyassets-daemon",
        delete_idx,
    )
    failure_idx = run_script.find(failure, delete_idx)
    assert validation_idx != -1
    assert delete_idx > validation_idx
    assert restart_idx > delete_idx
    assert failure_idx > restart_idx
    assert (
        "TINYASSETS_GITHUB_PR_CAPABILITIES && "
        "sudo systemctl restart tinyassets-daemon"
    ) in run_script
    assert (
        '"capability source must contain exactly one supported "'
        in run_script
    )


def _github_capability_validator() -> str:
    wf = _load()
    deploy_step = next(s for s in _steps(wf) if s.get("id") == "deploy")
    run_script = deploy_step.get("run", "") or ""
    segment = run_script[run_script.index("if ! scoped_github_pr_capabilities=") :]
    match = re.search(r"python -c '\n(?P<code>.*?)\n\s*'", segment, re.DOTALL)
    assert match is not None
    return textwrap.dedent(match.group("code"))


@pytest.mark.parametrize(
    "source",
    [
        {"Jonnyton/TinyAssets": "current-token"},
        {"Jonnyton/Workflow": "historical-token"},
    ],
)
def test_github_capability_validator_emits_only_current_destination(source: dict):
    result = subprocess.run(
        [sys.executable, "-c", _github_capability_validator()],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GITHUB_PR_CAPABILITIES_SOURCE": json.dumps(source),
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "Jonnyton/TinyAssets": next(iter(source.values()))
    }


@pytest.mark.parametrize(
    "source",
    [
        {"Jonnyton/Workflow": "old", "Jonnyton/TinyAssets": "new"},
        {"Jonnyton/Elsewhere": "token"},
        {"Jonnyton/Workflow": "token", "extra": "authority"},
        {"Jonnyton/Workflow": ""},
    ],
)
def test_github_capability_validator_rejects_ambiguous_or_invalid_maps(
    source: dict,
):
    result = subprocess.run(
        [sys.executable, "-c", _github_capability_validator()],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GITHUB_PR_CAPABILITIES_SOURCE": json.dumps(source),
        },
    )

    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "source",
    [
        '{"Jonnyton/TinyAssets":"first","Jonnyton/TinyAssets":"second"}',
        '{"Jonnyton/Workflow":"first","Jonnyton/Workflow":"second"}',
    ],
)
def test_github_capability_validator_rejects_duplicate_json_members(
    source: str,
):
    result = subprocess.run(
        [sys.executable, "-c", _github_capability_validator()],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GITHUB_PR_CAPABILITIES_SOURCE": source,
        },
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "first" not in result.stderr
    assert "second" not in result.stderr


def test_deploy_step_is_valid_bash_after_actions_expression_substitution():
    """Guard the executable script shape, including inline validators."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = re.sub(
        r"\$\{\{.*?\}\}",
        "github-actions-value",
        deploy_step.get("run", "") or "",
    )
    bash = None
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            bash = str(git_bash)
    if bash is None:
        bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run(
        [bash, "-n"],
        input=run_script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_deploy_step_summary_reports_github_pr_capability_visibility():
    """The GH Actions step summary must surface whether the capability
    was synced this run so the operator can confirm post-deploy."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""
    assert "Exact TinyAssets GitHub push capability source visible to deploy" in run_script, (
        "deploy step summary must report the capability-map visibility "
        "alongside the codex-auth visibility line so the operator can "
        "verify both auth surfaces from one place"
    )


def test_github_pr_capability_sync_runs_after_codex_auth_sync():
    """Determinism: both sync blocks live in the same Deploy step, and
    the capability sync must run AFTER the codex-auth sync so the
    summary order matches the operator's mental model (codex first,
    capability second)."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""
    codex_marker = "set TINYASSETS_CODEX_AUTH_JSON_B64"
    cap_marker = "set TINYASSETS_GITHUB_PUSH_CAPABILITIES"
    codex_idx = run_script.find(codex_marker)
    cap_idx = run_script.find(cap_marker)
    assert codex_idx != -1, "codex-auth sync block must be present"
    assert cap_idx != -1, "capability sync block must be present"
    assert codex_idx < cap_idx, (
        "capability sync must run after the codex-auth sync — both "
        "live in the same Deploy step and the operator-facing summary "
        "lists them in that order"
    )


# ---------------------------------------------------------------------------
# Round-2 (Codex round-1 finding) — capability-revoke must actually revoke
# ---------------------------------------------------------------------------


def test_deploy_step_deletes_github_pr_capability_when_secret_absent():
    """Round-2 regression guard. Round-1 logged a warning when
    ``TINYASSETS_GITHUB_PR_CAPABILITIES`` was absent but did NOT remove
    the existing key from ``/etc/tinyassets/env``, so deleting the GH
    Actions secret to revoke had no effect — the next deploy
    restarted the daemon with the OLD capability still active.

    The fix: when ``HAS_GITHUB_PR_CAPABILITY=false`` (or unset), the
    Deploy step must issue an explicit
    ``install-tinyassets-env.sh delete TINYASSETS_GITHUB_PR_CAPABILITIES``
    call so the effector observes ``missing_capability`` on its next
    read. The documented contract ("absence -> dry-run") was being
    silently violated; this test gates the fix.
    """
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""
    assert "install-tinyassets-env.sh delete TINYASSETS_GITHUB_PUSH_CAPABILITIES" in run_script, (
        "Deploy step must issue an explicit `install-tinyassets-env.sh "
        "delete TINYASSETS_GITHUB_PUSH_CAPABILITIES ...` call when the secret "
        "is absent so revoking the GH Actions secret actually "
        "revokes capability on the droplet (round-2 fix for PR #980 "
        "Codex finding)."
    )


def test_capability_delete_is_gated_on_else_branch():
    """The delete call must live inside the ``else`` branch of the
    ``HAS_GITHUB_PR_CAPABILITY`` conditional — never run when the
    secret IS present. A naive fix that placed the delete
    unconditionally would clobber the value the previous ``set``
    call just installed."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""

    # Anchor the conditional. The set call must come before the
    # else+delete tail.
    set_marker = "install-tinyassets-env.sh set TINYASSETS_GITHUB_PUSH_CAPABILITIES"
    delete_marker = "install-tinyassets-env.sh delete TINYASSETS_GITHUB_PUSH_CAPABILITIES"
    set_idx = run_script.find(set_marker)
    # The validation-failure branch also revokes. The last delete is the
    # absence/revocation arm whose placement this test owns.
    delete_idx = run_script.rfind(delete_marker)
    assert set_idx != -1, "set call must remain in the truthy branch"
    assert delete_idx != -1, "delete call must be present in else branch"
    assert set_idx < delete_idx, (
        "set call (truthy branch) must precede delete call (else "
        "branch) in the source — confirms the delete lives in the "
        "ELSE arm of the HAS_GITHUB_PR_CAPABILITY conditional"
    )

    # Walk the lines between the two markers and assert an ``else``
    # token sits between them. This is the regression guard: a future
    # refactor that flattens the conditional without re-checking would
    # fail this assertion.
    between = run_script[set_idx + len(set_marker) : delete_idx]
    assert "else" in between, (
        "An `else` keyword must appear between the set call and the "
        "delete call. If a refactor restructures the conditional, the "
        "delete must remain inside an else-gated branch — never run "
        "unconditionally."
    )


def test_capability_delete_warning_explains_revocation():
    """The warning line on the else branch must convey that the
    revocation actually happens (removing the prior key), not just
    that the secret is absent — operators need to know the deploy
    actively cleaned up the env."""
    wf = _load()
    deploy_step = next(
        (s for s in _steps(wf) if s.get("id") == "deploy"),
        None,
    )
    assert deploy_step is not None
    run_script = deploy_step.get("run", "") or ""
    assert "::warning::" in run_script
    # The warning must reference removing/deleting the prior value so
    # an operator skimming GH Actions logs can tell the difference
    # between "noop because never set" and "actually revoked".
    assert (
        "removing any prior" in run_script
        or "remove any prior" in run_script
        or "delete TINYASSETS_GITHUB_PR_CAPABILITIES" in run_script
    ), (
        "the absence warning must describe the revocation action so "
        "operators can confirm capability was actually cleared from "
        "/etc/tinyassets/env, not just absent from GH Actions"
    )


# ---------------------------------------------------------------------------
# retire-cheat-loop task 2.1 — transitional production stop-writer fence
# ---------------------------------------------------------------------------


def _stop_writer_step(wf: dict, name: str) -> dict:
    step = _step_named(wf, name)
    assert "retire-cheat-loop task 2.1" in str(step.get("run", "")), (
        f"{name!r} must be explicitly transitional so task 2.5 can remove "
        "the product-specific receipt/queue guard"
    )
    return step


def test_stop_writer_preflight_runs_before_image_mutation():
    wf = _load()
    steps = _steps(wf)
    preflight = _stop_writer_step(wf, "Transitional task 2.1 stop-writer preflight")
    deploy = next(step for step in steps if step.get("id") == "deploy")
    production_mutation = next(
        step for step in steps if step.get("id") == "production_mutation"
    )
    disk = _step_named(wf, "Preflight droplet disk before image pull")

    assert (
        steps.index(disk)
        < steps.index(preflight)
        < steps.index(production_mutation)
        < steps.index(deploy)
    )
    assert str(preflight.get("id")) == "stop-writer"
    assert str(preflight.get("env", {}).get("NEW_IMAGE", "")).endswith(
        "steps.tag.outputs.image_ref }}"
    )


def test_deploy_shares_production_host_mutation_concurrency_group():
    wf = _load()
    assert wf.get("concurrency") == {
        "group": "production-host-mutation",
        "cancel-in-progress": False,
    }


def test_stop_writer_ancestry_gate_has_complete_git_history():
    wf = _load()
    checkout = next(
        step
        for step in _steps(wf)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout.get("with", {}).get("fetch-depth") == 0


def test_disk_preflight_precedes_every_remote_image_pull():
    wf = _load()
    steps = _steps(wf)
    disk_index = steps.index(_step_named(wf, "Preflight droplet disk before image pull"))
    pull_indexes = []
    for index, step in enumerate(steps):
        for line in str(step.get("run", "")).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "docker pull" in stripped:
                pull_indexes.append(index)
    assert pull_indexes
    assert all(disk_index < index for index in pull_indexes)


def test_stop_writer_workflow_invokes_transitional_helper_subcommands():
    text = _text()
    assert "scripts/retire_cheat_loop_deploy_fence.py" in text
    for command in (
        " preflight --image-ref ",
        " prepare-deploy --image-ref ",
        " prove --image-ref ",
        " post-canary --image-ref ",
        " status",
        " observe",
        " quiesce-unsafe",
        " restore-if-safe --image-ref ",
    ):
        assert command in text


def test_stop_writer_deploy_proves_exact_safe_image_and_drains_old_ids():
    wf = _load()
    preflight = _stop_writer_step(
        wf, "Transitional task 2.1 stop-writer preflight"
    ).get("run", "")
    proof = _stop_writer_step(
        wf, "Transitional task 2.1 prove exact fleet and unchanged receipts"
    ).get("run", "")

    assert "35da9d4fc1a1fc51d3db56bf5d1627691f54d894" in preflight
    assert "org.opencontainers.image.revision" in preflight
    assert "git merge-base --is-ancestor" in preflight
    assert "systemd-run --quiet --collect --wait --pipe" in preflight
    assert "--property RuntimeMaxSec=300" in preflight
    assert "--property TimeoutStartSec=300" in preflight
    assert "--run-id '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}'" in preflight
    assert "prove --image-ref" in proof
    assert "receipt_snapshot_post_deploy.json" in proof


def test_stop_writer_blocks_unsafe_rollback_image():
    wf = _load()
    preflight = _stop_writer_step(
        wf, "Transitional task 2.1 stop-writer preflight"
    )
    rollback = _step_named(wf, "Rollback on failure")

    assert "safe_previous_image" in str(preflight.get("run", ""))
    assert (
        rollback.get("env", {}).get("PREV_IMAGE")
        == "${{ steps.stop-writer.outputs.safe_previous_image }}"
    )
    assert "steps.prev.outputs.previous" not in str(
        rollback.get("env", {}).get("PREV_IMAGE", "")
    )


def test_stop_writer_compares_post_deploy_and_post_canary_snapshots():
    wf = _load()
    steps = _steps(wf)
    deploy_proof = _stop_writer_step(
        wf, "Transitional task 2.1 prove exact fleet and unchanged receipts"
    )
    canary = _step_named(wf, "Post-deploy canary — canonical URL only")
    post_canary = _stop_writer_step(
        wf, "Transitional task 2.1 post-canary receipt proof"
    )
    forward = _step_named(wf, "Mark forward path complete")
    rollback = _step_named(wf, "Rollback on failure")

    assert (
        steps.index(deploy_proof)
        < steps.index(canary)
        < steps.index(post_canary)
        < steps.index(forward)
        < steps.index(rollback)
    )
    preflight = _stop_writer_step(
        wf, "Transitional task 2.1 stop-writer preflight"
    )
    assert "receipt_snapshot_before.json" in str(preflight.get("run", ""))
    assert "receipt_snapshot_post_deploy.json" in str(deploy_proof.get("run", ""))
    assert "receipt_snapshot_post_canary.json" in str(post_canary.get("run", ""))
    assert "post-canary --image-ref" in str(post_canary.get("run", ""))


def test_stop_writer_restores_timers_only_for_safe_fleet_and_uploads_evidence():
    wf = _load()
    restore = _stop_writer_step(
        wf, "Transitional task 2.1 restore restart racers when safe"
    )
    artifact = _step_named(wf, "Upload transitional task 2.1 deploy proof")

    assert str(restore.get("if", "")).strip() == "always()"
    restore_script = str(restore.get("run", ""))
    assert "retire-cheat-loop-deploy-fence.py status" in restore_script
    assert "retire-cheat-loop-deploy-fence.py observe" in restore_script
    assert "retire-cheat-loop-deploy-fence.py quiesce-unsafe" in restore_script
    assert "cleanup_mutation_started=true" in restore_script
    assert "cleanup_safely_fenced=false" in restore_script
    assert "cleanup_safely_fenced=true" in restore_script
    assert restore_script.index("cleanup_safely_fenced=true") > restore_script.index(
        'if [ "$fence_status" -ne 0 ]'
    )
    assert restore_script.index("cleanup_mutation_started=true") < restore_script.index(
        "retire-cheat-loop-deploy-fence.py quiesce-unsafe"
    )
    assert "git merge-base --is-ancestor" in restore_script
    assert "cleanup_restored=true" in restore_script
    assert "masked_units_after" in restore_script
    assert "tinyassets-daemon.service" in restore_script
    assert restore_script.index("git merge-base --is-ancestor") < restore_script.index(
        "restore-if-safe --image-ref"
    )
    assert str(artifact.get("if", "")).strip() == "always()"
    assert (artifact.get("uses") or "").startswith("actions/upload-artifact@")
    assert "retire-cheat-loop-task-2-1" in str(artifact.get("with", {}).get("name", ""))
    assert "stop-writer-evidence" in str(artifact.get("with", {}).get("path", ""))


def test_terminal_never_reports_deployed_without_exact_cleanup_restoration():
    wf = _load()
    terminal = _step_with_run_token(wf, "terminal_receipt_result=")
    assert (
        terminal.get("env", {}).get("STOP_WRITER_CLEANUP_RESTORED")
        == "${{ steps.stop-writer-cleanup.outputs.cleanup_restored }}"
    )
    assert (
        terminal.get("env", {}).get("STOP_WRITER_CLEANUP_MUTATION_STARTED")
        == "${{ steps.stop-writer-cleanup.outputs.cleanup_mutation_started }}"
    )
    assert (
        terminal.get("env", {}).get("STOP_WRITER_CLEANUP_SAFELY_FENCED")
        == "${{ steps.stop-writer-cleanup.outputs.cleanup_safely_fenced }}"
    )
    assert "steps.stop-writer-cleanup.outputs.cleanup_mutation_started" in str(
        terminal.get("env", {}).get("PRODUCTION_MUTATION_STARTED", "")
    )
    script = str(terminal.get("run", ""))
    assert 'if [ "${STOP_WRITER_CLEANUP_RESTORED}" != "true" ]' in script
    assert "export FORWARD_SUCCEEDED=false" not in script
    assert "export FORWARD_CANARY_OUTCOME=failure" not in script
    assert '"cleanup_restored": marker(' in script
    assert '"cleanup_safely_fenced": marker(' in script
    assert '"cleanup_mutation_started": marker(' in script
    assert "{{json .State.Running}}" in script
    cleanup_script = str(
        _step_named(
            wf,
            "Transitional task 2.1 restore restart racers when safe",
        ).get("run", "")
    )
    assert "expected_restored_unit_states" in cleanup_script
    assert "restored != expected" in cleanup_script
    assert 'daemon.get("enabled") != "enabled"' not in cleanup_script


def test_cleanup_derives_cutover_only_from_current_run_generation():
    wf = _load()
    cleanup = _step_named(
        wf,
        "Transitional task 2.1 restore restart racers when safe",
    )
    script = str(cleanup.get("run", ""))
    assert "current_run_cutover_started" in script
    assert "str(bool(status.get(\"state_exists\")))" not in script
    assert "status --run-id '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}'" in script
