"""Authenticated structured delivery through the existing graph action boundary."""

from __future__ import annotations

import json

from tinyassets import delivery_runtime, engine_admissions, runs
from tinyassets.api import receiver_links as management
from tinyassets.branches import BranchDefinition
from tinyassets.storage import deliveries, receiver_links

WRITE_ACTIONS = frozenset({
    "create_receiver", "update_receiver", "revoke_receiver", "connect_output",
    "disconnect_output", "deliver_output",
})
READ_ACTIONS = frozenset({"inspect_receiver", "list_output_links", "get_delivery"})


def _structured_inputs(receiver, link, outputs):
    if not isinstance(outputs, dict):
        raise ValueError("outputs must be an object")
    delivery_runtime.reject_file_references(outputs)
    deliveries._exact_json(outputs)
    mapping = json.loads(link["mapping_json"])
    if set(mapping) - set(outputs):
        raise ValueError("outputs are missing mapped source fields")
    values = {target: outputs[source] for source, target in mapping.items()}
    kinds = {"str": str, "int": int, "float": (float, int), "bool": bool,
             "list": list, "dict": dict}
    for field in json.loads(receiver["contract_json"]):
        kind = field["type"]
        if kind in {"file", "file_bundle"}:
            raise ValueError("delivery_file_transfer_not_implemented")
        if field["name"] not in values:
            if field["required"]:
                raise ValueError("receiver input is required")
            continue
        value = values[field["name"]]
        if kind != "any" and (
            kind not in kinds or not isinstance(value, kinds[kind])
            or (kind in {"int", "float"} and isinstance(value, bool))
        ):
            raise ValueError("receiver input type mismatch")
    branch = BranchDefinition.from_dict(json.loads(receiver["snapshot_json"]))
    runs.preflight_required_inputs(branch, values)
    return values


@management._owner_write
def deliver_output(*, universe_id, link_id, occurrence_id, outputs):
    principal = management._principal(write=True)
    base = management._base()
    # File envelopes and non-exact JSON fail before accepting or reserving a run.
    delivery_runtime.reject_file_references(outputs)
    deliveries._exact_json(outputs)
    with deliveries.transaction(base) as conn:
        link = dict(receiver_links._owned_link(conn, link_id, principal, universe_id))
        source = management._owned_branch(base, universe_id, link["branch_def_id"], principal)
        placement = next((n for n in source.graph_nodes if n.id == link["node_id"]), None)
        definition = next((n for n in source.node_defs if placement
                           and n.node_id == (placement.node_def_id or placement.id)), None)
        if (definition is None
                or set(json.loads(link["mapping_json"])) - set(definition.output_keys)):
            raise ValueError("source output contract changed; reconnect the output")
        prior = conn.execute(
            "SELECT * FROM graph_deliveries WHERE sender_id=? AND sender_universe_id=? "
            "AND link_id=? AND occurrence_id=?",
            (principal, universe_id, link_id, occurrence_id),
        ).fetchone()
        receiver = dict(conn.execute(
            "SELECT * FROM graph_receivers WHERE receiver_id=?", (link["receiver_id"],),
        ).fetchone())
        if prior is None:
            _, receiver = receiver_links.resolve_link_in_transaction(
                conn, link_id=link_id, owner_id=principal, universe_id=universe_id,
            )
            management._owned_branch(
                base, receiver["universe_id"], receiver["branch_def_id"], receiver["owner_id"],
            )
        else:
            # Replay uses the admitted contract/snapshot, not a later revision.
            receiver["snapshot_json"] = prior["snapshot_json"]
            original = json.loads(prior["inputs_json"])
            mapped = {target: outputs[source] for source, target
                      in json.loads(link["mapping_json"]).items() if source in outputs}
            if mapped != original:
                raise deliveries.OccurrenceConflict()
        values = _structured_inputs(receiver, link, outputs) if prior is None else mapped
        ticket = None
        if prior is None:
            admission = engine_admissions.admit_detail(
                receiver["universe_id"], write_max=engine_admissions.RUN_WRITE_LIMIT,
                total_max=engine_admissions.RUN_TOTAL_LIMIT,
                window_s=engine_admissions.RUN_WINDOW_SECONDS, fail_closed=True,
            )
            if admission.ticket is None:
                raise ValueError("receiver_resource_admission_refused")
            ticket = admission.ticket
        receipt = deliveries.accept_in_transaction(
            conn, sender_id=principal, sender_universe_id=universe_id,
            link_id=link_id, occurrence_id=occurrence_id, request_payload=outputs,
            validated_inputs=values,
        )
        private = deliveries.read_receipt_in_transaction(
            conn, delivery_id=receipt["delivery_id"], principal_id=receiver["owner_id"],
            universe_id=receiver["universe_id"],
        )
    if ticket is not None:
        engine_admissions.attach_run(ticket, private["run_id"])
    # Queue only after the authoritative acceptance transaction commits.
    delivery_runtime.dispatch_accepted_delivery(
        base, delivery_id=receipt["delivery_id"], attempt=receipt["attempt"],
    )
    return receipt


def action(action_name, kwargs):
    """Called only by the canonical extensions action/scope dispatcher."""
    try:
        payload = json.loads(kwargs.get("payload_json") or kwargs.get("inputs_json") or "{}")
        if not isinstance(payload, dict) or "universe_id" in payload:
            raise ValueError("payload must be an object without an authority selector")
        uid = kwargs.get("universe_id") or ""
        functions = {
            "create_receiver": management.save_receiver,
            "update_receiver": management.save_receiver,
            "revoke_receiver": management.revoke_receiver,
            "connect_output": management.connect_output,
            "disconnect_output": management.disconnect_output,
            "deliver_output": deliver_output,
        }
        if action_name in functions:
            if action_name == "create_receiver" and payload.get("receiver_id"):
                raise ValueError("create_receiver cannot select an existing receiver")
            if action_name == "update_receiver" and not payload.get("receiver_id"):
                raise ValueError("update_receiver requires receiver_id")
            result = functions[action_name](universe_id=uid, **payload)
        elif action_name == "inspect_receiver":
            result = management.inspect_receiver(**payload)
        else:
            principal = management._principal(write=False)
            base = management._base()
            management._require_admin(base, uid, principal)
            with deliveries.transaction(base) as conn:
                if action_name == "get_delivery":
                    result = deliveries.read_receipt_in_transaction(
                        conn, delivery_id=payload["delivery_id"],
                        principal_id=principal, universe_id=uid,
                    )
                elif action_name == "list_output_links":
                    result = {"links": [dict(row) for row in conn.execute(
                        "SELECT link_id, branch_def_id, node_id, receiver_id, "
                        "receiver_generation, mapping_json, disconnected_at "
                        "FROM graph_output_links WHERE owner_id=? AND universe_id=?",
                        (principal, uid),
                    )]}
                else:
                    raise ValueError("unknown_delivery_action")
        return json.dumps(result, ensure_ascii=False)
    except PermissionError:
        return json.dumps({"error": "receiver_or_link_not_found"})
    except (ValueError, TypeError, KeyError) as exc:
        return json.dumps({"error": "invalid_delivery_request", "detail": str(exc)})
