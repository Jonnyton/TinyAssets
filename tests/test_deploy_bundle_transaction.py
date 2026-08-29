"""`deploy/deploy_fail_safe.sh` runtime-bundle transaction, against a fake docker.

PR #2685 first restored the dropped compose/vector/unit sync as a workflow step
that INSTALLED. A cross-family review (Codex, 2026-08-29) refuted that shape:
config mutation sat outside the fail-safe transaction, so a failure in any later
step -- the auth-volume step, the deploy_fail_safe.sh scp, the host-mutation
lock, the candidate-image preflight -- stranded the new config under the old
image, and neither rollback path restored it. The workflow now only stages into
``/tmp/tinyassets-bundle`` and this script owns:

    validate -> snapshot -> install -> converge -> restore

These tests drive the real script with a fake ``docker`` and ``systemctl`` on
PATH and assert on the FILES it left behind, not on its log lines.

Why a real script run and not a source grep: the thing that failed in production
was ordering (install before the transaction), and only an execution can show
that production files are still the old bytes when a bundle is refused.

Windows is skipped -- the script drives ``install(1)``, ``flock``, ``sha256sum``
and POSIX ownership -- but every test runs on Linux CI, which is the oracle.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "deploy" / "deploy_fail_safe.sh"
REAL_COMPOSE = REPO / "deploy" / "compose.yml"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    os.name == "nt" or _BASH is None,
    reason=(
        "deploy_fail_safe.sh drives install(1)/flock/sha256sum and POSIX "
        "ownership; Linux CI is the oracle for this suite"
    ),
)

OLD_IMAGE = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "a" * 64
NEW_IMAGE = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "b" * 64
OTHER_IMAGE = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "c" * 64


# ---------------------------------------------------------------------------
# fake docker
# ---------------------------------------------------------------------------
# It reads the STAGED compose file for `config`, so an invalid fixture produces
# invalid JSON by construction rather than by a canned blob -- a canned blob
# would encode the behaviour under test and could never go red.

FAKE_DOCKER = r'''#!/usr/bin/env python3
"""Minimal docker stand-in: pull / run / inspect / image inspect / compose."""
import hashlib
import json
import os
import re
import sys

import yaml

STATE_PATH = os.environ["FAKE_DOCKER_STATE"]
CALL_LOG = os.environ["FAKE_DOCKER_CALLS"]


def load_state():
    with open(STATE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def record(argv):
    with open(CALL_LOG, "a", encoding="utf-8") as handle:
        handle.write(" ".join(argv) + "\n")


def image_id(ref):
    return "sha256:" + hashlib.sha256(ref.encode("utf-8")).hexdigest()


def read_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value
    except OSError:
        pass
    return values


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:\?[^}]*|:-[^}]*)?\}")


def interpolate(text, values):
    def sub(match):
        name, modifier = match.group(1), match.group(2) or ""
        value = values.get(name)
        if value:
            return value
        if modifier.startswith(":-"):
            return modifier[2:]
        if modifier.startswith(":?"):
            sys.stderr.write("required variable %s is missing\n" % name)
            raise SystemExit(1)
        return ""

    return _VAR.sub(sub, text)


def to_bytes(value):
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    for suffix, factor in (("g", 1024 ** 3), ("m", 1024 ** 2), ("k", 1024)):
        if text.endswith(suffix):
            return int(float(text[:-1]) * factor)
    try:
        return int(text)
    except ValueError:
        return value


def normalise_volumes(volumes):
    out = []
    for volume in volumes or []:
        if isinstance(volume, dict):
            out.append(volume)
            continue
        parts = str(volume).split(":")
        if len(parts) < 2:
            continue
        source, target = parts[0], parts[1]
        options = parts[2].split(",") if len(parts) > 2 else []
        out.append(
            {
                "type": "bind" if source.startswith("/") else "volume",
                "source": source,
                "target": target,
                "read_only": "ro" in options,
            }
        )
    return out


def compose_config(compose_file, env_values):
    with open(compose_file, encoding="utf-8") as handle:
        raw = handle.read()
    # Shell environment wins over the env file, exactly as compose interpolates.
    values = dict(env_values)
    values.update({k: v for k, v in os.environ.items() if v})
    data = yaml.safe_load(interpolate(raw, values)) or {}
    active = set(filter(None, os.environ.get("COMPOSE_PROFILES", "").split(",")))
    services = {}
    for name, service in (data.get("services") or {}).items():
        service = dict(service or {})
        profiles = set(service.pop("profiles", []) or [])
        if profiles and not (profiles & active):
            continue
        if "mem_limit" in service:
            service["mem_limit"] = to_bytes(service["mem_limit"])
        if "volumes" in service:
            service["volumes"] = normalise_volumes(service["volumes"])
        services[name] = service
    data["services"] = services
    return data


def main(argv):
    record(argv)
    state = load_state()

    if argv[:1] == ["pull"]:
        if not state.get("pull_ok", True):
            sys.stderr.write("fake docker: pull refused\n")
            return 1
        state.setdefault("images", {})[argv[-1]] = image_id(argv[-1])
        save_state(state)
        return 0

    if argv[:1] == ["run"]:
        return 0 if state.get("preflight_ok", True) else 1

    if argv[:2] == ["image", "inspect"]:
        fmt = argv[argv.index("-f") + 1] if "-f" in argv else ""
        target = argv[-1]
        images = state.get("images", {})
        if "{{.Id}}" in fmt:
            if target not in images:
                sys.stderr.write("Error: No such image: %s\n" % target)
                return 1
            print(images[target])
            return 0
        if "RepoDigests" in fmt:
            for ref, ident in images.items():
                if target in (ref, ident):
                    print(ref)
                    return 0
            sys.stderr.write("Error: No such image: %s\n" % target)
            return 1
        return 1

    if argv[:1] == ["inspect"]:
        fmt = argv[argv.index("-f") + 1] if "-f" in argv else ""
        name = argv[-1]
        container = (state.get("containers") or {}).get(name)
        if container is None:
            sys.stderr.write("Error: No such object: %s\n" % name)
            return 1
        if ".State.Health" in fmt:
            print(container.get("health") or container.get("status", "running"))
        elif "{{.State.Status}}" in fmt:
            print(container.get("status", "running"))
        elif "{{.Image}}" in fmt:
            print(container.get("image_id", ""))
        elif "{{.Config.Image}}" in fmt:
            print(container.get("image_ref", ""))
        else:
            print("")
        return 0

    if argv[:1] == ["compose"]:
        env_file = argv[argv.index("--env-file") + 1] if "--env-file" in argv else ""
        compose_file = argv[argv.index("-f") + 1] if "-f" in argv else ""
        env_values = read_env_file(env_file)
        if "config" in argv:
            try:
                config = compose_config(compose_file, env_values)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 - mirrors compose's own exit 1
                sys.stderr.write("fake docker compose config: %s\n" % exc)
                return 1
            print(json.dumps(config, indent=2, sort_keys=True))
            return 0
        if "up" in argv:
            if not state.get("up_ok", True):
                sys.stderr.write("fake docker: compose up refused\n")
                return 1
            ref = env_values.get("TINYASSETS_IMAGE", "")
            health = state.get("daemon_health", "healthy")
            # Per-image health: a rollback test needs the CANDIDATE to stay
            # unhealthy while the previous image comes back healthy.
            if ref in (state.get("unhealthy_images") or []):
                health = state.get("unhealthy_health", "starting")
            containers = state.setdefault("containers", {})
            containers["tinyassets-daemon"] = {
                "status": "running",
                "health": health,
                "image_id": image_id(ref),
                "image_ref": ref,
            }
            containers.setdefault(
                "tinyassets-tunnel",
                {"status": state.get("tunnel_status", "running")},
            )["status"] = state.get("tunnel_status", "running")
            logs_status = state.get("logs_status", "running")
            if "--force-recreate" in argv:
                logs_status = state.get("logs_recreate_status", logs_status)
            containers.setdefault("tinyassets-logs", {})["status"] = logs_status
            state.setdefault("images", {}).setdefault(ref, image_id(ref))
            save_state(state)
            return 0
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

FAKE_SYSTEMCTL = r'''#!/bin/sh
printf 'systemctl %s\n' "$*" >> "$FAKE_SYSTEMCTL_CALLS"
exit 0
'''

# Writes KEY=value into ENV_FILE the way install-tinyassets-env.sh does. The
# real helper chowns to root:tinyassets and needs privilege; the transaction
# under test is the bundle, not the env write.
FAKE_ENV_HELPER = r'''#!/usr/bin/env bash
set -euo pipefail
if [ "${FAKE_ENV_HELPER_FAIL:-0}" = "1" ]; then
  echo "fake env helper: refusing" >&2
  exit 3
fi
action="$1"; key="$2"
value="$(cat)"
tmp="$(mktemp)"
grep -v -E "^${key}=" "$ENV_FILE" > "$tmp" || true
printf '%s=%s\n' "$key" "$value" >> "$tmp"
cat "$tmp" > "$ENV_FILE"
rm -f "$tmp"
'''


# ---------------------------------------------------------------------------
# the fake droplet
# ---------------------------------------------------------------------------

OLD_VECTOR = "# live vector.yaml (pre-deploy)\nsources: {}\n"
OLD_BETTERSTACK = "# live vector-betterstack.yaml (pre-deploy)\nsinks: {}\n"
OLD_ENTRYPOINT = "#!/bin/sh\n# live vector-entrypoint.sh (pre-deploy)\n"
OLD_UNIT = "[Unit]\nDescription=live unit (pre-deploy)\n"
OLD_COMPOSE = "# live compose.yml (pre-deploy)\nservices: {}\n"

NEW_VECTOR = "# staged vector.yaml\nsources: {}\ntransforms: {}\n"
NEW_BETTERSTACK = "# staged vector-betterstack.yaml\nsinks: {}\n"
NEW_ENTRYPOINT = "#!/bin/sh\n# staged vector-entrypoint.sh\n"
NEW_UNIT = "[Unit]\nDescription=staged unit\n"


class Box:
    """A temp-directory stand-in for the droplet's filesystem."""

    def __init__(self, root: Path):
        self.root = root
        self.runtime = root / "opt" / "tinyassets"
        self.unit_file = root / "etc" / "systemd" / "system" / "tinyassets-daemon.service"
        self.env_file = root / "etc" / "tinyassets" / "env"
        self.stage = root / "tmp" / "tinyassets-bundle"
        self.state_dir = root / "var" / "lib" / "tinyassets-deploy"
        self.bin = root / "bin"
        self.docker_state = root / "docker-state.json"
        self.docker_calls = root / "docker-calls.log"
        self.systemctl_calls = root / "systemctl-calls.log"
        self.env_helper = root / "tmp" / "install-tinyassets-env.sh"
        self.lock = root / "host-mutation.lock"

    # -- live state ------------------------------------------------------
    @property
    def pointer(self) -> Path:
        return self.state_dir / "bundle-previous"

    @property
    def snapshots(self) -> Path:
        return self.state_dir / "bundle-snapshots"

    def live(self) -> dict[str, str]:
        """Every production file the bundle owns, by destination."""
        return {
            "compose": (self.runtime / "compose.yml").read_text(encoding="utf-8"),
            "deploy_compose": (self.runtime / "deploy" / "compose.yml").read_text(
                encoding="utf-8"
            ),
            "vector": (self.runtime / "deploy" / "vector.yaml").read_text(
                encoding="utf-8"
            ),
            "betterstack": (
                self.runtime / "deploy" / "vector-betterstack.yaml"
            ).read_text(encoding="utf-8"),
            "entrypoint": (self.runtime / "deploy" / "vector-entrypoint.sh").read_text(
                encoding="utf-8"
            ),
            "unit": self.unit_file.read_text(encoding="utf-8"),
        }

    def docker_state_json(self) -> dict:
        return json.loads(self.docker_state.read_text(encoding="utf-8"))

    def set_docker_state(self, **changes) -> None:
        state = self.docker_state_json()
        state.update(changes)
        self.docker_state.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def docker_calls_text(self) -> str:
        return (
            self.docker_calls.read_text(encoding="utf-8")
            if self.docker_calls.exists()
            else ""
        )

    def env_image(self) -> str:
        for line in self.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TINYASSETS_IMAGE="):
                return line.split("=", 1)[1]
        return ""

    # -- staging ---------------------------------------------------------
    def stage_bundle(self, compose_text: str | None = None) -> None:
        self.stage.mkdir(parents=True, exist_ok=True)
        (self.stage / "compose.yml").write_text(
            compose_text if compose_text is not None else self.valid_compose(),
            encoding="utf-8",
        )
        (self.stage / "vector.yaml").write_text(NEW_VECTOR, encoding="utf-8")
        (self.stage / "vector-betterstack.yaml").write_text(
            NEW_BETTERSTACK, encoding="utf-8"
        )
        (self.stage / "vector-entrypoint.sh").write_text(NEW_ENTRYPOINT, encoding="utf-8")
        (self.stage / "tinyassets-daemon.service").write_text(NEW_UNIT, encoding="utf-8")

    def valid_compose(self) -> str:
        """The REAL deploy/compose.yml, repointed at this box's runtime dir.

        Using the shipped file rather than a fixture means dropping `mem_limit`,
        a container_name or a vector mount from production compose.yml turns
        this suite red.
        """
        return REAL_COMPOSE.read_text(encoding="utf-8").replace(
            "/opt/tinyassets", str(self.runtime)
        )

    # -- invocation ------------------------------------------------------
    def env(self, **overrides) -> dict[str, str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "ENV_FILE": str(self.env_file),
            "ENV_HELPER": str(self.env_helper),
            "RUNTIME_DIR": str(self.runtime),
            "UNIT_FILE": str(self.unit_file),
            "BUNDLE_STAGE": str(self.stage),
            "BUNDLE_STATE_DIR": str(self.state_dir),
            "LOCK_FILE": str(self.lock),
            # Numeric ids: `install -o` needs privilege for any other owner, and
            # the tinyassets:tinyassets / root:root production contract is
            # asserted against the script's defaults in
            # test_install_ownership_defaults_match_the_unit_contract.
            "RUNTIME_OWNER": str(os.getuid()),
            "RUNTIME_GROUP": str(os.getgid()),
            "UNIT_OWNER": str(os.getuid()),
            "UNIT_GROUP": str(os.getgid()),
            "HEALTH_TIMEOUT": "5",
            "FAKE_DOCKER_STATE": str(self.docker_state),
            "FAKE_DOCKER_CALLS": str(self.docker_calls),
            "FAKE_SYSTEMCTL_CALLS": str(self.systemctl_calls),
        }
        env.update(overrides)
        return env

    def run(self, *args: str, **overrides) -> subprocess.CompletedProcess:
        return subprocess.run(
            [_BASH, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=self.env(**overrides),
        )


@pytest.fixture
def box(tmp_path: Path) -> Box:
    fake = Box(tmp_path)
    (fake.runtime / "deploy").mkdir(parents=True)
    fake.unit_file.parent.mkdir(parents=True)
    fake.env_file.parent.mkdir(parents=True)
    fake.stage.parent.mkdir(parents=True, exist_ok=True)
    fake.state_dir.mkdir(parents=True)
    fake.bin.mkdir()

    (fake.runtime / "compose.yml").write_text(OLD_COMPOSE, encoding="utf-8")
    (fake.runtime / "deploy" / "compose.yml").write_text(OLD_COMPOSE, encoding="utf-8")
    (fake.runtime / "deploy" / "vector.yaml").write_text(OLD_VECTOR, encoding="utf-8")
    (fake.runtime / "deploy" / "vector-betterstack.yaml").write_text(
        OLD_BETTERSTACK, encoding="utf-8"
    )
    (fake.runtime / "deploy" / "vector-entrypoint.sh").write_text(
        OLD_ENTRYPOINT, encoding="utf-8"
    )
    fake.unit_file.write_text(OLD_UNIT, encoding="utf-8")
    fake.env_file.write_text(f"TINYASSETS_IMAGE={OLD_IMAGE}\n", encoding="utf-8")

    for name, body in (
        ("docker", FAKE_DOCKER),
        ("systemctl", FAKE_SYSTEMCTL),
    ):
        path = fake.bin / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    fake.env_helper.write_text(FAKE_ENV_HELPER, encoding="utf-8", newline="\n")
    fake.env_helper.chmod(0o755)

    import hashlib

    fake.docker_state.write_text(
        json.dumps(
            {
                "pull_ok": True,
                "preflight_ok": True,
                "up_ok": True,
                "daemon_health": "healthy",
                "tunnel_status": "running",
                "logs_status": "running",
                "images": {
                    OLD_IMAGE: "sha256:"
                    + hashlib.sha256(OLD_IMAGE.encode("utf-8")).hexdigest()
                },
                "containers": {
                    "tinyassets-daemon": {
                        "status": "running",
                        "health": "healthy",
                        "image_id": "sha256:"
                        + hashlib.sha256(OLD_IMAGE.encode("utf-8")).hexdigest(),
                        "image_ref": OLD_IMAGE,
                    },
                    "tinyassets-tunnel": {"status": "running"},
                    "tinyassets-logs": {"status": "running"},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return fake


def _result(completed: subprocess.CompletedProcess) -> str:
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("deploy_result="):
            return line.split("=", 1)[1]
    return ""


def _deployed_image(completed: subprocess.CompletedProcess) -> str:
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("deployed_image="):
            return line.split("=", 1)[1]
    return ""


# ---------------------------------------------------------------------------
# (0) the harness itself must be able to go red
# ---------------------------------------------------------------------------


def test_fake_docker_rejects_a_compose_file_it_cannot_parse(box: Box):
    """A canned-JSON fake could never fail; this one parses the staged file."""
    box.stage_bundle(compose_text="services: [this is not a mapping\n")
    completed = box.run(NEW_IMAGE)
    assert completed.returncode == 1
    assert _result(completed) == "bundle_invalid"


# ---------------------------------------------------------------------------
# (a) invalid bundle -> refused before any install, production untouched
# ---------------------------------------------------------------------------


def _mutate(compose_text: str, old: str, new: str) -> str:
    assert old in compose_text, f"fixture drift: {old!r} is no longer in compose.yml"
    return compose_text.replace(old, new, 1)


@pytest.mark.parametrize(
    "label,old,new",
    [
        ("no daemon memory limit", "\n    mem_limit: 4g\n", "\n"),
        (
            "wrong logs container name",
            "container_name: tinyassets-logs",
            "container_name: tinyassets-logging",
        ),
        (
            "daemon image pinned instead of interpolated",
            "image: ${TINYASSETS_IMAGE:?Set TINYASSETS_IMAGE to an immutable "
            "ghcr.io/jonnyton/tinyassets-daemon@sha256:<digest> ref}",
            "image: ghcr.io/jonnyton/tinyassets-daemon:latest",
        ),
        (
            "a vector mount dropped",
            "      - /opt/tinyassets/deploy/vector-betterstack.yaml:"
            "/etc/vector/vector-betterstack.yaml:ro\n",
            "",
        ),
        (
            "a vector mount is writable",
            "/etc/vector/vector-entrypoint.sh:ro",
            "/etc/vector/vector-entrypoint.sh",
        ),
        (
            "daemon restart policy weakened",
            "    container_name: tinyassets-daemon\n    restart: unless-stopped",
            "    container_name: tinyassets-daemon\n    restart: 'no'",
        ),
    ],
)
def test_invalid_bundle_is_refused_before_any_install(box: Box, label, old, new):
    """Any production invariant miss refuses with production files untouched.

    `config --services` passed on "any syntactically valid file containing three
    skeletal services named daemon, cloudflared and logs" (Codex, 2026-08-29);
    each case here is such a file.
    """
    # The mount cases must be mutated against the ORIGINAL /opt path, before
    # valid_compose() repoints it at the temp runtime dir.
    raw = REAL_COMPOSE.read_text(encoding="utf-8")
    mutated = _mutate(raw, old, new).replace("/opt/tinyassets", str(box.runtime))
    before = box.live()
    box.stage_bundle(compose_text=mutated)

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 1, f"{label}: expected a refusal\n{completed.stderr}"
    assert _result(completed) == "bundle_invalid", label
    assert box.live() == before, f"{label}: production files were mutated"
    assert not box.pointer.exists(), f"{label}: the bundle pointer advanced"
    assert box.env_image() == OLD_IMAGE, f"{label}: TINYASSETS_IMAGE was swapped"
    assert "compose up" not in box.docker_calls_text(), f"{label}: the stack converged"


def test_partial_bundle_is_refused_rather_than_half_installed(box: Box):
    """Half a bundle is the 2026-08 502; an incomplete stage dir must refuse."""
    box.stage_bundle()
    (box.stage / "vector-betterstack.yaml").unlink()
    before = box.live()

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 1
    assert _result(completed) == "bundle_invalid"
    assert box.live() == before
    assert "incomplete" in completed.stderr


# ---------------------------------------------------------------------------
# (b) valid bundle -> snapshot written, files installed, pointer advanced
# ---------------------------------------------------------------------------


def test_valid_bundle_snapshots_installs_and_advances_the_pointer(box: Box):
    before = box.live()
    box.stage_bundle()

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert _result(completed) == "deployed"
    assert _deployed_image(completed) == NEW_IMAGE

    # installed
    after = box.live()
    assert after["vector"] == NEW_VECTOR
    assert after["betterstack"] == NEW_BETTERSTACK
    assert after["entrypoint"] == NEW_ENTRYPOINT
    assert after["unit"] == NEW_UNIT
    assert after["compose"] == box.valid_compose()
    assert after["deploy_compose"] == box.valid_compose()

    # modes: 0644 for config, 0755 for the entrypoint script
    def mode(path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    assert mode(box.runtime / "compose.yml") == 0o644
    assert mode(box.runtime / "deploy" / "compose.yml") == 0o644
    assert mode(box.runtime / "deploy" / "vector.yaml") == 0o644
    assert mode(box.runtime / "deploy" / "vector-betterstack.yaml") == 0o644
    assert mode(box.runtime / "deploy" / "vector-entrypoint.sh") == 0o755
    assert mode(box.unit_file) == 0o644

    # snapshot holds what was live BEFORE the install
    snapshot = Path(box.pointer.read_text(encoding="utf-8").strip())
    assert snapshot.is_dir()
    assert snapshot.parent == box.snapshots
    assert (snapshot / "compose.yml").read_text(encoding="utf-8") == before["compose"]
    assert (snapshot / "deploy" / "vector.yaml").read_text(
        encoding="utf-8"
    ) == before["vector"]
    assert (snapshot / "deploy" / "vector-betterstack.yaml").read_text(
        encoding="utf-8"
    ) == before["betterstack"]
    assert (snapshot / "deploy" / "vector-entrypoint.sh").read_text(
        encoding="utf-8"
    ) == before["entrypoint"]
    assert (snapshot / "systemd" / "tinyassets-daemon.service").read_text(
        encoding="utf-8"
    ) == before["unit"]

    assert box.env_image() == NEW_IMAGE
    assert "daemon-reload" in box.systemctl_calls.read_text(encoding="utf-8")


def test_back_to_back_deploys_get_distinct_snapshots(box: Box):
    """Two deploys inside one UTC second must not share a snapshot directory.

    A bare second-resolution stamp let the SECOND deploy write its snapshot into
    the first's directory -- capturing the files the first deploy had just
    installed, so the rollback target became the state being rolled back from.
    """
    box.stage_bundle()
    assert box.run(NEW_IMAGE).returncode == 0, "first deploy"
    first_snapshot = box.pointer.read_text(encoding="utf-8").strip()
    installed_by_first = box.live()

    box.stage_bundle(compose_text=box.valid_compose() + "\n# second deploy\n")
    assert box.run(OTHER_IMAGE).returncode == 0, "second deploy"
    second_snapshot = box.pointer.read_text(encoding="utf-8").strip()

    assert second_snapshot != first_snapshot
    assert Path(first_snapshot).is_dir(), "the first snapshot must survive"
    second = Path(second_snapshot)
    assert (second / "compose.yml").read_text(encoding="utf-8") == installed_by_first[
        "compose"
    ], "the second snapshot must hold what the FIRST deploy installed"
    assert (second / "deploy" / "vector.yaml").read_text(
        encoding="utf-8"
    ) == installed_by_first["vector"]


def test_snapshot_retention_keeps_the_last_five(box: Box):
    box.stage_bundle()
    for _ in range(7):
        # A UTC-second stamp would collide across a fast loop; seed distinct
        # older directories and let the run add its own.
        completed = box.run(NEW_IMAGE)
        assert completed.returncode == 0, completed.stderr
        box.set_docker_state(containers=box.docker_state_json()["containers"])
    for index in range(9):
        (box.snapshots / f"20260101T00000{index}Z").mkdir(exist_ok=True)
    completed = box.run(NEW_IMAGE)
    assert completed.returncode == 0, completed.stderr
    assert len(list(box.snapshots.iterdir())) <= 5, (
        "snapshot retention must keep the last 5"
    )


def test_pointer_does_not_advance_when_the_bundle_is_refused(box: Box):
    """The pointer must name the snapshot the LAST successful install replaced."""
    box.stage_bundle()
    assert box.run(NEW_IMAGE).returncode == 0
    good_snapshot = box.pointer.read_text(encoding="utf-8").strip()

    box.stage_bundle(compose_text="services: {}\n")
    completed = box.run(NEW_IMAGE)

    assert _result(completed) == "bundle_invalid"
    assert box.pointer.read_text(encoding="utf-8").strip() == good_snapshot


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores the directory mode this test uses to break install(1)",
)
def test_failed_install_restores_the_snapshot_and_leaves_the_pointer_alone(box: Box):
    """A part-way install must roll back and must NOT advance the pointer.

    The pointer is the contract a rollback depends on: if it advanced before the
    install succeeded it would name the state this deploy created, and
    `--restore-bundle` would restore the very bundle it is meant to undo.
    """
    box.stage_bundle()
    assert box.run(NEW_IMAGE).returncode == 0
    good_snapshot = box.pointer.read_text(encoding="utf-8").strip()
    before = box.live()

    # compose.yml installs into the runtime root first and succeeds; the next
    # destination is inside deploy/, which is now unwritable.
    box.stage_bundle()
    (box.runtime / "deploy").chmod(0o555)
    try:
        # A THIRD image, so "the env still names the previous deploy's image" is
        # a real assertion rather than a coincidence of the fixture.
        completed = box.run(OTHER_IMAGE)
    finally:
        (box.runtime / "deploy").chmod(0o755)

    assert completed.returncode == 1, completed.stderr
    assert _result(completed) == "bundle_install_failed"
    assert box.live() == before, "a failed install must restore its own snapshot"
    assert box.pointer.read_text(encoding="utf-8").strip() == good_snapshot
    assert box.env_image() == NEW_IMAGE, "a refused install must not swap the image"


# ---------------------------------------------------------------------------
# (c) converge failure after install -> snapshot restored, previous image back
# ---------------------------------------------------------------------------


def test_unhealthy_candidate_restores_the_bundle_and_the_previous_image(box: Box):
    before = box.live()
    box.stage_bundle()
    # The candidate converges but never becomes healthy; the previous image does.
    box.set_docker_state(unhealthy_images=[NEW_IMAGE])

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 2, completed.stderr
    assert _result(completed) == "rolled_back"
    assert _deployed_image(completed) == OLD_IMAGE
    assert box.live() == before, (
        "rollback must restore the runtime bundle, not just the image -- "
        "converging PREV_IMAGE against the NEW compose file rolls back half a change"
    )
    assert box.env_image() == OLD_IMAGE


def test_env_write_failure_after_install_restores_the_bundle(box: Box):
    """A failure between install and converge must not strand the new config."""
    before = box.live()
    box.stage_bundle()

    completed = box.run(NEW_IMAGE, FAKE_ENV_HELPER_FAIL="1")

    assert completed.returncode == 1
    assert _result(completed) == "failed_env_write"
    assert box.live() == before
    assert box.env_image() == OLD_IMAGE


# ---------------------------------------------------------------------------
# (d) --restore-bundle restores the pointer's snapshot
# ---------------------------------------------------------------------------


def test_restore_bundle_reinstalls_the_pointed_snapshot_then_converges(box: Box):
    """The public-canary rollback path."""
    before = box.live()
    box.stage_bundle()
    assert box.run(NEW_IMAGE).returncode == 0
    assert box.live() != before, "precondition: the forward deploy installed the bundle"

    completed = box.run("--restore-bundle", OLD_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert _result(completed) == "deployed"
    assert _deployed_image(completed) == OLD_IMAGE
    assert box.live() == before, "--restore-bundle must reinstall the snapshot"
    assert box.env_image() == OLD_IMAGE


def test_restore_bundle_does_not_reinstall_the_still_staged_bundle(box: Box):
    """The staged bundle is what a canary rollback is undoing, not applying."""
    before = box.live()
    box.stage_bundle()
    assert box.run(NEW_IMAGE).returncode == 0
    assert box.stage.is_dir(), "precondition: the stage directory survives the deploy"

    completed = box.run("--restore-bundle", OLD_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert box.live() == before


def test_restore_bundle_with_no_pointer_still_rolls_the_image_back(box: Box):
    """A box that never staged a bundle must not lose its image rollback."""
    shutil.rmtree(box.stage, ignore_errors=True)
    assert not box.pointer.exists()

    completed = box.run("--restore-bundle", NEW_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert _result(completed) == "deployed"
    assert box.env_image() == NEW_IMAGE
    assert "no" in completed.stdout and "pointer" in completed.stdout


# ---------------------------------------------------------------------------
# (e) vector change -> --force-recreate logs, and the container is verified
# ---------------------------------------------------------------------------


def test_changed_vector_inputs_force_recreate_the_logs_container(box: Box):
    """vector-entrypoint.sh copies the mounts into /run/vector-config at START.

    `up -d` leaves a container whose image and compose config are unchanged
    alone, so a new vector.yaml would otherwise never reach the running vector.
    """
    box.stage_bundle()

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 0, completed.stderr
    calls = box.docker_calls_text()
    assert "up -d --force-recreate logs" in calls, calls


def test_unchanged_vector_inputs_do_not_recreate_the_logs_container(box: Box):
    """A no-op vector change must not churn the log sidecar."""
    (box.runtime / "deploy" / "vector.yaml").write_text(NEW_VECTOR, encoding="utf-8")
    (box.runtime / "deploy" / "vector-betterstack.yaml").write_text(
        NEW_BETTERSTACK, encoding="utf-8"
    )
    (box.runtime / "deploy" / "vector-entrypoint.sh").write_text(
        NEW_ENTRYPOINT, encoding="utf-8"
    )
    box.stage_bundle()

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert "--force-recreate" not in box.docker_calls_text()


def test_logs_container_that_will_not_run_after_recreate_fails_the_deploy(box: Box):
    """A dead log sidecar is a deploy failure, not a warning."""
    before = box.live()
    box.stage_bundle()
    box.set_docker_state(logs_recreate_status="exited")

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 2, completed.stderr
    assert _result(completed) == "rolled_back"
    assert box.live() == before
    assert "tinyassets-logs" in completed.stderr


# ---------------------------------------------------------------------------
# (f) absent bundle -> image-only deploy
# ---------------------------------------------------------------------------


def test_absent_bundle_is_an_image_only_deploy(box: Box):
    """A manual run with no staged bundle must still deploy the image."""
    shutil.rmtree(box.stage, ignore_errors=True)
    before = box.live()

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 0, completed.stderr
    assert _result(completed) == "deployed"
    assert "bundle: absent, image-only deploy" in completed.stdout
    assert box.live() == before
    assert box.env_image() == NEW_IMAGE
    assert not box.pointer.exists()


# ---------------------------------------------------------------------------
# refusals that must still leave production untouched
# ---------------------------------------------------------------------------


def test_failed_image_pull_leaves_the_bundle_uninstalled(box: Box):
    """The pull failure Codex named: config must not already be live."""
    before = box.live()
    box.stage_bundle()
    box.set_docker_state(pull_ok=False)

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 1
    assert box.live() == before
    assert box.env_image() == OLD_IMAGE


def test_failed_candidate_preflight_leaves_the_bundle_uninstalled(box: Box):
    before = box.live()
    box.stage_bundle()
    box.set_docker_state(preflight_ok=False)

    completed = box.run(NEW_IMAGE)

    assert completed.returncode == 1
    assert box.live() == before


# ---------------------------------------------------------------------------
# the ownership contract the runtime tests cannot assert unprivileged
# ---------------------------------------------------------------------------


def test_install_ownership_defaults_match_the_unit_contract():
    """Runtime files are `tinyassets`-owned; the systemd unit stays root's.

    The unit runs compose as `tinyassets` (deploy/tinyassets-daemon.service), so
    the files it reads must be readable by that user -- the pre-#2442 contract.
    """
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'RUNTIME_OWNER="${RUNTIME_OWNER:-tinyassets}"' in script
    assert 'RUNTIME_GROUP="${RUNTIME_GROUP:-tinyassets}"' in script
    assert 'UNIT_OWNER="${UNIT_OWNER:-root}"' in script
    assert 'UNIT_GROUP="${UNIT_GROUP:-root}"' in script
    assert 'BUNDLE_STAGE="${BUNDLE_STAGE:-/tmp/tinyassets-bundle}"' in script
    assert 'BUNDLE_STATE_DIR="${BUNDLE_STATE_DIR:-/var/lib/tinyassets-deploy}"' in script
