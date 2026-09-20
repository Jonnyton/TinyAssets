"""Transaction-local declared file bindings shared by admission and execution.

No request identity, schema initialization, filesystem IO or new run is created
here. Callers hold current author authority and their existing runs transaction.
"""

from tinyassets.authoring.io import parse_manifest
from tinyassets.run_file_contract import declared_file_inputs, verify_reference
from tinyassets.storage import run_files as store


def file_declarations(branch):
    # Already retained inputs must not become unreadable when the operational
    # capacity setting is reduced. Storage admission, not schema parsing, owns
    # that global ceiling; metadata integers remain SQLite-safe and bounded.
    return parse_manifest(
        branch.to_dict(),
        strict=True,
        max_file_bytes=2**63 - 1,
        max_files=32,
    )


def _validated(conn, *, run_id, owner_id, universe_id, branch, inputs):
    store._owned_run(conn, run_id, owner_id, universe_id)
    declarations = declared_file_inputs(file_declarations(branch), inputs, branch.state_schema)
    result = {}
    for field, references in declarations.items():
        ids = []
        for reference in references:
            file_id = reference.get("file_id")
            row = conn.execute(
                "SELECT * FROM run_file_objects WHERE file_id=? AND owner_id=? "
                "AND universe_id=? AND state='ready'",
                (file_id, owner_id, universe_id),
            ).fetchone()
            if row is None:
                raise store.FileCustodyRefused("run_file_not_found")
            store.visible_operation_in_transaction(conn, row)
            ids.append(verify_reference(reference, row))
        result[field] = ids
    return result


def bind_declared_files(conn, *, run_id, owner_id, universe_id, branch, inputs):
    """Validate the whole bundle before binding under the admission transaction."""
    fields = _validated(
        conn,
        run_id=run_id,
        owner_id=owner_id,
        universe_id=universe_id,
        branch=branch,
        inputs=inputs,
    )
    # Existing fields are immutable; detect all conflicts before adding any new
    # field, even when an internal caller catches a validation error in its TX.
    for field, ids in fields.items():
        prior = [
            row[0]
            for row in conn.execute(
                "SELECT file_id FROM run_file_bindings WHERE run_id=? "
                "AND field_name=? ORDER BY ordinal",
                (run_id, field),
            )
        ]
        if prior and prior != ids:
            raise store.FileCustodyRefused("file_binding_conflict")
    for field, ids in fields.items():
        if ids:
            store.bind_in_transaction(
                conn,
                run_id=run_id,
                owner_id=owner_id,
                universe_id=universe_id,
                field_name=field,
                file_ids=ids,
            )


def validate_bound_files(conn, *, run_id, owner_id, universe_id, branch, inputs):
    """Worker revalidation never invents a missing admission binding."""
    fields = _validated(
        conn,
        run_id=run_id,
        owner_id=owner_id,
        universe_id=universe_id,
        branch=branch,
        inputs=inputs,
    )
    for field, ids in fields.items():
        bound = [
            row[0]
            for row in conn.execute(
                "SELECT file_id FROM run_file_bindings WHERE run_id=? "
                "AND field_name=? ORDER BY ordinal",
                (run_id, field),
            )
        ]
        if bound != ids:
            raise store.FileCustodyRefused("run_file_binding_missing")
