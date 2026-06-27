"""Discovery sources for the domain registry (Task #22).

Post-§3.2 `tinyassets.discovery.discover_domains()` unions two sources:

1. `importlib.metadata.entry_points(group="tinyassets.domains")` — for
   pip-installed domains (the canonical third-party install path).
2. Filesystem scan of ``domains/<name>/skill.py`` next to the
   ``tinyassets/`` package — editable-dev-install fallback.

This module covers the new behaviors. Pre-existing integration tests
in ``test_tinyassets_runtime.py`` continue to assert the filesystem-only
shape so the real-install smoke stays green; those aren't retested here.
"""

from __future__ import annotations

import importlib.metadata
from types import SimpleNamespace

import pytest

import tinyassets.discovery as discovery_mod

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_entry_points(entries: dict[str, str]):
    """Return a fake `entry_points(group=...)` result list.

    Each item exposes `.name` and `.value` — the two attributes the
    production code reads. Keeps us decoupled from the internal
    EntryPoint dataclass shape.
    """
    return [SimpleNamespace(name=k, value=v) for k, v in entries.items()]


@pytest.fixture
def patch_entry_points(monkeypatch):
    """Monkeypatch `importlib.metadata.entry_points` to return controlled data.

    Takes a dict passed at fixture-use time; yields the setter.
    """
    def _set(entries: dict[str, str]) -> None:
        def _fake(*args, **kwargs):
            group = kwargs.get("group") or (args[0] if args else None)
            if group == discovery_mod.ENTRY_POINT_GROUP:
                return _fake_entry_points(entries)
            # Delegate to real implementation for any other group so we
            # don't break unrelated metadata lookups.
            return importlib.metadata.entry_points.__wrapped__(*args, **kwargs) \
                if hasattr(importlib.metadata.entry_points, "__wrapped__") \
                else []
        monkeypatch.setattr(
            discovery_mod.importlib.metadata, "entry_points", _fake,
        )
    return _set


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


class TestDiscoverEntryPointDomains:

    def test_returns_empty_when_no_entry_points(self, patch_entry_points):
        patch_entry_points({})
        assert discovery_mod._discover_entry_point_domains() == {}

    def test_returns_mapping_of_name_to_target(self, patch_entry_points):
        patch_entry_points({
            "foo": "pkg.foo.skill:FooDomain",
            "bar": "pkg.bar.skill:BarDomain",
        })
        result = discovery_mod._discover_entry_point_domains()
        assert result == {
            "foo": "pkg.foo.skill:FooDomain",
            "bar": "pkg.bar.skill:BarDomain",
        }

    def test_handles_metadata_lookup_failure(self, monkeypatch):
        """If entry_points() blows up, we return {} — never raise."""
        def _boom(*_a, **_kw):
            raise RuntimeError("metadata catalog broken")
        monkeypatch.setattr(
            discovery_mod.importlib.metadata, "entry_points", _boom,
        )
        assert discovery_mod._discover_entry_point_domains() == {}

    def test_skips_entries_without_name_or_value(self, patch_entry_points):
        patch_entry_points({
            "": "pkg.empty:Empty",          # empty name — skipped
            "named": "",                    # empty value — skipped
            "keep": "pkg.keep:KeepDomain",
        })
        result = discovery_mod._discover_entry_point_domains()
        assert result == {"keep": "pkg.keep:KeepDomain"}


class TestDiscoverFilesystemDomains:

    def test_finds_repo_domains(self):
        """Real ``domains/`` tree exposes fantasy_daemon + research_probe."""
        names = discovery_mod._discover_filesystem_domains()
        assert "fantasy_daemon" in names
        assert "research_probe" in names


# ---------------------------------------------------------------------------
# Top-level discover_domains — union + dedup
# ---------------------------------------------------------------------------


class TestDiscoverDomainsUnion:

    def test_entry_point_only(self, patch_entry_points, monkeypatch):
        """Entry points present, filesystem scan returns nothing."""
        patch_entry_points({"third_party": "pkg.tp.skill:TPDomain"})
        monkeypatch.setattr(
            discovery_mod, "_discover_filesystem_domains", lambda: [],
        )
        result = discovery_mod.discover_domains()
        assert result == ["third_party"]

    def test_filesystem_only(self, patch_entry_points, monkeypatch):
        """Entry points empty, filesystem scan returns real domains."""
        patch_entry_points({})
        monkeypatch.setattr(
            discovery_mod, "_discover_filesystem_domains",
            lambda: ["dev_domain_a", "dev_domain_b"],
        )
        result = discovery_mod.discover_domains()
        assert result == ["dev_domain_a", "dev_domain_b"]

    def test_dedup_when_same_name_in_both(
        self, patch_entry_points, monkeypatch,
    ):
        """Domain reachable via entry-point AND filesystem → single entry."""
        patch_entry_points({"fantasy_daemon": "pkg.fd:FD"})
        monkeypatch.setattr(
            discovery_mod, "_discover_filesystem_domains",
            lambda: ["fantasy_daemon", "research_probe"],
        )
        result = discovery_mod.discover_domains()
        # Name appears once, order deterministic.
        assert result.count("fantasy_daemon") == 1
        assert result == sorted(["fantasy_daemon", "research_probe"])

    def test_results_sorted(self, patch_entry_points, monkeypatch):
        patch_entry_points({"zulu": "x:X", "alpha": "y:Y"})
        monkeypatch.setattr(
            discovery_mod, "_discover_filesystem_domains",
            lambda: ["mike", "bravo"],
        )
        result = discovery_mod.discover_domains()
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# auto_register via entry-point target
# ---------------------------------------------------------------------------


class _FakeRegistry:
    def __init__(self) -> None:
        self.registered: list = []

    def register(self, domain) -> None:
        self.registered.append(domain)


def test_auto_register_uses_entry_point_target(patch_entry_points, monkeypatch):
    """When a domain is declared via entry point, auto_register imports
    exactly the ``module:attr`` target and instantiates it.
    """
    instantiated = []

    class FakeDomain:
        def __init__(self) -> None:
            instantiated.append("ok")

    fake_module = SimpleNamespace(Probe=FakeDomain)

    def _fake_import(path: str):
        assert path == "pkg.probe.skill"
        return fake_module

    patch_entry_points({"probe": "pkg.probe.skill:Probe"})
    monkeypatch.setattr(
        discovery_mod, "_discover_filesystem_domains", lambda: [],
    )
    monkeypatch.setattr(
        discovery_mod.importlib, "import_module", _fake_import,
    )

    registry = _FakeRegistry()
    discovery_mod.auto_register(registry)
    assert instantiated == ["ok"]
    assert len(registry.registered) == 1


def test_auto_register_skips_bad_entry_point_target(
    patch_entry_points, monkeypatch,
):
    """Malformed ``module:attr`` entry point logs warning + skips; no
    other domains crash.
    """
    patch_entry_points({"broken": "no-colon-here"})
    monkeypatch.setattr(
        discovery_mod, "_discover_filesystem_domains", lambda: [],
    )

    registry = _FakeRegistry()
    # Must not raise.
    discovery_mod.auto_register(registry)
    assert registry.registered == []


def test_auto_register_filesystem_fallback_still_works(patch_entry_points):
    """When entry-point table is empty, the filesystem path still
    imports + registers ``research_probe`` the old way.
    """
    patch_entry_points({})
    # Don't mock the filesystem discovery — let it run against the
    # real ``domains/`` tree so we verify the real import chain.

    registry = _FakeRegistry()
    discovery_mod.auto_register(registry)

    registered_names = [
        d.config["name"] for d in registry.registered
        if hasattr(d, "config")
    ]
    assert "research_probe" in registered_names


def test_entry_point_group_constant_exposed():
    """``ENTRY_POINT_GROUP`` is part of the public API so third-party
    domain packages know which group string to declare.
    """
    assert discovery_mod.ENTRY_POINT_GROUP == "tinyassets.domains"
    assert "ENTRY_POINT_GROUP" in discovery_mod.__all__
