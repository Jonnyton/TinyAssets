"""Canonical graph-handle adapter for private cloud automations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe
from tinyassets.cloud_automation_control import (
    CloudAutomationControl,
    CloudAutomationDesiredState,
    CloudAutomationTriggerStatus,
    project_cloud_automation_health,
)
from tinyassets.provider_work_authority import (
    ProviderWorkBindingFence,
    ProviderWorkBindingRoot,
    ProviderWorkBindingService,
)
from tinyassets.provider_work_enrollment import (
    RequesterProviderEnrollmentResolver,
    enrollment_action,
)
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore
from tinyassets.storage.cloud_automation_inputs import stage_accepted_spec
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore
from tinyassets.user_owned_cloud_automation import (
    RepositorySpecWorkDefinition,
    acceptance_scenario_digest,
    repository_spec_automation_id,
    repository_spec_baseline_scenario,
)


class _AutomationPrerequisiteError(ValueError):
    def __init__(self, detail: str, prerequisites: dict[str, Any]) -> None:
        super().__init__(detail)
        self.prerequisites = prerequisites


def _not_found() -> dict[str, str]:
    return {"error": "not_found", "resource": "cloud_automation"}


def _actor() -> str | None:
    from tinyassets.api import permissions

    if not permissions.is_authenticated_request():
        return None
    actor = permissions.current_actor_id().strip()
    return actor if actor and actor != "anonymous" else None


def _activation_projection(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    subject = record.subject
    return {
        "epoch": record.epoch,
        "executor_class": (
            record.executor_class.value if record.executor_class is not None else None
        ),
        "subject": (
            {
                "kind": subject.kind.value,
                "ref": subject.ref,
                "digest": subject.digest,
            }
            if subject is not None
            else None
        ),
        "state": record.state.value,
        "updated_at": record.updated_at,
    }


def _control_projection(control: CloudAutomationControl) -> dict[str, Any]:
    return {
        "schema_version": control.schema_version,
        "universe_id": control.universe_id,
        "automation_id": control.automation_id,
        "principal_id": control.principal_id,
        "definition_digest": control.definition_digest,
        "cadence_seconds": control.cadence_seconds,
        "revision": control.revision,
        "desired_state": control.desired_state.value,
        "updated_at": control.updated_at,
    }


def _prerequisite_projection(*, actor: str, universe_id: str) -> dict[str, Any]:
    base = _base_path()
    provider_bindings = []
    for binding in SQLiteProviderWorkAuthorityStore(base).list_bindings(
        owner_user_id=actor,
        universe_id=universe_id,
    ):
        if (
            "repository_spec_delivery" not in binding.allowed_operations
            or "writer" not in binding.allowed_roles
        ):
            continue
        provider_bindings.append(
            {
                "binding_id": binding.binding_id,
                "provider": binding.provider,
                "allowed_operations": list(binding.allowed_operations),
                "allowed_roles": list(binding.allowed_roles),
                "max_invocations": binding.max_invocations,
                "max_tokens": binding.max_tokens,
                "max_cost_microunits": binding.max_cost_microunits,
                "expires_at": binding.expires_at,
            }
        )
    ledger = ConnectionLedger(
        base / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )
    destination_grants = []
    for grant in ledger.list_grants(
        owner_user_id=actor,
        universe_id=universe_id,
    ):
        connection = ledger.get_connection(grant.connection_id)
        if (
            connection is None
            or connection.revoked_at is not None
            or connection.connection_class != "pull-request-writer"
        ):
            continue
        destination_grants.append(
            {
                "grant_id": grant.grant_id,
                "connection_class": connection.connection_class,
                "provider": connection.provider,
                "destination": connection.destination,
                "scopes": list(connection.scopes),
                "action_cap": (
                    grant.unprompted_action_cap.as_dict()
                    if grant.unprompted_action_cap is not None
                    else None
                ),
            }
        )
    return {
        "provider_bindings": provider_bindings,
        "destination_grants": destination_grants,
        "ready": bool(provider_bindings and destination_grants),
        "provider_action": (
            None
            if provider_bindings
            else enrollment_action(owner_user_id=actor, universe_id=universe_id)
        ),
        "connection_action": (
            None
            if destination_grants
            else {
                "target": "connection",
                "operation": "connect",
                "required_fields": ["destination"],
                "next": "authorize GitHub, then reconcile the same destination",
            }
        ),
    }


def _hydrate_server_owned_prerequisites(
    raw_definition: dict[str, Any],
    *,
    actor: str,
    universe_id: str,
) -> dict[str, Any]:
    definition = dict(raw_definition)
    definition["principal_id"] = actor
    definition["universe_id"] = universe_id
    scenario = repository_spec_baseline_scenario()
    definition["acceptance_scenario_id"] = scenario.scenario_id
    definition["acceptance_scenario_digest"] = acceptance_scenario_digest(scenario)
    prerequisites = _prerequisite_projection(actor=actor, universe_id=universe_id)
    if not str(definition.get("provider_binding_id") or "").strip():
        candidates = prerequisites["provider_bindings"]
        if len(candidates) != 1:
            detail = (
                "connect requester-owned compute, then retry "
                "read_graph target=automations"
                if not candidates
                else "select one requester-owned provider binding from "
                "read_graph target=automations"
            )
            raise _AutomationPrerequisiteError(detail, prerequisites)
        definition["provider_binding_id"] = candidates[0]["binding_id"]
    if not str(definition.get("destination_grant_id") or "").strip():
        candidates = prerequisites["destination_grants"]
        if len(candidates) != 1:
            detail = (
                "connect the target repository, then retry "
                "read_graph target=automations"
                if not candidates
                else "select one requester-owned destination grant from "
                "read_graph target=automations"
            )
            raise _AutomationPrerequisiteError(detail, prerequisites)
        definition["destination_grant_id"] = candidates[0]["grant_id"]
    return definition


def _derive_phone_work_definition(
    raw_definition: dict[str, Any],
    *,
    accepted_spec_content: Any,
    actor: str,
    universe_id: str,
) -> dict[str, Any]:
    """Freeze internal authority and digest fields from human phone inputs."""
    authority_assertions = {
        field: raw_definition.get(field)
        for field in ("provider_binding_id", "destination_grant_id")
        if field in raw_definition
    }
    human_definition = {
        field: value
        for field, value in raw_definition.items()
        if field not in authority_assertions
    }
    definition = _hydrate_server_owned_prerequisites(
        human_definition,
        actor=actor,
        universe_id=universe_id,
    )
    repository = str(definition.get("repository") or "").strip()
    accepted_spec_ref = str(definition.get("accepted_spec_ref") or "").strip()
    branch_version_id = str(definition.get("branch_version_id") or "").strip()
    if not repository or not accepted_spec_ref or not branch_version_id:
        raise ValueError(
            "repository, accepted_spec_ref, and branch_version_id are required"
        )
    from tinyassets.branch_versions import get_branch_version

    version = get_branch_version(_base_path(), branch_version_id)
    if version is None:
        raise ValueError("immutable Branch version does not exist")
    if not isinstance(accepted_spec_content, str) or not accepted_spec_content:
        raise ValueError("accepted_spec_content is required for setup")
    accepted_spec_digest = (
        "sha256:"
        + hashlib.sha256(accepted_spec_content.encode("utf-8")).hexdigest()
    )
    provider = SQLiteProviderWorkAuthorityStore(_base_path()).get(
        str(definition["provider_binding_id"])
    )
    if provider is None:
        raise ValueError("requester-owned provider binding is unavailable")
    scenario = repository_spec_baseline_scenario()
    derived = {
        "schema_version": 1,
        "accepted_spec_digest": accepted_spec_digest,
        "branch_def_id": version.branch_def_id,
        "branch_content_digest": f"sha256:{version.content_hash}",
        "acceptance_scenario_id": scenario.scenario_id,
        "acceptance_scenario_digest": acceptance_scenario_digest(scenario),
        "input_artifact_digests": [
            accepted_spec_digest,
            f"sha256:{version.content_hash}",
        ],
        "destination_purpose": "pull_request",
        "max_attempts": 2,
        "max_provider_invocations": min(provider.max_invocations, 64),
        "max_wall_time_seconds": 3600,
        "max_tokens": provider.max_tokens,
        "max_cost_microunits": provider.max_cost_microunits,
        "provider_binding_id": definition["provider_binding_id"],
        "destination_grant_id": definition["destination_grant_id"],
    }
    for field, value in derived.items():
        asserted = (
            authority_assertions[field]
            if field in authority_assertions
            else raw_definition.get(field)
        )
        if field in raw_definition and asserted != value:
            label = field.replace("_", " ")
            raise ValueError(f"{label} assertion does not match server-derived value")
        definition[field] = value
    return definition


def _projection(
    control: CloudAutomationControl,
    *,
    limit: int,
) -> dict[str, Any]:
    from tinyassets.storage.cloud_automation_continuation import (
        SQLiteCloudAutomationContinuationStore,
    )

    base = _base_path()
    controls = CloudAutomationControlStore(base)
    triggers = controls.list_triggers(
        automation_id=control.automation_id,
        limit=max(limit, 100),
    )
    receipts = controls.list_receipts(
        automation_id=control.automation_id,
        limit=max(limit, 100),
    )
    current_trigger = next(
        (
            value
            for value in sorted(
                triggers,
                key=lambda item: (item.activation_epoch, item.slice_ordinal),
                reverse=True,
            )
            if value.status is not CloudAutomationTriggerStatus.EMITTED
        ),
        None,
    )
    latest_receipt = max(
        receipts,
        key=lambda value: (value.activation_epoch, value.slice_ordinal),
        default=None,
    )
    definition = control.definition
    continuation = SQLiteCloudAutomationContinuationStore(base).get(
        universe_id=control.universe_id,
        automation_id=control.automation_id,
    )
    activation = AutomationActivationStore(base).get(
        control.universe_id,
        control.automation_id,
    )
    health = project_cloud_automation_health(
        control,
        activation=activation,
        triggers=triggers,
        receipts=receipts,
        now=datetime.now(timezone.utc),
    )
    return {
        "automation": _control_projection(control),
        "activation": _activation_projection(activation),
        "health": health.to_dict(),
        "definition": definition.to_dict(),
        "baseline_evaluation": control.baseline_evaluation,
        "current_trigger": (
            current_trigger.to_dict() if current_trigger is not None else None
        ),
        "latest_terminal_receipt": (
            latest_receipt.to_dict() if latest_receipt is not None else None
        ),
        "authority": (
            {
                "source": "requester_owned_provider_binding",
                "provider_binding_id": continuation.provider_binding_id,
                "provider_binding_generation": continuation.provider_binding_generation,
                "destination_grant_id": continuation.destination_grant_id,
                "destination": continuation.destination,
            }
            if continuation is not None
            else None
        ),
        "budgets": {
            "max_attempts": definition.max_attempts,
            "max_provider_invocations": definition.max_provider_invocations,
            "max_wall_time_seconds": definition.max_wall_time_seconds,
            "max_tokens": definition.max_tokens,
            "max_cost_microunits": definition.max_cost_microunits,
        },
        "terminal_receipts": [
            value.to_dict()
            for value in sorted(
                receipts,
                key=lambda item: (item.activation_epoch, item.slice_ordinal),
                reverse=True,
            )[:limit]
        ],
    }


def cloud_automations(
    *,
    action: str,
    universe_id: str = "",
    automation_id: str = "",
    expected_revision: int = 0,
    limit: int = 30,
    payload: Any = None,
) -> dict[str, Any]:
    """Inspect or control one authenticated caller-owned cloud automation."""

    normalized = (action or "").strip().lower()
    actor = _actor()
    if actor is None:
        if normalized in {"get", "list"}:
            return _not_found()
        return {"error": "authentication_required", "resource": "cloud_automation"}
    uid = _request_universe(universe_id)
    from tinyassets.api import permissions

    if not permissions.universe_access_allows(uid, write=True):
        return _not_found()
    store = CloudAutomationControlStore(_base_path())

    if normalized in {"bind_provider", "reconcile_provider", "rebind", "rebind_provider"}:
        try:
            document = json.loads(payload) if isinstance(payload, str) else payload
        except (TypeError, ValueError, json.JSONDecodeError):
            return {
                "error": "provider_binding_setup_invalid",
                "detail": "payload_json must be a JSON object",
            }
        if not isinstance(document, dict):
            return {
                "error": "provider_binding_setup_invalid",
                "detail": "payload_json must be a JSON object",
            }
        provider = str(document.get("provider") or "").strip()
        # All authority fields are deliberately ignored; the resolver derives
        # the seed from server-owned enrollment and the authenticated actor.
        if provider not in {"codex", "claude-code"}:
            return {
                "error": "provider_binding_setup_invalid",
                "detail": "provider must be codex or claude-code",
            }
        try:
            resolver = RequesterProviderEnrollmentResolver.from_environment()
            provider_store = SQLiteProviderWorkAuthorityStore(_base_path())
            provider_service = ProviderWorkBindingService(provider_store, resolver)
            root = ProviderWorkBindingRoot(
                owner_user_id=actor,
                universe_id=uid,
                provider=provider,
            )
            if normalized in {"rebind", "rebind_provider"}:
                matching = [
                    item
                    for item in provider_store.list_bindings(
                        owner_user_id=actor,
                        universe_id=uid,
                    )
                    if item.provider == provider
                ]
                if len(matching) > 1:
                    raise PermissionError("ambiguous provider binding")
                if matching:
                    result = provider_service.rebind(
                        ProviderWorkBindingFence(matching[0]), root
                    )
                else:
                    result = provider_service.issue(root)
            else:
                result = provider_service.issue(root)
        except (TypeError, ValueError, PermissionError) as exc:
            return {
                "error": "provider_binding_setup_required",
                "detail": "requester-owned provider enrollment is unavailable",
                "reason": type(exc).__name__,
                "prerequisites": _prerequisite_projection(actor=actor, universe_id=uid),
            }
        binding = result.record
        if binding is None:
            return {
                "error": "provider_binding_setup_required",
                "detail": "provider binding was not issued",
            }
        return {
            "status": "provider_bound",
            "outcome": result.outcome.value,
            "binding": {
                "binding_id": binding.binding_id,
                "generation": binding.generation,
                "state": binding.state.value,
                "provider": binding.provider,
                "allowed_operations": list(binding.allowed_operations),
                "allowed_roles": list(binding.allowed_roles),
                "max_invocations": binding.max_invocations,
                "max_tokens": binding.max_tokens,
                "max_cost_microunits": binding.max_cost_microunits,
                "expires_at": binding.expires_at,
            },
            "next": (
                "create or resume the stopped cloud automation after the exact "
                "GitHub destination is connected"
            ),
        }

    if normalized == "create":
        try:
            from tinyassets.cloud_automation_setup import prepare_cloud_automation

            document = json.loads(payload) if isinstance(payload, str) else payload
            if not isinstance(document, dict):
                raise ValueError("payload_json must be a JSON object")
            raw_definition = document.get("definition")
            if not isinstance(raw_definition, dict):
                raise ValueError("payload_json.definition must be an object")
            server_definition = _derive_phone_work_definition(
                raw_definition,
                accepted_spec_content=document.get("accepted_spec_content"),
                actor=actor,
                universe_id=uid,
            )
            definition = RepositorySpecWorkDefinition.from_dict(server_definition)
            server_automation_id = repository_spec_automation_id(definition)
            if "accepted_spec_content" in document:
                stage_accepted_spec(
                    _base_path(),
                    accepted_spec_ref=definition.accepted_spec_ref,
                    content=document["accepted_spec_content"],
                    expected_digest=definition.accepted_spec_digest,
                )
            operator = document.get("operator")
            if not isinstance(operator, dict):
                operator = {}
            setup = prepare_cloud_automation(
                _base_path(),
                definition,
                automation_id=server_automation_id,
                cadence_seconds=int(document.get("cadence_seconds", 0)),
                operator_display_name=str(operator.get("display_name") or ""),
                operator_soul_text=str(operator.get("soul_text") or ""),
            )
        except _AutomationPrerequisiteError as exc:
            return {
                "error": "automation_setup_required",
                "detail": str(exc),
                "prerequisites": exc.prerequisites,
            }
        except (TypeError, ValueError, PermissionError) as exc:
            return {"error": "automation_setup_invalid", "detail": str(exc)}
        result = _projection(setup.control, limit=limit)
        result.update(
            {
                "status": "activation_requested",
                "daemon_id": setup.daemon_id,
                "continuation_id": setup.continuation_id,
            }
        )
        return result

    if normalized == "list":
        records = [
            _control_projection(value)
            for value in store.list_controls(universe_id=uid, limit=limit)
            if value.principal_id == actor
        ]
        return {
            "universe_id": uid,
            "automations": records,
            "count": len(records),
            "prerequisites": _prerequisite_projection(
                actor=actor,
                universe_id=uid,
            ),
        }

    control = store.get_control(universe_id=uid, automation_id=automation_id)
    if control is None or control.principal_id != actor:
        return _not_found()
    if normalized == "get":
        return _projection(control, limit=limit)

    if normalized == "rebind":
        if expected_revision != control.revision:
            return {
                "error": "automation_revision_conflict",
                "expected_revision": expected_revision,
                "current_revision": control.revision,
            }
        try:
            from tinyassets.cloud_automation_setup import prepare_cloud_automation

            document = json.loads(payload) if isinstance(payload, str) else payload
            if not isinstance(document, dict):
                raise ValueError("payload_json must be a JSON object")
            raw_definition = document.get("definition")
            if not isinstance(raw_definition, dict):
                raise ValueError("payload_json.definition must be an object")
            definition = RepositorySpecWorkDefinition.from_dict(
                _hydrate_server_owned_prerequisites(
                    raw_definition,
                    actor=actor,
                    universe_id=uid,
                )
            )
            if "accepted_spec_content" in document:
                stage_accepted_spec(
                    _base_path(),
                    accepted_spec_ref=definition.accepted_spec_ref,
                    content=document["accepted_spec_content"],
                    expected_digest=definition.accepted_spec_digest,
                )
            setup = prepare_cloud_automation(
                _base_path(),
                definition,
                automation_id=automation_id,
                cadence_seconds=control.cadence_seconds,
                operator_display_name="",
                operator_soul_text="",
                expected_control=control,
            )
        except _AutomationPrerequisiteError as exc:
            return {
                "error": "automation_setup_required",
                "detail": str(exc),
                "prerequisites": exc.prerequisites,
            }
        except (TypeError, ValueError, PermissionError) as exc:
            return {"error": "automation_rebind_invalid", "detail": str(exc)}
        result = _projection(setup.control, limit=limit)
        result.update(
            {
                "status": "activation_requested",
                "daemon_id": setup.daemon_id,
                "continuation_id": setup.continuation_id,
            }
        )
        return result

    desired = {
        "pause": CloudAutomationDesiredState.PAUSED,
        "resume": CloudAutomationDesiredState.ACTIVE,
        "stop": CloudAutomationDesiredState.STOPPED,
    }.get(normalized)
    if desired is None:
        return {
            "error": "unknown_automation_action",
            "action": action,
            "allowed_actions": [
                "create",
                "get",
                "list",
                "pause",
                "rebind",
                "resume",
                "stop",
            ],
        }
    if expected_revision != control.revision:
        return {
            "error": "automation_revision_conflict",
            "expected_revision": expected_revision,
            "current_revision": control.revision,
        }
    try:
        updated = store.set_desired_state(expected=control, desired_state=desired)
    except PermissionError as exc:
        return {"error": "automation_control_conflict", "detail": str(exc)}
    except ValueError as exc:
        return {"error": "automation_transition_invalid", "detail": str(exc)}
    return _projection(updated, limit=limit)


__all__ = ["cloud_automations"]
