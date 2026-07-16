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
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger("universe_server.branch_designs")

DESIGNS_DIR = Path(__file__).parent
DESIGN_FORMAT = "tinyassets.branch_design/v1"
REFERENCE_TAG = "reference-design"

_REQUIRED_ENVELOPE_KEYS = ("design_format", "design_id", "design_version", "spec")


@contextmanager
def _pinned_data_dir(base_path: str | Path) -> Iterator[None]:
    """Pin ``TINYASSETS_DATA_DIR`` to ``base_path`` for the duration of the block.

    The seeder reconciles/lists/deletes against an EXPLICIT ``base_path`` arg,
    but the composite build path (``_ext_branch_build`` -> ``_base_path()``)
    resolves the GLOBAL ``TINYASSETS_DATA_DIR``. When the two differ (an
    explicit ``base_path`` != the process env), the built row lands in the env
    registry while every other seed op hits ``base_path`` — a split-brain that
    reports ``failed`` and orphans a stray row (Codex S1 round-5). Pinning the
    env for the build makes the whole seed honor one registry.

    Exception-safe: the prior value is always restored (or the key unset if it
    was absent) on exit, including on failure — the seeder must never leave the
    process's data-dir resolution mutated.
    """
    key = "TINYASSETS_DATA_DIR"
    prior = os.environ.get(key)
    os.environ[key] = str(base_path)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


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


def _publish_reference(base_path: str | Path, branch_def_id: str, tag: str) -> None:
    """Publish a seeded reference for discovery/remix. Idempotent.

    Two steps, mirroring the user patch_branch flow exactly (Codex S1 review):
    round-trip through BranchDefinition (a raw row re-save drops the graph
    topology), and mint a PUBLISHED BRANCH VERSION — the published listing
    filters on versions, not the bare flag. ``publish_branch_version`` dedupes
    by content hash, so re-publishing a healthy reference is a no-op.
    """
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    branch = BranchDefinition.from_dict(
        get_branch_definition(base_path, branch_def_id=branch_def_id)
    )
    branch.published = True
    saved = save_branch_definition(base_path, branch_def=branch.to_dict())
    publish_branch_version(
        base_path, saved, publisher="reference-designs",
        notes=f"reference design seed {tag}",
    )


def _content_fingerprint(branch_dict: dict) -> str:
    """An id-independent fingerprint of a branch's meaningful published behavior.

    Reuses the platform's own canonical snapshot (entry point, node defs +
    prompts, edges, conditional maps, state schema, skills) minus the
    branch_def_id, so two branches with identical content — but different ids —
    fingerprint the same. Detects same-count content drift (a corrupted prompt),
    which a bare topology-count check misses (Codex S1 review).
    """
    from tinyassets.branch_versions import _canonical_snapshot, compute_content_hash

    snap = dict(_canonical_snapshot(branch_dict))
    snap.pop("branch_def_id", None)
    return compute_content_hash(snap)


def _build_reference_branch(base_path: str | Path, artifact: dict, tag: str) -> str:
    """Build the authoritative reference branch from the artifact via the ordinary
    composite user path (the reference is an ordinary build). Returns the new
    branch_def_id, or "" on build failure (logged loudly).

    ``_ext_branch_build`` writes through the GLOBAL data-dir resolver
    (``TINYASSETS_DATA_DIR`` / ``_base_path()``), NOT the ``base_path`` arg the
    rest of the seed reconciles against. Pin the resolver to ``base_path`` for
    the build so the whole seed honors one registry — otherwise an explicit
    ``base_path`` != the process env split-brains (build lands in env, list /
    fingerprint / publish / delete hit base_path -> ``failed`` + stray row;
    Codex S1 round-5)."""
    from tinyassets.api.branches import _ext_branch_build

    spec = dict(artifact["spec"])
    spec["tags"] = sorted(set(list(spec.get("tags") or []) + [REFERENCE_TAG, tag]))
    with _pinned_data_dir(base_path):
        out = json.loads(_ext_branch_build({"spec_json": json.dumps(spec)}))
    if out.get("status") != "built" or not out.get("branch_def_id"):
        logger.error(
            "reference design build FAILED for %s: %s", tag, out.get("error") or out,
        )
        return ""
    return out["branch_def_id"]


def _reference_row_is_healthy(
    base_path: str | Path, expected_fp: str, branch_def_id: str,
) -> bool:
    """Healthy = content matches the authoritative build (fingerprint, so drift
    is caught), ``published`` set, and >=1 published branch version (the
    published listing filters on versions)."""
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.daemon_server import get_branch_definition

    full = get_branch_definition(base_path, branch_def_id=branch_def_id)
    if _content_fingerprint(full) != expected_fp:
        return False
    if not full.get("published"):
        return False
    return bool(list_branch_versions(base_path, branch_def_id, limit=1))


def _overwrite_reference_content(
    base_path: str | Path, target_id: str, source_id: str,
) -> None:
    """Copy the authoritative branch content onto an existing id (same-id repair),
    so a drifted/partial reference is healed without changing its id or minting a
    duplicate row."""
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    branch = BranchDefinition.from_dict(
        get_branch_definition(base_path, branch_def_id=source_id)
    )
    branch.branch_def_id = target_id
    branch.published = True
    save_branch_definition(base_path, branch_def=branch.to_dict())


def seed_reference_designs(base_path: str | Path) -> dict[str, list[str]]:
    """Idempotently ensure every packaged reference design exists, matches the
    repo artifact, and is published/remixable in the commons.

    Strategy: build the authoritative branch from each artifact, fingerprint it,
    then reconcile against any existing tagged row — a healthy match is left as
    ``present`` (temp build discarded); a drifted or partially-published row is
    REPAIRED in place (content overwritten from the authoritative build, then
    published); a fresh install is seeded. Returns ``{"seeded", "present",
    "failed"}`` of design tags. Failures log loudly but never raise — a broken
    seed must not take down server startup (the canary + logs surface it).
    """
    from tinyassets.daemon_server import (
        delete_branch_definition,
        get_branch_definition,
        initialize_author_server,
        list_branch_definitions,
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
            # Build the authoritative branch first — it is both the fresh-seed
            # artifact and the drift/health reference for an existing row.
            correct_id = _build_reference_branch(base_path, artifact, tag)
            if not correct_id:
                results["failed"].append(tag)
                continue
            expected_fp = _content_fingerprint(
                get_branch_definition(base_path, branch_def_id=correct_id)
            )
            existing = [
                r for r in list_branch_definitions(base_path, tag=tag)
                if r.get("branch_def_id") != correct_id
            ]

            if not existing:
                # Fresh install: the branch we just built IS the reference.
                _publish_reference(base_path, correct_id, tag)
                results["seeded"].append(tag)
                logger.info(
                    "reference design seeded: %s -> %s", tag, correct_id,
                )
                continue

            if len(existing) > 1:
                logger.warning(
                    "reference design %s has %d rows; reconciling the first "
                    "(remixes carry their own ids, so extras are cruft to review)",
                    tag, len(existing),
                )
            target = existing[0]["branch_def_id"]

            if _reference_row_is_healthy(base_path, expected_fp, target):
                delete_branch_definition(base_path, branch_def_id=correct_id)  # discard temp
                results["present"].append(tag)
                continue

            # Drifted or partially-published — repair in place from the
            # authoritative build, then discard the temp build.
            _overwrite_reference_content(base_path, target, correct_id)
            _publish_reference(base_path, target, tag)
            delete_branch_definition(base_path, branch_def_id=correct_id)
            if _reference_row_is_healthy(base_path, expected_fp, target):
                logger.info("repaired reference seed %s (content/publish)", tag)
                results["seeded"].append(tag)
            else:
                logger.error("reference design %s could not be repaired", tag)
                results["failed"].append(tag)
        except Exception:  # noqa: BLE001 - seeding must never break startup
            logger.exception("reference design seed CRASHED for %s", tag)
            results["failed"].append(tag)
    return results
