from __future__ import annotations

import hashlib
import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tinyassets.api.github_effect_actions import (
    apply_github_pr_authorization,
    create_github_pr_authorization,
)
from tinyassets.runtime.effect_authorization import (
    EffectRouteError,
    GitHubEffectService,
    GitHubOwnerGrant,
    RepositorySnapshot,
    ResultReview,
)
from tinyassets.runtime.execution_capsule import hash_canonical_jcs
from tinyassets.storage.effect_authorizations import EffectAuthorizationStore
from tinyassets.storage.result_reviews import ResultReviewStore

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
JOB_ID = "ca443d6d-7f62-4b84-a8a4-c11fbf3482db"
LEASE_ID = "a805b02f-f1a4-4ac8-a665-c56682fe9f7e"
PATCH = (
    b"diff --git a/a.txt b/a.txt\n"
    b"new file mode 100644\n"
    b"--- /dev/null\n"
    b"+++ b/a.txt\n"
    b"@@ -0,0 +1 @@\n"
    b"+hello\n"
)
PATCH_SHA = hashlib.sha256(PATCH).hexdigest()
BASE_COMMIT = "2" * 40
BASE_TREE = "3" * 40
RESULTING_TREE = "4" * 40
RESULT_BODY = {
    "outcome": "succeeded",
    "executor": {"daemon_id": "daemon:1"},
    "repo_patch": {
        "format": "git-diff-v1",
        "blob_ref": f"blob:sha256:{PATCH_SHA}",
        "blob_sha256": PATCH_SHA,
        "size_bytes": len(PATCH),
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "resulting_tree": RESULTING_TREE,
    },
    "revalidation": {"verifier_policy_sha256": "6" * 64},
}
RESULT_SHA = hash_canonical_jcs(RESULT_BODY).hex()


class MemoryJobStore:
    def __init__(self) -> None:
        self.state = {
            "job_id": JOB_ID,
            "owner_user_id": "owner:1",
            "status": "succeeded",
            "lease_fence": 7,
            "lease_id": LEASE_ID,
            "capsule_sha256": "5" * 64,
            "accepted_result_sha256": RESULT_SHA,
            "candidate_result": {
                **RESULT_BODY,
                "signature": {"result_sha256": RESULT_SHA},
            },
        }

    def read_result_state(self, job_id: str) -> dict[str, Any]:
        assert job_id == JOB_ID
        return self.state


class MemoryCapsuleStore:
    def _load_verified_capsule(self, job_id: str, capsule_sha256: str) -> dict[str, Any]:
        assert (job_id, capsule_sha256) == (JOB_ID, "5" * 64)
        return {
            "payload": {
                "job_id": JOB_ID,
                "owner_user_id": "owner:1",
                "universe_scope": {"universe_id": "universe:1"},
                "base": {"commit": BASE_COMMIT, "tree": BASE_TREE},
                "lease": {"lease_id": LEASE_ID, "fence": 7},
            },
            "integrity": {"capsule_sha256": "5" * 64},
        }


class MemoryBlobStore:
    def __init__(self) -> None:
        self.content = PATCH

    def read_verified_bytes(self, **kwargs: Any) -> bytes:
        assert kwargs == {
            "blob_ref": f"blob:sha256:{PATCH_SHA}",
            "owner_user_id": "owner:1",
            "job_id": JOB_ID,
            "lease_id": LEASE_ID,
            "fence": 7,
            "expected_sha256": PATCH_SHA,
            "expected_size_bytes": len(PATCH),
        }
        return self.content


class MemoryCredentialResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self.fail = False

    @contextmanager
    def resolve_bound_credential(
        self,
        *,
        binding_id: str,
        universe_id: str,
        destination: str,
        purpose: str,
    ):
        self.calls.append((binding_id, universe_id, destination, purpose))
        if self.fail:
            raise RuntimeError("vault unavailable")
        yield b"vault-token"


class MemoryGitHub:
    def __init__(self) -> None:
        self.snapshot = RepositorySnapshot(
            repository_node_id="R_node_1",
            installation_id="installation:1",
            base_ref="main",
            head_sha=BASE_COMMIT,
            base_tree=BASE_TREE,
        )
        self.branches: dict[str, dict[str, str]] = {}
        self.prs: list[dict[str, Any]] = []
        self.branch_creates = 0
        self.pr_creates = 0
        self.approvals = 0
        self.merges = 0
        self.raise_after_branch = False
        self.raise_after_pr = False
        self.after_materialize = None

    def read_repository(self, **_: Any) -> RepositorySnapshot:
        return self.snapshot

    def find_effect(self, *, head_ref: str, effect_id: str, **_: Any) -> dict[str, Any]:
        branch = self.branches.get(head_ref)
        pr = next(
            (
                row
                for row in self.prs
                if row["head_ref"] == head_ref and row["effect_id"] == effect_id
            ),
            None,
        )
        return {"branch": branch, "pull_request": pr}

    def materialize_patch(self, **kwargs: Any) -> dict[str, str]:
        assert kwargs["patch_bytes"] == PATCH
        assert kwargs["base_commit"] == BASE_COMMIT
        assert kwargs["base_tree"] == BASE_TREE
        assert kwargs["resulting_tree"] == RESULTING_TREE
        assert kwargs["credential"] == b"vault-token"
        self.branch_creates += 1
        branch = {
            "head_ref": kwargs["head_ref"],
            "commit_sha": "7" * 40,
            "tree_sha": RESULTING_TREE,
            "effect_id": kwargs["effect_id"],
        }
        self.branches[kwargs["head_ref"]] = branch
        if self.after_materialize is not None:
            self.after_materialize()
        if self.raise_after_branch:
            self.raise_after_branch = False
            raise TimeoutError("lost response after branch creation")
        return branch

    def open_reviewable_pr(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["draft"] is False
        assert kwargs["credential"] == b"vault-token"
        self.pr_creates += 1
        pr = {
            "number": 42,
            "url": "https://github.example/pulls/42",
            "state": "open",
            "head_ref": kwargs["head_ref"],
            "effect_id": kwargs["effect_id"],
        }
        self.prs.append(pr)
        if self.raise_after_pr:
            self.raise_after_pr = False
            raise TimeoutError("lost response after PR creation")
        return pr


def _review(**overrides: Any) -> ResultReview:
    values = {
        "review_record_id": "review:1",
        "reviewer_id": "verifier:1",
        "verdict": "approved",
        "accepted_result_sha256": RESULT_SHA,
        "patch_blob_sha256": PATCH_SHA,
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "resulting_tree": RESULTING_TREE,
        "expected_repository_head_sha": BASE_COMMIT,
        "verifier_policy_sha256": "6" * 64,
        "reviewed_at": NOW,
        "revoked_at": None,
        "superseded_by": None,
    }
    values.update(overrides)
    return ResultReview(**values)


def _grant(**overrides: Any) -> GitHubOwnerGrant:
    values = {
        "grant_id": "grant:1",
        "owner_user_id": "owner:1",
        "universe_id": "universe:1",
        "github_installation_id": "installation:1",
        "repository_node_id": "R_node_1",
        "repository_full_name": "owner/repo",
        "permitted_action": "open_reviewable_pr",
        "permitted_base_ref": "main",
        "required_head_prefix": "tiny/effects/",
        "credential_binding_id": "secret:binding:1",
        "generation": 3,
        "granted_at": NOW,
        "expires_at": NOW + timedelta(days=1),
        "revoked_at": None,
    }
    values.update(overrides)
    return GitHubOwnerGrant(**values)


@pytest.fixture
def route(tmp_path: Path):
    authorization_store = EffectAuthorizationStore(tmp_path / "effects.sqlite3")
    review_store = ResultReviewStore(tmp_path / "reviews.sqlite3")
    review_store.record(_review())
    authorization_store.put_owner_grant(_grant())
    github = MemoryGitHub()
    credentials = MemoryCredentialResolver()
    service = GitHubEffectService(
        authorization_store=authorization_store,
        review_store=review_store,
        job_store=MemoryJobStore(),
        capsule_store=MemoryCapsuleStore(),
        blob_store=MemoryBlobStore(),
        github=github,
        credentials=credentials,
        clock=lambda: NOW,
    )
    return service, authorization_store, review_store, github, credentials


def _authorize(service: GitHubEffectService):
    return create_github_pr_authorization(
        service,
        job_id=JOB_ID,
        grant_id="grant:1",
        review_record_id="review:1",
        authenticated_owner_id="owner:1",
        expires_at=NOW + timedelta(hours=1),
    )


def test_exactly_once_across_duplicate_authorization_and_twenty_apply_calls(route) -> None:
    service, _, _, github, credentials = route
    first = _authorize(service)
    assert _authorize(service) == first
    assert first.effect_id == hash_canonical_jcs(
        ["github_pull_request/v1", "universe:1", "R_node_1", RESULT_SHA]
    ).hex()

    with ThreadPoolExecutor(max_workers=20) as pool:
        attempts = list(
            pool.map(
                lambda key: apply_github_pr_authorization(
                    service,
                    authorization_id=first.authorization_id,
                    idempotency_key=key,
                ),
                [f"transport-{i}" for i in range(20)],
            )
        )
    final = apply_github_pr_authorization(
        service,
        authorization_id=first.authorization_id,
        idempotency_key="transport-final",
    )

    succeeded = [attempt for attempt in attempts + [final] if attempt.status == "succeeded"]
    assert succeeded
    assert {attempt.effect_id for attempt in attempts + [final]} == {first.effect_id}
    assert {attempt.pr_url for attempt in succeeded} == {"https://github.example/pulls/42"}
    assert github.branch_creates == 1
    assert github.pr_creates == 1
    assert github.approvals == 0
    assert github.merges == 0
    assert credentials.calls
    assert set(credentials.calls) == {
        ("secret:binding:1", "universe:1", "owner/repo", "external_write")
    }


def test_apply_contract_accepts_no_repository_patch_or_token(route, monkeypatch) -> None:
    service, _, _, github, credentials = route
    authorization = _authorize(service)
    parameters = inspect.signature(apply_github_pr_authorization).parameters
    assert set(parameters) == {"service", "authorization_id", "idempotency_key"}

    monkeypatch.setenv("GITHUB_TOKEN", "ambient-attacker-token")
    credentials.fail = True
    with pytest.raises(EffectRouteError, match="credential_scope_mismatch"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == github.pr_creates == 0


def test_stale_head_is_rejected_before_any_write(route) -> None:
    service, _, _, github, _ = route
    authorization = _authorize(service)
    github.snapshot = RepositorySnapshot(
        repository_node_id="R_node_1",
        installation_id="installation:1",
        base_ref="main",
        head_sha="9" * 40,
        base_tree="8" * 40,
    )

    with pytest.raises(EffectRouteError, match="repository_head_moved"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == github.pr_creates == 0


def test_owner_grant_has_an_explicit_pr_only_action_ceiling() -> None:
    assert "permitted_action" in {field.name for field in fields(GitHubOwnerGrant)}


def test_effect_client_surface_has_no_approval_or_merge_authority() -> None:
    from tinyassets.effectors.github_pr import GitHubRestEffectClient
    from tinyassets.runtime.effect_authorization import GitHubEffectClient

    allowed_operations = {
        "find_effect",
        "materialize_patch",
        "open_reviewable_pr",
        "read_repository",
    }
    protocol_operations = {
        name
        for name, value in GitHubEffectClient.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    adapter_operations = {
        name
        for name, value in GitHubRestEffectClient.__dict__.items()
        if not name.startswith("_") and callable(value)
    }

    assert protocol_operations == allowed_operations
    assert adapter_operations == allowed_operations


def test_owner_grant_cannot_be_rewritten_without_a_generation_change(route) -> None:
    _, store, _, _, _ = route
    with pytest.raises(ValueError, match="new generation"):
        store.put_owner_grant(_grant(permitted_base_ref="release"))


def test_non_pr_owner_grant_cannot_authorize_the_effect(route) -> None:
    service, store, _, github, _ = route
    store.put_owner_grant(_grant(generation=4, permitted_action="merge"))
    with pytest.raises(EffectRouteError, match="target_not_granted"):
        _authorize(service)
    assert github.branch_creates == github.pr_creates == 0


def test_review_must_bind_every_effect_input_and_be_independent(route) -> None:
    service, _, reviews, github, _ = route
    reviews.record(
        _review(review_record_id="review:bad-binding", patch_blob_sha256="0" * 64)
    )
    with pytest.raises(EffectRouteError, match="review_binding_mismatch"):
        create_github_pr_authorization(
            service,
            job_id=JOB_ID,
            grant_id="grant:1",
            review_record_id="review:bad-binding",
            authenticated_owner_id="owner:1",
            expires_at=NOW + timedelta(hours=1),
        )
    reviews.record(
        _review(
            review_record_id="review:self",
            reviewer_id="daemon:1",
            patch_blob_sha256="1" * 64,
        )
    )
    with pytest.raises(EffectRouteError, match="cannot self-review"):
        create_github_pr_authorization(
            service,
            job_id=JOB_ID,
            grant_id="grant:1",
            review_record_id="review:self",
            authenticated_owner_id="owner:1",
            expires_at=NOW + timedelta(hours=1),
        )
    assert github.branch_creates == github.pr_creates == 0


def test_revoked_single_effect_authorization_cannot_start(route) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)
    store.invalidate(authorization.authorization_id)
    with pytest.raises(EffectRouteError, match="authorization_revoked"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == github.pr_creates == 0


def test_revocation_after_success_preserves_the_original_receipt(route) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)
    receipt = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-1",
    )
    store.invalidate(authorization.authorization_id, revoked_at=NOW)
    replay = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-2",
    )
    assert replay == receipt
    assert github.branch_creates == github.pr_creates == 1


def test_revocation_after_branch_creation_freezes_before_pr(route) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)
    github.after_materialize = lambda: store.invalidate(
        authorization.authorization_id, revoked_at=NOW
    )
    with pytest.raises(EffectRouteError, match="authorization_revoked"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert store.get(authorization.authorization_id).state == "needs_reconciliation"
    assert github.branch_creates == 1
    assert github.pr_creates == 0


def test_receipt_store_failure_happens_before_any_github_write(
    route, monkeypatch
) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)

    def fail_start(*_args, **_kwargs):
        raise sqlite3.OperationalError("receipt store unavailable")

    monkeypatch.setattr(store, "start", fail_start)
    with pytest.raises(EffectRouteError, match="receipt_store_unavailable"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == github.pr_creates == 0


def test_grant_generation_is_rechecked_between_branch_and_pr(route) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)
    github.after_materialize = lambda: store.put_owner_grant(_grant(generation=4))

    with pytest.raises(EffectRouteError, match="grant_generation_changed"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == 1
    assert github.pr_creates == 0


def test_abrupt_process_loss_after_pr_reconciles_after_stale_reservation(route) -> None:
    service, store, _, github, _ = route
    authorization = _authorize(service)
    disposition, _ = store.start(authorization.authorization_id, now=NOW)
    assert disposition == "start"
    github.branches[authorization.head_ref] = {
        "head_ref": authorization.head_ref,
        "commit_sha": "7" * 40,
        "tree_sha": RESULTING_TREE,
        "effect_id": authorization.effect_id,
    }
    github.prs.append(
        {
            "number": 42,
            "url": "https://github.example/pulls/42",
            "state": "open",
            "head_ref": authorization.head_ref,
            "effect_id": authorization.effect_id,
        }
    )
    service.clock = lambda: NOW + timedelta(minutes=6)

    held = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport",
    )
    assert held.status == "in_flight"
    assert store.get(authorization.authorization_id).state == "needs_reconciliation"
    recovered = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-reconcile",
    )
    assert recovered.status == "succeeded"
    assert github.branch_creates == github.pr_creates == 0


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        ("result_hash", "accepted_result_mismatch"),
        ("patch_bytes", "artifact_hash_mismatch"),
        ("capsule_base", "base_binding_mismatch"),
        ("review", "review_not_approved"),
        ("grant_generation", "grant_generation_changed"),
        ("repository", "repository_identity_mismatch"),
    ],
)
def test_every_authority_binding_fails_closed(route, mutation: str, failure: str) -> None:
    service, store, reviews, github, _ = route
    authorization = _authorize(service)
    if mutation == "result_hash":
        service.job_store.state["accepted_result_sha256"] = "0" * 64
    elif mutation == "patch_bytes":
        service.blob_store.content = b"substituted"
    elif mutation == "capsule_base":
        service.capsule_store._load_verified_capsule = lambda *_: {
            "payload": {
                "job_id": JOB_ID,
                "owner_user_id": "owner:1",
                "universe_scope": {"universe_id": "universe:1"},
                "base": {"commit": "0" * 40, "tree": BASE_TREE},
                "lease": {"lease_id": LEASE_ID, "fence": 7},
            },
            "integrity": {"capsule_sha256": "5" * 64},
        }
    elif mutation == "review":
        reviews.revoke("review:1", revoked_at=NOW)
    elif mutation == "grant_generation":
        store.put_owner_grant(_grant(generation=4))
    elif mutation == "repository":
        github.snapshot = RepositorySnapshot(
            repository_node_id="R_attacker",
            installation_id="installation:1",
            base_ref="main",
            head_sha=BASE_COMMIT,
            base_tree=BASE_TREE,
        )

    with pytest.raises(EffectRouteError, match=failure):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport",
        )
    assert github.branch_creates == github.pr_creates == 0
    assert store.get(authorization.authorization_id).state == "revoked"


@pytest.mark.parametrize("crash_point", ["branch", "pr"])
def test_crash_reconciles_deterministic_remote_state_without_duplicates(route, crash_point) -> None:
    service, _, _, github, _ = route
    authorization = _authorize(service)
    setattr(github, f"raise_after_{crash_point}", True)

    with pytest.raises(EffectRouteError, match="needs_reconciliation"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport-1",
        )
    recovered = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-2",
    )
    assert recovered.status == "succeeded"
    assert recovered.pr_url == "https://github.example/pulls/42"
    assert github.branch_creates == 1
    assert github.pr_creates == 1


def test_closed_pr_replay_returns_original_receipt(route) -> None:
    service, _, _, github, _ = route
    authorization = _authorize(service)
    receipt = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-1",
    )
    github.prs[0]["state"] = "closed"
    replay = apply_github_pr_authorization(
        service,
        authorization_id=authorization.authorization_id,
        idempotency_key="transport-2",
    )
    assert replay == receipt
    assert github.branch_creates == github.pr_creates == 1


def test_reconciliation_rejects_matching_pr_on_mismatched_remote_branch(route) -> None:
    service, _, _, github, _ = route
    authorization = _authorize(service)
    github.raise_after_pr = True
    with pytest.raises(EffectRouteError, match="needs_reconciliation"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport-1",
        )
    github.branches[authorization.head_ref]["tree_sha"] = "8" * 40

    with pytest.raises(EffectRouteError, match="remote_identity_conflict"):
        apply_github_pr_authorization(
            service,
            authorization_id=authorization.authorization_id,
            idempotency_key="transport-2",
        )
    assert github.branch_creates == github.pr_creates == 1


def test_platform_cas_read_recomputes_bytes_and_rejects_wrong_binding(tmp_path) -> None:
    from tinyassets.runtime.blob_refs import BlobBindingError, BlobStore

    store = BlobStore(tmp_path / "blobs")
    upload = store.init_blob(
        {
            "sha256": PATCH_SHA,
            "size_bytes": len(PATCH),
            "media_type": "text/x-diff",
            "confidentiality": "public",
            "job_id": JOB_ID,
            "lease_id": LEASE_ID,
            "fence": 7,
        },
        owner_user_id="owner:1",
        daemon_id="daemon:1",
    )
    store.write_upload(upload.upload_id, PATCH)
    reference = store.commit_blob(
        upload.upload_id,
        owner_user_id="owner:1",
        daemon_id="daemon:1",
    )

    assert store.read_verified_bytes(
        blob_ref=reference.ref,
        owner_user_id="owner:1",
        job_id=JOB_ID,
        lease_id=LEASE_ID,
        fence=7,
        expected_sha256=PATCH_SHA,
        expected_size_bytes=len(PATCH),
    ) == PATCH
    with pytest.raises(BlobBindingError):
        store.read_verified_bytes(
            blob_ref=reference.ref,
            owner_user_id="owner:attacker",
            job_id=JOB_ID,
            lease_id=LEASE_ID,
            fence=7,
            expected_sha256=PATCH_SHA,
            expected_size_bytes=len(PATCH),
        )


def test_bound_credential_requires_exact_opaque_binding(monkeypatch) -> None:
    from tinyassets import credential_broker
    from tinyassets.credentials import CredentialUnavailable

    binding_id = "secret:v1:" + "a" * 64
    binding = SimpleNamespace(ref=binding_id, scope=object())
    lease = object()
    backend = SimpleNamespace(get=lambda actual, scope: lease)
    monkeypatch.setattr(credential_broker, "find_binding", lambda *a, **k: binding)

    assert credential_broker.resolve_bound_credential(
        binding_id=binding_id,
        universe_id="universe:1",
        destination="owner/repo",
        purpose="external_write",
        backend=backend,
    ) is lease
    with pytest.raises(CredentialUnavailable):
        credential_broker.resolve_bound_credential(
            binding_id="secret:v1:" + "b" * 64,
            universe_id="universe:1",
            destination="owner/repo",
            purpose="external_write",
            backend=backend,
        )


def test_accepted_git_diff_is_applied_to_exact_base_contents() -> None:
    from tinyassets.effectors.github_pr import _changes_from_git_diff

    patch = (
        b"diff --git a/a.txt b/a.txt\n"
        b"--- a/a.txt\n"
        b"+++ b/a.txt\n"
        b"@@ -1,2 +1,2 @@\n"
        b"-hello\n"
        b"+goodbye\n"
        b" world\n"
        b"diff --git a/b.txt b/b.txt\n"
        b"new file mode 100644\n"
        b"--- /dev/null\n"
        b"+++ b/b.txt\n"
        b"@@ -0,0 +1 @@\n"
        b"+new\n"
    )

    changes = _changes_from_git_diff(
        patch,
        fetch_base=lambda path: {"a.txt": "hello\nworld\n"}[path],
    )
    assert changes == {"a.txt": "goodbye\nworld\n", "b.txt": "new\n"}


def test_accepted_git_diff_rejects_binary_or_path_escape() -> None:
    from tinyassets.effectors.github_pr import _changes_from_git_diff

    with pytest.raises(ValueError, match="binary"):
        _changes_from_git_diff(
            b"diff --git a/x b/x\nBinary files a/x and b/x differ\n",
            fetch_base=lambda _: "",
        )
    with pytest.raises(ValueError, match="path"):
        _changes_from_git_diff(
            b"diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n@@ -0,0 +1 @@\n+x\n",
            fetch_base=lambda _: "",
        )


def test_rest_effect_client_materializes_exact_result_binding(monkeypatch) -> None:
    from tinyassets.effectors import github_pr

    calls: list[dict[str, Any]] = []

    def fake_fetch(*, owner_repo, path, ref, capability_token):
        assert (owner_repo, path, ref, capability_token) == (
            "owner/repo",
            "a.txt",
            BASE_COMMIT,
            "vault-token",
        )
        return "hello\n", None

    def fake_materialize(**kwargs):
        calls.append(kwargs)
        return {
            "materialized": True,
            "head_branch": kwargs["head_branch"],
            "commit_sha": "7" * 40,
            "tree_sha": RESULTING_TREE,
        }

    monkeypatch.setattr(github_pr, "_fetch_file_at_ref", fake_fetch)
    monkeypatch.setattr(github_pr, "_materialize_branch", fake_materialize)
    client = github_pr.GitHubRestEffectClient()
    branch = client.materialize_patch(
        repository="owner/repo",
        installation_id="installation:1",
        base_ref="main",
        base_commit=BASE_COMMIT,
        base_tree=BASE_TREE,
        resulting_tree=RESULTING_TREE,
        head_ref="tiny/effects/effect-1",
        effect_id="effect-1",
        patch_bytes=(
            b"diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
            b"@@ -1 +1 @@\n-hello\n+goodbye\n"
        ),
        credential=b"vault-token",
    )

    assert branch["effect_id"] == "effect-1"
    assert calls[0]["changes_json"] == {"a.txt": "goodbye\n"}
    assert calls[0]["expected_base_commit"] == BASE_COMMIT
    assert calls[0]["expected_base_tree"] == BASE_TREE
    assert calls[0]["expected_resulting_tree"] == RESULTING_TREE


def test_rest_effect_client_opens_review_ready_pr_and_reconciles_all_states(
    monkeypatch,
) -> None:
    from tinyassets.effectors import github_pr

    created: list[dict[str, Any]] = []

    def fake_create(*, path, capability_token, body):
        created.append({"path": path, "token": capability_token, "body": body})
        return {"number": 42, "html_url": "https://github.example/pulls/42"}

    marker = "TinyAssets-Effect-ID: effect-1"

    def fake_git_data(*, method, path, capability_token, body=None):
        assert method == "GET"
        assert capability_token == "vault-token"
        assert body is None
        if "/git/ref/heads/" in path:
            return {"object": {"sha": "7" * 40}}, None
        if "/git/commits/" in path:
            return {"tree": {"sha": RESULTING_TREE}}, None
        if "/pulls?" in path:
            assert "state=all" in path
            return [
                {
                    "number": 41,
                    "html_url": "https://github.example/pulls/41",
                    "state": "open",
                    "body": "unrelated PR",
                    "head": {"ref": "tiny/effects/effect-1"},
                },
                {
                    "number": 42,
                    "html_url": "https://github.example/pulls/42",
                    "state": "closed",
                    "body": marker,
                    "head": {"ref": "tiny/effects/effect-1"},
                }
            ], None
        raise AssertionError(path)

    monkeypatch.setattr(github_pr, "_github_api_request", fake_create)
    monkeypatch.setattr(github_pr, "_git_data_api", fake_git_data)
    client = github_pr.GitHubRestEffectClient()
    opened = client.open_reviewable_pr(
        repository="owner/repo",
        installation_id="installation:1",
        base_ref="main",
        head_ref="tiny/effects/effect-1",
        effect_id="effect-1",
        title="Accepted result",
        body=marker,
        draft=False,
        credential=b"vault-token",
    )
    found = client.find_effect(
        repository="owner/repo",
        installation_id="installation:1",
        head_ref="tiny/effects/effect-1",
        effect_id="effect-1",
        credential=b"vault-token",
        include_all_pr_states=True,
    )

    assert opened["number"] == 42
    assert created[0]["body"]["draft"] is False
    assert marker in created[0]["body"]["body"]
    assert found["pull_request"]["state"] == "closed"
