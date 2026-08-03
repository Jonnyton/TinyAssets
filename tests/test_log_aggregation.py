"""Tests for Row K log aggregation sidecar (deploy/compose.yml + deploy/vector.yaml)."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "deploy" / "compose.yml"
VECTOR_YAML = REPO_ROOT / "deploy" / "vector.yaml"
VECTOR_BETTERSTACK_YAML = REPO_ROOT / "deploy" / "vector-betterstack.yaml"
VECTOR_ENTRYPOINT = REPO_ROOT / "deploy" / "vector-entrypoint.sh"
SHIP_LOGS = REPO_ROOT / "deploy" / "ship-logs.sh"
RUNBOOK = REPO_ROOT / "docs" / "ops" / "log-aggregation-runbook.md"


# ---------------------------------------------------------------------------
# compose.yml — sidecar service assertions
# ---------------------------------------------------------------------------


def _load_compose() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_logs_service_defined():
    data = _load_compose()
    assert "logs" in data["services"], "compose.yml must have a 'logs' sidecar service"


def test_logs_service_uses_vector_image():
    data = _load_compose()
    image = data["services"]["logs"]["image"]
    assert image.startswith("timberio/vector:"), f"unexpected image: {image}"


def test_logs_service_restart_policy():
    data = _load_compose()
    restart = data["services"]["logs"].get("restart")
    assert restart == "unless-stopped", f"restart policy should be unless-stopped, got: {restart}"


def test_logs_service_has_no_docker_socket_or_container_control():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    socket_mounts = [v for v in volumes if "/var/run/docker.sock" in str(v)]
    assert not socket_mounts, "logging sidecar must not receive Docker control access"


def test_runtime_containers_forward_logs_without_docker_socket():
    data = _load_compose()
    services = data["services"]
    for name in (
        "daemon",
        "cloudflared",
        "worker",
        "worker-codex-2",
        "worker-claude-1",
        "worker-claude-2",
    ):
        logging = services[name].get("logging") or {}
        assert logging.get("driver") == "fluentd", name
        options = logging.get("options") or {}
        assert options.get("fluentd-address") == "127.0.0.1:24224", name
        assert str(options.get("fluentd-async")).lower() == "true", name

    ports = services["logs"].get("ports") or []
    assert "127.0.0.1:24224:24224" in ports


def test_sidecars_receive_only_their_required_secret():
    services = _load_compose()["services"]
    expected = {
        "cloudflared": {"CLOUDFLARE_TUNNEL_TOKEN"},
        "logs": {"BETTERSTACK_SOURCE_TOKEN"},
    }
    for name, allowed in expected.items():
        service = services[name]
        assert not (service.get("env_file") or []), name
        environment = service.get("environment") or {}
        assert set(environment) == allowed, name
        assert all("${" in str(value) for value in environment.values()), name


def test_logs_service_mounts_vector_config():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    config_mounts = [v for v in volumes if "vector.yaml" in str(v)]
    assert config_mounts, "logs service must mount vector.yaml config"


def test_logs_service_depends_on_daemon():
    data = _load_compose()
    deps = data["services"]["logs"].get("depends_on", [])
    if isinstance(deps, dict):
        dep_names = list(deps.keys())
    else:
        dep_names = list(deps)
    assert "daemon" in dep_names, "logs service must depend on daemon"


# ---------------------------------------------------------------------------
# vector.yaml — source / transform / sink assertions
# ---------------------------------------------------------------------------


def _load_vector() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(VECTOR_YAML.read_text(encoding="utf-8"))


def test_vector_fluent_source_has_no_docker_api_dependency():
    data = _load_vector()
    sources = data.get("sources", {})
    assert all(source.get("type") != "docker_logs" for source in sources.values())
    fluent = next((v for v in sources.values() if v.get("type") == "fluent"), None)
    assert fluent is not None
    assert fluent.get("address") == "0.0.0.0:24224"
    assert fluent.get("mode") == "tcp"


def test_vector_classifies_forwarded_runtime_tags():
    data = _load_vector()
    transform = data["transforms"]["enriched"]
    source = transform.get("source", "")
    assert "tinyassets-daemon" in source
    assert "tinyassets-tunnel" in source
    assert "tinyassets-worker" in source


def test_vector_has_stdout_sink():
    data = _load_vector()
    sinks = data.get("sinks", {})
    console_sinks = [v for v in sinks.values() if v.get("type") == "console"]
    assert console_sinks, "vector.yaml must have a console/stdout sink (always-on fallback)"


def test_vector_base_has_no_betterstack_sink():
    """Base vector.yaml must NOT contain the betterstack sink — it lives in the
    separate vector-betterstack.yaml fragment to silence 401 errors when the
    token is unset."""
    data = _load_vector()
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert not http_sinks, (
        "base vector.yaml must not contain an http sink — betterstack belongs "
        "in vector-betterstack.yaml (loaded conditionally by vector-entrypoint.sh)"
    )


def test_vector_betterstack_fragment_exists():
    assert VECTOR_BETTERSTACK_YAML.exists(), (
        "deploy/vector-betterstack.yaml must exist (conditional betterstack sink)"
    )


def test_vector_betterstack_fragment_has_http_sink():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(VECTOR_BETTERSTACK_YAML.read_text(encoding="utf-8"))
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert http_sinks, "vector-betterstack.yaml must have an HTTP sink"


def test_vector_betterstack_fragment_uses_token_env():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(VECTOR_BETTERSTACK_YAML.read_text(encoding="utf-8"))
    sinks = data.get("sinks", {})
    http_sinks = [v for v in sinks.values() if v.get("type") == "http"]
    assert http_sinks
    auth_header = http_sinks[0].get("request", {}).get("headers", {}).get("Authorization", "")
    assert "BETTERSTACK_SOURCE_TOKEN" in auth_header


def test_vector_entrypoint_exists():
    assert VECTOR_ENTRYPOINT.exists(), "deploy/vector-entrypoint.sh must exist"


def test_vector_entrypoint_conditional_betterstack():
    text = VECTOR_ENTRYPOINT.read_text(encoding="utf-8")
    assert "BETTERSTACK_SOURCE_TOKEN" in text
    assert "vector-betterstack.yaml" in text


def test_vector_entrypoint_exec_vector():
    text = VECTOR_ENTRYPOINT.read_text(encoding="utf-8")
    assert "exec vector" in text


def test_compose_mounts_entrypoint():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    entrypoint_mounts = [v for v in volumes if "vector-entrypoint.sh" in str(v)]
    assert entrypoint_mounts, "compose must mount vector-entrypoint.sh"


def test_compose_mounts_betterstack_fragment():
    data = _load_compose()
    volumes = data["services"]["logs"].get("volumes", [])
    bs_mounts = [v for v in volumes if "vector-betterstack.yaml" in str(v)]
    assert bs_mounts, "compose must mount vector-betterstack.yaml"


def test_vector_yaml_parses_cleanly():
    yaml = pytest.importorskip("yaml")
    # Should not raise
    data = yaml.safe_load(VECTOR_YAML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# ship-logs.sh — basic sanity
# ---------------------------------------------------------------------------


_BASH_AVAILABLE = sys.platform != "win32"


def test_ship_logs_script_exists():
    assert SHIP_LOGS.exists(), "deploy/ship-logs.sh must exist"


def test_ship_logs_default_covers_complete_production_fleet():
    text = SHIP_LOGS.read_text(encoding="utf-8")
    for container in (
        "tinyassets-daemon",
        "tinyassets-tunnel",
        "tinyassets-worker",
        "tinyassets-worker-codex-2",
        "tinyassets-worker-claude-1",
        "tinyassets-worker-claude-2",
    ):
        assert container in text


def test_ship_logs_requires_a_complete_readable_fleet_archive():
    text = SHIP_LOGS.read_text(encoding="utf-8")
    collect = text.split("# Collect Docker container logs", 1)[1].split(
        "# Archive", 1
    )[0]
    assert "docker ps" not in collect
    assert "{{.State.Status}}" in collect
    assert "{{.Id}}" in collect
    assert "fleet-manifest.tsv" in text
    assert "docker logs" in collect
    assert "|| true" not in collect
    assert 'docker logs "${container_id}"' in collect
    assert 'current_id="$(docker inspect' in collect


def test_log_runbook_uses_current_production_identities():
    text = RUNBOOK.read_text(encoding="utf-8")
    for stale in (
        "docker-compose@workflow",
        "docker-compose@tinyassets",
        '.service = "workflow"',
        "workflow-logs-",
        "docker logs workflow-logs",
    ):
        assert stale not in text
    assert "journalctl -u tinyassets-daemon" in text
    assert '.service = "tinyassets"' in text
    assert "tinyassets-logs-" in text
    assert "docker logs tinyassets-logs" in text
    assert "/opt/tinyassets-host-uptime/current/deploy/ship-logs.sh" in text
    assert "/opt/tinyassets/deploy/ship-logs.sh" not in text


@pytest.mark.skipif(not _BASH_AVAILABLE, reason="bash not available on Windows")
def test_ship_logs_dry_run_exits_0(tmp_path):
    if not SHIP_LOGS.exists():
        pytest.skip("ship-logs.sh not yet created")
    env = {
        "DRY_RUN": "1",
        "LOG_DEST": "s3://test-bucket/logs",
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", str(SHIP_LOGS)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"DRY_RUN=1 should exit 0; got {result.returncode}\n{result.stderr}"
    )


@pytest.mark.skipif(not _BASH_AVAILABLE, reason="bash not available on Windows")
def test_ship_logs_dry_run_prints_indicator(tmp_path):
    if not SHIP_LOGS.exists():
        pytest.skip("ship-logs.sh not yet created")
    env = {
        "DRY_RUN": "1",
        "LOG_DEST": "s3://test-bucket/logs",
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", str(SHIP_LOGS)],
        env=env,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "dry" in combined.lower(), "DRY_RUN=1 should print a dry-run indicator"


@pytest.mark.skipif(not _BASH_AVAILABLE, reason="bash not available on Windows")
def test_ship_logs_missing_log_dest_exits_1(tmp_path):
    if not SHIP_LOGS.exists():
        pytest.skip("ship-logs.sh not yet created")
    env = {
        "LOG_DEST": "",
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", str(SHIP_LOGS)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "missing LOG_DEST should exit non-zero"


@pytest.mark.skipif(not _BASH_AVAILABLE, reason="bash not available on Windows")
@pytest.mark.parametrize(
    "failure", [None, "missing", "unreadable", "recreated", "recreated-earlier"]
)
def test_ship_logs_archives_stopped_members_and_fails_closed(tmp_path, failure):
    bin_dir = tmp_path / "bin"
    capture_dir = tmp_path / "capture"
    bin_dir.mkdir()
    capture_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "case \"$1\" in\n"
        "  inspect)\n"
        "    format=$3\n"
        "    name=$4\n"
        "    if [ \"${SHIP_LOG_FAILURE-}\" = missing ] "
        "&& [ \"$name\" = worker-b ]; then exit 1; fi\n"
        "    id=$(cat \"${SHIP_LOG_STATE:?}/$name.id\")\n"
        "    status=$(cat \"${SHIP_LOG_STATE:?}/$name.status\")\n"
        "    case \"$format\" in\n"
        "      '{{.Id}} {{.State.Status}}')\n"
        "        printf '%s %s\\n' \"$id\" \"$status\"\n"
        "        if [ \"${SHIP_LOG_FAILURE-}\" = recreated ] "
        "&& [ \"$name\" = worker-b ]; then printf '%064x' 99 > \"$SHIP_LOG_STATE/$name.id\"; fi\n"
        "        if [ \"${SHIP_LOG_FAILURE-}\" = recreated-earlier ] "
        "&& [ \"$name\" = worker-b ]; then "
        "printf '%064x' 98 > \"$SHIP_LOG_STATE/worker-a.id\"; fi\n"
        "        ;;\n"
        "      '{{.Id}}') printf '%s\\n' \"$id\" ;;\n"
        "      *) exit 91 ;;\n"
        "    esac\n"
        "    ;;\n"
        "  logs)\n"
        "    id=$2\n"
        "    if [ \"${SHIP_LOG_FAILURE-}\" = unreadable ] "
        "&& [ \"$id\" = \"$(cat \"$SHIP_LOG_STATE/worker-b.id\")\" ]; then exit 1; fi\n"
        "    printf 'logs for %s\\n' \"$id\"\n"
        "    ;;\n"
        "  *) exit 90 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    worker_ids = {
        "worker-a": f"{1:064x}",
        "worker-b": f"{2:064x}",
    }
    for name, container_id in worker_ids.items():
        (state_dir / f"{name}.id").write_text(container_id, encoding="utf-8")
        (state_dir / f"{name}.status").write_text(
            "exited" if name == "worker-b" else "running", encoding="utf-8"
        )
    rclone = bin_dir / "rclone"
    rclone.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"$1\" = copyto ]; then\n"
        "  cp \"$2\" \"${SHIP_LOG_CAPTURE:?}/archive.tar.gz\"\n"
        "  touch \"${SHIP_LOG_CAPTURE:?}/uploaded\"\n"
        "fi\n",
        encoding="utf-8",
    )
    rclone.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "LOG_DEST": "fake:logs",
            "LOG_CONTAINERS": "worker-a worker-b",
            "LOG_DIR": str(tmp_path / "scratch"),
            "SHIP_LOG_CAPTURE": str(capture_dir),
            "SHIP_LOG_FAILURE": failure or "",
            "SHIP_LOG_STATE": str(state_dir),
        }
    )

    result = subprocess.run(
        ["bash", str(SHIP_LOGS)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if failure:
        assert result.returncode != 0
        assert not (capture_dir / "uploaded").exists()
        return

    assert result.returncode == 0, result.stderr
    assert (capture_dir / "uploaded").exists()
    with tarfile.open(capture_dir / "archive.tar.gz", "r:gz") as archive:
        assert set(archive.getnames()) == {
            "fleet-manifest.tsv",
            "worker-a.log",
            "worker-b.log",
        }
        manifest = archive.extractfile("fleet-manifest.tsv")
        assert manifest is not None
        contents = manifest.read().decode("utf-8")
    assert f"worker-a\t{worker_ids['worker-a']}\trunning\tworker-a.log" in contents
    assert f"worker-b\t{worker_ids['worker-b']}\texited\tworker-b.log" in contents
