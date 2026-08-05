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
    "tinyassets-worker-founder",
)
_IMAGE_REF = f"ghcr.io/jonnyton/tinyassets-daemon@sha256:{'a' * 64}"


def test_rotation_fleet_helper_has_bounded_modes_and_fixed_workers():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "capture" in text
    assert "assert-quiesced" in text
    assert "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY" in text
    assert "{{.Id}} {{.State.Running}} {{.Config.Image}}" in text
    assert "{{.Id}} {{.State.Running}}" in text
    assert "{{range .Config.Env}}{{println .}}{{end}}" in text
    assert "docker exec" not in text
    assert "python -c" not in text
    for worker in _WORKERS:
        assert worker in text


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="invokes the production Bash helper with a fake Docker CLI",
)
def test_rotation_fleet_capture_then_exact_quiescence(tmp_path):
    env, state = _fake_docker_environment(tmp_path)
    captured = _run(["capture", _IMAGE_REF], env)

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
@pytest.mark.parametrize(
    "failure", ["key-present", "image-mismatch", "restarted", "identity-swap"]
)
def test_rotation_fleet_fails_closed_across_state_transitions(tmp_path, failure: str):
    env, state = _fake_docker_environment(tmp_path)

    if failure == "key-present":
        (state / f"{_WORKERS[0]}.env").write_text(
            "PATH=/usr/local/bin\n"
            "PYTHONPATH=/app\n"
            "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=secret\n",
            encoding="utf-8",
        )
        lied = subprocess.run(
            [
                "docker",
                "exec",
                _WORKERS[0],
                "python",
                "-c",
                "import os, sys; sys.exit(1 if "
                "'TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY' in os.environ else 0)",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert lied.returncode == 0, (
            "the planted worker-controlled sitecustomize.py must reproduce the "
            "old oracle bypass"
        )
        result = _run(["capture", _IMAGE_REF], env)
        assert (state / "exec-called").read_text(encoding="utf-8").splitlines() == [
            _WORKERS[0]
        ], (
            "the host-side proof must not trust worker-controlled Python, even if "
            "an in-container sitecustomize oracle would report the key absent"
        )
    elif failure == "image-mismatch":
        (state / f"{_WORKERS[1]}.image").write_text(
            f"ghcr.io/jonnyton/tinyassets-daemon@sha256:{'b' * 64}",
            encoding="utf-8",
        )
        result = _run(["capture", _IMAGE_REF], env)
    else:
        captured = _run(["capture", _IMAGE_REF], env)
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


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="invokes the production Bash helper with a fake Docker CLI",
)
@pytest.mark.parametrize("interleaving", ["current-member", "earlier-member"])
def test_rotation_fleet_quiescence_rejects_interleaved_recreation(
    tmp_path, interleaving: str
):
    env, state = _fake_docker_environment(tmp_path)
    captured = _run(["capture", _IMAGE_REF], env)
    assert captured.returncode == 0, captured.stderr
    ids = captured.stdout.splitlines()
    for worker in _WORKERS:
        (state / f"{worker}.running").write_text("false", encoding="utf-8")
    env["FAKE_DOCKER_INTERLEAVING"] = interleaving

    result = _run(["assert-quiesced", *ids], env)

    assert result.returncode != 0


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
        "    target=$4\n"
        "    name=\"\"\n"
        "    if [ -f \"$state/$target.id\" ]; then name=$target; else\n"
        "      for candidate in ${FAKE_DOCKER_WORKERS:?}; do\n"
        "        if [ \"$(cat \"$state/$candidate.expected-id\")\" "
        "= \"$target\" ]; then name=$candidate; break; fi\n"
        "      done\n"
        "    fi\n"
        "    [ -n \"$name\" ] || exit 92\n"
        "    case \"$format\" in\n"
        "      '{{.Id}}') cat \"$state/$name.id\" ;;\n"
        "      '{{.Id}} {{.State.Running}} {{.Config.Image}}')\n"
        "        printf '%s %s %s\\n' \"$(cat \"$state/$name.id\")\" "
        "\"$(cat \"$state/$name.running\")\" "
        "\"$(cat \"$state/$name.image\")\"\n"
        "        ;;\n"
        "      '{{.Id}} {{.State.Running}}')\n"
        "        printf '%s %s\\n' \"$target\" \"$(cat \"$state/$name.running\")\"\n"
        "        if [ \"${FAKE_DOCKER_INTERLEAVING-}\" = current-member ] "
        "&& [ \"$name\" = tinyassets-worker-codex-2 ]; then "
        "printf '%064x' 98 > \"$state/$name.id\"; fi\n"
        "        if [ \"${FAKE_DOCKER_INTERLEAVING-}\" = earlier-member ] "
        "&& [ \"$name\" = tinyassets-worker-codex-2 ]; then "
        "printf '%064x' 99 > \"$state/tinyassets-worker.id\"; fi\n"
        "        ;;\n"
        "      '{{.State.Running}}') cat \"$state/$name.running\" ;;\n"
        "      '{{range .Config.Env}}{{println .}}{{end}}') cat \"$state/$name.env\" ;;\n"
        "      *) exit 90 ;;\n"
        "    esac\n"
        "    ;;\n"
        "  exec)\n"
        "    name=$2\n"
        "    shift 2\n"
        "    printf '%s\\n' \"$name\" >> \"$state/exec-called\"\n"
        "    secret=$(grep '^TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=' "
        "\"$state/$name.env\" || true)\n"
        "    if [ -n \"$secret\" ]; then export \"$secret\"; fi\n"
        "    PYTHONPATH=\"$state/$name.app\" \"$@\"\n"
        "    ;;\n"
        "  *) exit 91 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    container_ids = (
        ("tinyassets-daemon", _worker_id(len(_WORKERS))),
        *((worker, _worker_id(index)) for index, worker in enumerate(_WORKERS)),
    )
    for worker, container_id in container_ids:
        (state / f"{worker}.id").write_text(container_id, encoding="utf-8")
        (state / f"{worker}.expected-id").write_text(
            container_id, encoding="utf-8"
        )
        (state / f"{worker}.running").write_text("true", encoding="utf-8")
        (state / f"{worker}.image").write_text(_IMAGE_REF, encoding="utf-8")
        (state / f"{worker}.env").write_text(
            "PATH=/usr/local/bin\nPYTHONPATH=/app\n", encoding="utf-8"
        )
        app_dir = state / f"{worker}.app"
        app_dir.mkdir()
        (app_dir / "sitecustomize.py").write_text(
            "import os\n"
            "os.environ.pop('TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY', None)\n",
            encoding="utf-8",
        )
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_DOCKER_STATE"] = str(state)
    env["FAKE_DOCKER_WORKERS"] = " ".join(("tinyassets-daemon", *_WORKERS))
    return env, state
