"""Two-universe grant-isolation integration proof (S3 executor boundary).

Buildable for the first time on the integration base: a REAL
``PlatformVaultBackend`` wired (via the S5 construction point) to a REAL run
store + daemon registry. Universe A and universe B each deposit a credential
and mint job grants from their own authoritative runs; the suite proves B can
never resolve A's credential and that wrong-run, forged-capability replay,
expiry, cross-universe mint, and missing ``verify_context`` ALL fail closed.

No mocks anywhere on the authority path: daemons, runtime instances, runs,
grants, and ciphertext are the production code paths.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from tinyassets.credential_broker import (
    GITHUB_PROVIDER,
    GITHUB_WRITE_PURPOSE,
    deposit_credential,
    find_binding,
    platform_backend,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    JobGrant,
    SecretKind,
    VaultErrorCode,
)
from tinyassets.credentials.paths import platform_vault_db_path


def _provision(data_root, *, founder: str, universe_id: str) -> str:
    """Real daemon + runtime instance + run for one universe. Returns run_id."""
    from tinyassets.daemon_registry import create_daemon, summon_daemon
    from tinyassets.runs import create_run

    daemon = create_daemon(
        data_root, display_name=f"daemon-{universe_id}", created_by=founder
    )
    runtime = summon_daemon(
        data_root,
        daemon_id=daemon["daemon_id"],
        universe_id=universe_id,
        provider_name="claude-code",
        model_name="test-model",
        created_by=founder,
    )
    return create_run(
        data_root,
        branch_def_id=f"branch-{universe_id}",
        thread_id=f"thread-{universe_id}",
        inputs={},
        daemon_id=daemon["daemon_id"],
        runtime_instance_id=runtime["runtime_instance_id"],
    )


@pytest.fixture()
def two_universes(platform_vault_env):
    """Universe A (founder-a) and universe B (founder-b), each with a
    deposited GitHub credential and a live run."""
    data_root = platform_vault_env
    setup = {}
    for label, founder, universe_id, secret in (
        ("a", "founder-a", "u-alpha", b"ghp_secret_ALPHA"),
        ("b", "founder-b", "u-beta", b"ghp_secret_BETA"),
    ):
        run_id = _provision(data_root, founder=founder, universe_id=universe_id)
        deposit_credential(
            universe_id=universe_id,
            founder_id=founder,
            provider=GITHUB_PROVIDER,
            destination=f"octo/{universe_id}",
            purpose=GITHUB_WRITE_PURPOSE,
            kind=SecretKind.GITHUB_PAT,
            value=secret,
        )
        setup[label] = {
            "founder": founder,
            "universe_id": universe_id,
            "run_id": run_id,
            "secret": secret,
            "binding": find_binding(
                universe_id, GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE,
                f"octo/{universe_id}",
            ),
        }
    setup["backend"] = platform_backend()
    setup["data_root"] = data_root
    return setup


def _verifier_for(universe_id: str, run_id: str):
    """The live-executor identity check S3 passes at resolve time."""

    def _verify(context) -> bool:
        return context.universe_id == universe_id and context.run_id == run_id

    return _verify


def test_each_universe_resolves_only_its_own_credential(two_universes):
    be = two_universes["backend"]
    for label in ("a", "b"):
        entry = two_universes[label]
        grant = be.mint_job_grant(
            entry["binding"], entry["binding"].scope, entry["run_id"]
        )
        with be.resolve_job_grant(
            grant,
            verify_context=_verifier_for(entry["universe_id"], entry["run_id"]),
        ) as lease:
            assert lease.reveal() == entry["secret"]


def test_b_cannot_mint_against_a_binding(two_universes):
    """Cross-universe mint: B's run cannot anchor a grant for A's credential —
    the authoritative run context disagrees with the expected scope."""
    be = two_universes["backend"]
    a, b = two_universes["a"], two_universes["b"]
    with pytest.raises(CredentialUnavailable) as exc:
        be.mint_job_grant(a["binding"], a["binding"].scope, b["run_id"])
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_b_grant_never_yields_a_secret_even_with_permissive_verifier(
    two_universes,
):
    """Worst-case worker compromise: B presents its own grant with a verifier
    that approves ANYTHING. It still only ever receives B's credential —
    the broker resolves against the grant's own stored context."""
    be = two_universes["backend"]
    a, b = two_universes["a"], two_universes["b"]
    grant_b = be.mint_job_grant(b["binding"], b["binding"].scope, b["run_id"])
    with be.resolve_job_grant(grant_b, verify_context=lambda _ctx: True) as lease:
        assert lease.reveal() == b["secret"]
        assert lease.reveal() != a["secret"]


def test_wrong_run_id_fails_closed(two_universes):
    be = two_universes["backend"]
    a = two_universes["a"]
    with pytest.raises(CredentialUnavailable) as exc:
        be.mint_job_grant(a["binding"], a["binding"].scope, "run-that-never-was")
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_missing_verify_context_fails_closed(two_universes):
    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(a["binding"], a["binding"].scope, a["run_id"])
    with pytest.raises(CredentialUnavailable) as exc:
        be.resolve_job_grant(grant)
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_rejecting_verifier_fails_closed(two_universes):
    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(a["binding"], a["binding"].scope, a["run_id"])
    with pytest.raises(CredentialUnavailable) as exc:
        be.resolve_job_grant(grant, verify_context=lambda _ctx: False)
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_forged_capability_replay_fails_closed(two_universes):
    """A bearer that learns a grant_id but not the private capability cannot
    resolve — the stored hash never matches."""
    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(a["binding"], a["binding"].scope, a["run_id"])
    forged = JobGrant(grant_id=grant.grant_id, secret=b"\x00" * 32)
    with pytest.raises(CredentialUnavailable) as exc:
        be.resolve_job_grant(
            forged, verify_context=_verifier_for(a["universe_id"], a["run_id"])
        )
    assert exc.value.code == VaultErrorCode.LEASE_LOST


def test_expired_grant_fails_closed(two_universes):
    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(
        a["binding"], a["binding"].scope, a["run_id"], ttl=0.05
    )
    time.sleep(0.1)
    with pytest.raises(CredentialUnavailable) as exc:
        be.resolve_job_grant(
            grant, verify_context=_verifier_for(a["universe_id"], a["run_id"])
        )
    assert exc.value.code == VaultErrorCode.EXPIRED


def test_revoked_grant_fails_closed(two_universes):
    """Grant GC seam: after job completion the daemon revokes the grant row
    (S3's completion hook calls revoke_grant); a revoked grant is NOT_FOUND."""
    from tinyassets.credentials.grants import revoke_grant

    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(a["binding"], a["binding"].scope, a["run_id"])
    conn = sqlite3.connect(platform_vault_db_path())
    try:
        revoke_grant(conn, grant.grant_id)
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        be.resolve_job_grant(
            grant, verify_context=_verifier_for(a["universe_id"], a["run_id"])
        )
    assert exc.value.code == VaultErrorCode.NOT_FOUND


def test_grant_object_carries_no_replayable_identifiers(two_universes):
    be = two_universes["backend"]
    a = two_universes["a"]
    grant = be.mint_job_grant(a["binding"], a["binding"].scope, a["run_id"])
    text = repr(grant)
    assert a["run_id"] not in text
    assert a["universe_id"] not in text
    assert "redacted" in text
