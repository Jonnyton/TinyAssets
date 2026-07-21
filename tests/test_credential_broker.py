"""S5 seam tests: daemon-side vault wiring, binding registry, deposit/resolve.

The vault CORE's own guarantees (crypto, CAS, grants, refresh fencing) are
proven in ``test_credential_vault_core/hardening/redaction/concurrency``.
This suite proves the SEAM: run-context lookup against the real run store,
the non-secret binding registry, typed misses, fail-closed legacy/redeposit
states, and the CLI env overlay. Uses the shared ``platform_vault_env``
fixture (tmp data root + in-memory KEK + per-test rollback guard).
"""

from __future__ import annotations

import json

import pytest

from tinyassets import credential_broker as broker
from tinyassets.credential_broker import (
    BINDING_STATUS_NEEDS_REDEPOSIT,
    ENGINE_DESTINATION,
    ENGINE_PURPOSE,
    GITHUB_PROVIDER,
    GITHUB_WRITE_PURPOSE,
    LegacyCredentialVaultError,
    deposit_credential,
    deposit_engine_api_key,
    find_binding,
    github_token,
    platform_store,
    provider_auth_env_overrides,
    record_binding,
    require_no_legacy_vault,
    run_context_lookup,
    universe_has_bindings,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    SecretBinding,
    SecretKind,
    SecretScope,
    VaultErrorCode,
    new_secret_ref,
)

FOUNDER = "founder-sub-1"


def _universe(data_root, name: str):
    udir = data_root / name
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def _deposit_github(data_root, universe_id: str, destination: str, token: bytes):
    return deposit_credential(
        universe_id=universe_id,
        founder_id=FOUNDER,
        provider=GITHUB_PROVIDER,
        destination=destination,
        purpose=GITHUB_WRITE_PURPOSE,
        kind=SecretKind.GITHUB_PAT,
        value=token,
    )


# ---------------------------------------------------------------------------
# run_context_lookup — the authoritative run-record join
# ---------------------------------------------------------------------------


def _provision_run(data_root, *, founder: str, universe_id: str) -> str:
    """A REAL daemon + runtime instance + run row (no mocks)."""
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
        branch_def_id="branch-1",
        thread_id="thread-1",
        inputs={},
        daemon_id=daemon["daemon_id"],
        runtime_instance_id=runtime["runtime_instance_id"],
    )


def test_run_context_lookup_returns_authoritative_context(platform_vault_env):
    data_root = platform_vault_env
    run_id = _provision_run(data_root, founder=FOUNDER, universe_id="u-ctx")
    context = run_context_lookup(data_root)(run_id)
    assert context.run_id == run_id
    assert context.universe_id == "u-ctx"
    assert context.founder_id == FOUNDER  # runs.owner_user_id, daemon-resolved


def test_run_context_lookup_rejects_stopped_run(platform_vault_env):
    from tinyassets.runs import RUN_STATUS_CANCELLED, update_run_status

    data_root = platform_vault_env
    run_id = _provision_run(data_root, founder=FOUNDER, universe_id="u-stopped")
    update_run_status(data_root, run_id, status=RUN_STATUS_CANCELLED)

    with pytest.raises(LookupError, match="not grant-authorized"):
        run_context_lookup(data_root)(run_id)


def test_run_context_lookup_missing_run_fails_loud(platform_vault_env):
    data_root = platform_vault_env
    _provision_run(data_root, founder=FOUNDER, universe_id="u-ctx")
    with pytest.raises(LookupError):
        run_context_lookup(data_root)("no-such-run")


def test_run_context_lookup_run_without_runtime_identity_fails_loud(
    platform_vault_env,
):
    from tinyassets.runs import create_run

    data_root = platform_vault_env
    run_id = create_run(
        data_root,
        branch_def_id="branch-1",
        thread_id="thread-1",
        inputs={},
        owner_user_id=FOUNDER,
    )
    with pytest.raises(LookupError, match="runtime_instance_id"):
        run_context_lookup(data_root)(run_id)


def test_run_context_lookup_ownerless_run_fails_loud(platform_vault_env):
    from tinyassets.runs import create_run

    data_root = platform_vault_env
    run_id = create_run(
        data_root,
        branch_def_id="branch-1",
        thread_id="thread-1",
        inputs={},
        owner_user_id="",
    )
    with pytest.raises(LookupError, match="owner_user_id"):
        run_context_lookup(data_root)(run_id)


# ---------------------------------------------------------------------------
# Binding registry + deposit/resolve
# ---------------------------------------------------------------------------


def test_deposit_and_resolve_roundtrip(platform_vault_env):
    projection = _deposit_github(
        platform_vault_env, "u-a", "octo/repo-a", b"ghp_secret_a"
    )
    # Public projection is non-secret: ref/kind/scope only.
    assert projection["kind"] == "github_pat"
    assert "ghp_secret_a" not in json.dumps(projection, default=str)
    binding = find_binding("u-a", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo-a")
    from tinyassets.credential_broker import resolve_credential

    with resolve_credential(
        "u-a", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo-a"
    ) as lease:
        assert lease.reveal() == b"ghp_secret_a"
        assert lease.ref == binding.ref


def test_redeposit_cas_rotates_value_and_revokes_outstanding_grants(
    platform_vault_env,
):
    _deposit_github(platform_vault_env, "u-rotate", "octo/repo", b"old-token")
    binding = find_binding(
        "u-rotate", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo"
    )
    backend = broker.platform_backend()
    run_id = _provision_run(
        platform_vault_env, founder=FOUNDER, universe_id="u-rotate"
    )
    grant = backend.mint_job_grant(binding, binding.scope, run_id)
    with backend.resolve_job_grant(grant, verify_context=lambda _ctx: True) as lease:
        assert lease.reveal() == b"old-token"

    projection = _deposit_github(
        platform_vault_env, "u-rotate", "octo/repo", b"new-token"
    )

    assert projection["ref"] == binding.ref
    with broker.resolve_credential(
        "u-rotate", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo"
    ) as lease:
        assert lease.reveal() == b"new-token"
        assert lease.version == 2
    with pytest.raises(CredentialUnavailable) as exc:
        backend.resolve_job_grant(grant, verify_context=lambda _ctx: True)
    assert exc.value.code == VaultErrorCode.NOT_FOUND


def test_new_deposit_registry_failure_revokes_unbound_value(
    platform_vault_env, monkeypatch
):
    backend = broker.platform_backend()
    captured = {}
    original_put = backend.put

    def capturing_put(*args, **kwargs):
        descriptor = original_put(*args, **kwargs)
        captured["descriptor"] = descriptor
        return descriptor

    monkeypatch.setattr(backend, "put", capturing_put)

    def fail_registry(*_args, **_kwargs):
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    monkeypatch.setattr(broker, "record_binding", fail_registry)
    with pytest.raises(CredentialUnavailable) as exc:
        deposit_credential(
            universe_id="u-registry-fail",
            founder_id=FOUNDER,
            provider=GITHUB_PROVIDER,
            destination="octo/repo",
            purpose=GITHUB_WRITE_PURPOSE,
            kind=SecretKind.GITHUB_PAT,
            value=b"must-not-remain-live",
            backend=backend,
        )
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE

    descriptor = captured["descriptor"]
    with pytest.raises(CredentialUnavailable) as revoked:
        backend.get(descriptor.binding, descriptor.binding.scope)
    assert revoked.value.code == VaultErrorCode.NOT_FOUND


def test_find_binding_typed_miss_never_none(platform_vault_env):
    _deposit_github(platform_vault_env, "u-a", "octo/repo-a", b"t")
    with pytest.raises(CredentialUnavailable) as exc:
        find_binding("u-a", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/other")
    assert exc.value.code == VaultErrorCode.NOT_FOUND


def test_needs_redeposit_binding_requires_reauthorization(platform_vault_env):
    binding = SecretBinding(
        ref=new_secret_ref(),
        kind=SecretKind.GITHUB_PAT,
        scope=SecretScope(
            founder_id="legacy:unverified",
            universe_id="u-legacy",
            provider=GITHUB_PROVIDER,
            destination="octo/old",
            purpose=GITHUB_WRITE_PURPOSE,
        ),
        store=platform_store(),
    )
    record_binding(binding, status=BINDING_STATUS_NEEDS_REDEPOSIT)
    with pytest.raises(CredentialUnavailable) as exc:
        find_binding("u-legacy", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/old")
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_corrupt_registry_row_fails_closed(platform_vault_env):
    import sqlite3

    _deposit_github(platform_vault_env, "u-a", "octo/repo-a", b"t")
    conn = sqlite3.connect(broker.bindings_db_path())
    conn.execute("UPDATE credential_bindings SET ref = 'not-a-ref'")
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        find_binding("u-a", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo-a")
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_tampered_registry_scope_cannot_leak_value(platform_vault_env):
    """A rewritten registry scope fails the AEAD decrypt — registry tamper
    can redirect a lookup but never decrypt another scope's value."""
    import sqlite3

    _deposit_github(platform_vault_env, "u-a", "octo/repo-a", b"secret-a")
    conn = sqlite3.connect(broker.bindings_db_path())
    conn.execute(
        "UPDATE credential_bindings SET universe_id = 'u-b', founder_id = 'thief'"
    )
    conn.commit()
    conn.close()
    from tinyassets.credential_broker import resolve_credential

    with pytest.raises(CredentialUnavailable) as exc:
        resolve_credential("u-b", GITHUB_PROVIDER, GITHUB_WRITE_PURPOSE, "octo/repo-a")
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


# ---------------------------------------------------------------------------
# GitHub two-tier contract
# ---------------------------------------------------------------------------


def test_github_token_tristate_contract(platform_vault_env):
    data_root = platform_vault_env
    udir = _universe(data_root, "u-gh")
    # Not vault-routed at all -> None (caller MAY use its env tier).
    assert github_token(udir, "octo/repo") is None
    # Vault-routed, wrong destination -> "" (env tier BLOCKED).
    _deposit_github(data_root, "u-gh", "octo/repo", b"tok-gh")
    assert github_token(udir, "octo/other") == ""
    # Vault-routed, matching -> the token.
    assert github_token(udir, "octo/repo") == "tok-gh"


def test_github_token_needs_redeposit_raises(platform_vault_env):
    udir = _universe(platform_vault_env, "u-q")
    record_binding(
        SecretBinding(
            ref=new_secret_ref(),
            kind=SecretKind.GITHUB_PAT,
            scope=SecretScope(
                founder_id="legacy:unverified", universe_id="u-q",
                provider=GITHUB_PROVIDER, destination="octo/repo",
                purpose=GITHUB_WRITE_PURPOSE,
            ),
            store=platform_store(),
        ),
        status=BINDING_STATUS_NEEDS_REDEPOSIT,
    )
    with pytest.raises(CredentialUnavailable) as exc:
        github_token(udir, "octo/repo")
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


# ---------------------------------------------------------------------------
# Legacy-state fail-closed boundary
# ---------------------------------------------------------------------------


def test_legacy_vault_file_blocks_all_reads(platform_vault_env):
    udir = _universe(platform_vault_env, "u-old")
    (udir / ".credential-vault.json").write_text("{}", encoding="utf-8")
    with pytest.raises(LegacyCredentialVaultError):
        require_no_legacy_vault(udir)
    with pytest.raises(LegacyCredentialVaultError):
        github_token(udir, "octo/repo")
    with pytest.raises(LegacyCredentialVaultError):
        provider_auth_env_overrides("claude-code", udir)


def test_orphan_credentials_dir_without_marker_blocks(platform_vault_env):
    udir = _universe(platform_vault_env, "u-orphan")
    (udir / ".credentials").mkdir()
    with pytest.raises(LegacyCredentialVaultError):
        require_no_legacy_vault(udir)


def test_migration_marker_unblocks(platform_vault_env):
    udir = _universe(platform_vault_env, "u-done")
    (udir / ".credential-vault.retired.json").write_text(
        json.dumps({"schema": 1}), encoding="utf-8"
    )
    require_no_legacy_vault(udir)  # no raise


# ---------------------------------------------------------------------------
# Engine env overlay
# ---------------------------------------------------------------------------


def test_engine_api_key_overlay_maps_service_to_cli_env(platform_vault_env):
    udir = _universe(platform_vault_env, "u-eng")
    deposit_engine_api_key(
        universe_id="u-eng", founder_id=FOUNDER,
        service="anthropic", api_key="sk-ant-test-XYZ",
    )
    overrides = provider_auth_env_overrides("claude-code", udir)
    assert overrides == {"ANTHROPIC_API_KEY": "sk-ant-test-XYZ"}
    # No cross-provider bleed.
    assert provider_auth_env_overrides("codex", udir) == {}


def test_engine_overlay_empty_without_any_deposit(platform_vault_env):
    udir = _universe(platform_vault_env, "u-none")
    assert provider_auth_env_overrides("claude-code", udir) == {}
    assert provider_auth_env_overrides("codex", udir) == {}


def test_engine_overlay_needs_redeposit_fails_closed(platform_vault_env):
    udir = _universe(platform_vault_env, "u-stop")
    record_binding(
        SecretBinding(
            ref=new_secret_ref(),
            kind=SecretKind.API_KEY,
            scope=SecretScope(
                founder_id="legacy:unverified", universe_id="u-stop",
                provider="anthropic", destination=ENGINE_DESTINATION,
                purpose=ENGINE_PURPOSE,
            ),
            store=platform_store(),
        ),
        status=BINDING_STATUS_NEEDS_REDEPOSIT,
    )
    with pytest.raises(CredentialUnavailable) as exc:
        provider_auth_env_overrides("claude-code", udir)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_engine_claude_oauth_token_overlay(platform_vault_env):
    udir = _universe(platform_vault_env, "u-oauth")
    deposit_credential(
        universe_id="u-oauth", founder_id=FOUNDER, provider="claude",
        destination=ENGINE_DESTINATION, purpose=ENGINE_PURPOSE,
        kind=SecretKind.OAUTH2_GENERIC, value=b"tok-universe-oauth",
    )
    overrides = provider_auth_env_overrides("claude-code", udir)
    assert overrides == {"CLAUDE_CODE_OAUTH_TOKEN": "tok-universe-oauth"}


def test_engine_codex_bundle_materializes_engine_auth_home(platform_vault_env):
    udir = _universe(platform_vault_env, "u-codex")
    deposit_credential(
        universe_id="u-codex", founder_id=FOUNDER, provider="codex",
        destination=ENGINE_DESTINATION, purpose=ENGINE_PURPOSE,
        kind=SecretKind.OAUTH2_GENERIC, value=b"{}",
    )
    overrides = provider_auth_env_overrides("codex", udir)
    home = udir / ".engine-auth" / "codex"
    assert overrides == {"CODEX_HOME": str(home)}
    assert (home / "auth.json").read_text(encoding="utf-8") == "{}"
    assert (home / "config.toml").read_text(encoding="utf-8") == (
        'cli_auth_credentials_store = "file"\n'
    )
    # The new materialization dir is NOT the legacy .credentials path, so the
    # legacy-remnant guard stays meaningful.
    require_no_legacy_vault(udir)


def test_subprocess_env_for_provider_end_to_end(platform_vault_env, monkeypatch):
    import tinyassets.engine_binding as engine_binding
    from tinyassets.config import write_universe_config_fields
    from tinyassets.providers.base import subprocess_env_for_provider

    udir = _universe(platform_vault_env, "u-subproc")
    write_universe_config_fields(udir, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id="u-subproc", founder_id=FOUNDER,
        service="anthropic", api_key="sk-ant-e2e",
    )
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)
    env = subprocess_env_for_provider("claude-code", universe_dir=udir)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-e2e"
    assert env.get("CLAUDE_CONFIG_DIR") == str(udir / ".engine-auth" / "claude")


def test_universe_has_bindings_counts_all_statuses(platform_vault_env):
    _deposit_github(platform_vault_env, "u-a", "octo/repo-a", b"t")
    assert universe_has_bindings("u-a") is True
    assert universe_has_bindings("u-a", provider=GITHUB_PROVIDER) is True
    assert universe_has_bindings("u-zzz") is False


# ---------------------------------------------------------------------------
# Legacy module is a fail-closed marker
# ---------------------------------------------------------------------------


def test_legacy_credential_vault_module_is_retired():
    from tinyassets import credential_vault
    from tinyassets.credential_vault import LegacyCredentialVaultRetired

    for name in (
        "load_credential_vault", "write_credential_vault", "resolve_github_token",
        "provider_auth_env_overrides", "apply_provider_auth_env", "vault_exists",
        "resolve_llm_api_key", "ensure_codex_home_from_vault",
    ):
        with pytest.raises(LegacyCredentialVaultRetired):
            getattr(credential_vault, name)()
