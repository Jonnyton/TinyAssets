"""Handoff authority — authenticated subject, source ownership, declaration
binding, destination consent, and irreversible-effect confirmation.

Requirement source: ``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets/
specs/real-world-handoffs-and-outcomes/spec.md`` (tasks 5.2, 5.4).

Covered requirements:
  - Real-world handoffs are declared external-effect outputs
  - Handoff authority combines destination consent and irreversible-action
    confirmation
  - Dry runs never create external handoffs or authoritative outcomes
"""

from __future__ import annotations

import json

import pytest

from tinyassets.handoffs import adapters as handoff_adapters
from tinyassets.handoffs import service
from tinyassets.handoffs.adapters import HandoffResult
from tinyassets.handoffs.models import (
    HandoffAuthorityError,
    HandoffConfirmationRequired,
    HandoffValidationError,
)

CANONICAL_HANDLES = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",
    "get_status",
}

DECLARATION = {
    "output_field": "submission",
    "adapter": "arxiv",
    "adapter_action": "submit",
    "destination": "arxiv.org/cs",
    "effect_class": "irreversible",
    "outcome_kind": "preprint_submission",
    "evidence_contract": {"id_field": "arxiv_id"},
}


def _branch(declarations: list[dict] | None = None, branch_def_id: str = "b1") -> dict:
    return {
        "branch_def_id": branch_def_id,
        "name": f"Branch {branch_def_id}",
        "entry_point": "n1",
        "graph_nodes": [{"id": "n1", "node_def_id": "n1", "position": 0}],
        "node_defs": [{
            "node_id": "n1",
            "display_name": "Writer",
            "source_code": "def run(state):\n    return {}",
            "output_keys": ["submission"],
            "handoffs": [dict(DECLARATION)] if declarations is None else declarations,
        }],
    }


class Env:
    """One isolated data root with a published version, a completed run, and a
    consent grant — the minimum shape a real handoff needs."""

    def __init__(self, base, universe_dir, version, run_id, owner="account-alice"):
        self.base = base
        self.universe_dir = universe_dir
        self.version = version
        self.run_id = run_id
        self.owner = owner
        self.calls: list = []

    @property
    def version_id(self) -> str:
        return self.version.branch_version_id


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.runs import create_run, update_run_status
    from tinyassets.storage.effector_consents import grant_consent

    version = publish_branch_version(base, _branch(), publisher="account-alice")
    run_id = create_run(
        base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="account-alice",
        owner_user_id="account-alice",
    )
    update_run_status(
        base, run_id, status="completed", output={"submission": {"title": "Paper"}}
    )
    universe_dir = base / "u1"
    universe_dir.mkdir()
    grant_consent(
        universe_dir,
        sink="arxiv",
        destination="arxiv.org/cs",
        granted_by="account-alice",
    )
    return Env(base, universe_dir, version, run_id)


@pytest.fixture
def adapter(env):
    """Register a recording adapter and always unregister it.

    The registry is process-global; leaving one bound would let a later test
    "pass" because a neighbour registered the adapter it forgot to.
    """
    def _adapter(request):
        env.calls.append(request)
        return HandoffResult(state="accepted", external_id="arXiv:2601.00001")

    handoff_adapters.register_adapter("arxiv", _adapter)
    yield _adapter
    handoff_adapters.unregister_adapter("arxiv")


def _prepare(env, **kwargs):
    return service.prepare(
        actor_id=kwargs.pop("actor_id", env.owner),
        base_path=env.base,
        universe_dir=env.universe_dir,
        run_id=kwargs.pop("run_id", env.run_id),
        branch_version_id=kwargs.pop("branch_version_id", env.version_id),
        output_field=kwargs.pop("output_field", "submission"),
        **kwargs,
    )


def _execute(env, **kwargs):
    return service.execute(
        actor_id=kwargs.pop("actor_id", env.owner),
        base_path=env.base,
        universe_dir=env.universe_dir,
        run_id=kwargs.pop("run_id", env.run_id),
        branch_version_id=kwargs.pop("branch_version_id", env.version_id),
        output_field=kwargs.pop("output_field", "submission"),
        **kwargs,
    )


# ── Authenticated subject ─────────────────────────────────────────────────────

class TestRequestSubject:
    def test_anonymous_request_has_no_handoff_authority(self, monkeypatch):
        from tinyassets.handoffs.authority import request_subject

        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: "anonymous",
        )
        with pytest.raises(HandoffAuthorityError):
            request_subject()

    def test_env_actor_does_not_confer_authority(self, monkeypatch):
        """UNIVERSE_SERVER_USER must not become a handoff subject.

        ``engine_helpers._current_actor`` still honours that env var; this path
        deliberately does not, because a handoff moves a real-world effect.
        """
        from tinyassets.handoffs.authority import request_subject

        monkeypatch.setenv("UNIVERSE_SERVER_USER", "account-mallory")
        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: "anonymous",
        )
        with pytest.raises(HandoffAuthorityError):
            request_subject()

    def test_authenticated_subject_is_returned(self, monkeypatch):
        from tinyassets.handoffs.authority import request_subject

        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: "account-alice",
        )
        assert request_subject() == "account-alice"


# ── Source authority ──────────────────────────────────────────────────────────

class TestSourceAuthority:
    def test_foreign_run_is_refused(self, env):
        with pytest.raises(HandoffAuthorityError):
            _prepare(env, actor_id="account-mallory")

    def test_foreign_run_and_missing_run_are_indistinguishable(self, env):
        """A probe must not learn that someone else's run exists."""
        with pytest.raises(HandoffAuthorityError) as foreign:
            _prepare(env, actor_id="account-mallory")
        with pytest.raises(HandoffAuthorityError) as missing:
            _prepare(env, actor_id="account-mallory", run_id="run-does-not-exist")
        assert "not available to this account" in str(foreign.value)
        assert "not available to this account" in str(missing.value)

    def test_incomplete_run_is_refused(self, env):
        from tinyassets.runs import create_run

        running = create_run(
            env.base,
            branch_def_id="b1",
            thread_id="t2",
            inputs={},
            actor=env.owner,
            owner_user_id=env.owner,
        )
        with pytest.raises(HandoffValidationError, match="completed run"):
            _prepare(env, run_id=running)

    def test_run_from_a_different_branch_is_refused(self, env):
        from tinyassets.branch_versions import publish_branch_version

        other = publish_branch_version(
            env.base, _branch(branch_def_id="b2"), publisher=env.owner
        )
        with pytest.raises(HandoffValidationError, match="did not come from"):
            _prepare(env, branch_version_id=other.branch_version_id)

    def test_run_without_the_declared_output_is_refused(self, env):
        from tinyassets.runs import create_run, update_run_status

        empty = create_run(
            env.base,
            branch_def_id="b1",
            thread_id="t3",
            inputs={},
            actor=env.owner,
            owner_user_id=env.owner,
        )
        update_run_status(env.base, empty, status="completed", output={"other": 1})
        with pytest.raises(HandoffValidationError, match="produced no"):
            _prepare(env, run_id=empty)


# ── Declaration binding ───────────────────────────────────────────────────────

class TestDeclarationBinding:
    def test_undeclared_output_is_refused(self, env):
        with pytest.raises(HandoffValidationError, match="not declared as a handoff"):
            _prepare(env, output_field="other")

    def test_substituted_destination_is_refused_before_consent(self, env):
        with pytest.raises(HandoffValidationError, match="not the declared destination"):
            _prepare(env, destination="evil.example.com")

    def test_substituted_destination_never_reaches_the_adapter(self, env, adapter):
        with pytest.raises(HandoffValidationError):
            _execute(env, destination="evil.example.com")
        assert env.calls == []

    def test_declaration_carrying_credential_material_is_refused(self, env):
        from tinyassets.branch_versions import publish_branch_version

        leaky = dict(DECLARATION)
        leaky["evidence_contract"] = {"headers": {"authorization": "Bearer abc"}}
        version = publish_branch_version(
            env.base, _branch([leaky], branch_def_id="b3"), publisher=env.owner
        )
        with pytest.raises(HandoffValidationError, match="credential material"):
            service.list_declarations(
                actor_id=env.owner,
                base_path=env.base,
                branch_version_id=version.branch_version_id,
            )

    def test_two_nodes_declaring_the_same_output_is_refused(self, env):
        from tinyassets.branch_versions import publish_branch_version

        branch = _branch(branch_def_id="b4")
        branch["graph_nodes"].append({"id": "n2", "node_def_id": "n2", "position": 1})
        branch["node_defs"].append({
            "node_id": "n2",
            "display_name": "Second",
            "source_code": "def run(state):\n    return {}",
            "output_keys": ["submission"],
            "handoffs": [dict(DECLARATION, destination="arxiv.org/math")],
        })
        version = publish_branch_version(env.base, branch, publisher=env.owner)
        with pytest.raises(HandoffValidationError, match="declared as a handoff twice"):
            service.list_declarations(
                actor_id=env.owner,
                base_path=env.base,
                branch_version_id=version.branch_version_id,
            )


# ── Destination consent ───────────────────────────────────────────────────────

class TestDestinationConsent:
    def test_missing_consent_refuses_before_the_adapter(self, env, adapter):
        from tinyassets.storage.effector_consents import revoke_consent

        revoke_consent(env.universe_dir, sink="arxiv", destination="arxiv.org/cs")
        with pytest.raises(HandoffAuthorityError, match="no active consent grant"):
            _execute(env)
        assert env.calls == []

    def test_consent_for_another_destination_does_not_transfer(self, env):
        from tinyassets.storage.effector_consents import grant_consent, revoke_consent

        revoke_consent(env.universe_dir, sink="arxiv", destination="arxiv.org/cs")
        grant_consent(
            env.universe_dir,
            sink="arxiv",
            destination="arxiv.org/math",
            granted_by=env.owner,
        )
        with pytest.raises(HandoffAuthorityError):
            _prepare(env)


# ── Irreversible-effect confirmation ──────────────────────────────────────────

class TestConfirmation:
    def test_irreversible_effect_requires_confirmation(self, env, adapter):
        with pytest.raises(HandoffConfirmationRequired) as exc:
            _execute(env)
        assert env.calls == []
        assert exc.value.requirement["destination"] == "arxiv.org/cs"
        assert exc.value.requirement["source_version"] == env.version_id

    def test_standing_consent_alone_does_not_authorize(self, env, adapter):
        """Consent is granted in the fixture; it is still not enough."""
        from tinyassets.storage.effector_consents import is_consent_active

        assert is_consent_active(
            env.universe_dir, sink="arxiv", destination="arxiv.org/cs"
        )
        with pytest.raises(HandoffConfirmationRequired):
            _execute(env)

    def test_prepare_then_confirm_executes_once(self, env, adapter):
        prepared = _prepare(env)
        assert prepared["status"] == "confirmation_required"
        result = _execute(env, confirmation=prepared["confirmation_token"])
        assert result["status"] == "accepted"
        assert result["executed"] is True
        assert len(env.calls) == 1

    def test_confirmation_is_single_use(self, env, adapter):
        prepared = _prepare(env)
        token = prepared["confirmation_token"]
        _execute(env, confirmation=token)
        # Replaying the same token must not authorize a second effect. The
        # receipt would also stop it, but the token must fail on its own.
        with pytest.raises(HandoffConfirmationRequired):
            service.execute(
                actor_id=env.owner,
                base_path=env.base,
                universe_dir=env.universe_dir,
                run_id=env.run_id,
                branch_version_id=env.version_id,
                output_field="submission",
                confirmation=token,
            )

    def test_expired_confirmation_is_refused(self, env, adapter):
        prepared = _prepare(env)
        with pytest.raises(HandoffConfirmationRequired):
            _execute(
                env,
                confirmation=prepared["confirmation_token"],
                now=prepared["confirmation_expires_at"] + 1.0,
            )
        assert env.calls == []

    def test_confirmation_from_another_account_is_refused(self, env, adapter):
        """A token is bound to the owner that minted it."""
        from tinyassets.handoffs.store import HandoffStore

        prepared = _prepare(env)
        store = HandoffStore(env.base)
        store.initialize()
        assert store.consume_confirmation(
            prepared["confirmation_token"],
            owner_id="account-mallory",
            effect_key=prepared["effect_key"],
            sink="arxiv",
            fingerprint="whatever",
            now=prepared["confirmation_expires_at"] - 1.0,
        ) is None

    def test_confirmation_bound_to_a_stale_source_version_does_not_match(
        self, env, adapter
    ):
        """Confirmation names source hash/version N; initiation names N+1."""
        from tinyassets.branch_versions import publish_branch_version
        from tinyassets.runs import create_run, update_run_status

        prepared = _prepare(env)

        edited = _branch()
        edited["node_defs"][0]["description"] = "revised"
        newer = publish_branch_version(env.base, edited, publisher=env.owner)
        assert newer.branch_version_id != env.version_id

        newer_run = create_run(
            env.base,
            branch_def_id="b1",
            thread_id="t9",
            inputs={},
            actor=env.owner,
            owner_user_id=env.owner,
        )
        update_run_status(
            env.base,
            newer_run,
            status="completed",
            output={"submission": {"title": "Paper"}},
        )

        with pytest.raises(HandoffConfirmationRequired):
            _execute(
                env,
                run_id=newer_run,
                branch_version_id=newer.branch_version_id,
                confirmation=prepared["confirmation_token"],
            )
        assert env.calls == []

    def test_reversible_effect_needs_no_confirmation(self, env):
        from tinyassets.branch_versions import publish_branch_version
        from tinyassets.runs import create_run, update_run_status
        from tinyassets.storage.effector_consents import grant_consent

        reversible = dict(DECLARATION, effect_class="reversible", outcome_kind="merged_pr")
        branch = _branch([reversible], branch_def_id="b5")
        version = publish_branch_version(env.base, branch, publisher=env.owner)
        run_id = create_run(
            env.base,
            branch_def_id="b5",
            thread_id="t5",
            inputs={},
            actor=env.owner,
            owner_user_id=env.owner,
        )
        update_run_status(
            env.base, run_id, status="completed", output={"submission": {"x": 1}}
        )
        grant_consent(
            env.universe_dir,
            sink="arxiv",
            destination="arxiv.org/cs",
            granted_by=env.owner,
        )
        prepared = service.prepare(
            actor_id=env.owner,
            base_path=env.base,
            universe_dir=env.universe_dir,
            run_id=run_id,
            branch_version_id=version.branch_version_id,
            output_field="submission",
        )
        assert prepared["status"] == "ready"
        assert prepared["confirmation_required"] is False


# ── Adapter seam ──────────────────────────────────────────────────────────────

class TestAdapterSeam:
    def test_unregistered_adapter_fails_closed(self, env):
        prepared = _prepare(env)
        with pytest.raises(HandoffValidationError, match="not registered"):
            _execute(env, confirmation=prepared["confirmation_token"])

    def test_unregistered_adapter_does_not_consume_the_confirmation(self, env):
        """Resolving the adapter happens before the token is spent."""
        prepared = _prepare(env)
        with pytest.raises(HandoffValidationError):
            _execute(env, confirmation=prepared["confirmation_token"])

        def _adapter(request):
            env.calls.append(request)
            return HandoffResult(state="accepted", external_id="arXiv:2601.00002")

        handoff_adapters.register_adapter("arxiv", _adapter)
        try:
            result = _execute(env, confirmation=prepared["confirmation_token"])
        finally:
            handoff_adapters.unregister_adapter("arxiv")
        assert result["status"] == "accepted"

    def test_adapter_never_receives_credential_material(self, env, adapter):
        prepared = _prepare(env)
        _execute(env, confirmation=prepared["confirmation_token"])
        request = env.calls[0]
        serialized = json.dumps(request.redacted())
        for banned in ("token", "secret", "authorization", "api_key"):
            assert banned not in serialized.lower()

    def test_accepted_without_an_external_id_is_rejected(self):
        with pytest.raises(HandoffValidationError, match="stable external id"):
            HandoffResult(state="accepted")


# ── Router half ───────────────────────────────────────────────────────────────

class TestRouterHalf:
    def test_handoff_actions_add_no_advertised_handle(self, env):
        """Ask the live MCP surface, not a reflection heuristic.

        An earlier version of this test scanned module attributes for a marker
        that does not exist, so it compared an empty set and could never go red.
        """
        import asyncio
        import importlib

        from tinyassets import universe_server as mod

        importlib.reload(mod)
        try:
            advertised = {
                tool.name for tool in asyncio.run(mod.mcp.list_tools(run_middleware=True))
            }
        finally:
            importlib.reload(mod)
        assert advertised == CANONICAL_HANDLES

    def test_handoff_actions_are_listed_for_discovery(self, env, monkeypatch):
        from tinyassets.api.extensions import _extensions_impl

        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: env.owner,
        )
        unknown = json.loads(_extensions_impl(action="definitely_not_an_action"))
        assert "handoff_execute" in unknown["available_actions"]

    def test_unauthenticated_router_call_is_refused(self, env, monkeypatch):
        from tinyassets.api.extensions import _extensions_impl

        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: "anonymous",
        )
        payload = json.loads(_extensions_impl(action="handoff_list"))
        assert payload["code"] == "handoff_authority_required"

    def test_router_resolves_the_actor_server_side(self, env, monkeypatch):
        """No caller kwarg can name the acting account."""
        from tinyassets.api.extensions import _extensions_impl

        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: env.owner,
        )
        payload = json.loads(
            _extensions_impl(action="handoff_list", author="account-mallory")
        )
        assert payload["handoffs"] == []
        assert "error" not in payload

    def test_scope_registry_derives_write_and_costly(self):
        from tinyassets.auth.provider import build_action_scope_registry

        registry = build_action_scope_registry()
        assert registry["extensions.handoff_execute"].oauth_scope.endswith(".costly")
        for action in (
            "handoff_prepare",
            "handoff_record_evidence",
            "handoff_attest_outcome",
        ):
            assert registry[f"extensions.{action}"].oauth_scope.endswith(".write")
        for action in ("handoff_get", "handoff_list", "handoff_dry_run"):
            assert registry[f"extensions.{action}"].oauth_scope.endswith(".read")
