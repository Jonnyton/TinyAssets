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


def test_deploy_resolves_image_to_digest_and_never_latest():
    text = _text()
    assert "image_ref=" in text
    assert "docker buildx imagetools inspect" in text
    assert "tag=\"latest\"" not in text
    assert ":latest" not in text, (
        "deploy-prod must not use :latest for deploy or rollback targets"
    )


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
        (
            candidate
            for candidate in _steps(wf)
            if token in (candidate.get("run", "") or "")
        ),
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
    assert "image_mutation_started" in str(
        step_env.get("IMAGE_MUTATION_STARTED", "")
    ), "rollback eligibility must consume the image-mutation marker"
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
        i for i, name in enumerate(names)
        if name == "Preflight droplet disk before image pull"
    )
    deploy_idx = next(
        i for i, step in enumerate(steps)
        if step.get("id") == "deploy"
    )

    assert preflight_idx < deploy_idx, (
        "disk preflight must happen before TINYASSETS_IMAGE is changed, "
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
        "BACKUP_DEST",
        "BACKUP_GH_REPO",
        "LOG_DEST",
    ):
        assert key in run_script


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
        (
            i
            for i, s in enumerate(steps)
            if s.get("name") == "Retire legacy Workflow service"
        ),
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
    assert "rm -f \"$unit_file\"" in run_script
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
    assert "::warning::No deploy-visible TINYASSETS_CODEX_AUTH_JSON_B64" not in run_script


def test_production_marker_is_immediately_before_first_scrub_host_write():
    wf = _load()
    scrub_step = _step_named(wf, "Scrub stale cloud env overrides")
    run_script = scrub_step.get("run", "") or ""
    lines = run_script.splitlines()
    first_host_write = next(
        i for i, line in enumerate(lines) if line.strip().startswith("ssh ")
    )
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
    while (
        command_start > 0
        and lines[command_start - 1].rstrip().endswith("\\")
    ):
        command_start -= 1
    marker_line = _previous_executable_line(lines, command_start)

    assert "image_mutation_started=true" in marker_line
    assert "GITHUB_OUTPUT" in marker_line


def test_rollback_and_terminal_receipt_are_ordered_under_always():
    wf = _load()
    steps = _steps(wf)
    canary_step = _step_named(wf, "Post-deploy canary — canonical URL only")
    access_step = _step_named(
        wf, "Verify CF Access gates direct URL (expects 403/401)"
    )
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


def test_terminal_receipt_keys_to_production_marker():
    wf = _load()
    scrub_step = _step_named(wf, "Scrub stale cloud env overrides")
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    step_env = terminal_step.get("env") or {}
    run_script = terminal_step.get("run", "") or ""

    expected_ref = (
        f"steps.{scrub_step['id']}.outputs.production_mutation_started"
    )
    assert expected_ref in str(
        step_env.get("PRODUCTION_MUTATION_STARTED", "")
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
        first_helper_call = run_script.find(
            output_helper, helper_definition + len(output_helper)
        )
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


def test_terminal_receipt_invokes_pure_helper_and_preserves_atomic_writer():
    wf = _load()
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    run_script = terminal_step.get("run", "") or ""

    helper_idx = run_script.find("python scripts/deploy_terminal_receipt.py")
    transfer_idx = run_script.find("scp ")
    install_idx = run_script.find("install -m 0644 -o 1001 -g 1001")
    assert helper_idx != -1, (
        "terminal publication must invoke the directly executable pure "
        "classifier/builder"
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
    not_applicable_idx = run_script.find(
        "terminal_receipt_result=not_applicable"
    )
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


def test_deploy_failure_issue_consumes_rollback_and_terminal_outputs():
    wf = _load()
    rollback_step = _step_named(wf, "Rollback on failure")
    terminal_step = _step_with_run_token(wf, "terminal_receipt_result=")
    issue_step = _step_named(wf, "Open deploy-failed issue")
    assert rollback_step.get("id"), "rollback outputs require a stable step id"
    assert terminal_step.get("id"), "terminal outputs require a stable step id"

    cond = str(issue_step.get("if", ""))
    env_text = "\n".join(
        str(value) for value in (issue_step.get("env") or {}).values()
    )
    assert "always()" in cond and "failure()" in cond, (
        "the issue must still run after a red rollback or terminal writer"
    )
    for output_name in (
        "rollback_attempted",
        "rollback_result",
        "rollback_canary_status",
        "rollback_reason",
    ):
        assert (
            f"steps.{rollback_step['id']}.outputs.{output_name}" in env_text
        ), f"deploy-failed issue must consume {output_name}"
    for output_name in (
        "terminal_receipt_result",
        "terminal_outcome",
        "terminal_active_identity_status",
        "terminal_canary_status",
        "terminal_configured_image_ref",
        "terminal_running_image_ref",
        "terminal_active_image_ref",
    ):
        assert (
            f"steps.{terminal_step['id']}.outputs.{output_name}" in env_text
        ), f"deploy-failed issue must consume {output_name}"


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
        (
            "Rollback status is unavailable; rollback success was not proven."
        ),
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
        (
            s for s in _steps(wf)
            if s.get("name") == "Prepare codex auth persistent volume"
        ),
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
    deploy_idx = next(
        i for i, step in enumerate(steps)
        if step.get("id") == "deploy"
    )
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
    end = next(
        (i for i, line in enumerate(lines[start + 1:], start=start + 1)
         if line.strip() == "SH"),
        None,
    ) if start is not None else None
    assert start is not None and end is not None, (
        "Could not locate heredoc body in 'Prepare codex auth persistent volume'"
    )
    body = lines[start + 1: end]

    chown_line_idx = next(
        (i for i, line in enumerate(body)
         if line.strip().startswith('chown "$TINYASSETS_UID:$TINYASSETS_GID" "$CODEX_DIR"')),
        None,
    )
    chmod_line_idx = next(
        (i for i, line in enumerate(body)
         if line.strip().startswith('chmod 700 "$CODEX_DIR"')),
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
        f"chmod line must sit at heredoc base indent ({base_indent}); "
        f"got indent {chmod_indent}."
    )


def test_codex_volume_step_creates_dir_idempotently():
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""
    assert 'docker volume create "$VOLUME_NAME"' in run_script, (
        "tinyassets-data named volume must be created idempotently before "
        "resolving its mountpoint"
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
    assert 'docker exec tinyassets-worker test -f /data/.codex/auth.json' in run_script, (
        "migration must check the new CODEX_HOME path before copying"
    )
    assert 'docker exec tinyassets-worker test -f /app/.codex/auth.json' in run_script, (
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
    assert 'docker exec tinyassets-worker test -d /data/.claude' in run_script
    assert 'docker exec tinyassets-worker test -d /app/.claude' in run_script
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
    assert "secrets.TINYASSETS_GITHUB_PR_CAPABILITIES" in raw_value, (
        "HAS_GITHUB_PR_CAPABILITY must be derived from the "
        "TINYASSETS_GITHUB_PR_CAPABILITIES secret presence check"
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
    assert "TINYASSETS_GITHUB_PR_CAPABILITIES" in step_env, (
        "Deploy step env must import TINYASSETS_GITHUB_PR_CAPABILITIES "
        "from secrets so the inline ssh sync can pipe the value"
    )
    raw_value = str(step_env["TINYASSETS_GITHUB_PR_CAPABILITIES"])
    assert "secrets.TINYASSETS_GITHUB_PR_CAPABILITIES" in raw_value


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
        "deploy must gate the TINYASSETS_GITHUB_PR_CAPABILITIES sync on "
        "HAS_GITHUB_PR_CAPABILITY=true so absence is a warning, not "
        "an unbound-variable failure"
    )
    assert (
        'printf \'%s\' "${TINYASSETS_GITHUB_PR_CAPABILITIES}"'
        in run_script
    ), (
        "deploy must pipe the secret via printf '%s' so the value is "
        "never echoed to the GH Actions log (matches the codex-auth "
        "pattern)"
    )
    assert (
        "install-tinyassets-env.sh set TINYASSETS_GITHUB_PR_CAPABILITIES"
        in run_script
    ), (
        "deploy must call the atomic install-tinyassets-env.sh helper "
        "(the same path that enforces root:tinyassets 640 + post-write "
        "readability) to write the capability map"
    )
    assert (
        "TINYASSETS_GITHUB_PR_CAPABILITIES is not visible to deploy"
        in run_script
    ), (
        "deploy must emit a structured ::warning:: when the secret is "
        "absent so the operator notices before chatbots try real-PR "
        "emission and see missing_capability dry-run evidence"
    )


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
    assert (
        "TINYASSETS_GITHUB_PR_CAPABILITIES visible to deploy"
        in run_script
    ), (
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
    cap_marker = "set TINYASSETS_GITHUB_PR_CAPABILITIES"
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
    assert (
        "install-tinyassets-env.sh delete TINYASSETS_GITHUB_PR_CAPABILITIES"
        in run_script
    ), (
        "Deploy step must issue an explicit `install-tinyassets-env.sh "
        "delete TINYASSETS_GITHUB_PR_CAPABILITIES` call when the secret "
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
    set_marker = "install-tinyassets-env.sh set TINYASSETS_GITHUB_PR_CAPABILITIES"
    delete_marker = (
        "install-tinyassets-env.sh delete TINYASSETS_GITHUB_PR_CAPABILITIES"
    )
    set_idx = run_script.find(set_marker)
    delete_idx = run_script.find(delete_marker)
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
    between = run_script[set_idx + len(set_marker):delete_idx]
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
