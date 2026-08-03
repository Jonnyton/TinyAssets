from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "deploy" / "verify-request-hmac-rotation-fleet.sh"
_WORKERS = (
    "tinyassets-worker",
    "tinyassets-worker-codex-2",
    "tinyassets-worker-claude-1",
    "tinyassets-worker-claude-2",
)


def test_rotation_fleet_helper_has_bounded_modes_and_fixed_workers():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "capture" in text
    assert "assert-quiesced" in text
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" in text
    assert "{{.Id}}" in text
    assert "{{.State.Running}}" in text
    for worker in _WORKERS:
        assert worker in text


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="invokes the production Bash helper with a fake Docker CLI",
)
def test_rotation_fleet_capture_then_exact_quiescence(tmp_path):
    env, state = _fake_docker_environment(tmp_path)
    captured = _run(["capture"], env)

    assert captured.returncode == 0, captured.stderr
    ids = captured.stdout.splitlines()
    assert ids == [_worker_id(index) for index in range(len(_WORKERS))]

    for worker in _WORKERS:
        (state / f"{worker}.running").write_text("false", encoding="utf-8")
    quiesced = _run(["assert-quiesced", *ids], env)
    assert quiesced.returncode == 0, quiesced.stderr


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="invokes the production Bash helper with a fake Docker CLI",
)
@pytest.mark.parametrize("failure", ["key-present", "restarted", "identity-swap"])
def test_rotation_fleet_fails_closed_across_state_transitions(tmp_path, failure: str):
    env, state = _fake_docker_environment(tmp_path)

    if failure == "key-present":
        (state / f"{_WORKERS[0]}.has_key").write_text("true", encoding="utf-8")
        result = _run(["capture"], env)
    else:
        captured = _run(["capture"], env)
        assert captured.returncode == 0, captured.stderr
        ids = captured.stdout.splitlines()
        for worker in _WORKERS:
            (state / f"{worker}.running").write_text("false", encoding="utf-8")
        if failure == "restarted":
            (state / f"{_WORKERS[1]}.running").write_text("true", encoding="utf-8")
        else:
            (state / f"{_WORKERS[1]}.id").write_text("f" * 64, encoding="utf-8")
        result = _run(["assert-quiesced", *ids], env)

    assert result.returncode != 0
    assert "secret" not in result.stdout + result.stderr


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _worker_id(index: int) -> str:
    return f"{index + 1:064x}"


def _fake_docker_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "state=${FAKE_DOCKER_STATE:?}\n"
        "case \"$1\" in\n"
        "  inspect)\n"
        "    format=$3\n"
        "    name=$4\n"
        "    case \"$format\" in\n"
        "      '{{.Id}}') cat \"$state/$name.id\" ;;\n"
        "      '{{.State.Running}}') cat \"$state/$name.running\" ;;\n"
        "      *) exit 90 ;;\n"
        "    esac\n"
        "    ;;\n"
        "  exec)\n"
        "    name=$2\n"
        "    [ \"$(cat \"$state/$name.has_key\")\" != true ]\n"
        "    ;;\n"
        "  *) exit 91 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    for index, worker in enumerate(_WORKERS):
        (state / f"{worker}.id").write_text(_worker_id(index), encoding="utf-8")
        (state / f"{worker}.running").write_text("true", encoding="utf-8")
        (state / f"{worker}.has_key").write_text("false", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_DOCKER_STATE"] = str(state)
    return env, state
