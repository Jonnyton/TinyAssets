from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "desktop-release.yml"
SUPERVISOR = Path(__file__).with_name("windows_lifecycle_supervisor.ps1")
PWSH = shutil.which("pwsh") or shutil.which("powershell")


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
    assert "windows_lifecycle_supervisor.ps1" in workflow
    assert "windows_lifecycle.ps1" in supervisor
    assert "health-probe" in lifecycle
    assert "Invoke-Installer" in lifecycle
    assert "unins000.exe" in lifecycle
    assert "clean-machine-content-marker.txt" in lifecycle


def test_unsigned_windows_lifecycle_is_bounded_and_diagnostic() -> None:
    workflow = _workflow_text()
    lifecycle = Path(__file__).with_name("windows_lifecycle.ps1").read_text(
        encoding="utf-8"
    )
    install_job = workflow.split("  test-unsigned-windows-install:", 1)[1].split(
        "  sign-and-verify:", 1
    )[0]

    assert "timeout-minutes: 10" in install_job
    assert "windows_lifecycle_supervisor.ps1" in install_job
    assert "-TotalTimeoutSeconds 300" in install_job
    assert "PhaseTimeoutSeconds" in lifecycle
    assert "WaitForExit" in lifecycle
    assert ".Kill()" in lifecycle
    assert ".Kill($true)" not in lifecycle
    assert "timed out after" in lifecycle
    assert "initial install" in lifecycle
    assert "packaged health probe" in lifecycle
    assert "same-version repair" in lifecycle
    assert "uninstall" in lifecycle
    assert "Start-Process" in lifecycle
    assert "-Wait" not in lifecycle
    assert "10_000" not in lifecycle


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
Start-Sleep -Seconds 60
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(tmp_path)

    started = time.monotonic()
    result = subprocess.run(
        [
            PWSH,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SUPERVISOR),
            "-Installer",
            str(installer),
            "-LifecycleScript",
            str(lifecycle),
            "-PhaseTimeoutSeconds",
            "1",
            "-TotalTimeoutSeconds",
            "2",
            "-CleanupTimeoutSeconds",
            "2",
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
    assert "total lifecycle timed out after 2 seconds" in output


def test_release_workflow_has_no_fake_signature_fallback() -> None:
    workflow = _workflow_text().lower()

    assert "self-signed" not in workflow
    assert "ad-hoc" not in workflow
    assert "fake signature" not in workflow
