"""The bundle validator, run against the shape REAL Docker Compose emits.

Why this file exists
--------------------
PR #2685's first production deploy refused a correct bundle
(`deploy_result=bundle_invalid`, "daemon.env_file is []") while
`tests/test_deploy_bundle_transaction.py` was 60/60 green. That suite drives the
validator through a fake `docker compose config`, and the fake modelled
`env_file` as a passthrough key. Compose v5 -- the droplet runs v5.1.3 --
resolves every `env_file` into `environment` and drops the key, so the suite was
asserting the fake's behaviour rather than Compose's. #2696 fixed both sides:
the validator reads `env_file` from a second `--no-interpolate` render, and the
fake reproduces the drop.

That fake is now correct. But a fake can only ever encode what its author
believed, which is precisely how this reached production. So this module is an
independent check that does not use the fake at all: it runs the validator's own
Python -- extracted from `deploy/deploy_fail_safe.sh`, never a copy -- against
JSON captured from a real

    docker compose --env-file /etc/tinyassets/env \\
        -f /opt/tinyassets/compose.yml config --format json

on the droplet (2026-08-30), plus the `--no-interpolate` companion render the
validator now also consumes.

It needs no bash, no docker and no WSL, so unlike the transaction suite it runs
on Windows as well as Linux CI. If the validator is changed to want a shape
production does not produce, this goes red everywhere.

Maintaining the capture
-----------------------
Re-measure on the droplet and reconcile `_render()` / `_render_no_interpolate()`
whenever Compose is upgraded or the compose file gains a directive these assert.
A capture that has silently drifted from production re-creates exactly the false
confidence this file exists to prevent -- it is worse than having no capture,
because it looks like evidence.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "deploy" / "deploy_fail_safe.sh"
REAL_COMPOSE = REPO / "deploy" / "compose.yml"

RUNTIME = "/opt/tinyassets"
ENV_FILE = "/etc/tinyassets/env"
IMAGE = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "b" * 64


def _validator_source() -> str:
    """The validator as it ships, lifted out of the shell heredoc."""
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"<<'PY'\n(.*?)\nPY\n", text, re.S)
    assert match, "could not extract the embedded validator from deploy_fail_safe.sh"
    return match.group(1)


def _render() -> dict:
    """`docker compose config --format json`, as measured on the droplet.

    The details that matter, all of which the original fake got wrong:
      * `services.daemon` has NO `env_file` key -- Compose v5 resolves it away
      * `environment` therefore carries the merged result (TINYASSETS_DATA_DIR)
      * `mem_limit` is the STRING '4294967296', not an int and not '4g'
      * a named volume carries `volume: {}` and no `read_only`
    """
    return {
        "services": {
            "daemon": {
                "cap_drop": ["ALL"],
                "command": ["python", "-m", "tinyassets.universe_server"],
                "container_name": "tinyassets-daemon",
                "entrypoint": ["/usr/bin/tini", "--"],
                "environment": {
                    "HOME": "/app",
                    "TINYASSETS_DATA_DIR": "/data",
                    "CODEX_HOME": "/data/.codex",
                    "CLAUDE_CONFIG_DIR": "/data/.claude",
                    "TINYASSETS_IMAGE": IMAGE,
                },
                "healthcheck": {
                    "test": ["CMD", "python", "/app/scripts/mcp_public_canary.py"],
                    "interval": "30s",
                },
                "image": IMAGE,
                "labels": {"org.tinyassets.component": "daemon"},
                "logging": {"driver": "fluentd"},
                "mem_limit": "4294967296",
                "memswap_limit": "4294967296",
                "networks": {"default": None},
                "ports": [{"mode": "ingress", "target": 8001, "published": "8001"}],
                "restart": "unless-stopped",
                "security_opt": ["seccomp=unconfined"],
                "volumes": [
                    {
                        "type": "volume",
                        "source": "tinyassets-data",
                        "target": "/data",
                        "volume": {},
                    }
                ],
            },
            "cloudflared": {
                "container_name": "tinyassets-tunnel",
                "image": "cloudflare/cloudflared:2026.3.0@sha256:" + "6" * 64,
                "restart": "unless-stopped",
            },
            "logs": {
                "container_name": "tinyassets-logs",
                "image": "timberio/vector:0.40.0-alpine@sha256:" + "7" * 64,
                "restart": "unless-stopped",
                "volumes": [
                    {
                        "type": "bind",
                        "source": f"{RUNTIME}/deploy/{name}",
                        "target": f"/etc/vector/{name}",
                        "read_only": True,
                    }
                    for name in (
                        "vector.yaml",
                        "vector-betterstack.yaml",
                        "vector-entrypoint.sh",
                    )
                ],
            },
        }
    }


def _render_no_interpolate() -> dict:
    """`config --format json --no-interpolate`, the companion render.

    Compose keeps `env_file` here, as `{path, required}` mappings, and leaves
    `${...}` unexpanded. The validator reads only `env_file` from this one.
    """
    return {
        "services": {
            "daemon": {
                "container_name": "tinyassets-daemon",
                "image": "${TINYASSETS_IMAGE:?Set TINYASSETS_IMAGE ...}",
                "env_file": [
                    {"path": ENV_FILE, "required": True},
                    {"path": "/etc/tinyassets/agent-interchange.env", "required": True},
                    {"path": "/etc/tinyassets/request-idempotency.env", "required": True},
                ],
            },
            "cloudflared": {"container_name": "tinyassets-tunnel"},
            "logs": {"container_name": "tinyassets-logs"},
        }
    }


def _source() -> str:
    return REAL_COMPOSE.read_text(encoding="utf-8")


def _validate(
    tmp_path: Path,
    config: dict,
    source: str,
    uninterpolated: dict | None = None,
) -> subprocess.CompletedProcess:
    if uninterpolated is None:
        uninterpolated = _render_no_interpolate()
    (tmp_path / "validator.py").write_text(_validator_source(), encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "compose.yml").write_text(source, encoding="utf-8")
    (tmp_path / "raw.json").write_text(json.dumps(uninterpolated), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(tmp_path / "validator.py"),
            str(tmp_path / "config.json"),
            str(tmp_path / "compose.yml"),
            str(tmp_path / "raw.json"),
        ],
        capture_output=True,
        text=True,
        env={
            "RUNTIME_DIR": RUNTIME,
            "EXPECT_IMAGE": IMAGE,
            "ENV_FILE": ENV_FILE,
            "SYSTEMROOT": "C:/Windows",  # cpython needs this on Windows
            "PATH": "",
        },
    )


# ---------------------------------------------------------------------------
# the regression this file was written for
# ---------------------------------------------------------------------------


def test_the_real_rendering_is_accepted(tmp_path: Path):
    """The exact shape the droplet produced, with the shipped compose.yml.

    This is the case that failed in production while the mocked suite was green.
    """
    result = _validate(tmp_path, _render(), _source())
    assert result.returncode == 0, (
        "the validator refused a rendering production actually produces:\n"
        f"{result.stderr}"
    )


def test_a_rendering_without_env_file_is_not_treated_as_missing_secrets(
    tmp_path: Path,
):
    """The production refusal, isolated: no `env_file` key in the interpolated
    render is not the same as no env_file configured."""
    config = _render()
    assert "env_file" not in config["services"]["daemon"], (
        "precondition: Compose v5 emits no env_file key in the default render"
    )
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 0, result.stderr
    assert "env_file" not in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# env_file, now read from the uninterpolated render — it must still bite
# ---------------------------------------------------------------------------


def test_losing_the_production_env_file_is_still_refused(tmp_path: Path):
    raw = _render_no_interpolate()
    raw["services"]["daemon"]["env_file"] = [
        {"path": "/etc/tinyassets/agent-interchange.env", "required": True}
    ]
    result = _validate(tmp_path, _render(), _source(), uninterpolated=raw)
    assert result.returncode == 1
    assert "env_file" in result.stderr


def test_no_env_file_in_either_render_is_refused(tmp_path: Path):
    raw = _render_no_interpolate()
    del raw["services"]["daemon"]["env_file"]
    result = _validate(tmp_path, _render(), _source(), uninterpolated=raw)
    assert result.returncode == 1
    assert "env_file" in result.stderr


def test_a_plain_string_env_file_list_is_accepted(tmp_path: Path):
    """Older Compose emits plain strings, not `{path, required}` mappings."""
    raw = _render_no_interpolate()
    raw["services"]["daemon"]["env_file"] = [ENV_FILE]
    result = _validate(tmp_path, _render(), _source(), uninterpolated=raw)
    assert result.returncode == 0, result.stderr


def test_env_file_falls_back_to_the_interpolated_render(tmp_path: Path):
    """The documented fallback for an older Compose that still carries it."""
    raw = _render_no_interpolate()
    del raw["services"]["daemon"]["env_file"]
    config = _render()
    config["services"]["daemon"]["env_file"] = [ENV_FILE]
    result = _validate(tmp_path, config, _source(), uninterpolated=raw)
    assert result.returncode == 0, result.stderr


def test_environment_is_still_checked_on_the_interpolated_render(tmp_path: Path):
    """env_file says what is wired; environment says what took effect."""
    config = _render()
    del config["services"]["daemon"]["environment"]["TINYASSETS_DATA_DIR"]
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "TINYASSETS_DATA_DIR" in result.stderr


# ---------------------------------------------------------------------------
# mem_limit: every shape Compose may emit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [4294967296, "4294967296", "4g", "4096m"])
def test_every_mem_limit_shape_compose_may_emit_is_accepted(tmp_path: Path, value):
    config = _render()
    config["services"]["daemon"]["mem_limit"] = value
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 0, f"{value!r} rejected:\n{result.stderr}"


@pytest.mark.parametrize("value", [0, "0", "", None, "not-a-size", True])
def test_a_missing_or_zero_mem_limit_is_still_refused(tmp_path: Path, value):
    config = _render()
    config["services"]["daemon"]["mem_limit"] = value
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1, f"{value!r} accepted"
    assert "mem_limit" in result.stderr


# ---------------------------------------------------------------------------
# the rest of the contract, against the real shape rather than the fake's
# ---------------------------------------------------------------------------


def test_a_named_volume_shape_satisfies_the_data_mount_check(tmp_path: Path):
    """`{'type':'volume','source':...,'target':'/data','volume':{}}` — no
    `read_only` key, which an over-strict check could trip on."""
    config = _render()
    assert config["services"]["daemon"]["volumes"][0]["volume"] == {}
    assert "read_only" not in config["services"]["daemon"]["volumes"][0]
    assert _validate(tmp_path, config, _source()).returncode == 0


def test_losing_the_data_volume_is_refused(tmp_path: Path):
    config = _render()
    config["services"]["daemon"]["volumes"] = []
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "/data" in result.stderr


def test_losing_the_healthcheck_is_refused(tmp_path: Path):
    config = _render()
    del config["services"]["daemon"]["healthcheck"]
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "healthcheck" in result.stderr


def test_an_unpinned_sidecar_image_is_refused(tmp_path: Path):
    config = _render()
    config["services"]["logs"]["image"] = "timberio/vector:latest"
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "digest-pinned" in result.stderr


def test_a_writable_vector_mount_is_refused(tmp_path: Path):
    config = _render()
    config["services"]["logs"]["volumes"][0]["read_only"] = False
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "read-only" in result.stderr


def test_an_extra_default_service_is_refused(tmp_path: Path):
    config = _render()
    config["services"]["surprise"] = {"image": "busybox"}
    result = _validate(tmp_path, config, _source())
    assert result.returncode == 1
    assert "service set" in result.stderr


def test_a_literal_daemon_image_is_refused_from_the_source(tmp_path: Path):
    """The source scan still bites against the real rendering."""
    source = _source().replace(
        "image: ${TINYASSETS_IMAGE:?Set TINYASSETS_IMAGE to an immutable "
        "ghcr.io/jonnyton/tinyassets-daemon@sha256:<digest> ref}",
        f"image: {IMAGE}",
        1,
    )
    result = _validate(tmp_path, _render(), source)
    assert result.returncode == 1
    assert "interpolate" in result.stderr
