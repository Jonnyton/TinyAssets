"""Prepare workflow discovery outside admission; authorize it at reservation.

Only owned connection metadata is fetched here. This is advisory preparation,
not a grant: the store reconstructs current member/model authority before arming.
"""

from pathlib import Path


def prepare_work_model_snapshot(*, base_path, universe_id, provider=None):
    from tinyassets.provider_assignment import (
        load_provider_assignment_in_transaction,
        provider_assignment_admission,
    )
    from tinyassets.provider_serving_binding import (
        _current_selected_member_authority,
        resolve_serving_agent_binding,
    )
    from tinyassets.providers.discovery_snapshot import refresh_model_discovery
    from tinyassets.storage.current_home import check_current_home
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    base = Path(base_path)
    universe = base / universe_id
    store = SQLiteProviderWorkAuthorityStore(base)
    with provider_assignment_admission().shared(universe):
        with store.connection() as conn:
            conn.execute("BEGIN")
            assignment = load_provider_assignment_in_transaction(conn, universe_id=universe_id)
            if assignment is None or not assignment.manifest_digest:
                return None
            selected_provider = provider or assignment.provider
            if not selected_provider.startswith("api_key_http:"):
                return None
            check_current_home(conn, assignment.owner_user_id, universe_id)
            agent = resolve_serving_agent_binding(
                base, universe_id=universe_id, owner_user_id=assignment.owner_user_id,
            )
            _current_selected_member_authority(
                conn, store=store, universe_dir=universe, base_path=base,
                universe_id=universe_id, owner_user_id=assignment.owner_user_id,
                agent=agent, provider=selected_provider,
            )
    # Deliberately outside BOTH the assignment fence and every SQL transaction.
    return refresh_model_discovery(
        owner_user_id=assignment.owner_user_id, universe_id=universe_id,
        definition_id=selected_provider.removeprefix("api_key_http:"),
    )


def selected_work_model(selection):
    """Reconstruct data covered by the carrier seal; this grants nothing alone."""
    from tinyassets.providers.discovery_contract import SourceContract
    from tinyassets.providers.discovery_protocols import discovery_protocol
    from tinyassets.providers.model_selection import SelectedModel

    if selection is None:
        return None
    evidence = selection.model_evidence()
    if evidence is None:
        return None
    contract = evidence["execution_contract"]
    compiled = (SourceContract.compile(contract["value"]) if contract["kind"] == "configured"
                else discovery_protocol(contract["value"]))
    return SelectedModel(
        selection.provider, selection.model_id, evidence["discovery_protocol"],
        tuple(sorted(evidence["cost_caps"].items())), evidence["source_digest"],
        evidence["context_tokens"], evidence["supports_tools"], compiled,
    )


def selection_with_model(selection, model, snapshot):
    """Persist the exact validated model and discovery interval, without callbacks."""
    import json
    from dataclasses import replace

    from tinyassets.providers.discovery_contract import SourceContract

    contract = model.contract()
    evidence = {
        "discovery_protocol": model.discovery_protocol,
        "source_digest": model.source_digest,
        "context_tokens": model.context_tokens,
        "supports_tools": model.supports_tools,
        "cost_caps": dict(model.cost_caps),
        "execution_contract": (
            {"kind": "configured", "value": json.loads(contract.descriptor_json)}
            if isinstance(contract, SourceContract)
            else {"kind": "installed", "value": model.discovery_protocol}
        ),
        "observed_at": snapshot.observed_at.isoformat().replace("+00:00", "Z"),
        "completed_at": snapshot.completed_at.isoformat().replace("+00:00", "Z"),
    }
    return replace(
        selection, model_id=model.model_id, executor_id=contract.inference_protocol,
        model_evidence_json=json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ),
    )


def bound_work_model_tokens(selection, max_tokens, max_cost_microunits):
    """Reserve a finite affordable output before arming a selected HTTP call."""
    model = selected_work_model(selection)
    if model is None:
        return max_tokens
    affordable = model.affordable_output(max_cost_microunits, output_limit=max_tokens)
    limit = max_tokens if affordable is None else min(max_tokens, affordable)
    if limit < 1:
        raise PermissionError("selected model exceeds the workflow cost allowance")
    return limit
