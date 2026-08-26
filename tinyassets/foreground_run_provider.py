"""Server-owned provider authority for authenticated foreground Branch runs."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterator

from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkReceipt,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkExecutionClaim,
)

RUN_GRAPH_OPERATION = "run_graph"
_SUPPORTED_ROLES = frozenset({"writer", "judge"})
_HELD = (
    "Connect your provider before running this universe. TinyAssets will not "
    "borrow platform credentials or start a metered trial."
)


def _content_digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prompt_nodes(snapshot: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = snapshot.get("node_defs", [])
    nodes = raw.values() if isinstance(raw, dict) else raw
    if not isinstance(nodes, (list, tuple)) and not hasattr(nodes, "__iter__"):
        raise PermissionError("immutable Branch node definitions are invalid")
    return tuple(
        node
        for node in nodes
        if isinstance(node, dict) and bool(str(node.get("prompt_template") or "").strip())
    )


def _declared_policy_providers(policy: dict[str, Any] | None) -> set[str]:
    providers: set[str] = set()
    if not policy:
        return providers
    for value in policy.values():
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            use = entry.get("use") if isinstance(entry, dict) else None
            candidate = use if isinstance(use, dict) else entry
            if isinstance(candidate, dict) and candidate.get("provider"):
                providers.add(str(candidate["provider"]).strip())
    return {provider for provider in providers if provider}


class _SeedResolver:
    def __init__(self, seed: ProviderWorkBindingSeed) -> None:
        self.seed = seed

    def resolve(self, root: ProviderWorkBindingRoot) -> ProviderWorkBindingSeed | None:
        return self.seed if self._matches(root) else None

    def resolve_current_in_transaction(
        self,
        _connection: object,
        root: ProviderWorkBindingRoot,
    ) -> ProviderWorkBindingSeed | None:
        return self.resolve(root)

    def _matches(self, root: ProviderWorkBindingRoot) -> bool:
        return (
            root.owner_user_id == self.seed.owner_user_id
            and root.universe_id == self.seed.universe_id
            and root.provider == self.seed.provider
        )


class _ForegroundRunProviderSession:
    def __init__(
        self,
        base_path: str | Path,
        *,
        universe_id: str,
        principal_id: str,
        provider_call: Callable[..., str],
    ) -> None:
        self._base_path = Path(base_path)
        self._universe_id = universe_id.strip()
        self._universe_dir = self._base_path / self._universe_id
        self._principal_id = principal_id.strip()
        self._provider_call = provider_call
        self._run_id = ""
        self._branch_def_id = ""
        self._branch_version_id = ""
        self._branch_digest = ""
        self._branch_snapshot: dict[str, Any] | None = None
        self._provider = ""
        self._receipt: ProviderUniverseWorkReceipt | None = None
        self._claim: ProviderWorkExecutionClaim | None = None
        self._call_index = 0
        self._lock = threading.Lock()
        self._closed = False

    def _validate_founder_home(self) -> None:
        from tinyassets.daemon_server import get_founder_home

        if (
            not self._principal_id
            or self._principal_id == "anonymous"
            or not self._universe_id
            or get_founder_home(self._base_path, self._principal_id) != self._universe_id
        ):
            raise PermissionError("foreground run is not the principal's own universe")

    def _run_record(self) -> dict[str, Any]:
        from tinyassets.runs import get_run

        record = get_run(self._base_path, self._run_id)
        if record is None:
            raise PermissionError("foreground run record is missing")
        return record

    def _validate_run(self, *, allowed_statuses: set[str]) -> None:
        from tinyassets.runs import is_cancel_requested

        record = self._run_record()
        exact = (
            record.get("status") in allowed_statuses,
            record.get("actor") == f"universe:{self._universe_id}",
            record.get("branch_def_id") == self._branch_def_id,
            (record.get("branch_version_id") or "") == self._branch_version_id,
            not is_cancel_requested(self._base_path, self._run_id),
        )
        if not all(exact):
            raise PermissionError("foreground run state or immutable subject changed")

    def admit(
        self,
        *,
        run_id: str,
        branch: Any,
        branch_version_id: str | None,
        allowed_statuses: set[str],
    ) -> None:
        from tinyassets.exceptions import ProviderAuthorityHeldError
        from tinyassets.provider_assignment import provider_assignment_admission
        from tinyassets.provider_serving_binding import (
            _current_serving_authority,
            _is_open_provider,
            resolve_serving_agent_binding,
        )
        from tinyassets.storage.provider_work_authority import (
            SQLiteProviderWorkAuthorityStore,
        )

        if self._run_id:
            raise ProviderAuthorityHeldError(_HELD)
        try:
            self._validate_founder_home()
            snapshot = branch.to_dict()
            branch_author = str(snapshot.get("author") or "").strip()
            if branch_author != self._principal_id:
                raise PermissionError("foreground Branch author is not the principal")
            branch_def_id = str(snapshot.get("branch_def_id") or "").strip()
            if not branch_def_id:
                raise PermissionError("foreground Branch identity is missing")
            nodes = _prompt_nodes(snapshot)
            roles = tuple(
                sorted(
                    {
                        str(node.get("model_hint") or "writer").strip() or "writer"
                        for node in nodes
                    }
                )
            )
            if not set(roles).issubset(_SUPPORTED_ROLES):
                raise PermissionError("foreground Branch requests an unsupported role")

            self._run_id = run_id.strip()
            self._branch_def_id = branch_def_id
            self._branch_version_id = str(branch_version_id or "").strip()
            self._branch_snapshot = snapshot
            self._branch_digest = _content_digest(snapshot)
            self._validate_run(allowed_statuses=allowed_statuses)
            if not nodes:
                return

            agent = resolve_serving_agent_binding(
                self._base_path,
                universe_id=self._universe_id,
                owner_user_id=self._principal_id,
            )
            store = SQLiteProviderWorkAuthorityStore(self._base_path)
            with provider_assignment_admission().shared(self._universe_dir):
                with store.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        assignment, parent_binding, _custody = _current_serving_authority(
                            conn,
                            store=store,
                            universe_dir=self._universe_dir,
                            owner_user_id=self._principal_id,
                            universe_id=self._universe_id,
                            agent=agent,
                        )
                        if _is_open_provider(assignment.provider):
                            raise PermissionError(
                                "foreground run LLM authority requires a subscription provider"
                            )
                        declared = set().union(
                            *(
                                _declared_policy_providers(node.get("llm_policy"))
                                for node in nodes
                            )
                        )
                        if declared - {assignment.provider}:
                            raise PermissionError(
                                "foreground Branch policy is outside the active provider"
                            )
                        if (
                            len(nodes) > parent_binding.max_invocations
                            or not set(roles).issubset(parent_binding.allowed_roles)
                            or parent_binding.max_tokens < 1
                            or parent_binding.max_cost_microunits < 1
                        ):
                            raise PermissionError(
                                "foreground Branch exceeds active serving authority"
                            )
                        seed = ProviderWorkBindingSeed(
                            owner_user_id=self._principal_id,
                            universe_id=self._universe_id,
                            provider=assignment.provider,
                            credential_reference_digest=(
                                parent_binding.credential_reference_digest
                            ),
                            allowed_operations=(RUN_GRAPH_OPERATION,),
                            allowed_roles=parent_binding.allowed_roles,
                            assignment_generation=assignment.generation,
                            assignment_digest=assignment.assignment_digest,
                            max_invocations=parent_binding.max_invocations,
                            max_tokens=parent_binding.max_tokens,
                            max_cost_microunits=parent_binding.max_cost_microunits,
                            expires_at=parent_binding.expires_at,
                        )
                        root = ProviderWorkBindingRoot(
                            owner_user_id=seed.owner_user_id,
                            universe_id=seed.universe_id,
                            provider=seed.provider,
                        )
                        issued = ProviderWorkBindingService(
                            store,
                            _SeedResolver(seed),
                        ).issue_in_transaction(conn, root)
                        if (
                            issued.outcome
                            not in {
                                ProviderWorkAuthorityWriteOutcome.APPLIED,
                                ProviderWorkAuthorityWriteOutcome.REPLAYED,
                            }
                            or issued.record is None
                        ):
                            raise PermissionError("run child provider binding is unavailable")
                        child_binding = issued.record
                        subject_ref = self._branch_version_id or (
                            f"{self._branch_def_id}@definition:"
                            f"{int(snapshot.get('version') or 1)}"
                        )
                        authority = ProviderUniverseWorkAuthority(
                            root=ProviderUniverseWorkRoot(
                                work_item_kind="run",
                                work_item_id=self._run_id,
                            ),
                            binding=child_binding,
                            principal_id=self._principal_id,
                            actor_id=f"universe:{self._universe_id}",
                            operation=RUN_GRAPH_OPERATION,
                            role=roles[0],
                            allowed_roles=roles,
                            executor_class="cloud",
                            max_invocations=len(nodes),
                            max_tokens=child_binding.max_tokens,
                            max_cost_microunits=child_binding.max_cost_microunits,
                            expires_at=child_binding.expires_at,
                            execution_subject=ExecutionSubject(
                                kind=ExecutionSubjectKind.BRANCH_VERSION,
                                ref=subject_ref,
                                digest=self._branch_digest,
                            ),
                            branch_def_id=self._branch_def_id,
                            branch_version_id=subject_ref,
                            parent_binding_id=parent_binding.binding_id,
                            parent_binding_generation=parent_binding.generation,
                            parent_binding_digest=parent_binding.binding_digest,
                            parent_binding_revocation_generation=(
                                parent_binding.revocation_generation
                            ),
                        )
                        nonce = _content_digest(
                            [
                                self._run_id,
                                self._principal_id,
                                self._universe_id,
                                self._branch_digest,
                                os.getpid(),
                            ]
                        )
                        receipt, claim = store._admit_run_in_transaction(
                            conn,
                            authority=authority,
                            worker_id=f"foreground-run:{os.getpid()}",
                            runtime_id=f"run:{self._run_id}",
                            claim_nonce_digest=nonce,
                            lease_seconds=3600,
                        )
                        self._validate_run(allowed_statuses=allowed_statuses)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
            self._provider = assignment.provider
            self._receipt = receipt
            self._claim = claim
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            raise ProviderAuthorityHeldError(_HELD) from exc

    def _validate_receipt_parent(self, parent_binding: Any, assignment: Any) -> None:
        receipt = self._receipt
        if receipt is None:
            raise PermissionError("foreground run receipt is unavailable")
        exact = (
            receipt.principal_id == self._principal_id,
            receipt.actor_id == f"universe:{self._universe_id}",
            receipt.universe_id == self._universe_id,
            receipt.work_item_id == self._run_id,
            receipt.branch_def_id == self._branch_def_id,
            receipt.execution_subject is not None,
            receipt.execution_subject is not None
            and receipt.execution_subject.digest == self._branch_digest,
            receipt.provider == assignment.provider == self._provider,
            receipt.assignment_generation == assignment.generation,
            receipt.assignment_digest == assignment.assignment_digest,
            receipt.credential_reference_digest
            == assignment.credential_reference_digest,
            receipt.parent_binding_id == parent_binding.binding_id,
            receipt.parent_binding_generation == parent_binding.generation,
            receipt.parent_binding_digest == parent_binding.binding_digest,
            receipt.parent_binding_revocation_generation
            == parent_binding.revocation_generation,
        )
        if not all(exact):
            raise PermissionError("foreground run provider authority is stale")

    @contextmanager
    def _authorize_attempt(
        self,
        *,
        role: str,
        prompt: str,
        system: str,
        policy: dict[str, Any] | None,
    ) -> Iterator[tuple[ProviderInvocationCarrier, Path | None, str]]:
        from tinyassets.credential_vault import (
            cleanup_llm_credential_snapshot,
            snapshot_llm_subscription_credential,
        )
        from tinyassets.exceptions import ProviderAuthorityHeldError
        from tinyassets.provider_assignment import provider_assignment_admission
        from tinyassets.provider_serving_binding import (
            _current_serving_authority,
            _is_open_provider,
            resolve_serving_agent_binding,
        )
        from tinyassets.storage.provider_work_authority import (
            SQLiteProviderWorkAuthorityStore,
        )

        snapshot = None
        carrier = None
        try:
            if self._closed or self._receipt is None or self._claim is None:
                raise PermissionError("foreground run provider session is not active")
            if role not in self._receipt.allowed_roles:
                raise PermissionError("foreground run provider role is not authorized")
            if _declared_policy_providers(policy) - {self._provider}:
                raise PermissionError("foreground policy is outside the active provider")
            self._validate_founder_home()
            if self._branch_snapshot is None or (
                _content_digest(self._branch_snapshot) != self._branch_digest
            ):
                raise PermissionError("foreground immutable Branch subject changed")
            self._validate_run(allowed_statuses={"running"})
            with self._lock:
                self._call_index += 1
                invocation_index = self._call_index
            prompt_digest = _content_digest([role, prompt, system])
            invocation_key = (
                f"run:{self._run_id}:{invocation_index}:{prompt_digest.removeprefix('sha256:')}"
            )
            agent = resolve_serving_agent_binding(
                self._base_path,
                universe_id=self._universe_id,
                owner_user_id=self._principal_id,
            )
            store = SQLiteProviderWorkAuthorityStore(self._base_path)
            with provider_assignment_admission().shared(self._universe_dir):
                with store.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        assignment, parent_binding, custody = _current_serving_authority(
                            conn,
                            store=store,
                            universe_dir=self._universe_dir,
                            owner_user_id=self._principal_id,
                            universe_id=self._universe_id,
                            agent=agent,
                        )
                        self._validate_receipt_parent(parent_binding, assignment)
                        token_share = max(
                            1,
                            self._receipt.max_tokens // self._receipt.max_invocations,
                        )
                        cost_share = max(
                            1,
                            self._receipt.max_cost_microunits
                            // self._receipt.max_invocations,
                        )
                        carrier = store._reserve_and_arm_run_carrier_in_transaction(
                            conn,
                            receipt=self._receipt,
                            claim=self._claim,
                            invocation_key=invocation_key,
                            role=role,
                            max_tokens=token_share,
                            max_cost_microunits=cost_share,
                        )
                        if not _is_open_provider(assignment.provider):
                            snapshot = snapshot_llm_subscription_credential(
                                universe_dir=self._universe_dir,
                                custody=custody,
                            )
                        self._validate_run(allowed_statuses={"running"})
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
            yield (
                carrier,
                snapshot.directory if snapshot is not None else None,
                assignment.provider,
            )
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            if carrier is not None:
                raise
            raise ProviderAuthorityHeldError(_HELD) from exc
        finally:
            cleanup_llm_credential_snapshot(snapshot)

    def _call(
        self,
        role: str,
        prompt: str,
        system: str,
        config: Any,
        policy: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> tuple[str, str]:
        supplied_operation = kwargs.pop("operation", RUN_GRAPH_OPERATION)
        supplied_context = kwargs.pop("universe_context", None)
        if supplied_operation != RUN_GRAPH_OPERATION:
            raise PermissionError("foreground provider operation cannot be substituted")
        if supplied_context is not None and (
            Path(supplied_context.universe_dir) != self._universe_dir
        ):
            raise PermissionError("foreground provider universe cannot be substituted")
        with self._authorize_attempt(
            role=role,
            prompt=prompt,
            system=system,
            policy=policy,
        ) as (carrier, snapshot_dir, provider):
            from tinyassets.config import load_universe_config
            from tinyassets.providers.base import ModelConfig, UniverseContext

            call_config = config
            if snapshot_dir is not None:
                if call_config is None:
                    call_config = ModelConfig()
                if not isinstance(call_config, ModelConfig):
                    raise TypeError("foreground provider config must be a ModelConfig")
                call_config = replace(
                    call_config,
                    credential_snapshot_dir=snapshot_dir,
                )
            result = self._provider_call(
                prompt,
                system,
                role=role,
                config=call_config,
                operation=RUN_GRAPH_OPERATION,
                universe_context=UniverseContext(
                    universe_dir=self._universe_dir,
                    config=load_universe_config(self._universe_dir),
                    provider_invocation=carrier,
                ),
                **kwargs,
            )
            return result, provider

    def __call__(
        self,
        prompt: str,
        system: str = "",
        *,
        role: str = "writer",
        **kwargs: Any,
    ) -> str:
        config = kwargs.pop("config", None)
        policy = kwargs.pop("policy", None)
        response, _provider = self._call(role, prompt, system, config, policy, kwargs)
        return response

    def call_with_policy_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict[str, Any] | None,
        config: Any = None,
        difficulty: str = "",
        **kwargs: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        del difficulty
        response, provider = self._call(role, prompt, system, config, policy, kwargs)
        return response, provider, {"authority": RUN_GRAPH_OPERATION, "attempts": 1}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receipt is not None:
            from tinyassets.storage.provider_work_authority import (
                SQLiteProviderWorkAuthorityStore,
            )

            SQLiteProviderWorkAuthorityStore(self._base_path).release_run_claim(
                self._receipt.receipt_id
            )


def new_foreground_run_provider_session(
    base_path: str | Path,
    *,
    universe_id: str,
    principal_id: str,
    provider_call: Callable[..., str],
) -> _ForegroundRunProviderSession:
    return _ForegroundRunProviderSession(
        base_path,
        universe_id=universe_id,
        principal_id=principal_id,
        provider_call=provider_call,
    )


def _session_from_provider_call(provider_call: Any) -> _ForegroundRunProviderSession | None:
    candidate = getattr(provider_call, "provider_call", None)
    return candidate if type(candidate) is _ForegroundRunProviderSession else None


def admit_foreground_run_provider(
    provider_call: Any,
    *,
    run_id: str,
    branch: Any,
    branch_version_id: str | None,
    allowed_statuses: set[str],
) -> Any:
    session = _session_from_provider_call(provider_call)
    if session is not None:
        session.admit(
            run_id=run_id,
            branch=branch,
            branch_version_id=branch_version_id,
            allowed_statuses=allowed_statuses,
        )
    return provider_call


def close_foreground_run_provider(provider_call: Any) -> None:
    session = _session_from_provider_call(provider_call)
    if session is not None:
        session.close()


__all__ = [
    "RUN_GRAPH_OPERATION",
    "admit_foreground_run_provider",
    "close_foreground_run_provider",
    "new_foreground_run_provider_session",
]
