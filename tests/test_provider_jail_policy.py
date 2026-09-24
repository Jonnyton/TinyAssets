"""The provider jail's policy: when it applies, what it refuses, what it binds.

Platform-neutral where it can be: every refusal here happens BEFORE a process
exists, so it is asserted on any host, and the spawn functions are replaced by
tripwires that fail the test if anything is launched. The real-jail proof of
what a jailed provider can read is ``tests/test_provider_universe_jail.py``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from tinyassets.providers import owned_process, provider_jail
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)
from tinyassets.providers.provider_jail import (
    JailMount,
    ProviderConfinementError,
    UniverseView,
    confine_launch,
    default_view,
    jail_argv,
    provider_launch_scope,
)

posix_paths = pytest.mark.skipif(
    os.name != "posix", reason="bwrap argv carries POSIX paths",
)


@pytest.fixture
def no_spawn(monkeypatch: pytest.MonkeyPatch) -> list:
    """Fail loudly if anything reaches a real process spawn."""
    launched: list = []

    async def _tripwire(*args, **kwargs):
        launched.append(args)
        raise AssertionError("a refused launch reached the process spawn")

    monkeypatch.setattr(owned_process, "_aspawn_anchored", _tripwire)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _tripwire)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", _tripwire)
    return launched


def _universe(root: Path, name: str = "u-alpha") -> Path:
    universe = root / "data" / name
    (universe / ".runtime" / "provider-launch-credentials" / "own-1").mkdir(parents=True)
    (universe / ".runtime" / "provider-launch-credentials" / "other-2").mkdir(parents=True)
    return universe


def test_a_launch_outside_any_provider_scope_is_unchanged():
    assert confine_launch(["tool", "--flag"]) is None


def test_a_provider_launch_with_no_owning_universe_is_refused_before_spawn(no_spawn):
    """A host-authority provider call (no universe) never runs a CLI on the host."""

    async def drive():
        with provider_launch_scope(None):
            await owned_process.aspawn_owned([sys.executable, "-c", "pass"])

    with pytest.raises(ProviderConfinementError, match="no owning universe"):
        asyncio.run(drive())
    assert no_spawn == []


def test_no_os_sandbox_refuses_rather_than_running_unconfined(
    tmp_path, monkeypatch, no_spawn,
):
    from tinyassets.providers import base

    monkeypatch.setattr(
        base, "get_sandbox_status",
        lambda: {"bwrap_available": False, "reason": "bwrap not found on PATH"},
    )
    universe = _universe(tmp_path)

    async def drive():
        with provider_launch_scope(universe):
            await owned_process.aspawn_owned([sys.executable, "-c", "pass"])

    with pytest.raises(ProviderConfinementError, match="no OS sandbox"):
        asyncio.run(drive())
    assert no_spawn == []


def test_a_refusal_is_authority_held_so_no_fallback_text_replaces_it():
    """Callers already never fold ProviderAuthorityHeldError into fallback text."""
    from tinyassets.exceptions import ProviderAuthorityHeldError, ProviderUnavailableError

    assert issubclass(ProviderConfinementError, ProviderAuthorityHeldError)
    # Not "unavailable": that would cool the provider for every owner.
    assert not issubclass(ProviderConfinementError, ProviderUnavailableError)


def test_a_view_cannot_bind_anything_outside_its_universe(tmp_path):
    universe = _universe(tmp_path)
    other = _universe(tmp_path, "u-bravo")
    view = UniverseView(
        universe_dir=universe,
        mounts=(JailMount("ro-bind", "/workspace", other),),
    )
    with pytest.raises(ProviderConfinementError, match="inside its own universe"):
        jail_argv(["cli"], view, bwrap_path="bwrap")


@pytest.mark.parametrize("dest", ["/", "/usr/bin", "/etc", "/proc/self", "relative"])
def test_a_view_cannot_mount_over_system_roots(tmp_path, dest):
    universe = _universe(tmp_path)
    view = UniverseView(universe_dir=universe, mounts=(JailMount("tmpfs", dest),))
    with pytest.raises(ProviderConfinementError, match="may not mount"):
        jail_argv(["cli"], view, bwrap_path="bwrap")


def test_a_view_for_another_universe_than_the_call_is_refused(tmp_path, no_spawn):
    universe = _universe(tmp_path)
    other = _universe(tmp_path, "u-bravo")
    view = UniverseView(universe_dir=other, mounts=())
    with provider_launch_scope(universe):
        with pytest.raises(ProviderConfinementError, match="different universe"):
            confine_launch(["cli"], view=view)


@posix_paths
def test_default_view_binds_the_universe_masks_launches_and_rebinds_its_own(tmp_path):
    universe = _universe(tmp_path).resolve()
    own = universe / ".runtime" / "provider-launch-credentials" / "own-1"
    view = default_view(universe, credential_dir=own, cwd=str(universe / "sub"))
    argv = jail_argv(["cli", "-p"], view, bwrap_path="/usr/bin/bwrap")

    for flag in ("--die-with-parent", "--new-session", "--unshare-all", "--share-net"):
        assert flag in argv, flag
    assert argv[argv.index("--proc") + 1] == "/proc"
    bind_u = argv.index(str(universe))
    mask = argv.index(str(universe / ".runtime" / "provider-launch-credentials"))
    rebind = max(i for i, a in enumerate(argv) if a == str(own))
    assert argv[bind_u - 1] == "--bind" and argv[mask - 1] == "--tmpfs"
    assert bind_u < mask < rebind, "the mask must sit over the bind and under its own snapshot"
    assert argv[rebind - 2] == "--bind"
    # The data root holding every universe is never bound, nor anything above it.
    for i, arg in enumerate(argv[:-3]):
        if arg in ("--bind", "--ro-bind"):
            assert not Path(universe.parent).is_relative_to(Path(argv[i + 1])), argv[i + 1]
    # A cwd inside the universe is honoured; one outside falls back to the universe.
    assert argv[argv.index("--chdir") + 1] == str(universe / "sub")
    outside = default_view(universe, cwd=str(universe.parent))
    assert outside.chdir == str(universe)
    assert argv[argv.index("--") + 1:] == ["cli", "-p"]


@posix_paths
def test_an_install_path_reaching_universe_data_is_refused(tmp_path):
    universe = _universe(tmp_path).resolve()
    view = default_view(universe)
    with pytest.raises(ProviderConfinementError, match="overlaps universe data"):
        jail_argv(["cli"], view, bwrap_path="/usr/bin/bwrap", install_paths=[universe.parent])


@posix_paths
def test_an_install_path_reaching_platform_source_is_refused(tmp_path):
    import tinyassets

    universe = _universe(tmp_path).resolve()
    source = Path(tinyassets.__file__).resolve().parent
    with pytest.raises(ProviderConfinementError, match="platform source"):
        jail_argv(
            ["cli"], default_view(universe), bwrap_path="/usr/bin/bwrap",
            install_paths=[source],
        )


# --- the router binds the owning universe ----------------------------------


class _ScopeRecorder(BaseProvider):
    family = "test"

    def __init__(self, name: str) -> None:
        self.name = name
        self.scopes: list = []

    async def complete(self, prompt, system, config, *, universe_dir=None):
        self.scopes.append(provider_jail._SCOPE.get())
        return ProviderResponse(
            text="ok", provider=self.name, model="m", family=self.family, latency_ms=1.0,
        )


class _SpawningProvider(BaseProvider):
    """A command adapter: spawns through the shared helper and nothing else."""

    family = "test"

    def __init__(self, name: str) -> None:
        self.name = name

    async def complete(self, prompt, system, config, *, universe_dir=None):
        await owned_process.aspawn_owned([sys.executable, "-c", "pass"])
        raise AssertionError("unreachable: the launch should have been refused")


def test_router_binds_the_owning_universe_around_the_provider_call(tmp_path):
    from tinyassets.config import UniverseConfig
    from tinyassets.providers.router import ProviderRouter

    universe = _universe(tmp_path)
    recorder = _ScopeRecorder("codex")
    router = ProviderRouter(providers={"codex": recorder})
    context = UniverseContext(
        universe_dir=universe, config=UniverseConfig(allowed_providers=["codex"]),
    )
    asyncio.run(router.call_judge_ensemble("p", "", universe_context=context))

    assert len(recorder.scopes) == 1
    assert recorder.scopes[0].universe_dir == universe
    assert provider_jail._SCOPE.get() is None, "the binding leaked past the call"


def test_router_binds_no_universe_for_a_host_call():
    from tinyassets.providers.router import ProviderRouter

    recorder = _ScopeRecorder("claude-code")
    router = ProviderRouter(providers={"claude-code": recorder})
    asyncio.run(router.call("writer", "p", "", ModelConfig()))

    assert len(recorder.scopes) == 1
    assert recorder.scopes[0] is not None and recorder.scopes[0].universe_dir is None


def test_router_refuses_a_host_authority_launch_without_cooling_the_provider(no_spawn):
    """The selector/leaderboard shape: a router call with no universe context."""
    from tinyassets.providers.router import ProviderRouter

    router = ProviderRouter(providers={"claude-code": _SpawningProvider("claude-code")})
    with pytest.raises(ProviderConfinementError):
        asyncio.run(router.call("writer", "p", "", ModelConfig()))
    assert no_spawn == []
    assert router._quota.available("claude-code"), "a host refusal cooled the provider"


def test_powershell_is_on_the_one_host_reach_floor():
    from tinyassets.providers.base import HOST_REACH_TOOLS
    from tinyassets.universe_intelligence import _ENGINE_DISALLOWED_TOOLS

    assert "PowerShell" in HOST_REACH_TOOLS
    assert "PowerShell" in _ENGINE_DISALLOWED_TOOLS
