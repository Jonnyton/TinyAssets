"""Authenticated structured delivery through the existing graph action boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from tinyassets import delivery_runtime, engine_admissions, runs
from tinyassets.api import receiver_links as management
from tinyassets.branches import BranchDefinition
from tinyassets.storage import deliveries, receiver_links

WRITE_ACTIONS = frozenset({
    "create_receiver", "update_receiver", "revoke_receiver", "connect_output",
    "disconnect_output", "deliver_output",
})
READ_ACTIONS = frozenset({"inspect_receiver", "list_output_links", "get_delivery"})


@dataclass(frozen=True)
class NodeDeliverySource:
    """Parent-only compiled placement and persisted run authority; never RPC data."""

    owner_user_id: str
    universe_id: str
    actor: str
    run_id: str
    branch_def_id: str
    node_id: str
    output_keys: tuple[str, ...]


def node_occurrence_id(source, link_id, occurrence_id):
    """Reuse canonical effect identity; content belongs only in the replay digest."""
    from tinyassets.idempotency import derive_effect_key

    receiver_links._name(occurrence_id)
    receiver_links._name(link_id)
    return derive_effect_key(
        goal_id=deliveries._exact_json([
            "node-delivery-v1", source.owner_user_id, source.universe_id, link_id,
        ]),
        schedule_period=source.run_id,
        item_fingerprint=hashlib.sha256(deliveries._exact_json({
            "placement_id": source.node_id, "occurrence_id": occurrence_id,
        }).encode("utf-8")).hexdigest(),
    )


def deliver_node_output(base, *, source, link_id, occurrence_id, outputs, should_cancel):
    """Trusted parent entry. No request identity or caller authority selectors."""
    if should_cancel():
        raise ValueError("delivery_source_cancelled")
    if not isinstance(source, NodeDeliverySource) or not all((
        source.owner_user_id, source.universe_id, source.actor, source.run_id,
        source.branch_def_id, source.node_id,
    )):
        raise PermissionError("delivery_source_unavailable")
    return _accept_output(
        base, principal=source.owner_user_id, universe_id=source.universe_id,
        link_id=link_id, occurrence_id=node_occurrence_id(source, link_id, occurrence_id),
        outputs=outputs, source=source, should_cancel=should_cancel,
    )


def _check_source(conn, source, link):
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (source.run_id,)).fetchone()
    if (row is None or row["status"] != "running"
            or row["owner_user_id"] != source.owner_user_id
            or row["actor"] != source.actor or row["queue_universe_id"] != source.universe_id
            or row["branch_def_id"] != source.branch_def_id
            or link["branch_def_id"] != source.branch_def_id or link["node_id"] != source.node_id
            or set(json.loads(link["mapping_json"])) - set(source.output_keys)):
        raise PermissionError("delivery_source_unavailable")


FILE_KINDS = frozenset({"file", "file_bundle"})


def _declared_files(branch):
    """File inputs the RECEIVER's own branch declares -- the only consent there is.

    A receiver contract reports its ``state_schema`` type, which ``io_manifest``
    requires to be dict/list for a file input, so the contract type alone can
    never name a file field. The manifest declaration is authoritative; the
    contract is only cross-checked against it below.
    """
    manifest = branch.to_dict().get("io_manifest") or {}
    inputs = manifest.get("inputs") or []
    if not any(isinstance(item, dict) and item.get("io_type") in FILE_KINDS
               for item in inputs):
        return {}
    from tinyassets.run_file_binding import file_declarations

    return {item.name: item.io_type for item in file_declarations(branch).inputs if item.is_file}


def _file_fields(receiver, values, branch):
    """Declared file fields actually present, in stable name order."""
    declared = _declared_files(branch)
    present = {}
    undeclared = []
    for field in json.loads(receiver["contract_json"]):
        name = field["name"]
        if field["type"] in FILE_KINDS and name not in declared:
            undeclared.append(name)
        if name not in declared:
            continue
        if name not in values:
            if field["required"]:
                raise ValueError("receiver input is required")
            continue
        present[name] = declared[name]
    if undeclared:
        raise ValueError(
            "receiver branch declares no file input for " + ", ".join(sorted(undeclared))
        )
    return present


def _declared_file_limits(branch, values, file_fields):
    """Limits come from the RECEIVER's own branch declaration, never the contract.

    ``declared_file_inputs`` already validates min/max count, max bytes and media
    types against ``io_manifest``; a contract file field the receiver's branch does
    not declare has no consent behind it and is refused. No per-user quota exists
    or is introduced: retained-byte ceilings stay the operational subsystem ones.
    """
    from tinyassets.authoring.models import ManifestViolation
    from tinyassets.run_file_binding import file_declarations
    from tinyassets.run_file_contract import declared_file_inputs

    try:
        resolved = declared_file_inputs(file_declarations(branch), values, branch.state_schema)
    except ManifestViolation as exc:
        raise ValueError(f"receiver_file_declaration_refused: {exc}") from exc
    missing = sorted(set(file_fields) - set(resolved))
    if missing:
        raise ValueError("receiver branch declares no file input for " + ", ".join(missing))
    return resolved


def _structured_inputs(receiver, link, outputs, *, allow_files=False):
    if not isinstance(outputs, dict):
        raise ValueError("outputs must be an object")
    delivery_runtime.validate_output_envelopes(outputs, allow_file_references=allow_files)
    deliveries._exact_json(outputs)
    mapping = json.loads(link["mapping_json"])
    if set(mapping) - set(outputs):
        raise ValueError("outputs are missing mapped source fields")
    values = {target: outputs[source] for source, target in mapping.items()}
    kinds = {"str": str, "int": int, "float": (float, int), "bool": bool,
             "list": list, "dict": dict}
    branch = BranchDefinition.from_dict(json.loads(receiver["snapshot_json"]))
    file_fields = _file_fields(receiver, values, branch)
    if file_fields and not allow_files:
        raise ValueError("delivery_file_transfer_not_implemented")
    for field in json.loads(receiver["contract_json"]):
        kind = field["type"]
        if kind in FILE_KINDS or field["name"] in file_fields:
            continue
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
    if file_fields:
        _declared_file_limits(branch, values, file_fields)
    runs.preflight_required_inputs(branch, values)
    return values


def deliver_output(*, universe_id, link_id, occurrence_id, outputs):
    principal = management._principal(write=True)
    base = management._base()
    return _accept_output(base, principal=principal, universe_id=universe_id,
                          link_id=link_id, occurrence_id=occurrence_id, outputs=outputs)


def _envelope_records(values, file_fields):
    """Flatten declared file positions into stable (field, ordinal) order."""
    records = []
    for field in sorted(file_fields):
        value = values[field]
        items = value if file_fields[field] == "file_bundle" else [value]
        if not isinstance(items, list) or not items:
            raise ValueError("receiver file input type mismatch")
        for ordinal, reference in enumerate(items):
            if not delivery_runtime.is_file_reference(reference):
                raise ValueError("receiver file input type mismatch")
            records.append({"field_name": field, "ordinal": ordinal, "reference": reference})
    return records


def _accepted_transfer(conn, delivery_id):
    """An already-accepted occurrence keeps its custody rows; no second copy."""
    rows = conn.execute(
        "SELECT * FROM graph_delivery_files WHERE delivery_id=? ORDER BY field_name, ordinal",
        (delivery_id,),
    ).fetchall()
    if not rows:
        return None
    return {"replay": True, "records": [
        {"field_name": row["field_name"], "ordinal": row["ordinal"],
         "sender_file_id": row["sender_file_id"], "receiver_file_id": row["receiver_file_id"],
         "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
        for row in rows
    ]}


def _transfer_files(base, *, principal, universe_id, link_id, occurrence_id, outputs, source,
                    should_cancel):
    """Phase A (read-only) then Phase B (copy), both ABOVE the acceptance fences.

    Acceptance holds the platform and runs writers together; a copy underneath
    them would open a second writer on both from the same thread. Copying first
    also means the receiver already owns its bytes before it is told yes, so a
    sender release right after acceptance cannot orphan an accepted delivery.
    """
    from tinyassets import run_file_crossowner

    with (
        management._owner_authority(base, universe_id, principal),
        deliveries.transaction(base) as conn,
    ):
        link = dict(receiver_links._owned_link(conn, link_id, principal, universe_id))
        _check_source(conn, source, link)
        receiver = dict(conn.execute(
            "SELECT * FROM graph_receivers WHERE receiver_id=?", (link["receiver_id"],),
        ).fetchone())
        mapping = json.loads(link["mapping_json"])
        prior = conn.execute(
            "SELECT * FROM graph_deliveries WHERE sender_id=? AND sender_universe_id=? "
            "AND link_id=? AND occurrence_id=?",
            (principal, universe_id, link_id, occurrence_id),
        ).fetchone()
        if prior is not None:
            # Mirrors the authoritative replay branch structure so a changed replay
            # is refused before any reservation, allocation or byte is moved.
            mapped = {target: outputs[field] for field, target in mapping.items()
                      if field in outputs}
            if mapped != json.loads(prior["inputs_json"]):
                raise deliveries.OccurrenceConflict()
            return _accepted_transfer(conn, prior["delivery_id"])
        _, resolved = receiver_links.resolve_link_in_transaction(
            conn, link_id=link_id, owner_id=principal, universe_id=universe_id,
        )
        receiver = dict(resolved)
        values = {target: outputs[field] for field, target in mapping.items()}
        branch = BranchDefinition.from_dict(json.loads(receiver["snapshot_json"]))
        file_fields = _file_fields(receiver, values, branch)
        if not file_fields:
            return None
        _declared_file_limits(branch, values, file_fields)
        records = _envelope_records(values, file_fields)
        # Read-only: every envelope must resolve under the trusted source run.
        for record in records:
            run_file_crossowner.resolve_bound_source(conn, source, record["reference"])
    try:
        copies = run_file_crossowner.copy_owned_custody_file(
            base, source=source, receiver_owner_id=receiver["owner_id"],
            receiver_universe_id=receiver["universe_id"], link_id=link_id,
            occurrence_id=occurrence_id,
            references=[record["reference"] for record in records],
            should_cancel=lambda: bool(should_cancel()),
        )
    except run_file_crossowner.store.FileCustodyRefused as exc:
        # The operation id is keyed on the occurrence alone, so a replay citing
        # different sender files re-enters the SAME operation with a different
        # request digest and conflicts before capacity, metadata or reservation.
        if str(exc) == "file_operation_conflict":
            raise deliveries.OccurrenceConflict() from exc
        raise
    if len(copies) != len(records):
        raise RuntimeError("cross-owner custody copy returned an unexpected bundle")
    return {"replay": False, "kinds": dict(file_fields), "records": [
        {"field_name": record["field_name"], "ordinal": record["ordinal"],
         "sender_file_id": record["reference"]["file_id"],
         "receiver_file_id": copy["file_id"], "sha256": copy["sha256"],
         "size_bytes": copy["size_bytes"], "reference": copy,
         # Kept so final acceptance can freshly resolve the SENDER envelope in
         # its own transaction; never persisted and never shown to the receiver.
         "source_reference": record["reference"]}
        for record, copy in zip(records, copies)
    ]}


def _revalidate_source_bindings(conn, source, transfer):
    """Acceptance re-resolves the sender bindings before the delivery exists.

    The copy runs above every acceptance fence, so a sender release, rebind or
    metadata change between the copy and this transaction would otherwise be
    accepted. Only a FIRST acceptance re-resolves: an accepted replay keeps its
    admitted custody rows and must never re-check, re-copy or re-bind.
    """
    from tinyassets import run_file_crossowner

    rows = run_file_crossowner.assert_bound_sources(
        conn, source, [record["source_reference"] for record in transfer["records"]],
    )
    for row, record in zip(rows, transfer["records"]):
        if (row["sha256"], row["size_bytes"]) != (record["sha256"], record["size_bytes"]):
            raise run_file_crossowner.store.FileCustodyRefused("file_source_changed")


def _accept_output(base, *, principal, universe_id, link_id, occurrence_id, outputs,
                   source=None, should_cancel=lambda: False):
    # Non-exact JSON fails before accepting or reserving a run. Without a trusted
    # source run there is nothing to resolve a file reference against, so the
    # unsourced RPC path keeps refusing every file envelope outright.
    delivery_runtime.validate_output_envelopes(outputs, allow_file_references=source is not None)
    deliveries._exact_json(outputs)
    transfer = None
    if source is not None and delivery_runtime.carries_file_reference(outputs):
        transfer = _transfer_files(
            base, principal=principal, universe_id=universe_id, link_id=link_id,
            occurrence_id=occurrence_id, outputs=outputs, source=source,
            should_cancel=should_cancel,
        )
    with (
        management._owner_authority(base, universe_id, principal),
        deliveries.transaction(base) as conn,
    ):
        link = dict(receiver_links._owned_link(conn, link_id, principal, universe_id))
        if source is not None:
            _check_source(conn, source, link)
        branch = management._owned_branch(base, universe_id, link["branch_def_id"], principal)
        placement = next((n for n in branch.graph_nodes if n.id == link["node_id"]), None)
        definition = next((n for n in branch.node_defs if placement
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
        values = (_structured_inputs(receiver, link, outputs, allow_files=source is not None)
                  if prior is None else mapped)
        if prior is None and transfer is not None and not transfer["replay"]:
            _revalidate_source_bindings(conn, source, transfer)
        if should_cancel():
            raise ValueError("delivery_source_cancelled")
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
            source_run_id=source.run_id if source is not None else None,
            file_transfer=transfer,
        )
        private = deliveries.read_receipt_in_transaction(
            conn, delivery_id=receipt["delivery_id"], principal_id=receiver["owner_id"],
            universe_id=receiver["universe_id"],
        )
    if source is not None:
        # A committed cross-owner transfer is a write even if the node later
        # fails/cancels. Final settlement cannot be refunded by the effect chain.
        engine_admissions.settle_write(source.run_id)
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
