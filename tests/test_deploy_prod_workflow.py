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


def test_deploy_resolves_previous_image_to_digest_for_rollback():
    text = _text()
    assert "previous WORKFLOW_IMAGE to immutable rollback ref" in text
    assert "prev_digest=" in text
    assert "prev_image=\"${prev%%:*}\"" in text


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
            assert "steps.prev.outputs.previous != ''" in cond, (
                "rollback must be skipped when no immutable previous image exists"
            )
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


def test_deploy_publishes_release_state_after_canaries_and_access_gate():
    wf = _load()
    steps = _steps(wf)
    names = [s.get("name", "") for s in steps]

    canary_idx = names.index("Post-deploy canary — canonical URL only")
    access_idx = names.index("Verify CF Access gates direct URL (expects 403/401)")
    receipt_idx = names.index("Publish release-state receipt")
    rollback_idx = names.index("Rollback on failure")

    assert canary_idx < receipt_idx < rollback_idx
    assert access_idx < receipt_idx

    receipt_step = steps[receipt_idx]
    run_script = receipt_step.get("run", "") or ""
    step_env = receipt_step.get("env") or {}

    for field in (
        "git_sha",
        "image_tag",
        "image_digest",
        "build_run_id",
        "build_run_url",
        "deploy_run_id",
        "deploy_run_url",
        "config_hash",
        "config_version",
        "schema_migration_rev",
        "canary_bundle_status",
        "deployed_at",
        "rollback_target",
        "actor",
        "repository",
        "workflow_event",
    ):
        assert field in run_script

    assert "SOURCE_SHA" in step_env
    assert "TARGET_IMAGE" in step_env
    assert "PREV_IMAGE" in step_env
    assert "WORKFLOW_EVENT" in step_env
    assert "docker image inspect" in run_script
    assert "sha256sum /etc/workflow/env" in run_script
    assert "docker volume inspect workflow-data" in run_script
    assert "release_state_host_dir" in run_script
    assert "/data/release-state.json" in run_script
    assert "${release_state_host_dir}/release-state.json" in run_script
    assert "/tmp/workflow-release-state.json /data/release-state.json" not in run_script
    assert "canary_bundle_status\": \"passed\"" in run_script


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
        "step that provisions /var/lib/workflow-codex on every deploy "
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
        "container restarts; otherwise the first restart would not "
        "see the persistent bind mount populated."
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
         if line.strip().startswith('chown "$WORKFLOW_UID:$WORKFLOW_GID" "$VOLUME_DIR"')),
        None,
    )
    chmod_line_idx = next(
        (i for i, line in enumerate(body)
         if line.strip().startswith('chmod 700 "$VOLUME_DIR"')),
        None,
    )
    assert chown_line_idx is not None, "chown on $VOLUME_DIR must be present"
    assert chmod_line_idx is not None, "chmod 700 on $VOLUME_DIR must be present"

    # Walk backwards from each line; the most recent unmatched `if [` must
    # NOT be the `[ ! -d "$VOLUME_DIR" ]` branch. Track indent depth via
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
    assert 'mkdir -p "$VOLUME_DIR"' in run_script, (
        "directory creation must use `mkdir -p` so re-running the step "
        "is a no-op when the dir already exists"
    )
    assert 'if [ ! -d "$VOLUME_DIR" ]' in run_script, (
        "dir-create branch must be guarded by an existence check so the "
        "create-log line is skipped when the dir already exists"
    )


def test_codex_volume_step_migrates_from_running_container_once():
    """First deploy after PR #965 onto a live droplet must copy the
    rotated auth.json out of the running workflow-worker into the
    persistent volume. Subsequent deploys skip (auth.json already
    present). No-op when no live source container exists.
    """
    wf = _load()
    step = _codex_volume_step(wf)
    run_script = step.get("run", "") or ""
    assert 'if [ ! -f "$VOLUME_DIR/auth.json" ]' in run_script, (
        "migration branch must be guarded so it fires exactly once"
    )
    assert "docker inspect workflow-worker" in run_script, (
        "migration must check workflow-worker presence before docker cp"
    )
    assert 'docker exec workflow-worker test -f /app/.codex/auth.json' in run_script, (
        "migration must confirm the live container has an auth.json before copying"
    )
    assert "docker cp workflow-worker:/app/.codex/auth.json" in run_script
    assert 'chown "$WORKFLOW_UID:$WORKFLOW_GID" "$VOLUME_DIR/auth.json"' in run_script
    assert 'chmod 600 "$VOLUME_DIR/auth.json"' in run_script


# ---------------------------------------------------------------------------
# PR-128 — Phase 2 capability map sync into /etc/workflow/env
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
        "HAS_GITHUB_PR_CAPABILITY must be derived from the "
        "WORKFLOW_GITHUB_PR_CAPABILITIES secret presence check"
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
    assert "WORKFLOW_GITHUB_PR_CAPABILITIES" in step_env, (
        "Deploy step env must import WORKFLOW_GITHUB_PR_CAPABILITIES "
        "from secrets so the inline ssh sync can pipe the value"
    )
    raw_value = str(step_env["WORKFLOW_GITHUB_PR_CAPABILITIES"])
    assert "secrets.WORKFLOW_GITHUB_PR_CAPABILITIES" in raw_value


def test_deploy_step_syncs_github_pr_capabilities_when_set():
    """When ``HAS_GITHUB_PR_CAPABILITY=true``, the Deploy step must
    pipe the secret into install-workflow-env.sh via the same atomic
    helper used for WORKFLOW_CODEX_AUTH_JSON_B64."""
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
        "deploy must gate the WORKFLOW_GITHUB_PR_CAPABILITIES sync on "
        "HAS_GITHUB_PR_CAPABILITY=true so absence is a warning, not "
        "an unbound-variable failure"
    )
    assert (
        'printf \'%s\' "${WORKFLOW_GITHUB_PR_CAPABILITIES}"'
        in run_script
    ), (
        "deploy must pipe the secret via printf '%s' so the value is "
        "never echoed to the GH Actions log (matches the codex-auth "
        "pattern)"
    )
    assert (
        "install-workflow-env.sh set WORKFLOW_GITHUB_PR_CAPABILITIES"
        in run_script
    ), (
        "deploy must call the atomic install-workflow-env.sh helper "
        "(the same path that enforces root:workflow 640 + post-write "
        "readability) to write the capability map"
    )
    assert (
        "WORKFLOW_GITHUB_PR_CAPABILITIES is not visible to deploy"
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
        "WORKFLOW_GITHUB_PR_CAPABILITIES visible to deploy"
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
    codex_marker = "set WORKFLOW_CODEX_AUTH_JSON_B64"
    cap_marker = "set WORKFLOW_GITHUB_PR_CAPABILITIES"
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
    ``WORKFLOW_GITHUB_PR_CAPABILITIES`` was absent but did NOT remove
    the existing key from ``/etc/workflow/env``, so deleting the GH
    Actions secret to revoke had no effect — the next deploy
    restarted the daemon with the OLD capability still active.

    The fix: when ``HAS_GITHUB_PR_CAPABILITY=false`` (or unset), the
    Deploy step must issue an explicit
    ``install-workflow-env.sh delete WORKFLOW_GITHUB_PR_CAPABILITIES``
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
        "install-workflow-env.sh delete WORKFLOW_GITHUB_PR_CAPABILITIES"
        in run_script
    ), (
        "Deploy step must issue an explicit `install-workflow-env.sh "
        "delete WORKFLOW_GITHUB_PR_CAPABILITIES` call when the secret "
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
    set_marker = "install-workflow-env.sh set WORKFLOW_GITHUB_PR_CAPABILITIES"
    delete_marker = (
        "install-workflow-env.sh delete WORKFLOW_GITHUB_PR_CAPABILITIES"
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
        or "delete WORKFLOW_GITHUB_PR_CAPABILITIES" in run_script
    ), (
        "the absence warning must describe the revocation action so "
        "operators can confirm capability was actually cleared from "
        "/etc/workflow/env, not just absent from GH Actions"
    )
