"""Opt-in process evidence for isolated cloud-behaviour tests, never autouse."""

import pytest

from tinyassets import platform_runtime_provenance as provenance


@pytest.fixture
def cloud_runtime(monkeypatch):
    """Only explicitly requesting modules/tests receive this fake observation.

    No network, credentials or production authority. Admission negatives select
    their own observations and must not inherit a suite-wide admitted default.
    """
    verdict = provenance.RuntimeProvenance(
        provenance.CLOUD, "instance_match", True, True
    )
    observation = provenance.ProcessProvenanceObservation(resolver=lambda: verdict)
    observation.observe()
    monkeypatch.setattr(provenance, "_PROCESS_OBSERVATION", observation)
    return observation


def install_admitted_observation() -> provenance.ProcessProvenanceObservation:
    """Install the fake admitted observation in THIS process, no monkeypatch.

    Only for a spawned child that cannot inherit the parent's monkeypatch (the
    cross-process load tests). Still explicit opt-in — a child calls it by name
    on its first line — and still an injected resolver: no network, no
    credential, no environment variable and no production authority.
    """
    verdict = provenance.RuntimeProvenance(
        provenance.CLOUD, "instance_match", True, True
    )
    observation = provenance.ProcessProvenanceObservation(resolver=lambda: verdict)
    observation.observe()
    provenance._PROCESS_OBSERVATION = observation
    return observation
