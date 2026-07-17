"""Per-universe credential vault tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.credential_vault import (
    VAULT_FILENAME,
    RetiredSubscriptionLaneError,
    apply_provider_auth_env,
    load_credential_vault,
    provider_auth_env_overrides,
    resolve_github_token,
    write_credential_vault,
)


def test_vault_round_trips_typed_credentials_without_secret_summary(tmp_path):
    summary = write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "write",
                "token": "ghs_secret",
            },
            {
                "credential_type": "social",
                "service": "twitter",
                "handle": "@workflow",
                "token": "social_secret",
            },
            {
                # A legacy llm_subscription record still WRITES/LOADS (so old
                # vaults can be read + migrated) — it is just never consumed as
                # spawn auth (round-12 #1).
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": ".credentials/claude",
            },
        ],
    )

    assert summary["path"].endswith(VAULT_FILENAME)
    assert summary["credential_count"] == 3
    assert summary["credential_types"] == ["llm_subscription", "social", "vcs"]
    assert "ghs_secret" not in str(summary)
    loaded = load_credential_vault(tmp_path)
    assert loaded[0]["token"] == "ghs_secret"


def test_vault_rejects_unknown_credential_type(tmp_path):
    with pytest.raises(ValueError, match="unknown credential_type"):
        write_credential_vault(
            tmp_path,
            [{"credential_type": "database", "service": "postgres"}],
        )


def test_resolve_github_token_uses_exact_destination_and_purpose(tmp_path):
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "read",
                "token": "read-token",
            },
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "write",
                "token": "write-token",
            },
        ],
    )

    assert resolve_github_token(
        tmp_path, "Jonnyton/TinyAssets", purpose="write"
    ) == "write-token"
    assert resolve_github_token(
        tmp_path, "Jonnyton/TinyAssets", purpose="read"
    ) == "read-token"
    assert resolve_github_token(tmp_path, "jonnyton/workflow", purpose="write") == ""


# ── Retired subscription-custody lane (round-12 #1) ──────────────────────────
# Founder subscription custody is a BLOCKED lane (2026-07-02 custody research):
# a per-universe llm_subscription record is NEVER injected into a spawn. The
# platform's own subscription auth is exclusively process-global. A legacy record
# is rejected (fail loud, quarantine) rather than silently skipped or consumed.


def test_legacy_codex_subscription_record_is_rejected_not_consumed(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": "e30=",
        }],
    )
    # Codex path injects nothing itself, but a present subscription record is a
    # retired lane and must fail loud.
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "codex")


def test_legacy_claude_subscription_record_is_rejected(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "claude",
            "claude_config_dir": str(tmp_path / "durable-claude"),
            "oauth_token": "sk-oauth-legacy",
        }],
    )
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "claude-code")


def test_apply_provider_auth_env_rejects_legacy_subscription_record(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "claude",
            "oauth_token": "sk-oauth-legacy",
        }],
    )
    env = {"TINYASSETS_UNIVERSE": str(tmp_path)}
    with pytest.raises(RetiredSubscriptionLaneError):
        apply_provider_auth_env(env, "claude-code")
    # Never injected the legacy subscription token.
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_no_vault_records_produce_no_overrides(tmp_path):
    # A universe with no vault (the common case) injects nothing — host auth is
    # process-global (inherited env).
    assert provider_auth_env_overrides(tmp_path, "claude-code") == {}
    assert provider_auth_env_overrides(tmp_path, "codex") == {}


def test_missing_vault_loads_as_empty(tmp_path: Path):
    assert load_credential_vault(tmp_path) == []


# ── Retired-subscription migration + rollback (round-16 #2) ──────────────────


def test_quarantine_then_rollback_round_trips(tmp_path):
    """The migration quarantines llm_subscription records (vault stops crashing)
    and rollback restores them — reversible predeployment step (round-16 #2)."""
    from tinyassets.credential_vault import (
        has_legacy_subscription_records,
        quarantine_legacy_subscription_records,
        restore_quarantined_subscription_records,
    )

    write_credential_vault(tmp_path, [
        {"credential_type": "vcs", "service": "github",
         "destination": "o/r", "token": "t"},
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    assert has_legacy_subscription_records(tmp_path) is True

    mig = quarantine_legacy_subscription_records(tmp_path)
    assert mig["migrated"] == 1 and mig["remaining"] == 1
    assert has_legacy_subscription_records(tmp_path) is False
    # Idempotent — a second migrate is a no-op.
    assert quarantine_legacy_subscription_records(tmp_path)["migrated"] == 0

    back = restore_quarantined_subscription_records(tmp_path)
    assert back["restored"] == 1
    assert has_legacy_subscription_records(tmp_path) is True
    # Idempotent rollback — nothing left to restore.
    assert restore_quarantined_subscription_records(tmp_path)["restored"] == 0


def test_migration_module_inventory_migrate_rollback(tmp_path, monkeypatch):
    """The runnable predeployment migration MODULE inventories, migrates
    (idempotent), and rolls back across universe dirs under the data root. Runnable
    as ``python -m tinyassets.migrations.retired_subscription_records`` so it ships
    inside the package + production image (round-16 #2 / round-17 #2 deployability)."""
    import importlib

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # Two universes: one with a legacy record, one clean.
    (tmp_path / "u-legacy").mkdir()
    write_credential_vault(tmp_path / "u-legacy", [
        {"credential_type": "llm_subscription", "service": "codex",
         "auth_json_b64": "e30="},
    ])
    (tmp_path / "u-clean").mkdir()
    write_credential_vault(tmp_path / "u-clean", [
        {"credential_type": "vcs", "service": "github",
         "destination": "o/r", "token": "t"},
    ])

    module = importlib.import_module(
        "tinyassets.migrations.retired_subscription_records"
    )

    assert module.main(["--inventory"]) == 0
    # Migrate: only u-legacy is affected; idempotent on re-run.
    assert module.main(["--migrate"]) == 0
    assert not [r for r in _load_vault_types(tmp_path / "u-legacy")
                if r == "llm_subscription"]
    assert module.main(["--migrate"]) == 0  # idempotent
    # Rollback restores it.
    assert module.main(["--rollback"]) == 0
    assert "llm_subscription" in _load_vault_types(tmp_path / "u-legacy")


def test_migration_module_importable_as_module(monkeypatch, tmp_path):
    """Regression for round-17 #2: the migration is importable via its package path
    (the old ``scripts/`` path raised ModuleNotFoundError in the production image
    because ``scripts/`` is not copied). Importing the module resolves
    ``tinyassets`` cleanly and exposes a ``main`` entrypoint."""
    import importlib

    module = importlib.import_module(
        "tinyassets.migrations.retired_subscription_records"
    )
    assert callable(module.main)
    # Runs end-to-end against an empty data root (no universes) → clean exit 0.
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    assert module.main(["--inventory"]) == 0


def _load_vault_types(universe_dir):
    return [r.get("credential_type") for r in load_credential_vault(universe_dir)]


# ── Crash-idempotency of the migration (round-17 #3) ─────────────────────────


def test_r17_3_crash_between_quarantine_and_vault_rewrite_is_idempotent(
    tmp_path, monkeypatch,
):
    """Round-17 #3: the reported bug — a crash BETWEEN the quarantine write and the
    vault rewrite, followed by a retry, produced TWO quarantined copies (and rollback
    then restored TWO active subscription creds). The quarantine-BEFORE-vault order
    is kept (so a crash never LOSES the credential), and content-ID dedup makes the
    retry converge to exactly ONE quarantine copy + ONE clean rollback."""
    import json as _json

    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])

    # Inject a fault AT the vault-rewrite boundary: the quarantine file has already
    # been written (tmp.replace done) but the vault has NOT yet been rewritten. The
    # SAME patched function heals on the retry (2nd call runs the real write), so no
    # broad monkeypatch.undo() is needed.
    real_write = cv.write_credential_vault
    calls = {"n": 0}

    def _crash_first_write(universe_dir, credentials):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(
                "simulated crash after quarantine write, before vault rewrite"
            )
        return real_write(universe_dir, credentials)

    monkeypatch.setattr(cv, "write_credential_vault", _crash_first_write)

    with pytest.raises(RuntimeError):
        cv.quarantine_legacy_subscription_records(tmp_path)

    # Post-crash state: quarantine written (ONE copy), vault still holds the legacy.
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    assert qpath.is_file()
    assert len(_json.loads(qpath.read_text(encoding="utf-8"))["quarantined"]) == 1
    assert cv.has_legacy_subscription_records(tmp_path) is True

    # RETRY (2nd write call runs for real): converges to exactly ONE quarantine copy
    # + a clean vault — NOT two (the pre-fix append duplicated on retry).
    result = cv.quarantine_legacy_subscription_records(tmp_path)
    assert result["migrated"] == 1
    quarantined = _json.loads(qpath.read_text(encoding="utf-8"))["quarantined"]
    assert len(quarantined) == 1, "retry must not duplicate the quarantine archive"
    assert cv.has_legacy_subscription_records(tmp_path) is False

    # Rollback restores exactly ONE active subscription cred (not two).
    back = cv.restore_quarantined_subscription_records(tmp_path)
    assert back["restored"] == 1
    assert _load_vault_types(tmp_path).count("llm_subscription") == 1


def test_r17_3_rollback_crash_before_quarantine_delete_is_idempotent(tmp_path):
    """Round-17 #3: a crash in ROLLBACK between the vault rewrite (records restored)
    and the quarantine delete, followed by a retry, must not restore a SECOND copy.
    Content-ID dedup on re-add makes the retry a no-op that just clears the archive."""
    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    # Real migrate → a normalized quarantine archive (matches what a real crash sees).
    cv.quarantine_legacy_subscription_records(tmp_path)
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    archive_snapshot = qpath.read_text(encoding="utf-8")

    # One full rollback: vault now holds the record; quarantine deleted.
    cv.restore_quarantined_subscription_records(tmp_path)
    assert cv.has_legacy_subscription_records(tmp_path) is True

    # Simulate the crash: vault already restored, but the quarantine file was NOT
    # deleted (re-materialize the exact archive). A retry must not double-restore.
    qpath.write_text(archive_snapshot, encoding="utf-8")
    back = cv.restore_quarantined_subscription_records(tmp_path)
    assert back["restored"] == 0  # already present by content id → no second copy
    assert not qpath.exists()
    assert _load_vault_types(tmp_path).count("llm_subscription") == 1


def test_r17_3_migration_creates_serializing_lock(tmp_path):
    """Round-17 #3: the migration is serialized under a per-universe sidecar lock so
    concurrent migrations cannot interleave their read-modify-write on vault +
    quarantine. Verify the lock file exists after a migration runs."""
    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "codex",
         "auth_json_b64": "e30="},
    ])
    cv.quarantine_legacy_subscription_records(tmp_path)
    assert (tmp_path / cv.VAULT_LOCK_FILENAME).exists()


# ── Corrupt-quarantine preservation (round-18 #4) ────────────────────────────


def test_r18_4_migration_preserves_corrupt_quarantine_archive(tmp_path):
    """Round-18 #4: an UNREADABLE existing quarantine archive must be PRESERVED, not
    overwritten. The migration FAILS LOUD (ValueError) and leaves the corrupt bytes
    intact for recovery — the prior code silently converted the parse error to
    ``prior=[]`` and then replaced the file, destroying recoverable creds."""
    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    corrupt = "{ this is NOT valid json <<< recoverable-cred-bytes"
    qpath.write_text(corrupt, encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable|corrupt|refusing"):
        cv.quarantine_legacy_subscription_records(tmp_path)

    # The corrupt archive is PRESERVED byte-for-byte (never overwritten).
    assert qpath.read_text(encoding="utf-8") == corrupt
    # And the migration did NOT half-run: the vault still holds the legacy record.
    assert cv.has_legacy_subscription_records(tmp_path) is True


def test_r18_4_migration_preserves_wrong_shape_quarantine_archive(tmp_path):
    """Round-18 #4: a quarantine archive that parses as JSON but has the WRONG SHAPE
    (not a {quarantined: list} object) is also preserved + fails loud, not silently
    treated as empty and overwritten."""
    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    wrong_shape = '{"quarantined": "not-a-list"}'
    qpath.write_text(wrong_shape, encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected shape|refusing"):
        cv.quarantine_legacy_subscription_records(tmp_path)

    assert qpath.read_text(encoding="utf-8") == wrong_shape
    assert cv.has_legacy_subscription_records(tmp_path) is True
