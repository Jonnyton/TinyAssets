from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "desktop-release.yml"
SUPERVISOR = Path(__file__).with_name("windows_lifecycle_supervisor.py")
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _supervisor_module():
    spec = importlib.util.spec_from_file_location("windows_lifecycle_supervisor", SUPERVISOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), "desktop release workflow is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_builds_all_supported_platforms() -> None:
    workflow = _workflow_text()

    assert "windows-latest" in workflow
    assert "macos-15" in workflow
    assert "ubuntu-24.04" in workflow
    assert "packaging/windows/build.ps1" in workflow
    assert "packaging/macos/build.sh" in workflow
    assert "packaging/linux/build.sh" in workflow


def test_unsigned_ci_builds_cannot_be_published_as_stable() -> None:
    workflow = _workflow_text()

    assert "unsigned-ci" in workflow
    assert "publication_requested" in workflow
    assert "signing identity not provisioned" in workflow
    assert "continue-on-error" not in workflow
    assert "publish-signed" in workflow


def test_signatures_and_notarization_are_verified_before_publication() -> None:
    workflow = _workflow_text()

    assert "signtool.exe verify" in workflow
    assert "xcrun stapler validate" in workflow
    assert '--verify "${artifact}.asc" "$artifact"' in workflow
    assert "needs: [plan, sign-and-verify]" in workflow


def test_workflow_emits_provenance_sbom_channels_and_rollback_evidence() -> None:
    workflow = _workflow_text()

    assert "actions/attest-build-provenance" in workflow
    assert "desktop_metadata.py sbom" in workflow
    assert "rollout_percent" in workflow
    assert "rollback-evidence-${{ matrix.platform }}-${{ matrix.architecture }}.json" in workflow
    assert "channel" in workflow


def test_macos_bundle_is_archived_before_cross_job_transport() -> None:
    workflow = _workflow_text()

    assert "TinyAssets.app.tar.gz" in workflow
    assert "tar -xzf" in workflow


def test_signed_outputs_are_attested_after_signing() -> None:
    workflow = _workflow_text()

    build = workflow.split("  build:", 1)[1].split("  test-unsigned-windows-install:", 1)[0]
    signing = workflow.split("sign-and-verify:", 1)[1]
    assert "actions/attest-build-provenance@v2" in signing
    assert "subject-path:" in signing
    assert "packaging/dist/${{ matrix.platform }}/*.json" in signing
    assert '--sbom "$sbom" --metadata "${artifact}.metadata.json"' in signing
    assert "--pyinstaller-analysis" in build
    assert "desktop_metadata.py sbom" in build
    assert "desktop_metadata.py sbom" not in signing
    signed_metadata = signing.split(
        "- name: Emit signed metadata, manifests, and rollback evidence", 1
    )[1]
    assert "desktop_metadata.py verify-build-sbom" in signed_metadata
    assert signed_metadata.index("desktop_metadata.py verify-build-sbom") < signed_metadata.index(
        "desktop_metadata.py metadata"
    )
    assert signed_metadata.index("desktop_metadata.py metadata") < signed_metadata.index(
        "desktop_metadata.py sign-update-manifest"
    )


def test_macos_certificate_is_imported_into_temporary_keychain() -> None:
    workflow = _workflow_text()

    assert "security import" in workflow
    assert "APPLE_CERTIFICATE_P12" in workflow


def test_unsigned_windows_artifact_is_installed_repaired_and_uninstalled() -> None:
    workflow = _workflow_text()
    lifecycle = Path(__file__).with_name("windows_lifecycle.ps1").read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")

    assert "test-unsigned-windows-install:" in workflow
    assert "windows_lifecycle_supervisor.py" in workflow
    assert "windows_lifecycle.ps1" in supervisor
    assert "health-probe" in lifecycle
    assert "Invoke-Installer" in lifecycle
    assert "unins000.exe" in lifecycle
    assert "clean-machine-content-marker.txt" in lifecycle


def test_unsigned_windows_lifecycle_is_bounded_and_diagnostic() -> None:
    workflow = _workflow_text()
    lifecycle = Path(__file__).with_name("windows_lifecycle.ps1").read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    install_job = workflow.split("  test-unsigned-windows-install:", 1)[1].split(
        "  sign-and-verify:", 1
    )[0]

    assert "timeout-minutes: 10" in install_job
    assert "actions/setup-python@v5" in install_job
    assert "windows_lifecycle_supervisor.py" in install_job
    assert "--phase-timeout-seconds 90" in install_job
    assert "--total-timeout-seconds 300" in install_job
    assert "--hard-timeout-seconds 420" in install_job
    assert "PhaseTimeoutSeconds" in lifecycle
    assert "WaitForExit" in lifecycle
    assert ".Kill()" not in lifecycle
    assert ".Kill($true)" not in lifecycle
    assert "$process.WaitForExit(10000)" not in lifecycle
    assert "Stop-Process -Id $process.Id -Force" in lifecycle
    assert "Windows lifecycle phase" in lifecycle
    assert "timed out after" in lifecycle
    assert "initial install" in lifecycle
    assert "packaged health probe" in lifecycle
    assert "same-version repair" in lifecycle
    assert "uninstall" in lifecycle
    assert "Start-Process" in lifecycle
    assert "-Wait" not in lifecycle
    assert "10_000" not in lifecycle
    assert "NamedTemporaryFile" in supervisor
    assert 'capture_path.open("rb")' in supervisor
    assert "TimeoutExpired" in supervisor
    assert "process.wait(timeout=" in supervisor
    assert "taskkill" in supervisor
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in supervisor
    assert "AssignProcessToJobObject" in supervisor
    assert "_drain_stream" in supervisor
    assert "subprocess.PIPE" in supervisor
    assert "thread.join(timeout=" in supervisor
    assert "_CHILD_BOOTSTRAP" in supervisor
    assert "faulthandler.dump_traceback_later" in supervisor
    assert "faulthandler.cancel_dump_traceback_later" in supervisor
    assert "exit=True" in supervisor


def test_windows_lifecycle_capture_replays_a_fixed_size_snapshot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = _supervisor_module()
    capture_path = tmp_path / "capture.bin"
    original_path_open = Path.open

    with capture_path.open("w+b") as capture:
        capture.write(b"before\n")
        capture.flush()

        def append_before_independent_open(
            path: Path,
            mode: str = "r",
            *args: object,
            **kwargs: object,
        ):
            if path == capture_path and mode == "rb":
                with original_path_open(capture_path, "ab") as appender:
                    appender.write(b"x" * 2048)
            return original_path_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "open", append_before_independent_open)

        destination = io.StringIO()
        supervisor._replay_capture(
            capture_path,
            capture_writer=capture,
            name="stdout",
            destination=destination,
            max_bytes=1024,
        )

    assert destination.getvalue() == "before\n"
    warning = capsys.readouterr().out
    assert "stdout capture truncated; replay cap 1024 bytes" in warning
    assert "observed at least 2055 bytes" in warning


def test_windows_lifecycle_capture_storage_is_strictly_bounded(tmp_path: Path) -> None:
    supervisor = _supervisor_module()
    capture_path = tmp_path / "bounded.capture"

    class SustainedOutput:
        remaining = 5_000_000

        def read(self, size: int) -> bytes:
            take = min(size, self.remaining)
            self.remaining -= take
            return b"x" * take

    with capture_path.open("w+b") as capture_writer:
        observed = supervisor._drain_stream(
            SustainedOutput(),
            capture_writer=capture_writer,
            max_bytes=4096,
        )

    assert observed == 5_000_000
    assert capture_path.stat().st_size == 4096


def test_windows_lifecycle_closes_tree_before_bounded_drain_wait() -> None:
    supervisor = SUPERVISOR.read_text(encoding="utf-8")

    close_boundary = supervisor.index('_checkpoint("process_tree.closed")')
    bounded_join = supervisor.index("thread.join(timeout=", close_boundary)
    assert close_boundary < bounded_join


def test_windows_lifecycle_assigns_guard_before_releasing_bootstrap() -> None:
    supervisor = SUPERVISOR.read_text(encoding="utf-8")

    assign = supervisor.index("process_job.assign(process)")
    release = supervisor.index('process.stdin.write(b"1")')
    assert assign < release


def test_windows_lifecycle_cleanup_never_uses_run_timeout_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = _supervisor_module()

    class TargetProcess:
        pid = 424242
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("target", timeout)

    class CleanupProcess:
        returncode = None
        killed = False

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("taskkill.exe", timeout)

        def kill(self):
            self.killed = True

    cleanup = CleanupProcess()
    monkeypatch.setattr(
        supervisor.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail(
            "subprocess.run timeout cleanup can wait without a second bound"
        ),
    )
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *args, **kwargs: cleanup)
    target = TargetProcess()

    supervisor._terminate_tree(target, cleanup_timeout_seconds=1)

    assert cleanup.killed is True
    assert target.killed is True


@pytest.mark.skipif(
    sys.platform != "win32" or PWSH is None,
    reason="Windows PowerShell process-tree contract",
)
def test_windows_lifecycle_supervisor_bounds_and_reports_hung_child(
    tmp_path: Path,
) -> None:
    assert PWSH is not None
    assert SUPERVISOR.is_file(), "Windows lifecycle supervisor is missing"

    installer = tmp_path / "synthetic installer.exe"
    installer.write_bytes(b"not executed by the injected lifecycle")
    lifecycle = tmp_path / "synthetic hung lifecycle.ps1"
    lifecycle.write_text(
        """param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [int]$PhaseTimeoutSeconds = 180
)
Write-Output \"synthetic lifecycle phase began for $Installer\"
while ($true) {
    [Console]::Out.WriteLine("synthetic noise " + ("x" * 4096))
}
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(tmp_path)

    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            str(SUPERVISOR),
            "--installer",
            str(installer),
            "--lifecycle-script",
            str(lifecycle),
            "--phase-timeout-seconds",
            "1",
            "--total-timeout-seconds",
            "2",
            "--cleanup-timeout-seconds",
            "2",
            "--max-capture-bytes-per-stream",
            "4096",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert elapsed < 15
    assert "synthetic lifecycle phase began" in output
    assert "stdout capture truncated; replay cap 4096 bytes" in output
    assert "total lifecycle timed out after 2 seconds" in output
    for stage in (
        "child.wait.started",
        "child.wait.timed_out",
        "cleanup.started",
        "cleanup.taskkill.started",
        "cleanup.root_wait.started",
        "cleanup.finished",
        "capture.stdout.started",
        "capture.stdout.finished",
        "capture.stderr.started",
        "capture.stderr.finished",
        "supervisor.exiting",
    ):
        assert f"stage={stage}" in output
    assert len(output) < 20_000


@pytest.mark.skipif(
    sys.platform != "win32" or PWSH is None,
    reason="Windows whole-supervisor hard-deadline contract",
)
def test_windows_lifecycle_hard_deadline_exits_outside_child_wait(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "synthetic installer.exe"
    installer.write_bytes(b"not executed by the injected lifecycle")
    lifecycle = tmp_path / "synthetic hard-deadline lifecycle.ps1"
    lifecycle.write_text(
        """param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [int]$PhaseTimeoutSeconds = 180
)
while ($true) {
    Start-Sleep -Seconds 1
}
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["TEMP"] = str(tmp_path)
    env["TMP"] = str(tmp_path)

    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            str(SUPERVISOR),
            "--installer",
            str(installer),
            "--lifecycle-script",
            str(lifecycle),
            "--phase-timeout-seconds",
            "20",
            "--total-timeout-seconds",
            "20",
            "--hard-timeout-seconds",
            "2",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert elapsed < 8
    assert "stage=supervisor.hard_deadline.armed.2s" in output
    assert "Timeout (0:00:02)!" in output


@pytest.mark.skipif(
    sys.platform != "win32" or PWSH is None,
    reason="Windows inherited descendant-handle contract",
)
def test_windows_lifecycle_supervisor_terminates_escaped_descendants(
    tmp_path: Path,
) -> None:
    assert PWSH is not None
    installer = tmp_path / "synthetic installer.exe"
    installer.write_bytes(b"not executed by the injected lifecycle")
    escaped_pid_path = tmp_path / "escaped-descendant.pid"
    escaped_done_path = tmp_path / "escaped-descendant.done"
    escaped_child = tmp_path / "escaped-descendant.ps1"
    escaped_child.write_text(
        """param(
    [Parameter(Mandatory = $true)][string]$PidPath,
    [Parameter(Mandatory = $true)][string]$DonePath
)
Set-Content -LiteralPath $PidPath -Value $PID -NoNewline
[Console]::Out.WriteLine("escaped descendant inherited output")
Start-Sleep -Seconds 5
Set-Content -LiteralPath $DonePath -Value "escaped" -NoNewline
""",
        encoding="utf-8",
    )
    quoted_child = str(escaped_child).replace("'", "''")
    quoted_pid = str(escaped_pid_path).replace("'", "''")
    quoted_done = str(escaped_done_path).replace("'", "''")
    lifecycle = tmp_path / "parent-exits-lifecycle.ps1"
    lifecycle.write_text(
        f"""param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [int]$PhaseTimeoutSeconds = 180
)
$engine = (Get-Process -Id $PID).Path
$childScript = '{quoted_child}'
$pidPath = '{quoted_pid}'
$donePath = '{quoted_done}'
$childArgs = @(
    '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-File', ('"' + $childScript + '"'),
    '-PidPath', ('"' + $pidPath + '"'),
    '-DonePath', ('"' + $donePath + '"')
)
$escaped = Start-Process -FilePath $engine -ArgumentList $childArgs -NoNewWindow -PassThru
$deadline = (Get-Date).AddSeconds(5)
while (-not (Test-Path -LiteralPath $pidPath) -and (Get-Date) -lt $deadline) {{
    Start-Sleep -Milliseconds 20
}}
if (-not (Test-Path -LiteralPath $pidPath)) {{
    throw "escaped descendant did not publish its PID"
}}
Write-Output "lifecycle parent exiting with escaped PID $($escaped.Id)"
exit 0
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["TEMP"] = str(tmp_path)
    env["TMP"] = str(tmp_path)

    started = time.monotonic()
    escaped_pid = None
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(SUPERVISOR),
                "--installer",
                str(installer),
                "--lifecycle-script",
                str(lifecycle),
                "--phase-timeout-seconds",
                "2",
                "--total-timeout-seconds",
                "5",
                "--cleanup-timeout-seconds",
                "2",
                "--max-capture-bytes-per-stream",
                "4096",
            ],
            capture_output=True,
            text=True,
            timeout=12,
            env=env,
            check=False,
        )
        supervisor_elapsed = time.monotonic() - started
    finally:
        deadline = time.monotonic() + 2
        while not escaped_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if escaped_pid_path.exists():
            escaped_pid = int(escaped_pid_path.read_text(encoding="utf-8"))
            probe = subprocess.run(
                ["tasklist.exe", "/FI", f"PID eq {escaped_pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if str(escaped_pid) in probe.stdout:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(escaped_pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert supervisor_elapsed < 3
    assert "lifecycle parent exiting with escaped PID" in output
    assert "stage=process_tree.closed" in output
    assert escaped_pid is not None
    assert str(escaped_pid) not in probe.stdout
    time.sleep(1)
    assert not escaped_done_path.exists()


def test_release_workflow_has_no_fake_signature_fallback() -> None:
    workflow = _workflow_text().lower()

    assert "self-signed" not in workflow
    assert "ad-hoc" not in workflow
    assert "fake signature" not in workflow
