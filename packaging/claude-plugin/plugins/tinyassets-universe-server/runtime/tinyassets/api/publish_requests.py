"""The ``publish`` ask: a universe proposes, its owner confirms, the platform publishes.

A universe that built something -- workflows, the screen that shows them, the
automations that keep them running -- could not share it: the served surface has
no publish (an agent running AS its owner could consent for them), and the app
had nowhere to press. This is the consent gate the deferral note asked for.

The shape is the existing action-bearing ask (``bind_model_access`` is the
model):

* **Ask** (served agent). The action names what to publish. ``capture_action``
  checks every item is the owner's own, pins a digest of each, and records what
  the tab must show. The platform writes the tab's text from that record
  (``tab_text``), so the agent cannot phrase the consent.
* **Answer** (a person's surface only; the served surface has no
  ``answer_request``). ``execute_action`` recomputes every digest -- anything
  edited since the tab was shown publishes nothing -- then makes each branch
  public, publishes a version of each, and publishes ONE definition that
  bundles the UI with a reference to each workflow and the trigger of each
  automation. Idempotent on the request id, so a retried confirm cannot publish
  a second definition.

What is never published: automation ``inputs``, conversations, files,
credentials. A copy of anything published runs as whoever installs it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BRANCH_REF_KIND = "tinyassets.branch-ref.v1"
AUTOMATION_SPEC_KIND = "tinyassets.automation-spec.v1"
UI_KIND = "tinyassets.app-ui.v1"

_MAX_NAME = 120
_MAX_DESCRIPTION = 4000
_MAX_ID = 200

#: The fixed consent sentence. The platform's words, not the agent's.
PUBLIC_SENTENCE = (
    "Anyone will be able to read and copy these. A copy runs in the copier's own "
    "universe on their own compute and never reaches yours. Publishing does not "
    "share your conversations, files, credentials or automation inputs."
)


def _ids(raw: Any, field: str, *, required: bool) -> list[str]:
    if raw is None:
        raw = []
    if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
        raise ValueError(f"{field} must be a list of ids")
    ids: list[str] = []
    for value in raw:
        text = value.strip()
        if not text or len(text) > _MAX_ID:
            raise ValueError(f"{field} holds an empty or over-long id")
        if text not in ids:
            ids.append(text)
    if required and not ids:
        raise ValueError(f"{field} must name at least one")
    return ids


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    """Shape only: the fields and their types. Ownership is ``capture_action``'s."""
    name = action.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > _MAX_NAME:
        raise ValueError(f"publish needs a public name of 1-{_MAX_NAME} characters")
    description = action.get("description", "")
    if not isinstance(description, str) or len(description) > _MAX_DESCRIPTION:
        raise ValueError(f"description must be text of at most {_MAX_DESCRIPTION} characters")
    ui_id = action.get("ui_id", "")
    if ui_id is None:
        ui_id = ""
    if not isinstance(ui_id, str) or len(ui_id) > 64:
        raise ValueError("ui_id must be the id of one UI in the owner's library")
    return {
        "type": "publish",
        "name": name.strip(),
        "description": description.strip(),
        "branch_ids": _ids(action.get("branch_ids"), "branch_ids", required=True),
        "ui_id": ui_id.strip(),
        "automation_ids": _ids(action.get("automation_ids"), "automation_ids", required=False),
    }


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: Fields of a branch row that publishing may change or that move on their own
#: (run stats, edit bookkeeping). EVERYTHING ELSE becomes publicly readable, so
#: everything else is pinned -- a denylist of volatile fields, never an allowlist
#: of the ones someone remembered to include (Codex refute 2026-09-29: tags
#: were outside the digest and published changed).
_UNPINNED_BRANCH_FIELDS = frozenset({"visibility", "published", "updated_at", "version", "stats"})


def branch_digest(branch: dict[str, Any]) -> str:
    """Digest of every field of a branch row that becomes public on publish."""
    from tinyassets.branches import BranchDefinition

    normalized = BranchDefinition.from_dict(branch).to_dict()
    return _digest({k: v for k, v in normalized.items() if k not in _UNPINNED_BRANCH_FIELDS})


def _branch_facts(base: Path, actor: str, branch_def_id: str) -> dict[str, Any]:
    """What the owner is shown and what is pinned, for one of THEIR branches."""
    from tinyassets.branch_versions import _canonical_snapshot
    from tinyassets.daemon_server import get_branch_definition

    try:
        raw = get_branch_definition(base, branch_def_id=branch_def_id)
    except (KeyError, FileNotFoundError):
        raise LookupError(f"no branch of yours is {branch_def_id}") from None
    if (raw.get("author") or "").strip() != actor:
        # Same words as absent: an ask cannot probe another author's ids.
        raise LookupError(f"no branch of yours is {branch_def_id}")
    return {
        "branch_def_id": branch_def_id,
        "name": str(raw.get("name") or branch_def_id),
        "description": str(raw.get("description") or ""),
        "nodes": len(_canonical_snapshot(raw).get("graph_nodes") or []),
        "digest": branch_digest(raw),
    }


#: The portable fields of a UI component -- exactly what the app renders
#: (``AppUI.FIELDS`` in onboarding/app_ui.js). A stored component may carry
#: anything else; none of it is published (Codex refute 2026-09-29: an
#: ``inputs`` field rode into the public definition).
UI_PORTABLE_FIELDS = ("kind", "version", "ui_id", "name", "markup", "style", "script")


def export_ui_component(component: dict[str, Any]) -> dict[str, Any]:
    exported = {k: component[k] for k in UI_PORTABLE_FIELDS if k in component}
    missing = [k for k in UI_PORTABLE_FIELDS if k not in exported]
    if missing:
        raise ValueError(f"that UI is missing {', '.join(missing)} and cannot be published")
    return json.loads(json.dumps(exported))


def _ui_facts(base: Path, actor: str, uid: str, ui_id: str) -> dict[str, Any]:
    from tinyassets.custom_agents import get_app_ui

    row = get_app_ui(base, owner_user_id=actor, universe_id=uid)
    for component in row.get("ui_library") or []:
        if isinstance(component, dict) and component.get("ui_id") == ui_id:
            if component.get("kind") != UI_KIND:
                break
            exported = export_ui_component(component)
            return {"ui_id": ui_id, "name": str(exported.get("name") or ui_id),
                    "component": exported, "digest": _digest(exported)}
    raise LookupError(f"no UI of yours is {ui_id}")


def _trigger(automation: Any) -> dict[str, Any]:
    return {
        "kind": automation.trigger_kind,
        "interval_seconds": automation.interval_seconds,
        "cron_expr": automation.cron_expr,
        "event_type": automation.event_type,
        "event_filter": dict(automation.event_filter or {}),
    }


def _automation_facts(
    base: Path, actor: str, uid: str, automation_id: str, branch_ids: list[str],
) -> dict[str, Any]:
    from tinyassets.automations import AutomationStore

    row = AutomationStore(base).get(automation_id)
    if (
        row is None or row.retired_at or row.universe_id != uid
        or row.owner_principal_id != actor
    ):
        raise LookupError(f"no automation of yours is {automation_id}")
    if row.branch_def_id not in branch_ids:
        raise ValueError(
            f"automation {automation_id} drives a workflow this ask does not "
            "publish; add that workflow or leave the automation out"
        )
    trigger = _trigger(row)
    return {"automation_id": automation_id, "name": row.name,
            "branch_def_id": row.branch_def_id, "trigger": trigger,
            "overlap": row.overlap,
            "digest": _digest({"branch": row.branch_def_id, "trigger": trigger,
                               "overlap": row.overlap, "name": row.name})}


def _facts(uid: str, action: dict[str, Any]) -> dict[str, Any]:
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path
    from tinyassets.principals import named_principal

    actor = named_principal(permissions.current_actor_id())
    if not actor:
        raise PermissionError("an authenticated owner is required")
    base = Path(_base_path())
    return {
        "branches": [_branch_facts(base, actor, b) for b in action["branch_ids"]],
        "ui": _ui_facts(base, actor, uid, action["ui_id"]) if action["ui_id"] else None,
        "automations": [
            _automation_facts(base, actor, uid, a, action["branch_ids"])
            for a in action["automation_ids"]
        ],
    }


def _pins(facts: dict[str, Any]) -> dict[str, str]:
    pins = {f"branch:{b['branch_def_id']}": b["digest"] for b in facts["branches"]}
    if facts["ui"]:
        pins[f"ui:{facts['ui']['ui_id']}"] = facts["ui"]["digest"]
    for a in facts["automations"]:
        pins[f"automation:{a['automation_id']}"] = a["digest"]
    return pins


def _shown(value: Any, limit: int = 80) -> str:
    """Agent-authored text as it may appear on the tab: one line, bounded.

    Names are the agent's words inside the platform's sentence. A newline would
    let a branch named "...\\n\\nNothing here is shared." read as the platform
    speaking, so every echoed name is flattened and cut, never rendered raw.
    """
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _trigger_words(trigger: dict[str, Any]) -> str:
    if trigger["kind"] == "interval":
        return f"every {trigger['interval_seconds']} seconds"
    if trigger["kind"] == "cron":
        return f"on the schedule {trigger['cron_expr']}"
    if trigger["kind"] == "event":
        return f"when {trigger['event_type']} happens"
    return trigger["kind"]


def capture_action(uid: str, action: dict[str, Any]) -> dict[str, Any]:
    """Check ownership, pin digests, and record what the tab must list."""
    facts = _facts(uid, action)
    shown = {
        "workflows": [{"name": _shown(b["name"]), "nodes": b["nodes"]}
                      for b in facts["branches"]],
        "ui": _shown(facts["ui"]["name"]) if facts["ui"] else "",
        "automations": [{"name": _shown(a["name"]), "when": _shown(_trigger_words(a["trigger"]))}
                        for a in facts["automations"]],
    }
    return {**action, "digests": _pins(facts), "shown": shown}


def tab_text(action: dict[str, Any]) -> tuple[str, str, str]:
    """``(kind, title, body)`` for the tab, written from the pinned action only."""
    shown = action["shown"]
    lines = [f"Public name: {_shown(action['name'], 120)}"]
    if action["description"]:
        lines.append(f"Description: {_shown(action['description'], 400)}")
    lines.append("These become public:")
    for w in shown["workflows"]:
        lines.append(f"- Workflow \"{w['name']}\" ({w['nodes']} steps)")
    if shown["ui"]:
        lines.append(f"- The screen \"{shown['ui']}\"")
    for a in shown["automations"]:
        lines.append(f"- The trigger of \"{a['name']}\": runs {a['when']} (its inputs stay private)")
    lines.append("")
    lines.append(PUBLIC_SENTENCE)
    return ("Publish", f"Publish \"{_shown(action['name'], 120)}\" for anyone to copy?",
            "\n".join(lines))


def _make_public_if_unchanged(pins: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Compare-and-set: flip EVERY branch public only if each is what was approved.

    One write transaction holds every check and every flip, so an edit cannot
    land between them and the set goes public whole or not at all (Codex refute
    2026-09-29: checking first and patching after let a concurrent edit publish
    a description the owner never saw). Returns each row AS FLIPPED, which is
    what its version is minted from -- never a second, unchecked read.
    """
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import _branch_def_from_row, _connect

    flipped: dict[str, dict[str, Any]] = {}
    with _connect(_base_path()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for branch_def_id, digest in pins.items():
            row = conn.execute(
                "SELECT * FROM branch_definitions WHERE branch_def_id = ?", (branch_def_id,),
            ).fetchone()
            if row is None or branch_digest(_branch_def_from_row(row)) != digest:
                # Raising inside the transaction rolls every flip back.
                raise ValueError(
                    "something in this ask changed after you were shown it, so "
                    "nothing was published; ask again and the tab will show what "
                    "is there now"
                )
            conn.execute(
                "UPDATE branch_definitions SET visibility = 'public', published = 1 "
                "WHERE branch_def_id = ?", (branch_def_id,),
            )
            flipped[branch_def_id] = _branch_def_from_row(conn.execute(
                "SELECT * FROM branch_definitions WHERE branch_def_id = ?", (branch_def_id,),
            ).fetchone())
    return flipped


def execute_action(uid: str, action: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    """Publish exactly what was pinned, or nothing. Raises to leave the ask pending."""
    from tinyassets.api import permissions
    from tinyassets.api.custom_agents import custom_agents
    from tinyassets.api.helpers import _base_path
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.custom_agents import AGENT_SCHEMA_VERSION
    from tinyassets.principals import named_principal

    actor = named_principal(permissions.current_actor_id())

    facts = _facts(uid, action)
    if _pins(facts) != action.get("digests"):
        raise ValueError(
            "something in this ask changed after you were shown it, so nothing "
            "was published; ask again and the tab will show what is there now"
        )
    approved_rows = _make_public_if_unchanged(
        {b["branch_def_id"]: b["digest"] for b in facts["branches"]})
    published_public = [b["name"] for b in facts["branches"]]
    versions: dict[str, str] = {}
    try:
        for branch in facts["branches"]:
            bid = branch["branch_def_id"]
            approved = approved_rows[bid]
            version = publish_branch_version(
                _base_path(), approved, publisher=actor, notes=action["name"])
            versions[bid] = version.branch_version_id
    except (KeyError, ValueError) as exc:
        # A public branch cannot be made unseen: someone may already have read
        # it. Say exactly what is public so the owner and the agent know.
        made = ", ".join(published_public) or "nothing"
        raise ValueError(f"{exc}. Already public: {made}.") from exc

    components: dict[str, dict[str, Any]] = {}
    keys: dict[str, str] = {}
    if facts["ui"]:
        components["ui"] = json.loads(json.dumps(facts["ui"]["component"]))
    for n, branch in enumerate(facts["branches"], start=1):
        key = f"workflow-{n}"
        keys[branch["branch_def_id"]] = key
        components[key] = {"kind": BRANCH_REF_KIND, "name": branch["name"],
                           "published_version_id": versions[branch["branch_def_id"]]}
    for n, auto in enumerate(facts["automations"], start=1):
        trigger = json.loads(json.dumps(auto["trigger"]))
        # A filter naming the author's own branch id would mean nothing in a
        # copy; it names the workflow component instead.
        followed = trigger["event_filter"].get("branch_def_id")
        if followed:
            trigger["event_filter"]["branch_def_id"] = keys.get(followed, "")
        components[f"automation-{n}"] = {
            "kind": AUTOMATION_SPEC_KIND, "name": auto["name"],
            "workflow": keys[auto["branch_def_id"]], "trigger": trigger,
            "overlap": auto["overlap"]}
    result = custom_agents(
        action="publish_agent",
        payload=json.dumps({"schema_version": AGENT_SCHEMA_VERSION,
                            "name": action["name"], "description": action["description"],
                            "tags": ["tinyassets.system.v1"], "components": components}),
        idempotency_key=f"publish-request:{request_id}",
    )
    agent = result.get("agent") if isinstance(result, dict) else None
    if not agent or result.get("error"):
        made = ", ".join(published_public) or "nothing"
        raise ValueError(
            f"the workflows were published but the bundle was not "
            f"({result.get('detail') or result.get('error')}). Already public: {made}."
        )
    return {
        "published": True,
        "agent_definition_id": agent["agent_definition_id"],
        "branch_versions": versions,
    }


__all__ = [
    "AUTOMATION_SPEC_KIND",
    "BRANCH_REF_KIND",
    "capture_action",
    "execute_action",
    "tab_text",
    "validate_action",
]
