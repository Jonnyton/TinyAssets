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


# ── Retired-subscription migration — FORWARD-ONLY, safe-forward (round-19) ───


def test_quarantine_is_forward_only_and_idempotent(tmp_path):
    """The migration quarantines llm_subscription records (vault stops crashing) and
    is idempotent. Round-19: it is FORWARD-ONLY — there is NO credential rollback.
    ``restore_quarantined_subscription_records`` is removed (its rollback machinery
    was the wrong complexity — global, archive-destroying, restart-bypass-prone).
    Quarantine-away is safe because absence is tolerated (see the safe-forward test)."""
    import tinyassets.credential_vault as cv
    from tinyassets.credential_vault import (
        has_legacy_subscription_records,
        quarantine_legacy_subscription_records,
    )

    # The credential-rollback surface no longer exists.
    assert not hasattr(cv, "restore_quarantined_subscription_records")

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
    # The archive is retained as an audit trail (manual-recovery source), not undone.
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    assert qpath.is_file()
    assert len(_json_load(qpath)["quarantined"]) == 1


def test_r20_1_retired_universe_fails_closed_never_ambient(tmp_path, monkeypatch):
    """Round-20 #1 (IDENTITY ISOLATION — the corrected claim): a retired universe must
    NEVER execute on the host's ambient credentials. Removing the raw record does NOT
    make ambient fallback safe — the daemon overlays subscription auth into the host's
    CODEX_HOME/CLAUDE_CONFIG_DIR/OAuth env, so ambient = the HOST'S identity (a
    cross-identity leak). A persistent non-secret MARKER keeps the universe fail-closed
    even after the record is stripped, until it is re-bound.

    Proves: BEFORE migration (present record) → fail closed. AFTER migration (record
    gone, marker present) → STILL fail closed (no ambient host creds). A FRESH universe
    (never had a subscription) → ambient is legitimately allowed."""
    from tinyassets.credential_vault import (
        RetiredSubscriptionLaneError,
        is_retired_universe,
        provider_auth_env_overrides,
        quarantine_legacy_subscription_records,
    )
    from tinyassets.engine_binding import resolve_engine_binding

    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    # Host ambient credentials that MUST NOT be inherited by a retired universe.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-ambient-oauth")
    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy-token"},
    ])
    # BEFORE: present record → retired, needs_migration, spawn fails closed.
    assert is_retired_universe(tmp_path) is True
    assert resolve_engine_binding(tmp_path).needs_migration is True
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "claude-code")
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "codex")

    quarantine_legacy_subscription_records(tmp_path)

    # AFTER (record stripped, MARKER remains): STILL retired → STILL fails closed. This
    # is the corrected r20 behavior: the universe can NEVER run on ambient host creds.
    assert is_retired_universe(tmp_path) is True
    binding = resolve_engine_binding(tmp_path)  # must not raise
    assert binding.bound is False
    assert binding.needs_migration is True
    assert "retired" in binding.reason.lower()
    # IDENTITY ISOLATION: env resolution refuses (fail closed) for EVERY provider —
    # it never returns an env that would run the affected universe on host creds.
    for provider in ("claude-code", "codex"):
        with pytest.raises(RetiredSubscriptionLaneError):
            provider_auth_env_overrides(tmp_path, provider)


def test_r20_2_quarantine_keeps_no_raw_token_only_non_secret_marker(tmp_path):
    """Round-20 #2: the quarantine archive must NOT custody the raw subscription token.
    It retains ONLY non-secret marker metadata — service + a one-way token_sha256 +
    retired_at — and the raw token is DELETED (not moved to another file). "Moving a
    secret to another file still custodies it" is exactly what this forbids."""
    import tinyassets.credential_vault as cv

    raw_token = "sk-ant-oat-SUPER-SECRET-oauth-token-value-123456"
    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": raw_token},
    ])
    cv.quarantine_legacy_subscription_records(tmp_path)

    qpath = tmp_path / cv.QUARANTINE_FILENAME
    archive_text = qpath.read_text(encoding="utf-8")
    # The raw token must appear NOWHERE in the archive.
    assert raw_token not in archive_text, "raw OAuth token leaked into the archive"
    entry = _json_load(qpath)["quarantined"][0]
    # Only the non-secret marker fields; no raw secret-bearing field.
    assert entry["credential_type"] == "llm_subscription"
    assert entry["service"] == "claude"
    assert entry["token_sha256"] == cv.hashlib.sha256(raw_token.encode()).hexdigest()
    assert "retired_at" in entry
    for secret_field in ("oauth_token", "token", "access_token", "refresh_token",
                         "auth_json_b64", "secret", "secret_b64", "token_b64"):
        assert secret_field not in entry, f"{secret_field} must be stripped"
    # And the raw record is GONE from the vault (deleted, not just moved).
    assert cv.has_legacy_subscription_records(tmp_path) is False


def test_r20_2_archive_never_carries_raw_token_across_reruns(tmp_path):
    """Round-20 #2: even across a crash-retry (the record is still in the vault while
    the archive already exists), the archive stays non-secret — the sanitizer strips
    any raw token from BOTH the prior archive entries and the newly-retired records."""
    import tinyassets.credential_vault as cv

    raw_token = "oauth-secret-should-never-persist-raw"
    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "codex",
         "oauth_token": raw_token},
    ])
    cv.quarantine_legacy_subscription_records(tmp_path)
    # Re-inject the record (simulate a crash-then-retry: vault has it, archive exists).
    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "codex",
         "oauth_token": raw_token},
    ])
    cv.quarantine_legacy_subscription_records(tmp_path)

    qpath = tmp_path / cv.QUARANTINE_FILENAME
    archive_text = qpath.read_text(encoding="utf-8")
    assert raw_token not in archive_text
    # Deduped by (service, token_sha256) → exactly one marker, not two.
    assert len(_json_load(qpath)["quarantined"]) == 1


def test_r20_1_fresh_universe_ambient_is_legitimate(tmp_path, monkeypatch):
    """Round-20 #1: a FRESH universe (NEVER had a subscription — no record, no marker)
    legitimately runs ambient (the single-tenant host default). The fail-closed gate
    must NOT over-block a fresh universe."""
    from tinyassets.credential_vault import (
        is_retired_universe,
        provider_auth_env_overrides,
    )

    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    assert is_retired_universe(tmp_path) is False
    # Ambient is allowed: no override injected, no raise.
    assert provider_auth_env_overrides(tmp_path, "claude-code") == {}
    assert provider_auth_env_overrides(tmp_path, "codex") == {}


def test_migration_module_inventory_then_migrate_forward_only(tmp_path, monkeypatch):
    """The runnable predeployment migration MODULE inventories then migrates
    (idempotent, forward-only) across universe dirs under the data root. Runnable as
    ``python -m tinyassets.migrations.retired_subscription_records`` so it ships inside
    the package + production image (round-17 #2). Round-19: no ``--rollback`` mode."""
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
    # The --rollback mode is GONE (forward-only) → argparse rejects it (SystemExit).
    with pytest.raises(SystemExit):
        module.main(["--rollback"])


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


def _json_load(path):
    import json as _json

    return _json.loads(path.read_text(encoding="utf-8"))


# ── Crash-idempotency of the migration (round-17 #3) ─────────────────────────


def test_r17_3_crash_between_quarantine_and_vault_rewrite_is_idempotent(
    tmp_path, monkeypatch,
):
    """Round-17 #3: the reported bug — a crash BETWEEN the quarantine write and the
    vault rewrite, followed by a retry, produced TWO quarantined copies. The
    quarantine-BEFORE-vault order is kept (so a crash never LOSES the credential — it
    stays in both places), and content-ID dedup makes the retry converge to exactly
    ONE quarantine copy + a clean vault. (Round-19: quarantine stays crash-idempotent;
    there is no credential rollback — the archive is a forward-only audit trail.)"""
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
    # Exactly one record was quarantined-away; the vault is clean (safe-forward).
    assert _load_vault_types(tmp_path).count("llm_subscription") == 0


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


def test_r19_1_migration_rejects_archive_with_non_object_record(tmp_path):
    """Round-19 #1: an archive whose ``quarantined`` list contains a NON-object record
    (``{"quarantined": [42]}``) must be REJECTED by the strict shared parser BEFORE any
    mutation — it must not pass migration validation (which would clean the vault while
    leaving an un-recoverable archive). The archive is preserved; the vault is not
    touched."""
    import tinyassets.credential_vault as cv

    write_credential_vault(tmp_path, [
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    qpath = tmp_path / cv.QUARANTINE_FILENAME
    bad = '{"quarantined": [42]}'
    qpath.write_text(bad, encoding="utf-8")

    with pytest.raises(ValueError, match="not a JSON object|refusing"):
        cv.quarantine_legacy_subscription_records(tmp_path)

    # Preserved untouched; the vault legacy record is NOT cleaned (no partial mutation).
    assert qpath.read_text(encoding="utf-8") == bad
    assert cv.has_legacy_subscription_records(tmp_path) is True


def test_r19_1_strict_parser_shared_by_read_path(tmp_path):
    """Round-19 #1: the ONE strict archive parser is the shared read path. It accepts a
    well-formed archive and rejects each malformed class (unreadable, wrong top shape,
    non-object record) identically — so an archive can never pass one path + fail
    another."""
    import tinyassets.credential_vault as cv

    qpath = tmp_path / cv.QUARANTINE_FILENAME
    # Missing → empty (nothing to merge).
    assert cv._read_quarantine_archive(qpath) == []
    # Well-formed → returns the records.
    qpath.write_text('{"quarantined": [{"credential_type": "llm_subscription"}]}',
                     encoding="utf-8")
    assert cv._read_quarantine_archive(qpath) == [
        {"credential_type": "llm_subscription"}
    ]
    # Each malformed class raises (preserving the file).
    for bad in ("{ not json", '{"quarantined": "x"}', '{"quarantined": [1]}', "[]"):
        qpath.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            cv._read_quarantine_archive(qpath)
        assert qpath.read_text(encoding="utf-8") == bad  # preserved
