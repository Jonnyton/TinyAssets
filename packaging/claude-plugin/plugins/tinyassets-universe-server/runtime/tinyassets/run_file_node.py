"""Trusted compiled placement and actual incoming dataflow for sandbox reads.

The sandbox supplies only file_id/offset/count. It never supplies this context,
the incoming state view or an execution-use receipt.
"""

from dataclasses import dataclass

from tinyassets import runs
from tinyassets.authoring.io import IODeclaration, Manifest
from tinyassets.run_file_contract import declared_file_inputs, verify_reference
from tinyassets.run_file_reader import read_bound_file
from tinyassets.storage import run_files as store
from tinyassets.storage.run_execution_lock import RunExecutionUse


@dataclass(frozen=True)
class NodeFileSource:
    owner_user_id: str
    universe_id: str
    actor: str
    run_id: str
    branch_def_id: str
    node_id: str
    # Intersection of this compiled node's explicit input_keys and the branch's
    # file declarations. Defaults/strict-input escape do not expand this set.
    fields: tuple[IODeclaration, ...]


def _check_source(conn, source):
    use = runs._RUN_EXECUTION_USE.get()
    if type(use) is not RunExecutionUse or use.run_id != source.run_id:
        raise store.FileCustodyRefused("file_node_authority_unavailable")
    use.require_in_use(conn)
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id=? AND owner_user_id=? AND queue_universe_id=? "
        "AND actor=? AND branch_def_id=? AND status='running'",
        (
            source.run_id,
            source.owner_user_id,
            source.universe_id,
            source.actor,
            source.branch_def_id,
        ),
    ).fetchone()
    if (
        row is None
        or conn.execute(
            "SELECT 1 FROM run_cancels WHERE run_id=?",
            (source.run_id,),
        ).fetchone()
    ):
        raise store.FileCustodyRefused("file_node_not_running")
    root = row["workspace_budget_root_run_id"]
    if root:
        state = conn.execute(
            "SELECT workspace_budget_closing_reason FROM runs WHERE run_id=?",
            (root,),
        ).fetchone()
        if state is None or state[0]:
            raise store.FileCustodyRefused("file_node_cancelled")


def read_node_file(base, *, source, incoming, file_id, offset, count, should_cancel):
    if (
        type(source) is not NodeFileSource
        or not all(
            (
                source.owner_user_id,
                source.universe_id,
                source.actor,
                source.run_id,
                source.branch_def_id,
                source.node_id,
            )
        )
        or not isinstance(incoming, dict)
    ):
        raise store.FileCustodyRefused("file_node_authority_unavailable")
    # The parent freezes this view at node entry. Listing a file ID in RPC kwargs
    # or receiving undeclared whole-state fields is never dataflow authority.
    declared = declared_file_inputs(
        Manifest(inputs=source.fields, outputs=()), incoming,
        [{"name": field.name, "type": "list" if field.io_type == "file_bundle" else "dict"}
         for field in source.fields],
    )
    candidates = [ref for values in declared.values() for ref in values
                  if ref.get("file_id") == file_id]
    if not candidates:
        raise store.FileCustodyRefused("file_not_in_declared_node_inputs")

    def cancelled():
        if should_cancel():
            return True
        with runs._connect(base) as conn:
            conn.execute("BEGIN")
            _check_source(conn, source)
            row = store.bound_file_in_transaction(
                conn,
                run_id=source.run_id,
                owner_id=source.owner_user_id,
                universe_id=source.universe_id,
                file_id=file_id,
            )
            for reference in candidates:
                verify_reference(reference, row)
        return False

    if cancelled():
        raise store.FileCustodyRefused("file_node_cancelled")
    return read_bound_file(
        base,
        owner_id=source.owner_user_id,
        universe_id=source.universe_id,
        run_id=source.run_id,
        file_id=file_id,
        offset=offset,
        count=count,
        should_cancel=cancelled,
    )
