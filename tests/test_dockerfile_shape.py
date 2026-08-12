"""Tests for Dockerfile shape and env wiring.

Verifies:
- codex CLI install layer is present in the Dockerfile
- nodejs runtime is included in the final stage
- TINYASSETS_CODEX_AUTH_JSON_B64 is referenced in tinyassets-env.template
- OPENAI_API_KEY remains a blank deprecated placeholder
- compose.yml env_file passes /etc/tinyassets/env to the daemon service
- The codex module copy layer is present

These are static text-parse tests — they don't require Docker to be
installed and run in < 0.1s.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
GITIGNORE = REPO_ROOT / ".gitignore"
COMPOSE = REPO_ROOT / "deploy" / "compose.yml"
ENV_TEMPLATE = REPO_ROOT / "deploy" / "tinyassets-env.template"
ENTRYPOINT = REPO_ROOT / "deploy" / "docker-entrypoint.sh"
CODEX_KEEPALIVE = REPO_ROOT / ".github" / "workflows" / "codex-auth-keepalive.yml"
CLAUDE_KEEPALIVE = REPO_ROOT / ".github" / "workflows" / "claude-auth-keepalive.yml"
CODEX_PROVIDER = REPO_ROOT / "tinyassets" / "providers" / "codex_provider.py"


# ---------------------------------------------------------------------------
# Dockerfile — codex CLI presence
# ---------------------------------------------------------------------------


def test_dockerfile_installs_codex_npm():
    """Builder stage must install @openai/codex via npm."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "@openai/codex" in text, (
        "Dockerfile must install @openai/codex — required by codex_provider.py"
    )
    assert "CODEX_CLI_VERSION=0." in text, (
        "Dockerfile must pin the Codex CLI package version for reproducible builds"
    )


def test_dockerfile_installs_claude_code_npm():
    """Builder stage must install Claude Code CLI via npm."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "@anthropic-ai/claude-code" in text, (
        "Dockerfile must install Claude Code CLI for claude_provider.py"
    )
    assert "CLAUDE_CODE_CLI_VERSION=2." in text, (
        "Dockerfile must pin Claude Code CLI package version"
    )


def test_dockerfile_builder_has_nodejs_for_npm():
    """Builder stage must include nodejs + npm to run npm install."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "nodesource" in text, (
        "Dockerfile must use nodesource to install Node.js 20 "
        "(Debian default nodejs is too old for @openai/codex)"
    )
    assert "NODEJS_VERSION=20." in text, (
        "Dockerfile must pin the exact NodeSource nodejs package version"
    )


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
    assert "GH_VERSION=2." in text, (
        "Final image stage must pin the GitHub CLI package version"
    )


def test_dockerfile_base_images_are_digest_pinned():
    """Both stages must use an immutable python base image digest."""
    from_lines = [
        line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]
    assert from_lines, "Dockerfile must contain FROM lines"
    assert all("@sha256:" in line for line in from_lines), (
        "Dockerfile FROM images must be pinned by digest, not mutable tags"
    )


def test_dockerfile_does_not_pipe_remote_installers_to_shell():
    """Build-time installers must be fetched/verified explicitly."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    executable_text = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert re.search(r"\|\s*(?:ba)?sh\b", executable_text) is None
    assert "RUSTUP_SHA256" in text
    assert "NODESOURCE_REPO_CHECKSUM" in text


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


def test_dockerfile_copies_claude_binary():
    """Final stage must COPY Claude Code install tree from builder."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY --from=builder /opt/claude-code-install /opt/claude-code-install" in text
    assert "ln -s /opt/claude-code-install/node_modules/.bin/claude /usr/local/bin/claude" in text


def test_dockerfile_codex_version_smoke():
    """Builder stage must run 'codex --version' to verify install."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "codex --version" in text, (
        "Dockerfile must run 'codex --version' after install to catch broken installs"
    )


def test_dockerfile_claude_version_smoke():
    """Builder/final stage must run 'claude --version' to verify install."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "claude --version" in text, (
        "Dockerfile must run 'claude --version' after install to catch broken installs"
    )


# ---------------------------------------------------------------------------
# Dockerfile — launch-scoped provider credentials
# ---------------------------------------------------------------------------


def test_dockerfile_installs_provider_clis_without_shared_auth_wrapper():
    """Provider CLIs run with the assigned credential's private snapshot."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "ln -s /opt/codex-install/node_modules/.bin/codex /usr/local/bin/codex" in text, (
        "Dockerfile must expose the installed Codex CLI directly"
    )
    assert "codex-flock-wrapper" not in text, (
        "worker-free execution must not serialize a shared host auth directory"
    )
    wrapper = REPO_ROOT / "deploy" / "codex-flock-wrapper.sh"
    assert not wrapper.exists(), (
        "the retired cross-container auth wrapper must not remain in deploy/"
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
        "tinyassets.api.universe._bundled_source_root() in the container"
    )


def test_dockerignore_allows_plan_md_into_context():
    """The broad *.md ignore must explicitly unignore PLAN.md."""
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    assert "*.md" in text
    assert "!PLAN.md" in text, (
        ".dockerignore must unignore PLAN.md; otherwise Docker COPY PLAN.md "
        "works locally but fails in CI build context"
    )


def test_local_git_credentials_stay_out_of_git_and_docker_context():
    """Local Git credential helpers must not be stageable or sent to Docker."""
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    dockerignore = DOCKERIGNORE.read_text(encoding="utf-8")

    assert "*git-credentials*" in gitignore, (
        ".gitignore must catch local Git credential helper files before staging"
    )
    assert "*credentials*" in dockerignore, (
        ".dockerignore must catch credential files even when the basename has "
        "a host/tool prefix"
    )


# ---------------------------------------------------------------------------
# tinyassets-env.template — subscription auth + deprecated API-key placeholder
# ---------------------------------------------------------------------------


def test_env_template_has_no_platform_provider_credentials():
    """Cloud host configuration must not offer an ambient LLM route."""
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    for forbidden in (
        "TINYASSETS_CODEX_AUTH_JSON_B64",
        "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "OPENAI_API_KEY",
        "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
    ):
        assert forbidden not in text


# ---------------------------------------------------------------------------
# compose.yml — env_file wiring
# ---------------------------------------------------------------------------


def test_compose_daemon_uses_env_file():
    """daemon service in compose.yml must load /etc/tinyassets/env."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "/etc/tinyassets/env" in text, (
        "compose.yml daemon service must reference /etc/tinyassets/env as env_file "
        "so subscription auth material and other secrets are passed to the container"
    )


def test_compose_requires_explicit_daemon_image_without_latest_default():
    """The daemon must not silently pull mutable :latest."""
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    for service_name in ("daemon",):
        image = data["services"][service_name].get("image", "")
        assert "${TINYASSETS_IMAGE:?" in image, (
            f"{service_name} image must require TINYASSETS_IMAGE instead of "
            "defaulting to ghcr.io/jonnyton/tinyassets-daemon:latest"
        )
        assert ":latest" not in image


def test_compose_sidecar_images_are_digest_pinned():
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    for service_name in ("cloudflared", "logs"):
        image = data["services"][service_name].get("image", "")
        assert "@sha256:" in image, (
            f"{service_name} image must pin the version tag by digest"
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
    assert any("/etc/tinyassets/env" in v for v in env_file_values), (
        "daemon service env_file must include /etc/tinyassets/env"
    )


def test_compose_has_no_ambient_codex_auth_home():
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    for service_name, service in data["services"].items():
        environment = service.get("environment") or {}
        assert "CODEX_HOME" not in environment, service_name


def test_compose_has_no_ambient_claude_config_dir():
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    for service_name, service in data["services"].items():
        environment = service.get("environment") or {}
        assert "CLAUDE_CONFIG_DIR" not in environment, service_name


def test_compose_declares_no_cloud_llm_workers():
    yaml = __import__("yaml")
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    assert not any(name == "worker" or name.startswith("worker-") for name in services)
    assert {"daemon", "cloudflared", "logs"} <= set(services)


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


def test_entrypoint_strips_codex_auth_bundle():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "TINYASSETS_CODEX_AUTH_JSON_B64" in text
    assert 'unset "${_name}"' in text
    assert "base64 -d" not in text


def test_entrypoint_strips_claude_config_dir():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "CLAUDE_CONFIG_DIR" in text
    assert 'unset "${_name}"' in text


def test_entrypoint_does_not_materialize_codex_credentials():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert 'cli_auth_credentials_store = "file"' not in text
    assert "auth.json" not in text


def test_entrypoint_does_not_login_with_api_key():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    executable_text = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "codex login" not in executable_text
    assert "--with-api-key" not in executable_text, (
        "default TinyAssets daemons must not authenticate Codex with OPENAI_API_KEY"
    )


def test_entrypoint_strips_api_key_providers_unconditionally():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "TINYASSETS_ALLOW_API_KEY_PROVIDERS" in text
    assert "OPENAI_API_KEY" in text
    assert 'unset "${_name}"' in text, (
        "entrypoint must strip API-key provider env vars"
    )


def test_entrypoint_never_seeds_auth_bundle():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "mktemp" not in text
    assert "base64 -d" not in text


def test_ambient_host_auth_keepalive_workflows_are_removed():
    assert not CODEX_KEEPALIVE.exists()
    assert not CLAUDE_KEEPALIVE.exists()


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
