"""Result-bound authority for an exactly-once reviewable GitHub PR effect."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Mapping, Protocol

from tinyassets.runtime.execution_capsule import hash_canonical_jcs

_INVALIDATING_PREFLIGHT_FAILURES = frozenset(
    {
        "accepted_result_missing",
        "accepted_result_mismatch",
        "artifact_hash_mismatch",
        "authorization_expired",
        "authorization_revoked",
        "base_binding_mismatch",
        "base_ref_forbidden",
        "grant_generation_changed",
        "head_ref_forbidden",
        "owner_mismatch",
        "repository_head_moved",
        "repository_identity_mismatch",
        "result_not_succeeded",
        "review_binding_mismatch",
        "review_missing",
        "review_not_approved",
        "review_superseded",
        "target_not_granted",
    }
)


@dataclass(frozen=True)
class GitHubOwnerGrant:
    grant_id: str
    owner_user_id: str
    universe_id: str
    github_installation_id: str
    repository_node_id: str
    repository_full_name: str
    permitted_action: str
    permitted_base_ref: str
    required_head_prefix: str
    credential_binding_id: str
    generation: int
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True)
class ResultReview:
    review_record_id: str
    reviewer_id: str
    verdict: str
    accepted_result_sha256: str
    patch_blob_sha256: str
    base_commit: str
    base_tree: str
    resulting_tree: str
    expected_repository_head_sha: str
    verifier_policy_sha256: str
    reviewed_at: datetime
    revoked_at: datetime | None
    superseded_by: str | None


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_node_id: str
    installation_id: str
    base_ref: str
    head_sha: str
    base_tree: str


@dataclass(frozen=True)
class GitHubEffectAuthorization:
    authorization_id: str
    effect_id: str
    grant_id: str
    grant_generation: int
    job_id: str
    lease_fence: int
    accepted_result_sha256: str
    patch_blob_sha256: str
    review_record_id: str
    base_commit: str
    base_tree: str
    resulting_tree: str
    expected_repository_head_sha: str
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    state: str
    pr_number: int | None
    pr_url: str | None
    head_ref: str
    remote_started_at: datetime | None


@dataclass(frozen=True)
class EffectReceipt:
    authorization_id: str
    effect_id: str
    status: Literal["in_flight", "succeeded"]
    head_ref: str
    pr_number: int | None
    pr_url: str | None


class EffectRouteError(RuntimeError):
    """Typed, fail-closed effect rejection."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class JobResultStore(Protocol):
    def read_result_state(self, job_id: str) -> Mapping[str, Any]: ...


class VerifiedCapsuleStore(Protocol):
    def _load_verified_capsule(
        self, job_id: str, capsule_sha256: str
    ) -> Mapping[str, Any]: ...


class EffectBlobStore(Protocol):
    def read_verified_bytes(self, **kwargs: Any) -> bytes: ...


class GitHubEffectClient(Protocol):
    def read_repository(self, **kwargs: Any) -> RepositorySnapshot: ...

    def find_effect(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def materialize_patch(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def open_reviewable_pr(self, **kwargs: Any) -> Mapping[str, Any]: ...


def derive_effect_id(
    *, universe_id: str, repository_node_id: str, accepted_result_sha256: str
) -> str:
    identity = [
        "github_pull_request/v1",
        universe_id,
        repository_node_id,
        accepted_result_sha256,
    ]
    return hash_canonical_jcs(identity).hex()


class _BoundCredentialContext:
    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def __enter__(self) -> Any:
        try:
            return self.manager.__enter__()
        except Exception as exc:
            raise EffectRouteError("credential_scope_mismatch", str(exc)) from exc

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            return bool(self.manager.__exit__(exc_type, exc, traceback))
        except Exception as cleanup_error:
            raise EffectRouteError(
                "credential_scope_mismatch", str(cleanup_error)
            ) from cleanup_error


class GitHubEffectService:
    """Create and apply one PR authorization without merge authority."""

    def __init__(
        self,
        *,
        authorization_store: Any,
        review_store: Any,
        job_store: JobResultStore,
        capsule_store: VerifiedCapsuleStore,
        blob_store: EffectBlobStore,
        github: GitHubEffectClient,
        credentials: Any,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.authorization_store = authorization_store
        self.review_store = review_store
        self.job_store = job_store
        self.capsule_store = capsule_store
        self.blob_store = blob_store
        self.github = github
        self.credentials = credentials
        self.clock = clock

    def authorize(
        self,
        *,
        job_id: str,
        grant_id: str,
        review_record_id: str,
        authenticated_owner_id: str,
        expires_at: datetime,
    ) -> GitHubEffectAuthorization:
        now = self._now()
        grant = self._active_grant(grant_id, now)
        if authenticated_owner_id != grant.owner_user_id:
            raise EffectRouteError("owner_mismatch")
        if expires_at.tzinfo is None or expires_at <= now:
            raise EffectRouteError("authorization_expired")
        if grant.expires_at is not None and expires_at > grant.expires_at:
            raise EffectRouteError("authorization_expired", "exceeds standing grant")

        job, result, patch = self._accepted_result(job_id)
        if job.get("owner_user_id") != grant.owner_user_id:
            raise EffectRouteError("owner_mismatch")
        capsule = self._verified_capsule(job, result)
        universe_id = capsule["universe_scope"]["universe_id"]
        if universe_id != grant.universe_id:
            raise EffectRouteError("target_not_granted")
        self._require_base_binding(capsule, patch)

        with self._credential(grant) as credential:
            snapshot = self._read_repository(grant, credential)
        self._require_repository_binding(grant, snapshot)
        if snapshot.head_sha != patch["base_commit"] or snapshot.base_tree != patch["base_tree"]:
            raise EffectRouteError("repository_head_moved")
        review = self._approved_review(
            review_record_id,
            result=result,
            patch=patch,
            expected_repository_head_sha=snapshot.head_sha,
        )

        effect_id = derive_effect_id(
            universe_id=grant.universe_id,
            repository_node_id=grant.repository_node_id,
            accepted_result_sha256=result["signature"]["result_sha256"],
        )
        head_ref = f"{grant.required_head_prefix}{effect_id}"
        if not head_ref.startswith("tiny/effects/"):
            raise EffectRouteError("head_ref_forbidden")
        authorization = GitHubEffectAuthorization(
            authorization_id=str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"tinyassets:github-effect:{effect_id}")
            ),
            effect_id=effect_id,
            grant_id=grant.grant_id,
            grant_generation=grant.generation,
            job_id=job_id,
            lease_fence=int(job["lease_fence"]),
            accepted_result_sha256=result["signature"]["result_sha256"],
            patch_blob_sha256=patch["blob_sha256"],
            review_record_id=review.review_record_id,
            base_commit=patch["base_commit"],
            base_tree=patch["base_tree"],
            resulting_tree=patch["resulting_tree"],
            expected_repository_head_sha=snapshot.head_sha,
            authorized_by=authenticated_owner_id,
            authorized_at=now,
            expires_at=expires_at,
            revoked_at=None,
            state="authorized",
            pr_number=None,
            pr_url=None,
            head_ref=head_ref,
            remote_started_at=None,
        )
        try:
            return self.authorization_store.create(authorization)
        except ValueError as exc:
            raise EffectRouteError("effect_identity_conflict", str(exc)) from exc

    def apply(self, *, authorization_id: str) -> EffectReceipt:
        authorization = self.authorization_store.get(authorization_id)
        if authorization is None:
            raise EffectRouteError("owner_authorization_missing")
        if authorization.state == "succeeded":
            return self._receipt(authorization, "succeeded")

        try:
            grant, _, _, _, patch_bytes = self._verify_for_apply(authorization)
            credential_context = self._credential(grant)
            with credential_context as credential:
                snapshot = self._read_repository(grant, credential)
                self._require_repository_binding(grant, snapshot)
                self._require_expected_head(authorization, snapshot)
                return self._apply_reserved(
                    authorization=authorization,
                    grant=grant,
                    patch_bytes=patch_bytes,
                    credential=credential,
                )
        except EffectRouteError as exc:
            current = self.authorization_store.get(authorization_id)
            if (
                exc.code in _INVALIDATING_PREFLIGHT_FAILURES
                and current is not None
                and current.state == "authorized"
            ):
                self.authorization_store.invalidate(authorization_id)
            raise

    def _apply_reserved(
        self,
        *,
        authorization: GitHubEffectAuthorization,
        grant: GitHubOwnerGrant,
        patch_bytes: bytes,
        credential: Any,
    ) -> EffectReceipt:
        authorization_id = authorization.authorization_id
        try:
            disposition, current = self.authorization_store.start(
                authorization_id, now=self._now()
            )
        except Exception as exc:
            raise EffectRouteError("receipt_store_unavailable", str(exc)) from exc
        if disposition == "succeeded":
            return self._receipt(current, "succeeded")
        if disposition in {"in_flight", "stale"}:
            return self._receipt(current, "in_flight")
        if disposition == "reconcile":
            return self._reconcile(current, grant, credential)

        try:
            current = self._current_authorization(authorization_id)
            self._verify_for_apply(current)
            self._require_expected_head(current, self._read_repository(grant, credential))
            branch = self.github.materialize_patch(
                repository=grant.repository_full_name,
                installation_id=grant.github_installation_id,
                base_ref=grant.permitted_base_ref,
                base_commit=current.base_commit,
                base_tree=current.base_tree,
                resulting_tree=current.resulting_tree,
                head_ref=current.head_ref,
                effect_id=current.effect_id,
                patch_bytes=patch_bytes,
                credential=credential,
            )
            self._require_remote_branch(current, branch)
            current = self._current_authorization(authorization_id)
            grant, _, _, _, _ = self._verify_for_apply(current)
            self._require_expected_head(current, self._read_repository(grant, credential))
            pull_request = self.github.open_reviewable_pr(
                repository=grant.repository_full_name,
                installation_id=grant.github_installation_id,
                base_ref=grant.permitted_base_ref,
                head_ref=current.head_ref,
                effect_id=current.effect_id,
                title=f"TinyAssets accepted result {current.accepted_result_sha256[:12]}",
                body=f"TinyAssets-Effect-ID: {current.effect_id}",
                draft=False,
                credential=credential,
            )
            return self._succeed(current, pull_request)
        except EffectRouteError:
            self.authorization_store.mark_needs_reconciliation(authorization_id)
            raise
        except Exception as exc:
            self.authorization_store.mark_needs_reconciliation(authorization_id)
            raise EffectRouteError("needs_reconciliation", str(exc)) from exc

    def _verify_for_apply(
        self, authorization: GitHubEffectAuthorization
    ) -> tuple[
        GitHubOwnerGrant,
        Mapping[str, Any],
        Mapping[str, Any],
        Mapping[str, Any],
        bytes,
    ]:
        now = self._now()
        if authorization.state == "revoked":
            raise EffectRouteError("authorization_revoked")
        if authorization.revoked_at is not None:
            raise EffectRouteError("authorization_revoked")
        if now >= authorization.expires_at:
            raise EffectRouteError("authorization_expired")
        grant = self._active_grant(authorization.grant_id, now)
        if grant.generation != authorization.grant_generation:
            raise EffectRouteError("grant_generation_changed")
        if grant.owner_user_id != authorization.authorized_by:
            raise EffectRouteError("owner_mismatch")

        job, result, patch = self._accepted_result(authorization.job_id)
        if not hmac.compare_digest(
            result["signature"]["result_sha256"],
            authorization.accepted_result_sha256,
        ):
            raise EffectRouteError("accepted_result_mismatch")
        if job.get("lease_fence") != authorization.lease_fence:
            raise EffectRouteError("accepted_result_mismatch", "lease fence changed")
        capsule = self._verified_capsule(job, result)
        self._require_base_binding(capsule, patch)
        if any(
            (
                patch["blob_sha256"] != authorization.patch_blob_sha256,
                patch["base_commit"] != authorization.base_commit,
                patch["base_tree"] != authorization.base_tree,
                patch["resulting_tree"] != authorization.resulting_tree,
            )
        ):
            raise EffectRouteError("accepted_result_mismatch")
        self._approved_review(
            authorization.review_record_id,
            result=result,
            patch=patch,
            expected_repository_head_sha=authorization.expected_repository_head_sha,
        )
        try:
            patch_bytes = self.blob_store.read_verified_bytes(
                blob_ref=patch["blob_ref"],
                owner_user_id=job["owner_user_id"],
                job_id=authorization.job_id,
                lease_id=result.get("lease_id", job.get("lease_id")),
                fence=authorization.lease_fence,
                expected_sha256=patch["blob_sha256"],
                expected_size_bytes=patch["size_bytes"],
            )
        except Exception as exc:
            raise EffectRouteError("artifact_hash_mismatch", str(exc)) from exc
        if not isinstance(patch_bytes, bytes) or not hmac.compare_digest(
            hashlib.sha256(patch_bytes).hexdigest(), patch["blob_sha256"]
        ):
            raise EffectRouteError("artifact_hash_mismatch")
        return grant, job, result, patch, patch_bytes

    def _accepted_result(
        self, job_id: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
        try:
            job = self.job_store.read_result_state(job_id)
        except Exception as exc:
            raise EffectRouteError("accepted_result_missing", str(exc)) from exc
        if job.get("status") != "succeeded":
            raise EffectRouteError("result_not_succeeded")
        accepted = job.get("accepted_result_sha256")
        result = job.get("candidate_result")
        if not isinstance(result, Mapping):
            raise EffectRouteError("accepted_result_missing")
        signature = result.get("signature")
        if not isinstance(signature, Mapping) or signature.get("result_sha256") != accepted:
            raise EffectRouteError("accepted_result_mismatch")
        body = {key: value for key, value in result.items() if key != "signature"}
        if not hmac.compare_digest(hash_canonical_jcs(body).hex(), str(accepted)):
            raise EffectRouteError("accepted_result_mismatch")
        if result.get("outcome") != "succeeded":
            raise EffectRouteError("result_not_succeeded")
        patch = result.get("repo_patch")
        if not isinstance(patch, Mapping) or patch.get("format") != "git-diff-v1":
            raise EffectRouteError("accepted_result_missing", "repo patch missing")
        return job, result, patch

    def _verified_capsule(
        self, job: Mapping[str, Any], result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        capsule_sha256 = job.get("capsule_sha256")
        try:
            capsule = self.capsule_store._load_verified_capsule(
                str(job["job_id"]), str(capsule_sha256)
            )
            payload = capsule["payload"]
            integrity = capsule["integrity"]
        except Exception as exc:
            raise EffectRouteError("base_binding_mismatch", str(exc)) from exc
        if (
            not isinstance(payload, Mapping)
            or not isinstance(integrity, Mapping)
            or integrity.get("capsule_sha256") != capsule_sha256
            or result.get("capsule_sha256", capsule_sha256) != capsule_sha256
            or payload.get("job_id") != job.get("job_id")
            or payload.get("owner_user_id") != job.get("owner_user_id")
        ):
            raise EffectRouteError("base_binding_mismatch")
        lease = payload.get("lease")
        if not isinstance(lease, Mapping) or (
            lease.get("lease_id") != result.get("lease_id", job.get("lease_id"))
            or lease.get("fence") != job.get("lease_fence")
        ):
            raise EffectRouteError("base_binding_mismatch")
        return payload

    @staticmethod
    def _require_base_binding(
        capsule: Mapping[str, Any], patch: Mapping[str, Any]
    ) -> None:
        base = capsule.get("base")
        if not isinstance(base, Mapping) or (
            base.get("commit") != patch.get("base_commit")
            or base.get("tree") != patch.get("base_tree")
        ):
            raise EffectRouteError("base_binding_mismatch")

    def _approved_review(
        self,
        review_record_id: str,
        *,
        result: Mapping[str, Any],
        patch: Mapping[str, Any],
        expected_repository_head_sha: str,
    ) -> ResultReview:
        review = self.review_store.get(review_record_id)
        if review is None:
            raise EffectRouteError("review_missing")
        if review.verdict != "approved" or review.revoked_at is not None:
            raise EffectRouteError("review_not_approved")
        if review.superseded_by is not None:
            raise EffectRouteError("review_superseded")
        executor = result.get("executor")
        if isinstance(executor, Mapping) and review.reviewer_id == executor.get("daemon_id"):
            raise EffectRouteError("review_not_approved", "executing daemon cannot self-review")
        revalidation = result.get("revalidation")
        expected_policy = (
            revalidation.get("verifier_policy_sha256")
            if isinstance(revalidation, Mapping)
            else None
        )
        bindings = (
            (review.accepted_result_sha256, result["signature"]["result_sha256"]),
            (review.patch_blob_sha256, patch.get("blob_sha256")),
            (review.base_commit, patch.get("base_commit")),
            (review.base_tree, patch.get("base_tree")),
            (review.resulting_tree, patch.get("resulting_tree")),
            (review.expected_repository_head_sha, expected_repository_head_sha),
            (review.verifier_policy_sha256, expected_policy),
        )
        if any(left != right for left, right in bindings):
            raise EffectRouteError("review_binding_mismatch")
        return review

    def _active_grant(self, grant_id: str, now: datetime) -> GitHubOwnerGrant:
        grant = self.authorization_store.get_owner_grant(grant_id)
        if grant is None:
            raise EffectRouteError("owner_authorization_missing")
        if grant.revoked_at is not None:
            raise EffectRouteError("authorization_revoked")
        if grant.expires_at is not None and now >= grant.expires_at:
            raise EffectRouteError("authorization_expired")
        if grant.required_head_prefix != "tiny/effects/":
            raise EffectRouteError("head_ref_forbidden")
        if grant.permitted_action != "open_reviewable_pr":
            raise EffectRouteError("target_not_granted")
        return grant

    def _current_authorization(
        self, authorization_id: str
    ) -> GitHubEffectAuthorization:
        current = self.authorization_store.get(authorization_id)
        if current is None:
            raise EffectRouteError("owner_authorization_missing")
        return current

    def _credential(self, grant: GitHubOwnerGrant) -> Any:
        try:
            manager = self.credentials.resolve_bound_credential(
                binding_id=grant.credential_binding_id,
                universe_id=grant.universe_id,
                destination=grant.repository_full_name,
                purpose="external_write",
            )
            return _BoundCredentialContext(manager)
        except Exception as exc:
            raise EffectRouteError("credential_scope_mismatch", str(exc)) from exc

    def _read_repository(
        self, grant: GitHubOwnerGrant, credential: Any
    ) -> RepositorySnapshot:
        try:
            snapshot = self.github.read_repository(
                repository=grant.repository_full_name,
                installation_id=grant.github_installation_id,
                base_ref=grant.permitted_base_ref,
                credential=credential,
            )
        except Exception as exc:
            raise EffectRouteError("github_unreadable", str(exc)) from exc
        if not isinstance(snapshot, RepositorySnapshot):
            raise EffectRouteError("github_unreadable", "invalid repository response")
        return snapshot

    @staticmethod
    def _require_repository_binding(
        grant: GitHubOwnerGrant, snapshot: RepositorySnapshot
    ) -> None:
        if snapshot.repository_node_id != grant.repository_node_id:
            raise EffectRouteError("repository_identity_mismatch")
        if snapshot.installation_id != grant.github_installation_id:
            raise EffectRouteError("repository_identity_mismatch")
        if snapshot.base_ref != grant.permitted_base_ref:
            raise EffectRouteError("base_ref_forbidden")

    @staticmethod
    def _require_expected_head(
        authorization: GitHubEffectAuthorization, snapshot: RepositorySnapshot
    ) -> None:
        if (
            snapshot.head_sha != authorization.expected_repository_head_sha
            or snapshot.base_tree != authorization.base_tree
        ):
            raise EffectRouteError("repository_head_moved")

    @staticmethod
    def _require_remote_branch(
        authorization: GitHubEffectAuthorization, branch: Mapping[str, Any]
    ) -> None:
        if (
            not isinstance(branch, Mapping)
            or branch.get("head_ref") != authorization.head_ref
            or branch.get("effect_id") != authorization.effect_id
            or branch.get("tree_sha") != authorization.resulting_tree
        ):
            raise EffectRouteError("remote_identity_conflict")

    def _reconcile(
        self,
        authorization: GitHubEffectAuthorization,
        grant: GitHubOwnerGrant,
        credential: Any,
    ) -> EffectReceipt:
        try:
            remote = self.github.find_effect(
                repository=grant.repository_full_name,
                installation_id=grant.github_installation_id,
                head_ref=authorization.head_ref,
                effect_id=authorization.effect_id,
                credential=credential,
                include_all_pr_states=True,
            )
            branch = remote.get("branch") if isinstance(remote, Mapping) else None
            pull_request = (
                remote.get("pull_request") if isinstance(remote, Mapping) else None
            )
            if isinstance(pull_request, Mapping):
                self._require_remote_branch(authorization, branch)
                return self._succeed(authorization, pull_request)
            if not isinstance(branch, Mapping):
                raise EffectRouteError(
                    "needs_reconciliation", "deterministic remote branch is absent"
                )
            self._require_remote_branch(authorization, branch)
            self._require_expected_head(
                authorization, self._read_repository(grant, credential)
            )
            pull_request = self.github.open_reviewable_pr(
                repository=grant.repository_full_name,
                installation_id=grant.github_installation_id,
                base_ref=grant.permitted_base_ref,
                head_ref=authorization.head_ref,
                effect_id=authorization.effect_id,
                title=f"TinyAssets accepted result {authorization.accepted_result_sha256[:12]}",
                body=f"TinyAssets-Effect-ID: {authorization.effect_id}",
                draft=False,
                credential=credential,
            )
            return self._succeed(authorization, pull_request)
        except EffectRouteError:
            self.authorization_store.mark_needs_reconciliation(
                authorization.authorization_id
            )
            raise
        except Exception as exc:
            self.authorization_store.mark_needs_reconciliation(
                authorization.authorization_id
            )
            raise EffectRouteError("needs_reconciliation", str(exc)) from exc

    def _succeed(
        self,
        authorization: GitHubEffectAuthorization,
        pull_request: Mapping[str, Any],
    ) -> EffectReceipt:
        if (
            pull_request.get("effect_id") != authorization.effect_id
            or pull_request.get("head_ref") != authorization.head_ref
        ):
            raise EffectRouteError("remote_identity_conflict")
        number = pull_request.get("number")
        url = pull_request.get("url")
        if type(number) is not int or type(url) is not str or not url:
            raise EffectRouteError("github_unreadable", "invalid pull request response")
        return self.authorization_store.succeed(
            authorization.authorization_id,
            pr_number=number,
            pr_url=url,
        )

    @staticmethod
    def _receipt(
        authorization: GitHubEffectAuthorization,
        status: Literal["in_flight", "succeeded"],
    ) -> EffectReceipt:
        return EffectReceipt(
            authorization_id=authorization.authorization_id,
            effect_id=authorization.effect_id,
            status=status,
            head_ref=authorization.head_ref,
            pr_number=authorization.pr_number,
            pr_url=authorization.pr_url,
        )

    def _now(self) -> datetime:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise EffectRouteError("clock_invalid")
        return now.astimezone(UTC)


__all__ = [
    "EffectReceipt",
    "EffectRouteError",
    "GitHubEffectAuthorization",
    "GitHubEffectService",
    "GitHubOwnerGrant",
    "RepositorySnapshot",
    "ResultReview",
    "derive_effect_id",
]
