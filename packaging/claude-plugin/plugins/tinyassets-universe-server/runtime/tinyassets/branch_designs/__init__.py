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

PHASE-2 EXECUTION BOUNDARY (patch_loop_reference; Codex r11 #2, host "build
execution first"). The reference declares the FULL intended loop with correct
effect + gate CONTRACTS (present emits a github_pull_request packet carrying the
changes reference + S4 review_queue metadata; merge emits a github_merge packet;
verify/owner_gate are canonical gates). It is a correct declared TEMPLATE — its
end-to-end EXECUTION does NOT run yet and is deferred to the Phase-2
durable-resume subsystem, which owns: (1) SUSPEND after present (the PR effector
runs post-graph, but the inline owner_gate currently decides BEFORE that write),
(2) RESUME on the owner's decision from the S4 review-queue, and (3) reshaping
the inline ``owner_gate -> merge`` edge into that pause/resume flow. Do NOT
restructure the graph or build the resume engine here — that is Phase 2. On S1
the repo-touching nodes (investigate/verify/draft_patch) are sandbox-required
and honestly FAIL CLOSED: the compiled node REFUSES to execute at invoke time
(before any provider dispatch) while a real sandbox RUNNER is unavailable
(``graph_compiler._sandbox_enforcement_available`` feature-detects
``tinyassets.sandbox_policy.coding_nodes_runnable`` — False on S1 AND on S1+S3,
because S3 is ENFORCEMENT-only; the per-job runner that actually confines +
executes such a node is a separate host-approved Phase-2 slice). NOT bypassable
by an env var (Codex r14 #1). So S1 alone SEEDS the reference as a
discoverable/remixable TEMPLATE, but it cannot RUN unconfined (Codex r13 #1).
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

# Packaged-design manifest (Codex r10 #4): the design_ids the package MUST ship
# and that SHOULD seed healthy. An empty designs dir / a dropped artifact would
# otherwise make ``load_design_artifacts`` return [] and the seed report all-empty
# — a BROKEN package looking healthy. This is a PACKAGING + HEALTH invariant: the
# seed marks a missing packaged design loudly
# (``failed:[<missing-packaged-design:...>]``, reflected in ``last_seed_result()``
# + get_status), and CI validates it. It is NOT a boot-readiness gate.
PACKAGED_DESIGN_IDS = frozenset({"patch_loop_reference"})

# Boot-REQUIRED fixtures (PLAN "required seeded fixtures refuse startup"). The
# reference patch loop is a COMMONS FEATURE, not boot-critical — the Forever Rule
# (24/7 uptime) + Hard Rule 4 mean a feature-seed failure must NOT refuse startup
# (Codex r13 #3, reclassified per r15 #4). So this set is EMPTY: nothing here
# fails startup readiness. Feature-seed health is reported LOUDLY (get_status +
# last_seed_result) and gated in CI, without process death. PLAN's refuse-startup
# rule still stands for any genuinely boot-critical fixture added here later.
REQUIRED_DESIGN_IDS: frozenset[str] = frozenset()

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
    when the value is the reserved author, else the value unchanged.

    Defensive against non-strings (Codex r12 #4): only a genuine string is
    stripped/compared. A non-string author is rejected at the public boundary
    (build_branch / create_branch); here we never ``.strip()`` a non-string, so
    even an internal caller can't trigger an AttributeError."""
    if not isinstance(author, str):
        return ""
    return "" if author.strip() == RESERVED_SEED_AUTHOR else author


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

    Rollback QUARANTINE contract (Codex r11 #1): the caller (the seed reconcile)
    must NEVER call this for content whose hash matches a ROLLED-BACK version
    (see ``_content_hash_quarantined``) — republishing rolled-back content active
    functionally bypasses the rollback. So here we just publish: a genuinely new
    content hash mints a fresh ACTIVE version; an existing ACTIVE same-hash
    version dedups to a no-op. We do NOT mint-fresh-active or reactivate on a
    rolled-back dedup hit (that was the r10 bug that resurrected rolled-back
    content); if publish unexpectedly returns a non-active row, log loudly and
    leave it — the health check reports it unhealthy.
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
    version = publish_branch_version(
        base_path, saved, publisher="reference-designs",
        notes=f"reference design seed {tag}",
    )
    if (version.status or "active") != "active":
        # Should be unreachable — the reconcile quarantines rolled-back content
        # before calling us. If it happens, DO NOT resurrect: log and let the
        # health check fail the reference.
        logger.error(
            "reference %s publish dedup'd to a non-active version %s "
            "(status=%s); NOT reactivating (quarantine bypass guard)",
            tag, version.branch_version_id, version.status,
        )


def _authoritative_version_hash(
    base_path: str | Path, source_id: str, fixed_id: str,
) -> str:
    """The version ``content_hash`` the reserved ``fixed_id`` row WOULD carry if
    published with the authoritative content from ``source_id``. The version hash
    includes ``branch_def_id`` (``_canonical_snapshot`` keeps it), so substitute
    ``fixed_id`` before hashing to match the eventual stored version."""
    from tinyassets.branch_versions import _canonical_snapshot, compute_content_hash
    from tinyassets.daemon_server import get_branch_definition

    d = dict(get_branch_definition(base_path, branch_def_id=source_id))
    d["branch_def_id"] = fixed_id
    return compute_content_hash(_canonical_snapshot(d))


def _content_hash_quarantined(
    base_path: str | Path, branch_def_id: str, content_hash: str,
) -> bool:
    """True when ``content_hash`` matches a ROLLED-BACK version for this design
    AND no ACTIVE version already carries it (Codex r11 #1).

    A rolled-back content hash is quarantined: re-activating that exact content —
    whether by reactivating the row or minting a fresh active version with the
    same hash — functionally UNDOES a deliberate security/regression rollback.
    Only genuinely different content (a new hash = a real fix / version bump) or
    an explicit authorized un-rollback may go live again. The active-exists check
    is the Fable belt-and-braces for the un-ORDER-BY'd dedup SELECT: if a
    legitimate active same-hash version already exists, the reference is fine.
    """
    from tinyassets.branch_versions import list_branch_versions

    versions = list_branch_versions(base_path, branch_def_id, limit=200)
    has_rolled_back = any(
        v.content_hash == content_hash and v.status == "rolled_back"
        for v in versions
    )
    has_active = any(
        v.content_hash == content_hash and (v.status or "active") == "active"
        for v in versions
    )
    return has_rolled_back and not has_active


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
    base_path: str | Path,
    expected_fp: str,
    branch_def_id: str,
    authoritative_hash: str,
) -> bool:
    """Healthy = the row's content matches the authoritative build (fingerprint),
    ``published`` set, AND there is an ACTIVE branch version whose ``content_hash``
    equals the AUTHORITATIVE content hash.

    Active-MATCHING-hash, not any-active (Codex r12 #1): "any active version"
    is bypassable — publish A, publish B, roll back B while A stays active leaves
    the row serving rolled-back content B (a fork copies it) yet health reported
    ``present`` because SOME active version (A) existed. Requiring the LIVE
    (active) version to carry the authoritative hash means a rolled-back or
    drifted live version fails health, so the reconcile repairs it (re-publishes
    the authoritative content, subject to the rollback quarantine) or reports
    failed. Also catches an interrupted publication (active version whose content
    != the authoritative artifact).
    """
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.daemon_server import get_branch_definition

    full = get_branch_definition(base_path, branch_def_id=branch_def_id)
    if _content_fingerprint(full) != expected_fp:
        return False
    if not full.get("published"):
        return False
    versions = list_branch_versions(base_path, branch_def_id, limit=200)
    return any(
        (v.status or "active") == "active" and v.content_hash == authoritative_hash
        for v in versions
    )


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

    # Packaged-design manifest (#4, reclassified r15 #4): a PACKAGED design that's
    # missing (or an empty package dir) must FAIL LOUD, not look healthy — record
    # each absent packaged id in ``failed`` so ``last_seed_result()`` / get_status
    # surface it. This is a packaging/health signal, NOT a boot-readiness gate.
    present_ids = {a.get("design_id") for a in artifacts}
    for packaged_id in sorted(PACKAGED_DESIGN_IDS - present_ids):
        logger.error(
            "reference design seeding: PACKAGED artifact %r is missing from the "
            "package (present=%s)", packaged_id, sorted(present_ids),
        )
        results["failed"].append(f"<missing-packaged-design:{packaged_id}>")

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
            # The version content_hash the fixed_id row WOULD carry with the
            # authoritative content — the single source of truth for both the
            # health check (an ACTIVE version must match it) and the rollback
            # quarantine. Computed once (Codex r12 #1).
            auth_hash = _authoritative_version_hash(base_path, correct_id, fixed_id)

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
                base_path, expected_fp, fixed_id, auth_hash
            ):
                results["present"].append(tag)
            elif _content_hash_quarantined(base_path, fixed_id, auth_hash):
                # Rollback QUARANTINE (Codex r11 #1): the authoritative content's
                # hash matches a ROLLED-BACK version (and no active version has
                # it). Re-activating it would resurrect deliberately-rolled-back
                # content — refuse. The reference stays unhealthy until the
                # artifact content actually changes (a new hash = a real fix) or
                # an authorized un-rollback happens.
                logger.error(
                    "reference design %s content is QUARANTINED (matches a "
                    "rolled-back version); refusing to re-activate", tag,
                )
                results["failed"].append(
                    f"<quarantined-rolled-back-content:{artifact['design_id']}>"
                )
            else:
                # Missing, drifted, or partially-published — (re)build the
                # canonical reserved-id row from the authoritative content and
                # publish. Upsert on the fixed id => concurrency-safe.
                _overwrite_reference_content(base_path, fixed_id, correct_id)
                _publish_reference(base_path, fixed_id, tag)
                if _reference_row_is_healthy(
                    base_path, expected_fp, fixed_id, auth_hash
                ):
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


def unhealthy_packaged_designs(results: dict[str, list[str]]) -> list[str]:
    """Return the PACKAGED design_ids that did NOT seed healthy in ``results``.

    A packaged design is healthy only if its tag landed in ``seeded`` or
    ``present``; a total artifact-load failure fails every packaged id. This is a
    packaging/health signal for loud reporting (get_status + logs), NOT a
    startup-readiness gate — the reference seed is a commons FEATURE, so a failure
    is reported, never fatal (Codex r15 #4 reclassification; Forever Rule).
    """
    if "<load-design-artifacts-failed>" in results.get("failed", []):
        return sorted(PACKAGED_DESIGN_IDS)
    healthy_tags = set(results.get("seeded", [])) | set(results.get("present", []))
    unhealthy: list[str] = []
    for design_id in sorted(PACKAGED_DESIGN_IDS):
        prefix = f"design:{design_id}@v"
        if not any(t.startswith(prefix) for t in healthy_tags):
            unhealthy.append(design_id)
    return unhealthy


def reference_designs_live_health(base_path: str | Path) -> dict[str, Any]:
    """Recompute CURRENT reference-design health at READ time — NOT boot-cached
    (Codex r14 #3). ``last_seed_result()`` is boot history; a row deleted after a
    healthy seed would still report healthy from that cache. This checks the LIVE
    registry: for each packaged design, stage the artifact IN MEMORY (no registry
    writes), derive the authoritative fingerprint + version hash, and verify the
    reserved fixed-id row exists with the reserved author AND has an ACTIVE
    version matching the authoritative hash (``_reference_row_is_healthy``).

    Returns ``{"healthy": bool, "unhealthy": [ids], "per_design": {id: bool}}``
    over the PACKAGED designs (the reference is OPTIONAL for startup but its
    health is still reported loudly — r15 #4). Best-effort — never raises; a
    compute failure marks a design unhealthy rather than lying healthy.
    """
    from tinyassets.branch_versions import _canonical_snapshot, compute_content_hash

    per_design: dict[str, bool] = {}
    try:
        artifacts = load_design_artifacts()
    except Exception:  # noqa: BLE001 — a broken package is unhealthy, not fatal
        return {
            "healthy": False,
            "unhealthy": sorted(PACKAGED_DESIGN_IDS),
            "per_design": {},
        }

    for artifact in artifacts:
        design_id = artifact.get("design_id", "")
        try:
            from tinyassets.api.branches import _staged_branch_from_spec

            fixed_id = _reference_branch_id(design_id, artifact["design_version"])
            staged, errors = _staged_branch_from_spec(dict(artifact["spec"]))
            if errors:
                per_design[design_id] = False
                continue
            staged.branch_def_id = fixed_id
            staged_dict = staged.to_dict()
            expected_fp = _content_fingerprint(staged_dict)
            auth_hash = compute_content_hash(_canonical_snapshot(staged_dict))
            row = _get_branch_or_none(base_path, fixed_id)
            per_design[design_id] = bool(
                row is not None
                and (row.get("author") or "") == RESERVED_SEED_AUTHOR
                and _reference_row_is_healthy(
                    base_path, expected_fp, fixed_id, auth_hash,
                )
            )
        except Exception:  # noqa: BLE001 — a compute failure is unhealthy
            logger.exception("live reference-design health check failed for %s", design_id)
            per_design[design_id] = False

    unhealthy = sorted(
        d for d in PACKAGED_DESIGN_IDS if not per_design.get(d, False)
    )
    return {
        "healthy": not unhealthy,
        "unhealthy": unhealthy,
        "per_design": per_design,
    }
