from __future__ import annotations

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "desktop-release.yml"
)


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
    assert "rollback-evidence.json" in workflow
    assert "channel" in workflow


def test_release_workflow_has_no_fake_signature_fallback() -> None:
    workflow = _workflow_text().lower()

    assert "self-signed" not in workflow
    assert "ad-hoc" not in workflow
    assert "fake signature" not in workflow
