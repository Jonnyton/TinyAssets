"""Durable reference branch designs, seeded into the commons at startup.

Design basis: ``docs/design-notes/2026-07-15-user-patch-loop-reference-design.md``
(S1). ``change_loop_v1`` — the only patch loop that ever ran — existed solely in
the live registry and was unrecoverably deleted with the 2026-07-13 volume
closure. Reference designs therefore live in THIS package as portable artifacts
(the same ``build_branch`` ``spec_json`` schema users author with, wrapped in a
thin versioned envelope) and are re-seeded idempotently at every server start:
a registry wipe can no longer delete a design class, only live remixes — which
re-fork from the reference.

The seeder deliberately builds through the SAME composite ``build_branch``
path a user's chatbot uses (dogfood: the reference IS an ordinary user build),
then tags + publishes the result. Idempotency is tag-based: one branch per
``design:<design_id>@v<version>`` tag.

Artifacts are repo-blind by contract: a design must never carry a repository
identity — binding a repo/credential is a user act at remix time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("universe_server.branch_designs")

DESIGNS_DIR = Path(__file__).parent
DESIGN_FORMAT = "tinyassets.branch_design/v1"
REFERENCE_TAG = "reference-design"

_REQUIRED_ENVELOPE_KEYS = ("design_format", "design_id", "design_version", "spec")


def design_tag(design_id: str, design_version: int) -> str:
    """The idempotency + drift-detection tag for one design version."""
    return f"design:{design_id}@v{int(design_version)}"


def load_design_artifacts() -> list[dict[str, Any]]:
    """Parse every ``*.json`` artifact in this package. Fail loudly on a bad one.

    A malformed artifact is a packaging bug: raise instead of skipping, so CI
    and the import probe catch it before a deploy ships a dead reference.
    """
    artifacts: list[dict[str, Any]] = []
    for path in sorted(DESIGNS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in _REQUIRED_ENVELOPE_KEYS if k not in data]
        if missing:
            raise ValueError(
                f"branch design artifact {path.name} missing envelope keys: {missing}"
            )
        if data["design_format"] != DESIGN_FORMAT:
            raise ValueError(
                f"branch design artifact {path.name} has unsupported design_format "
                f"{data['design_format']!r} (expected {DESIGN_FORMAT!r})"
            )
        artifacts.append(data)
    return artifacts


def seed_reference_designs(base_path: str | Path) -> dict[str, list[str]]:
    """Idempotently ensure every packaged reference design exists in the commons.

    Returns ``{"seeded": [...], "present": [...], "failed": [...]}`` of design
    tags. Failures are logged loudly but never raise — a broken seed must not
    take down server startup (the canary + logs surface it).
    """
    from tinyassets.daemon_server import (
        get_branch_definition,
        initialize_author_server,
        list_branch_definitions,
        save_branch_definition,
    )

    results: dict[str, list[str]] = {"seeded": [], "present": [], "failed": []}
    try:
        # The registry CRUD helpers assume the schema exists; at first boot on
        # a fresh volume it does not. Idempotent + serialized (see the
        # auto-birth init lock), so this is safe to call every seed.
        initialize_author_server(base_path)
    except Exception:  # noqa: BLE001 - the per-artifact loop will surface it
        logger.exception("reference design seeding: registry init failed")
    for artifact in load_design_artifacts():
        tag = design_tag(artifact["design_id"], artifact["design_version"])
        try:
            existing = list_branch_definitions(base_path, tag=tag)
            if existing:
                results["present"].append(tag)
                continue

            spec = dict(artifact["spec"])
            spec["tags"] = sorted(
                set(list(spec.get("tags") or []) + [REFERENCE_TAG, tag])
            )
            # Build through the ordinary composite user path — the reference is
            # an ordinary build, not a privileged registry write.
            from tinyassets.api.branches import _ext_branch_build

            out = json.loads(_ext_branch_build({"spec_json": json.dumps(spec)}))
            if out.get("status") != "built" or not out.get("branch_def_id"):
                logger.error(
                    "reference design seed FAILED for %s: %s",
                    tag,
                    out.get("error") or out,
                )
                results["failed"].append(tag)
                continue

            # Publish the reference so it is discoverable/remixable commons
            # content (published=False would hide it from the default listing).
            branch_def = get_branch_definition(
                base_path, branch_def_id=out["branch_def_id"],
            )
            branch_def["published"] = True
            save_branch_definition(base_path, branch_def=branch_def)
            results["seeded"].append(tag)
            logger.info(
                "reference design seeded: %s -> branch_def_id=%s",
                tag,
                out["branch_def_id"],
            )
        except Exception:  # noqa: BLE001 - seeding must never break startup
            logger.exception("reference design seed CRASHED for %s", tag)
            results["failed"].append(tag)
    return results
