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

import hashlib
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

# The seeder's ownership signal is a RESERVED system author, NOT the design tag.
# Tags are user-controllable: a fork INHERITS the source's tags and users can
# submit arbitrary tags (Codex S1 latest-model Finding 1). Reconciling by tag
# alone let a reseed treat a user's remix as "the reference row" and overwrite /
# delete it — user data loss. ``author`` does NOT propagate on fork (``fork()``
# records the FORKING user), and the user-facing build/fork paths strip this
# reserved value (see ``_sanitize_reserved_author``), so it cannot be smuggled.
# Reconcile + prune only ever touch rows carrying BOTH the reserved author and
# the reserved deterministic id below; a user row that merely shares the tag is
# invisible to the seeder.
RESERVED_SEED_AUTHOR = "reference-designs"

_REQUIRED_ENVELOPE_KEYS = ("design_format", "design_id", "design_version", "spec")
# Top-level envelope keys the artifact loader accepts. Anything else is a typo
# or a forward-compat field the current loader does not understand — reject it
# loudly (Codex S1 latest-model Finding 4b) rather than silently ignore it.
# NOTE: ``node_kind`` is a NODE field inside ``spec.node_defs[]`` (carried as
# data for the S3 enforcement slice), NOT a top-level key, so it is unaffected.
_ALLOWED_ENVELOPE_KEYS = frozenset(
    {"design_format", "design_id", "design_version", "title", "provenance", "spec"}
)


def _reference_branch_id(design_id: str, design_version: int) -> str:
    """Deterministic, RESERVED branch_def_id for a seeded reference design.

    Two jobs: (1) concurrency safety — ``save_branch_definition`` is
    ``INSERT OR REPLACE`` keyed on ``branch_def_id``, so two concurrent seeds
    (threads OR multi-worker processes) that both target this fixed id UPSERT
    to one row instead of minting duplicates (Codex S1 latest-model Finding 5);
    (2) unspoofable identity — ``branch_def_id`` is server-assigned on every
    build/fork (users cannot set it), so a user can never occupy this id. Same
    12-hex shape as ``_new_id`` so it round-trips every id-shaped consumer.
    """
    digest = hashlib.sha256(
        f"tinyassets.reference-design:{design_id}@v{int(design_version)}".encode()
    ).hexdigest()
    return digest[:12]


def _sanitize_reserved_author(author: str | None) -> str:
    """Strip the reserved seed author from a user-supplied value so it cannot be
    smuggled onto a user branch via build/fork/import (Finding 1c). Returns ""
    when the value is the reserved author, else the value unchanged."""
    return "" if (author or "").strip() == RESERVED_SEED_AUTHOR else (author or "")


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

    STARTUP-ONLY: this mutates a process-GLOBAL env var. Seeding runs on the
    single-threaded startup seam before request handlers exist, so the mutation
    is not observable. A future RUNTIME re-seed would race concurrent request
    handlers over ``TINYASSETS_DATA_DIR`` — do not call the seeder off the
    startup path without first replacing this env pin with a call-scoped
    resolver override.
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
        # Reject unknown TOP-LEVEL fields — a typo (``design_verison``) or a
        # forward-compat field this loader can't honor must fail loudly, not be
        # silently accepted (Finding 4b). node_kind lives in spec.node_defs[],
        # not here, so it is unaffected.
        unknown = sorted(set(data) - _ALLOWED_ENVELOPE_KEYS)
        if unknown:
            raise ValueError(
                f"branch design artifact {path.name} has unknown top-level "
                f"fields: {unknown} (allowed: {sorted(_ALLOWED_ENVELOPE_KEYS)})"
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

    Rolled-back restore (S2 Codex gate): ``publish_branch_version`` dedupes on
    content hash and returns the EXISTING row WITHOUT reactivating it — so a
    reference whose only version was rolled back cannot be re-minted active by a
    plain re-publish. The reserved reference is a durable commons design that
    must stay discoverable, and its content is the re-verified repo artifact, so
    the seeder REACTIVATES a dedup-hit rolled-back version (seeder-owned id only).
    """
    from tinyassets.branch_versions import _connect, publish_branch_version
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
    version = publish_branch_version(
        base_path, saved, publisher="reference-designs",
        notes=f"reference design seed {tag}",
    )
    if (version.status or "active") != "active":
        # Dedup hit a rolled-back version — restore the reserved reference to
        # active so active-only discovery lists it again.
        with _connect(base_path) as conn:
            conn.execute(
                "UPDATE branch_versions SET status='active', "
                "rolled_back_at=NULL, rolled_back_by=NULL, "
                "rolled_back_reason=NULL WHERE branch_version_id=?",
                (version.branch_version_id,),
            )
        logger.info(
            "reactivated rolled-back reference version %s for %s",
            version.branch_version_id, tag,
        )


def _content_fingerprint(branch_dict: dict) -> str:
    """An id-independent fingerprint of a branch's meaningful published behavior.

    Reuses the platform's own canonical snapshot (entry point, node defs +
    prompts, edges, conditional maps, state schema, skills) minus the
    branch_def_id, so two branches with identical content — but different ids —
    fingerprint the same. Detects same-count content drift (a corrupted prompt),
    which a bare topology-count check misses (Codex S1 review).

    node_kind note: the artifact intentionally carries ``node_kind`` on coding
    nodes as data for the S3 enforcement slice. On S1 alone, ``build_branch``
    drops it (``NodeDefinition`` has no such field yet) AND ``_canonical_snapshot``
    normalizes node_defs through ``NodeDefinition`` — so node_kind is absent from
    BOTH the seeded content and this fingerprint: no perpetual drift on S1. When
    S3 (bundled into the same deploy) adds the ``NodeDefinition.node_kind`` field
    + build threading, the fingerprint WILL include node_kind, so the old
    S1-seeded row (no node_kind) drifts from the S3 authoritative build and the
    reseed drift-repair heals it in place. The artifact contract is honored at
    the bundled deploy.
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
    is caught), ``published`` set, and >=1 ACTIVE (non-rolled-back) branch
    version.

    Active-not-just-present (S2 Codex gate, routed 2026-07-15): "any version
    exists" is NOT health — after a rollback of the only version, the version
    row stays in the table with ``status='rolled_back'`` but active-only
    discovery no longer lists it. Counting it as present would leave the commons
    with a rolled-back-invisible reference forever. Require an ACTIVE version so
    a rolled-back-only reference is re-published on the next seed instead.
    """
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.daemon_server import get_branch_definition

    full = get_branch_definition(base_path, branch_def_id=branch_def_id)
    if _content_fingerprint(full) != expected_fp:
        return False
    if not full.get("published"):
        return False
    versions = list_branch_versions(base_path, branch_def_id, limit=50)
    return any((v.status or "active") == "active" for v in versions)


def _overwrite_reference_content(
    base_path: str | Path, target_id: str, source_id: str,
) -> None:
    """Copy the authoritative branch content onto the canonical reserved id (an
    ``INSERT OR REPLACE`` upsert), stamping the RESERVED author so the row is
    recognizable as seeder-owned. Concurrent seeds converge on ``target_id``."""
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    branch = BranchDefinition.from_dict(
        get_branch_definition(base_path, branch_def_id=source_id)
    )
    branch.branch_def_id = target_id
    branch.author = RESERVED_SEED_AUTHOR
    branch.published = True
    save_branch_definition(base_path, branch_def=branch.to_dict())


def _get_branch_or_none(base_path: str | Path, branch_def_id: str) -> dict | None:
    """Return the branch row, or None when it does not exist."""
    from tinyassets.daemon_server import get_branch_definition

    try:
        return get_branch_definition(base_path, branch_def_id=branch_def_id)
    except KeyError:
        return None


def seed_reference_designs(base_path: str | Path) -> dict[str, list[str]]:
    """Idempotently ensure every packaged reference design exists at its
    canonical RESERVED id, matches the repo artifact, and is published/remixable.

    Identity model (Finding 1): the reference lives at a deterministic
    ``_reference_branch_id`` (unspoofable — users cannot set branch_def_id) and
    carries the ``RESERVED_SEED_AUTHOR``. Reconcile TARGETS that fixed id only;
    it never selects, overwrites, or deletes a row by tag. A user's remix (which
    inherits the tag) or a hostile user-tagged branch has a different id + a
    user author, so it is INVISIBLE to the seeder — no user data loss.

    Concurrency (Finding 5): the fixed id + ``INSERT OR REPLACE`` upsert makes
    two concurrent seeds converge on one row (no duplicates, no crash).

    Strategy per design: build the authoritative branch via the ordinary user
    composite path (validation + fingerprint), then ensure the canonical
    reserved-id row matches + is published — healthy => ``present``, missing or
    drifted => overwrite+publish (``seeded``). Returns ``{"seeded", "present",
    "failed"}`` of design tags. Failures log loudly but never raise — a broken
    seed must not take down startup (the canary + logs surface it).
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

    # A TOTAL failure to enumerate the artifacts (bad packaging, malformed JSON)
    # must be reported loudly as ``failed`` — never a silent green {'failed': []}
    # (Finding 5). ``load_design_artifacts`` raises by contract on a bad artifact.
    try:
        artifacts = load_design_artifacts()
    except Exception:  # noqa: BLE001 - startup must survive, but LOUDLY
        logger.exception("reference design seeding: artifact load failed")
        results["failed"].append("<load-design-artifacts-failed>")
        return results

    for artifact in artifacts:
        tag = design_tag(artifact["design_id"], artifact["design_version"])
        fixed_id = _reference_branch_id(
            artifact["design_id"], artifact["design_version"]
        )
        correct_id = ""
        try:
            # Build the authoritative branch (temp id, full user-path validation)
            # — the drift/health reference for the canonical reserved-id row.
            correct_id = _build_reference_branch(base_path, artifact, tag)
            if not correct_id:
                results["failed"].append(tag)
                continue
            expected_fp = _content_fingerprint(
                get_branch_definition(base_path, branch_def_id=correct_id)
            )

            existing = _get_branch_or_none(base_path, fixed_id)
            if existing is not None and (
                (existing.get("author") or "") != RESERVED_SEED_AUTHOR
            ):
                # Unreachable via the API (ids are server-assigned), but NEVER
                # clobber a non-reserved row occupying the reserved id — fail
                # loud instead of overwriting possible user data.
                logger.error(
                    "reference id %s occupied by a non-reserved row (author=%r); "
                    "refusing to overwrite", fixed_id, existing.get("author"),
                )
                results["failed"].append(tag)
            elif existing is not None and _reference_row_is_healthy(
                base_path, expected_fp, fixed_id
            ):
                results["present"].append(tag)
            else:
                # Missing, drifted, or partially-published — (re)build the
                # canonical reserved-id row from the authoritative content and
                # publish. Upsert on the fixed id => concurrency-safe.
                _overwrite_reference_content(base_path, fixed_id, correct_id)
                _publish_reference(base_path, fixed_id, tag)
                if _reference_row_is_healthy(base_path, expected_fp, fixed_id):
                    logger.info("reference design seeded: %s -> %s", tag, fixed_id)
                    results["seeded"].append(tag)
                else:
                    logger.error("reference design %s could not be seeded", tag)
                    results["failed"].append(tag)

            # Defensive prune: delete any OTHER rows carrying BOTH the reserved
            # author AND this tag (a legacy random-id reserved row, or a
            # concurrent-seed straggler). Gated on the reserved author, so a
            # user remix/tagged branch is NEVER touched. include_private=True so
            # a PRIVATE stray reserved row doesn't evade cleanup (Fable MINOR) —
            # only reserved-author rows are ever visible to this query.
            for r in list_branch_definitions(
                base_path, author=RESERVED_SEED_AUTHOR, tag=tag,
                include_private=True,
            ):
                if r.get("branch_def_id") not in (fixed_id, correct_id):
                    logger.warning(
                        "pruning stray reserved reference row %s for %s",
                        r.get("branch_def_id"), tag,
                    )
                    delete_branch_definition(
                        base_path, branch_def_id=r["branch_def_id"],
                    )
        except Exception:  # noqa: BLE001 - seeding must never break startup
            logger.exception("reference design seed CRASHED for %s", tag)
            results["failed"].append(tag)
        finally:
            # Always discard the temp authoritative build (never the fixed id).
            if correct_id and correct_id != fixed_id:
                try:
                    delete_branch_definition(base_path, branch_def_id=correct_id)
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    logger.exception(
                        "reference design %s: temp build %s cleanup failed",
                        tag, correct_id,
                    )
    return results
