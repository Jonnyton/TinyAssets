"""Tests for Dockerfile shape and env wiring.

Verifies:
- codex CLI install layer is present in the Dockerfile
- nodejs runtime is included in the final stage
- WORKFLOW_CODEX_AUTH_JSON_B64 is referenced in workflow-env.template
- OPENAI_API_KEY remains a blank deprecated placeholder
- compose.yml env_file passes /etc/workflow/env to the daemon service
- The codex module copy layer is present

These are static text-parse tests — they don't require Docker to be
installed and run in < 0.1s.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
COMPOSE = REPO_ROOT / "deploy" / "compose.yml"
ENV_TEMPLATE = REPO_ROOT / "deploy" / "workflow-env.template"
ENTRYPOINT = REPO_ROOT / "deploy" / "docker-entrypoint.sh"
CODEX_KEEPALIVE = REPO_ROOT / ".github" / "workflows" / "codex-auth-keepalive.yml"
CODEX_PROVIDER = REPO_ROOT / "workflow" / "providers" / "codex_provider.py"


# ---------------------------------------------------------------------------
# Dockerfile — codex CLI presence
# ---------------------------------------------------------------------------


def test_dockerfile_installs_codex_npm():
    """Builder stage must install @openai/codex via npm."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "@openai/codex" in text, (
        "Dockerfile must install @openai/codex — required by codex_provider.py"
    )


def test_dockerfile_builder_has_nodejs_for_npm():
    """Builder stage must include nodejs + npm to run npm install."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "nodesource" in text, (
        "Dockerfile must use nodesource to install Node.js 20 "
        "(Debian default nodejs is too old for @openai/codex)"
    )
    assert "setup_20.x" in text, "Dockerfile must pin Node.js 20 via setup_20.x"


def test_dockerfile_final_stage_has_nodejs_runtime():
    """Final stage must ship nodejs so the codex CLI (Node.js binary) can run."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    # The final stage starts at 'FROM python:3.11-slim' (second FROM).
    # Assert nodejs appears after the second FROM.
    froms = [i for i, line in enumerate(text.splitlines()) if line.startswith("FROM ")]
    assert len(froms) >= 2, "Expected at least 2 FROM stages"
    final_stage_text = "\n".join(text.splitlines()[froms[1]:])
    assert "nodejs" in final_stage_text, (
        "Final image stage must install nodejs runtime for codex CLI"
    )


def test_dockerfile_copies_codex_binary():
    """Final stage must COPY codex install tree from builder."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY --from=builder" in text, (
        "Dockerfile must COPY codex from builder to final stage"
    )
    # Codex is installed to /opt/codex-install in the builder; that dir is COPY'd.
    copy_lines = [
        line for line in text.splitlines()
        if line.strip().startswith("COPY --from=builder") and "codex-install" in line
    ]
    assert copy_lines, (
        "Expected a 'COPY --from=builder /opt/codex-install ...' line in final stage"
    )


def test_dockerfile_codex_version_smoke():
    """Builder stage must run 'codex --version' to verify install."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "codex --version" in text, (
        "Dockerfile must run 'codex --version' after install to catch broken installs"
    )


# ---------------------------------------------------------------------------
# Dockerfile — codex flock wrapper (PR #965 Codex round-2 Finding 1)
# ---------------------------------------------------------------------------


def test_dockerfile_installs_codex_flock_wrapper():
    """Final stage must install deploy/codex-flock-wrapper.sh as /usr/local/bin/codex.

    compose sets CODEX_HOME=/data/.codex across daemon + worker.
    Codex's official CI/CD auth guide forbids sharing one
    auth.json across concurrent runners; the wrapper serializes
    invocations via an exclusive flock on CODEX_HOME/.lock.

    Round-1 of PR #965 used a bare symlink (`ln -s ... /usr/local/bin/codex`),
    which is the exact pattern Codex Issue #10332 calls out as broken
    when the auth dir is shared. The wrapper replaces it.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY deploy/codex-flock-wrapper.sh /usr/local/bin/codex" in text, (
        "Dockerfile must COPY deploy/codex-flock-wrapper.sh to /usr/local/bin/codex "
        "so every `codex` invocation goes through the cross-container flock"
    )
    # The legacy bare symlink must be gone. Regression guard.
    assert "ln -s /opt/codex-install/node_modules/.bin/codex /usr/local/bin/codex" not in text, (
        "Dockerfile must not install codex via bare symlink; concurrent "
        "containers sharing CODEX_HOME would race the OAuth refresh "
        "(Codex Issue #10332). Use the flock wrapper instead."
    )


def test_dockerfile_installs_util_linux_for_flock():
    """flock(1) lives in util-linux. The final stage apt layer must include it
    explicitly so the wrapper works even if the base image trims util-linux
    in a future python-slim revision.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "util-linux" in text, (
        "Final stage must apt-install util-linux; flock(1) is part of "
        "that package and codex-flock-wrapper.sh exec's flock on every call"
    )


def test_codex_flock_wrapper_script_present():
    """The wrapper script itself must exist + be executable + lock the shared dir."""
    wrapper = REPO_ROOT / "deploy" / "codex-flock-wrapper.sh"
    assert wrapper.exists(), "deploy/codex-flock-wrapper.sh must exist"
    text = wrapper.read_text(encoding="utf-8")
    # Bash strict-mode header.
    assert text.startswith("#!/usr/bin/env bash"), (
        "wrapper must declare #!/usr/bin/env bash shebang"
    )
    assert "set -euo pipefail" in text, "wrapper must use strict bash"
    # Lock target must live next to auth.json so the shared CODEX_HOME
    # makes the lock visible across containers.
    assert "CODEX_HOME" in text and ".lock" in text, (
        "wrapper must lock a sentinel inside the codex auth directory"
    )
    assert "flock -x" in text, (
        "wrapper must use exclusive flock (`flock -x`) — shared locks "
        "would not serialize refresh writes"
    )
    # The actual codex binary should be the exec target.
    assert "/opt/codex-install/node_modules/.bin/codex" in text, (
        "wrapper must exec the real codex bin under flock"
    )
    assert text.rstrip().endswith('exec flock -x "${LOCK_FILE}" "${CODEX_BIN}" "$@"'), (
        "wrapper's final line must `exec flock -x ... codex \"$@\"` so the "
        "wrapper process is replaced (no double-fork) and signals + exit codes "
        "propagate from codex to the daemon/worker caller"
    )


def test_dockerfile_ships_plan_md_for_live_review_context():
    """PLAN.md must be present at /app/PLAN.md in the runtime image."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY PLAN.md ./" in text, (
        "Builder stage must copy PLAN.md so review-context tools can include "
        "architecture sections in the deployed MCP response"
    )
    assert "COPY --from=builder /build/PLAN.md /app/PLAN.md" in text, (
        "Final image must place PLAN.md at /app/PLAN.md, matching "
        "workflow.api.universe._repo_root() in the container"
    )


def test_dockerignore_allows_plan_md_into_context():
    """The broad *.md ignore must explicitly unignore PLAN.md."""
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    assert "*.md" in text
    assert "!PLAN.md" in text, (
        ".dockerignore must unignore PLAN.md; otherwise Docker COPY PLAN.md "
        "works locally but fails in CI build context"
    )


# ---------------------------------------------------------------------------
# workflow-env.template — subscription auth + deprecated API-key placeholder
# ---------------------------------------------------------------------------


def test_env_template_has_codex_subscription_auth_bundle():
    """workflow-env.template must include a Codex subscription auth placeholder."""
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in text, (
        "workflow-env.template must expose the Codex subscription auth bundle path"
    )


def test_env_template_has_openai_api_key():
    """workflow-env.template keeps OPENAI_API_KEY as a deprecated placeholder."""
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in text, (
        "workflow-env.template must mention OPENAI_API_KEY so operators know it is deprecated"
    )


def test_env_template_openai_key_is_placeholder():
    """OPENAI_API_KEY line must be blank (placeholder, not a real key)."""
    for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            value = line.split("=", 1)[1].strip()
            assert value == "", (
                f"OPENAI_API_KEY must be a blank placeholder; found: {value!r}"
            )
            return
    raise AssertionError("OPENAI_API_KEY= line not found in workflow-env.template")


# ---------------------------------------------------------------------------
# compose.yml — env_file wiring
# ---------------------------------------------------------------------------


def test_compose_daemon_uses_env_file():
    """daemon service in compose.yml must load /etc/workflow/env."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "/etc/workflow/env" in text, (
        "compose.yml daemon service must reference /etc/workflow/env as env_file "
        "so subscription auth material and other secrets are passed to the container"
    )


def test_compose_env_file_covers_daemon_service():
    """The env_file stanza must be in the daemon service block, not just cloudflared."""
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    daemon_env_files = data["services"]["daemon"].get("env_file", [])
    env_file_values = [
        ef if isinstance(ef, str) else ef.get("path", "")
        for ef in daemon_env_files
    ]
    assert any("/etc/workflow/env" in v for v in env_file_values), (
        "daemon service env_file must include /etc/workflow/env"
    )


def test_compose_codex_auth_home_is_shared_data_volume():
    """Services that invoke codex must share one persistent CODEX_HOME."""
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    for service_name in ("daemon", "worker"):
        service = data["services"][service_name]
        environment = service.get("environment") or {}
        volumes = service.get("volumes") or []
        assert environment.get("CODEX_HOME") == "/data/.codex", (
            f"{service_name} must use /data/.codex so Codex CLI and "
            "get_status look at the persistent workflow-data volume"
        )
        assert "workflow-data:/data" in volumes, (
            f"{service_name} must mount workflow-data at /data"
        )
        assert "/var/lib/workflow-codex:/app/.codex" not in volumes


# ---------------------------------------------------------------------------
# codex_provider.py — --skip-git-repo-check flag (BUG-004 fix A)
# ---------------------------------------------------------------------------


def test_codex_provider_has_skip_git_repo_check():
    """codex exec must pass --skip-git-repo-check so it works outside a git repo."""
    text = CODEX_PROVIDER.read_text(encoding="utf-8")
    assert "--skip-git-repo-check" in text, (
        "codex_provider.py must pass --skip-git-repo-check to 'codex exec'; "
        "without it codex v0.122+ refuses to run in /app (not a git repo)"
    )


def test_codex_provider_flag_is_on_exec_command():
    """--skip-git-repo-check must be on the exec invocation, not a separate call."""
    text = CODEX_PROVIDER.read_text(encoding="utf-8")
    start = text.index("cmd = [")
    end = text.index("]", start)
    cmd_block = text[start:end]
    assert '"exec"' in cmd_block
    assert "--skip-git-repo-check" in cmd_block
    assert "*sandbox_args" in cmd_block
    assert "--full-auto" in text
    assert "--dangerously-bypass-approvals-and-sandbox" in text


# ---------------------------------------------------------------------------
# docker-entrypoint.sh — subscription auth baked in (BUG-004 fix B)
# ---------------------------------------------------------------------------


def test_entrypoint_script_exists():
    assert ENTRYPOINT.exists(), f"Missing: {ENTRYPOINT}"


def test_entrypoint_installs_codex_auth_bundle():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in text
    assert 'CODEX_HOME="${CODEX_HOME:-/data/.codex}"' in text
    assert "base64 -d" in text
    assert "auth.json" in text, (
        "docker-entrypoint.sh must install the subscription-backed Codex auth bundle"
    )


def test_entrypoint_pins_codex_file_credentials_store():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'cli_auth_credentials_store = "file"' in text, (
        "container auth must use file-backed Codex credentials under CODEX_HOME"
    )


def test_entrypoint_does_not_login_with_api_key():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    executable_text = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "codex login" not in executable_text
    assert "--with-api-key" not in executable_text, (
        "default Workflow daemons must not authenticate Codex with OPENAI_API_KEY"
    )


def test_entrypoint_strips_api_key_providers_by_default():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "WORKFLOW_ALLOW_API_KEY_PROVIDERS" in text
    assert "OPENAI_API_KEY" in text
    assert 'unset "${_name}"' in text, (
        "entrypoint must strip API-key provider env vars unless explicitly enabled"
    )


def test_entrypoint_replaces_auth_bundle_atomically():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "mktemp" in text
    assert "mv " in text
    assert "failed to decode WORKFLOW_CODEX_AUTH_JSON_B64" in text, (
        "entrypoint must atomically replace Codex auth when a bundle is provided"
    )


def test_codex_auth_keepalive_exercises_shared_codex_home():
    text = CODEX_KEEPALIVE.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "schedule:" in text
    assert "DO_SSH_KEY" in text
    assert "docker exec -e CODEX_HOME=/data/.codex workflow-daemon codex exec" in text


def test_entrypoint_execs_cmd():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'exec "$@"' in text, (
        "entrypoint must end with exec \"$@\" to preserve tini PID-1 signal forwarding"
    )


def test_dockerfile_copies_entrypoint():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "docker-entrypoint.sh" in text, (
        "Dockerfile must COPY docker-entrypoint.sh into the image"
    )


def test_dockerfile_entrypoint_uses_entrypoint_script():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "docker-entrypoint.sh" in text, (
        "Dockerfile ENTRYPOINT must invoke docker-entrypoint.sh"
    )
    # tini must still be PID 1
    assert "tini" in text, "tini must remain as PID 1 in ENTRYPOINT"
