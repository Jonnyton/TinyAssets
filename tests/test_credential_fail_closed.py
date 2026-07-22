"""A universe with no credential of its own must not run on the host's.

Before this guard `subprocess_env_for_provider` stripped only API-key variables,
so `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CONFIG_DIR` / `CODEX_HOME` survived from
the server environment into every universe's provider subprocess. Production
mounts shared host auth homes (deploy/compose.yml), so a founder who signed up
minutes ago could spend the host's subscription via `converse` or `run_graph`,
and no receipt recorded that it happened.

Each test below states the mutation that must make it fail. A test that cannot
go red is not evidence.
"""
from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import errno
import os
import sys
import threading
from pathlib import Path

import pytest

from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_vault import (
    engine_assignment_lock,
    write_credential_vault,
)
from tinyassets.exceptions import ProviderUnavailableError
from tinyassets.providers.base import (
    API_KEY_PROVIDER_ENV_VARS,
    HOST_SUBSCRIPTION_ENV_VARS,
    ModelConfig,
    subprocess_env_for_provider,
)


@pytest.fixture
def host_auth(monkeypatch):
    """Simulate the prod container: host subscription auth present in the env."""
    for name in HOST_SUBSCRIPTION_ENV_VARS:
        monkeypatch.setenv(name, f"host-value-for-{name}")
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "0")


def _write_ready_assignment(universe: Path, provider: str = "claude-code") -> None:
    write_universe_config_fields(
        universe,
        preferred_writer=provider,
        allowed_providers=[provider],
        engine_assignment_state="ready",
    )


def _write_byo_key(universe: Path, provider: str, key: str = "fake-universe-key"):
    service = {"claude-code": "anthropic", "codex": "openai"}[provider]
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_api_key",
            "service": service,
            "api_key": key,
        }],
    )


@pytest.mark.parametrize("provider", ["claude-code", "codex"])
def test_universe_without_matching_byo_key_fails_closed(
    host_auth, tmp_path, provider,
):
    """A ready ceiling without its key cannot reach default host auth."""
    universe = tmp_path / f"u-newborn-{provider}"
    universe.mkdir()
    _write_ready_assignment(universe, provider)

    with pytest.raises(ProviderUnavailableError, match="credential|auth|key"):
        subprocess_env_for_provider(provider, universe_dir=universe)


@pytest.mark.parametrize("provider", ["claude-code", "codex"])
def test_missing_byo_key_rejects_before_cli_spawn(
    host_auth, tmp_path, monkeypatch, provider,
):
    """Neither CLI may consult its logged-in default home when the key is absent."""
    universe = tmp_path / f"u-pre-spawn-{provider}"
    universe.mkdir()
    _write_ready_assignment(universe, provider)
    spawned: list[tuple] = []

    async def forbidden_spawn(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("provider subprocess launched without a universe key")

    if provider == "claude-code":
        from tinyassets.providers import claude_provider as provider_module

        implementation = provider_module.ClaudeProvider()
        monkeypatch.setattr(
            provider_module, "_resolve_claude_cmd", lambda: (["claude"], False)
        )
    else:
        from tinyassets.providers import codex_provider as provider_module

        implementation = provider_module.CodexProvider()
        monkeypatch.setattr(
            provider_module, "_resolve_codex_cmd", lambda: (["codex"], False)
        )
    monkeypatch.setattr("asyncio.create_subprocess_exec", forbidden_spawn)

    with pytest.raises(ProviderUnavailableError, match="credential|auth|key"):
        asyncio.run(
            implementation.complete(
                "prompt",
                "system",
                ModelConfig(timeout=1),
                universe_dir=universe,
            )
        )

    assert spawned == []


@pytest.mark.parametrize(
    ("provider", "auth_var", "home_var", "home_name"),
    [
        ("claude-code", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "claude"),
        ("codex", "OPENAI_API_KEY", "CODEX_HOME", "codex"),
    ],
)
def test_explicit_byo_key_pins_private_universe_auth_home(
    host_auth, tmp_path, provider, auth_var, home_var, home_name,
):
    """A BYO CLI cannot fall through to ~/.claude or ~/.codex."""
    universe = tmp_path / f"u-private-home-{provider}"
    universe.mkdir()
    _write_ready_assignment(universe, provider)
    _write_byo_key(universe, provider)

    env = subprocess_env_for_provider(provider, universe_dir=universe)
    expected_home = universe / ".credentials" / home_name

    assert env[auth_var] == "fake-universe-key"
    assert Path(env[home_var]).resolve() == expected_home.resolve()
    assert expected_home.is_dir()


def test_host_local_daemon_keeps_its_own_auth(host_auth):
    """The guard must not break the host's own flows.

    MUTATION: strip unconditionally (drop the `resolved is not None` condition)
    -> RED, because the host daemon would lose its own credentials.
    """
    env = subprocess_env_for_provider("claude-code", universe_dir=None)

    for name in HOST_SUBSCRIPTION_ENV_VARS:
        assert env.get(name) == f"host-value-for-{name}", (
            f"{name} was stripped for a host-local call with no universe in "
            "play; that breaks the daemon and dev loop"
        )


def test_api_keys_are_still_stripped_when_not_opted_in(host_auth, tmp_path):
    """Pre-existing protection must survive the change.

    MUTATION: remove the API-key stripping -> RED.
    """
    os.environ["OPENAI_API_KEY"] = "sk-should-not-survive"
    try:
        universe = tmp_path / "u-newborn"
        universe.mkdir()
        _write_ready_assignment(universe)
        _write_byo_key(universe, "claude-code")
        env = subprocess_env_for_provider("claude-code", universe_dir=universe)
        assert "OPENAI_API_KEY" not in env
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_vault_supplied_auth_survives_ambient_stripping(host_auth, tmp_path, monkeypatch):
    """When the vault supplies auth, that value must survive untouched.

    Explicit-universe sanitization runs before the vault overlay; it must not
    strip the founder's credential after overlay.
    MUTATION: pop the host vars unconditionally -> RED.
    """
    universe = tmp_path / "u-with-vault"
    universe.mkdir()
    _write_ready_assignment(universe)

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["ANTHROPIC_API_KEY"] = "fake-universe-key"
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert env.get("ANTHROPIC_API_KEY") == "fake-universe-key", (
        "the vault supplied a credential for this universe and the ambient "
        "sanitizer discarded it"
    )


def test_explicit_universe_strips_ambient_api_keys_even_when_host_opted_in(
    host_auth, tmp_path, monkeypatch,
):
    """Host API-key opt-in is host policy, not universe authorization."""
    universe = tmp_path / "u-api-key-opt-in"
    universe.mkdir()
    _write_ready_assignment(universe)
    _write_byo_key(universe, "claude-code")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    for name in API_KEY_PROVIDER_ENV_VARS:
        monkeypatch.setenv(name, f"host-ambient-{name}")

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env["ANTHROPIC_API_KEY"] == "fake-universe-key"
    leaked = [
        name for name in API_KEY_PROVIDER_ENV_VARS
        if env.get(name, "").startswith("host-ambient-")
    ]
    assert leaked == []


def test_vault_field_does_not_preserve_unrelated_ambient_subscription_auth(
    host_auth, tmp_path, monkeypatch,
):
    """One vault overlay field must not bless every inherited host field."""
    universe = tmp_path / "u-one-vault-field"
    universe.mkdir()
    _write_ready_assignment(universe)
    vault_config_dir = str(universe / ".credentials" / "claude")

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["CLAUDE_CONFIG_DIR"] = vault_config_dir
        env["ANTHROPIC_API_KEY"] = "fake-universe-key"
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env.get("CLAUDE_CONFIG_DIR") == vault_config_dir
    leaked = [
        name
        for name in HOST_SUBSCRIPTION_ENV_VARS
        if name != "CLAUDE_CONFIG_DIR" and name in env
    ]
    assert leaked == [], (
        "a universe-supplied CLAUDE_CONFIG_DIR preserved unrelated ambient "
        f"subscription auth: {leaked}"
    )


@pytest.mark.parametrize(
    ("helper_name", "error_type"),
    [
        ("load_credential_vault", OSError),
        ("ensure_claude_config_dir_from_vault", RuntimeError),
        ("provider_auth_env_overrides", LookupError),
    ],
)
def test_non_value_error_vault_and_materialization_failures_propagate(
    host_auth, tmp_path, monkeypatch, helper_name, error_type,
):
    """Unexpected vault/helper failures must not return inherited host auth."""
    universe = tmp_path / f"u-helper-failure-{helper_name}"
    universe.mkdir()
    _write_ready_assignment(universe)

    def fail_closed(*args, **kwargs):
        raise error_type(f"injected {helper_name} failure")

    monkeypatch.setattr(
        f"tinyassets.credential_vault.{helper_name}", fail_closed
    )

    with pytest.raises(error_type, match=f"injected {helper_name} failure"):
        subprocess_env_for_provider("claude-code", universe_dir=universe)


def test_local_credential_vault_import_failure_propagates(
    host_auth, tmp_path, monkeypatch,
):
    """A local import failure must not return an ambient-auth environment."""
    universe = tmp_path / "u-import-failure"
    universe.mkdir()
    _write_ready_assignment(universe)
    real_import = builtins.__import__

    def fail_vault_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tinyassets.credential_vault":
            raise ImportError("injected credential-vault import failure")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_vault_import)

    with pytest.raises(ImportError, match="injected credential-vault import failure"):
        subprocess_env_for_provider("claude-code", universe_dir=universe)


def test_engine_assignment_lock_rethrows_non_contention_oserror(
    tmp_path, monkeypatch,
):
    """Permanent lock I/O errors must fail, not enter an infinite retry loop."""
    import tinyassets.config as config_module

    calls = 0

    def permanent_failure(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError(errno.EIO, "injected permanent lock failure")

    if sys.platform == "win32":
        monkeypatch.setattr(config_module, "_lock_windows_file", permanent_failure)
        monkeypatch.setattr(
            config_module.time,
            "sleep",
            lambda _delay: (_ for _ in ()).throw(
                AssertionError("non-contention lock failure was retried")
            ),
        )
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", permanent_failure)

    with pytest.raises(OSError) as exc_info:
        with engine_assignment_lock(tmp_path):
            pass

    assert exc_info.value.errno == errno.EIO
    assert calls == 1


def test_engine_assignment_lock_allows_shared_readers_but_rejects_writer(tmp_path):
    """Validation readers coexist while assignment writers stay exclusive."""
    reader_entered = threading.Event()
    release_reader = threading.Event()

    def hold_shared_reader() -> None:
        with engine_assignment_lock(tmp_path, shared=True):
            reader_entered.set()
            assert release_reader.wait(timeout=5)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        reader = pool.submit(hold_shared_reader)
        assert reader_entered.wait(timeout=5)
        try:
            with engine_assignment_lock(tmp_path, blocking=False, shared=True):
                pass
            with pytest.raises(BlockingIOError):
                with engine_assignment_lock(tmp_path, blocking=False):
                    pass
        finally:
            release_reader.set()
        reader.result(timeout=5)


def test_real_assignment_lock_blocks_cli_auth_and_later_retry_uses_commit(
    host_auth, tmp_path, monkeypatch,
):
    """A writer-held lock rejects materialization; retry sees one full commit."""
    from tinyassets.providers import claude_provider

    universe = tmp_path / "u-real-lock-interleaving"
    universe.mkdir()
    _write_ready_assignment(universe)
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "api_key": "fake-prior-assignment-key",
        }],
    )
    partial_written = threading.Event()
    release_writer = threading.Event()
    spawned_envs: list[dict[str, str]] = []

    def reassign_while_holding_lock() -> None:
        with engine_assignment_lock(universe):
            write_universe_config_fields(
                universe,
                engine_assignment_state="pending",
                allowed_providers=[],
            )
            write_credential_vault(
                universe,
                [{
                    "credential_type": "llm_api_key",
                    "service": "anthropic",
                    "api_key": "fake-new-assignment-key",
                }],
            )
            partial_written.set()
            assert release_writer.wait(timeout=5)
            write_universe_config_fields(
                universe,
                preferred_writer="claude-code",
                allowed_providers=["claude-code"],
                engine_assignment_state="ready",
            )

    class SuccessfulProcess:
        returncode = 0

        async def communicate(self, input=None):
            return b"complete assignment reply", b""

    async def fake_spawn(*args, **kwargs):
        spawned_envs.append(dict(kwargs.get("env") or {}))
        return SuccessfulProcess()

    def invoke_cli():
        return asyncio.run(
            claude_provider.ClaudeProvider().complete(
                "prompt",
                "system",
                ModelConfig(timeout=1),
                universe_dir=universe,
            )
        )

    monkeypatch.setattr(
        claude_provider, "_resolve_claude_cmd", lambda: (["claude"], False)
    )
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_spawn)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(reassign_while_holding_lock)
        assert partial_written.wait(timeout=5)
        first_attempt = pool.submit(invoke_cli)
        try:
            with pytest.raises(ProviderUnavailableError):
                first_attempt.result(timeout=0.5)
            assert spawned_envs == []
        finally:
            release_writer.set()
        writer.result(timeout=5)

    response = invoke_cli()
    assert response.text == "complete assignment reply"
    assert len(spawned_envs) == 1
    assert spawned_envs[0].get("ANTHROPIC_API_KEY") == "fake-new-assignment-key"
    assert "fake-prior-assignment-key" not in spawned_envs[0].values()


def _stage_ready_then_pending_assignment(universe: Path) -> None:
    """Model a request admitted under ready state before reassignment starts."""
    write_universe_config_fields(
        universe,
        preferred_writer="claude-code",
        allowed_providers=["claude-code"],
        engine_assignment_state="ready",
    )
    write_credential_vault(
        universe,
        [
            {
                "credential_type": "llm_api_key",
                "service": "anthropic",
                "api_key": "fake-prior-assignment-key",
            }
        ],
    )
    stale_admitted_config = load_universe_config(universe)
    assert stale_admitted_config.allowed_providers == ["claude-code"]

    write_universe_config_fields(
        universe,
        allowed_providers=[],
        engine_assignment_state="pending",
    )
    write_credential_vault(
        universe,
        [
            {
                "credential_type": "llm_api_key",
                "service": "anthropic",
                "api_key": "fake-new-assignment-key",
            }
        ],
    )


def test_cli_auth_materialization_revalidates_after_router_admission(
    host_auth, tmp_path,
):
    """A stale router admission cannot read a vault mutated under pending."""
    universe = tmp_path / "u-materialization-race"
    universe.mkdir()
    _stage_ready_then_pending_assignment(universe)

    returned_environment = None
    caught = None
    try:
        returned_environment = subprocess_env_for_provider(
            "claude-code", universe_dir=universe
        )
    except ProviderUnavailableError as exc:
        caught = exc

    assert returned_environment is None, (
        "CLI auth materialization returned an environment from a vault changed "
        "after router admission while the assignment was pending"
    )
    assert caught is not None, "pending assignment must fail closed before auth returns"


@pytest.mark.asyncio
async def test_cli_provider_never_spawns_from_pending_reassignment_auth(
    host_auth, tmp_path, monkeypatch,
):
    """The second locked check must run before CLI subprocess creation."""
    from tinyassets.providers import claude_provider

    universe = tmp_path / "u-no-spawn-race"
    universe.mkdir()
    _stage_ready_then_pending_assignment(universe)
    spawn_observations: list[bool] = []

    class SuccessfulProcess:
        returncode = 0

        async def communicate(self, input=None):
            return b"unexpected provider reply", b""

    async def fake_spawn(*args, **kwargs):
        child_env = kwargs.get("env") or {}
        spawn_observations.append(
            child_env.get("ANTHROPIC_API_KEY") == "fake-new-assignment-key"
        )
        return SuccessfulProcess()

    monkeypatch.setattr(
        claude_provider, "_resolve_claude_cmd", lambda: (["claude"], False)
    )
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_spawn)

    caught = None
    try:
        await claude_provider.ClaudeProvider().complete(
            "prompt",
            "system",
            ModelConfig(timeout=1),
            universe_dir=universe,
        )
    except ProviderUnavailableError as exc:
        caught = exc

    assert spawn_observations == [], (
        "a CLI subprocess launched after admission using auth materialized from "
        "a pending reassignment"
    )
    assert caught is not None, "pending reassignment must stop the CLI before spawn"
