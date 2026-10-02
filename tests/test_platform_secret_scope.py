"""The daemon and its children hold none of the platform's own secrets.

Found 2026-10-02: the production daemon and its engine MCP children carried the
account-wide DigitalOcean token, the live Stripe key, the tunnel token and the
WorkOS key in their environment, because the daemon loaded the box's whole env
file and the engine server copied ``os.environ``
(docs/concerns/2026-10-02-platform-secrets-in-daemon-env.md).

Values never appear here: every fixture value is a placeholder and every
assertion is on names.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tinyassets import platform_secrets
from tinyassets.platform_secrets import (
    CHILD_FORBIDDEN_ENV,
    DAEMON_FORBIDDEN_ENV,
    DAEMON_ONLY_ENV,
    child_env,
)

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "deploy" / "install-tinyassets-env.sh"
COMPOSE = REPO / "deploy" / "compose.yml"
PACKAGE = REPO / "tinyassets"

_POSIX_SHELL = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI",
)


def _shell_forbidden() -> set[str]:
    text = HELPER.read_text(encoding="utf-8")
    match = re.search(r"^DAEMON_FORBIDDEN_ENV=\(\n(.*?)^\)", text, re.S | re.M)
    assert match, "DAEMON_FORBIDDEN_ENV array not found in install-tinyassets-env.sh"
    return {line.strip() for line in match.group(1).splitlines() if line.strip()}


# ---------------------------------------------------------------------------
# the lists
# ---------------------------------------------------------------------------


def test_the_reported_secrets_are_scoped():
    assert {"DO_API_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN"} <= DAEMON_FORBIDDEN_ENV
    assert {"STRIPE_SECRET_KEY", "WORKOS_API_KEY"} <= DAEMON_ONLY_ENV
    assert DAEMON_FORBIDDEN_ENV | DAEMON_ONLY_ENV <= CHILD_FORBIDDEN_ENV


def test_shell_and_python_forbid_the_same_names():
    assert _shell_forbidden() == set(DAEMON_FORBIDDEN_ENV)


def _readers(name: str) -> set[str]:
    own = Path(platform_secrets.__file__).resolve()
    found = set()
    for path in PACKAGE.rglob("*.py"):
        if path.resolve() == own:
            continue
        if name in path.read_text(encoding="utf-8", errors="replace"):
            found.add(path.relative_to(REPO).as_posix())
    return found


#: Reads a forbidden name but is never imported by the daemon (asserted below).
_UNIMPORTED_READERS = {"tinyassets/host_pool/client.py"}


@pytest.mark.parametrize("name", sorted(DAEMON_FORBIDDEN_ENV))
def test_no_daemon_code_reads_a_forbidden_name(name):
    """Removing a name from the daemon is safe only while nothing reads it."""
    assert _readers(name) - _UNIMPORTED_READERS == set(), (
        f"{name} is now read by daemon code; it cannot be withheld from the daemon"
    )


def test_host_pool_is_not_imported_by_the_daemon():
    importers = {
        path.relative_to(REPO).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "host_pool" not in path.parts
        and re.search(
            r"^\s*(?:from|import)\s+[\w.]*host_pool\b|import_module\([^)]*host_pool",
            path.read_text(encoding="utf-8", errors="replace"),
            re.M,
        )
    }
    assert importers == set(), (
        "host_pool is imported now; it reads SUPABASE_SERVICE_ROLE_KEY, which the "
        "daemon no longer receives"
    )


@pytest.mark.parametrize("name", sorted(DAEMON_ONLY_ENV))
def test_daemon_only_names_are_read_by_daemon_routes_only(name):
    """Billing and account deletion are daemon HTTP routes; no child serves them."""
    allowed = {"tinyassets/billing/stripe_adapter.py", "tinyassets/account_deletion.py"}
    assert _readers(name) <= allowed


# ---------------------------------------------------------------------------
# the daemon container
# ---------------------------------------------------------------------------


def _daemon_service() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["daemon"]


def test_daemon_loads_the_rendered_env_file_not_the_secret_store():
    env_files = _daemon_service()["env_file"]
    assert "/etc/tinyassets/daemon.env" in env_files
    assert "/etc/tinyassets/env" not in env_files


def test_daemon_environment_block_names_no_forbidden_secret():
    environment = _daemon_service().get("environment") or {}
    assert set(environment) & DAEMON_FORBIDDEN_ENV == set()


def test_tunnel_still_gets_its_token_from_interpolation():
    """The split must not take the public surface down with it."""
    tunnel = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["cloudflared"]
    assert "${CLOUDFLARE_TUNNEL_TOKEN}" in tunnel["command"]


# ---------------------------------------------------------------------------
# children
# ---------------------------------------------------------------------------


def test_child_env_removes_every_platform_secret_and_keeps_the_rest():
    source = {name: "placeholder" for name in CHILD_FORBIDDEN_ENV}
    source.update({"TINYASSETS_DATA_DIR": "/data", "UNRELATED": "kept"})
    assert child_env(source) == {"TINYASSETS_DATA_DIR": "/data", "UNRELATED": "kept"}


def test_engine_mcp_server_child_gets_a_scrubbed_env(monkeypatch):
    from tinyassets import engine_mcp_http

    for name in CHILD_FORBIDDEN_ENV:
        monkeypatch.setenv(name, "placeholder")
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    captured = {}

    class _Proc:
        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return _Proc()

    monkeypatch.setattr(engine_mcp_http.subprocess, "Popen", fake_popen)
    server = engine_mcp_http._EngineServer("universe-a", "user:owner", 8790, "/data")
    assert server.start() is True

    env = captured["env"]
    assert captured["argv"][-1] == "tinyassets.engine_mcp_server"
    assert set(env) & CHILD_FORBIDDEN_ENV == set()
    # Its own pins and ordinary configuration still arrive.
    assert env["TINYASSETS_ENGINE_GRAPH_ID"] == "universe-a"
    assert env["TINYASSETS_ENGINE_ACTOR_ID"] == "user:owner"
    assert env["TINYASSETS_ENGINE_MCP_TOOLS"] == "1"
    assert env["TINYASSETS_DATA_DIR"] == "/data"


def test_the_stdio_engine_server_config_carries_no_inherited_env():
    """The stdio fallback is spawned by the provider CLI, whose own env is an
    allowlist; its config must add only the engine pins, never os.environ."""
    source = (PACKAGE / "providers" / "claude_provider.py").read_text(encoding="utf-8")
    block = source[source.index("server_env = {"):source.index('"env": server_env')]
    assert "os.environ" not in block


# ---------------------------------------------------------------------------
# the renderer
# ---------------------------------------------------------------------------


def _helper(tmp_path: Path, args: list[str], source: Path, daemon: Path, stdin: str = ""):
    env = os.environ.copy()
    env.update({
        "TINYASSETS_ENV_FILE": str(source),
        "TINYASSETS_LEGACY_ENV_FILE": str(tmp_path / "no-legacy"),
        "TINYASSETS_ENV_OWNER": "",
        "TINYASSETS_ENV_READ_USER": "",
        "TINYASSETS_DAEMON_ENV_SOURCE": str(source),
        "TINYASSETS_DAEMON_ENV_FILE": str(daemon),
    })
    return subprocess.run(
        ["bash", str(HELPER), *args], input=stdin, text=True, capture_output=True,
        cwd=tmp_path, env=env, check=False,
    )


def _assigned(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        names.add(re.split(r"\s*[=:]", line, maxsplit=1)[0])
    return names


@_POSIX_SHELL
def test_render_removes_every_compose_spelling_of_a_forbidden_name(tmp_path):
    source = tmp_path / "env"
    daemon = tmp_path / "daemon.env"
    source.write_text(
        "TINYASSETS_IMAGE=ghcr.io/x@sha256:abc\n"
        "DO_API_TOKEN=placeholder-do\n"
        "  export CLOUDFLARE_TUNNEL_TOKEN = placeholder-cf\n"
        "BETTERSTACK_SOURCE_TOKEN: placeholder-bs\n"
        "STRIPE_SECRET_KEY=placeholder-stripe\n"
        "# a comment kept verbatim\n"
        "WORKOS_API_KEY='placeholder-workos'\n",
        encoding="utf-8",
    )

    result = _helper(tmp_path, ["render-daemon-env"], source, daemon)

    assert result.returncode == 0, result.stderr
    assert _assigned(daemon) == {"TINYASSETS_IMAGE", "STRIPE_SECRET_KEY", "WORKOS_API_KEY"}
    text = daemon.read_text(encoding="utf-8")
    assert "# a comment kept verbatim\n" in text
    assert "placeholder-do" not in text and "placeholder-cf" not in text
    assert "placeholder-bs" not in text
    # The report names what it removed and never prints a value.
    assert "DO_API_TOKEN" in result.stdout
    assert "placeholder" not in result.stdout + result.stderr


@_POSIX_SHELL
def test_render_refuses_a_forbidden_value_that_continues_past_its_line(tmp_path):
    source = tmp_path / "env"
    daemon = tmp_path / "daemon.env"
    source.write_text(
        'KEEP=1\nDO_API_TOKEN="placeholder-start\nplaceholder-rest"\n', encoding="utf-8"
    )

    result = _helper(tmp_path, ["render-daemon-env"], source, daemon)

    assert result.returncode == 7
    assert not daemon.exists()
    assert "placeholder" not in result.stdout + result.stderr


@_POSIX_SHELL
def test_every_write_to_the_source_re_renders_the_daemon_copy(tmp_path):
    source = tmp_path / "env"
    daemon = tmp_path / "daemon.env"
    source.write_text("DO_API_TOKEN=placeholder\n", encoding="utf-8")

    set_result = _helper(tmp_path, ["set", "TINYASSETS_IMAGE"], source, daemon, stdin="ref-1\n")
    assert set_result.returncode == 0, set_result.stderr
    assert _assigned(daemon) == {"TINYASSETS_IMAGE"}

    delete_result = _helper(tmp_path, ["delete", "TINYASSETS_IMAGE"], source, daemon)
    assert delete_result.returncode == 0, delete_result.stderr
    assert _assigned(daemon) == set()


@_POSIX_SHELL
def test_a_write_to_another_env_file_renders_nothing(tmp_path):
    other = tmp_path / "request-idempotency.env"
    daemon = tmp_path / "daemon.env"
    env = os.environ.copy()
    env.update({
        "TINYASSETS_ENV_FILE": str(other),
        "TINYASSETS_LEGACY_ENV_FILE": str(tmp_path / "no-legacy"),
        "TINYASSETS_ENV_OWNER": "",
        "TINYASSETS_ENV_READ_USER": "",
        "TINYASSETS_DAEMON_ENV_SOURCE": str(tmp_path / "env"),
        "TINYASSETS_DAEMON_ENV_FILE": str(daemon),
    })
    result = subprocess.run(
        ["bash", str(HELPER), "set", "SOME_KEY"], input="v\n", text=True,
        capture_output=True, env=env, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not daemon.exists()


@_POSIX_SHELL
def test_forbidden_names_subcommand_prints_the_list(tmp_path):
    result = subprocess.run(
        ["bash", str(HELPER), "daemon-forbidden-names"], text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.split()) == set(DAEMON_FORBIDDEN_ENV)
