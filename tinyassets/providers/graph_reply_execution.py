"""Conservative graph projection into the existing strict answer receipt.

No routing authority or selected-model inference. Complex/reduced/rewritten
outputs deliberately have no single-model attribution until it can be proven.
"""

from tinyassets.providers.execution_receipt import normalize_execution_receipt


def direct_reply_node(snapshot, reply_key):
    """Identify a provable direct writer before reading only its bounded events."""
    if not isinstance(snapshot, dict):
        return None
    nodes = snapshot.get("node_defs")
    if not isinstance(nodes, list) or not nodes:
        return None
    # Any non-template writer can combine or transform state. Do not infer
    # provenance from a coincidentally equal string or declared output alone.
    if any(not isinstance(node, dict) or not node.get("prompt_template")
           or node.get("source_code") or node.get("invoke_branch_spec")
           or node.get("invoke_branch_version_spec") or node.get("node_ref") for node in nodes):
        return None
    writers = [node for node in nodes if reply_key in (
        node.get("output_keys") or [str(node.get("node_id")) + "_output"]
    )]
    if len(writers) != 1:
        return None
    writer = writers[0]
    if writer.get("output_keys") not in (None, [], [reply_key]):
        return None  # Multi-output/typed JSON transformations are not proven here.
    for field in snapshot.get("state_schema", []):
        if not isinstance(field, dict):
            return None
        if field.get("name") == reply_key and (
            field.get("reducer") or field.get("type", "str") != "str"
        ):
            return None
    refs = snapshot.get("graph_nodes") or []
    if refs and sum((ref.get("node_def_id") or ref.get("id")) == writer["node_id"]
                    for ref in refs if isinstance(ref, dict)) != 1:
        return None
    return writer["node_id"]


def direct_reply_execution(snapshot, reply_key, reply, events):
    node_id = direct_reply_node(snapshot, reply_key)
    if node_id is None or not isinstance(reply, str):
        return None
    matches = [event for event in events if event.get("node_id") == node_id
               and event.get("status") == "ran"]
    if len(matches) != 1:
        return None
    detail = matches[0].get("detail")
    if not isinstance(detail, dict) or detail.get("response") != reply:
        return None
    return normalize_execution_receipt(detail.get("execution"))
