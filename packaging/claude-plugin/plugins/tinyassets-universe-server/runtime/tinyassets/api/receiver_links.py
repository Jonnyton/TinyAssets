"""Authenticated collaboration management, not yet wired to public handles.

Uses request identity only. Storage's identifiers and snapshots never confer
universe authority, and inspecting a foreign contract does not disclose its graph.
"""

from __future__ import annotations

from functools import wraps

from tinyassets.auth.middleware import current_identity_or_none
from tinyassets.branches import BranchDefinition
from tinyassets.graph_compiler import _state_schema_defaults
from tinyassets.graph_ingress import project_receiver_entry
from tinyassets.storage import receiver_links as store


def _principal(*, write):
    identity = current_identity_or_none()
    scope = "tinyassets.extensions.write" if write else "tinyassets.extensions.read"
    if identity is None or not identity.user_id or not identity.can(scope).allowed:
        raise store.ReceiverAccessDenied()
    return identity.user_id


def _base():
    from tinyassets.api.helpers import _base_path

    return _base_path()


def _require_admin(base, universe_id, principal):
    from tinyassets.daemon_server import universe_access_permission

    if (
        not universe_id
        or universe_access_permission(
            base,
            universe_id=universe_id,
            actor_id=principal,
        )
        != "admin"
    ):
        raise store.ReceiverAccessDenied()


def _owner_write(function):
    """Fence source ownership/ACL changes through the receiver/link commit.

    The canonical author store owns both ACLs and branch definitions. Acquire
    its SQLite writer reservation BEFORE the runs-store transaction, and keep
    that order for every collaboration mutation. Read existing authority through
    its normal resolver; do not create a second ACL interpretation. No user code,
    provider work or file transfer may execute inside this small management guard.
    """

    @wraps(function)
    def guarded(*, universe_id, **kwargs):
        from tinyassets.daemon_server import initialize_author_server
        from tinyassets.storage import _connect

        principal = _principal(write=True)
        base = _base()
        initialize_author_server(base)
        with _connect(base) as authority:
            authority.execute("BEGIN IMMEDIATE")
            _require_admin(base, universe_id, principal)
            return function(universe_id=universe_id, **kwargs)

    return guarded


def _owned_branch(base, universe_id, branch_def_id, principal):
    from tinyassets.daemon_server import get_branch_definition

    _require_admin(base, universe_id, principal)
    try:
        branch = BranchDefinition.from_dict(
            get_branch_definition(base, branch_def_id=branch_def_id)
        )
    except KeyError as exc:
        raise store.ReceiverAccessDenied() from exc
    if branch.author not in {principal, f"universe:{universe_id}"}:
        raise store.ReceiverAccessDenied()
    return branch


@_owner_write
def save_receiver(
    *,
    universe_id,
    branch_def_id,
    node_id,
    input_keys,
    allowed_senders,
    description="",
    receiver_id=None,
    expected_generation=None,
):
    principal = _principal(write=True)
    base = _base()
    branch = _owned_branch(base, universe_id, branch_def_id, principal)
    if (
        not isinstance(input_keys, list)
        or any(not isinstance(key, str) or not key for key in input_keys)
        or len(set(input_keys)) != len(input_keys)
    ):
        raise ValueError("receiver input_keys must be an explicit list of unique names")
    projection = project_receiver_entry(branch, node_id, contract_input_keys=input_keys)
    fields = {item["name"]: item for item in branch.state_schema}
    defaults = _state_schema_defaults(branch.state_schema)
    # Explicitly advertised input metadata, not the receiver's private defaults
    # or arbitrary schema metadata. A default may contain private startup inputs.
    contract = [
        {
            "name": key,
            "type": fields[key].get("type", "str"),
            "required": key not in defaults,
            "description": fields[key].get("description", ""),
        }
        for key in input_keys
    ]
    return store.save_receiver(
        base,
        owner_id=principal,
        universe_id=universe_id,
        branch_def_id=branch_def_id,
        projection=projection,
        contract=contract,
        allowed_senders=allowed_senders,
        description=description,
        receiver_id=receiver_id,
        expected_generation=expected_generation,
    )


def inspect_receiver(*, receiver_id, owner_universe_id=None):
    principal = _principal(write=False)
    base = _base()
    if owner_universe_id is not None:
        _require_admin(base, owner_universe_id, principal)
    return store.inspect_receiver(
        base,
        receiver_id=receiver_id,
        principal_id=principal,
        owner_universe_id=owner_universe_id,
    )


@_owner_write
def revoke_receiver(*, receiver_id, universe_id, expected_generation):
    principal = _principal(write=True)
    base = _base()
    _require_admin(base, universe_id, principal)
    return store.revoke_receiver(
        base,
        receiver_id=receiver_id,
        universe_id=universe_id,
        owner_id=principal,
        expected_generation=expected_generation,
    )


@_owner_write
def connect_output(
    *, universe_id, branch_def_id, node_id, receiver_id, expected_generation, mapping
):
    principal = _principal(write=True)
    base = _base()
    branch = _owned_branch(base, universe_id, branch_def_id, principal)
    placed = [node for node in branch.graph_nodes if node.id == node_id]
    if len(placed) != 1:
        raise ValueError("source node must name one graph placement")
    definitions = [
        node for node in branch.node_defs if node.node_id == (placed[0].node_def_id or node_id)
    ]
    if (
        len(definitions) != 1
        or not isinstance(mapping, dict)
        or set(mapping) - set(definitions[0].output_keys)
    ):
        raise ValueError("mapping must select declared source node outputs")
    return store.connect_output(
        base,
        owner_id=principal,
        universe_id=universe_id,
        branch_def_id=branch_def_id,
        node_id=node_id,
        receiver_id=receiver_id,
        expected_generation=expected_generation,
        mapping=mapping,
    )


@_owner_write
def disconnect_output(*, link_id, universe_id):
    principal = _principal(write=True)
    base = _base()
    _require_admin(base, universe_id, principal)
    return store.disconnect_output(
        base, link_id=link_id, owner_id=principal, universe_id=universe_id
    )
