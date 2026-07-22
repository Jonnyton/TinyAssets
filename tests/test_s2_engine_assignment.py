"""S2 — per-universe engine assignment (BYO API key) via universe action=set_engine.

Covers: config.yaml partial-merge write path, the llm_api_key vault type +
CLI-subprocess env injection, the founder-only set_engine action, and that the
API key never reaches the response or the ledger.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_vault import (
    credential_vault_path,
    load_credential_vault,
    provider_auth_env_overrides,
    resolve_llm_api_key,
    supported_llm_api_key_services,
    write_credential_vault,
)
from tinyassets.providers.base import subprocess_env_for_provider


def test_write_universe_config_fields_merges_and_preserves(tmp_path):
    write_universe_config_fields(tmp_path, preferred_writer="codex")
    assert load_universe_config(tmp_path).preferred_writer == "codex"
    # A second partial write must preserve the earlier field.
    write_universe_config_fields(tmp_path, preferred_judge="gemini-free")
    cfg = load_universe_config(tmp_path)
    assert cfg.preferred_writer == "codex"
    assert cfg.preferred_judge == "gemini-free"


def test_llm_api_key_injects_into_claude_cli_env(tmp_path):
    write_universe_config_fields(
        tmp_path,
        engine_assignment_state="ready",
        allowed_providers=["claude-code"],
    )
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test-XYZ").decode("ascii"),
    }])
    assert resolve_llm_api_key(tmp_path, "ANTHROPIC_API_KEY") == "sk-ant-test-XYZ"
    # provider_auth_env_overrides maps it to the CLI env var.
    overrides = provider_auth_env_overrides(tmp_path, "claude-code")
    assert overrides["ANTHROPIC_API_KEY"] == "sk-ant-test-XYZ"
    # The subprocess env carries it even though the global api-key strip runs first.
    env = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test-XYZ"


def test_openai_key_maps_to_codex_only(tmp_path):
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-test").decode("ascii"),
    }])
    assert provider_auth_env_overrides(tmp_path, "codex")["OPENAI_API_KEY"] == "sk-openai-test"
    # The wrong provider does not receive it (no cross-provider bleed).
    assert "OPENAI_API_KEY" not in provider_auth_env_overrides(tmp_path, "claude-code")
    assert "ANTHROPIC_API_KEY" not in provider_auth_env_overrides(tmp_path, "claude-code")


def test_set_engine_action_writes_vault_and_config(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-test"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    out = json.loads(uni._action_set_engine(
        universe_id="u-test",
        inputs_json=json.dumps({"service": "anthropic", "api_key": "sk-secret-KEY"}),
    ))
    assert out["status"] == "engine_set"
    assert out["preferred_writer"] == "claude-code"  # inferred from service
    # The key is NEVER echoed in the response.
    assert "sk-secret-KEY" not in json.dumps(out)
    # config.yaml + vault were written and resolve end-to-end.
    assert load_universe_config(udir).preferred_writer == "claude-code"
    assert resolve_llm_api_key(udir, "ANTHROPIC_API_KEY") == "sk-secret-KEY"


def test_set_engine_requires_key_and_known_service(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-x"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-x")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    missing_key = json.loads(uni._action_set_engine(
        universe_id="u-x", inputs_json=json.dumps({"service": "anthropic"})))
    assert "error" in missing_key

    bad_service = json.loads(uni._action_set_engine(
        universe_id="u-x",
        inputs_json=json.dumps({"service": "nonsense", "api_key": "k"})))
    assert "error" in bad_service
    assert "nonsense" in bad_service["error"]


def test_ledger_extractor_never_leaks_the_key():
    from tinyassets.api.universe import _extract_set_engine

    target, summary, payload = _extract_set_engine(
        {"inputs_json": json.dumps({"api_key": "sk-SECRET-LEDGER"})},
        {"universe_id": "u-1", "service": "anthropic",
         "preferred_writer": "claude-code", "status": "engine_set"},
    )
    assert "sk-SECRET-LEDGER" not in json.dumps([target, summary, payload])


def test_set_engine_is_founder_admin_scoped():
    from tinyassets.api.universe import WRITE_ACTIONS
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    # Founder-only (admin scope) + ledger/ACL-write gated.
    assert "set_engine" in _UNIVERSE_ADMIN_ACTIONS
    assert "set_engine" in WRITE_ACTIONS


def test_supported_services_cover_both_cli_routes():
    services = supported_llm_api_key_services()
    assert {"anthropic", "openai"} <= services


def _set_engine(uni, *, service, api_key, preferred_writer=""):
    payload = {"service": service, "api_key": api_key}
    if preferred_writer:
        payload["preferred_writer"] = preferred_writer
    return json.loads(uni._action_set_engine(
        universe_id="u-test",
        inputs_json=json.dumps(payload),
    ))


def _llm_api_key_record(service: str, secret: str) -> dict[str, str]:
    return {
        "credential_type": "llm_api_key",
        "service": service,
        "secret_b64": base64.b64encode(secret.encode("utf-8")).decode("ascii"),
    }


def _setup_set_engine(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-test"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)
    return uni, udir


def test_byo_assignment_uses_singleton_ceiling_and_replaces_it(tmp_path, monkeypatch):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)

    first = _set_engine(uni, service="anthropic", api_key="sk-ant-first")
    first_config = load_universe_config(udir)
    assert first["status"] == "engine_set"
    assert first_config.preferred_writer == "claude-code"
    assert first_config.allowed_providers == ["claude-code"]
    assert first_config.engine_assignment_state == "ready"

    second = _set_engine(uni, service="openai", api_key="sk-openai-second")
    second_config = load_universe_config(udir)
    assert second["status"] == "engine_set"
    assert second_config.preferred_writer == "codex"
    assert second_config.allowed_providers == ["codex"]
    assert second_config.engine_assignment_state == "ready"
    assert resolve_llm_api_key(udir, "OPENAI_API_KEY") == "sk-openai-second"
    assert resolve_llm_api_key(udir, "ANTHROPIC_API_KEY") == ""


@pytest.mark.parametrize(
    "service,preferred_writer",
    [
        ("anthropic", "codex"),
        ("openai", "claude-code"),
        ("claude", ""),
        ("claude-code", ""),
        ("codex", ""),
        ("gemini", ""),
    ],
)
def test_byo_mismatch_or_unroutable_alias_has_zero_mutation(
    tmp_path, monkeypatch, service, preferred_writer,
):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    write_universe_config_fields(
        udir,
        engine_source="byo_api_key",
        preferred_writer="claude-code",
        allowed_providers=["claude-code"],
        engine_assignment_state="ready",
        untouched="keep-me",
    )
    write_credential_vault(udir, [_llm_api_key_record("anthropic", "sk-old")])
    config_before = (udir / "config.yaml").read_bytes()
    vault_before = credential_vault_path(udir).read_bytes()

    out = _set_engine(
        uni,
        service=service,
        api_key="sk-rejected",
        preferred_writer=preferred_writer,
    )

    assert "error" in out
    assert (udir / "config.yaml").read_bytes() == config_before
    assert credential_vault_path(udir).read_bytes() == vault_before


def test_byo_assignment_preserves_unrelated_vault_records(tmp_path, monkeypatch):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    unrelated = [
        {
            "credential_type": "social",
            "service": "mastodon",
            "secret_b64": base64.b64encode(b"social-token").decode("ascii"),
        },
        {
            "credential_type": "vcs",
            "service": "github",
            "destination": "example/repo",
            "secret_b64": base64.b64encode(b"github-token").decode("ascii"),
        },
        {
            "credential_type": "llm_subscription",
            "service": "codex",
            "secret_b64": base64.b64encode(b"subscription-token").decode("ascii"),
        },
    ]
    write_credential_vault(
        udir,
        unrelated + [_llm_api_key_record("anthropic", "sk-old")],
    )

    out = _set_engine(uni, service="openai", api_key="sk-new")

    assert out["status"] == "engine_set"
    records = load_credential_vault(udir)
    assert all(record in records for record in unrelated)
    api_keys = [
        record for record in records
        if record["credential_type"] == "llm_api_key"
    ]
    assert api_keys == [_llm_api_key_record("openai", "sk-new")]


def test_byo_transaction_persists_pending_before_secret_then_ready(
    tmp_path, monkeypatch,
):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    import tinyassets.config as config_module
    import tinyassets.credential_vault as vault_module

    real_config_write = config_module.write_universe_config_fields
    real_vault_write = vault_module.write_credential_vault
    events: list[str] = []

    def record_config_write(universe_dir, **fields):
        events.append(f"config:{fields.get('engine_assignment_state')}")
        return real_config_write(universe_dir, **fields)

    def record_vault_write(universe_dir, credentials):
        events.append("vault")
        return real_vault_write(universe_dir, credentials)

    monkeypatch.setattr(config_module, "write_universe_config_fields", record_config_write)
    monkeypatch.setattr(vault_module, "write_credential_vault", record_vault_write)

    out = _set_engine(uni, service="anthropic", api_key="sk-new")

    assert out["status"] == "engine_set"
    assert events == ["config:pending", "vault", "config:ready"]
    config = load_universe_config(udir)
    assert config.engine_assignment_state == "ready"
    assert config.allowed_providers == ["claude-code"]


@pytest.mark.parametrize("prior_exists", [True, False])
def test_byo_final_config_failure_exactly_restores_prior_files(
    tmp_path, monkeypatch, prior_exists,
):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    if prior_exists:
        write_universe_config_fields(
            udir,
            preferred_writer="claude-code",
            allowed_providers=["claude-code"],
            engine_assignment_state="ready",
            untouched="prior-config",
        )
        write_credential_vault(
            udir,
            [_llm_api_key_record("anthropic", "sk-prior")],
        )
    config_path = udir / "config.yaml"
    vault_path = credential_vault_path(udir)
    config_before = config_path.read_bytes() if config_path.exists() else None
    vault_before = vault_path.read_bytes() if vault_path.exists() else None

    import tinyassets.config as config_module

    real_config_write = config_module.write_universe_config_fields
    calls = 0

    def fail_ready_write(universe_dir, **fields):
        nonlocal calls
        calls += 1
        if fields.get("engine_assignment_state") == "ready":
            raise OSError("injected final config failure")
        return real_config_write(universe_dir, **fields)

    monkeypatch.setattr(config_module, "write_universe_config_fields", fail_ready_write)

    out = _set_engine(uni, service="openai", api_key="sk-new")

    assert "error" in out
    assert calls >= 2
    assert (config_path.read_bytes() if config_path.exists() else None) == config_before
    assert (vault_path.read_bytes() if vault_path.exists() else None) == vault_before


def test_byo_rollback_failure_leaves_pending_empty_ceiling(tmp_path, monkeypatch):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    write_universe_config_fields(
        udir,
        preferred_writer="claude-code",
        allowed_providers=["claude-code"],
        engine_assignment_state="ready",
    )
    write_credential_vault(udir, [_llm_api_key_record("anthropic", "sk-prior")])

    config_path = udir / "config.yaml"
    vault_path = credential_vault_path(udir)
    real_replace = os.replace
    config_replaces = 0
    vault_replaces = 0

    def fail_commit_and_vault_restore(src, dst):
        nonlocal config_replaces, vault_replaces
        target = Path(dst)
        if target == config_path:
            config_replaces += 1
            if config_replaces == 2:
                raise OSError("injected final config failure")
        elif target == vault_path:
            vault_replaces += 1
            if vault_replaces == 2:
                raise OSError("injected vault rollback failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_commit_and_vault_restore)

    out = _set_engine(uni, service="openai", api_key="sk-new")

    assert "error" in out
    assert "rollback" in json.dumps(out).lower()
    config = load_universe_config(udir)
    assert config.engine_assignment_state == "pending"
    assert config.allowed_providers == []


def test_byo_config_restore_failure_leaves_pending_empty_ceiling(
    tmp_path, monkeypatch,
):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    write_universe_config_fields(
        udir,
        preferred_writer="claude-code",
        allowed_providers=["claude-code"],
        engine_assignment_state="ready",
    )
    write_credential_vault(udir, [_llm_api_key_record("anthropic", "sk-prior")])

    config_path = udir / "config.yaml"
    vault_path = credential_vault_path(udir)
    vault_before = vault_path.read_bytes()
    real_replace = os.replace
    config_replaces = 0

    def fail_commit_and_config_restore(src, dst):
        nonlocal config_replaces
        if Path(dst) == config_path:
            config_replaces += 1
            if config_replaces in {2, 3}:
                phase = "commit" if config_replaces == 2 else "rollback"
                raise OSError(f"injected config {phase} failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_commit_and_config_restore)

    out = _set_engine(uni, service="openai", api_key="sk-new")

    assert "error" in out
    assert "rollback" in json.dumps(out).lower()
    config = load_universe_config(udir)
    assert config.engine_assignment_state == "pending"
    assert config.allowed_providers == []
    assert vault_path.read_bytes() == vault_before


def test_engine_assignment_lock_excludes_other_process_until_release(tmp_path):
    from tinyassets.config import engine_assignment_lock

    child_code = """
import sys
from pathlib import Path
from tinyassets.config import engine_assignment_lock

universe = Path(sys.argv[1])
print("attempting", flush=True)
with engine_assignment_lock(universe):
    print("acquired", flush=True)
"""

    with engine_assignment_lock(tmp_path):
        child = subprocess.Popen(
            [sys.executable, "-c", child_code, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "attempting"
        with pytest.raises(subprocess.TimeoutExpired):
            child.wait(timeout=0.4)

    stdout, stderr = child.communicate(timeout=5)
    assert child.returncode == 0, stderr
    assert stdout.strip() == "acquired"
    # The child also released the cross-process lock on context exit.
    with engine_assignment_lock(tmp_path):
        pass


def test_cross_process_shared_readers_coexist_and_exclude_assignment_writer(
    tmp_path,
):
    reader_code = """
import sys
import time
from pathlib import Path
from tinyassets.config import engine_assignment_lock

universe, acquired, release = map(Path, sys.argv[1:4])
with engine_assignment_lock(universe, shared=True):
    acquired.write_text("acquired", encoding="utf-8")
    while not release.exists():
        time.sleep(0.01)
"""
    writer_code = """
import sys
from pathlib import Path
from tinyassets.config import engine_assignment_lock

universe, attempted, acquired = map(Path, sys.argv[1:4])
attempted.write_text("attempted", encoding="utf-8")
with engine_assignment_lock(universe):
    acquired.write_text("acquired", encoding="utf-8")
"""
    reader_one_acquired = tmp_path / "reader-one-acquired"
    reader_two_acquired = tmp_path / "reader-two-acquired"
    readers_release = tmp_path / "release-readers"
    writer_attempted = tmp_path / "writer-attempted"
    writer_acquired = tmp_path / "writer-acquired"

    def wait_for(
        path: Path,
        *,
        processes: list[subprocess.Popen] | None = None,
        timeout: float = 3.0,
    ) -> None:
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            for process in processes or []:
                if process.poll() is not None:
                    assert process.stderr is not None
                    pytest.fail(process.stderr.read())
            time.sleep(0.01)
        assert path.exists(), f"timed out waiting for {path.name}"

    readers = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                reader_code,
                str(tmp_path),
                str(marker),
                str(readers_release),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for marker in (reader_one_acquired, reader_two_acquired)
    ]
    writer = None
    try:
        # Both markers must appear before either reader releases its shared lock.
        wait_for(reader_one_acquired, processes=readers)
        wait_for(reader_two_acquired, processes=readers)
        writer = subprocess.Popen(
            [
                sys.executable,
                "-c",
                writer_code,
                str(tmp_path),
                str(writer_attempted),
                str(writer_acquired),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wait_for(writer_attempted, processes=[writer])
        with pytest.raises(subprocess.TimeoutExpired):
            writer.wait(timeout=0.4)
        assert not writer_acquired.exists()

        readers_release.write_text("release", encoding="utf-8")
        for reader in readers:
            _stdout, stderr = reader.communicate(timeout=5)
            assert reader.returncode == 0, stderr
        _stdout, stderr = writer.communicate(timeout=5)
        assert writer.returncode == 0, stderr
        assert writer_acquired.read_text(encoding="utf-8") == "acquired"
    finally:
        readers_release.touch(exist_ok=True)
        for process in [*readers, writer]:
            if process is not None and process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)


def test_same_universe_assignments_are_serialized_and_stale_failure_cannot_win(
    tmp_path, monkeypatch,
):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch)
    import tinyassets.credential_vault as vault_module

    real_vault_write = vault_module.write_credential_vault
    anthropic_entered = threading.Event()
    openai_entered = threading.Event()
    release_anthropic = threading.Event()
    counter_lock = threading.Lock()
    active = 0
    max_active = 0

    def controlled_vault_write(universe_dir, credentials):
        nonlocal active, max_active
        service = credentials[0]["service"]
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            result = real_vault_write(universe_dir, credentials)
            if service == "anthropic":
                anthropic_entered.set()
                assert release_anthropic.wait(timeout=5)
                raise OSError("injected first-assignment failure")
            openai_entered.set()
            return result
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(vault_module, "write_credential_vault", controlled_vault_write)
    results: dict[str, dict] = {}

    def assign(name, service, key):
        try:
            results[name] = _set_engine(uni, service=service, api_key=key)
        except Exception as exc:  # RED captures the current uncaught failure.
            results[name] = {"exception": str(exc)}

    first = threading.Thread(
        target=assign,
        args=("first", "anthropic", "sk-first"),
        daemon=True,
    )
    second = threading.Thread(
        target=assign,
        args=("second", "openai", "sk-second"),
        daemon=True,
    )
    first.start()
    assert anthropic_entered.wait(timeout=5)
    second.start()
    overlapped = openai_entered.wait(timeout=0.5)
    release_anthropic.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert overlapped is False
    assert max_active == 1
    assert "error" in results["first"]
    assert results["second"]["status"] == "engine_set"
    config = load_universe_config(udir)
    assert config.preferred_writer == "codex"
    assert config.allowed_providers == ["codex"]
    assert config.engine_assignment_state == "ready"
    assert resolve_llm_api_key(udir, "OPENAI_API_KEY") == "sk-second"
    assert resolve_llm_api_key(udir, "ANTHROPIC_API_KEY") == ""
