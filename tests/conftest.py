"""Shared fixtures for TinyAssets tests.

Provides checkpointer, compiled graphs, and default state dicts
that all test modules can reuse.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

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


class _CredentialSubjectProvider(AuthProvider):
    """Resolve only issued test credentials to persisted subjects."""

    def __init__(self) -> None:
        self._identities_by_token: dict[str, Identity] = {}

    def issue_credential(self, subject: str) -> str:
        token = f"pytest-credential::{subject}"
        self._identities_by_token[token] = Identity(
            user_id=subject,
            username=f"{subject}-display",
            capabilities=[
                "tinyassets.extensions.read",
                "tinyassets.extensions.write",
                "tinyassets.extensions.admin",
            ],
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

    def authenticate(subject: str | None) -> None:
        token = provider.issue_credential(subject) if subject else None
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


# ---------------------------------------------------------------------------
# Process-global patch leak detector — see tests/_global_leak_guard.py
# ---------------------------------------------------------------------------

from tests import _global_leak_guard as _leak_guard  # noqa: E402

_LEAK_STASH = pytest.StashKey[dict]()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{_leak_guard.MARKER}(*targets): this test's fixture legitimately owns "
        "a process-global (e.g. 'subprocess.run') for its whole scope; do not "
        "flag or repair it.",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Baseline before the test's own fixtures run.

    Stored on `item.stash`, not a module global: a process-wide slot would be
    clobbered by a nested runtest protocol or an in-process threaded runner.
    """
    item.stash[_LEAK_STASH] = _leak_guard.snapshot()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    """Compare after every finalizer has run.

    `tryfirst`, NOT `trylast`. Hook wrappers unwind in reverse, so the wrapper
    that runs FIRST before the yield resumes LAST after it — which is where
    this check has to be, or it can flag a plugin before that plugin restores
    its own patch. Getting this backwards was a real defect (cross-family
    review 2026-08-03), as was an earlier autouse-fixture version that ran
    before `monkeypatch`'s undo and produced 34 false positives.
    """
    outcome = yield

    baseline = item.stash.get(_LEAK_STASH, None)
    if not baseline:
        return
    exempt = set()
    for marker in item.iter_markers(name=_leak_guard.MARKER):
        exempt |= _leak_guard.exempt_targets(marker.args)

    changed = _leak_guard.diff(baseline, exempt)
    if not changed:
        return
    message = _leak_guard.describe(item.nodeid, changed)
    _leak_guard.repair(changed)

    # NEVER mask an exception teardown already raised. Replacing it would hide
    # the more informative failure behind this diagnostic; the leak is reported
    # as an extra section instead.
    if outcome.excinfo is not None:
        item.add_report_section("teardown", "global-patch-leak", message)
        return
    raise AssertionError(message)
