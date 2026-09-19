"""Internal dispatch/recovery for already accepted receiver deliveries.

Not an intake API: acceptance, resource/file admission and public graph wiring
remain separate. Never treat a queued run row as a durable executor queue.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import threading

from tinyassets import runs
from tinyassets.api.receiver_links import _owned_branch
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity
from tinyassets.branches import BranchDefinition
from tinyassets.storage import _connect as author_connection
from tinyassets.storage import deliveries
from tinyassets.storage.delivery_lock import try_attempt_lock

logger = logging.getLogger(__name__)
_submitted = set()
_submitted_lock = threading.Lock()


def reject_file_references(value):
    """Fail explicitly until immutable runtime file bindings are implemented.

    These are reference envelope fields, not credential-key redaction. Ordinary
    structured fields named key/token remain exact data.
    """
    if isinstance(value, dict):
        if ({"handle_id", "artifact_id", "file_id"} & value.keys()
                or value.get("type") in ("file", "file_bundle")):
            raise ValueError("delivery_file_transfer_not_implemented")
        for child in value.values():
            reject_file_references(child)
    elif isinstance(value, list):
        for child in value:
            reject_file_references(child)


def _execution_subject(base, delivery):
    """Revalidate the persisted receiver grant; never use sender authority."""
    _owned_branch(
        base, delivery["receiver_universe_id"], delivery["receiver_branch_id"],
        delivery["receiver_owner_id"],
    )
    snapshot = delivery["snapshot_json"]
    if hashlib.sha256(snapshot.encode("utf-8")).hexdigest() != delivery["snapshot_sha256"]:
        raise ValueError("receiver_snapshot_integrity_failed")
    branch = BranchDefinition.from_dict(json.loads(snapshot))
    inputs = json.loads(delivery["inputs_json"])
    reject_file_references(inputs)
    if branch.validate():
        raise ValueError("receiver_snapshot_invalid")
    runs.preflight_required_inputs(branch, inputs)
    # Same owner-run capabilities as the existing served run bridge, derived
    # from the receiver-authored exposure and current admin/graph checks above.
    # Effects still enforce their own destination grants and consent.
    identity = Identity(
        user_id=delivery["receiver_owner_id"], username=delivery["receiver_owner_id"],
        capabilities=["read", "list", "write", "submit_request", "costly"],
    )
    return branch, inputs, identity


def _receiver_provider(base, delivery, branch, run_id):
    from tinyassets.api.runs import _bind_run_provider_call
    from tinyassets.foreground_run_provider import prepare_foreground_run_provider
    from tinyassets.providers.call import call_provider

    provider = _bind_run_provider_call(
        call_provider, delivery["receiver_universe_id"],
        principal_id=delivery["receiver_owner_id"],
    )
    return prepare_foreground_run_provider(
        provider, run_id=run_id, branch=branch, branch_version_id=None,
        allowed_statuses={runs.RUN_STATUS_QUEUED},
    )


def _work(base, delivery_id, attempt):
    """Lock lifetime includes provider execution and terminal settlement."""
    with try_attempt_lock(base, delivery_id=delivery_id, attempt=attempt) as guard:
        if guard is None:
            return
        state = deliveries.reconcile_attempt(base, guard)
        if state["state"] != "pending":
            return
        run_id = state["run_id"]
        claim = None
        try:
            # Preserve the canonical lock order: author store, then runs store.
            # No provider call or user code executes while either is held.
            with author_connection(base) as authority:
                authority.execute("BEGIN IMMEDIATE")
                with deliveries.transaction(base) as conn:
                    delivery = dict(conn.execute(
                        "SELECT * FROM graph_deliveries WHERE delivery_id=?", (delivery_id,),
                    ).fetchone())
                    branch, inputs, identity = _execution_subject(base, delivery)
                    claim = deliveries.start_attempt_in_transaction(conn, guard)
            if not claim:
                return
            # A crash after the durable start marker is ambiguous and NEVER
            # automatically replayed, even if it happened before first execution.
            with identity_context(identity):
                actor = f"universe:{delivery['receiver_universe_id']}"
                runs._initialize_prepared_run(base, run_id=run_id, branch=branch, actor=actor)
                provider = _receiver_provider(base, delivery, branch, run_id)
                runs._invoke_prepared_branch(
                    base, run_id=run_id, branch=branch, inputs=inputs, actor=actor,
                    provider_call=provider, recursion_limit=runs.DEFAULT_RECURSION_LIMIT,
                    enqueue_universe_id=delivery["receiver_universe_id"],
                )
        except Exception:
            logger.exception("Receiver delivery attempt failed: %s/%s", delivery_id, attempt)
            runs.update_run_status(
                base, run_id, status=runs.RUN_STATUS_FAILED,
                error="Receiver delivery processing failed; see receiver logs.",
                finished_at=runs._now(),
            )
        finally:
            if claim:
                with deliveries.transaction(base) as conn:
                    deliveries.finish_attempt_in_transaction(conn, guard, claim_token=claim)
            else:
                deliveries.reconcile_attempt(base, guard)


def dispatch_accepted_delivery(base, *, delivery_id, attempt=1):
    """Submit one reserved attempt in a fresh context to the existing executor.

    The OS guard is acquired INSIDE that worker and never handed across threads.
    Repeated reconciliation can resubmit only after the earlier Future settles;
    durable state/lock checks still decide whether execution is permitted.
    """
    key = (str(runs.runs_db_path(base).resolve()), delivery_id, attempt)
    with _submitted_lock:
        if key in _submitted:
            return False
        _submitted.add(key)
    try:
        with deliveries.transaction(base) as conn:
            row = conn.execute(
                "SELECT run_id FROM graph_delivery_attempts WHERE delivery_id=? AND attempt=?",
                (delivery_id, attempt),
            ).fetchone()
            if row is None:
                raise ValueError("delivery_attempt_not_found")
        future = runs._get_executor(invocation_depth=0).submit(
            contextvars.Context().run, _work, base, delivery_id, attempt,
        )
        runs._track_future(row["run_id"], future)
        def finished(_future):
            with _submitted_lock:
                _submitted.discard(key)
        future.add_done_callback(finished)
        return True
    except BaseException:
        with _submitted_lock:
            _submitted.discard(key)
        raise


def reconcile_deliveries(base):
    """One internal startup/maintenance pass; no new occurrence or retry.

    Wiring to daemon startup is deliberately separate from this function. A
    caller must not describe this as an installed background queue until wired.
    """
    with deliveries.transaction(base) as conn:
        pending = conn.execute(
            "SELECT delivery_id, attempt FROM graph_delivery_attempts "
            "WHERE state IN ('pending','executing') ORDER BY created_at",
        ).fetchall()
    return sum(dispatch_accepted_delivery(
        base, delivery_id=row["delivery_id"], attempt=row["attempt"],
    ) for row in pending)
