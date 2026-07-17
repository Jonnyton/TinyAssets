"""Legacy plaintext-vault migration: quarantine, needs_redeposit, fail-closed.

Proves the approved migration contract (design note "Legacy migration"):
values are NEVER promoted into live refs; every legacy credential becomes a
``needs_redeposit`` binding; artifacts are sealed under the platform KEK and
the plaintext removed; unreadable/ambiguous state BLOCKS with the plaintext
left in place.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.credential_broker import (
    GITHUB_PROVIDER,
    GITHUB_WRITE_PURPOSE,
    LegacyCredentialVaultError,
    github_token,
    list_bindings,
    provider_auth_env_overrides,
    require_no_legacy_vault,
)
from tinyassets.credential_migration import (
    CredentialMigrationBlocked,
    migrate_all_universes,
    migrate_universe_credentials,
)
from tinyassets.credentials import CredentialUnavailable, VaultErrorCode
from tinyassets.credentials.paths import platform_vault_dir

_SECRET_TOKEN = "ghp_LEGACY_PLAINTEXT_CANARY_77"


def _legacy_universe(data_root, name: str, records: list[dict] | None = None):
    udir = data_root / name
    udir.mkdir(parents=True, exist_ok=True)
    if records is not None:
        (udir / ".credential-vault.json").write_text(
            json.dumps({"schema_version": 1, "credentials": records}),
            encoding="utf-8",
        )
    return udir


_RECORDS = [
    {
        "credential_type": "vcs",
        "service": "github",
        "destination": "octo/legacy-repo",
        "purpose": "write",
        "token": _SECRET_TOKEN,
    },
    {
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "api_key": "sk-ant-legacy-KEY",
    },
    {
        "credential_type": "llm_subscription",
        "service": "codex",
        "auth_json_b64": "e30=",
    },
]


def test_clean_universe_is_noop(platform_vault_env):
    udir = _legacy_universe(platform_vault_env, "u-clean", records=None)
    summary = migrate_universe_credentials(udir)
    assert summary["status"] == "clean"
    assert not (udir / ".credential-vault.retired.json").exists()


def test_migration_creates_needs_redeposit_bindings_and_quarantine(
    platform_vault_env,
):
    data_root = platform_vault_env
    udir = _legacy_universe(data_root, "u-legacy", _RECORDS)
    (udir / ".credentials" / "codex").mkdir(parents=True)
    (udir / ".credentials" / "codex" / "auth.json").write_text(
        "{}", encoding="utf-8"
    )

    summary = migrate_universe_credentials(udir)
    assert summary["status"] == "migrated"

    # Plaintext is gone; the non-secret marker is present.
    assert not (udir / ".credential-vault.json").exists()
    assert not (udir / ".credentials").exists()
    marker = json.loads(
        (udir / ".credential-vault.retired.json").read_text(encoding="utf-8")
    )
    assert marker["status"] == "migrated"
    assert _SECRET_TOKEN not in json.dumps(marker)

    # Bindings exist with canonical scopes, all needs_redeposit.
    rows = list_bindings("u-legacy")
    assert len(rows) == 3
    assert {status for _b, status in rows} == {"needs_redeposit"}
    github_rows = [
        b for b, _s in rows if b.scope.provider == GITHUB_PROVIDER
    ]
    assert github_rows[0].scope.destination == "octo/legacy-repo"
    # Legacy 'write' purpose normalized to the canonical external_write.
    assert github_rows[0].scope.purpose == GITHUB_WRITE_PURPOSE

    # Quarantine blobs exist and contain NO plaintext secret bytes.
    qroot = platform_vault_dir() / "quarantine" / "u-legacy"
    blobs = list(qroot.rglob("*.quarantine.json"))
    assert len(blobs) == 2  # vault file + one .credentials artifact
    for blob in blobs:
        assert _SECRET_TOKEN not in blob.read_text(encoding="utf-8")
    manifest = json.loads(
        next(qroot.rglob("manifest.json")).read_text(encoding="utf-8")
    )
    assert len(manifest["files"]) == 2

    # Post-migration reads fail closed until re-deposit.
    require_no_legacy_vault(udir)  # marker unblocks the boundary...
    with pytest.raises(CredentialUnavailable) as exc:
        github_token(udir, "octo/legacy-repo")
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED
    with pytest.raises(CredentialUnavailable) as exc2:
        provider_auth_env_overrides("claude-code", udir)
    assert exc2.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_migration_is_idempotent(platform_vault_env):
    udir = _legacy_universe(platform_vault_env, "u-once", _RECORDS)
    assert migrate_universe_credentials(udir)["status"] == "migrated"
    assert migrate_universe_credentials(udir)["status"] == "already_migrated"
    assert len(list_bindings("u-once")) == 3  # no duplicate rows


def test_unreadable_vault_blocks_and_keeps_plaintext(platform_vault_env):
    udir = _legacy_universe(platform_vault_env, "u-bad", records=None)
    vault_file = udir / ".credential-vault.json"
    vault_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CredentialMigrationBlocked):
        migrate_universe_credentials(udir)
    assert vault_file.exists()  # BLOCK leaves the plaintext for the operator
    assert list_bindings("u-bad") == []
    # And the broker boundary stays blocked too.
    with pytest.raises(LegacyCredentialVaultError):
        github_token(udir, "octo/x")


def test_unknown_credential_type_blocks(platform_vault_env):
    udir = _legacy_universe(
        platform_vault_env, "u-unknown",
        [{"credential_type": "database", "service": "postgres"}],
    )
    with pytest.raises(CredentialMigrationBlocked):
        migrate_universe_credentials(udir)
    assert (udir / ".credential-vault.json").exists()


def test_orphan_credentials_dir_is_quarantined(platform_vault_env):
    """A .credentials/ dir with no vault file is ambiguous legacy state: it
    blocks reads until migration sweeps it into quarantine."""
    data_root = platform_vault_env
    udir = data_root / "u-orphan"
    (udir / ".credentials").mkdir(parents=True)
    (udir / ".credentials" / "stray.txt").write_text(
        _SECRET_TOKEN, encoding="utf-8"
    )
    with pytest.raises(LegacyCredentialVaultError):
        require_no_legacy_vault(udir)
    summary = migrate_universe_credentials(udir)
    assert summary["status"] == "migrated"
    assert summary["bindings_needing_redeposit"] == []
    assert not (udir / ".credentials").exists()
    require_no_legacy_vault(udir)


def test_empty_legacy_vault_migrates_to_zero_bindings(platform_vault_env):
    udir = _legacy_universe(platform_vault_env, "u-empty", [])
    summary = migrate_universe_credentials(udir)
    assert summary["status"] == "migrated"
    assert list_bindings("u-empty") == []
    assert not (udir / ".credential-vault.json").exists()


def test_migrate_all_universes_sweeps_and_reports(platform_vault_env):
    data_root = platform_vault_env
    _legacy_universe(data_root, "u-s1", _RECORDS[:1])
    _legacy_universe(data_root, "u-s2", records=None)
    summaries = migrate_all_universes()
    by_universe = {s["universe_id"]: s["status"] for s in summaries}
    assert by_universe["u-s1"] == "migrated"
    assert by_universe["u-s2"] == "clean"
