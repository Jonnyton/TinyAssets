"""Composition tests use real held lease directories, never registry traffic."""

import json
import os
import sys
from unittest.mock import patch

import pytest

from tinyassets import node_sandbox as sandbox
from tinyassets import workspace_provision_execution as execution
from tinyassets.workspace_provision import admit_requirements
from tinyassets.workspace_provision_process import StageResult
from tinyassets.workspace_registry_process import BrokerReceipt
from tinyassets.workspace_resolver import ProvisionManifests


@pytest.fixture
def attempt(tmp_path):
    if sys.platform != "linux":
        pytest.skip("held lease directories require Linux")
    repo = tmp_path / "repo"
    repo.mkdir()
    fds = [os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
           for path in (tmp_path, repo)]
    manifests = ProvisionManifests(admit_requirements(
        "example==1.0 --hash=sha256:" + "a" * 64), None)
    def run(**overrides):
        kwargs = dict(lease_fd=fds[0], repo_fd=fds[1], max_transfer_bytes=1000,
                      storage_bound=1024*1024, timeout_s=5, cancelled=lambda: False)
        kwargs.update(overrides)
        return execution.execute_provision(manifests, **kwargs)
    try:
        yield run, tmp_path, repo, fds
    finally:
        for fd in fds:
            os.close(fd)


@pytest.fixture
def stages(monkeypatch):
    events = []
    class Broker:
        def __init__(self, **kwargs):
            self.closed = False
            events.append(("reserve-bound", kwargs["max_bytes"]))
        def start(self):
            events.append("broker-start")
        def close(self):
            self.closed = True
            events.append("broker-closed")
    def stage(launcher, source, args, **kwargs):
        phase = launcher.provision_mount.phase
        events.append(phase)
        settings = json.loads(args[0])
        assert settings["env"] == execution.resolver.resolver_environment(
            "/tmp", "/usr/local/bin:/usr/bin:/bin")
        assert "TOKEN" not in source
        assert kwargs["storage_usage"]() > 0
        assert kwargs["cancelled"]() is False
        if phase == "acquire":
            assert launcher.workspace_bind is None
            assert "-I" in settings["commands"][0]
            assert kwargs["broker"].closed is False
        else:
            assert events.index("broker-closed") < events.index("install")
            assert "broker" not in kwargs
            assert launcher.workspace_bind.startswith("/proc/self/fd/")
            assert "--proxy" not in settings["commands"][0]
        return StageResult(None, b"private log", b"private error", (
            BrokerReceipt(123, 123, 1, None) if phase == "acquire" else None))
    monkeypatch.setattr(execution, "RegistryBrokerProcess", Broker)
    monkeypatch.setattr(execution, "run_provision_stage", stage)
    return events, stage


def test_two_stages_broker_revoked_cleanup_preserves_caller_handles(attempt, stages):
    run, root, _, fds = attempt
    result = run()
    assert result == execution.ProvisionResult(None, 123)
    assert [path.name for path in root.iterdir()] == ["repo"]
    for fd in fds:
        os.fstat(fd)
    assert "private" not in repr(result)
    assert stages[0] == [("reserve-bound", 1000), "broker-start", "acquire",
                         "broker-closed", "install"]


@pytest.mark.parametrize("symlink", [False, True])
def test_existing_python_environment_never_deleted_or_started(attempt, stages, symlink):
    run, root, repo, _ = attempt
    target = repo / ".venv"
    if symlink:
        target.symlink_to(root / "does-not-exist")
    else:
        target.mkdir()
        (target / "keep").write_text("owner content")
    assert run() == execution.ProvisionResult("existing_python_environment", 0)
    assert stages[0] == []
    assert os.path.lexists(target)


def test_cancel_before_staging_has_no_broker_or_scratch(attempt, stages):
    run, root, _, _ = attempt
    assert run(cancelled=lambda: True) == execution.ProvisionResult("cancelled", 0)
    assert stages[0] == []
    assert [path.name for path in root.iterdir()] == ["repo"]


@pytest.mark.parametrize("phase", ["acquire", "install"])
def test_failed_stage_never_claims_success(attempt, stages, monkeypatch, phase):
    run, root, _, _ = attempt
    original = stages[1]
    def stage(launcher, *args, **kwargs):
        if launcher.provision_mount.phase == phase:
            stages[0].append(phase)
            return StageResult("process_failed", b"", b"secret", (
                BrokerReceipt(1000, None, None, "interrupted") if phase == "acquire" else None))
        return original(launcher, *args, **kwargs)
    monkeypatch.setattr(execution, "run_provision_stage", stage)
    result = run()
    assert result == execution.ProvisionResult(
        "process_failed", 1000 if phase == "acquire" else 123)
    assert "secret" not in repr(result)
    assert [path.name for path in root.iterdir()] == ["repo"]
    if phase == "acquire":
        assert "install" not in stages[0]


@pytest.mark.parametrize("phase", ["acquire", "install"])
def test_unverified_death_retains_scratch_and_propagates(attempt, stages, monkeypatch, phase):
    run, root, _, _ = attempt
    original = stages[1]
    def stage(launcher, *args, **kwargs):
        if launcher.provision_mount.phase == phase:
            raise sandbox.SandboxTerminationError("not known dead")
        return original(launcher, *args, **kwargs)
    monkeypatch.setattr(execution, "run_provision_stage", stage)
    with pytest.raises(sandbox.SandboxTerminationError):
        run()
    assert len(list(root.glob("provision-*"))) == 1


def test_shared_deadline_is_not_reset_for_install(attempt, stages, monkeypatch):
    run, _, _, _ = attempt
    clock = [0.0]
    timeouts = []
    original = stages[1]
    def stage(*args, **kwargs):
        timeouts.append(kwargs["timeout_s"])
        result = original(*args, **kwargs)
        clock[0] += 2.0
        return result
    monkeypatch.setattr(execution.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(execution, "run_provision_stage", stage)
    assert run().failure is None
    assert timeouts == [5.0, 3.0]


def test_unconfirmed_broker_death_prevents_offline_install_and_cleanup(
    attempt, stages, monkeypatch,
):
    run, root, _, _ = attempt
    broker_type = execution.RegistryBrokerProcess
    def close(self):
        raise RuntimeError("registry termination unconfirmed")
    monkeypatch.setattr(broker_type, "close", close)
    with pytest.raises(RuntimeError, match="termination unconfirmed"):
        run()
    assert "install" not in stages[0]
    assert len(list(root.glob("provision-*"))) == 1


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), 1801])
def test_invalid_deadline_never_launches(attempt, timeout):
    with patch.object(execution, "RegistryBrokerProcess") as broker:
        with pytest.raises(ValueError):
            attempt[0](timeout_s=timeout)
        broker.assert_not_called()
