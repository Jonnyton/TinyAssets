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
# Process-global patch leak detector
# ---------------------------------------------------------------------------
#
# Watched callables are process-global. A test that patches one and fails to
# restore it corrupts every later test in the same interpreter, and the damage
# surfaces in the VICTIMS, never in the culprit — which reads as flaky ordering.
#
# Two measured incidents in this repo:
#
#   * a threaded `patch("...github_pr.subprocess.run")` leaked, and ~70
#     unrelated tests then received its canned stdout
#     `https://github.com/x/x/pull/99` from what they believed were real
#     subprocess calls. 111 quarantine entries flipped between two CI runs whose
#     trees differed by two test functions (#2197, #2199).
#   * a `shutil.which` stub latched `git_bridge.is_enabled` to False and
#     silently no-opped 138 tests (see `_reset_git_enabled_probe` above).
#
# This checks the CONDITION rather than the spelling. An earlier attempt used an
# AST lint to spot the unsafe pattern; five review rounds each found a fresh
# false positive in it (method targets, shadowed imports, `functools.partial`
# lookalikes, a parameter named `patch`), because deciding what a name refers to
# is real scope analysis. Checking what actually leaked is both simpler and
# strictly stronger: it catches any spelling, and correct code cannot trip it,
# because correct code restores what it patches.
_LEAK_WATCHED = (
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("shutil", "which"),
)

_leak_baseline: dict[tuple[str, str], object] = {}


def _snapshot_globals() -> dict[tuple[str, str], object]:
    import importlib

    snap: dict[tuple[str, str], object] = {}
    for module_name, attr in _LEAK_WATCHED:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - stdlib, but stay fail-soft
            continue
        snap[(module_name, attr)] = getattr(module, attr, None)
    return snap


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Baseline BEFORE the test's own fixtures run."""
    _leak_baseline.clear()
    _leak_baseline.update(_snapshot_globals())


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """Compare AFTER every finalizer, including `monkeypatch`'s undo.

    This is a teardown hookwrapper rather than an autouse fixture for a
    measured reason: as a fixture it ran BEFORE `monkeypatch` restored its
    patches, so it reported patches pytest was about to put back — a false
    positive on completely correct tests. The code after `yield` here runs once
    all finalizers are done.
    """
    import importlib

    yield

    if not _leak_baseline:
        return
    leaked = []
    for (module_name, attr), original in _leak_baseline.items():
        module = importlib.import_module(module_name)
        current = getattr(module, attr, None)
        if current is not original:
            leaked.append(f"{module_name}.{attr} -> {current!r}")
            # Repair, so ONE offender does not cascade into a wall of unrelated
            # failures. The point is to attribute the leak, not to punish its
            # victims.
            setattr(module, attr, original)
    _leak_baseline.clear()
    if leaked:
        raise AssertionError(
            f"{item.nodeid} left a process-global patched, which silently "
            f"corrupts every later test in this process: " + "; ".join(leaked)
            + ". A common cause is entering `patch(...)` from inside a thread "
            "worker: the swap is not thread-local, so two threads can "
            "interleave and leave the mock installed permanently. Hoist the "
            "patch to wrap the whole concurrent section on the calling thread."
        )
