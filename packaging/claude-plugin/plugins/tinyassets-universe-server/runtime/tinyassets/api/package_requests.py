"""The ``install`` ask: a published command-center package, quarantined until its owner says yes.

Change ``command-center-packages`` (D5). The second half of "publish the whole
command center as a package": another account's agent finds a package and
asks; its owner sees what lands where and confirms; only then does any of it
exist in their command center, as THEIR copy.

* **Ask** (served agent). ``capture_action`` reads the package's public
  definition, loads its blob from platform storage, runs the ingestion
  boundary (``check_blob``) and plans every file's destination against the
  installer's folder. Nothing is written into the command center. The pin
  (``pin_ask``) is the quarantine record: it lives outside every agent-reachable
  location and holds the plan, the digest and the tab the platform wrote.
* **Answer** (a person's surface only). ``execute_action`` executes the PIN,
  never the pending-request row. It re-verifies the blob, re-plans and refuses
  if the plan moved, claims the pin atomically, reserves the installer's
  storage, then materialises: private remixes of each workflow under its
  published name, the UI in their library, each automation created PAUSED, and
  the files written ``O_EXCL`` without following links. Every component's new id
  is recorded as it lands, so a retry resumes rather than duplicates.

What never crosses: the publisher's credentials, private data, model choice,
or any write path back to them. A copy runs as whoever installed it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ACTION_TYPE = "install"
_MAX_ID = 200

#: The fixed consent sentence: the platform's words, not the agent's.
INSTALL_SENTENCE = (
    "Everything installs as your own copy, in this command center, and runs as you "
    "with your own connections and models. It never reaches the publisher's "
    "command center. Its automations arrive paused; nothing runs until you resume "
    "one. Files already here stay yours and are not replaced."
)

_SHOWN_FILES = 200


def _shown(value: Any, limit: int = 80) -> str:
    from tinyassets.api.publish_requests import _shown as shown

    return shown(value, limit)


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    """Shape only. Whether the package exists and installs is ``capture_action``'s."""
    from tinyassets.command_center_packages import agent_id

    definition_id = action.get("agent_definition_id")
    if (not isinstance(definition_id, str) or not definition_id.strip()
            or len(definition_id.strip()) > _MAX_ID):
        raise ValueError("install needs the agent_definition_id of a published package")
    return {"type": ACTION_TYPE, "agent_definition_id": definition_id.strip(),
            "agent": agent_id(action.get("agent"))}


def _load(action: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any],
                                          dict[str, Any], dict[str, bytes]]:
    """``(definition, package component, manifest, files)``, all verified.

    The component's sha256, size and file count must match the blob, and the
    blob must pass the ingestion boundary, before anything is planned from it.
    """
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import (
        PACKAGE_KIND,
        PACKAGE_TAG,
        PackageError,
        check_blob,
        read_blob,
    )
    from tinyassets.custom_agents import get_definition

    definition = get_definition(_base_path(), action["agent_definition_id"])
    if definition is None or PACKAGE_TAG not in (definition.get("tags") or []):
        raise LookupError(f"no published package is {action['agent_definition_id']}")
    component = (definition.get("components") or {}).get("package") or {}
    if component.get("kind") != PACKAGE_KIND:
        raise LookupError(f"no published package is {action['agent_definition_id']}")
    try:
        blob = read_blob(_base_path(), str(component.get("blob_sha256") or ""))
        manifest, files = check_blob(blob)
    except PackageError as exc:
        raise ValueError(f"this package cannot be installed: {exc}") from None
    if component.get("size_bytes") != len(blob) or component.get("file_count") != len(files):
        raise ValueError("this package cannot be installed: its listing does not match "
                         "its content")
    return definition, component, manifest, files


def _connections_you_have(actor: str) -> set[str] | None:
    """Connection names the installer already holds, or None when unknown."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage.outbound_connections import ConnectionLedger

    try:
        views = ConnectionLedger(Path(_base_path()) / "outbound.db").list_connection_views(
            owner_user_id=actor, active_only=True, limit=500)
    except Exception:  # noqa: BLE001 - a preview line, never a refusal
        return None
    return {v.destination for v in views}


def _components(definition: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    from tinyassets.api.publish_requests import (
        AUTOMATION_SPEC_KIND,
        BRANCH_REF_KIND,
        UI_KIND,
    )

    components = definition.get("components") or {}
    workflows = [{"key": k, **c} for k, c in sorted(components.items())
                 if isinstance(c, dict) and c.get("kind") == BRANCH_REF_KIND]
    automations = [{"key": k, **c} for k, c in sorted(components.items())
                   if isinstance(c, dict) and c.get("kind") == AUTOMATION_SPEC_KIND]
    ui = components.get("ui") if isinstance(components.get("ui"), dict) else None
    if ui is not None and ui.get("kind") != UI_KIND:
        ui = None
    return {"workflows": workflows, "automations": automations, "ui": [ui] if ui else []}


def _plan(uid: str, action: dict[str, Any]) -> dict[str, Any]:
    """Everything the tab shows and the answer will do, from verified inputs."""
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.command_center_packages import PackageError, human, plan_install
    from tinyassets.principals import named_principal

    actor = named_principal(permissions.current_actor_id())
    if not actor:
        raise PermissionError("an authenticated owner is required")
    definition, component, manifest, files = _load(action)
    try:
        placement = plan_install(_universe_dir(uid), manifest, files)
    except PackageError as exc:
        raise ValueError(f"this package cannot be installed: {exc}") from None
    parts = _components(definition)
    needs = component.get("needs") or {}
    have = _connections_you_have(actor)
    connections = [{"name": str(name), "you_have": None if have is None else name in have}
                   for name in needs.get("connections") or []]
    digest = hashlib.sha256(json.dumps({
        "definition": definition["agent_definition_id"],
        "blob": component["blob_sha256"],
        "agent": action["agent"],
        "placement": placement,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "definition_id": definition["agent_definition_id"],
        "author": str(definition.get("author_id") or ""),
        "name": str(definition.get("name") or ""),
        "version": component.get("version"),
        "size": human(component["size_bytes"]),
        "blob_sha256": component["blob_sha256"],
        "placement": placement,
        "workflows": [{"key": w["key"], "name": str(w.get("name") or w["key"]),
                       "version_id": str(w.get("published_version_id") or "")}
                      for w in parts["workflows"]],
        "automations": [{"key": a["key"], "name": str(a.get("name") or a["key"]),
                         "workflow": str(a.get("workflow") or ""),
                         "trigger": a.get("trigger") or {},
                         "overlap": str(a.get("overlap") or "")}
                        for a in parts["automations"]],
        "ui": parts["ui"][0] if parts["ui"] else None,
        "model": str(needs.get("model") or ""),
        "connections": connections,
        "digest": digest,
    }


def capture_action(uid: str, action: dict[str, Any]) -> dict[str, Any]:
    """Quarantine: verify and plan now; nothing touches the command center."""
    plan = _plan(uid, action)
    return {**action, "snapshot_digest": plan["digest"], "plan": plan}


def tab_text(action: dict[str, Any]) -> tuple[str, str, str]:
    """``(kind, title, body)``, written from the pinned plan only."""
    plan = action["plan"]
    placement = plan["placement"]
    lines = [f"Package: {_shown(plan['name'], 120)} (version {plan['version']}, "
             f"{plan['size']}), published by {_shown(plan['author'], 80)}"]
    if plan["workflows"]:
        lines.append("Workflows, as your own private copies:")
        lines.extend(f"- {_shown(w['name'])}" for w in plan["workflows"])
    if plan["ui"]:
        lines.append(f"The screen \"{_shown(plan['ui'].get('name'))}\", added to your screens")
    if plan["automations"]:
        lines.append("Automations, paused until you resume them:")
        lines.extend(f"- {_shown(a['name'])}" for a in plan["automations"])
    lines.append(f"Files ({len(placement['land'])}) written into this command center:")
    for entry in placement["land"][:_SHOWN_FILES]:
        lines.append(f"  - {_shown(entry['to'], 160)}")
    if len(placement["land"]) > _SHOWN_FILES:
        lines.append(f"  - and {len(placement['land']) - _SHOWN_FILES} more")
    if placement["keep"]:
        lines.append(f"Already here, so kept as yours ({len(placement['keep'])}):")
        lines.extend(f"  - {_shown(p, 160)}" for p in placement["keep"][:_SHOWN_FILES])
    if any(p["to"].startswith("agents/") for p in placement["land"]):
        lines.append(f"Its agent's instructions and skills go under "
                     f"agents/{placement['agent_slug']}/, beside your own.")
    if plan["model"]:
        lines.append(f"It was built with the model {_shown(plan['model'], 80)}; your copy "
                     "uses your own models.")
    for c in plan["connections"]:
        state = ("you have one by that name" if c["you_have"]
                 else "you will need to connect your own" if c["you_have"] is False
                 else "connect your own if you have none")
        lines.append(f"Needs the connection {_shown(c['name'], 60)}: {state}.")
    lines.append("")
    lines.append(INSTALL_SENTENCE)
    return ("Install", f"Install \"{_shown(plan['name'], 120)}\" into this command center?",
            "\n".join(lines))


def pin_ask(uid: str, action: dict[str, Any], tab: tuple[str, str, str]) -> str:
    """The quarantine record, outside every agent-reachable location."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import pin

    kind, title, body = tab
    return pin(_base_path(), universe_id=uid, kind="install", agent=action["agent"],
               digest=action["snapshot_digest"],
               record={"action": action, "tab": {"kind": kind, "title": title, "body": body}})


_CHANGED = (
    "this command center changed since the install was shown (a file or folder it "
    "would write appeared), so nothing was installed; ask again and the tab will "
    "show what lands now"
)


def execute_action(uid: str, pinned: dict[str, Any]) -> dict[str, Any]:
    """Materialise exactly the pinned plan, or nothing new. Raises to leave the ask pending.

    ``pinned`` is the platform's consent record (``pin_for_request``), never the
    pending-request row.
    """
    from tinyassets import storage_accounting
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import (
        PackageError,
        claim,
        finish,
        human,
    )
    from tinyassets.principals import named_principal

    actor = named_principal(permissions.current_actor_id())
    if not actor:
        raise PermissionError("an authenticated owner is required")
    action = pinned["record"]["action"]
    plan = action["plan"]
    if pinned["state"] == "activated":
        return {**pinned["progress"], "already_installed": True}
    if pinned["state"] == "pinned" and _plan(uid, action)["digest"] != pinned["digest"]:
        # A resume skips this: its own earlier writes are what moved the plan.
        raise ValueError(_CHANGED)
    base = _base_path()
    try:
        state = claim(base, universe_id=uid, pin_id=pinned["pin_id"])
    except PackageError as exc:
        raise ValueError(str(exc)) from None
    if state == "activated":
        return {**pinned["progress"], "already_installed": True}
    progress: dict[str, Any] = dict(pinned["progress"]) if state == "activating" else {}
    progress.setdefault("workflows", {})
    progress.setdefault("automations", {})
    progress.setdefault("files", [])
    _, _, _, files = _load(action)
    try:
        from tinyassets.universe_owner import owner_of

        # Files in a command center are charged to its owner, as every write
        # into it is (`api/wiki.py`); None is an unattributed universe.
        account = owner_of(base, uid)
        with storage_accounting.admitted(
                base, account_id=account, scope_id=uid, store="universe_files",
                nbytes=plan["placement"]["bytes"]):
            _materialise(uid, actor, pinned["pin_id"], plan, files, progress)
    except storage_accounting.StorageRefused as refused:
        detail = storage_accounting.visible_record(refused).get("error", "")
        _release(uid, pinned["pin_id"], progress)
        raise ValueError(f"Installing writes {human(plan['placement']['bytes'])}, more than "
                         f"your storage has room for, so nothing was installed. "
                         f"{detail}") from None
    except (PackageError, OSError) as exc:
        _release(uid, pinned["pin_id"], progress)
        raise ValueError(f"the install stopped part way ({exc}); what landed is listed "
                         "in your command center, and confirming again resumes it") from None
    except BaseException:
        _release(uid, pinned["pin_id"], progress)
        raise
    receipt = {"installed": True, "package": plan["name"], "version": plan["version"],
               **progress}
    finish(base, universe_id=uid, pin_id=pinned["pin_id"], progress=receipt)
    return receipt


def _release(uid: str, pin_id: str, progress: dict[str, Any]) -> None:
    """Keep the progress for a resume; the pin stays ``activating``, unheld."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import record_progress, unclaim

    record_progress(_base_path(), universe_id=uid, pin_id=pin_id, progress=progress)
    unclaim(_base_path(), universe_id=uid, pin_id=pin_id)


def _materialise(uid: str, actor: str, pin_id: str, plan: dict[str, Any],
                 files: dict[str, bytes], progress: dict[str, Any]) -> None:
    """Each component once, recording its new id as it lands."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import record_progress

    def save() -> None:
        record_progress(_base_path(), universe_id=uid, pin_id=pin_id, progress=progress)

    for workflow in plan["workflows"]:
        if workflow["key"] not in progress["workflows"]:
            progress["workflows"][workflow["key"]] = _remix(pin_id, workflow)
            save()
    if plan["ui"] and "ui" not in progress:
        progress["ui"] = _add_ui(uid, plan["ui"])
        save()
    for automation in plan["automations"]:
        if automation["key"] not in progress["automations"]:
            progress["automations"][automation["key"]] = _automation(
                uid, actor, pin_id, automation, progress["workflows"])
            save()
    _write_files(uid, plan, files, progress)
    save()


def _remix(pin_id: str, workflow: dict[str, str]) -> str:
    """A private copy authored by the installer, from the immutable snapshot.

    The snapshot's skills are passed explicitly (an empty list included), so
    the fork can never fall back to the source branch's live skills; the model
    policy is cleared, so the copy runs on the installer's own model.
    """
    from tinyassets.api.extensions import _extensions_impl
    from tinyassets.api.helpers import _base_path
    from tinyassets.branch_versions import get_branch_version

    version = get_branch_version(_base_path(), workflow["version_id"])
    if version is None:
        raise ValueError(f"the workflow \"{workflow['name']}\" is no longer published")
    snapshot = version.snapshot if isinstance(version.snapshot, dict) else {}
    spec = {"name": workflow["name"], "fork_from": workflow["version_id"],
            "visibility": "private", "skills": list(snapshot.get("skills") or []),
            "default_llm_policy": None}
    raw = _extensions_impl(action="build_branch", spec_json=json.dumps(spec),
                           request_id=f"package-{pin_id}-{workflow['key']}")
    result = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(result, dict):
        result = {"error": str(raw)[:200]}
    branch_id = result.get("branch_def_id") or (result.get("branch") or {}).get(
        "branch_def_id")
    if not branch_id:
        detail = result.get("error") or result.get("status")
        raise ValueError(f"the workflow \"{workflow['name']}\" could not be copied ({detail})")
    return str(branch_id)


def _add_ui(uid: str, ui: dict[str, Any]) -> str:
    """The screen, added to the installer's library under a free ``ui_id``."""
    from tinyassets.api.app_ui import change_app_ui, read_app_ui

    library = (read_app_ui(universe_id=uid).get("app_ui") or {}).get("ui_library") or []
    taken = {c.get("ui_id") for c in library if isinstance(c, dict)}
    ui_id, n = str(ui.get("ui_id") or "package-ui"), 1
    base_id = ui_id
    while ui_id in taken:
        n += 1
        ui_id = f"{base_id[:56]}-{n}"
    outcome = change_app_ui(universe_id=uid, operation="add_ui",
                            payload={"component": {**ui, "ui_id": ui_id}})
    if outcome.get("error"):
        detail = outcome.get("detail") or outcome["error"]
        raise ValueError(f"the screen could not be added ({detail})")
    return ui_id


def _automation(uid: str, actor: str, pin_id: str, spec: dict[str, Any],
                workflows: dict[str, str]) -> str:
    """The automation against the installer's copy, stored PAUSED in one insert."""
    from tinyassets.api.helpers import _base_path
    from tinyassets.automations import AutomationUnavailable, register_automation

    branch_id = workflows.get(spec["workflow"])
    if not branch_id:
        raise ValueError(f"the automation \"{spec['name']}\" drives a workflow this "
                         "package does not carry")
    trigger = dict(spec["trigger"] or {})
    event_filter = dict(trigger.get("event_filter") or {})
    if event_filter.get("branch_def_id"):
        # Published as a workflow KEY; in a copy it names the installer's copy.
        event_filter["branch_def_id"] = workflows.get(event_filter["branch_def_id"], "")
    kind = str(trigger.get("kind") or "")
    try:
        row = register_automation(
            _base_path(), universe_id=uid, owner_principal_id=actor, name=spec["name"],
            branch_def_id=branch_id,
            interval_seconds=int(trigger.get("interval_seconds") or 0) if kind == "interval"
            else 0,
            cron_expr=str(trigger.get("cron_expr") or "") if kind == "cron" else "",
            event_type=str(trigger.get("event_type") or "") if kind == "event" else "",
            event_filter=event_filter if kind == "event" else None,
            overlap=spec.get("overlap") or "",
            event_key=f"package:{pin_id}:{spec['key']}",
            paused_reason="installed from a package; resume it when you are ready",
        )
    except AutomationUnavailable as exc:
        raise ValueError(f"the automation \"{spec['name']}\" could not be created "
                         f"({exc.reason})") from None
    return row.automation_id


def _write_files(uid: str, plan: dict[str, Any], files: dict[str, bytes],
                 progress: dict[str, Any]) -> None:
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.command_center_packages import write_new_file

    udir = _universe_dir(uid)
    done = set(progress["files"])
    kept = progress.setdefault("kept", [])
    for entry in plan["placement"]["land"]:
        if entry["to"] in done:
            continue
        if write_new_file(udir, entry["to"], files[entry["path"]]):
            progress["files"].append(entry["to"])
        elif entry["to"] not in kept:
            kept.append(entry["to"])
    for path in plan["placement"]["keep"]:
        if path not in kept:
            kept.append(path)


def list_packages(*, query: str = "", author: str = "", limit: int = 30) -> list[dict[str, Any]]:
    """The listing: one row per published package version, from its definition.

    Name, description and author are the publisher's words; size, version, file
    count, agents and needs are the platform's summary. Nothing else of the
    publisher's is here.
    """
    from tinyassets.api.helpers import _base_path
    from tinyassets.command_center_packages import PACKAGE_KIND, PACKAGE_TAG, human
    from tinyassets.custom_agents import list_definitions

    rows = []
    for definition in list_definitions(_base_path(), query=query, tags=[PACKAGE_TAG],
                                       author_id=author, limit=limit):
        component = (definition.get("components") or {}).get("package") or {}
        if component.get("kind") != PACKAGE_KIND:
            continue
        rows.append({
            "agent_definition_id": definition["agent_definition_id"],
            "name": definition.get("name", ""),
            "description": definition.get("description", ""),
            "author_id": definition.get("author_id", ""),
            "version": component.get("version"),
            "size": human(int(component.get("size_bytes") or 0)),
            "file_count": component.get("file_count"),
            "agents": component.get("agents") or [],
            "needs": component.get("needs") or {},
            "created_at": definition.get("created_at"),
        })
    return rows


__all__ = [
    "ACTION_TYPE",
    "INSTALL_SENTENCE",
    "capture_action",
    "execute_action",
    "list_packages",
    "pin_ask",
    "tab_text",
    "validate_action",
]
