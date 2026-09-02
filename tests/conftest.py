"""Shared fixtures for TinyAssets tests.

Provides checkpointer, compiled graphs, and default state dicts
that all test modules can reuse.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from collections.abc import Sequence
from typing import Any, Callable

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def pytest_configure(config: pytest.Config) -> None:
    """Refuse to run if pytest's temp root is inside the repo.

    A sandboxed agent (Codex, Cursor) that redirects ``--basetemp``/``TMPDIR``
    into the checkout creates those directories under a RESTRICTED TOKEN. On
    Windows the resulting ACL is owned by e.g. ``CodexSandboxUsers`` and denies
    the interactive user everything -- not just delete, but even reading the
    ACL. They then survive ``git worktree remove`` and need an elevated
    ``takeown`` to clear. Seventeen such husks were left behind on 2026-08-25
    and could not be removed from an ordinary shell.

    Failing here costs one clear error; the alternative costs an elevated
    cleanup and a directory nobody can delete. See ``AGENTS.md`` § *Testing*
    and ``scripts/clear_sandbox_temp_dirs.ps1``.

    On Windows, ALSO pass a SHORT ``--basetemp`` (e.g.
    ``C:/Users/<you>/AppData/Local/Temp/ta-pt``): pytest's default root plus a
    workspace lease plus ``.git/objects/pack/pack-<40 hex>.pack`` crosses
    MAX_PATH, and the failure reads as a real defect (a lease that will not
    delete) rather than as a path-length limit. Tests that build a real git
    checkout skip themselves when the root is too long to be safe.
    """
    roots: list[tuple[str, str]] = []
    basetemp = config.getoption("basetemp", default=None)
    if basetemp:
        roots.append(("--basetemp", str(basetemp)))
    for var in ("PYTEST_DEBUG_TEMPROOT", "TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(var)
        if value:
            roots.append((var, value))

    for label, raw in roots:
        try:
            resolved = pathlib.Path(raw).resolve()
        except (OSError, ValueError):
            continue
        if resolved == _REPO_ROOT or _REPO_ROOT in resolved.parents:
            raise pytest.UsageError(
                f"{label}={raw!r} points INSIDE the repo ({_REPO_ROOT}). "
                "Sandbox-created temp dirs here get an ACL the interactive user "
                "cannot delete and that survives worktree teardown. Point it at "
                "the system temp dir instead."
            )


# Force mock provider responses in all tests to avoid real API calls
from tinyassets.providers import call as _provider_call

_provider_call.set_force_mock(True)


@pytest.fixture(autouse=True)
def _request_admission_hmac_key(monkeypatch):
    """Install non-production server seal material for authority tests."""

    monkeypatch.setenv(
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY",
        "pytest-only-request-admission-hmac-key-0123456789abcdef",
    )


# The capability set an issued test credential carries unless a test asks for
# something else. Deliberately EXCLUDES `tinyassets.extensions.costly`, which
# gates run_branch and friends: several suites authenticate a subject and then
# assert a costly action is refused, so granting it by default would silently
# convert those into vacuous passes.
_DEFAULT_TEST_CAPABILITIES = (
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.admin",
)


class _CredentialSubjectProvider(AuthProvider):
    """Resolve only issued test credentials to persisted subjects."""

    def __init__(self) -> None:
        self._identities_by_token: dict[str, Identity] = {}

    def issue_credential(
        self, subject: str, capabilities: Sequence[str] | None = None
    ) -> str:
        token = f"pytest-credential::{subject}"
        self._identities_by_token[token] = Identity(
            user_id=subject,
            username=f"{subject}-display",
            # `is None`, NOT `or`: an explicit empty list is falsy, so `or`
            # would silently hand a test that asked for NO capabilities the
            # full default set — turning an authorization-refusal test into a
            # vacuous pass, which is the exact hazard this parameter exists to
            # avoid. Pinned by test_credential_capabilities.py.
            capabilities=list(
                _DEFAULT_TEST_CAPABILITIES if capabilities is None else capabilities
            ),
        )
        return token

    def resolve_token(self, token: str) -> Identity | None:
        return self._identities_by_token.get(token)

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "pytest-credential-subject", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "pytest-credential-subject-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture
def authenticate_request() -> Callable[[str | None], None]:
    """Bind branch-authority tests to a credential-derived request subject."""
    provider = _CredentialSubjectProvider()
    set_provider(provider)
    auth_middleware(None)

    def authenticate(
        subject: str | None, capabilities: Sequence[str] | None = None
    ) -> None:
        """Bind the request subject. `capabilities` defaults to read/write/admin.

        Pass an explicit list to grant `tinyassets.extensions.costly`, which
        `run_branch` requires. It is opt-in rather than default so that suites
        asserting a costly action is refused keep asserting something.
        """
        token = provider.issue_credential(subject, capabilities) if subject else None
        auth_middleware(token)

    yield authenticate
    auth_middleware(None)
    set_provider(DevAuthProvider())


@pytest.fixture(autouse=True)
def _emulate_deployed_visibility_backfill(request, monkeypatch):
    """Emulate the deployed ``backfill_universe_visibility`` for legacy modules.

    The universe-visibility contract fails closed on an *undeclared* universe
    (openspec/changes/universe-visibility). In production the one-time
    ``backfill_universe_visibility`` migration declares every pre-existing
    universe from its ``public_read`` bit, after which undeclared only ever means
    forged/corrupt. The hundreds of pre-visibility tests create bare universes
    and were written against that post-backfill world (undeclared == public).

    This fixture reproduces the deployed backfill state in the harness so those
    tests keep asserting their own concern (status shape, word count, telemetry)
    without each re-declaring visibility: for an *undeclared* universe it derives
    the level from ``public_read`` exactly as the backfill does, while an explicit
    (or forged) declaration, a corrupt store, and a blank id all defer to the real
    strict resolver. Production code ships fully strict; the true pre-backfill
    fail-closed behavior is exercised un-emulated by ``test_universe_visibility``.
    """
    module_name = getattr(request.node.module, "__name__", "")
    if module_name.endswith("test_universe_visibility"):
        return  # this module tests the real, un-backfilled strict resolver.

    from tinyassets.api import visibility as _vis

    _real = _vis.universe_visibility

    def _post_backfill(universe_id: str):
        if not (universe_id or "").strip():
            return _vis.CLOSED
        rules = _vis._read_rules(universe_id)
        if rules is _vis._CORRUPT:
            return _vis.CLOSED
        if rules is _vis._MISSING:
            # A bare universe: backfill would create a rules row (public_read
            # defaults True) and declare it public.
            return _vis.PUBLIC
        if not isinstance(rules, dict):
            return _vis.CLOSED
        meta = rules.get("metadata")
        if isinstance(meta, dict) and _vis.LEVEL_METADATA_KEY in meta:
            return _real(universe_id)  # explicit/forged -> real strict resolver.
        return _vis.PUBLIC if bool(rules.get("public_read", True)) else _vis.PRIVATE

    monkeypatch.setattr(_vis, "universe_visibility", _post_backfill)


@pytest.fixture(autouse=True)
def _identity_fingerprint_key(monkeypatch):
    """Give tests an explicit dedicated status-fingerprint key."""
    monkeypatch.setenv(
        "TINYASSETS_IDENTITY_FINGERPRINT_KEY",
        "pytest-only-identity-fingerprint-key-32-bytes",
    )
    monkeypatch.setenv("TINYASSETS_IDENTITY_FINGERPRINT_VERSION", "v1")


@pytest.fixture(autouse=True)
def _reset_runtime():
    """Clear runtime singletons before AND after every test to prevent leakage.

    The pre-test reset catches cases where a prior test's background thread
    (e.g. LangGraph executor) sets the global after the prior test's teardown.
    """
    from tinyassets import runtime_singletons as runtime

    runtime.reset()
    yield
    runtime.reset()


@pytest.fixture(autouse=True)
def _reset_git_enabled_probe():
    """Re-probe ``git_bridge.is_enabled`` for every test.

    The probe result is cached in a MODULE GLOBAL, so it leaks across the whole
    process: any earlier test that stubs ``shutil.which`` to None (e.g.
    test_api_status.py pinning endpoint_hint) latches ``False``, and every
    later git-touching test then silently no-ops with "git not enabled".
    A few files carried their own local version of this fixture; the cache is
    process-global, so its reset has to be too.

    Found 2026-08-03 by the `required-tests` gate itself: new tests arriving on
    main shifted collection order and turned 138 passing tests red at once,
    with no code change to any of them.
    """
    from tinyassets import git_bridge

    git_bridge.invalidate_cache()
    yield
    git_bridge.invalidate_cache()


@pytest.fixture(autouse=True)
def _reset_provider_request_state():
    """Clear the process-global provider-request capability state per test.

    ``_PROVIDER_REQUESTS`` (a module dict) plus the ``_current_provider_request``
    / ``_current_provider_reserve`` ContextVars hold the one-shot authenticated
    dispatch capability. ContextVars are NOT reset between pytest tests, so a
    test that ``reserve``/``claim``s a capability and doesn't tear it down leaks
    a stale ``ProviderRequestCapability`` into the next test: e.g. converse then
    reads it via ``provider_request_capability()`` and resolves the serving
    binding under the wrong principal (0 matches -> "exactly one founder serving
    binding is required"). Same collection-order leak class as
    ``_reset_git_enabled_probe`` above; the reset has to be process-global too.
    Reuses the canonical fork-time reset so there is one definition of "clean".
    """
    from tinyassets.auth.middleware import _reset_provider_request_state_after_fork

    _reset_provider_request_state_after_fork()
    yield
    _reset_provider_request_state_after_fork()


@pytest.fixture(autouse=True)
def _isolate_storage_backend(monkeypatch):
    """Pin the storage backend to ``sqlite_only`` by default for every test.

    Phase 7 Rationale: the module-global :class:`SqliteCachedBackend`
    anchors to ``Path.cwd()`` on first use and, once cached, keeps
    writing to the real repo ``branches/`` / ``goals/`` / ``nodes/``
    directories even when later tests point ``TINYASSETS_DATA_DIR``
    at a tmp dir. That causes (a) pollution of the working tree and
    (b) spurious ``DirtyFileError`` as tests fight over the same
    slug paths.

    Tests that explicitly exercise the cached backend (git-enabled
    path, YAML serialization, commit granularity) override this by
    re-setting the env var via their own ``monkeypatch``. See
    ``tests/test_storage_phase7_backend.py`` and future ``test_phase7_h3_*``.
    """
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite_only")
    from tinyassets import catalog as _catalog

    _catalog.invalidate_backend_cache()
    yield
    _catalog.invalidate_backend_cache()


@pytest.fixture(autouse=True)
def _code_nodes_use_the_plain_launcher(monkeypatch):
    """Change `sandboxed-code-node`: a source_code node runs in an OS sandbox
    (bwrap on Linux). The suite also runs on hosts without one, so every test
    injects the TESTS-ONLY plain subprocess launcher by dependency injection -
    production code has no switch to do this (Codex round 1, P0). Tests that
    exercise the real bwrap launcher construct it explicitly and skip when the
    host has no bwrap."""
    from tinyassets import node_sandbox

    monkeypatch.setattr(
        node_sandbox, "DEFAULT_LAUNCHER_FACTORY",
        lambda: node_sandbox.PlainSubprocessLauncher(),
    )


@pytest.fixture
def checkpointer():
    """Yield an in-memory SqliteSaver for testing.

    Uses the ``from_conn_string`` context manager pattern.
    """
    with SqliteSaver.from_conn_string(":memory:") as cp:
        yield cp


@pytest.fixture
def tmp_story_db():
    """Create a temp story.db path for world state, cleaned up after test."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="story_test_")
    os.close(fd)
    os.unlink(path)  # Remove so init_db creates fresh
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def scene_input(tmp_story_db) -> dict[str, Any]:
    """Minimal valid input for the Scene graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapter_number": 1,
        "scene_number": 1,
        "orient_result": {},
        "retrieved_context": {},
        "recent_prose": "",
        "workflow_instructions": {},
        "memory_context": {},
        "search_context": {},
        "plan_output": None,
        "draft_output": None,
        "commit_result": None,
        "editorial_notes": None,
        "second_draft_used": False,
        "verdict": "",
        "extracted_facts": [],
        "extracted_promises": [],
        "style_observations": [],
        "quality_trace": [],
        "quality_debt": [],
        "_universe_path": "",
        "_db_path": tmp_story_db,
        "_kg_path": "",
    }


@pytest.fixture
def chapter_input() -> dict[str, Any]:
    """Minimal valid input for the Chapter graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapter_number": 1,
        "scenes_completed": 0,
        "scenes_target": 2,
        "chapter_summary": None,
        "consolidated_facts": [],
        "quality_trend": {},
        "chapter_arc": {},
        "style_rules_observed": [],
        "craft_cards_generated": [],
    }


@pytest.fixture
def book_input() -> dict[str, Any]:
    """Minimal valid input for the Book graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapters_completed": 0,
        "chapters_target": 1,
        "book_summary": None,
        "book_arc": {},
        "health": {"stuck_level": 0},
        "cross_book_promises_active": [],
        "quality_trace": [],
    }


@pytest.fixture
def universe_input() -> dict[str, Any]:
    """Minimal valid input for the Universe graph."""
    return {
        "universe_id": "test-universe",
        "universe_path": "/tmp/test-universe",
        "review_stage": "foundation",
        "active_series": None,
        "series_completed": [],
        "selected_target_id": None,
        "selected_intent": None,
        "alternate_target_ids": [],
        "current_task": None,
        "current_execution_id": None,
        "current_execution_ref": None,
        "last_review_artifact_ref": None,
        "work_targets_ref": "work_targets.json",
        "hard_priorities_ref": "hard_priorities.json",
        "timeline_ref": None,
        "soft_conflicts": [],
        "world_state_version": 0,
        "canon_facts_count": 0,
        "total_words": 0,
        "total_chapters": 0,
        "health": {},
        "task_queue": ["write"],
        "universal_style_rules": [],
        "cross_series_facts": [],
        "quality_trace": [],
    }


# There is no anonymous principal (founder, 2026-09-02). The dev auth provider
# names its local operator through UNIVERSE_SERVER_DEV_USER and refuses to
# start without it; the suite runs as this named operator unless a test sets
# its own. A test that wants NO identity calls auth_middleware(None) and
# asserts the refusal, never a stand-in.
import os as _os

_os.environ.setdefault("UNIVERSE_SERVER_DEV_USER", "dev-tests")
